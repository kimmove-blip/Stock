"""
장중 자동매매 전략 기본 클래스
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import pandas as pd


class BaseStrategy(ABC):
    """장중 자동매매 전략 기본 클래스"""

    # 전략 메타정보 (서브클래스에서 오버라이드)
    NAME = "Base Strategy"
    DESCRIPTION = "기본 전략"
    SCORE_COLUMN = "v2"  # 스코어 CSV 컬럼명
    VERSION = "1.0"

    # 기본 설정
    DEFAULT_CONFIG = {
        'score_threshold': 70,
        'max_positions': 5,
        'min_amount': 5_000_000_000,  # 50억
        'max_change': 20.0,  # 최대 등락률 (상한가 제외)
        'exit_rules': {
            'target_atr_mult': 1.5,
            'stop_atr_mult': 0.8,
            'time_stop_days': 3,
            'trailing_start_atr': 0.5
        }
    }

    def __init__(self, config: Dict = None):
        """
        Args:
            config: 전략 설정 (없으면 기본값 사용)
        """
        self.config = {**self.DEFAULT_CONFIG}
        if config:
            self.config.update(config)

    @property
    def score_threshold(self) -> int:
        """매수 스코어 임계값"""
        return self.config.get('score_threshold', 70)

    @property
    def max_positions(self) -> int:
        """최대 포지션 수"""
        return self.config.get('max_positions', 5)

    @property
    def exit_rules(self) -> Dict:
        """청산 규칙"""
        return self.config.get('exit_rules', {})

    @abstractmethod
    def evaluate(self, row: pd.Series, context: Dict = None) -> Dict:
        """
        단일 종목 평가

        Args:
            row: 스코어 CSV의 한 행 (종목 데이터)
            context: 추가 컨텍스트 (시장 상황 등)

        Returns:
            {
                'signal': 'BUY'|'HOLD'|'SKIP',
                'score': int,
                'confidence': float (0~1),
                'reasons': List[str]
            }
        """
        pass

    @abstractmethod
    def filter_candidates(self, df: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """
        후보 종목 필터링

        Args:
            df: 전체 스코어 DataFrame
            context: 추가 컨텍스트

        Returns:
            필터링된 DataFrame
        """
        pass

    def get_entry_signals(
        self,
        df: pd.DataFrame,
        context: Dict = None
    ) -> List[Dict]:
        """
        매수 시그널 생성

        Args:
            df: 스코어 DataFrame
            context: 추가 컨텍스트

        Returns:
            매수 시그널 리스트
            [{'code': str, 'name': str, 'signal': str, 'score': int, ...}, ...]
        """
        # 후보 필터링
        candidates = self.filter_candidates(df, context)

        if candidates.empty:
            return []

        signals = []
        for _, row in candidates.iterrows():
            result = self.evaluate(row, context)

            if result.get('signal') == 'BUY':
                signals.append({
                    'code': row['code'],
                    'name': row.get('name', ''),
                    'price': row.get('close', 0),
                    'score': result.get('score', 0),
                    'confidence': result.get('confidence', 0),
                    'reasons': result.get('reasons', []),
                    'strategy': self.NAME,
                    'strategy_version': self.VERSION
                })

        # 스코어/신뢰도 순 정렬
        signals.sort(key=lambda x: (x['confidence'], x['score']), reverse=True)

        return signals[:self.max_positions]

    def get_exit_params(self, entry_price: int, atr: float = None) -> Dict:
        """
        청산 파라미터 계산

        Args:
            entry_price: 진입가
            atr: ATR 값 (없으면 기본 비율 사용)

        Returns:
            {'target_price': int, 'stop_price': int, ...}
        """
        rules = self.exit_rules

        # ATR이 없으면 가격의 3% 사용
        if atr is None or atr <= 0:
            atr = entry_price * 0.03

        target_mult = rules.get('target_atr_mult', 1.5)
        stop_mult = rules.get('stop_atr_mult', 0.8)
        trailing_mult = rules.get('trailing_start_atr', 0.5)

        return {
            'target_price': int(entry_price + atr * target_mult),
            'stop_price': int(entry_price - atr * stop_mult),
            'trailing_start': int(entry_price + atr * trailing_mult),
            'time_stop_days': rules.get('time_stop_days', 3)
        }

    def check_market_condition(self, context: Dict) -> Tuple[bool, str]:
        """
        시장 상황 체크 (서브클래스에서 오버라이드 가능)

        Args:
            context: 시장 컨텍스트 (지수 등락률 등)

        Returns:
            (거래 가능 여부, 사유)
        """
        if context is None:
            return True, "OK"

        # 시장 급락 시 매수 중단
        kospi_change = context.get('kospi_change', 0)
        kosdaq_change = context.get('kosdaq_change', 0)

        if kospi_change < -3 or kosdaq_change < -3:
            return False, "시장 급락 (-3% 이상)"

        return True, "OK"

    def calculate_position_size(
        self,
        total_capital: int,
        current_price: int,
        max_ratio: float = 0.1
    ) -> int:
        """
        포지션 크기 계산

        Args:
            total_capital: 총 투자금
            current_price: 현재가
            max_ratio: 종목당 최대 비중

        Returns:
            매수 수량
        """
        max_amount = int(total_capital * max_ratio)
        quantity = max_amount // current_price

        return max(quantity, 0)

    def __repr__(self) -> str:
        return f"{self.NAME} (v{self.VERSION})"


class TrendFollowingMixin:
    """추세 추종 전략용 믹스인"""

    def check_trend_alignment(self, row: pd.Series) -> Tuple[bool, List[str]]:
        """이평선 정배열 체크"""
        signals = row.get('signals', '')
        reasons = []

        if 'MA_ALIGNED' in signals:
            reasons.append("이평선 정배열")
            return True, reasons

        return False, reasons

    def check_macd_bullish(self, row: pd.Series) -> Tuple[bool, List[str]]:
        """MACD 상승 체크"""
        signals = row.get('signals', '')
        reasons = []

        if 'MACD_BULL' in signals:
            reasons.append("MACD 상승")
            return True, reasons

        return False, reasons

    def check_ma20_slope(self, row: pd.Series) -> Tuple[bool, List[str]]:
        """20일 이평선 기울기 체크"""
        signals = row.get('signals', '')
        reasons = []

        if 'MA_20_VERY_STEEP' in signals:
            reasons.append("MA20 급등세")
            return True, reasons
        elif 'MA_20_STEEP' in signals:
            reasons.append("MA20 상승세")
            return True, reasons

        return False, reasons


class ContrarianMixin:
    """역발상 전략용 믹스인"""

    def check_oversold(self, row: pd.Series) -> Tuple[bool, List[str]]:
        """과매도 체크"""
        signals = row.get('signals', '')
        reasons = []

        if 'RSI_OVERSOLD' in signals:
            reasons.append("RSI 과매도")
            return True, reasons

        return False, reasons

    def check_support_level(self, row: pd.Series) -> Tuple[bool, List[str]]:
        """지지선 근처 체크"""
        signals = row.get('signals', '')
        reasons = []

        if 'NEAR_SUPPORT' in signals or 'BB_LOWER' in signals:
            reasons.append("지지선 근처")
            return True, reasons

        return False, reasons

    def check_volume_surge(self, row: pd.Series) -> Tuple[bool, List[str]]:
        """거래량 급증 체크"""
        signals = row.get('signals', '')
        reasons = []

        if 'VOLUME_EXPLOSION' in signals:
            reasons.append("거래량 폭증")
            return True, reasons
        elif 'VOLUME_SURGE_3X' in signals:
            reasons.append("거래량 3배 이상")
            return True, reasons

        return False, reasons
