"""
자동매매 전략 모듈

네 가지 버전의 전략 구현:
- V1: 종합 기술적 분석 (analyze_full) - 과매도 가점, 역발상 투자
- V2: 추세 추종 강화 (analyze_trend_following_strict) - 현재 운영 중
- V3: 간소화 버전 - 래치 전략 강화
- V4: Hybrid Sniper - VCP, OBV 다이버전스, ATR 손절 등 고급 기능
"""

from .strategy_v1 import V1Strategy
from .strategy_v2 import V2Strategy
from .strategy_v3 import V3Strategy
from .strategy_v4 import V4Strategy

# 버전별 전략 매핑
STRATEGIES = {
    'v1': V1Strategy,
    'v2': V2Strategy,
    'v3': V3Strategy,
    'v4': V4Strategy,
}

# 기본 전략 (현재 운영 중)
DEFAULT_STRATEGY = 'v2'


def get_strategy(version: str = None):
    """
    전략 인스턴스 반환

    Args:
        version: 'v1', 'v2', 'v3', 'v4' 중 하나
                 None이면 기본 전략(v2) 반환

    Returns:
        Strategy 인스턴스

    Example:
        >>> strategy = get_strategy('v1')
        >>> result = strategy.analyze(df)
    """
    if version is None:
        version = DEFAULT_STRATEGY

    version = version.lower()

    if version not in STRATEGIES:
        raise ValueError(f"Unknown strategy version: {version}. Available: {list(STRATEGIES.keys())}")

    return STRATEGIES[version]()


def list_strategies():
    """
    사용 가능한 전략 목록 출력
    """
    print("\n=== 자동매매 전략 버전 ===\n")

    for version, strategy_class in STRATEGIES.items():
        is_default = " (현재 운영)" if version == DEFAULT_STRATEGY else ""
        print(f"[{version.upper()}]{is_default}")
        print(f"  이름: {strategy_class.NAME}")
        print(f"  설명: {strategy_class.DESCRIPTION}")
        print(f"  매수 기준: {strategy_class.BUY_THRESHOLD}점 이상")
        print()


def compare_strategies(df):
    """
    모든 전략으로 동일 종목 분석 비교

    Args:
        df: OHLCV 데이터프레임

    Returns:
        dict: 버전별 분석 결과
    """
    results = {}

    for version, strategy_class in STRATEGIES.items():
        strategy = strategy_class()
        result = strategy.analyze(df)

        if result:
            results[version] = {
                'score': result['score'],
                'action': result['action'],
                'signals': result['signals'][:5],  # 상위 5개만
            }
        else:
            results[version] = {'score': 0, 'action': 'ERROR', 'signals': []}

    return results


__all__ = [
    'V1Strategy',
    'V2Strategy',
    'V3Strategy',
    'V4Strategy',
    'get_strategy',
    'list_strategies',
    'compare_strategies',
    'STRATEGIES',
    'DEFAULT_STRATEGY',
]
