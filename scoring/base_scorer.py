"""
스코어러 베이스 클래스

목적:
- 스코어링 버전 간 공통 로직 추상화
- 템플릿 메서드 패턴으로 일관된 구조 제공
- 새 전략 추가 시간 단축

사용법:
    class ScorerV11(BaseScorer):
        VERSION = 'v11'
        NAME = '새로운 전략'

        def _score_groups(self, df: pd.DataFrame) -> Dict:
            # 그룹별 점수 계산
            ...

        def _check_disqualifiers(self, df: pd.DataFrame) -> bool:
            # 과락 조건 검사
            ...
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from .indicators import calculate_base_indicators, IndicatorCache


@dataclass
class ScoreResult:
    """스코어 계산 결과"""
    score: int  # 최종 점수 (0-100)
    version: str  # 스코어링 버전
    signals: List[str] = field(default_factory=list)  # 발생한 신호들
    indicators: Dict[str, Any] = field(default_factory=dict)  # 지표 값들
    groups: Dict[str, int] = field(default_factory=dict)  # 그룹별 점수
    warnings: List[str] = field(default_factory=list)  # 경고 메시지
    disqualified: bool = False  # 과락 여부
    disqualify_reason: Optional[str] = None  # 과락 사유
    computed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """기존 형식과 호환되는 딕셔너리 반환"""
        result = {
            'score': self.score,
            'signals': self.signals,
            'indicators': self.indicators,
            'version': self.version,
        }
        # 그룹별 점수 추가
        result.update(self.groups)
        if self.warnings:
            result['warnings'] = self.warnings
        return result


class BaseScorer(ABC):
    """스코어러 추상 베이스 클래스

    템플릿 메서드 패턴:
    1. calculate_score() - 메인 진입점 (final)
    2. _validate_data() - 데이터 유효성 검사
    3. _check_disqualifiers() - 과락 조건 검사 (추상)
    4. _score_groups() - 그룹별 점수 계산 (추상)
    5. _compute_final_score() - 최종 점수 계산
    """

    # 서브클래스에서 정의
    VERSION: str = 'base'
    NAME: str = 'Base Scorer'
    MIN_DATA_DAYS: int = 60
    MAX_SCORE: int = 100

    # 선택적 캐시
    _indicator_cache: Optional[IndicatorCache] = None

    def __init__(self, use_cache: bool = False, cache_maxsize: int = 500):
        """
        Args:
            use_cache: 지표 캐시 사용 여부
            cache_maxsize: 캐시 최대 크기
        """
        if use_cache:
            self._indicator_cache = IndicatorCache(maxsize=cache_maxsize)

    def calculate_score(
        self,
        df: pd.DataFrame,
        stock_code: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict]:
        """스코어 계산 메인 메서드 (템플릿 메서드)

        Args:
            df: OHLCV DataFrame
            stock_code: 종목코드 (캐시 키로 사용)
            **kwargs: 추가 파라미터 (수급 데이터 등)

        Returns:
            스코어 결과 딕셔너리 (기존 형식 호환)
        """
        # 1. 데이터 유효성 검사
        if not self._validate_data(df):
            return None

        try:
            # 2. 지표 계산 (캐시 또는 직접)
            if self._indicator_cache and stock_code:
                df_ind = self._indicator_cache.get_or_calculate(stock_code, df)
            else:
                df_ind = calculate_base_indicators(df)

            # 3. 과락 조건 검사
            disqualify_result = self._check_disqualifiers(df_ind, **kwargs)
            if disqualify_result:
                return self._disqualified_result(disqualify_result, df_ind)

            # 4. 그룹별 점수 계산
            result = self._score_groups(df_ind, **kwargs)

            # 5. 최종 점수 계산
            result = self._compute_final_score(result)

            # 6. 기본 지표 추가
            result = self._add_base_indicators(result, df_ind)

            return result.to_dict()

        except Exception as e:
            print(f"[{self.VERSION}] 스코어 계산 오류: {e}")
            return None

    def _validate_data(self, df: pd.DataFrame) -> bool:
        """데이터 유효성 검사

        Override 가능: 추가 검증이 필요한 경우
        """
        if df is None:
            return False
        if len(df) < self.MIN_DATA_DAYS:
            return False
        required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
        if not required_cols.issubset(df.columns):
            return False
        return True

    @abstractmethod
    def _check_disqualifiers(
        self,
        df: pd.DataFrame,
        **kwargs
    ) -> Optional[str]:
        """과락 조건 검사

        Returns:
            과락 사유 문자열 (None이면 통과)
        """
        pass

    @abstractmethod
    def _score_groups(
        self,
        df: pd.DataFrame,
        **kwargs
    ) -> ScoreResult:
        """그룹별 점수 계산

        Returns:
            ScoreResult 객체 (score는 아직 미계산 상태)
        """
        pass

    def _compute_final_score(self, result: ScoreResult) -> ScoreResult:
        """최종 점수 계산

        Override 가능: 스케일링 로직 커스터마이즈
        """
        # 그룹 점수 합산
        total = sum(result.groups.values())

        # 0-100 클리핑
        result.score = max(0, min(self.MAX_SCORE, total))

        return result

    def _disqualified_result(
        self,
        reason: str,
        df: pd.DataFrame
    ) -> Dict:
        """과락 결과 생성"""
        result = ScoreResult(
            score=0,
            version=self.VERSION,
            disqualified=True,
            disqualify_reason=reason,
        )

        # 과락 신호 추가
        if 'reverse' in reason.lower():
            result.signals.append('MA_REVERSE_ALIGNED')
        if '역배열' in reason:
            result.signals.append('MA_REVERSE_ALIGNED')

        # 기본 지표 추가
        result = self._add_base_indicators(result, df)

        return result.to_dict()

    def _add_base_indicators(
        self,
        result: ScoreResult,
        df: pd.DataFrame
    ) -> ScoreResult:
        """기본 지표 추가"""
        curr = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else curr

        result.indicators.update({
            'close': curr['Close'],
            'change_pct': ((curr['Close'] - prev['Close']) / prev['Close'] * 100)
            if prev['Close'] > 0 else 0,
            'volume': int(curr['Volume']),
        })

        # 거래대금
        if 'TRADING_VALUE' in df.columns:
            result.indicators['trading_value'] = int(curr['TRADING_VALUE'])
        else:
            result.indicators['trading_value'] = int(curr['Close'] * curr['Volume'])

        result.indicators['trading_value_억'] = (
            result.indicators['trading_value'] / 100_000_000
        )

        return result


class TrendFollowScorer(BaseScorer):
    """추세 추종 스코어러 베이스 (V2, V7 계열)

    특징:
    - 역배열 과락
    - 20일선 기울기 중시
    - RSI 떨어지는 칼날 감점
    """

    def _check_disqualifiers(
        self,
        df: pd.DataFrame,
        **kwargs
    ) -> Optional[str]:
        """역배열 과락"""
        if 'MA_REVERSE_ALIGNED' in df.columns:
            if df.iloc[-1]['MA_REVERSE_ALIGNED']:
                return '역배열 (5일 < 20일 < 60일)'
        else:
            # 수동 계산
            curr = df.iloc[-1]
            if 'SMA_5' in df.columns and 'SMA_20' in df.columns and 'SMA_60' in df.columns:
                if curr['SMA_5'] < curr['SMA_20'] < curr['SMA_60']:
                    return '역배열 (5일 < 20일 < 60일)'

        return None


class ContrarianScorer(BaseScorer):
    """역발상 스코어러 베이스 (V1, V8 계열)

    특징:
    - 과매도 가점
    - 바닥 확인 신호 중시
    - 역배열 감점 (과락 아님)
    """

    def _check_disqualifiers(
        self,
        df: pd.DataFrame,
        **kwargs
    ) -> Optional[str]:
        """역발상 전략은 과락 조건 없음 (역배열도 기회)"""
        return None


class PatternScorer(BaseScorer):
    """패턴 기반 스코어러 베이스 (V4, V5 계열)

    특징:
    - VCP, OBV 다이버전스 등 패턴 감지
    - 세력 축적 신호 중시
    """

    def _check_disqualifiers(
        self,
        df: pd.DataFrame,
        **kwargs
    ) -> Optional[str]:
        """극단적 역배열만 과락"""
        # 5일선이 60일선보다 5% 이상 아래면 과락
        curr = df.iloc[-1]
        if 'SMA_5' in df.columns and 'SMA_60' in df.columns:
            sma5, sma60 = curr['SMA_5'], curr['SMA_60']
            if pd.notna(sma5) and pd.notna(sma60) and sma60 > 0:
                gap = (sma5 - sma60) / sma60
                if gap < -0.05:
                    return f'극단적 역배열 (5일선 {gap*100:.1f}% 아래)'

        return None


# 유틸리티 함수

def create_scorer(version: str, **kwargs) -> Optional[BaseScorer]:
    """버전에 맞는 스코어러 인스턴스 생성

    Args:
        version: 스코어링 버전 ('v2', 'v4', etc.)
        **kwargs: 스코어러 초기화 파라미터

    Returns:
        BaseScorer 서브클래스 인스턴스
    """
    # 추후 각 버전별 스코어러 클래스 등록
    scorers = {
        # 'v2': ScorerV2,
        # 'v4': ScorerV4,
    }

    scorer_cls = scorers.get(version.lower())
    if scorer_cls:
        return scorer_cls(**kwargs)

    return None


def batch_score(
    stocks: Dict[str, pd.DataFrame],
    scorer: BaseScorer,
    parallel: bool = False,
    max_workers: int = 4
) -> Dict[str, Dict]:
    """배치 스코어 계산

    Args:
        stocks: {종목코드: DataFrame} 딕셔너리
        scorer: 스코어러 인스턴스
        parallel: 병렬 처리 여부
        max_workers: 병렬 워커 수

    Returns:
        {종목코드: 스코어 결과} 딕셔너리
    """
    results = {}

    if parallel:
        from concurrent.futures import ThreadPoolExecutor

        def score_one(item):
            code, df = item
            return code, scorer.calculate_score(df, stock_code=code)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for code, result in executor.map(score_one, stocks.items()):
                if result:
                    results[code] = result
    else:
        for code, df in stocks.items():
            result = scorer.calculate_score(df, stock_code=code)
            if result:
                results[code] = result

    return results
