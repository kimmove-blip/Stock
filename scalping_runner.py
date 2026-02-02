#!/usr/bin/env python3
"""
초단타 매매 실행기

WebSocket 실시간 데이터 + 신호 감지 + 자동 매매

사용법:
    # Dry-run (모의 거래)
    python scalping_runner.py --dry-run --stocks 005930,035420

    # 실전 매매 (user_id 필요)
    python scalping_runner.py --user-id 2 --stocks 005930

    # 거래대금 상위 종목 자동 선정
    python scalping_runner.py --dry-run --auto-select 10

알고리즘:
    1. 호가창: 매도잔량 > 매수잔량 × 2 (매도 우위)
    2. 체결강도: 10초간 가속도 +5 이상
    3. 기술적: 60틱 MA20 지지
    4. 진입: 3가지 조건 모두 충족 시 시장가 매수
    5. 청산: -1.5% 손절 / +0.5% 익절
"""

import asyncio
import argparse
import signal
import sys
from datetime import datetime, time
from typing import List, Optional
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent))

from trading.realtime.kis_websocket import KISWebSocket, ExecutionData, OrderbookData
from trading.realtime.scalping_detector import ScalpingSignalDetector, ScalpingSignal, SignalStrength
from trading.realtime.scalping_trader import ScalpingTrader, Position, CloseReason


