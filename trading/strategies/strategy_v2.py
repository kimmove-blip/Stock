"""
V2 Strategy - 추세 추종 강화판 (analyze_trend_following_strict)

현재 운영 중인 전략 (2026.01.21~)

핵심 철학:
- 추세를 따라가는 것이 핵심 (Trend Following)
- 과매도 = 떨어지는 칼날 (잡지 않음)
- 역배열 = 과락 (점수 0, 매수 금지)

점수 체계 (100점 만점):
- 추세 (30점): 정배열 +5, 20일선 기울기 최대 +15, MACD +3, Supertrend +7
- 모멘텀 (35점): RSI 60~75 +15, 60일 신고가 돌파 +15
- 거래량 (35점): 거래량 5배 +20, 거래대금 500억 +15

매수 기준: 75점 이상
매도 기준: 40점 이하 또는 20일선 이탈 (래치 전략)
손절 기준: -6%
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


class V2Strategy:
    """현재 구현된 전략 (analyze_trend_following_strict 래퍼)"""

    VERSION = "v2"
    NAME = "V2 추세 추종 (현재 운영)"
    DESCRIPTION = "20일선 기울기 + 거래대금 + 역배열 과락 + 래치 전략"

    # 매매 기준
    BUY_THRESHOLD = 75      # 매수 기준 점수
    SELL_THRESHOLD = 40     # 매도 기준 점수
    STOP_LOSS_PCT = -6.0    # 손절 기준 (%)

    def __init__(self):
        self.tech_analyst = TechnicalAnalyst()

    def analyze(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        종목 분석 실행

        Args:
            df: OHLCV 데이터프레임 (최소 60일)

        Returns:
            분석 결과 딕셔너리:
            {
                'score': 종합 점수 (0-100),
                'signals': 발생한 신호 리스트,
                'indicators': 지표 상세,
                'action': 'BUY' | 'SELL' | 'HOLD',
                'reason': 판단 이유
            }
        """
        if df is None or len(df) < 60:
            return None

        # 기존 분석 함수 호출
        result = self.tech_analyst.analyze_trend_following_strict(df)

        if result is None:
            return None

        # 매매 판단 추가
        score = result['score']
        signals = result['signals']
        indicators = result.get('indicators', {})

        action = 'HOLD'
        reason = ''

        if score >= self.BUY_THRESHOLD:
            action = 'BUY'
            reason = f'점수 {score}점 (>= {self.BUY_THRESHOLD}점)'
        elif score <= self.SELL_THRESHOLD:
            action = 'SELL'
            reason = f'점수 {score}점 (<= {self.SELL_THRESHOLD}점)'
        elif 'MA_REVERSE_ALIGNED' in signals:
            action = 'SELL'
            reason = '이평선 역배열'

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

        if result['action'] == 'BUY':
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
            sell_type: 'STOP_LOSS' | 'SCORE_DROP' | 'MA_BREACH' | None
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

        # 3. 20일선 이탈 체크 (래치 전략)
        sma20 = result['indicators'].get('sma20', None)
        if sma20 is None:
            df['SMA_20'] = ta.sma(df['Close'], length=20)
            sma20 = df['SMA_20'].iloc[-1]

        if curr_price < sma20:
            return True, f"20일선 이탈 (현재가 {curr_price:,.0f} < 20일선 {sma20:,.0f})", 'MA_BREACH'

        return False, "보유 유지", None

    def get_score_breakdown(self, df: pd.DataFrame) -> Dict:
        """
        점수 세부 내역 조회

        Returns:
            {
                'trend_score': 추세 점수,
                'momentum_score': 모멘텀 점수,
                'volume_score': 거래량 점수,
                'total_score': 총점,
                'details': {...}
            }
        """
        result = self.analyze(df)

        if result is None:
            return {}

        indicators = result.get('indicators', {})

        return {
            'trend_score': indicators.get('trend_score', 0),
            'momentum_score': indicators.get('momentum_score', 0),
            'volume_score': indicators.get('volume_score', 0),
            'total_score': result['score'],
            'details': {
                'sma20_slope': indicators.get('sma20_slope', 0),
                'rsi': indicators.get('rsi', 0),
                'volume_ratio': indicators.get('volume_ratio', 0),
                'trading_value_억': indicators.get('trading_value_억', 0),
                'high_60d_pct': indicators.get('high_60d_pct', 0),
            }
        }


# 테스트용
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    strategy = V2Strategy()

    # 삼성전자 테스트
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    df = fdr.DataReader('005930', start_date)

    result = strategy.analyze(df)

    if result:
        print(f"=== {strategy.NAME} ===")
        print(f"점수: {result['score']}")
        print(f"판단: {result['action']}")
        print(f"이유: {result['reason']}")
        print(f"신호: {result['signals']}")

        breakdown = strategy.get_score_breakdown(df)
        print(f"\n점수 세부:")
        print(f"  추세: {breakdown['trend_score']}")
        print(f"  모멘텀: {breakdown['momentum_score']}")
        print(f"  거래량: {breakdown['volume_score']}")
