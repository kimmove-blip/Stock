"""
멀티전략 엔진
여러 전략을 순회하며 매수/매도 신호 생성
"""

import sys
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trading.strategies.strategy_v2_trend import StrategyV2Trend
from trading.strategies.strategy_v8_bounce import StrategyV8Bounce
from trading.strategies.strategy_v10_follower import StrategyV10Follower


# 전략 우선순위 (높을수록 우선)
STRATEGY_PRIORITY = {
    'v9_gap': 100,       # V9 갭상승 (별도 스크립트)
    'v2_trend': 80,      # V2 추세추종
    'v8_bounce': 60,     # V8 역발상
    'v10_follower': 40,  # V10 대장주-종속주
}

# 기본 전략 설정 (v1.7 업데이트: 2026-01-27 백테스트 최종 결과)
#
# 최적 전략: V2>=65 + 거래대금 100억+
# - 5개 종목, +7.68% 평균 (KOSPI 대비 +4.95%p)
# - V2>=65가 V2>=55보다 성과 좋음 (+7.25% vs +1.63%)
#
DEFAULT_STRATEGY_CONFIG = {
    'v2_trend': {
        'enabled': True,
        'score_threshold': 65,   # V2>=65
        'max_positions': 10,
        'exit_rules': {
            'target_atr_mult': 1.0,  # 장중 청산용
            'stop_atr_mult': 0.8,    # 장중 청산용
            'time_stop_days': 1      # 당일 청산
        }
    },
    'v8_bounce': {
        'enabled': True,
        'score_threshold': 60,   # 하향 (70→60)
        'max_positions': 3,
        'exit_rules': {
            'target_atr_mult': 1.5,  # 상향 (1.2→1.5)
            'stop_atr_mult': 1.2,    # 하향 (0.6→1.2)
            'time_stop_days': 2
        }
    },
    'v10_follower': {
        'enabled': True,
        'leader_min_change': 3.0,
        'max_positions': 3,
        'exit_rules': {
            'target_catchup_pct': 70,
            'stop_pct': -3.0,
            'target_atr_mult': 1.5,  # 추가
            'stop_atr_mult': 1.0,    # 추가
            'time_stop_days': 3
        }
    }
}


