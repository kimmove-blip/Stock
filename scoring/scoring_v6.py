"""
V6 스코어링 엔진 - Swing Predictor (스윙 예측기)

목적: "2~5일 내 상승 확률"을 예측
철학: 선행 지표 중심 + 내장 청산 전략

점수 체계 (100점 만점):
- 에너지 축적 (35점): 폭발 직전 신호
- 세력 매집 (30점): 스마트머니 추적
- 기술적 지지 (20점): 반등 확률
- 모멘텀 전환 (15점): 방향 전환 신호

청산 전략:
- 목표가: 진입가 + ATR × 2
- 손절가: 진입가 - ATR × 1
- 시간 손절: 최대 5일 홀딩

투자 적격: 75점 이상
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List


def calculate_score_v6(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None
) -> Optional[Dict]:
    """
    V6 점수 계산 - Swing Predictor

    Args:
        df: OHLCV 데이터프레임 (최소 120일 권장)
        investor_data: 투자자별 매매동향 (선택)
            {
                'foreign_net': 외국인 순매수량 (5일 합계),
                'institution_net': 기관 순매수량 (5일 합계),
                'foreign_consecutive_days': 외국인 연속 순매수 일수,
                'institution_consecutive_days': 기관 연속 순매수 일수,
            }

    Returns:
        {
            'score': 최종 점수 (0-100),
            'energy_score': 에너지 축적 점수,
            'accumulation_score': 세력 매집 점수,
            'support_score': 기술적 지지 점수,
            'momentum_score': 모멘텀 전환 점수,
            'signals': 발생한 신호 리스트,
            'patterns': 감지된 패턴,
            'indicators': 지표 상세값,
            'exit_strategy': 청산 전략 (목표가, 손절가),
            'warnings': 경고 신호,
            'version': 'v6'
        }
    """
    if df is None or len(df) < 60:
        return None

    try:
        df = df.copy()
        df = _calculate_indicators(df)

        result = {
            'score': 0,
            'energy_score': 0,
            'accumulation_score': 0,
            'support_score': 0,
            'momentum_score': 0,
            'signals': [],
            'patterns': [],
            'indicators': {},
            'exit_strategy': {},
            'warnings': [],
            'hold_days': 5,  # 기본 홀딩 기간
            'version': 'v6'
        }

        curr = df.iloc[-1]

        # 기본 지표 저장
        result['indicators'] = {
            'close': curr['Close'],
            'open': curr['Open'],
            'high': curr['High'],
            'low': curr['Low'],
            'volume': curr['Volume'],
            'change_pct': (curr['Close'] - df.iloc[-2]['Close']) / df.iloc[-2]['Close'] * 100,
            'atr': curr['atr'],
            'atr_pct': curr['atr'] / curr['Close'] * 100,
        }

        # ========== 1. 에너지 축적 (최대 35점) ==========
        energy = _check_energy_accumulation(df)
        result['energy_score'] = energy['score']
        result['signals'].extend(energy['signals'])
        result['patterns'].extend(energy.get('patterns', []))

        # ========== 2. 세력 매집 (최대 30점) ==========
        accumulation = _check_smart_money_accumulation(df, investor_data)
        result['accumulation_score'] = accumulation['score']
        result['signals'].extend(accumulation['signals'])
        result['patterns'].extend(accumulation.get('patterns', []))

        # ========== 3. 기술적 지지 (최대 20점) ==========
        support = _check_technical_support(df)
        result['support_score'] = support['score']
        result['signals'].extend(support['signals'])

        # ========== 4. 모멘텀 전환 (최대 15점) ==========
        momentum = _check_momentum_reversal(df)
        result['momentum_score'] = momentum['score']
        result['signals'].extend(momentum['signals'])

        # ========== 과락 조건 체크 ==========
        disqualify = _check_disqualification(df)
        if disqualify['disqualified']:
            result['score'] = 0
            result['warnings'].extend(disqualify['reasons'])
            result['signals'].append('DISQUALIFIED')
            return result

        # ========== 경고 신호 ==========
        warnings = _check_warnings(df)
        result['warnings'].extend(warnings)

        # ========== 최종 점수 ==========
        total = (result['energy_score'] + result['accumulation_score'] +
                 result['support_score'] + result['momentum_score'])
        result['score'] = max(0, min(100, total))

        # ========== 청산 전략 계산 ==========
        result['exit_strategy'] = _calculate_exit_strategy(df, result['score'])

        # ========== 추가 지표 저장 ==========
        result['indicators'].update({
            'bb_width': curr['bb_width'],
            'bb_position': curr['bb_position'],
            'rsi': curr['rsi'],
            'macd_hist': curr['macd_hist'],
            'obv_slope': _calculate_obv_slope(df, 10),
            'volume_ratio': curr['vol_ratio'],
        })

        return result

    except Exception as e:
        print(f"V6 점수 계산 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_score_v6_with_investor(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None
) -> Optional[Dict]:
    """V6 점수 계산 (투자자 데이터 포함) - 별칭"""
    return calculate_score_v6(df, investor_data)


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()

    # === 이동평균선 ===
    for p in [5, 10, 20, 60, 120]:
        df[f'ma{p}'] = df['Close'].rolling(p, min_periods=1).mean()

    # 이평선 상태
    df['ma_aligned'] = (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20'])
    df['ma_reverse'] = (df['ma5'] < df['ma10']) & (df['ma10'] < df['ma20'])

    # === 거래량 ===
    df['vol_ma5'] = df['Volume'].rolling(5, min_periods=1).mean()
    df['vol_ma20'] = df['Volume'].rolling(20, min_periods=1).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_ma20']

    # === 볼린저 밴드 ===
    df['bb_middle'] = df['Close'].rolling(20, min_periods=1).mean()
    df['bb_std'] = df['Close'].rolling(20, min_periods=1).std()
    df['bb_upper'] = df['bb_middle'] + df['bb_std'] * 2
    df['bb_lower'] = df['bb_middle'] - df['bb_std'] * 2
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
    df['bb_width_ma'] = df['bb_width'].rolling(20, min_periods=1).mean()
    df['bb_position'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

    # === ATR ===
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift(1))
    low_close = abs(df['Low'] - df['Close'].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14, min_periods=1).mean()
    df['atr_ma'] = df['atr'].rolling(20, min_periods=1).mean()

    # === OBV ===
    df['obv'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    df['obv_ma20'] = df['obv'].rolling(20, min_periods=1).mean()

    # === RSI ===
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['rsi'] = df['rsi'].fillna(50)

    # === MACD ===
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # === 스토캐스틱 ===
    low14 = df['Low'].rolling(14, min_periods=1).min()
    high14 = df['High'].rolling(14, min_periods=1).max()
    df['stoch_k'] = 100 * (df['Close'] - low14) / (high14 - low14 + 0.0001)
    df['stoch_d'] = df['stoch_k'].rolling(3, min_periods=1).mean()

    # === 피보나치 되돌림 기준점 (최근 60일) ===
    recent_60 = df.tail(60)
    swing_high = recent_60['High'].max()
    swing_low = recent_60['Low'].min()
    swing_range = swing_high - swing_low

    df['fib_0'] = swing_low  # 0%
    df['fib_236'] = swing_low + swing_range * 0.236
    df['fib_382'] = swing_low + swing_range * 0.382
    df['fib_500'] = swing_low + swing_range * 0.500
    df['fib_618'] = swing_low + swing_range * 0.618
    df['fib_100'] = swing_high  # 100%

    return df


def _check_energy_accumulation(df: pd.DataFrame) -> Dict:
    """
    에너지 축적 분석 (최대 35점)
    - 폭발 직전의 "응축" 상태를 감지
    """
    result = {'score': 0, 'signals': [], 'patterns': []}

    curr = df.iloc[-1]

    # === 1. 볼린저 밴드 수축 (최대 12점) ===
    bb_squeeze_ratio = curr['bb_width'] / curr['bb_width_ma'] if curr['bb_width_ma'] > 0 else 1

    if bb_squeeze_ratio < 0.6:  # 극심한 수축
        result['score'] += 12
        result['signals'].append('BB_EXTREME_SQUEEZE')
        result['patterns'].append('ENERGY_SQUEEZE')
    elif bb_squeeze_ratio < 0.75:
        result['score'] += 8
        result['signals'].append('BB_STRONG_SQUEEZE')
    elif bb_squeeze_ratio < 0.9:
        result['score'] += 4
        result['signals'].append('BB_SQUEEZE')

    # === 2. ATR 수축 (변동성 감소) (최대 8점) ===
    atr_ratio = curr['atr'] / curr['atr_ma'] if curr['atr_ma'] > 0 else 1

    if atr_ratio < 0.7:
        result['score'] += 8
        result['signals'].append('ATR_CONTRACTION')
    elif atr_ratio < 0.85:
        result['score'] += 5
        result['signals'].append('ATR_SHRINKING')

    # === 3. VCP 패턴 변형 (최대 10점) ===
    vcp = _detect_vcp_pattern(df)
    if vcp['detected']:
        result['score'] += 10
        result['signals'].append('VCP_PATTERN')
        result['patterns'].append('VCP')
        if vcp.get('tight'):
            result['score'] += 2
            result['signals'].append('VCP_TIGHT')

    # === 4. 거래량 수축 + 저점 상승 (최대 5점) ===
    vol_contraction = _check_volume_contraction(df, 10)
    if vol_contraction['contraction'] and vol_contraction['higher_lows']:
        result['score'] += 5
        result['signals'].append('VOL_CONTRACTION_HIGHER_LOWS')
        result['patterns'].append('COILING')
    elif vol_contraction['contraction']:
        result['score'] += 3
        result['signals'].append('VOL_CONTRACTION')

    result['score'] = min(35, result['score'])
    return result


def _check_smart_money_accumulation(df: pd.DataFrame, investor_data: Optional[Dict]) -> Dict:
    """
    세력 매집 분석 (최대 30점)
    - 스마트머니의 축적 신호 감지
    """
    result = {'score': 0, 'signals': [], 'patterns': []}

    # === 1. OBV 선행 상승 (최대 12점) ===
    obv_analysis = _analyze_obv_divergence(df)

    if obv_analysis['strong_bullish_div']:
        result['score'] += 12
        result['signals'].append('OBV_STRONG_LEADING')
        result['patterns'].append('SMART_MONEY_ACCUMULATION')
    elif obv_analysis['bullish_div']:
        result['score'] += 8
        result['signals'].append('OBV_LEADING')
    elif obv_analysis['obv_rising']:
        result['score'] += 4
        result['signals'].append('OBV_RISING')

    # === 2. 거래량 없는 하락 (매도 고갈) (최대 8점) ===
    selling_exhaustion = _check_selling_exhaustion(df, 5)

    if selling_exhaustion['exhausted']:
        result['score'] += 8
        result['signals'].append('SELLING_EXHAUSTED')
        result['patterns'].append('DRY_UP')
    elif selling_exhaustion['low_volume_decline']:
        result['score'] += 5
        result['signals'].append('LOW_VOL_DECLINE')

    # === 3. 기관/외국인 수급 (최대 10점) ===
    if investor_data:
        foreign_net = investor_data.get('foreign_net', 0)
        inst_net = investor_data.get('institution_net', 0)
        foreign_days = investor_data.get('foreign_consecutive_days', 0)
        inst_days = investor_data.get('institution_consecutive_days', 0)

        # 외국인 + 기관 동시 순매수
        if foreign_net > 0 and inst_net > 0:
            result['score'] += 6
            result['signals'].append('INST_FOREIGN_BOTH_BUY')
        elif foreign_net > 0 or inst_net > 0:
            result['score'] += 3
            result['signals'].append('INST_OR_FOREIGN_BUY')

        # 연속 매수
        if foreign_days >= 5 or inst_days >= 5:
            result['score'] += 4
            result['signals'].append('CONSECUTIVE_BUY_5D')
        elif foreign_days >= 3 or inst_days >= 3:
            result['score'] += 2
            result['signals'].append('CONSECUTIVE_BUY_3D')

    result['score'] = min(30, result['score'])
    return result


def _check_technical_support(df: pd.DataFrame) -> Dict:
    """
    기술적 지지 분석 (최대 20점)
    - 반등 확률이 높은 지지선 근처인지 확인
    """
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]

    # === 1. 주요 이평선 지지 (최대 10점) ===
    ma_support = _check_ma_support(df)

    if ma_support['ma20_support']:
        result['score'] += 5
        result['signals'].append('MA20_SUPPORT')
    if ma_support['ma60_support']:
        result['score'] += 3
        result['signals'].append('MA60_SUPPORT')
    if ma_support['ma120_support']:
        result['score'] += 2
        result['signals'].append('MA120_SUPPORT')

    # === 2. 피보나치 되돌림 지지 (최대 6점) ===
    fib_support = _check_fibonacci_support(df)

    if fib_support['level']:
        if fib_support['level'] in ['38.2%', '50%']:
            result['score'] += 6
            result['signals'].append(f"FIB_{fib_support['level']}_SUPPORT")
        elif fib_support['level'] == '61.8%':
            result['score'] += 4
            result['signals'].append('FIB_61.8%_SUPPORT')

    # === 3. 볼린저 밴드 하단 반등 (최대 4점) ===
    if curr['bb_position'] < 0.2:  # 하단 20% 이내
        # 전일 대비 반등 중인지 확인
        if df.iloc[-1]['Close'] > df.iloc[-2]['Close']:
            result['score'] += 4
            result['signals'].append('BB_LOWER_BOUNCE')
        else:
            result['score'] += 2
            result['signals'].append('BB_LOWER_ZONE')

    result['score'] = min(20, result['score'])
    return result


def _check_momentum_reversal(df: pd.DataFrame) -> Dict:
    """
    모멘텀 전환 분석 (최대 15점)
    - 방향 전환 신호 감지
    """
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    # === 1. MACD 히스토그램 전환 (최대 5점) ===
    # 음에서 양으로 전환
    if curr['macd_hist'] > 0 and prev['macd_hist'] <= 0:
        result['score'] += 5
        result['signals'].append('MACD_HIST_CROSS_UP')
    # 하락 둔화 (음수이지만 증가)
    elif curr['macd_hist'] < 0 and curr['macd_hist'] > prev['macd_hist'] > prev2['macd_hist']:
        result['score'] += 3
        result['signals'].append('MACD_HIST_RISING')

    # === 2. RSI 다이버전스 또는 과매도 탈출 (최대 5점) ===
    rsi_signal = _check_rsi_signal(df)

    if rsi_signal['bullish_div']:
        result['score'] += 5
        result['signals'].append('RSI_BULLISH_DIV')
    elif rsi_signal['oversold_exit']:
        result['score'] += 4
        result['signals'].append('RSI_OVERSOLD_EXIT')
    elif rsi_signal['oversold']:
        result['score'] += 2
        result['signals'].append('RSI_OVERSOLD')

    # === 3. 스토캐스틱 바닥권 골든크로스 (최대 5점) ===
    stoch_cross = (curr['stoch_k'] > curr['stoch_d'] and
                   prev['stoch_k'] <= prev['stoch_d'])

    if stoch_cross and curr['stoch_k'] < 30:
        result['score'] += 5
        result['signals'].append('STOCH_GOLDEN_OVERSOLD')
    elif stoch_cross and curr['stoch_k'] < 50:
        result['score'] += 3
        result['signals'].append('STOCH_GOLDEN')
    elif curr['stoch_k'] < 20:
        result['score'] += 2
        result['signals'].append('STOCH_OVERSOLD')

    result['score'] = min(15, result['score'])
    return result


def _check_disqualification(df: pd.DataFrame) -> Dict:
    """
    과락 조건 체크
    """
    result = {'disqualified': False, 'reasons': []}

    curr = df.iloc[-1]

    # 1. 강한 역배열
    if curr['ma_reverse']:
        ma60 = curr['ma60']
        ma20 = curr['ma20']
        if pd.notna(ma60) and ma60 > 0:
            gap = (ma20 - ma60) / ma60 * 100
            if gap < -5:  # 20일선이 60일선보다 5% 이상 아래
                result['disqualified'] = True
                result['reasons'].append('STRONG_REVERSE_ALIGNMENT')

    # 2. RSI 극단적 과매수 (85 이상)
    if curr['rsi'] > 85:
        result['disqualified'] = True
        result['reasons'].append('RSI_EXTREME_OVERBOUGHT')

    # 3. 볼린저 밴드 상단 이탈 + 거래량 폭증 (천장 신호)
    if curr['bb_position'] > 1.1 and curr['vol_ratio'] > 3:
        result['disqualified'] = True
        result['reasons'].append('POSSIBLE_CLIMAX_TOP')

    # 4. 급락 중 (-5% 이상 하락)
    change_pct = (curr['Close'] - df.iloc[-2]['Close']) / df.iloc[-2]['Close'] * 100
    if change_pct < -5:
        result['disqualified'] = True
        result['reasons'].append('SHARP_DECLINE')

    return result


def _check_warnings(df: pd.DataFrame) -> List[str]:
    """
    경고 신호 체크
    """
    warnings = []

    curr = df.iloc[-1]

    # 1. 거래대금 부족
    trading_value = curr['Close'] * curr['Volume']
    if trading_value < 1_000_000_000:  # 10억 미만
        warnings.append('LOW_LIQUIDITY')

    # 2. 20일 급등 후
    recent_20 = df.tail(20)
    change_20d = (curr['Close'] - recent_20.iloc[0]['Close']) / recent_20.iloc[0]['Close'] * 100
    if change_20d > 30:
        warnings.append('OVEREXTENDED_20D')

    # 3. 상방 매물대 존재
    resistance = _check_nearby_resistance(df)
    if resistance['exists']:
        warnings.append('RESISTANCE_NEARBY')

    # 4. 음봉 지속
    recent_5 = df.tail(5)
    down_days = sum(1 for i in range(len(recent_5)) if recent_5.iloc[i]['Close'] < recent_5.iloc[i]['Open'])
    if down_days >= 4:
        warnings.append('CONSECUTIVE_DOWN_DAYS')

    return warnings


def _calculate_exit_strategy(df: pd.DataFrame, score: int) -> Dict:
    """
    청산 전략 계산
    """
    curr = df.iloc[-1]
    atr = curr['atr']
    close = curr['Close']

    # 점수에 따라 목표/손절 배율 조정
    if score >= 85:
        target_mult = 2.5
        stop_mult = 1.0
        hold_days = 5
    elif score >= 75:
        target_mult = 2.0
        stop_mult = 1.0
        hold_days = 4
    elif score >= 65:
        target_mult = 1.5
        stop_mult = 1.0
        hold_days = 3
    else:
        target_mult = 1.2
        stop_mult = 0.8
        hold_days = 2

    target_price = close + (atr * target_mult)
    stop_price = close - (atr * stop_mult)

    return {
        'entry_price': close,
        'target_price': round(target_price, 2),
        'stop_price': round(stop_price, 2),
        'target_pct': round((target_price - close) / close * 100, 2),
        'stop_pct': round((stop_price - close) / close * 100, 2),
        'risk_reward': round(target_mult / stop_mult, 2),
        'max_hold_days': hold_days,
        'atr': round(atr, 2),
        'atr_pct': round(atr / close * 100, 2),
    }


# ============================================================
# 헬퍼 함수들
# ============================================================

def _detect_vcp_pattern(df: pd.DataFrame) -> Dict:
    """VCP (Volatility Contraction Pattern) 감지"""
    result = {'detected': False, 'tight': False, 'contraction_pct': 0}

    if len(df) < 40:
        return result

    try:
        recent = df.tail(40)

        # 4개의 10일 구간
        ranges = []
        for i in range(4):
            period = recent.iloc[i*10:(i+1)*10]
            high = period['High'].max()
            low = period['Low'].min()
            vol = period['Volume'].mean()
            ranges.append({
                'high': high,
                'low': low,
                'range': high - low,
                'vol': vol
            })

        # VCP 조건
        # 1. 변동폭 수축 (마지막 구간이 첫 구간의 70% 이하)
        range_contraction = ranges[3]['range'] < ranges[0]['range'] * 0.7

        # 2. 저점 상승
        lows_rising = ranges[3]['low'] > ranges[0]['low']

        # 3. 거래량 수축
        vol_contraction = ranges[2]['vol'] < ranges[0]['vol'] * 0.7

        if range_contraction and lows_rising and vol_contraction:
            result['detected'] = True
            result['contraction_pct'] = (1 - ranges[3]['range'] / ranges[0]['range']) * 100

            # 매우 타이트한 수축
            if ranges[3]['range'] < ranges[0]['range'] * 0.5:
                result['tight'] = True
    except:
        pass

    return result


def _check_volume_contraction(df: pd.DataFrame, days: int = 10) -> Dict:
    """거래량 수축 + 저점 상승 체크"""
    result = {'contraction': False, 'higher_lows': False}

    if len(df) < days:
        return result

    recent = df.tail(days)

    # 거래량 수축: 후반 5일 평균 < 전반 5일 평균 * 0.7
    first_half_vol = recent.head(days//2)['Volume'].mean()
    second_half_vol = recent.tail(days//2)['Volume'].mean()

    if second_half_vol < first_half_vol * 0.7:
        result['contraction'] = True

    # 저점 상승: 후반 저점 > 전반 저점
    first_half_low = recent.head(days//2)['Low'].min()
    second_half_low = recent.tail(days//2)['Low'].min()

    if second_half_low > first_half_low:
        result['higher_lows'] = True

    return result


def _analyze_obv_divergence(df: pd.DataFrame) -> Dict:
    """OBV 다이버전스 분석"""
    result = {
        'strong_bullish_div': False,
        'bullish_div': False,
        'obv_rising': False
    }

    if len(df) < 20:
        return result

    recent = df.tail(20)

    # 가격 변화
    price_change = (recent.iloc[-1]['Close'] - recent.iloc[0]['Close']) / recent.iloc[0]['Close'] * 100

    # OBV 변화
    obv_change = recent.iloc[-1]['obv'] - recent.iloc[0]['obv']

    # OBV 상승 중
    if obv_change > 0:
        result['obv_rising'] = True

    # 불리시 다이버전스: 가격 하락/횡보 but OBV 상승
    if price_change < -5 and obv_change > 0:
        result['strong_bullish_div'] = True
    elif price_change < 0 and obv_change > 0:
        result['bullish_div'] = True

    return result


def _check_selling_exhaustion(df: pd.DataFrame, days: int = 5) -> Dict:
    """매도 고갈 체크 (거래량 없는 하락)"""
    result = {'exhausted': False, 'low_volume_decline': False}

    if len(df) < days:
        return result

    recent = df.tail(days)

    # 하락일 체크
    down_days = 0
    low_vol_down_days = 0

    for i in range(len(recent)):
        row = recent.iloc[i]
        if row['Close'] < row['Open']:  # 음봉
            down_days += 1
            if row['vol_ratio'] < 0.7:  # 평균 대비 낮은 거래량
                low_vol_down_days += 1

    # 하락일이 많지만 거래량이 낮음 = 매도 고갈
    if down_days >= 3 and low_vol_down_days >= 2:
        result['exhausted'] = True
    elif down_days >= 2 and low_vol_down_days >= 1:
        result['low_volume_decline'] = True

    return result


def _check_ma_support(df: pd.DataFrame) -> Dict:
    """이평선 지지 체크"""
    result = {
        'ma20_support': False,
        'ma60_support': False,
        'ma120_support': False
    }

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    close = curr['Close']
    low = curr['Low']

    # 20일선 지지: 저점이 20일선 터치 후 종가가 위
    ma20 = curr['ma20']
    if pd.notna(ma20):
        touch_ma20 = low <= ma20 * 1.01 and close >= ma20 * 0.99
        above_ma20 = close > ma20
        if touch_ma20 or (above_ma20 and prev['Low'] <= prev['ma20'] * 1.01):
            result['ma20_support'] = True

    # 60일선 지지
    ma60 = curr['ma60']
    if pd.notna(ma60):
        touch_ma60 = low <= ma60 * 1.02 and close >= ma60 * 0.98
        if touch_ma60:
            result['ma60_support'] = True

    # 120일선 지지
    ma120 = curr['ma120']
    if pd.notna(ma120):
        touch_ma120 = low <= ma120 * 1.03 and close >= ma120 * 0.97
        if touch_ma120:
            result['ma120_support'] = True

    return result


def _check_fibonacci_support(df: pd.DataFrame) -> Dict:
    """피보나치 지지 체크"""
    result = {'level': None, 'price': None}

    curr = df.iloc[-1]
    close = curr['Close']
    low = curr['Low']

    # 각 피보나치 레벨 근처인지 체크 (2% 오차 허용)
    levels = [
        ('38.2%', curr['fib_382']),
        ('50%', curr['fib_500']),
        ('61.8%', curr['fib_618']),
    ]

    for level_name, level_price in levels:
        if pd.notna(level_price) and level_price > 0:
            # 저점이 레벨 근처 터치 & 종가가 레벨 위
            touch = low <= level_price * 1.02
            above = close >= level_price * 0.98
            if touch and above:
                result['level'] = level_name
                result['price'] = level_price
                break

    return result


def _check_rsi_signal(df: pd.DataFrame) -> Dict:
    """RSI 신호 체크"""
    result = {
        'bullish_div': False,
        'oversold_exit': False,
        'oversold': False
    }

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 과매도
    if curr['rsi'] < 30:
        result['oversold'] = True

    # 과매도 탈출
    if curr['rsi'] > 30 and prev['rsi'] <= 30:
        result['oversold_exit'] = True

    # 다이버전스 (간단 버전): 가격 신저점 but RSI 저점 상승
    if len(df) >= 10:
        recent = df.tail(10)

        # 최근 저점이 이전 저점보다 낮은데 RSI는 높으면 다이버전스
        first_half = recent.head(5)
        second_half = recent.tail(5)

        if (second_half['Low'].min() < first_half['Low'].min() and
            second_half['rsi'].min() > first_half['rsi'].min()):
            result['bullish_div'] = True

    return result


def _check_nearby_resistance(df: pd.DataFrame) -> Dict:
    """상방 매물대 체크"""
    result = {'exists': False, 'level': None}

    if len(df) < 60:
        return result

    curr = df.iloc[-1]
    close = curr['Close']

    # 최근 60일 내 고거래량 발생 가격대
    recent = df.tail(60)
    high_vol_days = recent[recent['vol_ratio'] > 2.0]

    # 현재가 위 5% 이내에 저항 있는지
    upper_bound = close * 1.05

    for idx, row in high_vol_days.iterrows():
        if close < row['High'] <= upper_bound:
            result['exists'] = True
            result['level'] = row['High']
            break

    return result


def _calculate_obv_slope(df: pd.DataFrame, days: int = 10) -> float:
    """OBV 기울기 계산"""
    if len(df) < days:
        return 0

    recent = df.tail(days)
    obv_start = recent.iloc[0]['obv']
    obv_end = recent.iloc[-1]['obv']

    if obv_start == 0:
        return 0

    return (obv_end - obv_start) / abs(obv_start) * 100


# ============================================================
# 백테스트용 함수
# ============================================================

def simulate_trade(
    df: pd.DataFrame,
    entry_idx: int,
    exit_strategy: Dict,
    max_days: int = 5
) -> Dict:
    """
    단일 거래 시뮬레이션

    Args:
        df: 전체 OHLCV 데이터
        entry_idx: 진입 시점 인덱스 (iloc 기준)
        exit_strategy: 청산 전략 딕셔너리
        max_days: 최대 홀딩 일수

    Returns:
        거래 결과
    """
    if entry_idx + 1 >= len(df):
        return {'success': False, 'reason': 'NO_DATA'}

    # 익일 시가에 진입
    entry_day = df.iloc[entry_idx + 1]
    entry_price = entry_day['Open']

    # 갭업 15% 이상이면 스킵
    prev_close = df.iloc[entry_idx]['Close']
    gap_pct = (entry_price - prev_close) / prev_close * 100
    if gap_pct >= 15:
        return {'success': False, 'reason': 'GAP_UP_SKIP', 'gap_pct': gap_pct}

    # ATR 기반 목표/손절 재계산 (진입가 기준)
    atr = df.iloc[entry_idx]['atr']
    target_price = entry_price + (atr * 2)
    stop_price = entry_price - (atr * 1)

    result = {
        'success': True,
        'entry_date': df.index[entry_idx + 1],
        'entry_price': entry_price,
        'target_price': target_price,
        'stop_price': stop_price,
        'exit_date': None,
        'exit_price': None,
        'exit_reason': None,
        'pnl_pct': 0,
        'hold_days': 0
    }

    # 홀딩 기간 동안 시뮬레이션
    for day in range(1, max_days + 1):
        day_idx = entry_idx + 1 + day
        if day_idx >= len(df):
            break

        day_data = df.iloc[day_idx]

        # 장중 고점이 목표가 도달
        if day_data['High'] >= target_price:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = target_price
            result['exit_reason'] = 'TARGET_HIT'
            result['hold_days'] = day
            break

        # 장중 저점이 손절가 이탈
        if day_data['Low'] <= stop_price:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = stop_price
            result['exit_reason'] = 'STOP_HIT'
            result['hold_days'] = day
            break

        # 마지막 날이면 종가 청산
        if day == max_days:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = day_data['Close']
            result['exit_reason'] = 'TIME_EXIT'
            result['hold_days'] = day

    # 수익률 계산
    if result['exit_price']:
        result['pnl_pct'] = (result['exit_price'] - result['entry_price']) / result['entry_price'] * 100

    return result


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    # 샘플 데이터 생성
    np.random.seed(42)

    dates = pd.date_range(end='2026-01-24', periods=120, freq='D')

    # 기본 가격 생성
    base_price = 50000
    returns = np.random.randn(120) * 0.02
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        'Open': prices * (1 - np.random.rand(120) * 0.01),
        'High': prices * (1 + np.random.rand(120) * 0.02),
        'Low': prices * (1 - np.random.rand(120) * 0.02),
        'Close': prices,
        'Volume': np.random.randint(100000, 1000000, 120)
    }, index=dates)

    # V6 점수 계산
    result = calculate_score_v6(df)

    if result:
        print("=" * 60)
        print("V6 Swing Predictor 분석 결과")
        print("=" * 60)
        print(f"\n최종 점수: {result['score']}점")
        print(f"  - 에너지 축적: {result['energy_score']}/35")
        print(f"  - 세력 매집: {result['accumulation_score']}/30")
        print(f"  - 기술적 지지: {result['support_score']}/20")
        print(f"  - 모멘텀 전환: {result['momentum_score']}/15")

        print(f"\n신호: {result['signals']}")
        print(f"패턴: {result['patterns']}")
        print(f"경고: {result['warnings']}")

        print(f"\n청산 전략:")
        exit_s = result['exit_strategy']
        print(f"  - 진입가: {exit_s['entry_price']:,.0f}")
        print(f"  - 목표가: {exit_s['target_price']:,.0f} (+{exit_s['target_pct']:.1f}%)")
        print(f"  - 손절가: {exit_s['stop_price']:,.0f} ({exit_s['stop_pct']:.1f}%)")
        print(f"  - 손익비: {exit_s['risk_reward']:.1f}")
        print(f"  - 최대 홀딩: {exit_s['max_hold_days']}일")
    else:
        print("분석 실패")
