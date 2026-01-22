"""
V3 점수 계산 로직 - 사일런트 바이어 (Silent Buyer)

철학: "가격은 속여도 거래량은 속일 수 없다"
      세력이 숨어서 매집하는 흔적을 포착

점수 체계 (100점 만점):
- 추세 기반 (25점): 정배열, 20일선 기울기
- 매집 패턴 (40점): OBV 다이버전스, 매집봉, Spring, VCP
- 거래량 분석 (20점): 눌림목 거래량 급감, 거래량 터짐
- 모멘텀 (15점): RSI, 60일 고가 근접

핵심 매집 신호:
1. OBV 다이버전스: 주가↓ but OBV↑ (스마트머니 유입)
2. 매집봉: 바닥권 윗꼬리 + 거래량 급증 (매물 테스트)
3. Spring: 지지선 이탈 후 급반등 (개미 털기/베어트랩)
4. VCP: 변동성 축소 + 거래량 급감 (매집 완료 임박)
5. 눌림목 거래량 급감: 조정 시 거래량↓ (세력 미이탈)

┌──────────────────────────────────┬──────┐
│ 추세 그룹 (25점)                  │      │
├──────────────────────────────────┼──────┤
│ 정배열                            │ +5   │
│ 20일선 기울기 ≥ 1.5%              │ +15  │
│ 20일선 기울기 ≥ 0.5%              │ +10  │
│ 20일선 기울기 ≥ 0%                │ +5   │
├──────────────────────────────────┼──────┤
│ 매집 패턴 그룹 (40점)             │      │
├──────────────────────────────────┼──────┤
│ OBV 불리시 다이버전스              │ +12  │
│ 매집봉 (바닥권 윗꼬리+거래량)       │ +10  │
│ Spring 패턴 (지지선 이탈 후 회복)   │ +10  │
│ VCP 패턴 (변동성 수축)             │ +8   │
├──────────────────────────────────┼──────┤
│ 거래량 분석 그룹 (20점)            │      │
├──────────────────────────────────┼──────┤
│ 눌림목 거래량 급감 (조정時 저거래량) │ +8   │
│ 거래량 ≥ 3배 (돌파 시)             │ +12  │
│ 거래량 ≥ 2배                      │ +6   │
├──────────────────────────────────┼──────┤
│ 모멘텀 그룹 (15점)                │      │
├──────────────────────────────────┼──────┤
│ RSI 50~70                        │ +8   │
│ 60일 고가 95% 이내                 │ +7   │
└──────────────────────────────────┴──────┘
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Optional, List


def detect_obv_divergence(df: pd.DataFrame, lookback: int = 30) -> Dict:
    """
    OBV 불리시 다이버전스 감지

    세력 매집 신호: 주가는 저점을 낮추는데 OBV는 저점을 높임
    → "팽팽하게 감긴 스프링" (그랜빌)

    Returns:
        {
            'detected': bool,
            'strength': 강도 (0-100),
            'days': 다이버전스 발생 기간
        }
    """
    result = {'detected': False, 'strength': 0, 'days': 0}

    try:
        if len(df) < lookback:
            return result

        obv = ta.obv(df['Close'], df['Volume'])
        if obv is None:
            return result

        df_temp = df.tail(lookback).copy()
        df_temp['OBV'] = obv.tail(lookback).values

        # 저점 찾기 (5일 기준 로컬 미니멈)
        price_lows = []
        obv_at_lows = []

        for i in range(2, len(df_temp) - 2):
            if (df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i-1] and
                df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i-2] and
                df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i+1] and
                df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i+2]):
                price_lows.append((i, df_temp['Low'].iloc[i]))
                obv_at_lows.append((i, df_temp['OBV'].iloc[i]))

        # 최소 2개의 저점 필요
        if len(price_lows) >= 2:
            # 가장 최근 2개 저점 비교
            prev_price_low = price_lows[-2][1]
            curr_price_low = price_lows[-1][1]
            prev_obv = obv_at_lows[-2][1]
            curr_obv = obv_at_lows[-1][1]

            # 불리시 다이버전스: 가격↓ OBV↑
            if curr_price_low < prev_price_low and curr_obv > prev_obv:
                result['detected'] = True
                result['days'] = price_lows[-1][0] - price_lows[-2][0]

                # 다이버전스 강도 계산
                price_decline = (prev_price_low - curr_price_low) / prev_price_low * 100
                obv_rise = (curr_obv - prev_obv) / abs(prev_obv) * 100 if prev_obv != 0 else 0
                result['strength'] = min(100, price_decline + obv_rise)

    except Exception as e:
        pass

    return result


def detect_accumulation_candle(df: pd.DataFrame) -> Dict:
    """
    매집봉 감지: 바닥권에서 윗꼬리 양봉 + 거래량 급증

    세력 매집 신호:
    - 장중 급등 후 종가에 밀림 (윗꼬리)
    - 거래량이 평소 대비 급증
    - 바닥권 (20일 저가 근처)에서 발생

    Returns:
        {
            'detected': bool,
            'volume_ratio': 거래량 비율,
            'upper_wick_ratio': 윗꼬리 비율
        }
    """
    result = {'detected': False, 'volume_ratio': 0, 'upper_wick_ratio': 0}

    try:
        if len(df) < 20:
            return result

        curr = df.iloc[-1]
        vol_ma = df['Volume'].tail(20).mean()

        # 캔들 구조 분석
        body = curr['Close'] - curr['Open']
        upper_shadow = curr['High'] - max(curr['Close'], curr['Open'])
        lower_shadow = min(curr['Close'], curr['Open']) - curr['Low']
        total_range = curr['High'] - curr['Low']

        if total_range == 0:
            return result

        # 바닥권 확인: 20일 저가의 105% 이내
        low_20d = df['Low'].tail(20).min()
        is_near_bottom = curr['Low'] <= low_20d * 1.05

        # 윗꼬리 비율
        upper_wick_ratio = upper_shadow / total_range

        # 거래량 비율
        vol_ratio = curr['Volume'] / vol_ma if vol_ma > 0 else 0

        # 매집봉 조건:
        # 1. 바닥권
        # 2. 윗꼬리가 전체 범위의 40% 이상
        # 3. 거래량이 평균의 1.5배 이상
        # 4. 양봉 또는 도지 (음봉 X)
        is_bullish_or_doji = body >= 0

        if (is_near_bottom and
            upper_wick_ratio >= 0.4 and
            vol_ratio >= 1.5 and
            is_bullish_or_doji):
            result['detected'] = True
            result['volume_ratio'] = vol_ratio
            result['upper_wick_ratio'] = upper_wick_ratio * 100

    except Exception as e:
        pass

    return result


def detect_spring_pattern(df: pd.DataFrame) -> Dict:
    """
    Spring 패턴 감지 (개미 털기 / 베어트랩)

    세력 매집 신호:
    - 지지선(박스권 하단) 이탈 → 급반등
    - 개미 손절 물량 흡수 후 급등

    Returns:
        {
            'detected': bool,
            'recovery_strength': 회복 강도 (%),
            'volume_spike': 거래량 급증 여부
        }
    """
    result = {'detected': False, 'recovery_strength': 0, 'volume_spike': False}

    try:
        if len(df) < 20:
            return result

        recent = df.tail(10)
        curr = df.iloc[-1]

        # 20일 박스권 하단 (지지선)
        support = df['Low'].tail(20).quantile(0.1)  # 하위 10%

        # 최근 10일 내 지지선 이탈 여부
        breakdown_day = None
        for i in range(len(recent) - 1):
            if recent['Low'].iloc[i] < support:
                breakdown_day = i
                break

        if breakdown_day is not None:
            # 이탈 후 회복 확인
            breakdown_low = recent['Low'].iloc[breakdown_day]

            # 현재가가 지지선 위로 회복
            if curr['Close'] > support:
                recovery = (curr['Close'] - breakdown_low) / breakdown_low * 100
                result['recovery_strength'] = recovery

                # 회복 시 거래량 확인
                vol_ma = df['Volume'].tail(20).mean()
                if curr['Volume'] > vol_ma * 1.5:
                    result['volume_spike'] = True

                # Spring 조건: 지지선 이탈 후 3% 이상 회복
                if recovery >= 3:
                    result['detected'] = True

    except Exception as e:
        pass

    return result


def detect_vcp_pattern(df: pd.DataFrame) -> Dict:
    """
    VCP (Volatility Contraction Pattern) 감지

    세력 매집 완료 신호:
    - 변동성(등락폭) 점점 감소
    - 거래량도 급감
    - 매도 물량 소진 → 급등 준비

    Returns:
        {
            'detected': bool,
            'contraction_pct': 수축률 (%),
            'vol_dryup': 거래량 급감 여부
        }
    """
    result = {'detected': False, 'contraction_pct': 0, 'vol_dryup': False}

    try:
        if len(df) < 40:
            return result

        recent = df.tail(40)

        # 4개의 10일 구간 분석
        ranges = []
        volumes = []

        for i in range(4):
            period = recent.iloc[i*10:(i+1)*10]
            high = period['High'].max()
            low = period['Low'].min()
            vol = period['Volume'].mean()
            ranges.append(high - low)
            volumes.append(vol)

        # VCP 조건:
        # 1. 변동폭 수축: 마지막 구간이 첫 구간의 70% 미만
        # 2. 저점 상승: 마지막 저점 > 첫 저점
        # 3. 거래량 감소: 마지막 구간 거래량 < 첫 구간의 70%

        first_range = ranges[0]
        last_range = ranges[3]
        first_vol = volumes[0]
        last_vol = volumes[3]

        first_low = recent.iloc[:10]['Low'].min()
        last_low = recent.iloc[30:]['Low'].min()

        range_contraction = last_range < first_range * 0.7
        lows_rising = last_low > first_low
        vol_contraction = last_vol < first_vol * 0.7

        if range_contraction and lows_rising:
            result['detected'] = True
            result['contraction_pct'] = (1 - last_range / first_range) * 100

            if vol_contraction:
                result['vol_dryup'] = True

    except Exception as e:
        pass

    return result


def detect_pullback_volume_dryup(df: pd.DataFrame) -> Dict:
    """
    눌림목 거래량 급감 감지

    세력 미이탈 신호:
    - 주가 조정(하락) 시 거래량 급감
    - "세력은 안 팔고, 개미만 팔고 있다"

    Returns:
        {
            'detected': bool,
            'pullback_pct': 조정폭 (%),
            'vol_ratio': 조정 시 거래량 비율
        }
    """
    result = {'detected': False, 'pullback_pct': 0, 'vol_ratio': 0}

    try:
        if len(df) < 20:
            return result

        # 최근 5일 분석
        recent_5d = df.tail(5)
        prev_15d = df.iloc[-20:-5]

        # 최근 5일 중 하락일
        down_days = recent_5d[recent_5d['Close'] < recent_5d['Open']]

        if len(down_days) == 0:
            return result

        # 하락일 평균 거래량
        down_vol = down_days['Volume'].mean()

        # 이전 15일 평균 거래량
        prev_vol = prev_15d['Volume'].mean()

        if prev_vol > 0:
            vol_ratio = down_vol / prev_vol
            result['vol_ratio'] = vol_ratio

            # 조정폭 계산
            high_5d = recent_5d['High'].max()
            low_5d = recent_5d['Low'].min()
            pullback = (high_5d - low_5d) / high_5d * 100
            result['pullback_pct'] = pullback

            # 눌림목 거래량 급감 조건:
            # 1. 하락일 거래량이 평균의 60% 미만
            # 2. 조정폭 2% 이상 (의미있는 조정)
            if vol_ratio < 0.6 and pullback >= 2:
                result['detected'] = True

    except Exception as e:
        pass

    return result


def calculate_score_v3(df: pd.DataFrame) -> Optional[Dict]:
    """
    V3 점수 계산 (사일런트 바이어 - Silent Buyer)

    Args:
        df: OHLCV 데이터프레임 (최소 60일)

    Returns:
        {
            'score': 최종 점수 (0-100),
            'trend_score': 추세 점수,
            'accumulation_score': 매집 패턴 점수,
            'volume_score': 거래량 분석 점수,
            'momentum_score': 모멘텀 점수,
            'signals': 발생한 신호 리스트,
            'patterns': 감지된 패턴,
            'indicators': 지표 상세값
        }
    """
    if df is None or len(df) < 60:
        return None

    result = {
        'score': 0,
        'trend_score': 0,
        'accumulation_score': 0,
        'volume_score': 0,
        'momentum_score': 0,
        'signals': [],
        'patterns': [],
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

        # ========== 1. 추세 그룹 (최대 25점) ==========
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

                if sma20_slope >= 1.5:
                    trend_score += 15
                    result['signals'].append('SLOPE_STEEP')
                elif sma20_slope >= 0.5:
                    trend_score += 10
                    result['signals'].append('SLOPE_RISING')
                elif sma20_slope >= 0:
                    trend_score += 5
                    result['signals'].append('SLOPE_FLAT_UP')

        trend_score = min(25, trend_score)
        result['trend_score'] = trend_score

        # ========== 2. 매집 패턴 그룹 (최대 40점) ==========
        accumulation_score = 0
        detected_patterns = []

        # OBV 다이버전스: +12점
        obv_div = detect_obv_divergence(df)
        if obv_div['detected']:
            accumulation_score += 12
            result['signals'].append('OBV_BULLISH_DIV')
            detected_patterns.append('OBV_DIV')
            result['indicators']['obv_div_strength'] = obv_div['strength']
            result['indicators']['obv_div_days'] = obv_div['days']

        # 매집봉: +10점
        accum_candle = detect_accumulation_candle(df)
        if accum_candle['detected']:
            accumulation_score += 10
            result['signals'].append('ACCUMULATION_CANDLE')
            detected_patterns.append('ACCUM_CANDLE')
            result['indicators']['accum_vol_ratio'] = accum_candle['volume_ratio']
            result['indicators']['upper_wick_pct'] = accum_candle['upper_wick_ratio']

        # Spring 패턴: +10점
        spring = detect_spring_pattern(df)
        if spring['detected']:
            accumulation_score += 10
            result['signals'].append('SPRING_PATTERN')
            detected_patterns.append('SPRING')
            result['indicators']['spring_recovery'] = spring['recovery_strength']
            if spring['volume_spike']:
                result['signals'].append('SPRING_VOLUME_SPIKE')

        # VCP 패턴: +8점
        vcp = detect_vcp_pattern(df)
        if vcp['detected']:
            accumulation_score += 8
            result['signals'].append('VCP_PATTERN')
            detected_patterns.append('VCP')
            result['indicators']['vcp_contraction'] = vcp['contraction_pct']
            if vcp['vol_dryup']:
                result['signals'].append('VCP_VOL_DRYUP')

        accumulation_score = min(40, accumulation_score)
        result['accumulation_score'] = accumulation_score
        result['patterns'] = detected_patterns

        # ========== 3. 거래량 분석 그룹 (최대 20점) ==========
        volume_score = 0

        # 눌림목 거래량 급감: +8점
        pullback = detect_pullback_volume_dryup(df)
        if pullback['detected']:
            volume_score += 8
            result['signals'].append('PULLBACK_VOL_DRYUP')
            result['indicators']['pullback_pct'] = pullback['pullback_pct']
            result['indicators']['pullback_vol_ratio'] = pullback['vol_ratio']

        # 거래량 급증
        df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
        vol_ma = df.iloc[-1]['VOL_MA20']

        if pd.notna(vol_ma) and vol_ma > 0:
            vol_ratio = curr['Volume'] / vol_ma
            result['indicators']['volume_ratio'] = vol_ratio

            if vol_ratio >= 3.0:
                volume_score += 12
                result['signals'].append('VOLUME_3X')
            elif vol_ratio >= 2.0:
                volume_score += 6
                result['signals'].append('VOLUME_2X')

        volume_score = min(20, volume_score)
        result['volume_score'] = volume_score

        # ========== 4. 모멘텀 그룹 (최대 15점) ==========
        momentum_score = 0

        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        rsi = df.iloc[-1]['RSI']

        if pd.notna(rsi):
            result['indicators']['rsi'] = rsi

            if 50 <= rsi <= 70:
                momentum_score += 8
                result['signals'].append('RSI_HEALTHY')
            elif 40 <= rsi < 50:
                momentum_score += 4
                result['signals'].append('RSI_RECOVERING')

        # 60일 고가 근접
        high_60d = df['High'].tail(60).max()
        result['indicators']['high_60d'] = high_60d
        high_60d_pct = (curr['Close'] / high_60d - 1) * 100
        result['indicators']['high_60d_pct'] = high_60d_pct

        if high_60d_pct >= -5:  # 95% 이내
            momentum_score += 7
            result['signals'].append('NEAR_60D_HIGH')
        elif high_60d_pct >= -10:  # 90% 이내
            momentum_score += 3
            result['signals'].append('CLOSE_TO_60D')

        momentum_score = min(15, momentum_score)
        result['momentum_score'] = momentum_score

        # ========== 최종 점수 ==========
        total_score = trend_score + accumulation_score + volume_score + momentum_score
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

    # 테스트 종목
    test_stocks = ['005930', '035720', '000660']

    for code in test_stocks:
        df = fdr.DataReader(code, start_date)

        result = calculate_score_v3(df)
        if result:
            print(f"\n=== {code} V3 세력 매집 분석 ===")
            print(f"최종점수: {result['score']}")
            print(f"  추세: {result['trend_score']}/25")
            print(f"  매집: {result['accumulation_score']}/40")
            print(f"  거래량: {result['volume_score']}/20")
            print(f"  모멘텀: {result['momentum_score']}/15")
            print(f"패턴: {result['patterns']}")
            print(f"신호: {result['signals']}")
