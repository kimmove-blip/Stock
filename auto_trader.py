#!/usr/bin/env python3
"""
자동매매 시스템

사용법:
    python auto_trader.py              # 1회 실행
    python auto_trader.py --dry-run    # 테스트 실행 (주문 X)
    python auto_trader.py --report     # 성과 리포트만 출력

cron 설정 예시:
    # 매일 08:50 (장 시작 전)
    50 8 * * 1-5 /home/kimhc/Stock/venv/bin/python /home/kimhc/Stock/auto_trader.py
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent))

from api.services.kis_client import KISClient
from trading.order_executor import OrderExecutor
from trading.risk_manager import RiskManager, TradingLimits
from trading.trade_logger import TradeLogger, BuySuggestionManager
from technical_analyst import TechnicalAnalyst
from config import AutoTraderConfig, TelegramConfig, OUTPUT_DIR, SIGNAL_NAMES_KR


def get_tick_size(price: int) -> int:
    """주가에 따른 호가 단위 반환"""
    if price < 1000:
        return 1
    elif price < 5000:
        return 5
    elif price < 10000:
        return 10
    elif price < 50000:
        return 50
    elif price < 100000:
        return 100
    elif price < 500000:
        return 500
    else:
        return 1000


def round_to_tick(price: int, round_down: bool = True) -> int:
    """호가 단위로 반올림/내림"""
    tick = get_tick_size(price)
    if round_down:
        return (price // tick) * tick  # 내림
    else:
        return ((price + tick - 1) // tick) * tick  # 올림


class TelegramNotifier:
    """텔레그램 + 푸시 알림 발송"""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True, user_id: int = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.user_id = user_id  # 푸시 알림용

    def send(self, message: str):
        """메시지 발송"""
        if not self.enabled:
            return

        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            print(f"텔레그램 발송 실패: {e}")

    def notify_buy(self, stock_name: str, price: int, quantity: int):
        """매수 체결 알림"""
        msg = f"<b>[매수 체결]</b>\n{stock_name}\n{price:,}원 x {quantity}주"
        self.send(msg)

    def notify_sell(self, stock_name: str, price: int, quantity: int, profit_rate: float, reason: str):
        """매도 체결 알림"""
        emoji = "" if profit_rate >= 0 else ""
        rate_str = f"+{profit_rate*100:.1f}%" if profit_rate >= 0 else f"{profit_rate*100:.1f}%"
        msg = f"<b>{emoji} [매도 체결]</b>\n{stock_name}\n{price:,}원 ({rate_str})\n사유: {reason}"
        self.send(msg)

    def notify_stop_loss(self, stock_name: str, price: int, profit_rate: float):
        """손절 알림"""
        msg = f"<b>[손절]</b>\n{stock_name}\n{price:,}원 ({profit_rate*100:.1f}%)"
        self.send(msg)

    def notify_signal(self, stock_name: str, signals: List[str]):
        """매도 신호 알림"""
        signals_kr = [SIGNAL_NAMES_KR.get(s, s) for s in signals]
        msg = f"<b>[매도 신호]</b>\n{stock_name}\n{', '.join(signals_kr)}"
        self.send(msg)

    def notify_summary(self, buy_count: int, sell_count: int, total_profit: int):
        """일일 요약 알림 (체결 없으면 생략)"""
        if buy_count == 0 and sell_count == 0:
            return  # 체결 없으면 알림 안 보냄

        msg = (
            f"<b>[자동매매 완료]</b>\n"
            f"매수: {buy_count}건\n"
            f"매도: {sell_count}건\n"
            f"일일 손익: {total_profit:+,}원"
        )
        self.send(msg)

    def notify_error(self, error_msg: str):
        """오류 알림"""
        msg = f"<b>[오류]</b>\n{error_msg}"
        self.send(msg)

    def send_push(self, title: str, body: str, url: str = None):
        """앱 푸시 알림 전송"""
        if not self.enabled or not self.user_id:
            return

        try:
            from api.routers.push import send_push_to_user
            send_push_to_user(self.user_id, title, body, url)
        except Exception as e:
            print(f"푸시 알림 전송 실패: {e}")

    def notify_buy_suggestion(
        self,
        stock_name: str,
        stock_code: str,
        score: int,
        probability: float,
        confidence: float,
        current_price: int,
        recommended_price: int,
        target_price: int,
        stop_loss_price: int,
        signals: List[str],
        expire_hours: int = 24
    ):
        """매수 제안 알림 (semi-auto 모드)"""
        signals_kr = [SIGNAL_NAMES_KR.get(s, s) for s in signals[:4]]

        msg = f"""📊 <b>[매수 제안]</b> {stock_name} ({stock_code})

<b>분석 결과</b>
• 점수: {score}점
• 상승확률: {probability:.0f}%
• 신뢰도: {confidence:.0f}%

<b>가격 정보</b>
• 현재가: {current_price:,}원
• 추천 매수가: {recommended_price:,}원
• 목표가: {target_price:,}원 (+{((target_price/recommended_price)-1)*100:.0f}%)
• 손절가: {stop_loss_price:,}원 ({((stop_loss_price/recommended_price)-1)*100:.0f}%)

<b>주요 신호</b>
{chr(10).join(['  • ' + s for s in signals_kr])}

<b>승인 방법</b>
대시보드에서 승인/거부하세요.

