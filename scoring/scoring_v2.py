"""
V2 점수 계산 로직 - 추세 추종 강화판

철학: 추세를 따라가는 것이 핵심, 과매도 = 떨어지는 칼날 (역배열 = 과락)

점수 체계 (100점 만점, 스케일링 없음):
- 추세 (30점): 정배열 +5, 20일선 기울기 최대 +15, MACD +3, Supertrend +7
- 모멘텀 (35점): RSI 60~75 +15, 60일 신고가 돌파 +15
- 수급 (35점): 거래량 5배 +20, 회전율(거래대금/시총) 5%+ +15

핵심 변경 (vs V1):
- 과매도(RSI<30) → 감점 (떨어지는 칼날)
- 역배열 → 0점 반환 (과락)
- 20일선 기울기 → 핵심 지표
- 거래대금 필터 → 잡주 필터링
- 60일 신고가 → 가산점

┌──────────────────────────────────┬──────┐
│ 추세 그룹 (30점)                  │      │
├──────────────────────────────────┼──────┤
│ 정배열                            │ +5   │
│ 20일선 기울기 ≥ 3%                │ +15  │
│ 20일선 기울기 ≥ 1.5%              │ +10  │
│ 20일선 기울기 ≥ 0.5%              │ +3   │
│ MACD > 0                         │ +3   │
│ Supertrend 매수 전환              │ +7   │
├──────────────────────────────────┼──────┤
│ 모멘텀 그룹 (35점)                │      │
├──────────────────────────────────┼──────┤
│ RSI 60~75 (Sweet Spot)           │ +15  │
│ RSI 50~60                        │ +5   │
│ RSI > 80 (상승 중)                │ +10  │
│ RSI > 80 (꺾임)                   │ -5   │
│ RSI < 30 (떨어지는 칼날)           │ -10  │
│ 60일 신고가 돌파                   │ +15  │
│ 60일 고가 97% 이내                 │ +7   │
├──────────────────────────────────┼──────┤
│ 수급 그룹 (35점)                  │      │
├──────────────────────────────────┼──────┤
│ 거래량 ≥ 5배                      │ +20  │
│ 거래량 ≥ 3배                      │ +12  │
│ 거래량 ≥ 2배                      │ +5   │
│ 회전율 ≥ 5% (거래대금/시총)        │ +15  │
│ 회전율 ≥ 2%                       │ +10  │
│ 회전율 ≥ 1%                       │ +3   │
│ 회전율 < 0.2%                     │ -5   │
└──────────────────────────────────┴──────┘
"""

import pandas as pd
import pandas_ta as ta
from datetime import datetime
from typing import Dict, Optional


def calculate_projected_volume(curr_vol: int) -> int:
    """장중 예상 거래량 계산 (시간 가중치 적용)"""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if now < market_open or now >= market_close:
        return curr_vol

    total_minutes = 390  # 6시간 30분
    elapsed_minutes = max(1, (now - market_open).total_seconds() / 60)

    if elapsed_minutes < 60:
        projection_factor = (total_minutes / elapsed_minutes) * 0.7
    else:
        projection_factor = total_minutes / elapsed_minutes

    return int(curr_vol * projection_factor)