class ScalpingRunner:
    """초단타 매매 실행기"""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        is_virtual: bool = True,
        dry_run: bool = True,
        stock_codes: List[str] = None,
        # 신호 감지 설정
        ask_bid_ratio: float = 2.0,
        strength_threshold: float = 5.0,
        ma_threshold_pct: float = 0.5,
        # 거래 설정
        stop_loss_pct: float = -1.5,
        take_profit_pct: float = 0.5,
        investment_per_stock: int = 500_000,
        max_positions: int = 3,
        # 기타
        verbose: bool = True,
    ):
        self.is_virtual = is_virtual
        self.dry_run = dry_run
        self.stock_codes = stock_codes or []
        self.verbose = verbose

        # WebSocket 클라이언트
        self.ws = KISWebSocket(
            app_key=app_key,
            app_secret=app_secret,
            is_virtual=is_virtual,
        )

        # 신호 감지기
        self.detector = ScalpingSignalDetector(
            ask_bid_ratio_threshold=ask_bid_ratio,
            strength_acceleration_threshold=strength_threshold,
            ma_threshold_pct=ma_threshold_pct,
            tick_size=60,
            ma_period=20,
        )

        # 트레이더
        self.trader = ScalpingTrader(
            kis_client=None,  # WebSocket 사용 시 별도 클라이언트 필요
            dry_run=dry_run,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            investment_per_stock=investment_per_stock,
            max_positions=max_positions,
            on_fill=self._on_fill,
            on_close=self._on_close,
        )

        # 상태
        self._running = False
        self._start_time: Optional[datetime] = None

    async def start(self):
        """실행 시작"""
        print("=" * 60)
        print("초단타 매매 시스템 시작")
        print("=" * 60)
        print(f"모드: {'DRY-RUN (모의거래)' if self.dry_run else '실전 매매'}")
        print(f"계좌: {'모의투자' if self.is_virtual else '실전투자'}")
        print(f"대상 종목: {', '.join(self.stock_codes)}")
        print(f"손절: {self.trader.stop_loss_pct}%")
        print(f"익절: {self.trader.take_profit_pct}%")
        print(f"종목당 투자금: {self.trader.investment_per_stock:,}원")
        print("=" * 60)

        # 장 시간 체크
        if not self._is_market_hours():
            print("\n⚠️  현재 장 시간이 아닙니다.")
            print("장 시간: 09:00 ~ 15:30")

            if not self.dry_run:
                print("실전 매매는 장 시간에만 가능합니다.")
                return

            print("Dry-run 모드로 계속합니다.\n")

        # WebSocket 콜백 설정
        self.ws.on_execution = self._on_execution
        self.ws.on_orderbook = self._on_orderbook
        self.ws.on_connect = self._on_ws_connect
        self.ws.on_disconnect = self._on_ws_disconnect
        self.ws.on_error = self._on_ws_error

        # 연결
        connected = await self.ws.connect()
        if not connected:
            print("WebSocket 연결 실패")
            return

        # 종목 구독
        if self.stock_codes:
            await self.ws.subscribe(self.stock_codes, include_orderbook=True)

        self._running = True
        self._start_time = datetime.now()

        print("\n실시간 데이터 수신 대기 중...")
        print("종료: Ctrl+C\n")

        # 메인 루프
        try:
            await self.ws.run_forever()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self):
        """실행 중지"""
        self._running = False

        # 전체 청산
        if self.trader.position_count > 0:
            print("\n포지션 전체 청산 중...")
            await self.trader.close_all(CloseReason.MANUAL)

        # WebSocket 종료
        await self.ws.disconnect()

        # 결과 출력
        self._print_summary()

    async def _on_execution(self, data: ExecutionData):
        """체결 데이터 수신 콜백"""
        code = data.stock_code

        # 1. 보유 포지션 모니터링
        if code in [p.stock_code for p in self.trader.active_positions]:
            await self.trader.monitor_position(code, data.price)

        # 2. 신호 감지
        signal = self.detector.process_execution(data)

        if signal and signal.should_buy:
            await self._handle_buy_signal(signal)
        elif signal and signal.signal_count >= 2 and self.verbose:
            # 2개 조건 충족 시 로그
            self._log_signal(signal)

    async def _on_orderbook(self, data: OrderbookData):
        """호가 데이터 수신 콜백"""
        self.detector.update_orderbook(data)

    async def _on_ws_connect(self):
        """WebSocket 연결 콜백"""
        print("[WS] 연결됨")

    async def _on_ws_disconnect(self):
        """WebSocket 연결 해제 콜백"""
        print("[WS] 연결 해제됨")

    async def _on_ws_error(self, error: Exception):
        """WebSocket 오류 콜백"""
        print(f"[WS] 오류: {error}")

    async def _on_fill(self, position: Position):
        """매수 체결 콜백"""
        print(f"\n🟢 매수 체결: {position.stock_code} "
              f"{position.quantity}주 @ {position.entry_price:,}원")

    async def _on_close(self, position: Position):
        """청산 완료 콜백"""
        emoji = "🟢" if position.profit_loss >= 0 else "🔴"
        print(f"\n{emoji} 청산: {position.stock_code} "
              f"@ {position.close_price:,}원 "
              f"({position.close_reason.value}) "
              f"P/L: {position.profit_loss:+,}원 ({position.profit_loss_pct:+.2f}%)")

    async def _handle_buy_signal(self, signal: ScalpingSignal):
        """매수 신호 처리"""
        print(f"\n{'='*50}")
        print(f"🎯 매수 신호: {signal.stock_code}")
        print(f"   체결강도: {signal.exec_strength:.1f} (가속도: {signal.strength_acceleration:+.1f})")
        print(f"   호가비율: {signal.ask_bid_ratio:.2f} (매도/매수)")
        print(f"   MA20: {signal.ma20_price:,.0f} (거리: {signal.ma_distance_pct:+.2f}%)")
        print(f"   현재가: {signal.current_price:,}원")
        print(f"{'='*50}")

        # 매수 실행
        result = await self.trader.on_buy_signal(signal)

        if not result.success:
            print(f"   ❌ 매수 실패: {result.error}")

    def _log_signal(self, signal: ScalpingSignal):
        """신호 로그"""
        conditions = []
        if signal.orderbook_signal:
            conditions.append(f"호가({signal.ask_bid_ratio:.1f})")
        if signal.momentum_signal:
            conditions.append(f"강도({signal.strength_acceleration:+.1f})")
        if signal.ma_support_signal:
            conditions.append(f"MA20({signal.ma_distance_pct:+.1f}%)")

        print(f"[신호] {signal.stock_code}: {', '.join(conditions)}")

    def _is_market_hours(self) -> bool:
        """장 시간 여부"""
        now = datetime.now()

        # 주말 체크
        if now.weekday() >= 5:
            return False

        # 시간 체크 (09:00 ~ 15:30)
        market_open = time(9, 0)
        market_close = time(15, 30)

        return market_open <= now.time() <= market_close

    def _print_summary(self):
        """결과 요약 출력"""
        stats = self.trader.stats
        runtime = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0

        print("\n" + "=" * 60)
        print("거래 결과 요약")
        print("=" * 60)
        print(f"실행 시간: {runtime/60:.1f}분")
        print(f"총 거래: {stats['total_trades']}회")
        print(f"승/패: {stats['win_count']}/{stats['loss_count']} "
              f"(승률: {stats['win_rate']:.1f}%)")
        print(f"총 수익: {stats['total_profit']:+,}원")
        print(f"총 손실: {stats['total_loss']:,}원")
        print(f"순손익: {stats['net_profit']:+,}원")
        print(f"최대 수익: {stats['max_profit']:+,}원")
        print(f"최대 손실: {stats['max_loss']:,}원")
        print("=" * 60)


