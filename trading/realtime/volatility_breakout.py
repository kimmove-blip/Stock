"""
변동성 돌파 전략 (Larry Williams)

Reference 프로그램 (엘리의 자동매매)의 핵심 전략 구현

알고리즘:
    목표가 = 금일 시가 + (전일 고가 - 전일 저가) × K
    K = 0.5 (기본값)

진입:
    - 현재가 >= 목표가 돌파 시 매수

청산:
    - 익일 시가 매도 (오버나이트)
    - 또는 당일 장마감 청산 (데이트레이딩)
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Dict, List
from enum import Enum


class BreakoutStatus(Enum):
    """돌파 상태"""
    WAITING = "waiting"          # 목표가 대기
    BREAKOUT = "breakout"        # 돌파 발생
    ENTERED = "entered"          # 진입 완료
    CLOSED = "closed"            # 청산 완료


@dataclass
class BreakoutSignal:
    """변동성 돌파 신호"""
    stock_code: str
    stock_name: str
    timestamp: datetime

    # 가격 정보
    prev_high: int               # 전일 고가
    prev_low: int                # 전일 저가
    prev_close: int              # 전일 종가
    today_open: int              # 금일 시가
    current_price: int           # 현재가

    # 계산값
    volatility: int              # 변동폭 (전일 고가 - 저가)
    k_value: float               # K값 (기본 0.5)
    target_price: int            # 목표가

    # 신호
    is_breakout: bool = False    # 돌파 여부
    breakout_pct: float = 0.0    # 목표가 대비 상승률

    # 추가 필터
    volume_condition: bool = True   # 거래량 조건
    price_condition: bool = True    # 가격 조건 (상한가 제외 등)

    @property
    def should_buy(self) -> bool:
        """매수 신호"""
        return (
            self.is_breakout and
            self.volume_condition and
            self.price_condition and
            self.breakout_pct < 5.0  # 5% 이상 급등 시 제외
        )

    def to_dict(self) -> Dict:
        return {
            'stock_code': self.stock_code,
            'stock_name': self.stock_name,
            'timestamp': self.timestamp.isoformat(),
            'prev_high': self.prev_high,
            'prev_low': self.prev_low,
            'today_open': self.today_open,
            'current_price': self.current_price,
            'volatility': self.volatility,
            'k_value': self.k_value,
            'target_price': self.target_price,
            'is_breakout': self.is_breakout,
            'breakout_pct': round(self.breakout_pct, 2),
            'should_buy': self.should_buy,
        }


class VolatilityBreakoutDetector:
    """변동성 돌파 감지기"""

    def __init__(
        self,
        k_value: float = 0.5,              # K값 (변동폭 배수)
        min_volatility_pct: float = 2.0,   # 최소 변동폭 (%)
        max_breakout_pct: float = 5.0,     # 최대 돌파율 (급등 제외)
        min_volume_ratio: float = 1.0,     # 최소 거래량 비율
    ):
        self.k_value = k_value
        self.min_volatility_pct = min_volatility_pct
        self.max_breakout_pct = max_breakout_pct
        self.min_volume_ratio = min_volume_ratio

        # 종목별 데이터 캐시
        self._prev_data: Dict[str, Dict] = {}  # 전일 데이터
        self._today_data: Dict[str, Dict] = {} # 금일 데이터
        self._signals: Dict[str, BreakoutSignal] = {}  # 발생한 신호
        self._entered: set = set()  # 진입 완료 종목

    def set_prev_day_data(self, stock_code: str, high: int, low: int, close: int):
        """전일 데이터 설정"""
        self._prev_data[stock_code] = {
            'high': high,
            'low': low,
            'close': close,
        }

    def set_today_open(self, stock_code: str, open_price: int, stock_name: str = ""):
        """금일 시가 설정"""
        self._today_data[stock_code] = {
            'open': open_price,
            'name': stock_name,
        }

    def calculate_target(self, stock_code: str) -> Optional[int]:
        """목표가 계산"""
        prev = self._prev_data.get(stock_code)
        today = self._today_data.get(stock_code)

        if not prev or not today:
            return None

        volatility = prev['high'] - prev['low']
        target = today['open'] + int(volatility * self.k_value)
        return target

    def check_breakout(
        self,
        stock_code: str,
        current_price: int,
        volume_ratio: float = 1.0,
    ) -> Optional[BreakoutSignal]:
        """돌파 체크"""
        # 이미 진입한 종목은 제외
        if stock_code in self._entered:
            return None

        prev = self._prev_data.get(stock_code)
        today = self._today_data.get(stock_code)

        if not prev or not today:
            return None

        volatility = prev['high'] - prev['low']
        target_price = today['open'] + int(volatility * self.k_value)

        # 최소 변동폭 체크
        volatility_pct = (volatility / prev['close']) * 100 if prev['close'] > 0 else 0
        price_condition = volatility_pct >= self.min_volatility_pct

        # 거래량 조건
        volume_condition = volume_ratio >= self.min_volume_ratio

        # 돌파 체크
        is_breakout = current_price >= target_price
        breakout_pct = ((current_price - target_price) / target_price * 100) if target_price > 0 else 0

        signal = BreakoutSignal(
            stock_code=stock_code,
            stock_name=today.get('name', stock_code),
            timestamp=datetime.now(),
            prev_high=prev['high'],
            prev_low=prev['low'],
            prev_close=prev['close'],
            today_open=today['open'],
            current_price=current_price,
            volatility=volatility,
            k_value=self.k_value,
            target_price=target_price,
            is_breakout=is_breakout,
            breakout_pct=breakout_pct,
            volume_condition=volume_condition,
            price_condition=price_condition and (breakout_pct < self.max_breakout_pct),
        )

        if signal.should_buy:
            self._signals[stock_code] = signal

        return signal

    def mark_entered(self, stock_code: str):
        """진입 완료 표시"""
        self._entered.add(stock_code)

    def reset_daily(self):
        """일일 리셋"""
        self._today_data.clear()
        self._signals.clear()
        self._entered.clear()

    def get_all_targets(self) -> Dict[str, int]:
        """모든 종목의 목표가 조회"""
        targets = {}
        for code in self._prev_data:
            target = self.calculate_target(code)
            if target:
                targets[code] = target
        return targets