def calculate_score_v2(df: pd.DataFrame, market_cap: float = None, prev_trading_value: float = None) -> Optional[Dict]:
    """
    V2 점수 계산 (추세 추종 강화판)

    Args:
        df: OHLCV 데이터프레임 (최소 60일)
        market_cap: 시가총액 (원). 회전율 계산에 사용. None이면 거래대금 기반 점수 사용
        prev_trading_value: 전일 거래대금 (원). 장 초반에 사용

    Returns:
        {
            'score': 최종 점수 (0-100),
            'trend_score': 추세 점수,
            'momentum_score': 모멘텀 점수,
            'volume_score': 수급 점수,
            'signals': 발생한 신호 리스트,
            'indicators': 지표 상세값
        }
    """
    if df is None or len(df) < 60:
        return None

    result = {
        'score': 0,
        'trend_score': 0,
        'momentum_score': 0,
        'volume_score': 0,
        'signals': [],
        'indicators': {},
        'version': 'v2'
    }

    try:
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 기본 정보
        result['indicators']['close'] = curr['Close']
        result['indicators']['change_pct'] = ((curr['Close'] - prev['Close']) / prev['Close']) * 100
        result['indicators']['volume'] = curr['Volume']

        # 거래대금 (장 초반에는 예상 거래대금 또는 전일 거래대금 사용)
        curr_trading_value = curr['Close'] * curr['Volume']
        projected_trading_value = curr['Close'] * calculate_projected_volume(int(curr['Volume']))

        # 장 초반(10시 전)이고 예상 거래대금이 전일 거래대금보다 작으면 전일 거래대금 사용
        now = datetime.now()
        if now.hour < 10 and prev_trading_value and projected_trading_value < prev_trading_value:
            trading_value = prev_trading_value
            result['indicators']['trading_value_source'] = 'prev_day'
        else:
            trading_value = projected_trading_value
            result['indicators']['trading_value_source'] = 'projected'

        result['indicators']['trading_value'] = trading_value
        result['indicators']['trading_value_억'] = trading_value / 100_000_000

        # ========== 이동평균선 계산 ==========
        df['SMA_5'] = ta.sma(df['Close'], length=5)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_60'] = ta.sma(df['Close'], length=60)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        curr_sma5 = curr['SMA_5']
        curr_sma20 = curr['SMA_20']
        curr_sma60 = curr['SMA_60']

        # === 과락: 역배열 → 0점 반환 ===
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

        # 20일선 기울기 (핵심 지표)
        if len(df) >= 6:
            sma20_5d_ago = df['SMA_20'].iloc[-6]
            if pd.notna(sma20_5d_ago) and sma20_5d_ago > 0:
                sma20_slope = (curr_sma20 - sma20_5d_ago) / sma20_5d_ago * 100
                result['indicators']['sma20_slope'] = sma20_slope

                if sma20_slope >= 3.0:
                    trend_score += 15
                    result['signals'].append('MA_20_VERY_STEEP')
                elif sma20_slope >= 1.5:
                    trend_score += 10
                    result['signals'].append('MA_20_STEEP')
                elif sma20_slope >= 0.5:
                    trend_score += 3
                    result['signals'].append('MA_20_RISING')

        # MACD > 0: +3점
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is not None:
            macd_col = [c for c in macd.columns if 'MACD_' in c and 'MACDh' not in c and 'MACDs' not in c][0]
            curr_macd = macd.iloc[-1][macd_col]
            result['indicators']['macd'] = curr_macd

            if curr_macd > 0:
                trend_score += 3
                result['signals'].append('MACD_BULL')

        # Supertrend 매수 전환: +7점
        supertrend = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        if supertrend is not None:
            st_col = [c for c in supertrend.columns if 'SUPERTd' in c][0]
            curr_st = supertrend.iloc[-1][st_col]
            prev_st = supertrend.iloc[-2][st_col]

            if prev_st == -1 and curr_st == 1:
                trend_score += 7
                result['signals'].append('SUPERTREND_BUY')

        trend_score = min(30, trend_score)
        result['trend_score'] = trend_score

        # ========== 2. 모멘텀 그룹 (최대 35점) ==========
        momentum_score = 0

        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        rsi = df.iloc[-1]['RSI']
        prev_rsi = df.iloc[-2]['RSI']

        if pd.notna(rsi):
            result['indicators']['rsi'] = rsi

            if 60 <= rsi <= 75:
                momentum_score += 15
                result['signals'].append('RSI_SWEET_SPOT')
            elif 50 <= rsi < 60:
                momentum_score += 5
                result['signals'].append('RSI_HEALTHY')
            elif rsi > 80:
                if pd.notna(prev_rsi) and rsi > prev_rsi:
                    momentum_score += 10
                    result['signals'].append('RSI_POWER_BULL')
                else:
                    momentum_score -= 5
                    result['signals'].append('RSI_PEAK_OUT')
            elif rsi < 30:
                momentum_score -= 10
                result['signals'].append('RSI_FALLING_KNIFE')

        # 60일 신고가 돌파
        high_60d = df['High'].tail(60).max()
        result['indicators']['high_60d'] = high_60d
        result['indicators']['high_60d_pct'] = (curr['Close'] / high_60d - 1) * 100

        if curr['Close'] >= high_60d:
            momentum_score += 15
            result['signals'].append('BREAKOUT_60D_HIGH')
        elif curr['Close'] >= high_60d * 0.97:
            momentum_score += 7
            result['signals'].append('NEAR_60D_HIGH')
        elif curr['Close'] >= high_60d * 0.95:
            momentum_score += 3
            result['signals'].append('CLOSE_TO_60D_HIGH')

        momentum_score = min(35, max(-10, momentum_score))
        result['momentum_score'] = momentum_score

        # ========== 3. 수급 그룹 (최대 35점) ==========
        volume_score = 0

        # 거래량 분석 (장중 예상 거래량 적용)
        df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
        vol_ma = df.iloc[-1]['VOL_MA20']
        curr_vol = int(curr['Volume'])
        projected_vol = calculate_projected_volume(curr_vol)

        if pd.isna(vol_ma) or vol_ma == 0:
            vol_ratio = 1.0
        else:
            vol_ratio = projected_vol / vol_ma

        result['indicators']['volume_ratio'] = vol_ratio
        result['indicators']['projected_volume'] = projected_vol

        if vol_ratio >= 5.0:
            volume_score += 20
            result['signals'].append('VOLUME_EXPLOSION')
        elif vol_ratio >= 3.0:
            volume_score += 12
            result['signals'].append('VOLUME_SURGE_3X')
        elif vol_ratio >= 2.0:
            volume_score += 5
            result['signals'].append('VOLUME_HIGH')

        # 회전율 기반 수급 점수 (거래대금/시총)
        if market_cap and market_cap > 0:
            turnover = (trading_value / market_cap) * 100  # 회전율 %
            result['indicators']['turnover'] = turnover

            if turnover >= 5.0:
                volume_score += 15
                result['signals'].append('TURNOVER_HIGH_5PCT')
            elif turnover >= 2.0:
                volume_score += 10
                result['signals'].append('TURNOVER_MID_2PCT')
            elif turnover >= 1.0:
                volume_score += 3
                result['signals'].append('TURNOVER_LOW_1PCT')
            elif turnover < 0.2:
                volume_score -= 5
                result['signals'].append('TURNOVER_VERY_LOW')
        else:
            # 시총 정보 없으면 기존 거래대금 기준 (하위 호환)
            if trading_value >= 50_000_000_000:
                volume_score += 15
                result['signals'].append('TRADING_VALUE_500B')
            elif trading_value >= 10_000_000_000:
                volume_score += 10
                result['signals'].append('TRADING_VALUE_100B')
            elif trading_value >= 3_000_000_000:
                volume_score += 3
                result['signals'].append('TRADING_VALUE_30B')
            elif trading_value < 1_000_000_000:
                volume_score -= 5
                result['signals'].append('LOW_LIQUIDITY')

        volume_score = min(35, max(-10, volume_score))
        result['volume_score'] = volume_score

        # ========== 최종 점수 (스케일링 없음) ==========
        total_score = trend_score + momentum_score + volume_score
        result['score'] = max(0, min(100, total_score))

        return result

    except Exception as e:
        print(f"V2 점수 계산 오류: {e}")
        return None


# 테스트
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    df = fdr.DataReader('005930', start_date)

    result = calculate_score_v2(df)
    if result:
        print(f"=== V2 점수 계산 결과 ===")
        print(f"최종점수: {result['score']}")
        print(f"  추세: {result['trend_score']}/30")
        print(f"  모멘텀: {result['momentum_score']}/35")
        print(f"  수급: {result['volume_score']}/35")
        print(f"신호: {result['signals']}")
