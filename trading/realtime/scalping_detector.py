"""
초단타 매매 신호 감지기

핵심 알고리즘:
1. 호가창 분석: 매도잔량 > 매수잔량 × 2 (매도 우위 = 매수 타이밍)
2. 체결강도 가속도: 최근 10초간 체결강도 급상승
3. 기술적 타점: 60틱 MA20 지지선 근접

사용법:
    from trading.realtime import ScalpingSignalDetector, ScalpingSignal

    detector = ScalpingSignalDetector()

    # 체결 데이터 수신 시
    signal = detector.process_execution(execution_data)

    # 호가 데이터 수신 시
    detector.update_orderbook(orderbook_data)

    # 매수 신호 확인
    if signal and signal.should_buy:
        print(f"매수 신호: {signal}")
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Deque
from collections import deque
from enum import Enum

from .kis_websocket import ExecutionData, OrderbookData
from .tick_chart import TickChart


class SignalStrength(Enum):
    """신호 강도"""
    NONE = 0
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class ScalpingSignal:
    """초단타 매매 신호"""
    stock_code: str
    timestamp: datetime

    # 개별 조건 충족 여부
    orderbook_signal: bool = False    # 호가창 매도 우위
    momentum_signal: bool = False     # 체결강도 가속도
    ma_support_signal: bool = False   # MA 지지

    # VI(변동성 완화장치) 상태
    vi_active: bool = False           # VI 발동 여부

    # 신호 세부 정보
    ask_bid_ratio: float = 0.0        # 매도/매수 잔량 비율
    strength_acceleration: float = 0.0  # 체결강도 가속도
    current_price: int = 0
    ma20_price: float = 0.0
    ma_distance_pct: float = 0.0      # MA와의 거리 (%)

    # 추가 정보
    exec_strength: float = 0.0        # 현재 체결강도
    volume_surge: bool = False        # 거래량 급증
    price_momentum: float = 0.0       # 가격 모멘텀 (%)

    @property
    def should_buy(self) -> bool:
        """매수 신호 여부 (3가지 조건 모두 충족 + VI 미발동)"""
        if self.vi_active:
            return False  # VI 발동 시 매수 금지
        return self.orderbook_signal and self.momentum_signal and self.ma_support_signal

    @property
    def signal_count(self) -> int:
        """충족된 조건 수"""
        return sum([
            self.orderbook_signal,
            self.momentum_signal,
            self.ma_support_signal,
        ])

    @property
    def strength(self) -> SignalStrength:
        """신호 강도"""
        count = self.signal_count
        if count == 0:
            return SignalStrength.NONE
        elif count == 1:
            return SignalStrength.WEAK
        elif count == 2:
            return SignalStrength.MODERATE
        elif count == 3:
            if self.ask_bid_ratio >= 3.0 and self.strength_acceleration >= 10:
                return SignalStrength.VERY_STRONG
            return SignalStrength.STRONG
        return SignalStrength.NONE

    def to_dict(self) -> Dict:
        """딕셔너리 변환"""
        return {
            'stock_code': self.stock_code,
            'timestamp': self.timestamp.isoformat(),
            'should_buy': self.should_buy,
            'signal_count': self.signal_count,
            'strength': self.strength.name,
            'orderbook_signal': self.orderbook_signal,
            'momentum_signal': self.momentum_signal,
            'ma_support_signal': self.ma_support_signal,
            'ask_bid_ratio': round(self.ask_bid_ratio, 2),
            'strength_acceleration': round(self.strength_acceleration, 2),
            'current_price': self.current_price,
            'ma20_price': round(self.ma20_price, 0),
            'ma_distance_pct': round(self.ma_distance_pct, 2),
            'exec_strength': round(self.exec_strength, 2),
        }


class ScalpingSignalDetector:
    """초단타 매매 신호 감지기"""

    def __init__(
        self,
        # 호가창 조건
        ask_bid_ratio_threshold: float = 2.0,  # 매도/매수 비율 기준

        # 체결강도 조건
        strength_window_seconds: int = 10,     # 체결강도 측정 구간 (초)
        strength_acceleration_threshold: float = 5.0,  # 체결강도 가속도 기준
        min_strength_level: float = 100.0,     # 최소 체결강도 (100% 이상)

        # MA 지지 조건
        tick_size: int = 60,                   # 틱 캔들 크기
        ma_period: int = 20,                   # MA 기간
        ma_threshold_pct: float = 0.5,         # MA 근접 기준 (%)

        # 거래량 필터 (단주 거래 필터링 강화)
        min_exec_volume: int = 100,            # 최소 체결수량 (노이즈 필터)
        min_exec_amount: int = 30_000_000,     # 최소 체결금액 (3천만원으로 상향)

        # 신호 발생 쿨다운
        signal_cooldown_seconds: int = 3,      # 신호 발생 후 쿨다운 (초)
    ):
        # 조건 임계값
        self.ask_bid_ratio_threshold = ask_bid_ratio_threshold
        self.strength_window_seconds = strength_window_seconds
        self.strength_acceleration_threshold = strength_acceleration_threshold
        self.min_strength_level = min_strength_level
        self.tick_size = tick_size
        self.ma_period = ma_period
        self.ma_threshold_pct = ma_threshold_pct
        self.min_exec_volume = min_exec_volume
        self.min_exec_amount = min_exec_amount
        self.signal_cooldown_seconds = signal_cooldown_seconds

        # 종목별 데이터
        self._tick_charts: Dict[str, TickChart] = {}
        self._orderbooks: Dict[str, OrderbookData] = {}
        self._strength_history: Dict[str, Deque] = {}  # (timestamp, strength)
        self._last_signal_time: Dict[str, datetime] = {}

        # VI(변동성 완화장치) 상태 추적
        self._vi_status: Dict[str, bool] = {}  # 종목별 VI 발동 여부
        self._last_exec_time: Dict[str, datetime] = {}  # 마지막 체결 시간 (VI 감지용)

    def process_execution(self, data: ExecutionData) -> Optional[ScalpingSignal]:
        """
        체결 데이터 처리 및 신호 생성

        Args:
            data: 실시간 체결 데이터

        Returns:
            매수 신호 (조건 충족 시)
        """
        code = data.stock_code

        # 노이즈 필터링
        if data.exec_volume < self.min_exec_volume:
            return None

        exec_amount = data.price * data.exec_volume
        if exec_amount < self.min_exec_amount:
            return None

        # 초기화
        if code not in self._tick_charts:
            self._tick_charts[code] = TickChart(
                tick_size=self.tick_size,
                ma_periods=[5, self.ma_period, 60]
            )
        if code not in self._strength_history:
            self._strength_history[code] = deque(maxlen=1000)

        # 틱 차트 업데이트
        tick_chart = self._tick_charts[code]
        tick_chart.add_tick(data.price, data.exec_volume, data.timestamp)

        # 체결강도 히스토리 업데이트
        self._strength_history[code].append((data.timestamp, data.exec_strength))

        # VI 감지를 위한 마지막 체결 시간 업데이트
        self._last_exec_time[code] = data.timestamp

        # VI 해제 확인 (체결 재개 시)
        if self._vi_status.get(code, False):
            self._vi_status[code] = False  # 체결 수신 = VI 해제

        # 쿨다운 체크
        if code in self._last_signal_time:
            elapsed = (datetime.now() - self._last_signal_time[code]).total_seconds()
            if elapsed < self.signal_cooldown_seconds:
                return None

        # 신호 생성
        signal = self._generate_signal(code, data)

        # 쿨다운 업데이트 (신호 발생 시)
        if signal and signal.signal_count >= 2:
            self._last_signal_time[code] = datetime.now()

        return signal

    def update_orderbook(self, data: OrderbookData):
        """호가 데이터 업데이트"""
        self._orderbooks[data.stock_code] = data

    def _check_vi_status(self, code: str) -> bool:
        """VI(변동성 완화장치) 발동 여부 감지

        VI 발동 시:
        - 2분간 체결 데이터 중단
        - 단일가 매매 전환

        감지 방법:
        - 마지막 체결 후 5초 이상 체결 없음 = VI 의심
        - 체결강도 급변 (100% 이상 → 0 등)
        """
        now = datetime.now()
        last_exec = self._last_exec_time.get(code)

        if last_exec:
            gap_seconds = (now - last_exec).total_seconds()
            # 5초 이상 체결 없으면 VI 의심
            if gap_seconds > 5.0:
                self._vi_status[code] = True
                return True

        # VI 해제 확인 (체결 재개)
        self._vi_status[code] = False
        return False

    def update_vi_status(self, code: str, is_vi_active: bool):
        """외부에서 VI 상태 업데이트 (WebSocket 메시지 기반)"""
        self._vi_status[code] = is_vi_active

    def _generate_signal(self, code: str, exec_data: ExecutionData) -> ScalpingSignal:
        """신호 생성"""
        now = datetime.now()

        # VI 상태 확인
        vi_active = self._vi_status.get(code, False)

        signal = ScalpingSignal(
            stock_code=code,
            timestamp=now,
            current_price=exec_data.price,
            exec_strength=exec_data.exec_strength,
            vi_active=vi_active,
        )

        # 1. 호가창 분석
        signal.orderbook_signal, signal.ask_bid_ratio = self._check_orderbook(code, exec_data)

        # 2. 체결강도 가속도
        signal.momentum_signal, signal.strength_acceleration = self._check_strength_momentum(code)

        # 3. MA 지지
        signal.ma_support_signal, signal.ma20_price, signal.ma_distance_pct = self._check_ma_support(code)

        # 추가 정보
        signal.volume_surge = self._check_volume_surge(code)
        signal.price_momentum = self._get_price_momentum(code)

        return signal

    def _check_orderbook(self, code: str, exec_data: ExecutionData) -> tuple:
        """
        호가창 매도 우위 확인

        매도잔량 > 매수잔량 × threshold (기본 2배)
        → 매수세가 적극적으로 매수 중임을 의미

        Returns:
            (신호 여부, 매도/매수 비율)
        """
        # 호가 데이터 확인
        orderbook = self._orderbooks.get(code)

        # 호가 데이터가 없으면 체결 데이터의 잔량 사용
        if orderbook:
            total_ask = orderbook.total_ask_qty
            total_bid = orderbook.total_bid_qty
        else:
            total_ask = exec_data.total_ask_qty
            total_bid = exec_data.total_bid_qty

        if total_bid == 0:
            return False, float('inf')

        ratio = total_ask / total_bid

        # 매도잔량이 매수잔량의 threshold배 이상
        signal = ratio >= self.ask_bid_ratio_threshold

        return signal, ratio

    def _check_strength_momentum(self, code: str) -> tuple:
        """
        체결강도 가속도 확인

        최근 N초간 체결강도 변화율 측정

        Returns:
            (신호 여부, 가속도)
        """
        history = self._strength_history.get(code)
        if not history or len(history) < 2:
            return False, 0.0

        now = datetime.now()
        cutoff = now - timedelta(seconds=self.strength_window_seconds)

        # 최근 N초 데이터 필터
        recent = [(t, s) for t, s in history if t >= cutoff]
        if len(recent) < 2:
            return False, 0.0

        # 시작과 끝 체결강도
        start_strength = recent[0][1]
        end_strength = recent[-1][1]

        # 가속도 계산 (체결강도 변화)
        acceleration = end_strength - start_strength

        # 추가: 평균 대비 현재 강도
        avg_strength = sum(s for _, s in recent) / len(recent)

        # 조건: 가속도가 임계값 이상 & 현재 강도가 min_strength_level 이상
        # 체결강도 100% 이상은 매수세 > 매도세를 의미
        signal = (
            acceleration >= self.strength_acceleration_threshold and
            end_strength >= self.min_strength_level
        )

        return signal, acceleration

    def _check_ma_support(self, code: str) -> tuple:
        """
        60틱 MA20 지지 확인

        현재가가 MA20 근처이고, 지지 패턴 형성

        Returns:
            (신호 여부, MA20 가격, MA와의 거리 %)
        """
        tick_chart = self._tick_charts.get(code)
        if not tick_chart:
            return False, 0.0, 0.0

        ma20 = tick_chart.get_ma(self.ma_period)
        current = tick_chart.get_current_price()

        if ma20 is None or current is None:
            return False, 0.0, 0.0

        # MA와의 거리 계산
        distance_pct = (current - ma20) / ma20 * 100

        # 조건 1: 현재가가 MA 근처 (-threshold ~ +threshold)
        near_ma = abs(distance_pct) <= self.ma_threshold_pct

        # 조건 2: MA 지지 패턴 (이전에 MA 위에 있다가 하락 후 지지)
        support_pattern = tick_chart.get_ma_support_signal(
            ma_period=self.ma_period,
            lookback=5,
            threshold_pct=self.ma_threshold_pct
        )

        # 조건 3: MA 위에 있거나 근접
        above_or_near = distance_pct >= -self.ma_threshold_pct

        signal = (near_ma or support_pattern) and above_or_near

        return signal, ma20, distance_pct

    def _check_volume_surge(self, code: str) -> bool:
        """거래량 급증 확인"""
        tick_chart = self._tick_charts.get(code)
        if not tick_chart:
            return False

        candles = tick_chart.get_candles(10)
        if len(candles) < 5:
            return False

        # 최근 5개 캔들 평균 거래량
        recent_volumes = [c.volume for c in candles[-5:]]
        avg_volume = sum(recent_volumes[:-1]) / 4 if len(recent_volumes) > 1 else 0

        # 마지막 캔들이 평균의 2배 이상
        if avg_volume > 0:
            return recent_volumes[-1] >= avg_volume * 2

        return False

    def _get_price_momentum(self, code: str) -> float:
        """가격 모멘텀 (5캔들 변화율)"""
        tick_chart = self._tick_charts.get(code)
        if not tick_chart:
            return 0.0

        momentum = tick_chart.get_momentum(5)
        return momentum or 0.0

    def get_tick_chart(self, code: str) -> Optional[TickChart]:
        """종목 틱 차트 조회"""
        return self._tick_charts.get(code)

    def get_orderbook(self, code: str) -> Optional[OrderbookData]:
        """종목 호가 데이터 조회"""
        return self._orderbooks.get(code)

    def get_status(self, code: str) -> Dict:
        """종목 상태 조회"""
        tick_chart = self._tick_charts.get(code)
        orderbook = self._orderbooks.get(code)
        strength_history = self._strength_history.get(code, [])

        return {
            'code': code,
            'tick_chart': tick_chart.to_dict() if tick_chart else None,
            'orderbook': {
                'ask_bid_ratio': orderbook.imbalance_ratio if orderbook else None,
                'total_ask': orderbook.total_ask_qty if orderbook else None,
                'total_bid': orderbook.total_bid_qty if orderbook else None,
            } if orderbook else None,
            'strength_history_count': len(strength_history),
            'last_strength': strength_history[-1][1] if strength_history else None,
        }

    def reset(self, code: Optional[str] = None):
        """데이터 초기화"""
        if code:
            self._tick_charts.pop(code, None)
            self._orderbooks.pop(code, None)
            self._strength_history.pop(code, None)
            self._last_signal_time.pop(code, None)
        else:
            self._tick_charts.clear()
            self._orderbooks.clear()
            self._strength_history.clear()
            self._last_signal_time.clear()


class MultiStockScalpingDetector:
    """다종목 초단타 신호 감지기"""

    def __init__(
        self,
        max_stocks: int = 20,
        **detector_kwargs
    ):
        """
        Args:
            max_stocks: 최대 감시 종목 수
            **detector_kwargs: ScalpingSignalDetector 파라미터
        """
        self.max_stocks = max_stocks
        self._detectors: Dict[str, ScalpingSignalDetector] = {}
        self._detector_kwargs = detector_kwargs

        # 전체 신호 히스토리
        self._signal_history: Deque[ScalpingSignal] = deque(maxlen=1000)

    def add_stock(self, code: str):
        """종목 추가"""
        if code not in self._detectors:
            if len(self._detectors) >= self.max_stocks:
                # 가장 오래된 종목 제거
                oldest = next(iter(self._detectors))
                del self._detectors[oldest]

            self._detectors[code] = ScalpingSignalDetector(**self._detector_kwargs)

    def remove_stock(self, code: str):
        """종목 제거"""
        self._detectors.pop(code, None)

    def process_execution(self, data: ExecutionData) -> Optional[ScalpingSignal]:
        """체결 데이터 처리"""
        code = data.stock_code

        if code not in self._detectors:
            self.add_stock(code)

        signal = self._detectors[code].process_execution(data)

        if signal and signal.signal_count >= 2:
            self._signal_history.append(signal)

        return signal

    def update_orderbook(self, data: OrderbookData):
        """호가 데이터 업데이트"""
        code = data.stock_code

        if code not in self._detectors:
            self.add_stock(code)

        self._detectors[code].update_orderbook(data)

    def get_buy_signals(self, min_strength: SignalStrength = SignalStrength.STRONG) -> List[ScalpingSignal]:
        """매수 신호 종목 조회"""
        return [
            s for s in self._signal_history
            if s.should_buy and s.strength.value >= min_strength.value
        ]

    def get_recent_signals(self, seconds: int = 60) -> List[ScalpingSignal]:
        """최근 신호 조회"""
        cutoff = datetime.now() - timedelta(seconds=seconds)
        return [s for s in self._signal_history if s.timestamp >= cutoff]

    @property
    def active_stocks(self) -> List[str]:
        """활성 종목 리스트"""
        return list(self._detectors.keys())
