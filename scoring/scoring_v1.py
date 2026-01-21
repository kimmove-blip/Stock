"""
V1 점수 계산 로직 - 종합 기술적 분석

철학: 모든 지표를 종합하여 점수 산출, 과매도 = 매수 기회 (역발상)

점수 체계:
- 17개 이상의 기술 지표 종합
- 과매도(RSI<30) → +15점 (매수 기회)
- 역배열 → -10점 (과락 아님)
- 스케일링: 0-60→0-54, 60-100→54-80, 100+→80-100

지표별 점수:
┌──────────────────────────────────┬──────┐
│ 이동평균선                        │      │
├──────────────────────────────────┼──────┤
│ 정배열 (5>20>60)                  │ +15  │
│ 골든크로스 5/20                    │ +20  │
│ 골든크로스 20/60                   │ +25  │
│ 데드크로스 5/20                    │ -15  │
│ 역배열                            │ -10  │
├──────────────────────────────────┼──────┤
│ RSI                              │      │
├──────────────────────────────────┼──────┤
│ RSI < 30 (과매도)                 │ +15  │
│ 30 ≤ RSI < 50                    │ +5   │
│ RSI > 70 (과매수)                 │ -10  │
├──────────────────────────────────┼──────┤
│ MACD                             │      │
├──────────────────────────────────┼──────┤
│ MACD 골든크로스                    │ +20  │
│ 히스토그램 양전환                   │ +10  │
│ 히스토그램 상승 중                  │ +5   │
├──────────────────────────────────┼──────┤
│ Stochastic                       │      │
├──────────────────────────────────┼──────┤
│ K<30에서 골든크로스                 │ +20  │
│ 일반 골든크로스                     │ +10  │
│ K < 20 (과매도)                   │ +5   │
├──────────────────────────────────┼──────┤
│ 볼린저밴드                         │      │
├──────────────────────────────────┼──────┤
│ 하단 터치 후 반등                   │ +15  │
│ 하단 터치                          │ +10  │
│ 상단 돌파                          │ -5   │
├──────────────────────────────────┼──────┤
│ 거래량                            │      │
├──────────────────────────────────┼──────┤
│ 2배 이상                          │ +15  │
│ 1.5배 이상                        │ +10  │
│ 1.2배 이상                        │ +5   │
└──────────────────────────────────┴──────┘
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict, Optional


def calculate_score_v1(df: pd.DataFrame) -> Optional[Dict]:
    """
    V1 점수 계산 (종합 기술적 분석)

    Args:
        df: OHLCV 데이터프레임 (최소 60일)

    Returns:
        {
            'score': 최종 점수 (0-100),
            'raw_score': 원점수,
            'signals': 발생한 신호 리스트,
            'indicators': 지표 상세값,
            'patterns': 캔들 패턴
        }
    """
    if df is None or len(df) < 60:
        return None

    result = {
        'score': 0,
        'raw_score': 0,
        'signals': [],
        'indicators': {},
        'patterns': [],
        'version': 'v1'
    }

    try:
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 기본 정보
        result['indicators']['close'] = curr['Close']
        result['indicators']['change_pct'] = ((curr['Close'] - prev['Close']) / prev['Close']) * 100
        result['indicators']['volume'] = curr['Volume']

        raw_score = 0

        # ========== 1. 이동평균선 ==========
        df['SMA_5'] = ta.sma(df['Close'], length=5)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_60'] = ta.sma(df['Close'], length=60)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 정배열 (+15)
        if curr['SMA_5'] > curr['SMA_20'] > curr['SMA_60']:
            raw_score += 15
            result['signals'].append('MA_ALIGNED')

        # 골든크로스 5/20 (+20)
        if prev['SMA_5'] < prev['SMA_20'] and curr['SMA_5'] > curr['SMA_20']:
            raw_score += 20
            result['signals'].append('GOLDEN_CROSS_5_20')

        # 골든크로스 20/60 (+25)
        if prev['SMA_20'] < prev['SMA_60'] and curr['SMA_20'] > curr['SMA_60']:
            raw_score += 25
            result['signals'].append('GOLDEN_CROSS_20_60')

        # 데드크로스 5/20 (-15)
        if prev['SMA_5'] > prev['SMA_20'] and curr['SMA_5'] < curr['SMA_20']:
            raw_score -= 15
            result['signals'].append('DEAD_CROSS_5_20')

        # 역배열 (-10)
        if curr['SMA_5'] < curr['SMA_20'] < curr['SMA_60']:
            raw_score -= 10
            result['signals'].append('MA_REVERSE_ALIGNED')

        # ========== 2. RSI ==========
        df['RSI'] = ta.rsi(df['Close'], length=14)
        rsi = df.iloc[-1]['RSI']
        if pd.notna(rsi):
            result['indicators']['rsi'] = rsi
            if rsi < 30:
                raw_score += 15  # 과매도 = 매수 기회
                result['signals'].append('RSI_OVERSOLD')
            elif 30 <= rsi < 50:
                raw_score += 5
                result['signals'].append('RSI_RECOVERING')
            elif rsi > 70:
                raw_score -= 10
                result['signals'].append('RSI_OVERBOUGHT')

        # ========== 3. MACD ==========
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is not None:
            macd_col = [c for c in macd.columns if 'MACD_' in c and 'MACDh' not in c and 'MACDs' not in c][0]
            signal_col = [c for c in macd.columns if 'MACDs' in c][0]
            hist_col = [c for c in macd.columns if 'MACDh' in c][0]

            curr_macd = macd.iloc[-1][macd_col]
            curr_signal = macd.iloc[-1][signal_col]
            curr_hist = macd.iloc[-1][hist_col]
            prev_hist = macd.iloc[-2][hist_col]

            result['indicators']['macd'] = curr_macd

            # MACD 골든크로스 (+20)
            if macd.iloc[-2][macd_col] < macd.iloc[-2][signal_col] and curr_macd > curr_signal:
                raw_score += 20
                result['signals'].append('MACD_GOLDEN_CROSS')

            # 히스토그램 양전환 (+10)
            if prev_hist < 0 and curr_hist > 0:
                raw_score += 10
                result['signals'].append('MACD_HIST_POSITIVE')
            elif prev_hist < curr_hist and curr_hist < 0:
                raw_score += 5
                result['signals'].append('MACD_HIST_RISING')

        # ========== 4. 볼린저밴드 ==========
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            upper_col = [c for c in bb.columns if c.startswith('BBU')][0]
            lower_col = [c for c in bb.columns if c.startswith('BBL')][0]

            upper = bb.iloc[-1][upper_col]
            lower = bb.iloc[-1][lower_col]

            # 하단 터치 후 반등 (+15)
            if df.iloc[-2]['Close'] <= bb.iloc[-2][lower_col] and curr['Close'] > lower:
                raw_score += 15
                result['signals'].append('BB_LOWER_BOUNCE')
            elif curr['Close'] < lower:
                raw_score += 10
                result['signals'].append('BB_LOWER_TOUCH')

            # 상단 돌파 (-5)
            if curr['Close'] > upper:
                raw_score -= 5
                result['signals'].append('BB_UPPER_BREAK')

        # ========== 5. Stochastic ==========
        stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3)
        if stoch is not None:
            k_col = [c for c in stoch.columns if 'STOCHk' in c][0]
            d_col = [c for c in stoch.columns if 'STOCHd' in c][0]

            curr_k = stoch.iloc[-1][k_col]
            curr_d = stoch.iloc[-1][d_col]
            prev_k = stoch.iloc[-2][k_col]
            prev_d = stoch.iloc[-2][d_col]

            result['indicators']['stoch_k'] = curr_k
            result['indicators']['stoch_d'] = curr_d

            # 과매도 구간 골든크로스 (+20)
            if prev_k < prev_d and curr_k > curr_d and curr_k < 30:
                raw_score += 20
                result['signals'].append('STOCH_GOLDEN_OVERSOLD')
            elif prev_k < prev_d and curr_k > curr_d:
                raw_score += 10
                result['signals'].append('STOCH_GOLDEN_CROSS')

            if curr_k < 20:
                raw_score += 5
                result['signals'].append('STOCH_OVERSOLD')

        # ========== 6. ADX ==========
        adx = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        if adx is not None:
            adx_col = [c for c in adx.columns if c.startswith('ADX')][0]
            dmp_col = [c for c in adx.columns if 'DMP' in c][0]
            dmn_col = [c for c in adx.columns if 'DMN' in c][0]

            curr_adx = adx.iloc[-1][adx_col]
            curr_dmp = adx.iloc[-1][dmp_col]
            curr_dmn = adx.iloc[-1][dmn_col]

            result['indicators']['adx'] = curr_adx

            if curr_adx > 25 and curr_dmp > curr_dmn:
                raw_score += 15
                result['signals'].append('ADX_STRONG_UPTREND')
            elif curr_adx > 20 and curr_dmp > curr_dmn:
                raw_score += 10
                result['signals'].append('ADX_UPTREND')

        # ========== 7. CCI ==========
        cci = ta.cci(df['High'], df['Low'], df['Close'], length=20)
        if cci is not None:
            curr_cci = cci.iloc[-1]
            result['indicators']['cci'] = curr_cci

            if curr_cci < -100:
                raw_score += 10
                result['signals'].append('CCI_OVERSOLD')
            elif curr_cci > 100:
                raw_score -= 5
                result['signals'].append('CCI_OVERBOUGHT')

        # ========== 8. Williams %R ==========
        willr = ta.willr(df['High'], df['Low'], df['Close'], length=14)
        if willr is not None:
            curr_willr = willr.iloc[-1]
            result['indicators']['williams_r'] = curr_willr

            if curr_willr < -80:
                raw_score += 10
                result['signals'].append('WILLR_OVERSOLD')
            elif curr_willr > -20:
                raw_score -= 5
                result['signals'].append('WILLR_OVERBOUGHT')

        # ========== 9. OBV ==========
        obv = ta.obv(df['Close'], df['Volume'])
        if obv is not None:
            df['OBV'] = obv
            df['OBV_SMA'] = ta.sma(obv, length=20)

            curr_obv = df.iloc[-1]['OBV']
            curr_obv_sma = df.iloc[-1]['OBV_SMA']

            if pd.notna(curr_obv_sma) and curr_obv > curr_obv_sma:
                raw_score += 10
                result['signals'].append('OBV_ABOVE_MA')

            obv_5d_ago = df.iloc[-5]['OBV'] if len(df) >= 5 else df.iloc[0]['OBV']
            if curr_obv > obv_5d_ago * 1.05:
                raw_score += 5
                result['signals'].append('OBV_RISING')

        # ========== 10. MFI ==========
        mfi = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
        if mfi is not None:
            curr_mfi = mfi.iloc[-1]
            result['indicators']['mfi'] = curr_mfi

            if curr_mfi < 20:
                raw_score += 15
                result['signals'].append('MFI_OVERSOLD')
            elif curr_mfi < 40:
                raw_score += 5
                result['signals'].append('MFI_LOW')
            elif curr_mfi > 80:
                raw_score -= 10
                result['signals'].append('MFI_OVERBOUGHT')

        # ========== 11. 거래량 ==========
        df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
        vol_ma = df.iloc[-1]['VOL_MA20']
        if pd.notna(vol_ma) and vol_ma > 0:
            vol_ratio = curr['Volume'] / vol_ma
            result['indicators']['volume_ratio'] = vol_ratio

            if vol_ratio >= 2.0:
                raw_score += 15
                result['signals'].append('VOLUME_SURGE')
            elif vol_ratio >= 1.5:
                raw_score += 10
                result['signals'].append('VOLUME_HIGH')
            elif vol_ratio >= 1.2:
                raw_score += 5
                result['signals'].append('VOLUME_ABOVE_AVG')

        # ========== 12. Supertrend ==========
        supertrend = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        if supertrend is not None:
            st_col = [c for c in supertrend.columns if 'SUPERTd' in c][0]
            curr_st = supertrend.iloc[-1][st_col]
            prev_st = supertrend.iloc[-2][st_col]

            if prev_st == -1 and curr_st == 1:
                raw_score += 20
                result['signals'].append('SUPERTREND_BUY')
            elif curr_st == 1:
                raw_score += 5
                result['signals'].append('SUPERTREND_UPTREND')

        # ========== 13. PSAR ==========
        psar = ta.psar(df['High'], df['Low'], df['Close'])
        if psar is not None:
            psar_long_col = [c for c in psar.columns if 'PSARl' in c]
            if psar_long_col:
                curr_psar_long = psar.iloc[-1][psar_long_col[0]]
                prev_psar_long = psar.iloc[-2][psar_long_col[0]]

                if pd.isna(prev_psar_long) and pd.notna(curr_psar_long):
                    raw_score += 15
                    result['signals'].append('PSAR_BUY_SIGNAL')

        # ========== 14. ROC ==========
        roc = ta.roc(df['Close'], length=10)
        if roc is not None:
            curr_roc = roc.iloc[-1]
            prev_roc = roc.iloc[-2]

            result['indicators']['roc'] = curr_roc

            if prev_roc < 0 and curr_roc > 0:
                raw_score += 10
                result['signals'].append('ROC_POSITIVE_CROSS')
            elif curr_roc > 5:
                raw_score += 5
                result['signals'].append('ROC_STRONG_MOMENTUM')

        # ========== 15. 일목균형표 ==========
        ichimoku = ta.ichimoku(df['High'], df['Low'], df['Close'])
        if ichimoku is not None and len(ichimoku) == 2:
            ich_df = ichimoku[0]
            tenkan_col = [c for c in ich_df.columns if 'ITS' in c]
            kijun_col = [c for c in ich_df.columns if 'IKS' in c]
            span_a_col = [c for c in ich_df.columns if 'ISA' in c]
            span_b_col = [c for c in ich_df.columns if 'ISB' in c]

            if tenkan_col and kijun_col:
                curr_tenkan = ich_df.iloc[-1][tenkan_col[0]]
                curr_kijun = ich_df.iloc[-1][kijun_col[0]]
                prev_tenkan = ich_df.iloc[-2][tenkan_col[0]]
                prev_kijun = ich_df.iloc[-2][kijun_col[0]]

                if prev_tenkan < prev_kijun and curr_tenkan > curr_kijun:
                    raw_score += 15
                    result['signals'].append('ICHIMOKU_GOLDEN_CROSS')

                if span_a_col and span_b_col:
                    span_a = ich_df.iloc[-1][span_a_col[0]]
                    span_b = ich_df.iloc[-1][span_b_col[0]]
                    if pd.notna(span_a) and pd.notna(span_b):
                        cloud_top = max(span_a, span_b)
                        if curr['Close'] > cloud_top:
                            raw_score += 10
                            result['signals'].append('ICHIMOKU_ABOVE_CLOUD')

        # ========== 16. CMF ==========
        cmf = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'], length=20)
        if cmf is not None:
            curr_cmf = cmf.iloc[-1]
            result['indicators']['cmf'] = curr_cmf

            if curr_cmf > 0.2:
                raw_score += 10
                result['signals'].append('CMF_STRONG_INFLOW')
            elif curr_cmf > 0:
                raw_score += 5
                result['signals'].append('CMF_POSITIVE')
            elif curr_cmf < -0.2:
                raw_score -= 10
                result['signals'].append('CMF_STRONG_OUTFLOW')

        # ========== 17. 52주 고/저가 ==========
        if len(df) >= 252:
            high_52w = df['High'].tail(252).max()
            low_52w = df['Low'].tail(252).min()
            result['indicators']['high_52w'] = float(high_52w)
            result['indicators']['low_52w'] = float(low_52w)

            if curr['Close'] >= high_52w * 0.98:
                raw_score += 15
                result['signals'].append('NEW_HIGH_52W')
                if curr['Close'] >= high_52w:
                    raw_score += 5
                    result['signals'].append('BREAKOUT_52W_HIGH')

            if curr['Close'] <= low_52w * 1.02:
                raw_score -= 10
                result['signals'].append('NEW_LOW_52W')

        # ========== 18. 캔들 패턴 ==========
        try:
            hammer = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='hammer')
            if hammer is not None and len(hammer) > 0 and hammer.iloc[-1].values[0] != 0:
                raw_score += 10
                result['patterns'].append('HAMMER')

            engulfing = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='engulfing')
            if engulfing is not None and len(engulfing) > 0:
                if engulfing.iloc[-1].values[0] > 0:
                    raw_score += 15
                    result['patterns'].append('BULLISH_ENGULFING')
                elif engulfing.iloc[-1].values[0] < 0:
                    raw_score -= 10
                    result['patterns'].append('BEARISH_ENGULFING')

            morning_star = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='morningstar')
            if morning_star is not None and len(morning_star) > 0 and morning_star.iloc[-1].values[0] != 0:
                raw_score += 20
                result['patterns'].append('MORNING_STAR')

            evening_star = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='eveningstar')
            if evening_star is not None and len(evening_star) > 0 and evening_star.iloc[-1].values[0] != 0:
                raw_score -= 15
                result['patterns'].append('EVENING_STAR')
        except:
            pass

        # ========== 점수 스케일링 ==========
        result['raw_score'] = raw_score

        if raw_score <= 60:
            scaled_score = int(raw_score * 0.9)
        elif raw_score <= 100:
            scaled_score = 54 + int((raw_score - 60) * 0.65)
        else:
            scaled_score = 80 + int((raw_score - 100) * 0.4)

        result['score'] = max(0, min(100, scaled_score))

        return result

    except Exception as e:
        print(f"V1 점수 계산 오류: {e}")
        return None


# 테스트
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    df = fdr.DataReader('005930', start_date)

    result = calculate_score_v1(df)
    if result:
        print(f"=== V1 점수 계산 결과 ===")
        print(f"원점수: {result['raw_score']}")
        print(f"최종점수: {result['score']}")
        print(f"신호: {result['signals']}")
        print(f"패턴: {result['patterns']}")
