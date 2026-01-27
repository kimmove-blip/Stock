"""
V3 Strategy (간소화 버전)

점수 체계 (100점 만점):
- 과락: 역배열 → 0점 (매수 금지)
- 추세 (30점): 정배열 +5, 20일선 기울기 3%+ → +15, 1.5%+ → +10
- 수급 (35점): 거래량 5배+ → +20, 3배+ → +12, 거래대금 500억+ → +15
- 모멘텀 (35점): RSI 60~75 → +15, 60일 신고가 돌파 → +15

매수 기준: 75점 이상
매도 기준: 래치 전략 - 20일선 이탈 시에만 매도
손절 기준: -6%
"""

import pandas as pd
import pandas_ta as ta
from datetime import datetime
from typing import Dict, Optional, List


class V3Strategy:
    """V3 전략 - 간소화된 점수 체계"""

    VERSION = "v3"
    NAME = "V3 (간소화 버전)"
    DESCRIPTION = "정배열 + 기울기 + 거래대금 + RSI + 신고가"

    # 매매 기준
    BUY_THRESHOLD = 75      # 매수 기준 점수
    STOP_LOSS_PCT = -6.0    # 손절 기준 (%)

    # 래치 전략: 20일선 이탈까지 보유

    def __init__(self):
        pass

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

        result = {
            'score': 0,
            'signals': [],
            'indicators': {},
            'analysis_type': 'v3_simplified'
        }

        try:
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # 기본 정보
            result['indicators']['close'] = curr['Close']
            result['indicators']['change_pct'] = ((curr['Close'] - prev['Close']) / prev['Close']) * 100
            result['indicators']['volume'] = curr['Volume']

            # 거래대금
            trading_value = curr['Close'] * curr['Volume']
            result['indicators']['trading_value'] = trading_value
            result['indicators']['trading_value_억'] = trading_value / 100_000_000

            # ========== 이동평균선 계산 ==========
            df['SMA_5'] = ta.sma(df['Close'], length=5)
            df['SMA_20'] = ta.sma(df['Close'], length=20)
            df['SMA_60'] = ta.sma(df['Close'], length=60)

            curr = df.iloc[-1]

            curr_sma5 = curr['SMA_5']
            curr_sma20 = curr['SMA_20']
            curr_sma60 = curr['SMA_60']

            result['indicators']['sma5'] = curr_sma5
            result['indicators']['sma20'] = curr_sma20
            result['indicators']['sma60'] = curr_sma60

            # === 과락: 역배열 → 0점 ===
            if curr_sma5 < curr_sma20 < curr_sma60:
                result['signals'].append('MA_REVERSE_ALIGNED')
                result['indicators']['ma_status'] = 'reverse_aligned'
                result['score'] = 0
                result['action'] = 'AVOID'
                result['reason'] = '역배열 (매수 금지)'
                result['strategy_version'] = self.VERSION
                return result

            # ========== 1. 추세 그룹 (최대 30점) ==========
            trend_score = 0

            # 정배열: +5점
            if curr_sma5 > curr_sma20 > curr_sma60:
                trend_score += 5
                result['signals'].append('MA_ALIGNED')
                result['indicators']['ma_status'] = 'aligned'
            else:
                result['indicators']['ma_status'] = 'partial'

            # 20일선 기울기
            if len(df) >= 6:
                sma20_5d_ago = df['SMA_20'].iloc[-6]
                if pd.notna(sma20_5d_ago) and sma20_5d_ago > 0:
                    sma20_slope = (curr_sma20 - sma20_5d_ago) / sma20_5d_ago * 100
                    result['indicators']['sma20_slope'] = sma20_slope

                    if sma20_slope >= 3.0:
                        trend_score += 15
                        result['signals'].append('SLOPE_VERY_STEEP')
                    elif sma20_slope >= 1.5:
                        trend_score += 10
                        result['signals'].append('SLOPE_STEEP')
                    elif sma20_slope >= 0.5:
                        trend_score += 5
                        result['signals'].append('SLOPE_RISING')

            trend_score = min(30, trend_score)
            result['indicators']['trend_score'] = trend_score

            # ========== 2. 수급 그룹 (최대 35점) ==========
            supply_score = 0

            # 거래량 분석
            df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
            vol_ma = df.iloc[-1]['VOL_MA20']

            if pd.notna(vol_ma) and vol_ma > 0:
                vol_ratio = curr['Volume'] / vol_ma
                result['indicators']['volume_ratio'] = vol_ratio

                if vol_ratio >= 5.0:
                    supply_score += 20
                    result['signals'].append('VOLUME_5X')
                elif vol_ratio >= 3.0:
                    supply_score += 12
                    result['signals'].append('VOLUME_3X')
                elif vol_ratio >= 2.0:
                    supply_score += 5
                    result['signals'].append('VOLUME_2X')

            # 거래대금
            if trading_value >= 50_000_000_000:  # 500억 이상
                supply_score += 15
                result['signals'].append('VALUE_500B')
            elif trading_value >= 10_000_000_000:  # 100억 이상
                supply_score += 10
                result['signals'].append('VALUE_100B')
            elif trading_value >= 3_000_000_000:  # 30억 이상
                supply_score += 5
                result['signals'].append('VALUE_30B')

            supply_score = min(35, supply_score)
            result['indicators']['supply_score'] = supply_score

            # ========== 3. 모멘텀 그룹 (최대 35점) ==========
            momentum_score = 0

            # RSI
            df['RSI'] = ta.rsi(df['Close'], length=14)
            rsi = df.iloc[-1]['RSI']

            if pd.notna(rsi):
                result['indicators']['rsi'] = rsi

                if 60 <= rsi <= 75:
                    # Sweet Spot
                    momentum_score += 15
                    result['signals'].append('RSI_SWEET_SPOT')
                elif 50 <= rsi < 60:
                    momentum_score += 8
                    result['signals'].append('RSI_HEALTHY')
                elif rsi > 80:
                    # 과열 - 감점 없음 (래치 전략)
                    momentum_score += 5
                    result['signals'].append('RSI_OVERBOUGHT')
                elif rsi < 30:
                    # 급락 중 - 감점
                    momentum_score -= 10
                    result['signals'].append('RSI_FALLING')

            # 60일 신고가 돌파
            high_60d = df['High'].tail(60).max()
            result['indicators']['high_60d'] = high_60d
            result['indicators']['high_60d_pct'] = (curr['Close'] / high_60d - 1) * 100

            if curr['Close'] >= high_60d:
                momentum_score += 15
                result['signals'].append('BREAKOUT_60D')
            elif curr['Close'] >= high_60d * 0.97:
                momentum_score += 10
                result['signals'].append('NEAR_60D_HIGH')
            elif curr['Close'] >= high_60d * 0.95:
                momentum_score += 5
                result['signals'].append('CLOSE_TO_60D')

            momentum_score = min(35, max(-10, momentum_score))
            result['indicators']['momentum_score'] = momentum_score

            # ========== 최종 점수 ==========
            total_score = trend_score + supply_score + momentum_score
            result['score'] = max(0, min(100, total_score))

            # 매매 판단
            if result['score'] >= self.BUY_THRESHOLD:
                result['action'] = 'BUY'
                result['reason'] = f"점수 {result['score']}점 (>= {self.BUY_THRESHOLD}점)"
            else:
                result['action'] = 'HOLD'
                result['reason'] = f"점수 {result['score']}점"

            result['strategy_version'] = self.VERSION
            return result

        except Exception as e:
            print(f"V3 분석 오류: {e}")
            return None

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
        매도 여부 판단 (래치 전략)

        래치 전략: 점수가 떨어져도 20일선만 유지하면 보유

        Args:
            df: 현재 가격 데이터
            entry_price: 매수가

        Returns:
            (should_sell: bool, reason: str, sell_type: str)
        """
        if df is None or len(df) < 20:
            return False, "데이터 부족", None

        curr = df.iloc[-1]
        curr_price = curr['Close']
        pnl_pct = ((curr_price - entry_price) / entry_price) * 100

        # 1. 손절 체크 (-6%)
        if pnl_pct <= self.STOP_LOSS_PCT:
            return True, f"손절 ({pnl_pct:.1f}%)", 'STOP_LOSS'

        # 2. 20일선 이탈 체크 (래치 전략 핵심)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        sma20 = df['SMA_20'].iloc[-1]

        if pd.notna(sma20) and curr_price < sma20:
            return True, f"20일선 이탈 (현재가 {curr_price:,.0f} < 20일선 {sma20:,.0f})", 'MA_BREACH'

        return False, "보유 유지 (래치 전략)", None

    def get_score_breakdown(self, df: pd.DataFrame) -> Dict:
        """점수 세부 내역 조회"""
        result = self.analyze(df)

        if result is None:
            return {}

        indicators = result.get('indicators', {})

        return {
            'trend_score': indicators.get('trend_score', 0),
            'supply_score': indicators.get('supply_score', 0),
            'momentum_score': indicators.get('momentum_score', 0),
            'total_score': result['score'],
            'details': {
                'sma20_slope': indicators.get('sma20_slope', 0),
                'volume_ratio': indicators.get('volume_ratio', 0),
                'trading_value_억': indicators.get('trading_value_억', 0),
                'rsi': indicators.get('rsi', 0),
                'high_60d_pct': indicators.get('high_60d_pct', 0),
            }
        }


# 테스트용
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    strategy = V3Strategy()

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
        print(f"  추세: {breakdown['trend_score']}/30")
        print(f"  수급: {breakdown['supply_score']}/35")
        print(f"  모멘텀: {breakdown['momentum_score']}/35")
