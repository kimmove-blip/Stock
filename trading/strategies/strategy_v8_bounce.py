"""
V8 역발상반등 전략 (장중 자동매매용)
- 약세 종목의 모멘텀 반전 캐치
- 바닥 확인 후 반등 시점 진입
"""

import pandas as pd
from typing import Dict, List
from .base_strategy import BaseStrategy, ContrarianMixin


class StrategyV8Bounce(BaseStrategy, ContrarianMixin):
    """V8 역발상반등 전략"""

    NAME = "V8 역발상반등"
    DESCRIPTION = "약세 종목 모멘텀 반전, 바닥 확인 후 진입"
    SCORE_COLUMN = "v8"
    VERSION = "1.0"

    DEFAULT_CONFIG = {
        'score_threshold': 70,
        'max_positions': 3,
        'min_amount': 5_000_000_000,  # 50억
        'max_change': 10.0,  # 과도한 상승 제외
        'min_change': -5.0,  # 하락 중인 종목
        'exit_rules': {
            'target_atr_mult': 1.2,  # 빠른 목표 도달
            'stop_atr_mult': 0.6,    # 빠른 손절
            'time_stop_days': 2,     # 짧은 보유
            'trailing_start_atr': 0.4
        }
    }

    def filter_candidates(self, df: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """
        V8 전략 후보 필터링

        Args:
            df: 전체 스코어 DataFrame
            context: 시장 컨텍스트

        Returns:
            필터링된 DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        result = df.copy()

        # 1. V8 스코어 필터
        if self.SCORE_COLUMN in result.columns:
            result = result[result[self.SCORE_COLUMN] >= self.score_threshold]

        # 2. 거래대금 필터
        min_amount = self.config.get('min_amount', 5_000_000_000)
        if 'prev_amount' in result.columns:
            result = result[result['prev_amount'] >= min_amount]

        # 3. 등락률 필터 (하락 또는 소폭 상승)
        max_change = self.config.get('max_change', 10.0)
        min_change = self.config.get('min_change', -5.0)
        if 'change_pct' in result.columns:
            result = result[result['change_pct'] <= max_change]
            result = result[result['change_pct'] >= min_change]

        # 4. V8 점수 순 정렬
        if self.SCORE_COLUMN in result.columns:
            result = result.sort_values(self.SCORE_COLUMN, ascending=False)

        return result

    def evaluate(self, row: pd.Series, context: Dict = None) -> Dict:
        """
        단일 종목 평가

        Args:
            row: 종목 데이터
            context: 시장 컨텍스트

        Returns:
            평가 결과
        """
        score = row.get(self.SCORE_COLUMN, 0)
        signals = row.get('signals', '')
        change_pct = row.get('change_pct', 0)

        reasons = []
        confidence = 0.5

        # 1. 과매도 체크
        oversold, oversold_reasons = self.check_oversold(row)
        if oversold:
            confidence += 0.15
            reasons.extend(oversold_reasons)

        # 2. 지지선 근처 체크
        support, support_reasons = self.check_support_level(row)
        if support:
            confidence += 0.1
            reasons.extend(support_reasons)

        # 3. 거래량 급증 (반등 신호)
        volume, volume_reasons = self.check_volume_surge(row)
        if volume:
            confidence += 0.15
            reasons.extend(volume_reasons)

        # 4. 하락 후 양봉 전환
        if change_pct > 0 and 'IS_BULL' in signals:
            confidence += 0.1
            reasons.append("양봉 전환")

        # 5. 볼린저 밴드 하단
        if 'BB_LOWER' in signals or 'BB_SQUEEZE' in signals:
            confidence += 0.1
            reasons.append("볼린저 하단")

        # 6. 20일 저점 근처에서 반등
        if 'FROM_LOW_20D' in signals or 'NEAR_LOW_20D' in signals:
            confidence += 0.1
            reasons.append("20일 저점 근처")

        # 7. MACD 상향 전환
        if 'MACD_BULL' in signals:
            confidence += 0.05
            reasons.append("MACD 상향")

        # 8. 스코어 기반 조정
        if score >= 80:
            confidence += 0.1
        elif score >= 70:
            confidence += 0.05

        # 신뢰도 상한 제한
        confidence = min(confidence, 1.0)

        # 매수 결정 (V8은 신뢰도가 중요)
        signal = 'SKIP'
        if score >= self.score_threshold and confidence >= 0.65:
            signal = 'BUY'
        elif score >= self.score_threshold - 5 and confidence >= 0.55:
            signal = 'HOLD'

        return {
            'signal': signal,
            'score': int(score),
            'confidence': round(confidence, 2),
            'reasons': reasons
        }

    def check_bounce_confirmation(self, row: pd.Series) -> bool:
        """
        반등 확인 (V8 전용)

        Args:
            row: 종목 데이터

        Returns:
            반등 확인 여부
        """
        signals = row.get('signals', '')
        change_pct = row.get('change_pct', 0)

        # 하락 후 양전환 + 거래량 증가
        has_volume = 'VOLUME_SURGE' in signals or 'VOLUME_EXPLOSION' in signals
        is_recovering = change_pct > -1.0  # 하락폭 축소 또는 양전환

        return has_volume and is_recovering

    def get_exit_params(self, entry_price: int, atr: float = None) -> Dict:
        """V8 전용 청산 파라미터"""
        params = super().get_exit_params(entry_price, atr)

        # V8은 빠른 청산 (반등 실패 시 손절)
        params['use_trailing'] = False  # 트레일링 스탑 미사용
        params['quick_exit'] = True

        # 반등 실패 판단 기준
        params['bounce_fail_threshold'] = -2.0  # -2% 이하면 반등 실패

        return params


class StrategyV8BounceStrict(StrategyV8Bounce):
    """V8 역발상반등 엄격 버전"""

    NAME = "V8 역발상반등 (엄격)"
    DESCRIPTION = "더 높은 스코어와 엄격한 조건"
    VERSION = "1.0-strict"

    DEFAULT_CONFIG = {
        'score_threshold': 80,
        'max_positions': 2,
        'min_amount': 10_000_000_000,  # 100억
        'max_change': 5.0,
        'min_change': -3.0,
        'exit_rules': {
            'target_atr_mult': 1.0,
            'stop_atr_mult': 0.4,  # 매우 빠른 손절
            'time_stop_days': 1,   # 당일 또는 익일 청산
            'trailing_start_atr': 0.3
        }
    }

    def evaluate(self, row: pd.Series, context: Dict = None) -> Dict:
        """엄격한 평가"""
        result = super().evaluate(row, context)

        # 반등 확인 필수
        if result['signal'] == 'BUY' and not self.check_bounce_confirmation(row):
            result['signal'] = 'HOLD'
            result['reasons'].append("반등 미확인")

        return result


if __name__ == "__main__":
    # 테스트
    import sys
    sys.path.insert(0, '/home/kimhc/Stock')

    from trading.intraday.score_monitor import ScoreMonitor

    monitor = ScoreMonitor()
    df = monitor.get_latest_scores()

    if df is not None:
        strategy = StrategyV8Bounce()

        print(f"=== {strategy.NAME} 테스트 ===")
        print(f"스코어 임계값: {strategy.score_threshold}")
        print(f"최대 포지션: {strategy.max_positions}")

        signals = strategy.get_entry_signals(df)

        print(f"\n매수 시그널 ({len(signals)}개):")
        for sig in signals[:5]:
            print(f"  {sig['code']} {sig['name']:12s} "
                  f"점수={sig['score']:3d} 신뢰도={sig['confidence']:.2f} "
                  f"가격={sig['price']:,}원")
            print(f"    사유: {', '.join(sig['reasons'][:3])}")
