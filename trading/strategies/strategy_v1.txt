"""
V1 Strategy - 종합 기술적 분석 (analyze_full)

어제까지 운영되던 기존 전략

핵심 철학:
- 모든 기술 지표를 종합하여 점수 산출
- 과매도 = 매수 기회 (역발상 투자)
- 역배열도 감점일 뿐, 과락 없음

점수 체계:
- 17개 이상의 기술 지표 종합
- 과매도(RSI<30) → +15점
- 역배열 → -10점 (과락 아님)
- 스케일링: 0-60→0-54, 60-100→54-80, 100+→80-100

매수 기준: 70점 이상
매도 기준: 50점 이하
"""

import pandas as pd
import pandas_ta as ta
from datetime import datetime
from typing import Dict, Optional, List
import sys
import os

# 상위 디렉토리의 technical_analyst 참조
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from technical_analyst import TechnicalAnalyst


class V1Strategy:
    """V1 전략 - 종합 기술적 분석 (analyze_full 래퍼)"""

    VERSION = "v1"
    NAME = "V1 종합 분석"
    DESCRIPTION = "모든 지표 종합 + 과매도 가점 + 역발상 투자"

    # 매매 기준
    BUY_THRESHOLD = 70          # 매수 기준 점수
    BUY_THRESHOLD_STRONG = 80   # 강력 매수 기준
    SELL_THRESHOLD = 50         # 매도 기준 점수
    STOP_LOSS_PCT = -10.0       # 손절 기준 (%)

    def __init__(self):
        self.tech_analyst = TechnicalAnalyst()

    def analyze(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        종목 분석 실행

        Args:
            df: OHLCV 데이터프레임 (최소 60일)

        Returns:
            분석 결과 딕셔너리
        """
        if df is None or len(df) < 60:
            return None

        # analyze_full 호출
        result = self.tech_analyst.analyze_full(df)

        if result is None:
            return None

        # 매매 판단 추가
        score = result['score']
        signals = result['signals']

        action = 'HOLD'
        reason = ''

        if score >= self.BUY_THRESHOLD_STRONG:
            action = 'STRONG_BUY'
            reason = f'강력 매수 ({score}점 >= {self.BUY_THRESHOLD_STRONG}점)'
        elif score >= self.BUY_THRESHOLD:
            action = 'BUY'
            reason = f'매수 ({score}점 >= {self.BUY_THRESHOLD}점)'
        elif score <= self.SELL_THRESHOLD:
            action = 'SELL'
            reason = f'매도 ({score}점 <= {self.SELL_THRESHOLD}점)'

        result['action'] = action
        result['reason'] = reason
        result['strategy_version'] = self.VERSION

        return result

    def should_buy(self, df: pd.DataFrame) -> tuple:
        """
        매수 여부 판단

        Returns:
            (should_buy: bool, reason: str, score: int)
        """
        result = self.analyze(df)

        if result is None:
            return False, "분석 실패", 0

        score = result['score']

        if result['action'] in ['STRONG_BUY', 'BUY']:
            return True, result['reason'], score

        return False, f"조건 미충족 ({score}점)", score

    def should_sell(self, df: pd.DataFrame, entry_price: float) -> tuple:
        """
        매도 여부 판단

        Args:
            df: 현재 가격 데이터
            entry_price: 매수가

        Returns:
            (should_sell: bool, reason: str, sell_type: str)
        """
        result = self.analyze(df)

        if result is None:
            return False, "분석 실패", None

        curr_price = df.iloc[-1]['Close']
        pnl_pct = ((curr_price - entry_price) / entry_price) * 100

        # 1. 손절 체크
        if pnl_pct <= self.STOP_LOSS_PCT:
            return True, f"손절 ({pnl_pct:.1f}%)", 'STOP_LOSS'

        # 2. 점수 하락 체크
        score = result['score']
        if score <= self.SELL_THRESHOLD:
            return True, f"점수 하락 ({score}점)", 'SCORE_DROP'

        return False, "보유 유지", None

    def get_score_breakdown(self, df: pd.DataFrame) -> Dict:
        """점수 세부 내역 조회"""
        result = self.analyze(df)

        if result is None:
            return {}

        indicators = result.get('indicators', {})
        signals = result.get('signals', [])
        patterns = result.get('patterns', [])

        # 신호 분류
        bullish = [s for s in signals if not s.startswith(('DEAD_', 'RSI_OVERBOUGHT', 'BB_UPPER', 'CMF_STRONG_OUTFLOW'))]
        bearish = [s for s in signals if s.startswith(('DEAD_', 'RSI_OVERBOUGHT', 'BB_UPPER', 'CMF_STRONG_OUTFLOW'))]

        return {
            'total_score': result['score'],
            'bullish_signals': len(bullish),
            'bearish_signals': len(bearish),
            'patterns': patterns,
            'details': {
                'rsi': indicators.get('rsi', 0),
                'macd': indicators.get('macd', 0),
                'volume_ratio': indicators.get('volume_ratio', 0),
                'adx': indicators.get('adx', 0),
                'cmf': indicators.get('cmf', 0),
                'stoch_k': indicators.get('stoch_k', 0),
            },
            'all_signals': signals
        }


# 테스트용
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    strategy = V1Strategy()

    # 삼성전자 테스트
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    df = fdr.DataReader('005930', start_date)

    result = strategy.analyze(df)

    if result:
        print(f"=== {strategy.NAME} ===")
        print(f"점수: {result['score']}")
        print(f"판단: {result['action']}")
        print(f"이유: {result['reason']}")
        print(f"신호: {result['signals'][:5]}...")
        print(f"패턴: {result.get('patterns', [])}")

        breakdown = strategy.get_score_breakdown(df)
        print(f"\n신호 요약:")
        print(f"  상승 신호: {breakdown['bullish_signals']}개")
        print(f"  하락 신호: {breakdown['bearish_signals']}개")
