"""
틱 차트 생성 모듈

실시간 체결 데이터를 틱 기반 캔들로 변환
60틱 기준 이동평균선 계산

사용법:
    from trading.realtime import TickChart

    chart = TickChart(tick_size=60, ma_periods=[5, 20])

    # 체결 데이터가 들어올 때마다 호출
    candle = chart.add_tick(price=10500, volume=100)

    if candle:
        print(f"캔들 완성: {candle}")

    # 현재 MA20 값
    ma20 = chart.get_ma(20)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Deque
from collections import deque
import statistics


@dataclass
class TickCandle:
    """틱 기반 캔들"""
    tick_count: int          # 틱 수 (예: 60)
    open: int                # 시가
    high: int                # 고가
    low: int                 # 저가
    close: int               # 종가
    volume: int              # 거래량
    amount: int              # 거래대금
    avg_price: float         # 평균가 (VWAP)
    start_time: datetime     # 시작 시간
    end_time: datetime       # 종료 시간
    tick_prices: List[int] = field(default_factory=list)  # 개별 틱 가격


class TickChart:
    """틱 차트 생성기"""

    def __init__(
        self,
        tick_size: int = 60,
        ma_periods: List[int] = None,
        max_candles: int = 500,
    ):
        """
        Args:
            tick_size: 캔들당 틱 수 (기본 60)
            ma_periods: 이동평균 기간 리스트 (기본 [5, 20, 60])
            max_candles: 최대 캔들 보관 수
        """
        self.tick_size = tick_size
        self.ma_periods = ma_periods or [5, 20, 60]
        self.max_candles = max_candles

        # 완성된 캔들 저장
        self._candles: Deque[TickCandle] = deque(maxlen=max_candles)

        # 진행 중인 캔들 데이터
        self._current_tick_count = 0
        self._current_open: Optional[int] = None
        self._current_high: Optional[int] = None
        self._current_low: Optional[int] = None
        self._current_close: Optional[int] = None
        self._current_volume = 0
        self._current_amount = 0
        self._current_start: Optional[datetime] = None
        self._current_prices: List[int] = []

        # 이동평균 캐시
        self._ma_cache: Dict[int, float] = {}

    def add_tick(
        self,
        price: int,
        volume: int = 1,
        timestamp: Optional[datetime] = None
    ) -> Optional[TickCandle]:
        """
        틱 데이터 추가

        Args:
            price: 체결가
            volume: 체결수량
            timestamp: 체결시간

        Returns:
            캔들이 완성되면 TickCandle 반환, 아니면 None
        """
        if price <= 0:
            return None

        now = timestamp or datetime.now()

        # 첫 틱
        if self._current_tick_count == 0:
            self._current_open = price
            self._current_high = price
            self._current_low = price
            self._current_start = now

        # 틱 업데이트
        self._current_tick_count += 1
        self._current_high = max(self._current_high, price)
        self._current_low = min(self._current_low, price)
        self._current_close = price
        self._current_volume += volume
        self._current_amount += price * volume
        self._current_prices.append(price)

        # 틱 수 도달 시 캔들 완성
        if self._current_tick_count >= self.tick_size:
            candle = self._complete_candle(now)
            return candle

        return None

    def _complete_candle(self, end_time: datetime) -> TickCandle:
        """캔들 완성"""
        avg_price = self._current_amount / self._current_volume if self._current_volume > 0 else self._current_close

        candle = TickCandle(
            tick_count=self._current_tick_count,
            open=self._current_open,
            high=self._current_high,
            low=self._current_low,
            close=self._current_close,
            volume=self._current_volume,
            amount=self._current_amount,
            avg_price=avg_price,
            start_time=self._current_start,
            end_time=end_time,
            tick_prices=self._current_prices.copy(),
        )

        self._candles.append(candle)
        self._reset_current()
        self._invalidate_ma_cache()

        return candle

    def _reset_current(self):
        """현재 캔들 데이터 초기화"""
        self._current_tick_count = 0
        self._current_open = None
        self._current_high = None
        self._current_low = None
        self._current_close = None
        self._current_volume = 0
        self._current_amount = 0
        self._current_start = None
        self._current_prices = []

    def _invalidate_ma_cache(self):
        """MA 캐시 무효화"""
        self._ma_cache = {}

    def get_ma(self, period: int) -> Optional[float]:
        """
        이동평균 계산

        Args:
            period: MA 기간

        Returns:
            이동평균값 (캔들 부족 시 None)
        """
        if period in self._ma_cache:
            return self._ma_cache[period]

        if len(self._candles) < period:
            return None

        closes = [c.close for c in list(self._candles)[-period:]]
        ma = sum(closes) / len(closes)
        self._ma_cache[period] = ma
        return ma

    def get_ema(self, period: int) -> Optional[float]:
        """
        지수이동평균 계산

        Args:
            period: EMA 기간

        Returns:
            지수이동평균값
        """
        if len(self._candles) < period:
            return None

        closes = [c.close for c in list(self._candles)[-period * 2:]]
        if not closes:
            return None

        multiplier = 2 / (period + 1)
        ema = closes[0]

        for price in closes[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def get_current_price(self) -> Optional[int]:
        """현재가 (마지막 틱 가격)"""
        return self._current_close

    def get_last_candle(self) -> Optional[TickCandle]:
        """마지막 완성 캔들"""
        if not self._candles:
            return None
        return self._candles[-1]

    def get_candles(self, count: int = 0) -> List[TickCandle]:
        """
        캔들 리스트 조회

        Args:
            count: 조회할 캔들 수 (0이면 전체)
        """
        if count <= 0:
            return list(self._candles)
        return list(self._candles)[-count:]

    def is_near_ma(
        self,
        ma_period: int,
        threshold_pct: float = 0.5
    ) -> bool:
        """
        현재가가 MA 근처인지 확인

        Args:
            ma_period: MA 기간
            threshold_pct: 허용 범위 (%)

        Returns:
            MA 근처 여부
        """
        current = self.get_current_price()
        ma = self.get_ma(ma_period)

        if current is None or ma is None:
            return False

        diff_pct = abs(current - ma) / ma * 100
        return diff_pct <= threshold_pct

    def is_above_ma(self, ma_period: int) -> Optional[bool]:
        """
        현재가가 MA 위인지 확인

        Returns:
            MA 위: True, MA 아래: False, 판단 불가: None
        """
        current = self.get_current_price()
        ma = self.get_ma(ma_period)

        if current is None or ma is None:
            return None

        return current > ma

    def get_ma_support_signal(
        self,
        ma_period: int = 20,
        lookback: int = 5,
        threshold_pct: float = 0.3
    ) -> bool:
        """
        MA 지지 신호 감지

        조건:
        - 최근 lookback 캔들 중 대부분이 MA 위에 있었음
        - 현재가가 MA에 근접 (threshold_pct 이내)
        - 하락 후 반등 형태

        Args:
            ma_period: MA 기간
            lookback: 확인할 캔들 수
            threshold_pct: MA 근접 판단 기준 (%)

        Returns:
            MA 지지 신호 여부
        """
        ma = self.get_ma(ma_period)
        current = self.get_current_price()

        if ma is None or current is None:
            return False

        candles = self.get_candles(lookback + 1)
        if len(candles) < lookback:
            return False

        # 최근 캔들들이 MA 위에 있었는지
        above_ma_count = sum(1 for c in candles[:-1] if c.close > ma)
        if above_ma_count < lookback * 0.6:  # 60% 이상이 MA 위
            return False

        # 현재가가 MA 근처인지
        diff_pct = abs(current - ma) / ma * 100
        if diff_pct > threshold_pct:
            return False

        # 하락 후 반등 형태 (최근 캔들이 하락 -> 현재 반등)
        last_candle = candles[-1]
        if last_candle.close > last_candle.open:  # 양봉
            if last_candle.low <= ma:  # 저점이 MA 터치
                return True

        return current >= ma  # MA 위로 복귀

    def get_momentum(self, period: int = 5) -> Optional[float]:
        """
        모멘텀 계산 (N캔들 전 대비 변화율)

        Returns:
            변화율 (%)
        """
        candles = self.get_candles(period + 1)
        if len(candles) < period + 1:
            return None

        old_close = candles[0].close
        current_close = candles[-1].close

        if old_close == 0:
            return None

        return (current_close - old_close) / old_close * 100

    def get_volatility(self, period: int = 20) -> Optional[float]:
        """
        변동성 계산 (종가 표준편차)

        Returns:
            변동성 (표준편차)
        """
        candles = self.get_candles(period)
        if len(candles) < period:
            return None

        closes = [c.close for c in candles]
        return statistics.stdev(closes)

    def clear(self):
        """차트 데이터 초기화"""
        self._candles.clear()
        self._reset_current()
        self._invalidate_ma_cache()

    @property
    def candle_count(self) -> int:
        """완성된 캔들 수"""
        return len(self._candles)

    @property
    def current_tick_count(self) -> int:
        """현재 진행 중인 틱 수"""
        return self._current_tick_count

    def to_dict(self) -> Dict:
        """상태 딕셔너리 변환"""
        return {
            'tick_size': self.tick_size,
            'candle_count': self.candle_count,
            'current_tick_count': self.current_tick_count,
            'current_price': self.get_current_price(),
            'ma5': self.get_ma(5),
            'ma20': self.get_ma(20),
            'ma60': self.get_ma(60),
        }
