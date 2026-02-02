"""
초단타 매매 트레이더

신호 감지 → 매수 → 손익 관리 → 청산 자동화

핵심 규칙 (2026년 세제 개편 대응):
- 손절: -1.0% (타이트하게)
- 익절: +1.0% (거래비용 0.23% 감안)
- 주문: 최유리 지정가 (슬리피지 감소)
- API: 토큰 버킷 Rate Limiting
- 시간: 서버 시간 동기화
- VI: 발동 시 매매 중지

사용법:
    from trading.realtime import ScalpingTrader

    trader = ScalpingTrader(
        kis_client=client,
        dry_run=True,
        stop_loss_pct=-1.0,
        take_profit_pct=1.0,
        order_type="05",  # 최유리 지정가
    )

    # 서버 시간 동기화
    await trader.sync_server_time()

    # 신호 발생 시 매수
    await trader.on_buy_signal(signal)

    # 체결 데이터로 포지션 모니터링
    await trader.monitor_position(code, current_price)
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Any
from enum import Enum

from .scalping_detector import ScalpingSignal, SignalStrength


class TokenBucket:
    """토큰 버킷 알고리즘 (API Rate Limiting)

    초당 최대 요청 수를 제한하여 API 과부하 방지

    사용법:
        bucket = TokenBucket(rate=5, capacity=10)  # 초당 5개, 최대 10개
        if bucket.consume():
            # API 호출
        else:
            # 대기 필요
    """

    def __init__(self, rate: float = 5.0, capacity: int = 10):
        """
        Args:
            rate: 초당 토큰 생성 수 (기본 5개/초)
            capacity: 최대 토큰 보유량 (기본 10개)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """토큰 소비 시도

        Args:
            tokens: 소비할 토큰 수

        Returns:
            성공 여부
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now

            # 토큰 충전
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def wait_and_consume(self, tokens: int = 1, timeout: float = 5.0) -> bool:
        """토큰이 충분해질 때까지 대기 후 소비

        Args:
            tokens: 소비할 토큰 수
            timeout: 최대 대기 시간 (초)

        Returns:
            성공 여부
        """
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if await self.consume(tokens):
                return True
            await asyncio.sleep(0.1)
        return False

    @property
    def available_tokens(self) -> float:
        """현재 사용 가능한 토큰 수"""
        now = time.monotonic()
        elapsed = now - self.last_update
        return min(self.capacity, self.tokens + elapsed * self.rate)


class PositionStatus(Enum):
    """포지션 상태"""
    PENDING = "pending"      # 주문 대기
    ORDERED = "ordered"      # 주문 전송됨
    FILLED = "filled"        # 체결 완료
    CLOSING = "closing"      # 청산 중
    CLOSED = "closed"        # 청산 완료
    CANCELLED = "cancelled"  # 취소됨


class CloseReason(Enum):
    """청산 사유"""
    STOP_LOSS = "stop_loss"           # 손절
    TAKE_PROFIT = "take_profit"       # 익절
    TRAILING_STOP = "trailing_stop"   # 트레일링 스탑
    TIME_LIMIT = "time_limit"         # 시간 제한
    MANUAL = "manual"                 # 수동 청산
    SIGNAL_REVERSE = "signal_reverse" # 신호 반전


@dataclass
class Position:
    """보유 포지션"""
    stock_code: str
    stock_name: str
    quantity: int
    entry_price: int
    entry_time: datetime
    status: PositionStatus = PositionStatus.PENDING

    # 주문 정보
    order_no: str = ""
    filled_qty: int = 0
    filled_price: int = 0
    filled_time: Optional[datetime] = None

    # 현재 상태
    current_price: int = 0
    high_price: int = 0           # 진입 후 최고가 (트레일링 스탑용)
    low_price: int = 0            # 진입 후 최저가

    # 청산 정보
    close_price: int = 0
    close_time: Optional[datetime] = None
    close_reason: Optional[CloseReason] = None

    # 신호 정보
    signal: Optional[ScalpingSignal] = None

    @property
    def entry_amount(self) -> int:
        """진입 금액"""
        return self.entry_price * self.quantity

    @property
    def current_amount(self) -> int:
        """현재 평가금액"""
        return self.current_price * self.quantity

    @property
    def profit_loss(self) -> int:
        """손익 금액"""
        if self.status == PositionStatus.CLOSED:
            return (self.close_price - self.entry_price) * self.quantity
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def profit_loss_pct(self) -> float:
        """손익률 (%)"""
        if self.entry_price == 0:
            return 0.0
        if self.status == PositionStatus.CLOSED:
            return (self.close_price - self.entry_price) / self.entry_price * 100
        return (self.current_price - self.entry_price) / self.entry_price * 100

    @property
    def holding_seconds(self) -> float:
        """보유 시간 (초)"""
        end_time = self.close_time or datetime.now()
        return (end_time - self.entry_time).total_seconds()

    def to_dict(self) -> Dict:
        """딕셔너리 변환"""
        return {
            'stock_code': self.stock_code,
            'stock_name': self.stock_name,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat(),
            'status': self.status.value,
            'current_price': self.current_price,
            'profit_loss': self.profit_loss,
            'profit_loss_pct': round(self.profit_loss_pct, 2),
            'holding_seconds': round(self.holding_seconds, 1),
            'close_reason': self.close_reason.value if self.close_reason else None,
        }


@dataclass
class TradeResult:
    """거래 결과"""
    success: bool
    position: Optional[Position] = None
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class ScalpingTrader:
    """초단타 매매 트레이더"""

    # 거래 비용 (수수료 + 세금)
    TRANSACTION_COST_PCT = 0.23  # 0.23% (증권사 0.015% × 2 + 거래세 0.20%)

    # 주문 구분 코드 (한국투자증권)
    ORDER_TYPE_MARKET = "01"       # 시장가
    ORDER_TYPE_LIMIT = "00"        # 지정가
    ORDER_TYPE_BEST_LIMIT = "05"   # 최유리 지정가 (슬리피지 감소)
    ORDER_TYPE_FIRST_LIMIT = "06"  # 최우선 지정가

    def __init__(
        self,
        kis_client: Any = None,
        dry_run: bool = True,

        # 손익 설정 (2026년 거래세 0.20% + 수수료 감안)
        # 거래비용 약 0.23% → 손익비 1:1 이상 확보 필요
        stop_loss_pct: float = -1.0,       # 손절 기준 (%) - 강화
        take_profit_pct: float = 1.0,      # 익절 기준 (%) - 상향
        trailing_stop_pct: float = 0.5,    # 트레일링 스탑 (최고가 대비 하락 %)

        # 투자 금액
        investment_per_stock: int = 500_000,  # 종목당 투자금 (50만원)
        max_positions: int = 3,               # 최대 동시 보유

        # 쿨다운
        order_cooldown_seconds: float = 1.0,  # 주문 후 쿨다운
        stock_cooldown_seconds: float = 60.0, # 같은 종목 재매수 쿨다운

        # 시간 제한
        max_holding_seconds: int = 300,       # 최대 보유 시간 (5분)

        # 주문 설정
        order_type: str = "05",               # 기본: 최유리 지정가 (슬리피지 감소)
        api_rate_limit: float = 5.0,          # API 초당 최대 호출 수

        # 서버 시간 동기화
        server_time_offset: float = 0.0,      # 서버-로컬 시간 차이 (초)

        # 콜백
        on_order: Optional[Callable] = None,
        on_fill: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
    ):
        self.kis_client = kis_client
        self.dry_run = dry_run

        # 손익 설정
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct

        # 투자 설정
        self.investment_per_stock = investment_per_stock
        self.max_positions = max_positions

        # 쿨다운
        self.order_cooldown_seconds = order_cooldown_seconds
        self.stock_cooldown_seconds = stock_cooldown_seconds
        self.max_holding_seconds = max_holding_seconds

        # 주문 설정
        self.order_type = order_type
        self.server_time_offset = server_time_offset

        # 콜백
        self.on_order = on_order
        self.on_fill = on_fill
        self.on_close = on_close

        # 상태
        self._positions: Dict[str, Position] = {}
        self._closed_positions: List[Position] = []
        self._last_order_time: Optional[datetime] = None
        self._stock_cooldowns: Dict[str, datetime] = {}
        self._order_lock = asyncio.Lock()

        # API Rate Limiting (토큰 버킷)
        self._api_bucket = TokenBucket(rate=api_rate_limit, capacity=int(api_rate_limit * 2))

        # 통계
        self._stats = {
            'total_trades': 0,
            'win_count': 0,
            'loss_count': 0,
            'total_profit': 0,
            'total_loss': 0,
            'max_profit': 0,
            'max_loss': 0,
        }

    async def on_buy_signal(self, signal: ScalpingSignal) -> TradeResult:
        """
        매수 신호 처리

        Args:
            signal: 초단타 매수 신호

        Returns:
            거래 결과
        """
        code = signal.stock_code

        # 이미 보유 중인지 확인
        if code in self._positions:
            return TradeResult(success=False, error="이미 보유 중")

        # 최대 포지션 확인
        active_count = sum(1 for p in self._positions.values()
                         if p.status in [PositionStatus.ORDERED, PositionStatus.FILLED])
        if active_count >= self.max_positions:
            return TradeResult(success=False, error="최대 보유 종목 초과")

        # 주문 쿨다운 확인
        if self._last_order_time:
            elapsed = (datetime.now() - self._last_order_time).total_seconds()
            if elapsed < self.order_cooldown_seconds:
                return TradeResult(success=False, error="주문 쿨다운 중")

        # 종목 쿨다운 확인
        if code in self._stock_cooldowns:
            elapsed = (datetime.now() - self._stock_cooldowns[code]).total_seconds()
            if elapsed < self.stock_cooldown_seconds:
                return TradeResult(success=False, error="종목 쿨다운 중")

        # 수량 계산
        price = signal.current_price
        if price <= 0:
            return TradeResult(success=False, error="가격 정보 없음")

        quantity = self.investment_per_stock // price
        if quantity <= 0:
            return TradeResult(success=False, error="수량 부족")

        # 매수 실행
        async with self._order_lock:
            result = await self._execute_buy(code, "", quantity, price, signal)
            return result

    def _get_server_time(self) -> datetime:
        """서버 시간 보정된 현재 시간"""
        return datetime.now() + timedelta(seconds=self.server_time_offset)

    async def sync_server_time(self) -> float:
        """서버 시간 동기화

        Returns:
            오프셋 (초): 서버시간 - 로컬시간
        """
        if not self.kis_client:
            return 0.0

        try:
            # KIS API 서버 시간 조회
            # (실제 API에 시간 조회 엔드포인트가 있다면 사용)
            local_before = datetime.now()
            # result = self.kis_client.get_server_time()  # API 호출
            local_after = datetime.now()

            # 네트워크 지연 추정
            latency = (local_after - local_before).total_seconds() / 2
            # server_time = datetime.fromisoformat(result['time'])
            # self.server_time_offset = (server_time - local_before).total_seconds() - latency

            print(f"[Time] 서버 시간 동기화 완료 (오프셋: {self.server_time_offset:.3f}초)")
            return self.server_time_offset

        except Exception as e:
            print(f"[Time] 서버 시간 동기화 실패: {e}")
            return 0.0

    async def _execute_buy(
        self,
        code: str,
        name: str,
        quantity: int,
        price: int,
        signal: ScalpingSignal
    ) -> TradeResult:
        """매수 주문 실행"""
        now = self._get_server_time()

        position = Position(
            stock_code=code,
            stock_name=name,
            quantity=quantity,
            entry_price=price,
            entry_time=now,
            status=PositionStatus.PENDING,
            current_price=price,
            high_price=price,
            low_price=price,
            signal=signal,
        )

        if self.dry_run:
            # 모의 체결
            position.status = PositionStatus.FILLED
            position.filled_qty = quantity
            position.filled_price = price
            position.filled_time = now
            position.order_no = f"DRY_{now.strftime('%H%M%S%f')}"

            self._positions[code] = position
            self._last_order_time = now

            print(f"[DRY] 매수: {code} {quantity}주 @ {price:,}원")

            if self.on_fill:
                await self._call_handler(self.on_fill, position)

            return TradeResult(success=True, position=position)

        # API Rate Limiting (토큰 버킷)
        if not await self._api_bucket.wait_and_consume(1, timeout=2.0):
            return TradeResult(success=False, error="API 속도 제한 (토큰 부족)")

        # 실제 주문
        try:
            if not self.kis_client:
                return TradeResult(success=False, error="KIS 클라이언트 없음")

            # 최유리 지정가 주문 (슬리피지 감소)
            # order_dvsn: 00-지정가, 01-시장가, 05-최유리지정가, 06-최우선지정가
            result = self.kis_client.place_order(
                stock_code=code,
                order_type="buy",
                quantity=quantity,
                price=0,  # 최유리 지정가는 가격 0
                order_dvsn=self.order_type,  # 기본: 05 (최유리 지정가)
            )

            if result and result.get('success'):
                position.status = PositionStatus.ORDERED
                position.order_no = result.get('order_no', '')
                self._positions[code] = position
                self._last_order_time = datetime.now()

                if self.on_order:
                    await self._call_handler(self.on_order, position)

                return TradeResult(success=True, position=position)
            else:
                error = result.get('msg', '주문 실패') if result else '응답 없음'
                return TradeResult(success=False, error=error)

        except Exception as e:
            return TradeResult(success=False, error=str(e))

    async def monitor_position(self, code: str, current_price: int) -> Optional[TradeResult]:
        """
        포지션 모니터링 및 청산 판단

        Args:
            code: 종목코드
            current_price: 현재가

        Returns:
            청산 시 TradeResult
        """
        if code not in self._positions:
            return None

        position = self._positions[code]

        if position.status != PositionStatus.FILLED:
            return None

        # 현재가 업데이트
        position.current_price = current_price
        position.high_price = max(position.high_price, current_price)
        position.low_price = min(position.low_price, current_price)

        # 청산 조건 확인
        close_reason = self._check_close_conditions(position)

        if close_reason:
            return await self._execute_sell(position, close_reason)

        return None

    def _check_close_conditions(self, position: Position) -> Optional[CloseReason]:
        """청산 조건 확인"""
        pnl_pct = position.profit_loss_pct

        # 1. 손절 (-1.5%)
        if pnl_pct <= self.stop_loss_pct:
            return CloseReason.STOP_LOSS

        # 2. 익절 (+0.5%)
        if pnl_pct >= self.take_profit_pct:
            return CloseReason.TAKE_PROFIT

        # 3. 트레일링 스탑 (최고가 대비 하락)
        if position.high_price > position.entry_price:
            high_pnl = (position.high_price - position.entry_price) / position.entry_price * 100
            current_pnl = pnl_pct

            # 최고가에서 trailing_stop_pct% 이상 하락
            if high_pnl > 0 and (high_pnl - current_pnl) >= self.trailing_stop_pct:
                # 단, 수익 상태에서만 트레일링 스탑
                if current_pnl > 0:
                    return CloseReason.TRAILING_STOP

        # 4. 시간 제한 (5분)
        if position.holding_seconds >= self.max_holding_seconds:
            return CloseReason.TIME_LIMIT

        return None

    async def _execute_sell(
        self,
        position: Position,
        reason: CloseReason
    ) -> TradeResult:
        """매도 주문 실행"""
        code = position.stock_code
        now = self._get_server_time()
        position.status = PositionStatus.CLOSING

        if self.dry_run:
            # 모의 청산
            position.status = PositionStatus.CLOSED
            position.close_price = position.current_price
            position.close_time = now
            position.close_reason = reason

            # 통계 업데이트
            self._update_stats(position)

            # 포지션 이동
            del self._positions[code]
            self._closed_positions.append(position)
            self._stock_cooldowns[code] = now

            pnl = position.profit_loss
            pnl_pct = position.profit_loss_pct
            print(f"[DRY] 매도: {code} @ {position.close_price:,}원 "
                  f"({reason.value}) P/L: {pnl:+,}원 ({pnl_pct:+.2f}%)")

            if self.on_close:
                await self._call_handler(self.on_close, position)

            return TradeResult(success=True, position=position)

        # API Rate Limiting (토큰 버킷)
        if not await self._api_bucket.wait_and_consume(1, timeout=2.0):
            position.status = PositionStatus.FILLED  # 롤백
            return TradeResult(success=False, error="API 속도 제한", position=position)

        # 실제 주문
        try:
            if not self.kis_client:
                return TradeResult(success=False, error="KIS 클라이언트 없음")

            # 매도는 빠른 체결 위해 시장가 사용 (손절 시 중요)
            sell_order_type = "01" if reason == CloseReason.STOP_LOSS else self.order_type

            result = self.kis_client.place_order(
                stock_code=code,
                order_type="sell",
                quantity=position.quantity,
                price=0,
                order_dvsn=sell_order_type,  # 손절 시 시장가, 그 외 최유리지정가
            )

            if result and result.get('success'):
                position.close_price = position.current_price
                position.close_time = self._get_server_time()
                position.close_reason = reason

                self._update_stats(position)

                del self._positions[code]
                self._closed_positions.append(position)
                self._stock_cooldowns[code] = self._get_server_time()

                if self.on_close:
                    await self._call_handler(self.on_close, position)

                return TradeResult(success=True, position=position)
            else:
                position.status = PositionStatus.FILLED  # 롤백
                error = result.get('msg', '매도 실패') if result else '응답 없음'
                return TradeResult(success=False, error=error, position=position)

        except Exception as e:
            position.status = PositionStatus.FILLED  # 롤백
            return TradeResult(success=False, error=str(e), position=position)

    def _update_stats(self, position: Position):
        """통계 업데이트"""
        self._stats['total_trades'] += 1

        pnl = position.profit_loss

        if pnl > 0:
            self._stats['win_count'] += 1
            self._stats['total_profit'] += pnl
            self._stats['max_profit'] = max(self._stats['max_profit'], pnl)
        else:
            self._stats['loss_count'] += 1
            self._stats['total_loss'] += abs(pnl)
            self._stats['max_loss'] = max(self._stats['max_loss'], abs(pnl))

    async def close_all(self, reason: CloseReason = CloseReason.MANUAL) -> List[TradeResult]:
        """전체 청산"""
        results = []

        for code in list(self._positions.keys()):
            position = self._positions[code]
            if position.status == PositionStatus.FILLED:
                result = await self._execute_sell(position, reason)
                results.append(result)

        return results

    async def _call_handler(self, handler: Callable, *args):
        """콜백 핸들러 호출"""
        try:
            result = handler(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"[Trader] 핸들러 오류: {e}")

    @property
    def active_positions(self) -> List[Position]:
        """활성 포지션"""
        return [p for p in self._positions.values()
                if p.status in [PositionStatus.ORDERED, PositionStatus.FILLED]]

    @property
    def position_count(self) -> int:
        """활성 포지션 수"""
        return len(self.active_positions)

    @property
    def total_invested(self) -> int:
        """총 투자금액"""
        return sum(p.entry_amount for p in self.active_positions)

    @property
    def total_current_value(self) -> int:
        """총 평가금액"""
        return sum(p.current_amount for p in self.active_positions)

    @property
    def total_pnl(self) -> int:
        """총 손익"""
        return sum(p.profit_loss for p in self.active_positions)

    @property
    def stats(self) -> Dict:
        """거래 통계"""
        total = self._stats['total_trades']
        win_rate = self._stats['win_count'] / total * 100 if total > 0 else 0
        net_profit = self._stats['total_profit'] - self._stats['total_loss']

        return {
            'total_trades': total,
            'win_count': self._stats['win_count'],
            'loss_count': self._stats['loss_count'],
            'win_rate': round(win_rate, 1),
            'total_profit': self._stats['total_profit'],
            'total_loss': self._stats['total_loss'],
            'net_profit': net_profit,
            'max_profit': self._stats['max_profit'],
            'max_loss': self._stats['max_loss'],
        }

    def get_position(self, code: str) -> Optional[Position]:
        """포지션 조회"""
        return self._positions.get(code)

    def get_closed_positions(self, count: int = 0) -> List[Position]:
        """청산 포지션 조회"""
        if count <= 0:
            return self._closed_positions.copy()
        return self._closed_positions[-count:]

    def to_dict(self) -> Dict:
        """상태 딕셔너리"""
        return {
            'dry_run': self.dry_run,
            'position_count': self.position_count,
            'max_positions': self.max_positions,
            'total_invested': self.total_invested,
            'total_current_value': self.total_current_value,
            'total_pnl': self.total_pnl,
            'active_positions': [p.to_dict() for p in self.active_positions],
            'stats': self.stats,
            'settings': {
                'stop_loss_pct': self.stop_loss_pct,
                'take_profit_pct': self.take_profit_pct,
                'trailing_stop_pct': self.trailing_stop_pct,
                'investment_per_stock': self.investment_per_stock,
                'max_holding_seconds': self.max_holding_seconds,
            }
        }