class StrategyEngine:
    """멀티전략 엔진"""

    def __init__(self, config: Dict = None):
        """
        Args:
            config: 전략별 설정 (없으면 기본값 사용)
        """
        self.config = config or DEFAULT_STRATEGY_CONFIG
        self.strategies = {}
        self._init_strategies()

    def _init_strategies(self):
        """전략 인스턴스 초기화"""
        # V2 추세추종
        if self.config.get('v2_trend', {}).get('enabled', True):
            v2_config = self.config.get('v2_trend', {})
            self.strategies['v2_trend'] = StrategyV2Trend(v2_config)

        # V8 역발상
        if self.config.get('v8_bounce', {}).get('enabled', True):
            v8_config = self.config.get('v8_bounce', {})
            self.strategies['v8_bounce'] = StrategyV8Bounce(v8_config)

        # V10 대장주-종속주
        if self.config.get('v10_follower', {}).get('enabled', True):
            v10_config = self.config.get('v10_follower', {})
            self.strategies['v10_follower'] = StrategyV10Follower(v10_config)

    def get_strategy(self, name: str):
        """전략 인스턴스 반환"""
        return self.strategies.get(name)

    def list_strategies(self) -> List[str]:
        """활성화된 전략 목록"""
        return list(self.strategies.keys())

    def evaluate_all(
        self,
        df: pd.DataFrame,
        context: Dict = None,
        exclude_codes: List[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        모든 전략으로 평가

        Args:
            df: 스코어 DataFrame
            context: 시장 컨텍스트
            exclude_codes: 제외할 종목코드 (이미 보유 중인 종목)

        Returns:
            전략별 매수 시그널 매핑
        """
        exclude_codes = exclude_codes or []
        results = {}

        for name, strategy in self.strategies.items():
            signals = strategy.get_entry_signals(df, context)

            # 제외 종목 필터링
            signals = [s for s in signals if s['code'] not in exclude_codes]

            results[name] = signals

        return results

    def get_best_signals(
        self,
        df: pd.DataFrame,
        context: Dict = None,
        exclude_codes: List[str] = None,
        max_total: int = 10
    ) -> List[Dict]:
        """
        전략 간 최적 시그널 선택

        Args:
            df: 스코어 DataFrame
            context: 시장 컨텍스트
            exclude_codes: 제외할 종목코드
            max_total: 최대 시그널 수

        Returns:
            우선순위 정렬된 매수 시그널 리스트
        """
        all_signals = self.evaluate_all(df, context, exclude_codes)

        # 전략별 우선순위와 신뢰도 기반 정렬
        combined = []
        for strategy_name, signals in all_signals.items():
            priority = STRATEGY_PRIORITY.get(strategy_name, 0)

            for sig in signals:
                sig['strategy_name'] = strategy_name
                sig['priority'] = priority
                combined.append(sig)

        # 중복 종목 제거 (우선순위 높은 전략 유지)
        seen_codes = set()
        unique_signals = []

        # 우선순위 -> 신뢰도 -> 스코어 순 정렬
        combined.sort(key=lambda x: (x['priority'], x['confidence'], x['score']), reverse=True)

        for sig in combined:
            if sig['code'] not in seen_codes:
                seen_codes.add(sig['code'])
                unique_signals.append(sig)

        return unique_signals[:max_total]

    def resolve_conflicts(
        self,
        signals: List[Dict]
    ) -> List[Dict]:
        """
        전략 간 충돌 해결

        Args:
            signals: 매수 시그널 리스트

        Returns:
            충돌 해결된 시그널 리스트
        """
        # 동일 종목에 대해 여러 전략 시그널이 있을 경우
        # 우선순위 높은 전략 선택

        code_signals = {}
        for sig in signals:
            code = sig['code']
            if code not in code_signals:
                code_signals[code] = sig
            else:
                # 우선순위 비교
                existing = code_signals[code]
                if sig.get('priority', 0) > existing.get('priority', 0):
                    code_signals[code] = sig

        return list(code_signals.values())

    def check_market_conditions(self, context: Dict = None) -> Dict:
        """
        시장 상황 체크 (모든 전략 공통)

        Args:
            context: 시장 컨텍스트 (지수 등락률 등)

        Returns:
            {'can_trade': bool, 'reason': str, 'strategies_enabled': List}
        """
        if context is None:
            return {
                'can_trade': True,
                'reason': 'OK',
                'strategies_enabled': self.list_strategies()
            }

        kospi_change = context.get('kospi_change', 0)
        kosdaq_change = context.get('kosdaq_change', 0)

        enabled_strategies = []

        # 시장 급락 시
        if kospi_change < -3 or kosdaq_change < -3:
            # V8 역발상만 허용
            if 'v8_bounce' in self.strategies:
                enabled_strategies.append('v8_bounce')
            return {
                'can_trade': len(enabled_strategies) > 0,
                'reason': '시장 급락 - 역발상만 허용',
                'strategies_enabled': enabled_strategies
            }

        # 시장 급등 시
        if kospi_change > 3 or kosdaq_change > 3:
            # V2 추세추종만 허용
            if 'v2_trend' in self.strategies:
                enabled_strategies.append('v2_trend')
            return {
                'can_trade': len(enabled_strategies) > 0,
                'reason': '시장 급등 - 추세추종만 허용',
                'strategies_enabled': enabled_strategies
            }

        # 정상 시장
        return {
            'can_trade': True,
            'reason': 'OK',
            'strategies_enabled': self.list_strategies()
        }

    def get_strategy_summary(self) -> List[Dict]:
        """
        전략 요약 정보

        Returns:
            전략별 설정 요약
        """
        summary = []
        for name, strategy in self.strategies.items():
            summary.append({
                'name': name,
                'display_name': strategy.NAME,
                'version': strategy.VERSION,
                'score_threshold': strategy.score_threshold,
                'max_positions': strategy.max_positions,
                'priority': STRATEGY_PRIORITY.get(name, 0),
                'enabled': True
            })

        # 우선순위 순 정렬
        summary.sort(key=lambda x: x['priority'], reverse=True)
        return summary


class StrategySelector:
    """시장 상황에 따른 전략 자동 선택"""

    def __init__(self, engine: StrategyEngine):
        self.engine = engine

    def select_strategies(
        self,
        market_context: Dict,
        time_context: Dict = None
    ) -> List[str]:
        """
        시장/시간 상황에 따른 전략 선택

        Args:
            market_context: 시장 상황 (지수 등락률, 거래대금 등)
            time_context: 시간 상황 (장 시작/중간/마감 등)

        Returns:
            선택된 전략 이름 리스트
        """
        available = self.engine.list_strategies()

        # 시장 상황 체크
        market_check = self.engine.check_market_conditions(market_context)
        available = [s for s in available if s in market_check['strategies_enabled']]

        # 시간대별 조정
        if time_context:
            hour = time_context.get('hour', 12)

            # 장 초반 (09:00~10:00): 추세추종 우선
            if 9 <= hour < 10:
                if 'v2_trend' in available:
                    return ['v2_trend']

            # 장 마감 전 (14:00~15:30): V9 갭상승 (별도 처리)
            # 여기서는 장중 전략만 반환

            # 점심 시간 (11:30~13:00): 역발상 기회
            if 11 <= hour < 13:
                if 'v8_bounce' in available:
                    available.insert(0, available.pop(available.index('v8_bounce')))

        return available


if __name__ == "__main__":
    # 테스트
    from trading.intraday.score_monitor import ScoreMonitor

    monitor = ScoreMonitor()
    df = monitor.get_latest_scores()

    if df is not None:
        engine = StrategyEngine()

        print("=== 전략 엔진 테스트 ===")
        print(f"활성화된 전략: {engine.list_strategies()}")

        print("\n=== 전략 요약 ===")
        for s in engine.get_strategy_summary():
            print(f"  {s['name']:15s} (우선순위 {s['priority']:3d}): "
                  f"스코어 {s['score_threshold']}+ / 최대 {s['max_positions']}개")

        print("\n=== 전략별 시그널 ===")
        all_signals = engine.evaluate_all(df)
        for strategy_name, signals in all_signals.items():
            print(f"\n[{strategy_name}] {len(signals)}개 시그널:")
            for sig in signals[:3]:
                print(f"  {sig['code']} {sig['name']:12s} "
                      f"신뢰도={sig['confidence']:.2f} 가격={sig.get('price', 0):,}원")

        print("\n=== 최적 시그널 (상위 5개) ===")
        best = engine.get_best_signals(df, max_total=5)
        for sig in best:
            print(f"  [{sig['strategy_name']:12s}] {sig['code']} {sig['name']:12s} "
                  f"우선순위={sig['priority']} 신뢰도={sig['confidence']:.2f}")
