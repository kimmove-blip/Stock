"""
점수 계산 모듈

버전별 점수 계산 로직:
- V1: 종합 기술적 분석 (과매도 가점, 역발상)
- V2: 추세 추종 강화 (역배열 과락, 20일선 기울기)
- V3: 사일런트 바이어 (OBV 다이버전스, 매집봉, Spring, VCP)
- V3.5: 사일런트 바이어 발전형 (와이코프 Phase, 위치 필터, 숏커버링, 공시 확증)
- V4: Hybrid Sniper (VCP, OBV 다이버전스, 수급)
- V5: 장대양봉 (Long Bullish Candle) - 눌림목, BB수축, 이평선 밀집, OBV 다이버전스
- V6: Swing Predictor (스윙 예측기) - 2~5일 홀딩, 목표가/손절가 청산
- V7: Trend Momentum (추세 모멘텀) - 추세필터, 3일홀딩, 트레일링스탑
- V8: Contrarian Bounce (역발상 반등) - 약세종목 모멘텀반전, 바닥확인
- V9: Gap-Up Predictor (ML 기반) - 오버나잇 갭상승 확률 예측
- V10: Leader-Follower (대장주-종속주) - 상관관계 기반 캐치업 전략

공통 모듈:
- indicators: 기술적 지표 일괄 계산 (LRU 캐시)
- base_scorer: 스코어러 추상 베이스 클래스
"""

from .scoring_v1 import calculate_score_v1
from .scoring_v2 import calculate_score_v2
from .scoring_v3 import calculate_score_v3
from .scoring_v3_5 import calculate_score_v3_5, calculate_score_v3_5_with_investor
from .scoring_v4 import calculate_score_v4, calculate_score_v4_with_investor
from .scoring_v5 import calculate_score_v5
from .scoring_v6 import calculate_score_v6, calculate_score_v6_with_investor
from .score_v7_trend_momentum import calculate_score_v7
from .score_v8_contrarian_bounce import calculate_score_v8, calculate_score_v8_with_investor
from .score_v10_leader_follower import (
    calculate_score_v10,
    calculate_score_v10_with_market_data,
    get_follower_opportunities,
    get_reference_info,
    load_reference,
)

# 공통 모듈
from .indicators import (
    calculate_base_indicators,
    IndicatorCache,
    check_ma_status,
    check_rsi_status,
    check_volume_status,
    detect_obv_divergence,
    detect_vcp_pattern,
    get_global_cache,
)
from .base_scorer import (
    BaseScorer,
    ScoreResult,
    TrendFollowScorer,
    ContrarianScorer,
    PatternScorer,
    batch_score,
)

# 버전별 함수 매핑
SCORING_FUNCTIONS = {
    'v1': calculate_score_v1,
    'v2': calculate_score_v2,
    'v3': calculate_score_v3,
    'v3.5': calculate_score_v3_5,
    'v4': calculate_score_v4,
    'v5': calculate_score_v5,
    'v6': calculate_score_v6,
    'v7': calculate_score_v7,
    'v8': calculate_score_v8,
    'v10': calculate_score_v10,
}

# 기본 버전 (현재 운영 중)
DEFAULT_VERSION = 'v2'


def calculate_score(df, version: str = None):
    """
    점수 계산 함수

    Args:
        df: OHLCV 데이터프레임
        version: 'v1', 'v2', 'v3', 'v3.5', 'v4' 중 하나 (기본값: v2)

    Returns:
        점수 계산 결과 딕셔너리

    Example:
        >>> from scoring import calculate_score
        >>> result = calculate_score(df, 'v1')
        >>> print(result['score'])
    """
    if version is None:
        version = DEFAULT_VERSION

    version = version.lower()

    if version not in SCORING_FUNCTIONS:
        raise ValueError(f"Unknown version: {version}. Available: {list(SCORING_FUNCTIONS.keys())}")

    return SCORING_FUNCTIONS[version](df)


def compare_scores(df):
    """
    모든 버전으로 점수 계산 비교

    Args:
        df: OHLCV 데이터프레임

    Returns:
        dict: 버전별 점수 결과
    """
    results = {}

    for version, func in SCORING_FUNCTIONS.items():
        result = func(df)
        if result:
            results[version] = {
                'score': result['score'],
                'signals': result['signals'][:5],
            }
        else:
            results[version] = {'score': 0, 'signals': []}

    return results


def list_versions():
    """사용 가능한 버전 목록 출력"""
    print("\n=== 점수 계산 버전 ===\n")

    descriptions = {
        'v1': '종합 기술적 분석 (과매도 가점, 역발상)',
        'v2': '추세 추종 강화 (역배열 과락, 20일선 기울기) [현재 운영]',
        'v3': '사일런트 바이어 (OBV 다이버전스, 매집봉, Spring, VCP)',
        'v3.5': '사일런트 바이어 발전형 (와이코프 Phase, 위치 필터, 숏커버링, 공시 확증)',
        'v4': 'Hybrid Sniper (VCP, OBV 다이버전스, 수급)',
        'v5': '장대양봉 (Long Bullish Candle) - 눌림목, BB수축, 이평선 밀집',
        'v6': 'Swing Predictor (스윙 예측기) - 2~5일 홀딩, 목표가/손절가 청산',
        'v7': 'Trend Momentum (추세 모멘텀) - 추세필터, 3일홀딩, 트레일링스탑',
        'v8': 'Contrarian Bounce (역발상 반등) - 약세종목 모멘텀반전, 바닥확인',
        'v10': 'Leader-Follower (대장주-종속주) - 상관관계 기반 캐치업 전략',
    }

    for version in SCORING_FUNCTIONS.keys():
        is_default = " ← 기본값" if version == DEFAULT_VERSION else ""
        print(f"[{version.upper()}]{is_default}")
        print(f"  {descriptions.get(version, '')}")
        print()


__all__ = [
    # 버전별 스코어링 함수
    'calculate_score_v1',
    'calculate_score_v2',
    'calculate_score_v3',
    'calculate_score_v3_5',
    'calculate_score_v3_5_with_investor',
    'calculate_score_v4',
    'calculate_score_v4_with_investor',
    'calculate_score_v5',
    'calculate_score_v6',
    'calculate_score_v6_with_investor',
    'calculate_score_v7',
    'calculate_score_v8',
    'calculate_score_v8_with_investor',
    'calculate_score_v10',
    'calculate_score_v10_with_market_data',
    'get_follower_opportunities',
    'get_reference_info',
    'load_reference',
    # 통합 함수
    'calculate_score',
    'compare_scores',
    'list_versions',
    'SCORING_FUNCTIONS',
    'DEFAULT_VERSION',
    # 공통 지표 모듈
    'calculate_base_indicators',
    'IndicatorCache',
    'check_ma_status',
    'check_rsi_status',
    'check_volume_status',
    'detect_obv_divergence',
    'detect_vcp_pattern',
    'get_global_cache',
    # 베이스 클래스
    'BaseScorer',
    'ScoreResult',
    'TrendFollowScorer',
    'ContrarianScorer',
    'PatternScorer',
    'batch_score',
]
