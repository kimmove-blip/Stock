#!/usr/bin/env python3
"""
스캘핑 전략 비교 시뮬레이터

두 전략을 동시에 시뮬레이션하여 수익률 비교:
1. 현재 전략: 체결강도 + 호가 + MA (매수잔량/매도잔량 ≥2, 체결강도 가속도 ≥5)
2. 변동성 돌파: Larry Williams (목표가 = 시가 + 전일변동폭 × K)

사용법:
    # 폴링 모드 (pykrx, 1분 간격)
    python scalping_simulator.py --auto-select 20

    # WebSocket 실시간 모드 (권장)
    python scalping_simulator.py --auto-select 20 --websocket
    python scalping_simulator.py -a 20 -w -u 2  # user_id 지정

    # 특정 종목 지정
    python scalping_simulator.py --stocks 005930,035420 --websocket

    # 결과 리포트
    python scalping_simulator.py --report

WebSocket 모드:
    - 한투 API 실시간 체결/호가 데이터 사용
    - 체결강도, 호가잔량 실시간 계산
    - 정확한 전략 비교 가능
"""

import asyncio
import argparse
import json
import signal
import sys
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from collections import deque

sys.path.insert(0, str(Path(__file__).parent))

from pykrx import stock
import pandas as pd

# 한투 WebSocket (실시간 데이터)
try:
    from trading.realtime.kis_websocket import KISWebSocket, ExecutionData, OrderbookData
    from trading.trade_logger import TradeLogger
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("[경고] WebSocket 모듈 미설치 - 폴링 모드만 사용 가능")


# ============================================================
# 시뮬레이션 데이터 구조
# ============================================================

@dataclass
class SimulatedTrade:
    """시뮬레이션 거래"""
    strategy: str              # 'scalping' or 'breakout'
    stock_code: str
    stock_name: str
    entry_time: datetime
    entry_price: int
    quantity: int = 1          # 시뮬레이션은 1주 기준

    # 청산 정보 (나중에 업데이트)
    exit_time: Optional[datetime] = None
    exit_price: Optional[int] = None
    exit_reason: str = ""

    # 수익률
    profit_pct: float = 0.0
    profit_amount: int = 0

    # 신호 정보
    signal_info: Dict = field(default_factory=dict)

    @property
    def is_closed(self) -> bool:
        return self.exit_price is not None

    def close(self, exit_price: int, reason: str = ""):
        """청산"""
        self.exit_time = datetime.now()
        self.exit_price = exit_price
        self.exit_reason = reason
        self.profit_amount = exit_price - self.entry_price
        self.profit_pct = (self.profit_amount / self.entry_price) * 100 if self.entry_price > 0 else 0


@dataclass
class DailyResult:
    """일일 결과"""
    date: str
    strategy: str

    # 거래 통계
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0

    # 수익 통계
    total_profit: int = 0
    total_loss: int = 0
    net_profit: int = 0
    avg_profit_pct: float = 0.0

    # 최대 손익
    max_profit: int = 0
    max_loss: int = 0

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.win_count / self.total_trades) * 100


# ============================================================
# 시뮬레이터
# ============================================================

