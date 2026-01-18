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
from trading.trade_logger import TradeLogger
from config import AutoTraderConfig, TelegramConfig, OUTPUT_DIR, SIGNAL_NAMES_KR


class TelegramNotifier:
    """텔레그램 알림 발송"""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled

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
        """일일 요약 알림"""
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


class AutoTrader:
    """자동매매 시스템"""

    def __init__(self, dry_run: bool = False):
        """
        Args:
            dry_run: True면 주문을 실제로 실행하지 않음
        """
        self.dry_run = dry_run
        self.config = AutoTraderConfig

        # KIS 클라이언트 초기화
        self.kis_client = KISClient(is_virtual=self.config.IS_VIRTUAL)

        # 모듈 초기화
        self.executor = OrderExecutor(self.kis_client)
        self.risk_manager = RiskManager(TradingLimits(
            max_position_pct=self.config.MAX_POSITION_PCT,
            stop_loss_pct=self.config.STOP_LOSS_PCT,
            take_profit_pct=self.config.TAKE_PROFIT_PCT,
            max_daily_trades=self.config.MAX_DAILY_TRADES,
            max_holdings=self.config.MAX_HOLDINGS,
            max_hold_days=self.config.MAX_HOLD_DAYS,
            min_buy_score=self.config.MIN_BUY_SCORE,
            min_volume_ratio=self.config.MIN_VOLUME_RATIO,
        ))
        self.logger = TradeLogger()
        self.notifier = TelegramNotifier(
            bot_token=TelegramConfig.BOT_TOKEN,
            chat_id=TelegramConfig.CHAT_ID,
            enabled=self.config.TELEGRAM_NOTIFY and not dry_run
        )

        # 실행 통계
        self.stats = {
            "buy_orders": [],
            "sell_orders": [],
            "total_profit": 0,
        }

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

            # 점수 조건
            if score < self.config.MIN_BUY_SCORE:
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

            # 주의 신호 체크 (있으면 제외)
            caution_signals = ["RSI_OVERBOUGHT", "MFI_OVERBOUGHT", "BB_UPPER_BREAK"]
            has_caution = any(s in signals for s in caution_signals)
            if has_caution:
                continue

            candidates.append({
                "stock_code": stock.get("code"),
                "stock_name": stock.get("name"),
                "score": score,
                "signals": signals,
                "volume_ratio": volume_ratio,
                "current_price": int(stock.get("close", 0)),
                "target_price": stock.get("target_price"),
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
                # 거래 기록
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="sell",
                    quantity=quantity,
                    price=item.get("current_price", 0),
                    order_no=result.get("order_no"),
                    trade_reason=", ".join(sell_reasons),
                    status="executed" if not self.dry_run else "dry_run"
                )

                # 보유 종목에서 제거
                if not self.dry_run:
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
            current_price = item.get("current_price", 0)

            if current_price <= 0:
                current_price = self.executor.get_current_price(stock_code) or 0

            if current_price <= 0:
                print(f"  {stock_name}: 가격 조회 실패")
                continue

            quantity = investment_per_stock // current_price

            if quantity <= 0:
                print(f"  {stock_name}: 매수 가능 수량 없음")
                continue

            print(f"\n매수: {stock_name} ({stock_code})")
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
                        buy_reason=f"점수 {item.get('score')}점"
                    )

                # 알림
                self.notifier.notify_buy(stock_name, current_price, quantity)

                self.stats["buy_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def run(self) -> Dict:
        """
        자동매매 실행

        Returns:
            실행 결과 요약
        """
        print("\n" + "=" * 60)
        print("  자동매매 시스템 시작")
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

        holdings = balance.get("holdings", [])
        cash = balance.get("summary", {}).get("cash_balance", 0)
        total_assets = balance.get("summary", {}).get("total_eval_amount", 0) + cash

        print(f"  현금: {cash:,}원")
        print(f"  보유 종목: {len(holdings)}개")
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
            print(f"\n[5] 매수 주문 실행 중...")
            print(f"  종목당 투자금액: {investment_per_stock:,}원")

            self.execute_buy_orders(filtered_candidates, investment_per_stock)
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
