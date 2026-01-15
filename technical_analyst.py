import FinanceDataReader as fdr
import pandas_ta as ta
import pandas as pd
from datetime import datetime, timedelta

class TechnicalAnalyst:
    """
    확장된 기술적 분석기
    - 기본 지표: SMA, RSI, 볼린저밴드
    - 추세/모멘텀: MACD, ADX, Stochastic, CCI, Williams %R, ROC
    - 거래량: OBV, MFI, VWAP, CMF
    - 고급 지표: Supertrend, Ichimoku, PSAR, ATR
    - 캔들 패턴: Hammer, Engulfing, Doji, Morning/Evening Star
    """

    def __init__(self):
        pass

    def get_ohlcv(self, stock_code, days=365):
        """주가 데이터 수집"""
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = fdr.DataReader(stock_code, start_date)
        return df

    def analyze(self, df):
        """기본 분석 (기존 호환성 유지)"""
        if df is None or len(df) < 60:
            return 0, ["데이터 부족"], {}

        score = 0
        reasons = []
        details = {}

        # 1. 이동평균선
        df['SMA_5'] = ta.sma(df['Close'], length=5)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_60'] = ta.sma(df['Close'], length=60)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 전일비 계산
        diff = curr['Close'] - prev['Close']
        pct = (diff / prev['Close']) * 100

        details['현재가'] = f"{int(curr['Close']):,}원"
        details['전일비'] = int(diff)
        details['등락률'] = float(pct)

        if curr['SMA_5'] > curr['SMA_20'] > curr['SMA_60']:
            score += 20
            reasons.append("✅ 이평선 정배열 (강한 상승 추세)")

        if prev['SMA_5'] < prev['SMA_20'] and curr['SMA_5'] > curr['SMA_20']:
            score += 15
            reasons.append("✅ 골든크로스 발생 (단기 매수 신호)")

        # 2. RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        curr_rsi = df.iloc[-1]['RSI']
        if pd.isna(curr_rsi): curr_rsi = 50
        details['RSI'] = f"{curr_rsi:.1f}"

        if curr_rsi < 30:
            score += 15
            reasons.append("✅ RSI 과매도 구간 (반등 기대)")
        elif curr_rsi > 70:
            score -= 10
            reasons.append("⚠️ RSI 과매수 구간 (조정 주의)")

        # 3. 볼린저 밴드
        bb = ta.bbands(df['Close'], length=20, std=2)
        upper_col = [c for c in bb.columns if c.startswith('BBU')][0]
        lower_col = [c for c in bb.columns if c.startswith('BBL')][0]

        upper_band = bb.iloc[-1][upper_col]
        lower_band = bb.iloc[-1][lower_col]

        if curr['Close'] > upper_band:
            reasons.append("⚠️ 볼린저 밴드 상단 돌파 (단기 과열)")
        elif curr['Close'] < lower_band:
            score += 10
            reasons.append("✅ 볼린저 밴드 하단 터치 (저점 매수 기회)")

        return score, reasons, details

    def analyze_full(self, df):
        """
        전체 기술적 분석 (스크리닝용)
        모든 지표를 계산하고 종합 점수 산출
        """
        if df is None or len(df) < 60:
            return None

        result = {
            'score': 0,
            'signals': [],
            'indicators': {},
            'patterns': []
        }

        try:
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # 기본 정보
            result['indicators']['close'] = curr['Close']
            result['indicators']['change_pct'] = ((curr['Close'] - prev['Close']) / prev['Close']) * 100
            result['indicators']['volume'] = curr['Volume']

            # ========== 1. 이동평균선 분석 ==========
            df['SMA_5'] = ta.sma(df['Close'], length=5)
            df['SMA_20'] = ta.sma(df['Close'], length=20)
            df['SMA_60'] = ta.sma(df['Close'], length=60)
            df['SMA_120'] = ta.sma(df['Close'], length=120)
            df['EMA_12'] = ta.ema(df['Close'], length=12)
            df['EMA_26'] = ta.ema(df['Close'], length=26)

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # 정배열 체크
            if curr['SMA_5'] > curr['SMA_20'] > curr['SMA_60']:
                result['score'] += 15
                result['signals'].append('MA_ALIGNED')

            # 골든크로스 (5/20)
            if prev['SMA_5'] < prev['SMA_20'] and curr['SMA_5'] > curr['SMA_20']:
                result['score'] += 20
                result['signals'].append('GOLDEN_CROSS_5_20')

            # 골든크로스 (20/60)
            if prev['SMA_20'] < prev['SMA_60'] and curr['SMA_20'] > curr['SMA_60']:
                result['score'] += 25
                result['signals'].append('GOLDEN_CROSS_20_60')

            # 데드크로스 감점
            if prev['SMA_5'] > prev['SMA_20'] and curr['SMA_5'] < curr['SMA_20']:
                result['score'] -= 15
                result['signals'].append('DEAD_CROSS_5_20')

            # ========== 2. RSI ==========
            df['RSI'] = ta.rsi(df['Close'], length=14)
            rsi = df.iloc[-1]['RSI']
            if pd.notna(rsi):
                result['indicators']['rsi'] = rsi
                if rsi < 30:
                    result['score'] += 15
                    result['signals'].append('RSI_OVERSOLD')
                elif rsi < 50 and rsi > 30:
                    result['score'] += 5
                    result['signals'].append('RSI_RECOVERING')
                elif rsi > 70:
                    result['score'] -= 10
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
                result['indicators']['macd_signal'] = curr_signal
                result['indicators']['macd_hist'] = curr_hist

                # MACD 골든크로스
                if macd.iloc[-2][macd_col] < macd.iloc[-2][signal_col] and curr_macd > curr_signal:
                    result['score'] += 20
                    result['signals'].append('MACD_GOLDEN_CROSS')

                # 히스토그램 상승 전환
                if prev_hist < 0 and curr_hist > 0:
                    result['score'] += 10
                    result['signals'].append('MACD_HIST_POSITIVE')
                elif prev_hist < curr_hist and curr_hist < 0:
                    result['score'] += 5
                    result['signals'].append('MACD_HIST_RISING')

            # ========== 4. 볼린저 밴드 ==========
            bb = ta.bbands(df['Close'], length=20, std=2)
            if bb is not None:
                upper_col = [c for c in bb.columns if c.startswith('BBU')][0]
                lower_col = [c for c in bb.columns if c.startswith('BBL')][0]
                mid_col = [c for c in bb.columns if c.startswith('BBM')][0]

                upper = bb.iloc[-1][upper_col]
                lower = bb.iloc[-1][lower_col]
                mid = bb.iloc[-1][mid_col]

                result['indicators']['bb_upper'] = upper
                result['indicators']['bb_lower'] = lower
                result['indicators']['bb_mid'] = mid

                # BB 하단 터치 후 반등
                if df.iloc[-2]['Close'] <= bb.iloc[-2][lower_col] and curr['Close'] > lower:
                    result['score'] += 15
                    result['signals'].append('BB_LOWER_BOUNCE')
                elif curr['Close'] < lower:
                    result['score'] += 10
                    result['signals'].append('BB_LOWER_TOUCH')

                # BB 상단 돌파 (과열)
                if curr['Close'] > upper:
                    result['score'] -= 5
                    result['signals'].append('BB_UPPER_BREAK')

            # ========== 5. Stochastic Oscillator ==========
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

                # 과매도 구간에서 골든크로스
                if prev_k < prev_d and curr_k > curr_d and curr_k < 30:
                    result['score'] += 20
                    result['signals'].append('STOCH_GOLDEN_OVERSOLD')
                elif prev_k < prev_d and curr_k > curr_d:
                    result['score'] += 10
                    result['signals'].append('STOCH_GOLDEN_CROSS')

                if curr_k < 20:
                    result['score'] += 5
                    result['signals'].append('STOCH_OVERSOLD')

            # ========== 6. ADX (추세 강도) ==========
            adx = ta.adx(df['High'], df['Low'], df['Close'], length=14)
            if adx is not None:
                adx_col = [c for c in adx.columns if c.startswith('ADX')][0]
                dmp_col = [c for c in adx.columns if 'DMP' in c][0]
                dmn_col = [c for c in adx.columns if 'DMN' in c][0]

                curr_adx = adx.iloc[-1][adx_col]
                curr_dmp = adx.iloc[-1][dmp_col]
                curr_dmn = adx.iloc[-1][dmn_col]

                result['indicators']['adx'] = curr_adx
                result['indicators']['di_plus'] = curr_dmp
                result['indicators']['di_minus'] = curr_dmn

                # 강한 상승 추세
                if curr_adx > 25 and curr_dmp > curr_dmn:
                    result['score'] += 15
                    result['signals'].append('ADX_STRONG_UPTREND')
                elif curr_adx > 20 and curr_dmp > curr_dmn:
                    result['score'] += 10
                    result['signals'].append('ADX_UPTREND')

            # ========== 7. CCI (Commodity Channel Index) ==========
            cci = ta.cci(df['High'], df['Low'], df['Close'], length=20)
            if cci is not None:
                curr_cci = cci.iloc[-1]
                result['indicators']['cci'] = curr_cci

                if curr_cci < -100:
                    result['score'] += 10
                    result['signals'].append('CCI_OVERSOLD')
                elif curr_cci > 100:
                    result['score'] -= 5
                    result['signals'].append('CCI_OVERBOUGHT')

            # ========== 8. Williams %R ==========
            willr = ta.willr(df['High'], df['Low'], df['Close'], length=14)
            if willr is not None:
                curr_willr = willr.iloc[-1]
                result['indicators']['williams_r'] = curr_willr

                if curr_willr < -80:
                    result['score'] += 10
                    result['signals'].append('WILLR_OVERSOLD')
                elif curr_willr > -20:
                    result['score'] -= 5
                    result['signals'].append('WILLR_OVERBOUGHT')

            # ========== 9. OBV (On Balance Volume) ==========
            obv = ta.obv(df['Close'], df['Volume'])
            if obv is not None:
                df['OBV'] = obv
                df['OBV_SMA'] = ta.sma(obv, length=20)

                curr_obv = df.iloc[-1]['OBV']
                curr_obv_sma = df.iloc[-1]['OBV_SMA']

                result['indicators']['obv'] = curr_obv

                # OBV가 이동평균 위에 있고 상승 중
                if pd.notna(curr_obv_sma):
                    if curr_obv > curr_obv_sma:
                        result['score'] += 10
                        result['signals'].append('OBV_ABOVE_MA')

                    # OBV 상승 추세 (최근 5일)
                    obv_5d_ago = df.iloc[-5]['OBV'] if len(df) >= 5 else df.iloc[0]['OBV']
                    if curr_obv > obv_5d_ago * 1.05:
                        result['score'] += 5
                        result['signals'].append('OBV_RISING')

            # ========== 10. MFI (Money Flow Index) ==========
            mfi = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
            if mfi is not None:
                curr_mfi = mfi.iloc[-1]
                result['indicators']['mfi'] = curr_mfi

                if curr_mfi < 20:
                    result['score'] += 15
                    result['signals'].append('MFI_OVERSOLD')
                elif curr_mfi < 40:
                    result['score'] += 5
                    result['signals'].append('MFI_LOW')
                elif curr_mfi > 80:
                    result['score'] -= 10
                    result['signals'].append('MFI_OVERBOUGHT')

            # ========== 11. ATR (Average True Range) - 변동성 ==========
            atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            if atr is not None:
                curr_atr = atr.iloc[-1]
                result['indicators']['atr'] = curr_atr
                result['indicators']['atr_pct'] = (curr_atr / curr['Close']) * 100

            # ========== 12. 거래량 분석 ==========
            df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
            vol_ratio = curr['Volume'] / df.iloc[-1]['VOL_MA20'] if df.iloc[-1]['VOL_MA20'] > 0 else 1

            result['indicators']['volume_ratio'] = vol_ratio

            # 거래량 급증 (2배 이상)
            if vol_ratio >= 2.0:
                result['score'] += 15
                result['signals'].append('VOLUME_SURGE')
            elif vol_ratio >= 1.5:
                result['score'] += 10
                result['signals'].append('VOLUME_HIGH')
            elif vol_ratio >= 1.2:
                result['score'] += 5
                result['signals'].append('VOLUME_ABOVE_AVG')

            # ========== 13. Supertrend ==========
            supertrend = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
            if supertrend is not None:
                st_col = [c for c in supertrend.columns if 'SUPERTd' in c][0]
                curr_st = supertrend.iloc[-1][st_col]
                prev_st = supertrend.iloc[-2][st_col]

                result['indicators']['supertrend'] = curr_st

                # 상승 추세 전환
                if prev_st == -1 and curr_st == 1:
                    result['score'] += 20
                    result['signals'].append('SUPERTREND_BUY')
                elif curr_st == 1:
                    result['score'] += 5
                    result['signals'].append('SUPERTREND_UPTREND')

            # ========== 14. PSAR (Parabolic SAR) ==========
            psar = ta.psar(df['High'], df['Low'], df['Close'])
            if psar is not None:
                psar_long_col = [c for c in psar.columns if 'PSARl' in c]
                psar_short_col = [c for c in psar.columns if 'PSARs' in c]

                if psar_long_col:
                    curr_psar_long = psar.iloc[-1][psar_long_col[0]]
                    prev_psar_long = psar.iloc[-2][psar_long_col[0]]

                    # PSAR 매수 전환 (NaN에서 값으로)
                    if pd.isna(prev_psar_long) and pd.notna(curr_psar_long):
                        result['score'] += 15
                        result['signals'].append('PSAR_BUY_SIGNAL')
                    elif pd.notna(curr_psar_long):
                        result['signals'].append('PSAR_UPTREND')

            # ========== 15. ROC (Rate of Change) ==========
            roc = ta.roc(df['Close'], length=10)
            if roc is not None:
                curr_roc = roc.iloc[-1]
                prev_roc = roc.iloc[-2]

                result['indicators']['roc'] = curr_roc

                # ROC 0선 상향 돌파
                if prev_roc < 0 and curr_roc > 0:
                    result['score'] += 10
                    result['signals'].append('ROC_POSITIVE_CROSS')
                elif curr_roc > 5:
                    result['score'] += 5
                    result['signals'].append('ROC_STRONG_MOMENTUM')

            # ========== 16. Ichimoku Cloud (일목균형표) ==========
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

                    result['indicators']['ichimoku_tenkan'] = curr_tenkan
                    result['indicators']['ichimoku_kijun'] = curr_kijun

                    # 전환선/기준선 골든크로스
                    if prev_tenkan < prev_kijun and curr_tenkan > curr_kijun:
                        result['score'] += 15
                        result['signals'].append('ICHIMOKU_GOLDEN_CROSS')

                    # 가격이 구름대 위
                    if span_a_col and span_b_col:
                        span_a = ich_df.iloc[-1][span_a_col[0]]
                        span_b = ich_df.iloc[-1][span_b_col[0]]
                        cloud_top = max(span_a, span_b) if pd.notna(span_a) and pd.notna(span_b) else None

                        if cloud_top and curr['Close'] > cloud_top:
                            result['score'] += 10
                            result['signals'].append('ICHIMOKU_ABOVE_CLOUD')

            # ========== 17. CMF (Chaikin Money Flow) ==========
            cmf = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'], length=20)
            if cmf is not None:
                curr_cmf = cmf.iloc[-1]
                result['indicators']['cmf'] = curr_cmf

                if curr_cmf > 0.2:
                    result['score'] += 10
                    result['signals'].append('CMF_STRONG_INFLOW')
                elif curr_cmf > 0:
                    result['score'] += 5
                    result['signals'].append('CMF_POSITIVE')
                elif curr_cmf < -0.2:
                    result['score'] -= 10
                    result['signals'].append('CMF_STRONG_OUTFLOW')

            # ========== 18. 캔들 패턴 분석 ==========
            self._analyze_candle_patterns(df, result)

            # 최종 점수 조정
            # 점수 구간별 차등 스케일링:
            # - 낮은 점수(0-60)는 비교적 그대로 유지
            # - 높은 점수(60+)는 더 강하게 압축
            # 이를 통해 80점 이상은 정말 강한 신호, 90점 이상은 매우 드문 경우
            raw_score = result['score']
            if raw_score <= 60:
                scaled_score = int(raw_score * 0.9)  # 0-60 -> 0-54
            elif raw_score <= 100:
                scaled_score = 54 + int((raw_score - 60) * 0.65)  # 60-100 -> 54-80
            else:
                scaled_score = 80 + int((raw_score - 100) * 0.4)  # 100+ -> 80-100
            result['score'] = max(0, min(100, scaled_score))

            return result

        except Exception as e:
            print(f"분석 오류: {e}")
            return None

    def _analyze_candle_patterns(self, df, result):
        """
        캔들스틱 패턴 분석
        주의: TA-Lib가 설치되어 있어야 작동합니다.
        TA-Lib 없이도 다른 지표들은 정상 작동합니다.
        """
        try:
            import io
            import sys

            # TA-Lib 경고 메시지 억제
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            try:
                # Hammer (망치형)
                hammer = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='hammer')
                if hammer is not None and len(hammer) > 0 and hammer.iloc[-1].values[0] != 0:
                    result['score'] += 10
                    result['patterns'].append('HAMMER')

                # Inverted Hammer (역망치형)
                inv_hammer = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='invertedhammer')
                if inv_hammer is not None and len(inv_hammer) > 0 and inv_hammer.iloc[-1].values[0] != 0:
                    result['score'] += 8
                    result['patterns'].append('INVERTED_HAMMER')

                # Bullish Engulfing (상승 장악형)
                engulfing = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='engulfing')
                if engulfing is not None and len(engulfing) > 0:
                    if engulfing.iloc[-1].values[0] > 0:
                        result['score'] += 15
                        result['patterns'].append('BULLISH_ENGULFING')
                    elif engulfing.iloc[-1].values[0] < 0:
                        result['score'] -= 10
                        result['patterns'].append('BEARISH_ENGULFING')

                # Doji (도지)
                doji = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='doji')
                if doji is not None and len(doji) > 0 and doji.iloc[-1].values[0] != 0:
                    result['patterns'].append('DOJI')

                # Morning Star (샛별형)
                morning_star = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='morningstar')
                if morning_star is not None and len(morning_star) > 0 and morning_star.iloc[-1].values[0] != 0:
                    result['score'] += 20
                    result['patterns'].append('MORNING_STAR')

                # Evening Star (저녁별형)
                evening_star = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='eveningstar')
                if evening_star is not None and len(evening_star) > 0 and evening_star.iloc[-1].values[0] != 0:
                    result['score'] -= 15
                    result['patterns'].append('EVENING_STAR')

            finally:
                sys.stdout = old_stdout

        except Exception:
            pass  # TA-Lib 미설치 또는 패턴 분석 실패시 조용히 무시

    def calculate_support_resistance(self, df):
        """
        지지선/저항선 계산 (Pivot Point 기반)
        Returns: dict with support/resistance levels
        """
        if df is None or len(df) < 5:
            return None

        try:
            # 최근 거래일 기준
            high = df['High'].iloc[-1]
            low = df['Low'].iloc[-1]
            close = df['Close'].iloc[-1]

            # Pivot Point 계산
            pivot = (high + low + close) / 3

            # 지지선/저항선 계산
            r1 = 2 * pivot - low       # 1차 저항선
            r2 = pivot + (high - low)  # 2차 저항선
            s1 = 2 * pivot - high      # 1차 지지선
            s2 = pivot - (high - low)  # 2차 지지선

            # 추가: 최근 20일 고점/저점 기반 레벨
            recent_high = df['High'].tail(20).max()
            recent_low = df['Low'].tail(20).min()

            return {
                'pivot': round(pivot, 0),
                'resistance_1': round(r1, 0),
                'resistance_2': round(r2, 0),
                'support_1': round(s1, 0),
                'support_2': round(s2, 0),
                'recent_high': round(recent_high, 0),
                'recent_low': round(recent_low, 0)
            }

        except Exception as e:
            print(f"지지/저항선 계산 오류: {e}")
            return None

    def calculate_probability_confidence(self, score, signals):
        """
        상승확률 및 신뢰도 계산
        Args:
            score: 기술적 분석 점수 (0-100)
            signals: 신호 리스트
        Returns: dict with probability and confidence
        """
        # 상승형 신호
        BULLISH_SIGNALS = {
            'MA_ALIGNED', 'GOLDEN_CROSS_5_20', 'GOLDEN_CROSS_20_60',
            'RSI_OVERSOLD', 'RSI_RECOVERING', 'MACD_GOLDEN_CROSS',
            'MACD_HIST_POSITIVE', 'MACD_HIST_RISING', 'BB_LOWER_BOUNCE',
            'BB_LOWER_TOUCH', 'STOCH_GOLDEN_OVERSOLD', 'STOCH_GOLDEN_CROSS',
            'STOCH_OVERSOLD', 'ADX_STRONG_UPTREND', 'ADX_UPTREND',
            'CCI_OVERSOLD', 'WILLR_OVERSOLD', 'OBV_ABOVE_MA', 'OBV_RISING',
            'MFI_OVERSOLD', 'MFI_LOW', 'VOLUME_SURGE', 'VOLUME_HIGH',
            'VOLUME_ABOVE_AVG', 'SUPERTREND_BUY', 'SUPERTREND_UPTREND',
            'PSAR_BUY_SIGNAL', 'PSAR_UPTREND', 'ROC_POSITIVE_CROSS',
            'ROC_STRONG_MOMENTUM', 'ICHIMOKU_GOLDEN_CROSS', 'ICHIMOKU_ABOVE_CLOUD',
            'CMF_STRONG_INFLOW', 'CMF_POSITIVE', 'HAMMER', 'INVERTED_HAMMER',
            'BULLISH_ENGULFING', 'MORNING_STAR'
        }

        # 하락형 신호
        BEARISH_SIGNALS = {
            'DEAD_CROSS_5_20', 'RSI_OVERBOUGHT', 'BB_UPPER_BREAK',
            'CCI_OVERBOUGHT', 'WILLR_OVERBOUGHT', 'MFI_OVERBOUGHT',
            'CMF_STRONG_OUTFLOW', 'BEARISH_ENGULFING', 'EVENING_STAR'
        }

        # 상승확률: 점수 기반 (30-70% 범위 - 보수적)
        probability = min(70, max(30, score * 0.4 + 30))

        # 신뢰도: 신호 일관성 기반
        positive_count = sum(1 for s in signals if s in BULLISH_SIGNALS)
        negative_count = sum(1 for s in signals if s in BEARISH_SIGNALS)
        total_count = len(signals) if signals else 1

        # 일관성 = 같은 방향 신호가 많을수록 높음
        consistency = abs(positive_count - negative_count) / max(total_count, 1)
        signal_strength = min(total_count / 5, 1.0)  # 5개 이상이면 만점

        # 신뢰도 계산 (30-80% 범위 - 보수적)
        confidence = min(80, max(30, 30 + consistency * 30 + signal_strength * 20))

        return {
            'probability': round(probability, 1),
            'confidence': round(confidence, 1),
            'bullish_signals': positive_count,
            'bearish_signals': negative_count
        }

    def get_quick_score(self, df):
        """빠른 스크리닝용 간소화된 점수 (속도 우선)
        Returns: dict with score, signals, indicators, close, volume, change_pct
        """
        if df is None or len(df) < 60:
            return None

        try:
            score = 0
            signals = []
            indicators = {}
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # 이동평균
            sma5 = ta.sma(df['Close'], length=5).iloc[-1]
            sma20 = ta.sma(df['Close'], length=20).iloc[-1]
            sma60 = ta.sma(df['Close'], length=60).iloc[-1]

            if sma5 > sma20 > sma60:
                score += 15
                signals.append('MA_ALIGNED')

            # 골든크로스 체크 (5/20)
            prev_sma5 = ta.sma(df['Close'], length=5).iloc[-2]
            prev_sma20 = ta.sma(df['Close'], length=20).iloc[-2]
            if prev_sma5 < prev_sma20 and sma5 > sma20:
                score += 15
                signals.append('GOLDEN_CROSS_5_20')

            # RSI
            rsi_val = ta.rsi(df['Close'], length=14).iloc[-1]
            if pd.notna(rsi_val):
                indicators['rsi'] = float(rsi_val)
                if rsi_val < 30:
                    score += 15
                    signals.append('RSI_OVERSOLD')
                elif rsi_val < 50:
                    score += 5
                elif rsi_val > 70:
                    score -= 10
                    signals.append('RSI_OVERBOUGHT')

            # 거래량
            vol_ma = ta.sma(df['Volume'], length=20).iloc[-1]
            vol_ratio = 1.0
            if vol_ma > 0:
                vol_ratio = curr['Volume'] / vol_ma
                indicators['volume_ratio'] = float(vol_ratio)
                if vol_ratio >= 2:
                    score += 15
                    signals.append('VOLUME_SURGE')
                elif vol_ratio >= 1.5:
                    score += 10
                    signals.append('VOLUME_HIGH')

            # MACD
            macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
            if macd is not None:
                hist_col = [c for c in macd.columns if 'MACDh' in c][0]
                macd_col = [c for c in macd.columns if c.startswith('MACD_')][0]
                signal_col = [c for c in macd.columns if 'MACDs' in c][0]
                curr_macd = macd.iloc[-1][macd_col]
                prev_macd = macd.iloc[-2][macd_col]
                curr_signal = macd.iloc[-1][signal_col]
                prev_signal = macd.iloc[-2][signal_col]
                curr_hist = macd.iloc[-1][hist_col]
                prev_hist = macd.iloc[-2][hist_col]
                indicators['macd'] = float(curr_macd)

                # MACD 골든크로스
                if prev_macd < prev_signal and curr_macd > curr_signal:
                    score += 20
                    signals.append('MACD_GOLDEN_CROSS')
                elif prev_hist < 0 and curr_hist > 0:
                    score += 15
                    signals.append('MACD_HIST_POSITIVE')
                elif curr_hist > prev_hist:
                    score += 5

            # 기본 지표 저장
            indicators['close'] = float(curr['Close'])
            indicators['volume'] = float(curr['Volume'])
            indicators['change_pct'] = ((curr['Close'] - prev['Close']) / prev['Close']) * 100

            # Quick 모드는 4개 지표만 사용하므로 점수 부스트 (최대 60 → 최대 80)
            # 점수에 1.33 배수를 적용하여 full 모드와 비슷한 범위로 조정
            boosted_score = int(score * 1.33)
            final_score = max(0, min(100, boosted_score))

            return {
                'score': final_score,
                'signals': signals,
                'indicators': indicators,
                'close': curr['Close'],
                'volume': curr['Volume'],
                'change_pct': indicators['change_pct']
            }

        except Exception:
            return None