class ScalpingSimulator:
    """스캘핑 전략 비교 시뮬레이터"""

    def __init__(
        self,
        stock_codes: List[str],
        # 현재 전략 설정
        scalping_stop_loss: float = -1.0,
        scalping_take_profit: float = 1.0,
        # 변동성 돌파 설정
        breakout_k: float = 0.5,
        breakout_stop_loss: float = -2.0,  # 변동성 돌파는 더 넓은 손절
        # 공통 설정
        investment_per_stock: int = 500_000,
        # 실제 주문 설정
        execute_mode: bool = False,
        kis_client=None,
    ):
        self.stock_codes = stock_codes
        self.investment = investment_per_stock

        # 전략 설정
        self.scalping_stop_loss = scalping_stop_loss
        self.scalping_take_profit = scalping_take_profit
        self.breakout_k = breakout_k
        self.breakout_stop_loss = breakout_stop_loss

        # 실제 주문 모드
        self.execute_mode = execute_mode
        self.kis_client = kis_client
        self.real_positions: Dict[str, Dict] = {}  # 실제 보유 포지션

        # 상태
        self.trades: List[SimulatedTrade] = []
        self.active_positions: Dict[str, Dict[str, SimulatedTrade]] = {
            'scalping': {},
            'breakout': {},
        }

        # 전일 데이터
        self.prev_data: Dict[str, Dict] = {}
        self.today_data: Dict[str, Dict] = {}

        # 목표가 (변동성 돌파)
        self.breakout_targets: Dict[str, int] = {}
        self.breakout_entered: set = set()

        # 결과 저장 경로
        self.output_dir = Path(__file__).parent / "output" / "scalping_simulation"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def calculate_quantity(self, price: int) -> int:
        """투자금액 기준 수량 계산 (10만원 이상 종목은 1주)"""
        if price >= 100_000:
            return 1
        return max(1, self.investment // price)

    def execute_buy(self, stock_code: str, stock_name: str, price: int, strategy: str) -> bool:
        """실제 매수 주문 실행"""
        if not self.execute_mode or not self.kis_client:
            return True  # 시뮬레이션 모드

        quantity = self.calculate_quantity(price)
        try:
            result = self.kis_client.place_order(
                stock_code=stock_code,
                side='buy',
                quantity=quantity,
                price=0,  # 시장가
                order_type='01'
            )
            if result and result.get('success'):
                self.real_positions[stock_code] = {
                    'quantity': quantity,
                    'entry_price': price,
                    'strategy': strategy,
                    'stock_name': stock_name,
                }
                print(f"[실제주문] 매수: {stock_name} {quantity}주 @ 시장가 (투자: {price * quantity:,}원)")
                return True
            else:
                msg = result.get('message', '알 수 없는 오류') if result else '응답 없음'
                print(f"[실제주문] 매수 실패: {stock_name} - {msg}")
                return False
        except Exception as e:
            print(f"[실제주문] 매수 에러: {stock_name} - {e}")
            return False

    def execute_sell(self, stock_code: str, stock_name: str, reason: str) -> bool:
        """실제 매도 주문 실행"""
        if not self.execute_mode or not self.kis_client:
            return True  # 시뮬레이션 모드

        position = self.real_positions.get(stock_code)
        if not position:
            return True  # 포지션 없음

        try:
            result = self.kis_client.place_order(
                stock_code=stock_code,
                side='sell',
                quantity=position['quantity'],
                price=0,  # 시장가
                order_type='01'
            )
            if result and result.get('success'):
                del self.real_positions[stock_code]
                print(f"[실제주문] 매도: {stock_name} {position['quantity']}주 ({reason})")
                return True
            else:
                msg = result.get('message', '알 수 없는 오류') if result else '응답 없음'
                print(f"[실제주문] 매도 실패: {stock_name} - {msg}")
                return False
        except Exception as e:
            print(f"[실제주문] 매도 에러: {stock_name} - {e}")
            return False

    def load_prev_day_data(self):
        """전일 데이터 로드"""
        print("전일 데이터 로드 중...")

        # 최근 거래일 찾기
        today = datetime.now()
        for i in range(1, 10):
            prev_date = (today - timedelta(days=i)).strftime("%Y%m%d")
            try:
                df = stock.get_market_ohlcv(prev_date, prev_date, self.stock_codes[0])
                if not df.empty:
                    break
            except:
                continue
        else:
            print("전일 데이터를 찾을 수 없습니다.")
            return

        print(f"전일: {prev_date}")

        for code in self.stock_codes:
            try:
                df = stock.get_market_ohlcv(prev_date, prev_date, code)
                if df.empty:
                    continue

                row = df.iloc[0]
                self.prev_data[code] = {
                    'high': int(row['고가']),
                    'low': int(row['저가']),
                    'close': int(row['종가']),
                    'volume': int(row['거래량']),
                }

                # 목표가 계산 (변동성 돌파)
                volatility = self.prev_data[code]['high'] - self.prev_data[code]['low']
                # 시가는 나중에 업데이트

            except Exception as e:
                print(f"  {code} 데이터 로드 실패: {e}")

        print(f"  {len(self.prev_data)}개 종목 로드 완료")

    def update_today_open(self, stock_code: str, open_price: int, name: str = ""):
        """금일 시가 업데이트 및 목표가 계산"""
        self.today_data[stock_code] = {
            'open': open_price,
            'name': name,
        }

        # 변동성 돌파 목표가 계산
        if stock_code in self.prev_data:
            prev = self.prev_data[stock_code]
            volatility = prev['high'] - prev['low']
            target = open_price + int(volatility * self.breakout_k)
            self.breakout_targets[stock_code] = target

    def check_scalping_signal(
        self,
        stock_code: str,
        current_price: int,
        ask_bid_ratio: float,
        strength_accel: float,
        ma_distance_pct: float,
    ) -> bool:
        """현재 전략 신호 체크"""
        # 3가지 조건 모두 충족
        orderbook_signal = ask_bid_ratio >= 2.0
        momentum_signal = strength_accel >= 5.0
        ma_support_signal = abs(ma_distance_pct) <= 0.5

        return orderbook_signal and momentum_signal and ma_support_signal

    def check_breakout_signal(
        self,
        stock_code: str,
        current_price: int,
    ) -> bool:
        """변동성 돌파 신호 체크"""
        if stock_code in self.breakout_entered:
            return False

        target = self.breakout_targets.get(stock_code)
        if not target:
            return False

        return current_price >= target

    def process_price_update(
        self,
        stock_code: str,
        stock_name: str,
        current_price: int,
        # 현재 전략용 데이터
        ask_bid_ratio: float = 0.0,
        strength_accel: float = 0.0,
        ma_distance_pct: float = 0.0,
    ):
        """가격 업데이트 처리"""
        now = datetime.now()

        # 1. 기존 포지션 모니터링
        self._monitor_positions(stock_code, current_price)

        # 2. 현재 전략 신호 체크
        if stock_code not in self.active_positions['scalping']:
            if self.check_scalping_signal(stock_code, current_price, ask_bid_ratio, strength_accel, ma_distance_pct):
                # 실제 주문 실행
                if self.execute_mode:
                    if not self.execute_buy(stock_code, stock_name, current_price, 'scalping'):
                        return  # 주문 실패시 포지션 등록 안함

                trade = SimulatedTrade(
                    strategy='scalping',
                    stock_code=stock_code,
                    stock_name=stock_name,
                    entry_time=now,
                    entry_price=current_price,
                    signal_info={
                        'ask_bid_ratio': ask_bid_ratio,
                        'strength_accel': strength_accel,
                        'ma_distance_pct': ma_distance_pct,
                    }
                )
                self.active_positions['scalping'][stock_code] = trade
                self.trades.append(trade)
                print(f"[SCALPING] 매수: {stock_name} @ {current_price:,}원")

        # 3. 변동성 돌파 신호 체크
        if stock_code not in self.active_positions['breakout']:
            if self.check_breakout_signal(stock_code, current_price):
                # 실제 주문 실행
                if self.execute_mode:
                    if not self.execute_buy(stock_code, stock_name, current_price, 'breakout'):
                        return  # 주문 실패시 포지션 등록 안함

                target = self.breakout_targets.get(stock_code, 0)
                trade = SimulatedTrade(
                    strategy='breakout',
                    stock_code=stock_code,
                    stock_name=stock_name,
                    entry_time=now,
                    entry_price=current_price,
                    signal_info={
                        'target_price': target,
                        'k_value': self.breakout_k,
                    }
                )
                self.active_positions['breakout'][stock_code] = trade
                self.breakout_entered.add(stock_code)
                self.trades.append(trade)
                print(f"[BREAKOUT] 매수: {stock_name} @ {current_price:,}원 (목표가: {target:,})")

    def _monitor_positions(self, stock_code: str, current_price: int):
        """포지션 모니터링"""
        # 현재 전략 포지션
        if stock_code in self.active_positions['scalping']:
            trade = self.active_positions['scalping'][stock_code]
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100

            if profit_pct <= self.scalping_stop_loss:
                if self.execute_mode:
                    self.execute_sell(stock_code, trade.stock_name, "손절")
                trade.close(current_price, "stop_loss")
                del self.active_positions['scalping'][stock_code]
                print(f"[SCALPING] 손절: {trade.stock_name} @ {current_price:,}원 ({profit_pct:+.2f}%)")
            elif profit_pct >= self.scalping_take_profit:
                if self.execute_mode:
                    self.execute_sell(stock_code, trade.stock_name, "익절")
                trade.close(current_price, "take_profit")
                del self.active_positions['scalping'][stock_code]
                print(f"[SCALPING] 익절: {trade.stock_name} @ {current_price:,}원 ({profit_pct:+.2f}%)")

        # 변동성 돌파 포지션 (익절 +2%, 손절 -1%, 10분 시간청산)
        if stock_code in self.active_positions['breakout']:
            trade = self.active_positions['breakout'][stock_code]
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
            holding_minutes = (datetime.now() - trade.entry_time).total_seconds() / 60

            if profit_pct <= -1.0:  # 손절 -1%
                if self.execute_mode:
                    self.execute_sell(stock_code, trade.stock_name, "손절")
                trade.close(current_price, "stop_loss")
                del self.active_positions['breakout'][stock_code]
                print(f"[BREAKOUT] 손절: {trade.stock_name} @ {current_price:,}원 ({profit_pct:+.2f}%)")
            elif profit_pct >= 2.0:  # 익절 +2%
                if self.execute_mode:
                    self.execute_sell(stock_code, trade.stock_name, "익절")
                trade.close(current_price, "take_profit")
                del self.active_positions['breakout'][stock_code]
                print(f"[BREAKOUT] 익절: {trade.stock_name} @ {current_price:,}원 ({profit_pct:+.2f}%)")
            elif holding_minutes >= 10:  # 10분 시간청산
                if self.execute_mode:
                    self.execute_sell(stock_code, trade.stock_name, "시간청산")
                trade.close(current_price, "time_exit")
                del self.active_positions['breakout'][stock_code]
                print(f"[BREAKOUT] 시간청산: {trade.stock_name} @ {current_price:,}원 ({profit_pct:+.2f}%, {holding_minutes:.0f}분)")

    def close_all_positions(self, prices: Dict[str, int]):
        """모든 포지션 청산 (장마감)"""
        for strategy in ['scalping', 'breakout']:
            for code, trade in list(self.active_positions[strategy].items()):
                if code in prices:
                    trade.close(prices[code], "market_close")
                    print(f"[{strategy.upper()}] 장마감 청산: {trade.stock_name} @ {prices[code]:,}원 ({trade.profit_pct:+.2f}%)")
            self.active_positions[strategy].clear()

    def get_daily_results(self) -> Dict[str, DailyResult]:
        """일일 결과 계산"""
        today = datetime.now().strftime("%Y-%m-%d")
        results = {}

        for strategy in ['scalping', 'breakout']:
            strategy_trades = [t for t in self.trades if t.strategy == strategy and t.is_closed]

            result = DailyResult(date=today, strategy=strategy)
            result.total_trades = len(strategy_trades)

            for trade in strategy_trades:
                if trade.profit_amount > 0:
                    result.win_count += 1
                    result.total_profit += trade.profit_amount
                    result.max_profit = max(result.max_profit, trade.profit_amount)
                else:
                    result.loss_count += 1
                    result.total_loss += abs(trade.profit_amount)
                    result.max_loss = min(result.max_loss, trade.profit_amount)

            result.net_profit = result.total_profit - result.total_loss
            if result.total_trades > 0:
                result.avg_profit_pct = sum(t.profit_pct for t in strategy_trades) / result.total_trades

            results[strategy] = result

        return results

    def save_results(self):
        """결과 저장"""
        today = datetime.now().strftime("%Y%m%d")

        # 거래 내역 저장
        trades_file = self.output_dir / f"trades_{today}.json"
        trades_data = []
        for trade in self.trades:
            data = {
                'strategy': trade.strategy,
                'stock_code': trade.stock_code,
                'stock_name': trade.stock_name,
                'entry_time': trade.entry_time.isoformat() if trade.entry_time else None,
                'entry_price': trade.entry_price,
                'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
                'exit_price': trade.exit_price,
                'exit_reason': trade.exit_reason,
                'profit_pct': round(trade.profit_pct, 2),
                'profit_amount': trade.profit_amount,
                'signal_info': trade.signal_info,
            }
            trades_data.append(data)

        with open(trades_file, 'w', encoding='utf-8') as f:
            json.dump(trades_data, f, ensure_ascii=False, indent=2)

        # 일일 결과 저장
        results = self.get_daily_results()
        summary_file = self.output_dir / f"summary_{today}.json"
        summary_data = {
            'date': today,
            'scalping': asdict(results['scalping']),
            'breakout': asdict(results['breakout']),
        }

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        print(f"\n결과 저장: {trades_file}")
        print(f"요약 저장: {summary_file}")

    def print_comparison(self):
        """비교 결과 출력"""
        results = self.get_daily_results()

        print("\n" + "=" * 60)
        print("전략 비교 결과")
        print("=" * 60)
        print(f"{'':20} {'현재(체결강도)':>15} {'변동성돌파':>15}")
        print("-" * 60)

        s = results['scalping']
        b = results['breakout']

        print(f"{'총 거래':20} {s.total_trades:>15} {b.total_trades:>15}")
        print(f"{'승/패':20} {f'{s.win_count}/{s.loss_count}':>15} {f'{b.win_count}/{b.loss_count}':>15}")
        print(f"{'승률':20} {f'{s.win_rate:.1f}%':>15} {f'{b.win_rate:.1f}%':>15}")
        print(f"{'평균수익률':20} {f'{s.avg_profit_pct:+.2f}%':>15} {f'{b.avg_profit_pct:+.2f}%':>15}")
        print(f"{'순손익':20} {f'{s.net_profit:+,}':>15} {f'{b.net_profit:+,}':>15}")
        print(f"{'최대수익':20} {f'{s.max_profit:+,}':>15} {f'{b.max_profit:+,}':>15}")
        print(f"{'최대손실':20} {f'{s.max_loss:,}':>15} {f'{b.max_loss:,}':>15}")
        print("=" * 60)

        # 승자 판정
        if s.net_profit > b.net_profit:
            winner = "현재 전략 (체결강도+호가+MA)"
        elif b.net_profit > s.net_profit:
            winner = "변동성 돌파 (Larry Williams)"
        else:
            winner = "무승부"

        print(f"\n오늘의 승자: {winner}")


# ============================================================
# 실시간 시뮬레이션 (WebSocket 없이 폴링)
# ============================================================

async def run_polling_simulation(simulator: ScalpingSimulator, poll_interval: float = 2.0, kis_client=None, volatile_count: int = 10):
    """폴링 방식 시뮬레이션 (KIS REST API, 2초 간격)

    동적 종목 업데이트: 5분마다 인트라데이 스코어 CSV에서 변동성 상위 종목 재선정
    """
    print(f"\n실시간 시뮬레이션 시작 ({poll_interval}초 간격 폴링)")
    print("동적 종목 업데이트: 5분마다 변동성 상위 종목 재선정")
    print("종료: Ctrl+C\n")

    # 전일 데이터 로드
    simulator.load_prev_day_data()

    # 종목명 캐시
    stock_names = {}
    for code in simulator.stock_codes:
        stock_names[code] = stock.get_market_ticker_name(code)

    last_prices = {}
    update_count = 0

    # 동적 종목 업데이트용 변수
    last_stock_update = datetime.now()
    last_csv_file = None
    stock_update_interval = 300  # 5분 (초)

    while True:
        now = datetime.now()

        # 장 시간 체크: 09:00 ~ 15:30
        if now.hour < 9 or (now.hour == 15 and now.minute >= 30) or now.hour >= 16:
            print(f"[{now.strftime('%H:%M:%S')}] 시뮬레이션 시간이 아닙니다 (09:00~15:30)")
            await asyncio.sleep(10)
            continue

        # 동적 종목 업데이트 (5분마다)
        if volatile_count > 0 and (now - last_stock_update).total_seconds() >= stock_update_interval:
            try:
                scores_dir = Path(__file__).parent / "output" / "intraday_scores"
                csv_files = sorted(scores_dir.glob("*.csv"), reverse=True)

                if csv_files:
                    latest_file = csv_files[0]

                    # 새 파일이 있으면 종목 업데이트
                    if last_csv_file != latest_file.name:
                        print(f"\n[{now.strftime('%H:%M:%S')}] 종목 업데이트 감지: {latest_file.name}")

                        # 현재 보유 종목 (포지션 있는 종목은 유지)
                        holding_codes = set()
                        for trade in simulator.trades:
                            if not trade.is_closed:
                                holding_codes.add(trade.stock_code)

                        # 새 변동성 종목 조회
                        new_stocks = get_volatile_stocks(count=volatile_count)

                        if new_stocks:
                            # 보유 종목 + 새 종목 병합
                            merged_codes = list(holding_codes) + [c for c in new_stocks if c not in holding_codes]
                            merged_codes = merged_codes[:volatile_count + len(holding_codes)]  # 최대 개수 제한

                            # 새로 추가된 종목
                            added = [c for c in merged_codes if c not in simulator.stock_codes]
                            removed = [c for c in simulator.stock_codes if c not in merged_codes and c not in holding_codes]

                            if added or removed:
                                simulator.stock_codes = merged_codes

                                # 새 종목 이름 캐시
                                for code in added:
                                    if code not in stock_names:
                                        stock_names[code] = stock.get_market_ticker_name(code)

                                # 새 종목 전일 데이터 로드
                                simulator.load_prev_day_data()

                                print(f"  추가: {[stock_names.get(c, c) for c in added]}")
                                print(f"  제거: {[stock_names.get(c, c) for c in removed]}")
                                print(f"  현재 추적: {len(simulator.stock_codes)}개\n")

                        last_csv_file = latest_file.name

                last_stock_update = now

            except Exception as e:
                print(f"[종목 업데이트 오류] {e}")

        # 현재가 조회 (KIS REST API 사용)
        try:
            for code in simulator.stock_codes:
                try:
                    name = stock_names.get(code, code)

                    # KIS API로 현재가 조회
                    if kis_client:
                        price_data = kis_client.get_current_price(code)
                        if price_data:
                            current_price = price_data.get('current_price', 0)
                            open_price = price_data.get('open_price', 0)
                            volume = price_data.get('volume', 0)
                        else:
                            continue
                    else:
                        # fallback: pykrx
                        today_str = now.strftime("%Y%m%d")
                        df = stock.get_market_ohlcv(today_str, today_str, code)
                        if df.empty:
                            continue
                        row = df.iloc[0]
                        current_price = int(row['종가'])
                        open_price = int(row['시가'])

                    if current_price <= 0:
                        continue

                    # 시가 업데이트 (최초 1회)
                    if code not in simulator.today_data:
                        open_price = open_price if open_price >= 100 else current_price
                        simulator.update_today_open(code, open_price, name)
                        target = simulator.breakout_targets.get(code, 0)
                        print(f"  {name}: 시가 {open_price:,}원, 목표가 {target:,}원")

                    # 가격 변동 감지
                    prev_price = last_prices.get(code, 0)
                    if prev_price != current_price:
                        change_pct = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
                        if abs(change_pct) >= 0.1:  # 0.1% 이상 변동 시 출력
                            print(f"  [{now.strftime('%H:%M:%S')}] {name}: {current_price:,}원 ({change_pct:+.2f}%)")
                        last_prices[code] = current_price

                    # 가격 업데이트 (전략 처리)
                    simulator.process_price_update(
                        stock_code=code,
                        stock_name=name,
                        current_price=current_price,
                        ask_bid_ratio=0.0,
                        strength_accel=0.0,
                        ma_distance_pct=0.0,
                    )

                except Exception as e:
                    pass

            update_count += 1
            if update_count % 30 == 0:  # 1분마다 상태 출력
                print(f"[{now.strftime('%H:%M:%S')}] 폴링 {update_count}회 완료")

        except Exception as e:
            print(f"[{now.strftime('%H:%M:%S')}] 오류: {e}")

        # 15:20 자동청산
        if now.hour >= 15 and now.minute >= 20:
            print("\n[15:20] 자동청산 시작...")

            # 종가 조회
            closing_prices = {}
            for code in simulator.stock_codes:
                try:
                    if kis_client:
                        price_data = kis_client.get_current_price(code)
                        if price_data:
                            closing_prices[code] = price_data.get('current_price', 0)
                    else:
                        today_str = now.strftime("%Y%m%d")
                        df = stock.get_market_ohlcv(today_str, today_str, code)
                        if not df.empty:
                            closing_prices[code] = int(df.iloc[0]['종가'])
                except:
                    pass

            simulator.close_all_positions(closing_prices)
            simulator.print_comparison()
            simulator.save_results()
            break

        await asyncio.sleep(poll_interval)  # 2초 대기


# ============================================================
# 실시간 시뮬레이션 (WebSocket)
# ============================================================

class WebSocketSimulator:
    """WebSocket 기반 실시간 시뮬레이터"""

    def __init__(
        self,
        simulator: ScalpingSimulator,
        app_key: str,
        app_secret: str,
        is_virtual: bool = False,
    ):
        self.simulator = simulator
        self.ws = KISWebSocket(app_key, app_secret, is_virtual=is_virtual)

        # 체결강도 히스토리 (가속도 계산용)
        self._strength_history: Dict[str, deque] = {}
        self._last_strength: Dict[str, float] = {}

        # 호가 데이터
        self._orderbook: Dict[str, OrderbookData] = {}

        # MA 계산용 시가 데이터
        self._ohlcv_cache: Dict[str, pd.DataFrame] = {}

    async def start(self):
        """시뮬레이션 시작"""
        print("\n[WebSocket] 실시간 시뮬레이션 시작")
        print("종료: Ctrl+C\n")

        # 전일 데이터 로드
        self.simulator.load_prev_day_data()

        # OHLCV 캐시 로드 (MA 계산용)
        self._load_ohlcv_cache()

        # 콜백 설정
        self.ws.on_execution = self._on_execution
        self.ws.on_orderbook = self._on_orderbook
        self.ws.on_connect = self._on_connect

        # WebSocket 연결
        connected = await self.ws.connect()
        if not connected:
            print("[WebSocket] 연결 실패")
            return

        # 종목 구독
        await self.ws.subscribe(self.simulator.stock_codes, include_orderbook=True)

        # 버퍼 초기화
        for code in self.simulator.stock_codes:
            self._strength_history[code] = deque(maxlen=60)  # 최근 60개 체결

        # 메시지 수신 루프
        try:
            await self._run_with_market_close()
        finally:
            await self.ws.disconnect()

    async def _run_with_market_close(self):
        """장 마감 체크 포함 실행"""
        loop = asyncio.get_event_loop()
        ws_task = loop.create_task(self.ws.run_forever())

        while True:
            now = datetime.now()

            # 15:00 자동청산
            if now.hour >= 15:
                print("\n[WebSocket] 15:00 자동청산 시작...")

                # 마지막 체결가로 청산
                closing_prices = {}
                for code in self.simulator.stock_codes:
                    executions = self.ws.get_recent_executions(code, 1)
                    if executions:
                        closing_prices[code] = executions[-1].price

                self.simulator.close_all_positions(closing_prices)
                self.simulator.print_comparison()
                self.simulator.save_results()
                ws_task.cancel()
                break

            await asyncio.sleep(10)

    async def _on_connect(self):
        """연결 완료 콜백"""
        print("[WebSocket] 연결 완료")

    async def _on_execution(self, data: ExecutionData):
        """체결 데이터 콜백"""
        code = data.stock_code
        now = datetime.now()

        # 09:30 이전은 시가만 기록하고 신호 무시
        is_before_trading = now.hour < 9 or (now.hour == 9 and now.minute < 30)

        # 시가 업데이트 (최초 1회)
        if code not in self.simulator.today_data:
            # open_price가 비정상적이면 (100원 미만) 현재가 사용
            open_price = data.open_price if data.open_price >= 100 else data.price
            self.simulator.update_today_open(code, open_price, data.stock_name)
            target = self.simulator.breakout_targets.get(code, 0)
            print(f"  [{data.stock_name}] 시가 {open_price:,}원, 목표가 {target:,}원")

        # 체결강도 히스토리 저장
        self._strength_history[code].append({
            'time': now,
            'strength': data.exec_strength,
        })
        self._last_strength[code] = data.exec_strength

        # 체결강도 가속도 계산 (최근 10초 vs 이전 10초)
        strength_accel = self._calc_strength_acceleration(code)

        # 호가 비율 계산
        orderbook = self._orderbook.get(code)
        ask_bid_ratio = 0.0
        if orderbook and orderbook.total_ask_qty > 0:
            ask_bid_ratio = orderbook.total_bid_qty / orderbook.total_ask_qty

        # MA 거리 계산 (5일 이동평균)
        ma_distance_pct = self._calc_ma_distance(code, data.price)

        # 09:30 이전은 데이터 수집만, 신호 처리 안함
        if is_before_trading:
            return

        # 시뮬레이터에 가격 업데이트
        self.simulator.process_price_update(
            stock_code=code,
            stock_name=data.stock_name,
            current_price=data.price,
            ask_bid_ratio=ask_bid_ratio,
            strength_accel=strength_accel,
            ma_distance_pct=ma_distance_pct,
        )

    async def _on_orderbook(self, data: OrderbookData):
        """호가 데이터 콜백"""
        self._orderbook[data.stock_code] = data

    def _calc_strength_acceleration(self, code: str) -> float:
        """체결강도 가속도 계산 (최근 10초 평균 - 이전 10초 평균)"""
        history = list(self._strength_history.get(code, []))
        if len(history) < 10:
            return 0.0

        now = datetime.now()

        # 최근 10초
        recent = [h['strength'] for h in history if (now - h['time']).total_seconds() <= 10]
        # 이전 10~20초
        prev = [h['strength'] for h in history if 10 < (now - h['time']).total_seconds() <= 20]

        if not recent or not prev:
            return 0.0

        recent_avg = sum(recent) / len(recent)
        prev_avg = sum(prev) / len(prev)

        return recent_avg - prev_avg

    def _load_ohlcv_cache(self):
        """OHLCV 캐시 로드 (MA 계산용)"""
        print("OHLCV 데이터 로드 중...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        for code in self.simulator.stock_codes:
            try:
                df = stock.get_market_ohlcv(
                    start_date.strftime("%Y%m%d"),
                    end_date.strftime("%Y%m%d"),
                    code
                )
                if not df.empty:
                    self._ohlcv_cache[code] = df
            except:
                pass

        print(f"  {len(self._ohlcv_cache)}개 종목 OHLCV 로드 완료")

    def _calc_ma_distance(self, code: str, current_price: int) -> float:
        """5일 이동평균 대비 거리 (%)"""
        df = self._ohlcv_cache.get(code)
        if df is None or len(df) < 5:
            return 0.0

        ma5 = df['종가'].tail(5).mean()
        if ma5 == 0:
            return 0.0

        return ((current_price - ma5) / ma5) * 100


async def run_websocket_simulation(
    simulator: ScalpingSimulator,
    user_id: int = 2,
    volatile_count: int = 10,
):
    """WebSocket 기반 실시간 시뮬레이션"""
    if not WEBSOCKET_AVAILABLE:
        print("[오류] WebSocket 모듈을 사용할 수 없습니다.")
        print("폴링 모드로 전환합니다.")
        await run_polling_simulation(simulator, poll_interval=2.0, kis_client=None, volatile_count=volatile_count)
        return

    # API 키 조회
    logger = TradeLogger()
    api_data = logger.get_api_key_settings(user_id)

    if not api_data or not api_data.get('app_key'):
        print(f"[오류] user_id={user_id}의 API 키가 없습니다.")
        return

    is_virtual = bool(api_data.get('is_mock', False))
    mode_str = "모의투자" if is_virtual else "실전투자"
    print(f"[WebSocket] {mode_str} 모드 (user_id={user_id})")

    ws_sim = WebSocketSimulator(
        simulator=simulator,
        app_key=api_data['app_key'],
        app_secret=api_data['app_secret'],
        is_virtual=is_virtual,
    )

    await ws_sim.start()


def get_top_trading_stocks(count: int = 20) -> List[str]:
    """거래대금 상위 종목 조회"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        df = stock.get_market_ohlcv(today, market="ALL")

        if df.empty:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            df = stock.get_market_ohlcv(yesterday, market="ALL")

        if df.empty:
            return []

        # 거래대금 기준 정렬
        df = df.sort_values('거래대금', ascending=False)
        return df.head(count).index.tolist()

    except Exception as e:
        print(f"종목 조회 오류: {e}")
        return []


def get_volatile_stocks(
    count: int = 10,
    min_volatility_pct: float = 4.0,
    max_change_pct: float = 25.0,  # 상한가/하한가 제외
    min_trading_value: int = 50,   # 억원
    min_market_cap: int = 500,     # 억원
) -> List[str]:
    """
    변동성 큰 종목 필터링 (인트라데이 스코어 CSV 활용)

    조건:
    - 전일 변동폭 >= min_volatility_pct%
    - 등락률 < max_change_pct% (상한가/하한가 제외)
    - 거래대금 >= min_trading_value억
    - 시총 >= min_market_cap억 (작전주 제외)
    """
    try:
        # 최신 인트라데이 스코어 CSV 찾기
        scores_dir = Path(__file__).parent / "output" / "intraday_scores"
        csv_files = sorted(scores_dir.glob("*.csv"), reverse=True)

        if not csv_files:
            print("인트라데이 스코어 파일이 없습니다.")
            return _get_volatile_stocks_pykrx(count, min_volatility_pct, min_trading_value, min_market_cap)

        # 가장 최근 파일 사용
        latest_file = csv_files[0]
        df = pd.read_csv(latest_file, encoding='utf-8-sig')

        print(f"\n[변동성 필터] {latest_file.name} 기준")

        # 변동폭 계산 (고가-저가)/종가 × 100
        df['변동폭'] = ((df['high'] - df['low']) / df['close'] * 100).round(2)

        # trading_value_억 컬럼 사용
        if 'trading_value_억' not in df.columns:
            df['trading_value_억'] = 0

        # 시총 (prev_marcap)
        if 'prev_marcap' not in df.columns:
            df['prev_marcap'] = 0

        # 필터링
        filtered = df[
            (df['변동폭'] >= min_volatility_pct) &
            (df['change_pct'].abs() < max_change_pct) &  # 상한가/하한가 제외
            (df['trading_value_억'] >= min_trading_value) &
            (df['prev_marcap'] >= min_market_cap * 100_000_000)  # 억원 → 원
        ].copy()

        # 변동폭 기준 정렬
        filtered = filtered.sort_values('변동폭', ascending=False)

        result = filtered.head(count)['code'].astype(str).str.zfill(6).tolist()

        print(f"  조건: 변동폭 {min_volatility_pct}%+, 등락률 ±{max_change_pct}% 미만, 거래대금 {min_trading_value}억+, 시총 {min_market_cap}억+")
        print(f"  결과: {len(result)}개 종목\n")

        for _, row in filtered.head(10).iterrows():
            code = str(row['code']).zfill(6)
            name = row.get('name', code)
            vol = row['변동폭']
            value = row.get('trading_value_억', 0)
            chg = row.get('change_pct', 0)
            print(f"    {name}({code}): 변동폭 {vol:.1f}%, 등락률 {chg:+.1f}%, 거래대금 {value:.0f}억")

        return result

    except Exception as e:
        print(f"변동성 종목 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return []


def _get_volatile_stocks_pykrx(
    count: int,
    min_volatility_pct: float,
    min_trading_value: int,
    min_market_cap: int,
) -> List[str]:
    """pykrx 폴백 (CSV 없을 때)"""
    try:
        today = datetime.now()
        for i in range(1, 10):
            prev_date = (today - timedelta(days=i)).strftime("%Y%m%d")
            try:
                df = stock.get_market_ohlcv(prev_date, market="ALL")
                if not df.empty:
                    break
            except:
                continue
        else:
            print("전일 데이터를 찾을 수 없습니다.")
            return []

        df['변동폭'] = ((df['고가'] - df['저가']) / df['종가'] * 100).round(2)

        filtered = df[
            (df['변동폭'] >= min_volatility_pct) &
            (df['거래대금'] >= min_trading_value * 100_000_000)
        ].copy()

        filtered = filtered.sort_values('변동폭', ascending=False)
        return filtered.head(count).index.tolist()

    except Exception as e:
        print(f"pykrx 폴백 오류: {e}")
        return []


def generate_report():
    """누적 결과 리포트 생성"""
    output_dir = Path(__file__).parent / "output" / "scalping_simulation"

    if not output_dir.exists():
        print("시뮬레이션 결과가 없습니다.")
        return

    # 모든 summary 파일 로드
    summaries = []
    for f in sorted(output_dir.glob("summary_*.json")):
        with open(f, 'r', encoding='utf-8') as file:
            summaries.append(json.load(file))

    if not summaries:
        print("시뮬레이션 결과가 없습니다.")
        return

    print("=" * 70)
    print("누적 결과 리포트")
    print("=" * 70)

    # 전략별 누적 통계
    for strategy in ['scalping', 'breakout']:
        total_trades = sum(s[strategy]['total_trades'] for s in summaries)
        total_wins = sum(s[strategy]['win_count'] for s in summaries)
        total_profit = sum(s[strategy]['net_profit'] for s in summaries)

        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

        strategy_name = "체결강도+호가+MA" if strategy == 'scalping' else "변동성 돌파"
        print(f"\n[{strategy_name}]")
        print(f"  총 거래: {total_trades}회")
        print(f"  승률: {win_rate:.1f}%")
        print(f"  누적 손익: {total_profit:+,}원")

    # 일별 상세
    print("\n" + "-" * 70)
    print(f"{'날짜':12} {'체결강도':>12} {'변동성돌파':>12} {'승자':>12}")
    print("-" * 70)

    for s in summaries:
        date = s['date']
        scalp = s['scalping']['net_profit']
        brk = s['breakout']['net_profit']
        winner = "체결강도" if scalp > brk else ("변동성돌파" if brk > scalp else "무승부")
        print(f"{date:12} {scalp:>+12,} {brk:>+12,} {winner:>12}")

    print("=" * 70)


async def main():
    parser = argparse.ArgumentParser(description='스캘핑 전략 비교 시뮬레이터')

    parser.add_argument('--stocks', '-s', type=str,
                        help='종목코드 (쉼표 구분)')
    parser.add_argument('--auto-select', '-a', type=int, default=0,
                        help='거래대금 상위 N개 종목 자동 선정')
    parser.add_argument('--report', '-r', action='store_true',
                        help='누적 결과 리포트 출력')

    # 전략 설정
    parser.add_argument('--scalping-sl', type=float, default=-1.0,
                        help='현재전략 손절 %% (기본: -1.0)')
    parser.add_argument('--scalping-tp', type=float, default=1.0,
                        help='현재전략 익절 %% (기본: 1.0)')
    parser.add_argument('--breakout-k', type=float, default=0.5,
                        help='변동성돌파 K값 (기본: 0.5)')
    parser.add_argument('--breakout-sl', type=float, default=-2.0,
                        help='변동성돌파 손절 %% (기본: -2.0)')

    # WebSocket 설정
    parser.add_argument('--websocket', '-w', action='store_true',
                        help='WebSocket 실시간 모드 (기본: 폴링)')
    parser.add_argument('--user-id', '-u', type=int, default=2,
                        help='API 키 사용자 ID (기본: 2)')

    # 변동성 필터 설정
    parser.add_argument('--volatile', '-v', type=int, default=0,
                        help='변동성 상위 N개 종목 (전일 변동폭 기준)')
    parser.add_argument('--min-vol', type=float, default=4.0,
                        help='최소 변동폭 %% (기본: 4.0)')
    parser.add_argument('--min-value', type=int, default=50,
                        help='최소 거래대금 (억원, 기본: 50)')
    parser.add_argument('--min-cap', type=int, default=500,
                        help='최소 시총 (억원, 기본: 500)')

    # 실제 주문 설정
    parser.add_argument('--execute', '-e', action='store_true',
                        help='실제 주문 실행 (모의투자 권장)')
    parser.add_argument('--investment', '-i', type=int, default=100000,
                        help='종목당 투자금액 (기본: 100,000원)')

    args = parser.parse_args()

    # 리포트 모드
    if args.report:
        generate_report()
        return

    # 종목 선정
    stock_codes = []
    if args.stocks:
        stock_codes = [c.strip() for c in args.stocks.split(',')]

    if args.volatile > 0:
        # 변동성 기준 선정 (권장)
        print(f"\n변동성 상위 {args.volatile}개 종목 조회 중...")
        volatile_stocks = get_volatile_stocks(
            count=args.volatile,
            min_volatility_pct=args.min_vol,
            min_trading_value=args.min_value,
            min_market_cap=args.min_cap,
        )
        stock_codes.extend(volatile_stocks)
    elif args.auto_select > 0:
        # 거래대금 기준 (기존 방식)
        print(f"거래대금 상위 {args.auto_select}개 종목 조회 중...")
        auto_stocks = get_top_trading_stocks(args.auto_select)
        stock_codes.extend(auto_stocks)

    if not stock_codes:
        print("오류: 종목을 지정해주세요 (--stocks, --auto-select, 또는 --volatile)")
        return

    stock_codes = list(set(stock_codes))  # 중복 제거
    print(f"대상 종목: {len(stock_codes)}개")

    # KIS 클라이언트 생성 (폴링/실제주문용)
    kis_client = None
    try:
        from api.services.kis_client import KISClient
        logger = TradeLogger()
        api_data = logger.get_api_key_settings(args.user_id)
        if api_data and api_data.get('app_key'):
            kis_client = KISClient(
                app_key=api_data['app_key'],
                app_secret=api_data['app_secret'],
                account_number=api_data.get('account_number', ''),
                account_product_code=api_data.get('account_product_code', '01'),
                is_virtual=bool(api_data.get('is_mock', False))
            )
            print(f"[KIS] API 클라이언트 초기화 완료 (user_id={args.user_id})")
    except Exception as e:
        print(f"[KIS] 클라이언트 초기화 실패: {e}")

    # 실제 주문 모드 확인
    if args.execute:
        if not kis_client:
            print("[오류] 실제 주문 모드에는 KIS 클라이언트가 필요합니다.")
            return
        print(f"[실제주문] 모드 활성화 - 종목당 {args.investment:,}원")
        print(f"[실제주문] 주가 10만원 이상 종목은 1주만 매매")

    # 시뮬레이터 생성
    simulator = ScalpingSimulator(
        stock_codes=stock_codes,
        scalping_stop_loss=args.scalping_sl,
        scalping_take_profit=args.scalping_tp,
        breakout_k=args.breakout_k,
        breakout_stop_loss=args.breakout_sl,
        investment_per_stock=args.investment,
        execute_mode=args.execute,
        kis_client=kis_client,
    )

    # 시그널 핸들러
    def shutdown(sig, frame):
        print("\n종료 신호 수신...")
        simulator.print_comparison()
        simulator.save_results()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 실행 모드 선택
    volatile_count = args.volatile if args.volatile > 0 else 0
    if args.websocket:
        print("[모드] WebSocket 실시간")
        await run_websocket_simulation(simulator, user_id=args.user_id, volatile_count=volatile_count)
    else:
        print("[모드] 폴링 (2초 간격, KIS REST API)")
        await run_polling_simulation(simulator, poll_interval=2.0, kis_client=kis_client, volatile_count=volatile_count)


if __name__ == "__main__":
    asyncio.run(main())