def get_top_trading_stocks(count: int = 10) -> List[str]:
    """거래대금 상위 종목 조회"""
    try:
        from pykrx import stock

        today = datetime.now().strftime("%Y%m%d")
        df = stock.get_market_ohlcv(today, market="ALL")

        if df.empty:
            # 전일 데이터 사용
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            df = stock.get_market_ohlcv(yesterday, market="ALL")

        if df.empty:
            print("거래 데이터를 가져올 수 없습니다.")
            return []

        # 거래대금 기준 정렬
        df = df.sort_values('거래대금', ascending=False)

        # 상위 N개 종목
        top_codes = df.head(count).index.tolist()
        return top_codes

    except Exception as e:
        print(f"종목 조회 오류: {e}")
        return []


def load_credentials(user_id: int = None) -> dict:
    """API 자격 증명 로드"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    if user_id:
        # DB에서 사용자 설정 로드
        try:
            from trading.trade_logger import TradeLogger
            logger = TradeLogger()
            settings = logger.get_api_key_settings(user_id)

            if settings:
                return {
                    'app_key': settings.get('app_key'),
                    'app_secret': settings.get('app_secret'),
                    'is_virtual': bool(settings.get('is_mock', True)),
                }
        except Exception as e:
            print(f"사용자 설정 로드 실패: {e}")

    # 환경 변수 사용
    return {
        'app_key': os.getenv('KIS_APP_KEY'),
        'app_secret': os.getenv('KIS_APP_SECRET'),
        'is_virtual': os.getenv('KIS_IS_VIRTUAL', 'true').lower() == 'true',
    }


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='초단타 매매 실행기')

    # 필수 옵션
    parser.add_argument('--stocks', '-s', type=str,
                        help='종목코드 (쉼표 구분, 예: 005930,035420)')
    parser.add_argument('--auto-select', '-a', type=int, default=0,
                        help='거래대금 상위 N개 종목 자동 선정')

    # 계정 설정
    parser.add_argument('--user-id', '-u', type=int,
                        help='사용자 ID (DB에서 API 키 로드)')
    parser.add_argument('--dry-run', '-d', action='store_true',
                        help='모의 거래 모드 (실제 주문 X)')

    # 신호 설정
    parser.add_argument('--ask-bid-ratio', type=float, default=2.0,
                        help='매도/매수 잔량 비율 기준 (기본: 2.0)')
    parser.add_argument('--strength-threshold', type=float, default=5.0,
                        help='체결강도 가속도 기준 (기본: 5.0)')
    parser.add_argument('--ma-threshold', type=float, default=0.5,
                        help='MA 근접 기준 %% (기본: 0.5)')

    # 거래 설정 (2026년 거래세 감안, 손익비 1:1 이상)
    parser.add_argument('--stop-loss', type=float, default=-1.0,
                        help='손절 기준 %% (기본: -1.0)')
    parser.add_argument('--take-profit', type=float, default=1.0,
                        help='익절 기준 %% (기본: 1.0)')
    parser.add_argument('--investment', type=int, default=500_000,
                        help='종목당 투자금 (기본: 500,000)')
    parser.add_argument('--max-positions', type=int, default=3,
                        help='최대 동시 보유 종목 (기본: 3)')

    # 기타
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='상세 로그 출력')

    args = parser.parse_args()

    # 종목 코드 파싱
    stock_codes = []
    if args.stocks:
        stock_codes = [c.strip() for c in args.stocks.split(',') if c.strip()]

    if args.auto_select > 0:
        print(f"거래대금 상위 {args.auto_select}개 종목 조회 중...")
        auto_stocks = get_top_trading_stocks(args.auto_select)
        stock_codes.extend(auto_stocks)
        print(f"선정된 종목: {', '.join(auto_stocks)}")

    if not stock_codes:
        print("오류: 종목을 지정해주세요 (--stocks 또는 --auto-select)")
        parser.print_help()
        return

    # 자격 증명 로드
    creds = load_credentials(args.user_id)

    if not creds.get('app_key') or not creds.get('app_secret'):
        print("오류: KIS API 키가 설정되지 않았습니다.")
        print("환경 변수 KIS_APP_KEY, KIS_APP_SECRET을 설정하거나 --user-id를 사용하세요.")
        return

    # 러너 생성
    runner = ScalpingRunner(
        app_key=creds['app_key'],
        app_secret=creds['app_secret'],
        is_virtual=creds['is_virtual'],
        dry_run=args.dry_run,
        stock_codes=list(set(stock_codes)),  # 중복 제거
        ask_bid_ratio=args.ask_bid_ratio,
        strength_threshold=args.strength_threshold,
        ma_threshold_pct=args.ma_threshold,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
        investment_per_stock=args.investment,
        max_positions=args.max_positions,
        verbose=args.verbose,
    )

    # 시그널 핸들러
    loop = asyncio.get_event_loop()

    def shutdown():
        print("\n종료 신호 수신...")
        loop.create_task(runner.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    # 실행
    await runner.start()


if __name__ == "__main__":
    asyncio.run(main())