⏰ {expire_hours}시간 후 자동 만료"""

        self.send(msg)

        # 앱 푸시 알림도 전송
        push_body = f"{stock_name} {score}점 | 추천가 {recommended_price:,}원"
        self.send_push(
            title="📊 매수 제안",
            body=push_body,
            url=f"/stock/{stock_code}"
        )

    def notify_suggestion_executed(self, stock_name: str, price: int, quantity: int):
        """제안 매수 실행 알림"""
        msg = f"<b>✅ [제안 매수 완료]</b>\n{stock_name}\n{price:,}원 x {quantity}주\n\n추천 매수가 도달로 자동 매수"
        self.send(msg)


class AutoTrader:
    """자동매매 시스템"""

    def __init__(self, dry_run: bool = False, user_id: int = None, user_config: dict = None):
        """
        Args:
            dry_run: True면 주문을 실제로 실행하지 않음
            user_id: 사용자 ID (다중 사용자 지원)
            user_config: 사용자별 설정 (API 키, 텔레그램 등)
        """
        self.dry_run = dry_run
        self.user_id = user_id
        self.user_config = user_config or {}
        self.config = AutoTraderConfig

        # 사용자별 API 키가 있으면 사용, 없으면 환경변수 사용
        app_key = self.user_config.get('app_key')
        app_secret = self.user_config.get('app_secret')
        account_number = self.user_config.get('account_number')
        is_mock = self.user_config.get('is_mock', self.config.IS_VIRTUAL)

        # KIS 클라이언트 초기화
        if app_key and app_secret and account_number:
            self.kis_client = KISClient(
                is_virtual=is_mock,
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number
            )
        else:
            self.kis_client = KISClient(is_virtual=self.config.IS_VIRTUAL)

        # 모듈 초기화 - 순서 중요: logger를 먼저 초기화해야 사용자 설정 조회 가능
        self.logger = TradeLogger()
        self.executor = OrderExecutor(self.kis_client)

        # 사용자 설정에서 stock_ratio 가져오기 (DB 설정 > config 설정)
        user_settings = self.logger.get_auto_trade_settings(user_id) if user_id else None
        max_position_pct = self.config.MAX_POSITION_PCT  # 기본값 (config에서)
        stop_loss_pct = self.config.STOP_LOSS_PCT
        max_holdings = self.config.MAX_HOLDINGS
        max_daily_trades = self.config.MAX_DAILY_TRADES
        max_hold_days = self.config.MAX_HOLD_DAYS
        min_buy_score = self.config.MIN_BUY_SCORE

        if user_settings:
            # 사용자 설정이 있으면 해당 값 사용
            stock_ratio = user_settings.get('stock_ratio')
            if stock_ratio and stock_ratio > 0:
                max_position_pct = stock_ratio / 100  # 10% -> 0.1
                print(f"[AutoTrader] 사용자 {user_id} stock_ratio: {stock_ratio}% -> max_position_pct: {max_position_pct}")

            if user_settings.get('stop_loss_rate'):
                stop_loss_pct = -abs(user_settings['stop_loss_rate']) / 100

            if user_settings.get('max_holdings'):
                max_holdings = user_settings['max_holdings']

            if user_settings.get('max_daily_trades'):
                max_daily_trades = user_settings['max_daily_trades']

            if user_settings.get('max_holding_days'):
                max_hold_days = user_settings['max_holding_days']

            if user_settings.get('min_buy_score'):
                min_buy_score = user_settings['min_buy_score']

        self.risk_manager = RiskManager(TradingLimits(
            max_position_pct=max_position_pct,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=self.config.TAKE_PROFIT_PCT,
            max_daily_trades=max_daily_trades,
            max_holdings=max_holdings,
            max_hold_days=max_hold_days,
            min_buy_score=min_buy_score,
            min_hold_score=self.config.MIN_HOLD_SCORE,
            min_volume_ratio=self.config.MIN_VOLUME_RATIO,
        ))
        self.suggestion_manager = BuySuggestionManager(user_id=user_id)
        self.analyst = TechnicalAnalyst()

        # 사용자별 텔레그램 + 푸시 설정
        telegram_chat_id = self.user_config.get('telegram_chat_id') or TelegramConfig.CHAT_ID
        self.notifier = TelegramNotifier(
            bot_token=TelegramConfig.BOT_TOKEN,
            user_id=user_id,  # 푸시 알림용
            chat_id=telegram_chat_id,
            enabled=self.config.TELEGRAM_NOTIFY and not dry_run
        )

        # 모의투자 가상 잔고 초기화
        if is_mock:
            initial_cash = getattr(self.config, 'VIRTUAL_INITIAL_CASH', 100_000_000)
            self.logger.init_virtual_balance(initial_cash, user_id=user_id)

        # 실행 통계
        self.stats = {
            "buy_orders": [],
            "sell_orders": [],
            "total_profit": 0,
        }

    def _save_alert_history(self, stock_code: str, stock_name: str, alert_type: str, message: str):
        """알림 기록 저장"""
        if not self.user_id:
            return
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            with db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO alert_history (user_id, stock_code, stock_name, alert_type, message)
                    VALUES (?, ?, ?, ?, ?)
                """, (self.user_id, stock_code, stock_name, alert_type, message))
                conn.commit()
        except Exception as e:
            print(f"알림 기록 저장 실패: {e}")

    def load_analysis_results(self) -> Optional[List[Dict]]:
        """
        최신 분석 결과 로드

        Returns:
            종목 분석 결과 리스트
        """
        # 오늘 또는 가장 최근 분석 파일 찾기
        today = datetime.now()

        for days_back in range(7):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%Y%m%d")
            json_path = OUTPUT_DIR / f"top100_{date_str}.json"

            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"분석 결과 로드: {json_path.name}")
                return data.get("stocks", [])

        print("분석 결과 파일을 찾을 수 없습니다.")
        return None

    def filter_buy_candidates(self, stocks: List[Dict]) -> List[Dict]:
        """
        매수 후보 필터링

        Args:
            stocks: 분석 결과 종목 리스트

        Returns:
            필터링된 매수 후보 리스트
        """
        candidates = []

        for stock in stocks:
            score = stock.get("score", 0)
            signals = stock.get("signals", []) + stock.get("patterns", [])

            # 점수 조건 (사용자 설정 min_buy_score 사용)
            if score < self.risk_manager.limits.min_buy_score:
                continue

            # 거래량 조건
            volume_ratio = stock.get("indicators", {}).get("volume_ratio", 0)
            if volume_ratio < self.config.MIN_VOLUME_RATIO:
                continue

            # 신뢰도 높은 신호 포함 여부
            has_strong_signal = any(
                s in signals for s in self.config.STRONG_BUY_SIGNALS
            )
            if not has_strong_signal:
                continue

            # 추천 매수가 계산 (피보나치 61.8% 기반)
            current_price = int(stock.get("close", 0))
            stock_code = stock.get("code")
            indicators = stock.get("indicators", {})

            # bb_mid = 피보나치 61.8% 되돌림 (60일 고점 기준)
            fib_618 = indicators.get("bb_mid", current_price * 0.97)

            # 추천 매수가 = 피보나치 61.8% 지지선
            # 매수 밴드 상한 = 추천가 +5% (현재가가 추천가의 105% 이내면 매수)
            recommended_price = int(min(fib_618, current_price * 0.97))
            buy_band_high = int(recommended_price * 1.05)

            # 목표가 +20%, 손절가 -10%
            target_price = stock.get("target_price") or int(recommended_price * 1.20)
            stop_loss_price = int(recommended_price * 0.90)

            candidates.append({
                "stock_code": stock_code,
                "stock_name": stock.get("name"),
                "market": stock.get("market", "KOSDAQ"),
                "score": score,
                "signals": signals,
                "volume_ratio": volume_ratio,
                "current_price": current_price,
                "recommended_price": recommended_price,
                "buy_band_high": buy_band_high,
                "target_price": target_price,
                "stop_loss_price": stop_loss_price,
                "expected_return": stock.get("expected_return"),
            })

        # 점수순 정렬
        candidates.sort(key=lambda x: x["score"], reverse=True)

        return candidates

    def get_current_signals(self, stock_code: str, analysis_stocks: List[Dict]) -> List[str]:
        """종목의 현재 신호 조회"""
        for stock in analysis_stocks:
            if stock.get("code") == stock_code:
                return stock.get("signals", []) + stock.get("patterns", [])
        return []

    def get_current_score(self, stock_code: str, analysis_stocks: List[Dict]) -> int:
        """종목의 현재 점수 조회"""
        for stock in analysis_stocks:
            if stock.get("code") == stock_code:
                return stock.get("score", 50)
        return 50  # 분석 데이터 없으면 기본 50점

    def check_market_hours(self) -> bool:
        """장 운영 시간 체크"""
        now = datetime.now()

        # 주말 제외
        if now.weekday() >= 5:
            print("주말에는 거래하지 않습니다.")
            return False

        # 장 시간 체크 (09:00 ~ 15:30)
        market_open = now.replace(hour=9, minute=0, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)

        if now < market_open or now > market_close:
            print(f"장 운영 시간이 아닙니다. (현재: {now.strftime('%H:%M')})")
            return False

        return True

    def execute_sell_orders(self, sell_list: List[Dict]) -> List[Dict]:
        """
        매도 주문 실행

        Args:
            sell_list: 매도 대상 종목 리스트

        Returns:
            주문 결과 리스트
        """
        results = []

        for item in sell_list:
            stock_code = item["stock_code"]
            stock_name = item.get("stock_name", stock_code)
            quantity = item["quantity"]
            sell_reasons = item.get("sell_reasons", [])
            profit_rate = item.get("profit_rate", 0)

            print(f"\n매도: {stock_name} ({stock_code}) {quantity}주")
            print(f"  사유: {', '.join(sell_reasons)}")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "stock_code": stock_code, "dry_run": True}
            else:
                result = self.executor.place_sell_order(
                    stock_code=stock_code,
                    quantity=quantity
                )

            if result.get("success"):
                # 손익 계산 (수수료/세금 포함)
                sell_price = item.get("current_price", 0)
                avg_price = item.get("avg_price", sell_price)
                market = item.get("market", "KOSDAQ")

                # 수수료/세금 계산
                buy_amount = avg_price * quantity
                sell_amount = sell_price * quantity
                buy_commission = int(buy_amount * self.config.COMMISSION_RATE)
                sell_commission = int(sell_amount * self.config.COMMISSION_RATE)
                if market == "KOSPI":
                    sell_tax = int(sell_amount * self.config.TAX_RATE_KOSPI)
                else:
                    sell_tax = int(sell_amount * self.config.TAX_RATE_KOSDAQ)
                total_fees = buy_commission + sell_commission + sell_tax

                # 실현손익 = 매도금액 - 매수금액 - 수수료/세금
                realized_profit = sell_amount - buy_amount - total_fees
                realized_rate = realized_profit / buy_amount if buy_amount > 0 else 0

                # 거래 기록
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="sell",
                    quantity=quantity,
                    price=sell_price,
                    order_no=result.get("order_no"),
                    trade_reason=", ".join(sell_reasons),
                    status="executed" if not self.dry_run else "dry_run",
                    profit_loss=realized_profit,
                    profit_rate=realized_rate
                )

                # 보유 종목에서 제거
                if not self.dry_run:
                    # 모의투자 가상 잔고 업데이트 (매도)
                    if self.config.IS_VIRTUAL:
                        # 매도 후 현금 = 매도금액 - 매도수수료 - 세금
                        net_sell_amount = sell_amount - sell_commission - sell_tax
                        self.logger.update_virtual_balance_on_sell(net_sell_amount, buy_amount, realized_profit)

                    self.logger.remove_holding(stock_code)

                # 알림
                reason_str = sell_reasons[0] if sell_reasons else "조건 충족"
                if "손절" in reason_str:
                    self.notifier.notify_stop_loss(
                        stock_name, item.get("current_price", 0), profit_rate
                    )
                else:
                    self.notifier.notify_sell(
                        stock_name, item.get("current_price", 0),
                        quantity, profit_rate, reason_str
                    )

                self.stats["sell_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def execute_buy_orders(self, buy_list: List[Dict], investment_per_stock: int) -> List[Dict]:
        """
        매수 주문 실행

        Args:
            buy_list: 매수 대상 종목 리스트
            investment_per_stock: 종목당 투자금액

        Returns:
            주문 결과 리스트
        """
        results = []

        for item in buy_list:
            stock_code = item["stock_code"]
            stock_name = item.get("stock_name", stock_code)
            # 현재가 조회 (실시간)
            current_price = self.executor.get_current_price(stock_code)
            if not current_price or current_price <= 0:
                current_price = item.get("current_price", 0)

            if current_price <= 0:
                print(f"  {stock_name}: 가격 조회 실패")
                continue

            # 추천 매수가 체크 - 현재가가 매수밴드 이하일 때만 매수
            buy_band_high = item.get("buy_band_high", current_price)
            recommended_price = item.get("recommended_price", current_price)
            if current_price > buy_band_high:
                print(f"  {stock_name}: 현재가 {current_price:,}원 > 매수밴드 {buy_band_high:,}원 (추천가 {recommended_price:,}원) - 대기")
                continue

            quantity = investment_per_stock // current_price

            if quantity <= 0:
                print(f"  {stock_name}: 매수 가능 수량 없음")
                continue

            print(f"\n매수: {stock_name} ({stock_code})")
            print(f"  현재가: {current_price:,}원 (추천가 {recommended_price:,}원 이하)")
            print(f"  가격: {current_price:,}원 x {quantity}주 = {current_price * quantity:,}원")
            print(f"  점수: {item.get('score')}, 신호: {len(item.get('signals', []))}개")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "stock_code": stock_code, "dry_run": True}
            else:
                result = self.executor.place_buy_order(
                    stock_code=stock_code,
                    quantity=quantity
                )

            if result.get("success"):
                # 거래 기록
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="buy",
                    quantity=quantity,
                    price=current_price,
                    order_no=result.get("order_no"),
                    trade_reason=f"점수 {item.get('score')}점",
                    status="executed" if not self.dry_run else "dry_run"
                )

                # 보유 종목 추가
                if not self.dry_run:
                    self.logger.add_holding(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        quantity=quantity,
                        avg_price=current_price,
                        buy_reason=f"점수 {item.get('score')}점",
                        market=item.get("market", "KOSDAQ")
                    )

                    # 모의투자 가상 잔고 업데이트 (매수 수수료 차감)
                    if self.config.IS_VIRTUAL:
                        buy_amount = current_price * quantity
                        buy_commission = int(buy_amount * self.config.COMMISSION_RATE)
                        self.logger.update_virtual_balance_on_buy(buy_amount + buy_commission)

                # 알림
                self.notifier.notify_buy(stock_name, current_price, quantity)

                self.stats["buy_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def create_buy_suggestion(self, candidate: Dict) -> Optional[int]:
        """
        매수 제안 생성 및 텔레그램 알림

        Args:
            candidate: 매수 후보 종목 정보

        Returns:
            생성된 제안 ID 또는 None
        """
        stock_code = candidate.get("stock_code")
        stock_name = candidate.get("stock_name", stock_code)
        score = candidate.get("score", 0)
        signals = candidate.get("signals", [])

        # 이미 대기 중인 제안이 있으면 스킵
        if self.suggestion_manager.has_pending_for_stock(stock_code):
            print(f"  {stock_name}: 이미 대기 중인 제안 존재")
            return None

        # 미체결 매수 주문이 있는 종목은 스킵 (중복 주문 방지)
        pending_orders = getattr(self, '_pending_orders', []) or []
        total_assets = getattr(self, '_total_assets', 0)

        if pending_orders:
            for order in pending_orders:
                if order.get('stock_code') == stock_code and order.get('side') == 'buy':
                    pending_amount = int(order.get('order_qty', 0)) * int(order.get('order_price', 0))
                    pct = pending_amount / total_assets * 100 if total_assets > 0 else 0
                    print(f"  {stock_name}: 미체결 매수 주문 존재 ({pending_amount:,}원, {pct:.1f}%) - 스킵")
                    return None

        # 주가 데이터 가져와서 추천 매수가 계산
        try:
            df = self.analyst.get_ohlcv(stock_code, days=120)
            price_info = self.analyst.calculate_recommended_buy_price(
                df,
                target_profit_pct=self.config.TARGET_PROFIT_PCT,
                stop_loss_pct=self.config.SUGGESTED_STOP_LOSS_PCT,
                buy_band_pct=self.config.BUY_BAND_PCT
            )

            if not price_info:
                print(f"  {stock_name}: 추천 매수가 계산 실패")
                return None

            # 상승확률/신뢰도 계산
            prob_conf = self.analyst.calculate_probability_confidence(score, signals)

            # 매수 제안 생성
            suggestion_id = self.suggestion_manager.create_suggestion(
                stock_code=stock_code,
                stock_name=stock_name,
                score=score,
                probability=prob_conf.get('probability', 50),
                confidence=prob_conf.get('confidence', 50),
                current_price=price_info['current_price'],
                recommended_price=price_info['recommended_price'],
                target_price=price_info['target_price'],
                stop_loss_price=price_info['stop_loss_price'],
                buy_band_low=price_info['buy_band_low'],
                buy_band_high=price_info['buy_band_high'],
                signals=signals,
                expire_hours=self.config.SUGGESTION_EXPIRE_HOURS
            )

            # 텔레그램 알림
            self.notifier.notify_buy_suggestion(
                stock_name=stock_name,
                stock_code=stock_code,
                score=score,
                probability=prob_conf.get('probability', 50),
                confidence=prob_conf.get('confidence', 50),
                current_price=price_info['current_price'],
                recommended_price=price_info['recommended_price'],
                target_price=price_info['target_price'],
                stop_loss_price=price_info['stop_loss_price'],
                signals=signals,
                expire_hours=self.config.SUGGESTION_EXPIRE_HOURS
            )

            print(f"  {stock_name}: 매수 제안 생성 (ID: {suggestion_id})")
            print(f"    현재가: {price_info['current_price']:,}원")
            print(f"    추천가: {price_info['recommended_price']:,}원")
            print(f"    목표가: {price_info['target_price']:,}원")

            return suggestion_id

        except Exception as e:
            print(f"  {stock_name}: 매수 제안 생성 오류 - {e}")
            return None

    def execute_approved_suggestions(self, investment_per_stock: int) -> List[Dict]:
        """
        승인된 매수 제안 실행 (추천 매수가 이하일 때만)

        Args:
            investment_per_stock: 종목당 투자금액

        Returns:
            주문 결과 리스트
        """
        results = []
        approved = self.suggestion_manager.get_approved_suggestions()

        if not approved:
            return results

        print(f"\n승인된 제안 {len(approved)}개 확인 중...")

        for suggestion in approved:
            stock_code = suggestion['stock_code']
            stock_name = suggestion.get('stock_name', stock_code)
            recommended_price = suggestion.get('recommended_price', 0)
            buy_band_high = suggestion.get('buy_band_high', recommended_price)

            # 현재가 조회
            current_price = self.executor.get_current_price(stock_code)
            if not current_price:
                print(f"  {stock_name}: 현재가 조회 실패")
                continue

            # 매수 가격 및 방식 결정
            if current_price <= buy_band_high:
                # 현재가가 매수밴드 이하 → 시장가 매수
                order_price = 0
                order_type = "01"  # 시장가
                exec_price = current_price
                order_desc = "시장가"
            else:
                # 현재가가 매수밴드 초과 → 매수밴드 가격으로 지정가 주문
                # 호가 단위로 내림 (2201 → 2200)
                limit_price = round_to_tick(buy_band_high, round_down=True)
                order_price = limit_price
                order_type = "00"  # 지정가
                exec_price = limit_price
                order_desc = f"지정가 {limit_price:,}원"

            # 매수 수량 계산 (지정가 기준)
            quantity = investment_per_stock // exec_price
            if quantity <= 0:
                print(f"  {stock_name}: 매수 가능 수량 없음")
                continue

            print(f"\n[승인 제안 매수] {stock_name}")
            print(f"  추천가: {recommended_price:,}원 / 현재가: {current_price:,}원")
            print(f"  주문: {order_desc} x {quantity}주")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "stock_code": stock_code, "dry_run": True}
            else:
                result = self.executor.place_buy_order(
                    stock_code=stock_code,
                    quantity=quantity,
                    price=order_price,
                    order_type=order_type
                )

            if result.get("success"):
                # 지정가/시장가 구분
                is_limit_order = (order_type == "00")

                # 거래 기록 (지정가는 pending, 시장가는 executed)
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="buy",
                    quantity=quantity,
                    price=exec_price,
                    order_no=result.get("order_no"),
                    trade_reason=f"제안승인 (점수 {suggestion.get('score')}점) - {order_desc}",
                    status="pending" if is_limit_order else ("executed" if not self.dry_run else "dry_run")
                )

                # 시장가 주문은 바로 체결 → 보유 종목 추가
                # 지정가 주문은 미체결 → 보유 종목 추가 안 함 (체결 시 별도 처리)
                if not self.dry_run and not is_limit_order:
                    self.logger.add_holding(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        quantity=quantity,
                        avg_price=exec_price,
                        buy_reason=f"제안승인 (점수 {suggestion.get('score')}점)",
                        market=suggestion.get("market", "KOSDAQ")
                    )

                    # 모의투자 가상 잔고 업데이트 (매수 수수료 차감)
                    if self.config.IS_VIRTUAL:
                        buy_amount = exec_price * quantity
                        buy_commission = int(buy_amount * self.config.COMMISSION_RATE)
                        self.logger.update_virtual_balance_on_buy(buy_amount + buy_commission)

                # 제안 실행 완료 처리 (주문 접수됨)
                self.suggestion_manager.mark_executed(suggestion['id'])

                # 알림
                if is_limit_order:
                    self.notifier.send_push(
                        title=f"📝 지정가 매수 주문: {stock_name}",
                        body=f"{exec_price:,}원 x {quantity}주 (미체결)",
                        url="/auto-trade/pending-orders"
                    )
                else:
                    self.notifier.notify_suggestion_executed(stock_name, exec_price, quantity)

                self.stats["buy_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def run_semi_auto(self) -> Dict:
        """
        반자동 모드 실행 (매수 제안 생성)

        Returns:
            실행 결과 요약
        """
        print("\n" + "=" * 60)
        print("  반자동 매매 시스템 (Semi-Auto Mode)")
        print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  모드: {'모의투자' if self.config.IS_VIRTUAL else '실전투자'}")
        print("=" * 60)

        # 긴급 정지 체크
        if self.config.EMERGENCY_STOP:
            print("\n긴급 정지 상태입니다.")
            return {"status": "emergency_stop"}

        # 장 시간 체크 (dry_run이 아닐 때만)
        if not self.dry_run and not self.check_market_hours():
            return {"status": "market_closed"}

        # 1. 만료된 제안 정리
        print("\n[1] 만료 제안 정리 중...")
        expired_count = self.suggestion_manager.expire_old_suggestions()
        if expired_count > 0:
            print(f"  {expired_count}개 제안 만료 처리")

        # 2. 분석 결과 로드
        print("\n[2] 분석 결과 로드 중...")
        analysis_stocks = self.load_analysis_results()
        if not analysis_stocks:
            self.notifier.notify_error("분석 결과 파일을 찾을 수 없습니다.")
            return {"status": "no_data"}

        # 3. 계좌 잔고 조회
        print("\n[3] 계좌 잔고 조회 중...")
        balance = self.executor.get_account_balance()
        if not balance:
            self.notifier.notify_error("계좌 잔고 조회 실패")
            return {"status": "balance_error"}

        all_holdings = balance.get("holdings", [])
        # 수량 > 0인 종목만 필터링 (매도 완료된 종목 제외)
        holdings = [h for h in all_holdings if h.get("quantity", 0) > 0]
        summary = balance.get("summary", {})
        # 예수금: d2_cash_balance (실제 자산 기준)
        d2_cash = summary.get("d2_cash_balance", 0) or summary.get("cash_balance", 0)
        # 주문가능금액: max_buy_amt (미체결 제외)
        max_buy_amt = summary.get("max_buy_amt", 0) or d2_cash
        # 총자산: 평가금액 + d2 예수금 (고정)
        total_eval = summary.get("total_eval_amount", 0)
        total_assets = total_eval + d2_cash

        print(f"  예수금(D+2): {d2_cash:,}원")
        print(f"  주문가능금액: {max_buy_amt:,}원")
        print(f"  보유 종목: {len(holdings)}개 (수량>0 필터링)")

        # 미체결 주문 조회 (제안 생성 시 중복 체크용)
        self._pending_orders = self.executor.get_pending_orders()
        self._total_assets = total_assets
        self._investment_per_stock = self.risk_manager.calculate_investment_amount(total_assets)
        if self._pending_orders:
            print(f"  미체결 주문: {len(self._pending_orders)}건")

        # 4. 보유 종목 매도 체크 - semi-auto에서는 매도 실행 안 함 (알림만)
        print("\n[4] 보유 종목 평가 중...")
        if holdings:
            current_prices = {}
            current_signals = {}
            current_scores = {}
            buy_dates = {}

            for h in holdings:
                stock_code = h["stock_code"]
                current_prices[stock_code] = h.get("current_price", 0)
                current_signals[stock_code] = self.get_current_signals(stock_code, analysis_stocks)
                current_scores[stock_code] = self.get_current_score(stock_code, analysis_stocks)
                buy_date = self.logger.get_buy_date(stock_code)
                if buy_date:
                    buy_dates[stock_code] = buy_date

            sell_list = self.risk_manager.evaluate_holdings(
                holdings=holdings,
                current_prices=current_prices,
                current_signals=current_signals,
                buy_dates=buy_dates,
                current_scores=current_scores
            )

            if sell_list:
                # semi-auto 모드에서는 매도 실행하지 않고 알림만 전송
                print(f"  ⚠️ 매도 신호 감지: {len(sell_list)}개 (semi-auto 모드에서는 자동 매도 안 함)")
                for item in sell_list:
                    stock_code = item.get('stock_code')
                    stock_name = item.get('stock_name', stock_code)
                    reasons = ', '.join(item.get('sell_reasons', []))
                    profit_rate = item.get('profit_rate', 0) * 100
                    print(f"    - {stock_name}: {reasons} ({profit_rate:+.1f}%)")
                    # 푸시 알림으로 매도 신호 전달 (사용자가 직접 판단)
                    self.notifier.send_push(
                        title=f"⚠️ 매도 신호: {stock_name}",
                        body=f"{reasons} ({profit_rate:+.1f}%)",
                        url=f"/auto-trade/manual"
                    )
                    # 알림 기록 저장
                    self._save_alert_history(stock_code, stock_name, "매도 신호", f"{reasons} ({profit_rate:+.1f}%)")
            else:
                print("  매도 대상 없음")

        # 5. 승인된 매수 제안 실행 (추천 매수가 이하일 때)
        print("\n[5] 승인된 제안 매수 실행 중...")
        investment_per_stock = self.risk_manager.calculate_investment_amount(total_assets)
        # 실제 주문금액은 min(종목당 투자금, 주문가능금액)
        actual_investment = min(investment_per_stock, max_buy_amt)
        print(f"  종목당 투자금: {investment_per_stock:,}원, 주문가능: {max_buy_amt:,}원 → 실제: {actual_investment:,}원")
        self.execute_approved_suggestions(actual_investment)

        # 6. 새 매수 후보 → 제안 생성
        print("\n[6] 새 매수 제안 생성 중...")
        candidates = self.filter_buy_candidates(analysis_stocks)
        print(f"  매수 조건 충족 종목: {len(candidates)}개")

        # 현재 보유 종목과 리스크 관리 반영
        current_holdings = self.executor.get_holdings()
        filtered_candidates = self.risk_manager.filter_buy_candidates(
            candidates, current_holdings
        )

        # 최대 대기 제안 수 체크
        pending = self.suggestion_manager.get_pending_suggestions()
        remaining_slots = self.config.MAX_PENDING_SUGGESTIONS - len(pending)

        new_suggestions = 0
        for candidate in filtered_candidates[:remaining_slots]:
            if self.create_buy_suggestion(candidate):
                new_suggestions += 1

        print(f"  새 매수 제안: {new_suggestions}개 생성")

        # 7. 일일 성과 저장
        print("\n[7] 성과 저장 중...")
        final_balance = self.executor.get_account_balance()
        if final_balance:
            final_holdings = final_balance.get("holdings", [])
            total_invested = sum(h.get("avg_price", 0) * h.get("quantity", 0) for h in final_holdings)
            total_profit = final_balance.get("summary", {}).get("total_profit_loss", 0)

            self.logger.save_daily_performance(
                total_assets=final_balance.get("summary", {}).get("total_eval_amount", 0),
                total_invested=total_invested,
                total_profit=total_profit,
                holdings_count=len(final_holdings)
            )

        # 8. 완료
        print("\n[8] 완료")
        stats = self.suggestion_manager.get_statistics()
        buy_count = len(self.stats["buy_orders"])
        sell_count = len(self.stats["sell_orders"])

        result = {
            "status": "completed",
            "mode": "semi-auto",
            "buy_count": buy_count,
            "sell_count": sell_count,
            "new_suggestions": new_suggestions,
            "pending_suggestions": stats.get('pending', 0),
            "approved_suggestions": stats.get('approved', 0),
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n매수: {buy_count}건, 매도: {sell_count}건")
        print(f"대기 제안: {stats.get('pending', 0)}개, 승인 대기: {stats.get('approved', 0)}개")
        print("=" * 60)

        return result

    def run(self) -> Dict:
        """
        자동매매 실행 (모드에 따라 auto/semi-auto 분기)

        Returns:
            실행 결과 요약
        """
        # 사용자별 설정 확인 (DB 설정 > config 설정)
        trade_mode = getattr(self.config, 'TRADE_MODE', 'auto')
        trading_enabled = True  # 기본값

        if self.user_id:
            user_settings = self.logger.get_auto_trade_settings(self.user_id)
            if user_settings:
                # 중요: trading_enabled 체크 (비활성화면 실행 안 함)
                trading_enabled = bool(user_settings.get('trading_enabled', 0))
                if not trading_enabled:
                    print(f"[AutoTrader] user_id={self.user_id}: trading_enabled=0 → 실행 안 함")
                    return {"status": "disabled", "message": "자동매매가 비활성화되어 있습니다."}

                db_mode = user_settings.get('trade_mode', 'auto')
                # DB 값 변환: 'semi' -> 'semi-auto'
                if db_mode == 'semi':
                    trade_mode = 'semi-auto'
                elif db_mode == 'auto':
                    trade_mode = 'auto'
                elif db_mode == 'manual':
                    trade_mode = 'manual'

        # manual 모드면 실행 안함
        if trade_mode == 'manual':
            return {"status": "manual_mode", "message": "수동 모드입니다."}

        if trade_mode == 'semi-auto':
            return self.run_semi_auto()

        # 기존 auto 모드
        print("\n" + "=" * 60)
        print("  자동매매 시스템 시작 (Auto Mode)")
        print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  모드: {'모의투자' if self.config.IS_VIRTUAL else '실전투자'}")
        print(f"  DRY-RUN: {self.dry_run}")
        print("=" * 60)

        # 긴급 정지 체크
        if self.config.EMERGENCY_STOP:
            print("\n긴급 정지 상태입니다.")
            return {"status": "emergency_stop"}

        # 장 시간 체크 (dry_run이 아닐 때만)
        if not self.dry_run and not self.check_market_hours():
            return {"status": "market_closed"}

        # 거래 가능 여부 체크
        can_trade, reason = self.risk_manager.can_trade()
        if not can_trade:
            print(f"\n거래 불가: {reason}")
            return {"status": "trade_limit", "reason": reason}

        # 1. 분석 결과 로드
        print("\n[1] 분석 결과 로드 중...")
        analysis_stocks = self.load_analysis_results()
        if not analysis_stocks:
            self.notifier.notify_error("분석 결과 파일을 찾을 수 없습니다.")
            return {"status": "no_data"}

        # 2. 계좌 잔고 조회
        print("\n[2] 계좌 잔고 조회 중...")
        balance = self.executor.get_account_balance()
        if not balance:
            self.notifier.notify_error("계좌 잔고 조회 실패")
            return {"status": "balance_error"}

        all_holdings = balance.get("holdings", [])
        # 수량 > 0인 종목만 필터링 (매도 완료된 종목 제외)
        holdings = [h for h in all_holdings if h.get("quantity", 0) > 0]
        summary = balance.get("summary", {})
        # 예수금: d2_cash_balance (실제 자산 기준)
        d2_cash = summary.get("d2_cash_balance", 0) or summary.get("cash_balance", 0)
        # 주문가능금액: max_buy_amt (미체결 제외)
        max_buy_amt = summary.get("max_buy_amt", 0) or d2_cash
        # 총자산: 평가금액 + d2 예수금 (고정)
        total_eval = summary.get("total_eval_amount", 0)
        total_assets = total_eval + d2_cash

        print(f"  예수금(D+2): {d2_cash:,}원")
        print(f"  주문가능금액: {max_buy_amt:,}원")
        print(f"  보유 종목: {len(holdings)}개 (수량>0 필터링)")
        print(f"  총 자산: {total_assets:,}원")

        # 3. 보유 종목 매도 체크
        print("\n[3] 보유 종목 평가 중...")
        if holdings:
            # 현재가, 신호, 점수 조회
            current_prices = {}
            current_signals = {}
            current_scores = {}
            buy_dates = {}

            for h in holdings:
                stock_code = h["stock_code"]
                current_prices[stock_code] = h.get("current_price", 0)
                current_signals[stock_code] = self.get_current_signals(stock_code, analysis_stocks)
                current_scores[stock_code] = self.get_current_score(stock_code, analysis_stocks)

                # DB에서 매수일 조회
                buy_date = self.logger.get_buy_date(stock_code)
                if buy_date:
                    buy_dates[stock_code] = buy_date

            # 매도 대상 선정
            sell_list = self.risk_manager.evaluate_holdings(
                holdings=holdings,
                current_prices=current_prices,
                current_signals=current_signals,
                buy_dates=buy_dates,
                current_scores=current_scores
            )

            if sell_list:
                print(f"  매도 대상: {len(sell_list)}개")
                for item in sell_list:
                    print(f"    - {item['stock_name']}: {', '.join(item['sell_reasons'])}")

                # 매도 실행
                self.execute_sell_orders(sell_list)
            else:
                print("  매도 대상 없음")

        # 4. 매수 후보 필터링
        print("\n[4] 매수 후보 필터링 중...")
        candidates = self.filter_buy_candidates(analysis_stocks)
        print(f"  매수 조건 충족 종목: {len(candidates)}개")

        # 현재 보유 종목과 리스크 관리 반영
        current_holdings = self.executor.get_holdings()
        filtered_candidates = self.risk_manager.filter_buy_candidates(
            candidates, current_holdings
        )
        print(f"  최종 매수 후보: {len(filtered_candidates)}개")

        # 5. 매수 실행
        if filtered_candidates:
            investment_per_stock = self.risk_manager.calculate_investment_amount(total_assets)
            # 실제 주문금액은 min(종목당 투자금, 주문가능금액)
            actual_investment = min(investment_per_stock, max_buy_amt)
            print(f"\n[5] 매수 주문 실행 중...")
            print(f"  종목당 투자금: {investment_per_stock:,}원, 주문가능: {max_buy_amt:,}원 → 실제: {actual_investment:,}원")

            self.execute_buy_orders(filtered_candidates, actual_investment)
        else:
            print("\n[5] 매수할 종목이 없습니다.")

        # 6. 일일 성과 저장
        print("\n[6] 성과 저장 중...")
        final_balance = self.executor.get_account_balance()
        if final_balance:
            final_holdings = final_balance.get("holdings", [])
            total_invested = sum(h.get("avg_price", 0) * h.get("quantity", 0) for h in final_holdings)
            total_eval = sum(h.get("eval_amount", 0) for h in final_holdings)
            total_profit = final_balance.get("summary", {}).get("total_profit_loss", 0)

            self.logger.save_daily_performance(
                total_assets=final_balance.get("summary", {}).get("total_eval_amount", 0),
                total_invested=total_invested,
                total_profit=total_profit,
                holdings_count=len(final_holdings)
            )

        # 7. 요약 알림
        print("\n[7] 완료")
        buy_count = len(self.stats["buy_orders"])
        sell_count = len(self.stats["sell_orders"])

        self.notifier.notify_summary(buy_count, sell_count, self.stats["total_profit"])

        result = {
            "status": "completed",
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_orders": self.stats["buy_orders"],
            "sell_orders": self.stats["sell_orders"],
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n매수: {buy_count}건, 매도: {sell_count}건")
        print("=" * 60)

        return result

    def print_report(self, days: int = 30):
        """성과 리포트 출력"""
        report = self.logger.export_report(days=days)
        print(report)


def main():
    parser = argparse.ArgumentParser(description="자동매매 시스템")
    parser.add_argument("--dry-run", action="store_true", help="테스트 실행 (실제 주문 X)")
    parser.add_argument("--report", action="store_true", help="성과 리포트만 출력")
    parser.add_argument("--days", type=int, default=30, help="리포트 조회 기간 (기본: 30일)")
    args = parser.parse_args()

    trader = AutoTrader(dry_run=args.dry_run)

    if args.report:
        trader.print_report(days=args.days)
    else:
        trader.run()


if __name__ == "__main__":
    main()
