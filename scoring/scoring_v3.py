"""
V3 점수 계산 로직 - 간소화 버전 (래치 전략 강화)

철학: V2를 간소화하고 래치 전략에 최적화
      점수가 떨어져도 20일선만 유지하면 보유

점수 체계 (100점 만점):
- 추세 (30점): 정배열 +5, 20일선 기울기
- 수급 (35점): 거래량, 거래대금
- 모멘텀 (35점): RSI, 60일 신고가

특징:
- V2 대비 지표 간소화
- 매도는 20일선 이탈 시에만 (래치 전략)
- 점수 하락만으로는 매도 안 함

┌──────────────────────────────────┬──────┐
│ 추세 그룹 (30점)                  │      │
├──────────────────────────────────┼──────┤
│ 정배열                            │ +5   │
│ 20일선 기울기 ≥ 3%                │ +15  │
│ 20일선 기울기 ≥ 1.5%              │ +10  │
│ 20일선 기울기 ≥ 0.5%              │ +5   │
├──────────────────────────────────┼──────┤
│ 수급 그룹 (35점)                  │      │
├──────────────────────────────────┼──────┤
│ 거래량 ≥ 5배                      │ +20  │
│ 거래량 ≥ 3배                      │ +12  │
│ 거래량 ≥ 2배                      │ +5   │
│ 거래대금 ≥ 500억                  │ +15  │
│ 거래대금 ≥ 100억                  │ +10  │
│ 거래대금 ≥ 30억                   │ +5   │
├──────────────────────────────────┼──────┤
│ 모멘텀 그룹 (35점)                │      │
├──────────────────────────────────┼──────┤
│ RSI 60~75 (Sweet Spot)           │ +15  │
│ RSI 50~60                        │ +8   │
│ RSI > 80                         │ +5   │
│ RSI < 30                         │ -10  │
│ 60일 신고가 돌파                   │ +15  │
│ 60일 고가 97% 이내                 │ +10  │
│ 60일 고가 95% 이내                 │ +5   │
└──────────────────────────────────┴──────┘
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict, Optional


def calculate_score_v3(df: pd.DataFrame) -> Optional[Dict]:
    """
    V3 점수 계산 (간소화 + 래치 전략)

    Args:
        df: OHLCV 데이터프레임 (최소 60일)

    Returns:
        {
            'score': 최종 점수 (0-100),
            'trend_score': 추세 점수,
            'supply_score': 수급 점수,
            'momentum_score': 모멘텀 점수,
            'signals': 발생한 신호 리스트,
            'indicators': 지표 상세값
        }
    """
    if df is None or len(df) < 60:
        return None

    result = {
        'score': 0,
        'trend_score': 0,
        'supply_score': 0,
        'momentum_score': 0,
        'signals': [],
        'indicators': {},
        'version': 'v3'
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
        result['indicators']['trading_value_억'] = trading_value / 100_000_000

        # ========== 이동평균선 ==========
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
        result['trend_score'] = trend_score

        # ========== 2. 수급 그룹 (최대 35점) ==========
        supply_score = 0

        # 거래량
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
        if trading_value >= 50_000_000_000:
            supply_score += 15
            result['signals'].append('VALUE_500B')
        elif trading_value >= 10_000_000_000:
            supply_score += 10
            result['signals'].append('VALUE_100B')
        elif trading_value >= 3_000_000_000:
            supply_score += 5
            result['signals'].append('VALUE_30B')

        supply_score = min(35, supply_score)
        result['supply_score'] = supply_score

        # ========== 3. 모멘텀 그룹 (최대 35점) ==========
        momentum_score = 0

        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        rsi = df.iloc[-1]['RSI']

        if pd.notna(rsi):
            result['indicators']['rsi'] = rsi

            if 60 <= rsi <= 75:
                momentum_score += 15
                result['signals'].append('RSI_SWEET_SPOT')
            elif 50 <= rsi < 60:
                momentum_score += 8
                result['signals'].append('RSI_HEALTHY')
            elif rsi > 80:
                momentum_score += 5
                result['signals'].append('RSI_OVERBOUGHT')
            elif rsi < 30:
                momentum_score -= 10
                result['signals'].append('RSI_FALLING')

        # 60일 신고가
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
        result['momentum_score'] = momentum_score

        # ========== 최종 점수 ==========
        total_score = trend_score + supply_score + momentum_score
        result['score'] = max(0, min(100, total_score))

        return result

    except Exception as e:
        print(f"V3 점수 계산 오류: {e}")
        return None


# 테스트
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    df = fdr.DataReader('005930', start_date)

    result = calculate_score_v3(df)
    if result:
        print(f"=== V3 점수 계산 결과 ===")
        print(f"최종점수: {result['score']}")
        print(f"  추세: {result['trend_score']}/30")
        print(f"  수급: {result['supply_score']}/35")
        print(f"  모멘텀: {result['momentum_score']}/35")
        print(f"신호: {result['signals']}")
