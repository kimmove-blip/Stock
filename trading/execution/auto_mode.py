"""
완전 자동 매매 모드

목적:
- 장중 자동 매매 실행
- CSV 스코어 기반 매수/매도 결정
- 손절/익절 자동 처리

사용법:
    from trading.execution import AutoModeTrader

    trader = AutoModeTrader(
        config=config,
        dry_run=True,
        kis_client=client
    )

    result = trader.run(
        min_score=75,
        versions=['v2', 'v4'],
        buy_conditions='V2>=70 AND V4>=50'
    )
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd

from .base_trader import BaseTrader, TradeResult
from trading.core.config import TradingConfig
from trading.core.exceptions import TradingError, OrderExecutionError
from trading.data import IntradayScoreLoader
from trading.notifications import BaseNotifier


class AutoModeTrader(BaseTrader):
    """완전 자동 매매 트레이더"""

    def __init__(
        self,
        config: Optional[TradingConfig] = None,
        dry_run: bool = False,
        notifier: Optional[BaseNotifier] = None,
        user_id: Optional[int] = None,
        kis_client: Any = None,
        order_executor: Any = None,
        trade_logger: Any = None,
    ):
        """
        Args:
            config: 트레이딩 설정
            dry_run: 테스트 모드
            notifier: 알림 전송자
            user_id: 사용자 ID
            kis_client: KIS API 클라이언트
            order_executor: 주문 실행기
            trade_logger: 거래 로거
        """
        super().__init__(config, dry_run, notifier, user_id)

        self.kis_client = kis_client
        self.order_executor = order_executor
        self.trade_logger = trade_logger

        # 스코어 로더
        self.score_loader = IntradayScoreLoader()

    def run(
        self,
        min_score: int = 75,
        versions: Optional[List[str]] = None,
        buy_conditions: Optional[str] = None,
        sell_conditions: Optional[str] = None,
        investment_amount: Optional[int] = None,
    ) -> TradeResult:
        """자동 매매 실행

        Args:
            min_score: 최소 매수 점수
            versions: 스코어 버전 리스트
            buy_conditions: 매수 조건 문자열 (예: "V2>=70 AND V4>=50")
            sell_conditions: 매도 조건 문자열
            investment_amount: 종목당 투자 금액

        Returns:
            TradeResult
        """
        result = TradeResult(success=True, mode='auto')
        versions = versions or ['v2']

        try:
            # 1. 상태 초기화
            self.reset_daily_state()

            # 2. 장 시간 체크
            can_trade, reason = self.check_market_hours()
            if not can_trade and not self.dry_run:
                self.log(f"거래 불가: {reason}", "WARN")
                result.success = False
                result.errors.append(reason)
                return result

            # 3. 스코어 데이터 로드
            score_data = self.score_loader.load_latest(min_freshness=True)
            if not score_data:
                self.log("최신 스코어 데이터 없음", "WARN")
                result.errors.append("스코어 데이터 없음")
                return result

            self.log(f"스코어 로드: {score_data.record_count}종목, {score_data.age_minutes:.1f}분 전")

            # 4. 보유 종목 조회
            holdings = self._get_holdings()

            # 5. 매도 처리
            sell_result = self._process_sells(
                holdings, score_data.df, sell_conditions
            )
            result.sell_count = sell_result['count']
            result.sell_amount = sell_result['amount']
            result.realized_profit = sell_result['profit']
            result.trades.extend(sell_result['trades'])

            # 6. 매수 처리
            buy_result = self._process_buys(
                score_data.df,
                holdings,
                min_score,
                versions,
                buy_conditions,
                investment_amount
            )
            result.buy_count = buy_result['count']
            result.buy_amount = buy_result['amount']
            result.trades.extend(buy_result['trades'])

            # 7. 요약 알림
            if result.buy_count > 0 or result.sell_count > 0:
                self.notify_summary(
                    result.buy_count,
                    result.sell_count,
                    result.realized_profit
                )

            self.log(f"완료: 매수 {result.buy_count}건, 매도 {result.sell_count}건")

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.log(f"오류: {e}", "ERROR")

        return result

    def _get_holdings(self) -> List[Dict]:
        """보유 종목 조회"""
        if self.dry_run:
            return []

        if self.kis_client:
            try:
                response = self.kis_client.get_balance()
                return response.get('holdings', [])
            except Exception as e:
                self.log(f"보유종목 조회 오류: {e}", "ERROR")
                return []

        return []

    def _process_sells(
        self,
        holdings: List[Dict],
        score_df: pd.DataFrame,
        sell_conditions: Optional[str]
    ) -> Dict:
        """매도 처리"""
        result = {
            'count': 0,
            'amount': 0,
            'profit': 0,
            'trades': []
        }

        if not holdings:
            return result

        # 스코어 딕셔너리 생성
        score_dict = {}
        for _, row in score_df.iterrows():
            code = row['code']
            score_dict[code] = {
                'v1': int(row.get('v1', 0)),
                'v2': int(row.get('v2', 0)),
                'v4': int(row.get('v4', 0)),
                'v5': int(row.get('v5', 0)),
                'close': row.get('close', 0),
            }

        for holding in holdings:
            stock_code = holding.get('stock_code')
            stock_name = holding.get('stock_name', stock_code)
            quantity = holding.get('quantity', 0)
            avg_price = holding.get('avg_price', 0)

            if quantity <= 0:
                continue

            # 현재가 조회
            current_price = holding.get('current_price', 0)
            if stock_code in score_dict:
                current_price = score_dict[stock_code].get('close', current_price)

            if current_price <= 0:
                continue

            # 수익률 계산
            profit_rate = (current_price - avg_price) / avg_price if avg_price > 0 else 0

            # 매도 조건 체크
            sell_reasons = []

            # 1. 손절
            if profit_rate <= self.config.stop_loss_pct:
                sell_reasons.append(f"손절 ({profit_rate*100:.1f}%)")

            # 2. 익절 (설정된 경우)
            if self.config.take_profit_pct and profit_rate >= self.config.take_profit_pct:
                sell_reasons.append(f"익절 ({profit_rate*100:.1f}%)")

            # 3. 점수 하락
            if stock_code in score_dict:
                v2_score = score_dict[stock_code].get('v2', 0)
                if v2_score < self.config.min_hold_score:
                    sell_reasons.append(f"점수하락 (V2={v2_score})")

            # 4. 커스텀 매도 조건
            if sell_conditions and stock_code in score_dict:
                if self._evaluate_conditions(sell_conditions, score_dict[stock_code]):
                    sell_reasons.append("조건충족")

            # 매도 실행
            if sell_reasons:
                reason = ", ".join(sell_reasons)

                if self.dry_run:
                    self.log(f"[DRY] 매도: {stock_name} {quantity}주 ({reason})")
                else:
                    success = self._execute_sell(
                        stock_code, stock_name, quantity, current_price
                    )
                    if success:
                        result['count'] += 1
                        result['amount'] += quantity * current_price
                        result['profit'] += int((current_price - avg_price) * quantity)

                        self.add_traded_stock(stock_code)
                        self.notify_sell(
                            stock_code, stock_name, quantity,
                            current_price, profit_rate, reason
                        )

                result['trades'].append({
                    'type': 'sell',
                    'code': stock_code,
                    'name': stock_name,
                    'quantity': quantity,
                    'price': current_price,
                    'profit_rate': profit_rate,
                    'reason': reason,
                })

        return result

    def _process_buys(
        self,
        score_df: pd.DataFrame,
        holdings: List[Dict],
        min_score: int,
        versions: List[str],
        buy_conditions: Optional[str],
        investment_amount: Optional[int]
    ) -> Dict:
        """매수 처리"""
        result = {
            'count': 0,
            'amount': 0,
            'trades': []
        }

        # 보유 종목 코드
        holding_codes = {h.get('stock_code') for h in holdings}

        # 남은 슬롯 수
        remaining_slots = self.config.max_holdings - len(holdings)
        if remaining_slots <= 0:
            self.log(f"최대 보유종목 도달: {len(holdings)}/{self.config.max_holdings}")
            return result

        # 투자 금액
        invest_amount = investment_amount or self.config.max_per_stock

        # 매수 후보 필터링
        candidates = []
        for _, row in score_df.iterrows():
            code = row['code']

            # 이미 보유 중
            if code in holding_codes:
                continue

            # 당일 거래 종목
            if self.is_traded_today(code):
                continue

            scores = {
                'v1': int(row.get('v1', 0)),
                'v2': int(row.get('v2', 0)),
                'v4': int(row.get('v4', 0)),
                'v5': int(row.get('v5', 0)),
            }

            # 점수 필터
            main_score = scores.get(versions[0], 0)
            if main_score < min_score:
                continue

            # 커스텀 조건
            if buy_conditions:
                if not self._evaluate_conditions(buy_conditions, scores):
                    continue

            candidates.append({
                'code': code,
                'name': row.get('name', code),
                'close': row.get('close', 0),
                'scores': scores,
                'signals': row.get('signals', ''),
            })

        # 점수순 정렬
        candidates.sort(key=lambda x: x['scores'].get(versions[0], 0), reverse=True)

        # 매수 실행
        for candidate in candidates[:remaining_slots]:
            if result['count'] >= self.config.max_daily_trades:
                break

            code = candidate['code']
            name = candidate['name']
            price = int(candidate['close'])
            score = candidate['scores'].get(versions[0], 0)

            if price <= 0:
                continue

            quantity = self.calculate_position_size(price, invest_amount)
            if quantity <= 0:
                continue

            if self.dry_run:
                self.log(f"[DRY] 매수: {name} {quantity}주 @ {price:,}원 (V2={score})")
                result['count'] += 1
                result['amount'] += quantity * price
            else:
                success = self._execute_buy(code, name, quantity, price)
                if success:
                    result['count'] += 1
                    result['amount'] += quantity * price
                    self.add_traded_stock(code)
                    self.notify_buy(code, name, quantity, price, score)

            result['trades'].append({
                'type': 'buy',
                'code': code,
                'name': name,
                'quantity': quantity,
                'price': price,
                'score': score,
            })

        return result

    def _execute_buy(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: int
    ) -> bool:
        """매수 주문 실행"""
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

    def _execute_sell(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: int
    ) -> bool:
        """매도 주문 실행"""
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

    def _evaluate_conditions(self, condition_str: str, scores: Dict) -> bool:
        """조건 문자열 평가

        예: "V2>=70 AND V4>=50"
        """
        import re

        if not condition_str:
            return False

        # AND/OR 분리
        parts = re.split(r'\s+(AND|OR)\s+', condition_str, flags=re.IGNORECASE)

        results = []
        connectors = []

        for part in parts:
            part = part.strip()
            if part.upper() in ('AND', 'OR'):
                connectors.append(part.upper())
            else:
                # V2>=70 형식 파싱
                match = re.match(r'^(V\d+)\s*(>=|<=|>|<|=)\s*(\d+)$', part, re.IGNORECASE)
                if match:
                    score_key = match.group(1).lower()
                    op = match.group(2)
                    target = int(match.group(3))
                    value = scores.get(score_key, 0)

                    if op == '>=':
                        results.append(value >= target)
                    elif op == '<=':
                        results.append(value <= target)
                    elif op == '>':
                        results.append(value > target)
                    elif op == '<':
                        results.append(value < target)
                    elif op == '=':
                        results.append(value == target)

        if not results:
            return False

        # 조건 조합
        final = results[0]
        for i, connector in enumerate(connectors):
            if i + 1 < len(results):
                if connector == 'AND':
                    final = final and results[i + 1]
                else:
                    final = final or results[i + 1]

        return final
