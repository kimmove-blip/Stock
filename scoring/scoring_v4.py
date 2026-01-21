"""
V4 점수 계산 로직 - Hybrid Sniper (하이브리드 스나이퍼)

철학: 고급 기술적 분석으로 정밀 진입
      VCP 패턴, OBV 다이버전스 등 세력 축적 신호 탐지

점수 체계 (100점 만점):
- 추세 (30점): 정배열 +5, 20일선 기울기 +15, 구름대 위 +5, MACD +5
- 수급 (30점): 거래량 +12, 거래대금 +10, 기관/외국인 +8
- 패턴 (20점): VCP +12, OBV 다이버전스 +8
- 모멘텀 (20점): RSI +8, StochRSI +7, 60일 신고가 +5

특징:
- VCP (Volatility Contraction Pattern) 감지
- OBV 다이버전스 (세력 축적) 감지
- Stochastic RSI 정밀 과열/과매도 판단
- MACD 오실레이터 추세 확인
- 캔들 패턴 감지 (유성형 감점)
- 기관/외국인 수급 데이터 (한투 API)
- 85점 이상 = 강력 매수

┌──────────────────────────────────┬──────┐
│ 추세 그룹 (30점)                  │      │
├──────────────────────────────────┼──────┤
│ 정배열                            │ +5   │
│ 20일선 기울기 ≥ 3%                │ +15  │
│ 20일선 기울기 ≥ 1.5%              │ +10  │
│ 20일선 기울기 ≥ 0.5%              │ +5   │
│ 일목 구름대 위                     │ +5   │
│ MACD > 0 & 상승                   │ +5   │
│ MACD 하락 다이버전스               │ -5   │
├──────────────────────────────────┼──────┤
│ 수급 그룹 (30점)                  │      │
├──────────────────────────────────┼──────┤
│ 거래량 ≥ 5배                      │ +12  │
│ 거래량 ≥ 3배                      │ +8   │
│ 거래량 ≥ 2배                      │ +4   │
│ 거래대금 ≥ 500억                  │ +10  │
│ 거래대금 ≥ 100억                  │ +6   │
│ 거래대금 ≥ 30억                   │ +3   │
│ 거래대금 < 10억                   │ -5   │
│ 기관+외국인 순매수 (5일) > 0       │ +5   │
│ 외국인 연속 3일 이상 순매수         │ +3   │
│ 기관+외국인 순매도 (5일)           │ -3   │
├──────────────────────────────────┼──────┤
│ 패턴 그룹 (20점)                  │      │
├──────────────────────────────────┼──────┤
│ VCP 패턴 감지                     │ +12  │
│ OBV 불리시 다이버전스              │ +8   │
├──────────────────────────────────┼──────┤
│ 모멘텀 그룹 (20점)                │      │
├──────────────────────────────────┼──────┤
│ RSI 60~75                        │ +8   │
│ RSI 50~60                        │ +4   │
│ RSI > 85                         │ -5   │
│ StochRSI 골든크로스 (K<30)        │ +7   │
│ StochRSI 상승 추세                │ +4   │
│ 60일 신고가 돌파                   │ +5   │
│ 유성형 캔들 (Shooting Star)       │ -5   │
└──────────────────────────────────┴──────┘

※ 기관/외국인 수급: investor_data 파라미터로 전달 (한투 API FHKST01010900)
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Optional


def detect_vcp_pattern(df: pd.DataFrame) -> Dict:
    """
    VCP (Volatility Contraction Pattern) 패턴 감지

    VCP 특징:
    1. 고점은 비슷하게 유지
    2. 저점은 점점 높아짐 (수축)
    3. 거래량도 수축
    4. 마지막에 거래량 터지며 돌파
    """
    result = {'detected': False, 'contraction_pct': 0, 'vol_breakout': False}

    try:
        if len(df) < 40:
            return result

        recent = df.tail(40).copy()

        # 4개의 10일 구간으로 나누기
        ranges = []
        for i in range(4):
            start_idx = i * 10
            end_idx = start_idx + 10
            period = recent.iloc[start_idx:end_idx]
            high = period['High'].max()
            low = period['Low'].min()
            vol = period['Volume'].mean()
            ranges.append({'high': high, 'low': low, 'vol': vol, 'range': high - low})

        # VCP 조건 체크
        range_contraction = ranges[3]['range'] < ranges[0]['range'] * 0.7
        lows_rising = ranges[3]['low'] > ranges[0]['low']
        vol_contraction = ranges[2]['vol'] < ranges[0]['vol'] * 0.7
        vol_expansion = ranges[3]['vol'] > ranges[2]['vol']

        if range_contraction and lows_rising and vol_contraction:
            result['detected'] = True
            result['contraction_pct'] = (1 - ranges[3]['range'] / ranges[0]['range']) * 100
            result['vol_breakout'] = vol_expansion

    except:
        pass

    return result


def detect_obv_divergence(df: pd.DataFrame) -> Dict:
    """
    OBV 다이버전스 감지 (세력 축적 신호)

    불리시 다이버전스:
    - 가격은 저점을 낮추는데
    - OBV는 저점을 높이는 경우
    """
    result = {'bullish_divergence': False, 'days': 0}

    try:
        if len(df) < 30:
            return result

        obv = ta.obv(df['Close'], df['Volume'])
        if obv is None:
            return result

        df_temp = df.copy()
        df_temp['OBV'] = obv

        recent = df_temp.tail(30)

        # 가격 저점들 찾기
        price_lows = []
        for i in range(2, len(recent) - 2):
            if (recent['Low'].iloc[i] < recent['Low'].iloc[i-1] and
                recent['Low'].iloc[i] < recent['Low'].iloc[i-2] and
                recent['Low'].iloc[i] < recent['Low'].iloc[i+1] and
                recent['Low'].iloc[i] < recent['Low'].iloc[i+2]):
                price_lows.append((i, recent['Low'].iloc[i], recent['OBV'].iloc[i]))

        if len(price_lows) >= 2:
            prev_low = price_lows[-2]
            curr_low = price_lows[-1]

            if curr_low[1] < prev_low[1] and curr_low[2] > prev_low[2]:
                result['bullish_divergence'] = True
                result['days'] = curr_low[0] - prev_low[0]

    except:
        pass

    return result


def calculate_stoch_rsi(df: pd.DataFrame) -> Optional[Dict]:
    """Stochastic RSI 계산"""
    try:
        stoch_rsi = ta.stochrsi(df['Close'], length=14, rsi_length=14, k=3, d=3)
        if stoch_rsi is None:
            return None

        k_col = [c for c in stoch_rsi.columns if 'STOCHRSIk' in c]
        d_col = [c for c in stoch_rsi.columns if 'STOCHRSId' in c]

        if not k_col or not d_col:
            return None

        curr_k = stoch_rsi.iloc[-1][k_col[0]]
        curr_d = stoch_rsi.iloc[-1][d_col[0]]
        prev_k = stoch_rsi.iloc[-2][k_col[0]]
        prev_d = stoch_rsi.iloc[-2][d_col[0]]

        golden_cross = (prev_k < prev_d) and (curr_k > curr_d)

        return {
            'k': curr_k * 100,
            'd': curr_d * 100,
            'golden_cross': golden_cross
        }
    except:
        return None


def calculate_score_v4(df: pd.DataFrame, investor_data: Optional[Dict] = None) -> Optional[Dict]:
    """
    V4 점수 계산 (Hybrid Sniper)

    Args:
        df: OHLCV 데이터프레임 (최소 60일)
        investor_data: 투자자별 매매동향 (한투 API FHKST01010900)
            {
                'foreign_net': 외국인 순매수량 (5일 합계),
                'institution_net': 기관 순매수량 (5일 합계),
                'daily': [일별 상세 데이터]
            }

    Returns:
        {
            'score': 최종 점수 (0-100),
            'trend_score': 추세 점수,
            'pattern_score': 패턴 점수,
            'momentum_score': 모멘텀 점수,
            'supply_score': 수급 점수,
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
        'pattern_score': 0,
        'momentum_score': 0,
        'supply_score': 0,
        'signals': [],
        'patterns': [],
        'indicators': {},
        'version': 'v4'
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

        # === 과락: 역배열 ===
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

                if sma20_slope >= 1.0:
                    trend_score += 15
                    result['signals'].append('SLOPE_VERY_STEEP')
                elif sma20_slope >= 0.5:
                    trend_score += 10
                    result['signals'].append('SLOPE_STEEP')
                elif sma20_slope >= 0:
                    trend_score += 5
                    result['signals'].append('SLOPE_RISING')

        # 일목균형표 구름대 위
        ichimoku = ta.ichimoku(df['High'], df['Low'], df['Close'])
        if ichimoku is not None and len(ichimoku) == 2:
            ich_df = ichimoku[0]
            span_a_col = [c for c in ich_df.columns if 'ISA' in c]
            span_b_col = [c for c in ich_df.columns if 'ISB' in c]

            if span_a_col and span_b_col:
                span_a = ich_df.iloc[-1][span_a_col[0]]
                span_b = ich_df.iloc[-1][span_b_col[0]]
                if pd.notna(span_a) and pd.notna(span_b):
                    cloud_top = max(span_a, span_b)
                    if curr['Close'] > cloud_top:
                        trend_score += 5
                        result['signals'].append('ABOVE_CLOUD')

        # MACD 오실레이터 (추가됨)
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is not None:
            macd_col = [c for c in macd.columns if 'MACD_' in c and 'MACDh' not in c and 'MACDs' not in c]
            macdh_col = [c for c in macd.columns if 'MACDh' in c]
            if macd_col and macdh_col:
                curr_macd = macd.iloc[-1][macd_col[0]]
                prev_macd = macd.iloc[-2][macd_col[0]]
                curr_hist = macd.iloc[-1][macdh_col[0]]
                prev_hist = macd.iloc[-2][macdh_col[0]]
                result['indicators']['macd'] = curr_macd
                result['indicators']['macd_hist'] = curr_hist

                # MACD > 0 & 히스토그램 상승: +5점
                if curr_macd > 0 and curr_hist > prev_hist:
                    trend_score += 5
                    result['signals'].append('MACD_RISING')
                # MACD 하락 다이버전스 감지 (가격은 신고가인데 MACD는 하락)
                elif curr_macd < prev_macd and curr['Close'] > df.iloc[-2]['Close']:
                    trend_score -= 5
                    result['signals'].append('MACD_BEARISH_DIV')

        trend_score = min(30, max(-5, trend_score))
        result['trend_score'] = trend_score

        # ========== 2. 패턴 그룹 (최대 20점) ==========
        pattern_score = 0

        # VCP 패턴: +12점
        vcp_result = detect_vcp_pattern(df)
        if vcp_result['detected']:
            pattern_score += 12
            result['signals'].append('VCP_PATTERN')
            result['patterns'].append('VCP')
            result['indicators']['vcp_contraction'] = vcp_result['contraction_pct']

        # OBV 다이버전스: +8점
        obv_div = detect_obv_divergence(df)
        if obv_div['bullish_divergence']:
            pattern_score += 8
            result['signals'].append('OBV_BULLISH_DIV')
            result['patterns'].append('OBV_DIV')
            result['indicators']['obv_divergence_days'] = obv_div['days']

        pattern_score = min(20, pattern_score)
        result['pattern_score'] = pattern_score

        # ========== 3. 모멘텀 그룹 (최대 20점) ==========
        momentum_score = 0

        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        rsi = df.iloc[-1]['RSI']

        if pd.notna(rsi):
            result['indicators']['rsi'] = rsi

            if 60 <= rsi <= 75:
                momentum_score += 8
                result['signals'].append('RSI_SWEET_SPOT')
            elif 50 <= rsi < 60:
                momentum_score += 4
                result['signals'].append('RSI_HEALTHY')
            elif rsi > 85:
                momentum_score -= 5
                result['signals'].append('RSI_EXTREME')

        # Stochastic RSI
        stoch_rsi = calculate_stoch_rsi(df)
        if stoch_rsi is not None:
            result['indicators']['stoch_rsi_k'] = stoch_rsi['k']
            result['indicators']['stoch_rsi_d'] = stoch_rsi['d']

            if stoch_rsi['golden_cross'] and stoch_rsi['k'] < 30:
                momentum_score += 7
                result['signals'].append('STOCH_RSI_GOLDEN')
            elif stoch_rsi['k'] > stoch_rsi['d'] and stoch_rsi['k'] < 80:
                momentum_score += 4
                result['signals'].append('STOCH_RSI_BULLISH')

        # 60일 신고가
        high_60d = df['High'].tail(60).max()
        result['indicators']['high_60d'] = high_60d
        result['indicators']['high_60d_pct'] = (curr['Close'] / high_60d - 1) * 100

        if curr['Close'] >= high_60d:
            momentum_score += 5
            result['signals'].append('BREAKOUT_60D')

        # 캔들 패턴 감점 (유성형 - Shooting Star)
        try:
            # 유성형: 윗꼬리가 길고 실체가 작은 음봉 (고점 부근에서 발생하면 하락 신호)
            body = abs(curr['Close'] - curr['Open'])
            upper_shadow = curr['High'] - max(curr['Close'], curr['Open'])
            lower_shadow = min(curr['Close'], curr['Open']) - curr['Low']
            total_range = curr['High'] - curr['Low']

            if total_range > 0:
                # 유성형 조건: 윗꼬리가 실체의 2배 이상, 아래꼬리가 실체보다 작음
                is_shooting_star = (
                    upper_shadow >= body * 2 and
                    lower_shadow < body and
                    curr['Close'] < curr['Open'] and  # 음봉
                    curr['Close'] >= high_60d * 0.95  # 60일 고점 근처
                )
                if is_shooting_star:
                    momentum_score -= 5
                    result['signals'].append('SHOOTING_STAR')
                    result['patterns'].append('SHOOTING_STAR')
        except:
            pass

        momentum_score = min(20, max(-10, momentum_score))
        result['momentum_score'] = momentum_score

        # ========== 4. 수급 그룹 (최대 30점) ==========
        supply_score = 0

        # 거래량 (최대 12점)
        df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
        vol_ma = df.iloc[-1]['VOL_MA20']

        if pd.notna(vol_ma) and vol_ma > 0:
            vol_ratio = curr['Volume'] / vol_ma
            result['indicators']['volume_ratio'] = vol_ratio

            if vol_ratio >= 2.5:
                supply_score += 12
                result['signals'].append('VOLUME_2.5X')
            elif vol_ratio >= 2.0:
                supply_score += 8
                result['signals'].append('VOLUME_2X')
            elif vol_ratio >= 1.5:
                supply_score += 4
                result['signals'].append('VOLUME_1.5X')

        # 거래대금 (최대 10점)
        if trading_value >= 50_000_000_000:
            supply_score += 10
            result['signals'].append('VALUE_500B')
        elif trading_value >= 10_000_000_000:
            supply_score += 6
            result['signals'].append('VALUE_100B')
        elif trading_value >= 3_000_000_000:
            supply_score += 3
            result['signals'].append('VALUE_30B')
        elif trading_value < 1_000_000_000:
            supply_score -= 5
            result['signals'].append('LOW_LIQUIDITY')

        # 기관/외국인 수급 (최대 8점) - 한투 API FHKST01010900
        if investor_data is not None:
            foreign_net = investor_data.get('foreign_net', 0)
            institution_net = investor_data.get('institution_net', 0)
            daily = investor_data.get('daily', [])

            result['indicators']['foreign_net_5d'] = foreign_net
            result['indicators']['institution_net_5d'] = institution_net

            # 기관+외국인 합산 순매수
            total_inst_foreign = foreign_net + institution_net

            if total_inst_foreign > 0:
                supply_score += 5
                result['signals'].append('INST_FOREIGN_BUY')
            elif total_inst_foreign < 0:
                supply_score -= 3
                result['signals'].append('INST_FOREIGN_SELL')

            # 외국인 연속 순매수 체크 (최근 3일)
            if len(daily) >= 3:
                consecutive_foreign_buy = all(
                    d.get('foreign_net', 0) > 0 for d in daily[:3]
                )
                if consecutive_foreign_buy:
                    supply_score += 3
                    result['signals'].append('FOREIGN_CONSECUTIVE_BUY')

        supply_score = min(30, max(-8, supply_score))
        result['supply_score'] = supply_score

        # ========== ATR 계산 (참고용) ==========
        atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        if atr is not None:
            curr_atr = atr.iloc[-1]
            result['indicators']['atr'] = curr_atr
            result['indicators']['atr_pct'] = (curr_atr / curr['Close']) * 100

        # ========== 최종 점수 ==========
        total_score = trend_score + pattern_score + momentum_score + supply_score
        result['score'] = max(0, min(100, total_score))

        return result

    except Exception as e:
        print(f"V4 점수 계산 오류: {e}")
        return None


def calculate_score_v4_with_investor(
    df: pd.DataFrame,
    stock_code: str,
    kis_client=None
) -> Optional[Dict]:
    """
    투자자 데이터 포함 V4 점수 계산 (편의 함수)

    Args:
        df: OHLCV 데이터프레임
        stock_code: 종목코드 (6자리)
        kis_client: KISClient 인스턴스 (없으면 투자자 데이터 제외)

    Returns:
        V4 점수 결과 (투자자 데이터 포함)

    Example:
        >>> from api.services.kis_client import KISClient
        >>> kis = KISClient(is_virtual=False)
        >>> result = calculate_score_v4_with_investor(df, '005930', kis)
    """
    investor_data = None

    if kis_client is not None:
        try:
            investor_data = kis_client.get_investor_trend(stock_code, days=5)
        except Exception as e:
            print(f"투자자 데이터 조회 실패 [{stock_code}]: {e}")

    return calculate_score_v4(df, investor_data)


# 테스트
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    df = fdr.DataReader('005930', start_date)

    print("=== V4 점수 계산 (투자자 데이터 없음) ===")
    result = calculate_score_v4(df)
    if result:
        print(f"최종점수: {result['score']}")
        print(f"  추세: {result['trend_score']}/30")
        print(f"  수급: {result['supply_score']}/30")
        print(f"  패턴: {result['pattern_score']}/20")
        print(f"  모멘텀: {result['momentum_score']}/20")
        print(f"신호: {result['signals']}")
        print(f"패턴: {result['patterns']}")
