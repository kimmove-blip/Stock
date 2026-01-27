"""
V4 Strategy - Hybrid Sniper (하이브리드 스나이퍼)

고급 기술적 분석 기반 정밀 매매 전략

특징:
1. VCP 패턴 감지 (Volatility Contraction Pattern)
2. OBV 다이버전스 감지 (세력 축적 탐지)
3. Stochastic RSI (과열/과매도 정밀 판단)
4. ATR 기반 동적 손절 (변동성 연동)
5. 분할 매도 (Scale-out)
6. 본절 스탑 (Breakeven Stop)
7. 3분봉 확인 (장중 정밀 진입) - 별도 함수

점수 체계 (100점 만점):
- 추세 (25점): 정배열 +5, 20일선 기울기 +15, 구름대 위 +5
- 패턴 (25점): VCP +15, OBV 다이버전스 +10
- 모멘텀 (25점): RSI 60~75 +10, StochRSI +10, 60일 신고가 +5
- 수급 (25점): 거래량 급증 +15, 거래대금 +10

매수 기준: 85점 이상 (강력 매수)
매도 기준: ATR 기반 동적 손절 + 분할 매도
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime
from typing import Dict, Optional, List, Tuple


class V4Strategy:
    """V4 전략 - Hybrid Sniper (고급 기술 분석)"""

    VERSION = "v4"
    NAME = "V4 Hybrid Sniper"
    DESCRIPTION = "VCP + OBV 다이버전스 + ATR 손절 + 분할매도"

    # 매매 기준
    BUY_THRESHOLD = 85          # 강력 매수 기준
    BUY_THRESHOLD_MODERATE = 75  # 일반 매수 기준

    # 분할 매도 설정
    SCALE_OUT_1 = 0.10          # +10%에서 1/3 매도
    SCALE_OUT_2 = 0.20          # +20%에서 1/3 매도
    SCALE_OUT_3_TRAIL = True    # 나머지는 트레일링 스탑

    # ATR 기반 손절 배수
    ATR_STOP_MULTIPLIER = 2.0   # 진입가 - 2*ATR

    # 본절 스탑 활성화 기준
    BREAKEVEN_TRIGGER_PCT = 0.05  # +5% 도달 시 본절 스탑 활성화

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
            'patterns': [],
            'analysis_type': 'v4_hybrid_sniper'
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

            # ========== 이동평균선 계산 ==========
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
                result['action'] = 'AVOID'
                result['reason'] = '역배열 (매수 금지)'
                result['strategy_version'] = self.VERSION
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

                    if sma20_slope >= 3.0:
                        trend_score += 15
                        result['signals'].append('SLOPE_VERY_STEEP')
                    elif sma20_slope >= 1.5:
                        trend_score += 10
                        result['signals'].append('SLOPE_STEEP')
                    elif sma20_slope >= 0.5:
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

            trend_score = min(25, trend_score)
            result['indicators']['trend_score'] = trend_score

            # ========== 2. 패턴 그룹 (최대 25점) ==========
            pattern_score = 0

            # VCP 패턴 감지
            vcp_result = self._detect_vcp_pattern(df)
            if vcp_result['detected']:
                pattern_score += 15
                result['signals'].append('VCP_PATTERN')
                result['patterns'].append('VCP')
                result['indicators']['vcp_contraction'] = vcp_result['contraction_pct']

            # OBV 다이버전스 감지
            obv_div = self._detect_obv_divergence(df)
            if obv_div['bullish_divergence']:
                pattern_score += 10
                result['signals'].append('OBV_BULLISH_DIV')
                result['patterns'].append('OBV_DIV')
                result['indicators']['obv_divergence_days'] = obv_div['days']

            pattern_score = min(25, pattern_score)
            result['indicators']['pattern_score'] = pattern_score

            # ========== 3. 모멘텀 그룹 (최대 25점) ==========
            momentum_score = 0

            # RSI
            df['RSI'] = ta.rsi(df['Close'], length=14)
            rsi = df.iloc[-1]['RSI']

            if pd.notna(rsi):
                result['indicators']['rsi'] = rsi

                if 60 <= rsi <= 75:
                    momentum_score += 10
                    result['signals'].append('RSI_SWEET_SPOT')
                elif 50 <= rsi < 60:
                    momentum_score += 5
                    result['signals'].append('RSI_HEALTHY')
                elif rsi > 85:
                    momentum_score -= 5
                    result['signals'].append('RSI_EXTREME')

            # Stochastic RSI
            stoch_rsi = self._calculate_stoch_rsi(df)
            if stoch_rsi is not None:
                result['indicators']['stoch_rsi_k'] = stoch_rsi['k']
                result['indicators']['stoch_rsi_d'] = stoch_rsi['d']

                # StochRSI 골든크로스 (20 이하에서)
                if stoch_rsi['golden_cross'] and stoch_rsi['k'] < 30:
                    momentum_score += 10
                    result['signals'].append('STOCH_RSI_GOLDEN')
                elif stoch_rsi['k'] > stoch_rsi['d'] and stoch_rsi['k'] < 80:
                    momentum_score += 5
                    result['signals'].append('STOCH_RSI_BULLISH')

            # 60일 신고가 돌파
            high_60d = df['High'].tail(60).max()
            result['indicators']['high_60d'] = high_60d
            result['indicators']['high_60d_pct'] = (curr['Close'] / high_60d - 1) * 100

            if curr['Close'] >= high_60d:
                momentum_score += 5
                result['signals'].append('BREAKOUT_60D')

            momentum_score = min(25, max(-10, momentum_score))
            result['indicators']['momentum_score'] = momentum_score

            # ========== 4. 수급 그룹 (최대 25점) ==========
            supply_score = 0

            # 거래량 분석
            df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
            vol_ma = df.iloc[-1]['VOL_MA20']

            if pd.notna(vol_ma) and vol_ma > 0:
                vol_ratio = curr['Volume'] / vol_ma
                result['indicators']['volume_ratio'] = vol_ratio

                if vol_ratio >= 5.0:
                    supply_score += 15
                    result['signals'].append('VOLUME_5X')
                elif vol_ratio >= 3.0:
                    supply_score += 10
                    result['signals'].append('VOLUME_3X')
                elif vol_ratio >= 2.0:
                    supply_score += 5
                    result['signals'].append('VOLUME_2X')

            # 거래대금
            if trading_value >= 50_000_000_000:  # 500억 이상
                supply_score += 10
                result['signals'].append('VALUE_500B')
            elif trading_value >= 10_000_000_000:  # 100억 이상
                supply_score += 7
                result['signals'].append('VALUE_100B')
            elif trading_value >= 3_000_000_000:  # 30억 이상
                supply_score += 3
                result['signals'].append('VALUE_30B')

            supply_score = min(25, supply_score)
            result['indicators']['supply_score'] = supply_score

            # ========== ATR 계산 (손절용) ==========
            atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            if atr is not None:
                curr_atr = atr.iloc[-1]
                result['indicators']['atr'] = curr_atr
                result['indicators']['atr_pct'] = (curr_atr / curr['Close']) * 100
                result['indicators']['stop_loss_price'] = curr['Close'] - (curr_atr * self.ATR_STOP_MULTIPLIER)

            # ========== 최종 점수 ==========
            total_score = trend_score + pattern_score + momentum_score + supply_score
            result['score'] = max(0, min(100, total_score))

            # 매매 판단
            if result['score'] >= self.BUY_THRESHOLD:
                result['action'] = 'STRONG_BUY'
                result['reason'] = f"강력 매수 ({result['score']}점 >= {self.BUY_THRESHOLD}점)"
            elif result['score'] >= self.BUY_THRESHOLD_MODERATE:
                result['action'] = 'BUY'
                result['reason'] = f"매수 ({result['score']}점 >= {self.BUY_THRESHOLD_MODERATE}점)"
            else:
                result['action'] = 'HOLD'
                result['reason'] = f"관망 ({result['score']}점)"

            result['strategy_version'] = self.VERSION
            return result

        except Exception as e:
            print(f"V4 분석 오류: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _detect_vcp_pattern(self, df: pd.DataFrame) -> Dict:
        """
        VCP (Volatility Contraction Pattern) 패턴 감지

        VCP 특징:
        1. 고점은 비슷하게 유지
        2. 저점은 점점 높아짐 (수축)
        3. 거래량도 수축
        4. 마지막에 거래량 터지며 돌파

        Returns:
            {'detected': bool, 'contraction_pct': float}
        """
        result = {'detected': False, 'contraction_pct': 0}

        try:
            if len(df) < 40:
                return result

            # 최근 40일 데이터
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
            # 1. 레인지가 점점 수축 (최근이 더 좁음)
            range_contraction = ranges[3]['range'] < ranges[0]['range'] * 0.7  # 30% 이상 수축

            # 2. 저점이 점점 높아짐
            lows_rising = ranges[3]['low'] > ranges[0]['low']

            # 3. 거래량도 수축 (마지막 전까지)
            vol_contraction = ranges[2]['vol'] < ranges[0]['vol'] * 0.7

            # 4. 마지막 구간에서 거래량 증가 (돌파 준비)
            vol_expansion = ranges[3]['vol'] > ranges[2]['vol']

            if range_contraction and lows_rising and vol_contraction:
                result['detected'] = True
                result['contraction_pct'] = (1 - ranges[3]['range'] / ranges[0]['range']) * 100

                if vol_expansion:
                    result['vol_breakout'] = True

        except Exception as e:
            pass

        return result

    def _detect_obv_divergence(self, df: pd.DataFrame) -> Dict:
        """
        OBV 다이버전스 감지 (세력 축적 신호)

        불리시 다이버전스:
        - 가격은 저점을 낮추는데
        - OBV는 저점을 높이는 경우
        - 세력이 물량을 축적하고 있다는 신호

        Returns:
            {'bullish_divergence': bool, 'days': int}
        """
        result = {'bullish_divergence': False, 'days': 0}

        try:
            if len(df) < 30:
                return result

            # OBV 계산
            obv = ta.obv(df['Close'], df['Volume'])
            if obv is None:
                return result

            df_temp = df.copy()
            df_temp['OBV'] = obv

            # 최근 30일에서 저점 찾기
            recent = df_temp.tail(30)

            # 가격 저점들 찾기 (로컬 미니멈)
            price_lows = []
            obv_lows = []

            for i in range(2, len(recent) - 2):
                # 가격 저점
                if (recent['Low'].iloc[i] < recent['Low'].iloc[i-1] and
                    recent['Low'].iloc[i] < recent['Low'].iloc[i-2] and
                    recent['Low'].iloc[i] < recent['Low'].iloc[i+1] and
                    recent['Low'].iloc[i] < recent['Low'].iloc[i+2]):
                    price_lows.append((i, recent['Low'].iloc[i], recent['OBV'].iloc[i]))

            if len(price_lows) >= 2:
                # 최근 두 저점 비교
                prev_low = price_lows[-2]
                curr_low = price_lows[-1]

                # 불리시 다이버전스: 가격 하락, OBV 상승
                if (curr_low[1] < prev_low[1] and  # 가격 저점 낮아짐
                    curr_low[2] > prev_low[2]):     # OBV 저점 높아짐
                    result['bullish_divergence'] = True
                    result['days'] = curr_low[0] - prev_low[0]

        except Exception as e:
            pass

        return result

    def _calculate_stoch_rsi(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Stochastic RSI 계산

        StochRSI = (RSI - RSI_Low) / (RSI_High - RSI_Low)
        골든크로스: %K가 %D를 상향 돌파
        """
        try:
            # RSI 계산
            rsi = ta.rsi(df['Close'], length=14)
            if rsi is None:
                return None

            # Stochastic on RSI
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

            # 골든크로스 체크
            golden_cross = (prev_k < prev_d) and (curr_k > curr_d)

            return {
                'k': curr_k * 100,  # 0-100 스케일
                'd': curr_d * 100,
                'golden_cross': golden_cross
            }

        except Exception as e:
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

        if result['action'] in ['STRONG_BUY', 'BUY']:
            return True, result['reason'], score

        return False, f"조건 미충족 ({score}점)", score

    def should_sell(self, df: pd.DataFrame, entry_price: float, highest_price: float = None) -> tuple:
        """
        매도 여부 판단 (V4 고급 전략)

        특징:
        1. ATR 기반 동적 손절
        2. 본절 스탑 (+5% 도달 후)
        3. 분할 매도 시그널

        Args:
            df: 현재 가격 데이터
            entry_price: 매수가
            highest_price: 보유 중 최고가 (트레일링용)

        Returns:
            (should_sell: bool, reason: str, sell_type: str, sell_ratio: float)
        """
        if df is None or len(df) < 20:
            return False, "데이터 부족", None, 0

        curr = df.iloc[-1]
        curr_price = curr['Close']
        pnl_pct = ((curr_price - entry_price) / entry_price) * 100

        # ATR 계산
        atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        curr_atr = atr.iloc[-1] if atr is not None else curr_price * 0.03

        # 1. ATR 기반 손절 (진입가 - 2*ATR)
        stop_price = entry_price - (curr_atr * self.ATR_STOP_MULTIPLIER)
        if curr_price <= stop_price:
            return True, f"ATR 손절 (현재가 {curr_price:,.0f} <= 스탑 {stop_price:,.0f})", 'ATR_STOP', 1.0

        # 2. 본절 스탑 (+5% 도달 후)
        if highest_price is not None:
            highest_pnl = ((highest_price - entry_price) / entry_price) * 100
            if highest_pnl >= self.BREAKEVEN_TRIGGER_PCT * 100:
                # 본절 스탑 활성화
                if curr_price <= entry_price * 1.01:  # +1%까지 떨어지면 본절
                    return True, f"본절 스탑 (최고 +{highest_pnl:.1f}% → 현재 +{pnl_pct:.1f}%)", 'BREAKEVEN_STOP', 1.0

        # 3. 분할 매도 체크
        if pnl_pct >= self.SCALE_OUT_2 * 100:  # +20%
            return True, f"2차 분할 매도 (+{pnl_pct:.1f}%)", 'SCALE_OUT_2', 0.33

        if pnl_pct >= self.SCALE_OUT_1 * 100:  # +10%
            return True, f"1차 분할 매도 (+{pnl_pct:.1f}%)", 'SCALE_OUT_1', 0.33

        # 4. 20일선 이탈 체크 (마지막 방어선)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        sma20 = df['SMA_20'].iloc[-1]

        if pd.notna(sma20) and curr_price < sma20 * 0.98:  # 20일선 -2% 이탈
            return True, f"20일선 이탈 (현재가 {curr_price:,.0f} < 20일선 {sma20:,.0f})", 'MA_BREACH', 1.0

        return False, "보유 유지", None, 0

    def get_score_breakdown(self, df: pd.DataFrame) -> Dict:
        """점수 세부 내역 조회"""
        result = self.analyze(df)

        if result is None:
            return {}

        indicators = result.get('indicators', {})

        return {
            'trend_score': indicators.get('trend_score', 0),
            'pattern_score': indicators.get('pattern_score', 0),
            'momentum_score': indicators.get('momentum_score', 0),
            'supply_score': indicators.get('supply_score', 0),
            'total_score': result['score'],
            'patterns': result.get('patterns', []),
            'details': {
                'sma20_slope': indicators.get('sma20_slope', 0),
                'vcp_contraction': indicators.get('vcp_contraction', 0),
                'rsi': indicators.get('rsi', 0),
                'stoch_rsi_k': indicators.get('stoch_rsi_k', 0),
                'volume_ratio': indicators.get('volume_ratio', 0),
                'trading_value_억': indicators.get('trading_value_억', 0),
                'atr_pct': indicators.get('atr_pct', 0),
            }
        }

    def get_position_sizing(self, df: pd.DataFrame, account_balance: float) -> Dict:
        """
        ATR 기반 포지션 사이징

        리스크 1% 기준으로 포지션 크기 결정

        Args:
            df: 가격 데이터
            account_balance: 계좌 잔고

        Returns:
            {'quantity': int, 'risk_amount': float, 'stop_price': float}
        """
        if df is None or len(df) < 20:
            return {'quantity': 0, 'risk_amount': 0, 'stop_price': 0}

        curr_price = df.iloc[-1]['Close']

        # ATR 계산
        atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        curr_atr = atr.iloc[-1] if atr is not None else curr_price * 0.03

        # 리스크 1% = 계좌의 1%만 손실 허용
        risk_per_share = curr_atr * self.ATR_STOP_MULTIPLIER
        risk_amount = account_balance * 0.01

        # 수량 계산
        quantity = int(risk_amount / risk_per_share)

        # 최대 포지션 한도 (계좌의 10%)
        max_amount = account_balance * 0.10
        max_quantity = int(max_amount / curr_price)
        quantity = min(quantity, max_quantity)

        return {
            'quantity': max(1, quantity),
            'risk_amount': risk_amount,
            'stop_price': curr_price - risk_per_share,
            'position_value': quantity * curr_price
        }


# 테스트용
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    strategy = V4Strategy()

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
        print(f"패턴: {result['patterns']}")

        breakdown = strategy.get_score_breakdown(df)
        print(f"\n점수 세부:")
        print(f"  추세: {breakdown['trend_score']}/25")
        print(f"  패턴: {breakdown['pattern_score']}/25")
        print(f"  모멘텀: {breakdown['momentum_score']}/25")
        print(f"  수급: {breakdown['supply_score']}/25")

        print(f"\n상세 지표:")
        for key, val in breakdown['details'].items():
            if isinstance(val, float):
                print(f"  {key}: {val:.2f}")
            else:
                print(f"  {key}: {val}")

        # 포지션 사이징 테스트
        sizing = strategy.get_position_sizing(df, 10_000_000)
        print(f"\n포지션 사이징 (1천만원 계좌):")
        print(f"  추천 수량: {sizing['quantity']}주")
        print(f"  리스크 금액: {sizing['risk_amount']:,.0f}원")
        print(f"  손절가: {sizing['stop_price']:,.0f}원")
