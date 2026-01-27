"""
V2 추세추종 전략 (장중 자동매매용)
- 이평선 정배열 + MA20 기울기 기반
- 현재 운영 중인 기본 전략
"""

import pandas as pd
from typing import Dict, List
from .base_strategy import BaseStrategy, TrendFollowingMixin


class StrategyV2Trend(BaseStrategy, TrendFollowingMixin):
    """V2 추세추종 전략"""

    NAME = "V2 추세추종"
    DESCRIPTION = "이평선 정배열 + MA20 기울기 기반 추세추종"
    SCORE_COLUMN = "v2"
    VERSION = "2.0"

    DEFAULT_CONFIG = {
        'score_threshold': 75,
        'max_positions': 5,
        'min_amount': 5_000_000_000,  # 50억
        'max_change': 20.0,
        'required_signals': ['MA_ALIGNED'],
        'excluded_signals': ['RSI_OVERBOUGHT'],
        'exit_rules': {
            'target_atr_mult': 1.5,
            'stop_atr_mult': 0.8,
            'time_stop_days': 3,
            'trailing_start_atr': 0.5
        }
    }

    def filter_candidates(self, df: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """
        V2 전략 후보 필터링

        Args:
            df: 전체 스코어 DataFrame
            context: 시장 컨텍스트

        Returns:
            필터링된 DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        result = df.copy()

        # 1. 스코어 필터
        if self.SCORE_COLUMN in result.columns:
            result = result[result[self.SCORE_COLUMN] >= self.score_threshold]

        # 2. 거래대금 필터
        min_amount = self.config.get('min_amount', 5_000_000_000)
        if 'prev_amount' in result.columns:
            result = result[result['prev_amount'] >= min_amount]

        # 3. 등락률 필터 (상한가 제외)
        max_change = self.config.get('max_change', 20.0)
        if 'change_pct' in result.columns:
            result = result[result['change_pct'] <= max_change]
            result = result[result['change_pct'] >= -10.0]  # 급락 종목 제외

        # 4. 시그널 필터
        if 'signals' in result.columns:
            required = self.config.get('required_signals', ['MA_ALIGNED'])
            excluded = self.config.get('excluded_signals', ['RSI_OVERBOUGHT'])

            for signal in required:
                result = result[result['signals'].str.contains(signal, na=False)]

            for signal in excluded:
                result = result[~result['signals'].str.contains(signal, na=False)]

        # 5. V2 점수 순 정렬
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

        # 1. 이평선 정배열 체크
        aligned, align_reasons = self.check_trend_alignment(row)
        if aligned:
            confidence += 0.15
            reasons.extend(align_reasons)

        # 2. MACD 상승 체크
        macd_bull, macd_reasons = self.check_macd_bullish(row)
        if macd_bull:
            confidence += 0.1
            reasons.extend(macd_reasons)

        # 3. MA20 기울기 체크
        ma20_steep, ma20_reasons = self.check_ma20_slope(row)
        if ma20_steep:
            confidence += 0.15
            reasons.extend(ma20_reasons)

        # 4. RSI 적정 구간 (과열 아님)
        if 'RSI_SWEET_SPOT' in signals:
            confidence += 0.1
            reasons.append("RSI 적정 구간")
        elif 'RSI_POWER_BULL' in signals:
            confidence += 0.05
            reasons.append("RSI 강세")

        # 5. 60일 고점 근처
        if 'BREAKOUT_60D_HIGH' in signals:
            confidence += 0.1
            reasons.append("60일 신고가 돌파")
        elif 'NEAR_60D_HIGH' in signals:
            confidence += 0.05
            reasons.append("60일 고점 근처")

        # 6. 거래량 급증
        if 'VOLUME_EXPLOSION' in signals:
            confidence += 0.1
            reasons.append("거래량 폭증")
        elif 'VOLUME_SURGE_3X' in signals:
            confidence += 0.05
            reasons.append("거래량 3배")

        # 7. 스코어 기반 조정
        if score >= 80:
            confidence += 0.1
        elif score >= 70:
            confidence += 0.05

        # 신뢰도 상한 제한
        confidence = min(confidence, 1.0)

        # 매수 결정
        signal = 'SKIP'
        if score >= self.score_threshold and aligned and confidence >= 0.6:
            signal = 'BUY'
        elif score >= self.score_threshold - 5 and aligned:
            signal = 'HOLD'  # 관심 종목

        return {
            'signal': signal,
            'score': int(score),
            'confidence': round(confidence, 2),
            'reasons': reasons
        }

    def get_exit_params(self, entry_price: int, atr: float = None) -> Dict:
        """V2 전용 청산 파라미터"""
        params = super().get_exit_params(entry_price, atr)

        # V2는 추세 추종이므로 트레일링 스탑 활용
        params['use_trailing'] = True
        params['trailing_pct'] = 0.03  # 3% 트레일링

        return params


class StrategyV2TrendConservative(StrategyV2Trend):
    """V2 추세추종 보수적 버전"""

    NAME = "V2 추세추종 (보수)"
    DESCRIPTION = "높은 스코어 임계값과 빠른 손절"
    VERSION = "2.0-conservative"

    DEFAULT_CONFIG = {
        'score_threshold': 80,
        'max_positions': 3,
        'min_amount': 10_000_000_000,  # 100억
        'max_change': 15.0,
        'required_signals': ['MA_ALIGNED', 'MACD_BULL'],
        'excluded_signals': ['RSI_OVERBOUGHT', 'RSI_POWER_BULL'],
        'exit_rules': {
            'target_atr_mult': 1.2,
            'stop_atr_mult': 0.5,  # 빠른 손절
            'time_stop_days': 2,
            'trailing_start_atr': 0.3
        }
    }


class StrategyV2TrendAggressive(StrategyV2Trend):
    """V2 추세추종 공격적 버전"""

    NAME = "V2 추세추종 (공격)"
    DESCRIPTION = "낮은 스코어 임계값과 넓은 손절"
    VERSION = "2.0-aggressive"

    DEFAULT_CONFIG = {
        'score_threshold': 65,
        'max_positions': 7,
        'min_amount': 3_000_000_000,  # 30억
        'max_change': 25.0,
        'required_signals': ['MA_ALIGNED'],
        'excluded_signals': [],
        'exit_rules': {
            'target_atr_mult': 2.0,
            'stop_atr_mult': 1.0,
            'time_stop_days': 5,
            'trailing_start_atr': 0.7
        }
    }


if __name__ == "__main__":
    # 테스트
    import sys
    sys.path.insert(0, '/home/kimhc/Stock')

    from trading.intraday.score_monitor import ScoreMonitor

    monitor = ScoreMonitor()
    df = monitor.get_latest_scores()

    if df is not None:
        strategy = StrategyV2Trend()

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
