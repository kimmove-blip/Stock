"""
반자동 매매 모드 (제안 기반)

목적:
- 매수 제안 생성 및 관리
- 사용자 승인 후 자동 실행
- 손절만 자동 처리

사용법:
    from trading.execution import SemiAutoTrader

    trader = SemiAutoTrader(
        config=config,
        dry_run=True,
        kis_client=client,
        suggestion_manager=manager
    )

    # 제안 생성
    result = trader.create_suggestions(score_df, min_score=75)

    # 승인된 제안 실행
    result = trader.execute_approved()
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd

from .base_trader import BaseTrader, TradeResult
from trading.core.config import TradingConfig
from trading.notifications import BaseNotifier


class SemiAutoTrader(BaseTrader):
    """반자동 매매 트레이더 (제안 기반)"""

    def __init__(
        self,
        config: Optional[TradingConfig] = None,
        dry_run: bool = False,
        notifier: Optional[BaseNotifier] = None,
        user_id: Optional[int] = None,
        kis_client: Any = None,
        order_executor: Any = None,
        suggestion_manager: Any = None,
    ):
        """
        Args:
            config: 트레이딩 설정
            dry_run: 테스트 모드
            notifier: 알림 전송자
            user_id: 사용자 ID
            kis_client: KIS API 클라이언트
            order_executor: 주문 실행기
            suggestion_manager: 매수 제안 관리자
        """
        super().__init__(config, dry_run, notifier, user_id)

        self.kis_client = kis_client
        self.order_executor = order_executor
        self.suggestion_manager = suggestion_manager

    def run(self) -> TradeResult:
        """반자동 매매 실행

        1. 손절 대상 자동 매도
        2. 승인된 제안 실행
        3. 새 제안 생성
        """
        result = TradeResult(success=True, mode='semi-auto')

        try:
            self.reset_daily_state()

            # 1. 장 시간 체크
            can_trade, reason = self.check_market_hours()
            if not can_trade and not self.dry_run:
                self.log(f"거래 불가: {reason}", "WARN")
                result.errors.append(reason)
                return result

            # 2. 보유 종목 조회
            holdings = self._get_holdings()

            # 3. 손절 자동 처리
            stop_loss_result = self._process_stop_loss(holdings)
            result.sell_count = stop_loss_result['count']
            result.realized_profit = stop_loss_result['profit']
            result.trades.extend(stop_loss_result['trades'])

            # 4. 승인된 제안 실행
            approved_result = self._execute_approved_suggestions()
            result.executed_suggestions = approved_result['count']
            result.buy_count = approved_result['count']
            result.buy_amount = approved_result['amount']
            result.trades.extend(approved_result['trades'])

            self.log(f"완료: 손절 {stop_loss_result['count']}건, 제안실행 {approved_result['count']}건")

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.log(f"오류: {e}", "ERROR")

        return result

    def create_suggestions(
        self,
        score_df: pd.DataFrame,
        min_score: int = 75,
        version: str = 'v2',
        max_suggestions: int = 10
    ) -> TradeResult:
        """매수 제안 생성

        Args:
            score_df: 스코어 DataFrame
            min_score: 최소 점수
            version: 스코어 버전
            max_suggestions: 최대 제안 수

        Returns:
            TradeResult (suggestions_created 포함)
        """
        result = TradeResult(success=True, mode='suggestion')

        try:
            # 보유 종목 코드
            holdings = self._get_holdings()
            holding_codes = {h.get('stock_code') for h in holdings}

            # 기존 제안 종목
            pending_codes = set()
            if self.suggestion_manager:
                pending = self.suggestion_manager.get_pending_suggestions(self.user_id)
                pending_codes = {s.get('stock_code') for s in pending}

            # 후보 필터링
            candidates = []
            for _, row in score_df.iterrows():
                code = row['code']

                # 이미 보유 또는 제안 중
                if code in holding_codes or code in pending_codes:
                    continue

                # 당일 거래
                if self.is_traded_today(code):
                    continue

                score = int(row.get(version, 0))
                if score < min_score:
                    continue

                candidates.append({
                    'code': code,
                    'name': row.get('name', code),
                    'close': row.get('close', 0),
                    'score': score,
                    'signals': row.get('signals', ''),
                })

            # 점수순 정렬
            candidates.sort(key=lambda x: x['score'], reverse=True)

            # 제안 생성
            created = 0
            for candidate in candidates[:max_suggestions]:
                if created >= max_suggestions:
                    break

                suggestion = self._create_suggestion(candidate)
                if suggestion:
                    created += 1
                    result.trades.append({
                        'type': 'suggestion',
                        'code': candidate['code'],
                        'name': candidate['name'],
                        'score': candidate['score'],
                    })

                    # 알림
                    self._notify_suggestion(candidate)

            result.suggestions_created = created
            self.log(f"제안 생성: {created}건")

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.log(f"제안 생성 오류: {e}", "ERROR")

        return result

    def _get_holdings(self) -> List[Dict]:
        """보유 종목 조회"""
        if self.dry_run or not self.kis_client:
            return []

        try:
            response = self.kis_client.get_balance()
            return response.get('holdings', [])
        except Exception as e:
            self.log(f"보유종목 조회 오류: {e}", "ERROR")
            return []

    def _process_stop_loss(self, holdings: List[Dict]) -> Dict:
        """손절 자동 처리"""
        result = {
            'count': 0,
            'profit': 0,
            'trades': []
        }

        for holding in holdings:
            stock_code = holding.get('stock_code')
            stock_name = holding.get('stock_name', stock_code)
            quantity = holding.get('quantity', 0)
            avg_price = holding.get('avg_price', 0)
            current_price = holding.get('current_price', 0)

            if quantity <= 0 or avg_price <= 0 or current_price <= 0:
                continue

            profit_rate = (current_price - avg_price) / avg_price

            # 손절 조건
            if profit_rate <= self.config.stop_loss_pct:
                reason = f"손절 ({profit_rate*100:.1f}%)"

                if self.dry_run:
                    self.log(f"[DRY] 손절: {stock_name} {quantity}주")
                else:
                    success = self._execute_sell(stock_code, stock_name, quantity, current_price)
                    if success:
                        result['count'] += 1
                        result['profit'] += int((current_price - avg_price) * quantity)
                        self.add_traded_stock(stock_code)
                        self.notify_sell(
                            stock_code, stock_name, quantity,
                            current_price, profit_rate, reason
                        )

                result['trades'].append({
                    'type': 'stop_loss',
                    'code': stock_code,
                    'name': stock_name,
                    'quantity': quantity,
                    'price': current_price,
                    'profit_rate': profit_rate,
                })

        return result

    def _execute_approved_suggestions(self) -> Dict:
        """승인된 제안 실행"""
        result = {
            'count': 0,
            'amount': 0,
            'trades': []
        }

        if not self.suggestion_manager:
            return result

        try:
            approved = self.suggestion_manager.get_approved_suggestions(self.user_id)

            for suggestion in approved:
                stock_code = suggestion.get('stock_code')
                stock_name = suggestion.get('stock_name', stock_code)
                target_price = suggestion.get('target_price', 0)
                quantity = suggestion.get('quantity', 0)

                if quantity <= 0:
                    continue

                # 현재가 조회 (필요시)
                current_price = target_price

                if self.dry_run:
                    self.log(f"[DRY] 제안 실행: {stock_name} {quantity}주")
                    result['count'] += 1
                    result['amount'] += quantity * current_price
                else:
                    success = self._execute_buy(stock_code, stock_name, quantity, current_price)
                    if success:
                        result['count'] += 1
                        result['amount'] += quantity * current_price
                        self.add_traded_stock(stock_code)

                        # 제안 상태 업데이트
                        self.suggestion_manager.mark_executed(suggestion.get('id'))

                        self.notify_buy(stock_code, stock_name, quantity, current_price)

                result['trades'].append({
                    'type': 'suggestion_executed',
                    'code': stock_code,
                    'name': stock_name,
                    'quantity': quantity,
                    'price': current_price,
                })

        except Exception as e:
            self.log(f"제안 실행 오류: {e}", "ERROR")

        return result

    def _create_suggestion(self, candidate: Dict) -> Optional[Dict]:
        """매수 제안 생성"""
        if not self.suggestion_manager:
            return None

        try:
            price = int(candidate['close'])
            quantity = self.calculate_position_size(price)

            # 목표가/손절가 계산
            target_price = int(price * (1 + self.config.target_profit_pct))
            stop_loss_price = int(price * (1 + self.config.stop_loss_pct))

            suggestion = {
                'user_id': self.user_id,
                'stock_code': candidate['code'],
                'stock_name': candidate['name'],
                'score': candidate['score'],
                'signals': candidate.get('signals', ''),
                'current_price': price,
                'target_price': target_price,
                'stop_loss_price': stop_loss_price,
                'quantity': quantity,
                'expires_at': datetime.now() + timedelta(hours=self.config.suggestion_expire_hours),
            }

            if self.dry_run:
                self.log(f"[DRY] 제안: {candidate['name']} (점수: {candidate['score']})")
                return suggestion

            result = self.suggestion_manager.create_suggestion(suggestion)
            return result

        except Exception as e:
            self.log(f"제안 생성 오류 [{candidate['code']}]: {e}", "ERROR")
            return None

    def _execute_buy(self, stock_code: str, stock_name: str, quantity: int, price: int) -> bool:
        """매수 주문"""
        try:
            if self.order_executor:
                result = self.order_executor.buy(
                    stock_code=stock_code,
                    quantity=quantity,
                    price=price
                )
                return result.get('success', False)
            return False
        except Exception as e:
            self.log(f"매수 주문 오류 [{stock_name}]: {e}", "ERROR")
            return False

    def _execute_sell(self, stock_code: str, stock_name: str, quantity: int, price: int) -> bool:
        """매도 주문"""
        try:
            if self.order_executor:
                result = self.order_executor.sell(
                    stock_code=stock_code,
                    quantity=quantity,
                    price=price
                )
                return result.get('success', False)
            return False
        except Exception as e:
            self.log(f"매도 주문 오류 [{stock_name}]: {e}", "ERROR")
            return False

    def _notify_suggestion(self, candidate: Dict) -> None:
        """제안 알림"""
        price = int(candidate['close'])
        target = int(price * (1 + self.config.target_profit_pct))
        stop = int(price * (1 + self.config.stop_loss_pct))

        msg = f"💡 [매수 제안] {candidate['name']} ({candidate['code']})\n"
        msg += f"현재가: {price:,}원\n"
        msg += f"점수: {candidate['score']}점\n"
        msg += f"목표가: {target:,}원 (+{self.config.target_profit_pct*100:.0f}%)\n"
        msg += f"손절가: {stop:,}원 ({self.config.stop_loss_pct*100:.0f}%)"

        self.notifier.send_message(msg)
