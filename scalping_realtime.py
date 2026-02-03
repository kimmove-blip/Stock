#!/usr/bin/env python3
"""
스캘핑 실시간 테스트 v1.0
조건:
- 익절: +2%
- 손절: -2%
- 최대 보유시간: 5분
- 재매수 허용
- 15:19 전량 청산
"""

import argparse
import asyncio
import signal
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json

# 프로젝트 모듈
sys.path.insert(0, '/home/kimhc/Stock')
from api.services.kis_client import KISClient
from trading.trade_logger import TradeLogger


@dataclass
class Position:
    """포지션 정보"""
    stock_code: str
    stock_name: str
    entry_price: int
    entry_time: datetime
    quantity: int

    def get_pnl_pct(self, current_price: int) -> float:
        return (current_price - self.entry_price) / self.entry_price * 100

    def get_hold_seconds(self) -> float:
        return (datetime.now() - self.entry_time).total_seconds()


@dataclass
class Trade:
    """거래 기록"""
    stock_code: str
    stock_name: str
    entry_time: datetime
    exit_time: datetime
    entry_price: int
    exit_price: int
    quantity: int
    pnl_pct: float
    pnl_amount: int
    exit_reason: str


class ScalpingTrader:
    """스캘핑 트레이더"""

    def __init__(
        self,
        kis_client: KISClient,
        stock_codes: List[str],
        mode: str = 'simulation',  # simulation / live
        take_profit: float = 3.0,  # 실시간 테스트용
        stop_loss: float = 2.0,
        max_hold_seconds: int = 900,  # 15분
        investment_per_trade: int = 100_000,
        max_positions: int = 3,
        daily_loss_limit: int = -50_000,
    ):
        self.kis = kis_client
        self.stock_codes = stock_codes
        self.mode = mode
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_hold_seconds = max_hold_seconds
        self.investment_per_trade = investment_per_trade
        self.max_positions = max_positions
        self.daily_loss_limit = daily_loss_limit
        self.tax_fee_rate = 0.00203  # 세금+수수료 (매도대금의 0.203%)

        # 상태
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.stock_names: Dict[str, str] = {}
        self.last_prices: Dict[str, int] = {}
        self.last_entry_time: Dict[str, datetime] = {}  # 재진입 쿨다운

        # 통계
        self.daily_pnl = 0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0

        # 플래그
        self.running = True
        self.trading_enabled = True

    def log(self, msg: str):
        """로그 출력"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {msg}", flush=True)

    def is_trading_time(self) -> bool:
        """매매 가능 시간 확인"""
        now = datetime.now()
        # 09:10 ~ 15:15
        start = now.replace(hour=9, minute=10, second=0)
        end = now.replace(hour=15, minute=15, second=0)
        return start <= now <= end

    def is_closing_time(self) -> bool:
        """장마감 청산 시간 확인 (15:19~)"""
        now = datetime.now()
        close = now.replace(hour=15, minute=19, second=0)
        return now >= close

    def should_enter(self, code: str, price_data: dict) -> tuple:
        """진입 조건 확인"""
        if not self.trading_enabled:
            return False, "매매 중단"

        if not self.is_trading_time():
            return False, "매매 시간 아님"

        if len(self.positions) >= self.max_positions:
            return False, f"최대 포지션 {self.max_positions}개"

        if code in self.positions:
            return False, "이미 보유 중"

        # 재진입 쿨다운 (1분)
        last_entry = self.last_entry_time.get(code)
        if last_entry and (datetime.now() - last_entry).total_seconds() < 60:
            return False, "재진입 대기"

        # 가격 데이터 확인
        current_price = price_data.get('current_price', 0)
        change_pct = price_data.get('change_rate', 0)
        volume = price_data.get('volume', 0)

        if current_price <= 0:
            return False, "가격 없음"

        # 진입 조건: 등락률 +0.5% ~ +5%
        if not (0.5 <= change_pct <= 5.0):
            return False, f"등락률 {change_pct:.1f}% 범위 밖"

        return True, f"진입조건 충족 (등락률 {change_pct:+.1f}%)"

    def check_exit(self, pos: Position, current_price: int) -> tuple:
        """청산 조건 확인"""
        pnl_pct = pos.get_pnl_pct(current_price)
        hold_seconds = pos.get_hold_seconds()

        # 1. 익절
        if pnl_pct >= self.take_profit:
            return True, f"익절 {pnl_pct:+.2f}%"

        # 2. 손절
        if pnl_pct <= -self.stop_loss:
            return True, f"손절 {pnl_pct:+.2f}%"

        # 3. 시간초과
        if hold_seconds >= self.max_hold_seconds:
            return True, f"시간초과 {int(hold_seconds)}초"

        # 4. 장마감
        if self.is_closing_time():
            return True, f"장마감청산"

        return False, f"보유중 {pnl_pct:+.2f}% ({int(hold_seconds)}초)"

    def execute_buy(self, code: str, name: str, price: int):
        """매수 실행"""
        quantity = self.investment_per_trade // price
        if quantity <= 0:
            self.log(f"  {name}: 수량 부족")
            return

        if self.mode == 'live':
            result = self.kis.place_order(
                stock_code=code,
                side='buy',
                quantity=quantity,
                price=0,
                order_type='01'
            )
            if not result or not result.get('success'):
                self.log(f"  {name}: 매수 주문 실패")
                return

        # 포지션 기록
        self.positions[code] = Position(
            stock_code=code,
            stock_name=name,
            entry_price=price,
            entry_time=datetime.now(),
            quantity=quantity
        )
        self.last_entry_time[code] = datetime.now()

        mode_str = "[LIVE]" if self.mode == 'live' else "[SIM]"
        self.log(f"  {mode_str} 매수: {name} {quantity}주 @ {price:,}원")

    def execute_sell(self, code: str, current_price: int, reason: str):
        """매도 실행"""
        pos = self.positions.get(code)
        if not pos:
            return

        if self.mode == 'live':
            result = self.kis.place_order(
                stock_code=code,
                side='sell',
                quantity=pos.quantity,
                price=0,
                order_type='01'
            )
            if not result or not result.get('success'):
                self.log(f"  {pos.stock_name}: 매도 주문 실패")
                return

        # 손익 계산 (세금/수수료 0.203% 차감)
        pnl_pct = pos.get_pnl_pct(current_price)
        sell_amount = current_price * pos.quantity
        tax_fee = int(sell_amount * self.tax_fee_rate)
        gross_pnl = int(self.investment_per_trade * pnl_pct / 100)
        pnl_amount = gross_pnl - tax_fee

        # 거래 기록
        trade = Trade(
            stock_code=code,
            stock_name=pos.stock_name,
            entry_time=pos.entry_time,
            exit_time=datetime.now(),
            entry_price=pos.entry_price,
            exit_price=current_price,
            quantity=pos.quantity,
            pnl_pct=pnl_pct,
            pnl_amount=pnl_amount,
            exit_reason=reason
        )
        self.trades.append(trade)

        # 통계 업데이트
        self.daily_pnl += pnl_amount
        self.trade_count += 1
        if pnl_pct > 0:
            self.win_count += 1
        elif pnl_pct < 0:
            self.loss_count += 1

        # 일일 손실 한도 체크
        if self.daily_pnl <= self.daily_loss_limit:
            self.trading_enabled = False
            self.log(f"[경고] 일일 손실 한도 도달: {self.daily_pnl:,}원")

        # 포지션 삭제
        del self.positions[code]

        mode_str = "[LIVE]" if self.mode == 'live' else "[SIM]"
        self.log(f"  {mode_str} 매도: {pos.stock_name} @ {current_price:,}원 ({reason}) → {pnl_pct:+.2f}% ({pnl_amount:+,}원)")

    async def run(self, poll_interval: float = 2.0):
        """메인 루프"""
        self.log("=" * 60)
        self.log(f"스캘핑 실시간 테스트 시작")
        self.log(f"모드: {self.mode.upper()}")
        self.log(f"종목: {len(self.stock_codes)}개")
        self.log(f"익절: +{self.take_profit}%, 손절: -{self.stop_loss}%")
        self.log(f"최대보유: {self.max_hold_seconds}초")
        self.log(f"투자금/거래: {self.investment_per_trade:,}원")
        self.log("=" * 60)

        # 종목명 로드
        for code in self.stock_codes:
            try:
                from pykrx import stock
                name = stock.get_market_ticker_name(code)
                self.stock_names[code] = name or code
            except:
                self.stock_names[code] = code

        self.log(f"종목명 로드 완료: {len(self.stock_names)}개")

        while self.running:
            now = datetime.now()

            # 장 시간 체크 (09:00 ~ 15:30)
            if now.hour < 9 or (now.hour >= 15 and now.minute >= 30):
                if self.positions:
                    self.log("장 마감 - 전량 청산")
                    for code in list(self.positions.keys()):
                        price_data = self.kis.get_current_price(code)
                        if price_data:
                            self.execute_sell(code, price_data['current_price'], "장마감")
                    self.print_summary()
                    break
                await asyncio.sleep(10)
                continue

            # 각 종목 처리
            for code in self.stock_codes:
                try:
                    price_data = self.kis.get_current_price(code)
                    if not price_data:
                        continue

                    current_price = price_data.get('current_price', 0)
                    if current_price <= 0:
                        continue

                    name = self.stock_names.get(code, code)

                    # 가격 변동 감지
                    prev_price = self.last_prices.get(code, 0)
                    if prev_price > 0:
                        change = (current_price - prev_price) / prev_price * 100
                        if abs(change) >= 0.3:
                            self.log(f"  {name}: {current_price:,}원 ({change:+.2f}%)")
                    self.last_prices[code] = current_price

                    # 포지션 있으면 청산 체크
                    if code in self.positions:
                        should_exit, reason = self.check_exit(self.positions[code], current_price)
                        if should_exit:
                            self.execute_sell(code, current_price, reason)

                    # 포지션 없으면 진입 체크
                    elif self.trading_enabled:
                        should_enter, reason = self.should_enter(code, price_data)
                        if should_enter:
                            self.execute_buy(code, name, current_price)

                except Exception as e:
                    pass

            # 상태 출력 (30초마다)
            if now.second % 30 == 0:
                pos_str = ", ".join([f"{p.stock_name}({p.get_pnl_pct(self.last_prices.get(p.stock_code, p.entry_price)):+.1f}%)"
                                     for p in self.positions.values()])
                if pos_str:
                    self.log(f"[상태] 포지션: {pos_str} | 일일손익: {self.daily_pnl:+,}원")

            await asyncio.sleep(poll_interval)

        self.print_summary()

    def print_summary(self):
        """결과 요약 출력"""
        self.log("\n" + "=" * 60)
        self.log("스캘핑 테스트 결과")
        self.log("=" * 60)

        if self.trade_count == 0:
            self.log("거래 없음")
            return

        win_rate = self.win_count / self.trade_count * 100
        avg_pnl = sum(t.pnl_pct for t in self.trades) / len(self.trades)

        self.log(f"총 거래: {self.trade_count}건")
        self.log(f"승/패: {self.win_count}/{self.loss_count}")
        self.log(f"승률: {win_rate:.1f}%")
        self.log(f"평균 수익률: {avg_pnl:+.2f}%")
        self.log(f"총 손익: {self.daily_pnl:+,}원")

        # 청산 사유별
        reasons = {}
        for t in self.trades:
            key = t.exit_reason.split()[0]
            if key not in reasons:
                reasons[key] = {'count': 0, 'pnl': 0}
            reasons[key]['count'] += 1
            reasons[key]['pnl'] += t.pnl_amount

        self.log("\n[청산 사유별]")
        for reason, data in reasons.items():
            self.log(f"  {reason}: {data['count']}건, {data['pnl']:+,}원")

        self.log("=" * 60)

        # 결과 저장
        self.save_results()

    def save_results(self):
        """결과 저장"""
        today = datetime.now().strftime('%Y%m%d')

        trades_data = [
            {
                'code': t.stock_code,
                'name': t.stock_name,
                'entry_time': t.entry_time.strftime('%H:%M:%S'),
                'exit_time': t.exit_time.strftime('%H:%M:%S'),
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'quantity': t.quantity,
                'pnl_pct': round(t.pnl_pct, 2),
                'pnl_amount': t.pnl_amount,
                'exit_reason': t.exit_reason
            }
            for t in self.trades
        ]

        result = {
            'date': today,
            'mode': self.mode,
            'settings': {
                'take_profit': self.take_profit,
                'stop_loss': self.stop_loss,
                'max_hold_seconds': self.max_hold_seconds,
                'investment_per_trade': self.investment_per_trade
            },
            'summary': {
                'total_trades': self.trade_count,
                'win_count': self.win_count,
                'loss_count': self.loss_count,
                'win_rate': round(self.win_count / self.trade_count * 100, 1) if self.trade_count > 0 else 0,
                'total_pnl': self.daily_pnl
            },
            'trades': trades_data
        }

        output_path = f'/home/kimhc/Stock/output/scalping_realtime_{today}.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self.log(f"결과 저장: {output_path}")

    def stop(self):
        """중지"""
        self.running = False


async def main():
    parser = argparse.ArgumentParser(description='스캘핑 실시간 테스트')
    parser.add_argument('--stocks', '-s', type=str, required=True,
                        help='종목코드 (쉼표 구분)')
    parser.add_argument('--user-id', '-u', type=int, default=2,
                        help='사용자 ID (default: 2)')
    parser.add_argument('--mode', '-m', type=str, default='simulation',
                        choices=['simulation', 'live'],
                        help='모드 (simulation/live)')
    parser.add_argument('--tp', type=float, default=2.0,
                        help='익절 % (default: 2.0)')
    parser.add_argument('--sl', type=float, default=2.0,
                        help='손절 % (default: 2.0)')
    parser.add_argument('--max-hold', type=int, default=300,
                        help='최대 보유시간 초 (default: 300)')
    parser.add_argument('--investment', type=int, default=100000,
                        help='거래당 투자금 (default: 100000)')
    parser.add_argument('--poll', type=float, default=2.0,
                        help='폴링 간격 초 (default: 2.0)')

    args = parser.parse_args()

    stock_codes = [c.strip() for c in args.stocks.split(',')]

    # KIS 클라이언트 초기화
    logger = TradeLogger()
    api_data = logger.get_api_key_settings(args.user_id)

    if not api_data or not api_data.get('app_key'):
        print(f"[오류] user_id={args.user_id}의 API 키가 없습니다.")
        return

    kis_client = KISClient(
        app_key=api_data['app_key'],
        app_secret=api_data['app_secret'],
        account_number=api_data.get('account_number', ''),
        account_product_code=api_data.get('account_product_code', '01'),
        is_virtual=bool(api_data.get('is_mock', False))
    )

    # 트레이더 생성
    trader = ScalpingTrader(
        kis_client=kis_client,
        stock_codes=stock_codes,
        mode=args.mode,
        take_profit=args.tp,
        stop_loss=args.sl,
        max_hold_seconds=args.max_hold,
        investment_per_trade=args.investment
    )

    # 시그널 핸들러
    def shutdown(sig, frame):
        print("\n종료 신호 수신...")
        trader.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 실행
    await trader.run(poll_interval=args.poll)


if __name__ == "__main__":
    asyncio.run(main())
