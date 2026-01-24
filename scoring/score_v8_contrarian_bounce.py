"""
V8 스코어링 엔진 - Contrarian Bounce (역발상 반등 전략)

V7 백테스트 심층 분석 결과 반영:
- 추세<=15 & 모멘텀>=12: 42.9% 승률, +2.77% 평균수익률
- 모멘텀>=12 & 에너지>=10: 31.1% 승률, +1.14% 평균수익률
- 추세 점수가 낮을수록 오히려 수익률 증가

핵심 전략 (역발상):
- 추세가 약한 종목에서 (역배열 또는 MA 아래)
- 모멘텀 반전 신호가 강한 종목을 찾아
- 단기 반등을 노리는 전략

점수 체계 (100점 만점):
- 반등 신호 (40점): 모멘텀 반전, RSI 과매도 탈출, 스토캐스틱 골든
- 에너지 축적 (25점): BB수축, ATR수축, VCP
- 바닥 확인 (20점): 지지선, 저점 상승, 거래량 바닥
- 수급 (15점): OBV 다이버전스, 이평선 터치

필수 조건 (과락 아니면 통과):
- 모멘텀 점수 >= 12 (필수)
- 추세 점수 <= 20 (너무 강한 추세 제외)

청산 전략:
- 목표가: 진입가 + ATR × 1.5
- 손절가: 진입가 - ATR × 0.8
- 시간 손절: 최대 3일 홀딩
- 트레일링 스탑: ATR×0.5 수익 시 본전 스탑

투자 적격: 45점 이상 (낮춤 - 더 많은 기회)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List


def calculate_score_v8(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None
) -> Optional[Dict]:
    """
    V8 점수 계산 - Contrarian Bounce (역발상 반등)

    Args:
        df: OHLCV 데이터프레임 (최소 60일 권장)
        investor_data: 투자자별 매매동향 (선택)

    Returns:
        점수 및 분석 결과 딕셔너리
    """
    if df is None or len(df) < 60:
        return None

    try:
        df = df.copy()
        df = _calculate_indicators(df)

        result = {
            'score': 0,
            'bounce_score': 0,      # 반등 신호 (40점)
            'energy_score': 0,       # 에너지 축적 (25점)
            'bottom_score': 0,       # 바닥 확인 (20점)
            'supply_score': 0,       # 수급 (15점)
            'trend_score': 0,        # 추세 점수 (참고용, 점수에 반영 안함)
            'momentum_score': 0,     # 모멘텀 점수 (참고용)
            'signals': [],
            'patterns': [],
            'indicators': {},
            'exit_strategy': {},
            'warnings': [],
            'disqualified': False,
            'disqualify_reason': None,
            'hold_days': 3,
            'version': 'v8'
        }

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # ========== 기본 지표 저장 ==========
        result['indicators'] = {
            'close': curr['Close'],
            'open': curr['Open'],
            'high': curr['High'],
            'low': curr['Low'],
            'volume': curr['Volume'],
            'change_pct': (curr['Close'] - prev['Close']) / prev['Close'] * 100,
            'atr': curr['atr'],
            'atr_pct': curr['atr'] / curr['Close'] * 100,
            'ma20': curr['ma20'],
            'ma60': curr['ma60'],
            'rsi': curr['rsi'],
        }

        # ========== 추세/모멘텀 점수 계산 (V7 방식으로 참고용) ==========
        trend = _check_trend_score_v7_style(df)
        momentum = _check_momentum_score_v7_style(df)
        result['trend_score'] = trend['score']
        result['momentum_score'] = momentum['score']

        # ========== V8 필수 조건 체크 ==========
        disqualify = _check_disqualification_v8(df, momentum['score'], trend['score'])
        if disqualify['disqualified']:
            result['disqualified'] = True
            result['disqualify_reason'] = disqualify['reasons']
            result['signals'].append('DISQUALIFIED')
            return result

        # ========== 1. 반등 신호 (최대 40점) ==========
        bounce = _check_bounce_signals(df)
        result['bounce_score'] = bounce['score']
        result['signals'].extend(bounce['signals'])

        # ========== 2. 에너지 축적 (최대 25점) ==========
        energy = _check_energy_accumulation_v8(df)
        result['energy_score'] = energy['score']
        result['signals'].extend(energy['signals'])
        result['patterns'].extend(energy.get('patterns', []))

        # ========== 3. 바닥 확인 (최대 20점) ==========
        bottom = _check_bottom_confirmation(df)
        result['bottom_score'] = bottom['score']
        result['signals'].extend(bottom['signals'])

        # ========== 4. 수급 (최대 15점) ==========
        supply = _check_supply_v8(df, investor_data)
        result['supply_score'] = supply['score']
        result['signals'].extend(supply['signals'])

        # ========== 경고 신호 ==========
        warnings = _check_warnings_v8(df)
        result['warnings'].extend(warnings)

        # ========== 최종 점수 ==========
        total = (result['bounce_score'] + result['energy_score'] +
                 result['bottom_score'] + result['supply_score'])
        result['score'] = max(0, min(100, total))

        # ========== 청산 전략 계산 ==========
        result['exit_strategy'] = _calculate_exit_strategy_v8(df, result['score'])

        # 추가 지표
        result['indicators'].update({
            'bb_width': curr['bb_width'],
            'bb_position': curr['bb_position'],
            'macd_hist': curr['macd_hist'],
            'stoch_k': curr['stoch_k'],
            'volume_ratio': curr['vol_ratio'],
        })

        return result

    except Exception as e:
        print(f"V8 점수 계산 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_score_v8_with_investor(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None
) -> Optional[Dict]:
    """투자자 데이터 포함 버전"""
    return calculate_score_v8(df, investor_data)


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()

    # === 이동평균선 ===
    for p in [5, 10, 20, 60, 120]:
        df[f'ma{p}'] = df['Close'].rolling(p, min_periods=1).mean()

    # 이평선 상태
    df['ma_aligned'] = (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20']) & (df['ma20'] > df['ma60'])
    df['ma_reverse'] = (df['ma5'] < df['ma10']) & (df['ma10'] < df['ma20'])  # 역배열

    # === 거래량 ===
    df['vol_ma5'] = df['Volume'].rolling(5, min_periods=1).mean()
    df['vol_ma20'] = df['Volume'].rolling(20, min_periods=1).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_ma20']

    # === 거래대금 ===
    df['trading_value'] = df['Close'] * df['Volume']
    df['trading_value_ma20'] = df['trading_value'].rolling(20, min_periods=1).mean()

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

    # === 20일 최저가 대비 위치 ===
    df['low_20d'] = df['Low'].rolling(20, min_periods=1).min()
    df['high_20d'] = df['High'].rolling(20, min_periods=1).max()
    df['pos_in_range'] = (df['Close'] - df['low_20d']) / (df['high_20d'] - df['low_20d'] + 0.0001)

    return df


def _check_trend_score_v7_style(df: pd.DataFrame) -> Dict:
    """V7 스타일 추세 점수 (참고용)"""
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]

    # 완전 정배열 +15점
    if curr['ma_aligned']:
        result['score'] += 15
        result['signals'].append('FULL_ALIGNMENT')
    # 부분 정배열 +10점
    elif pd.notna(curr['ma20']) and pd.notna(curr['ma60']):
        if curr['Close'] > curr['ma20'] > curr['ma60']:
            result['score'] += 10
            result['signals'].append('PARTIAL_ALIGNMENT')

    # 20일선 위 +5점
    if pd.notna(curr['ma20']) and curr['Close'] > curr['ma20']:
        result['score'] += 5

    # 60일선 위 +5점
    if pd.notna(curr['ma60']) and curr['Close'] > curr['ma60']:
        result['score'] += 5

    result['score'] = min(25, result['score'])
    return result


def _check_momentum_score_v7_style(df: pd.DataFrame) -> Dict:
    """V7 스타일 모멘텀 점수 (참고용)"""
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else prev

    # MACD 골든크로스 +10점
    if curr['macd'] > curr['macd_signal'] and prev['macd'] <= prev['macd_signal']:
        result['score'] += 10
        result['signals'].append('MACD_GOLDEN_CROSS')
    elif curr['macd_hist'] > 0 and prev['macd_hist'] <= 0:
        result['score'] += 6
        result['signals'].append('MACD_HIST_CROSS_UP')
    elif curr['macd_hist'] > prev['macd_hist'] > prev2['macd_hist']:
        result['score'] += 3
        result['signals'].append('MACD_HIST_RISING')

    # RSI 과매도 탈출 +8점
    if curr['rsi'] > 30 and prev['rsi'] <= 30:
        result['score'] += 8
        result['signals'].append('RSI_OVERSOLD_EXIT')
    elif 30 < curr['rsi'] < 50 and curr['rsi'] > prev['rsi']:
        result['score'] += 4
        result['signals'].append('RSI_TURNING_UP')

    # 스토캐스틱 골든크로스 +7점
    if curr['stoch_k'] > curr['stoch_d'] and prev['stoch_k'] <= prev['stoch_d']:
        if curr['stoch_k'] < 30:
            result['score'] += 7
        elif curr['stoch_k'] < 50:
            result['score'] += 4

    # 거래량 급증 양봉 +5점
    if curr['Close'] > curr['Open'] and curr['vol_ratio'] > 2.0:
        result['score'] += 5

    result['score'] = min(30, result['score'])
    return result


def _check_disqualification_v8(df: pd.DataFrame, momentum_score: int, trend_score: int) -> Dict:
    """
    V8 과락 조건 (역발상 전략용) - 완화된 버전
    """
    result = {'disqualified': False, 'reasons': []}

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 1. 모멘텀 점수 최소 기준 제거 (V8은 반등 신호로 판단)
    # momentum_score 필터 제거

    # 2. 추세가 너무 강하면 제외 (역발상이므로)
    # 완전 정배열 + RSI 75 이상이면 과락 (기준 완화)
    if curr['ma_aligned'] and curr['rsi'] > 75:
        result['disqualified'] = True
        result['reasons'].append('TOO_STRONG_TREND')

    # 3. RSI 극단적 과매수 (80 이상)
    if curr['rsi'] > 80:
        result['disqualified'] = True
        result['reasons'].append('RSI_EXTREME_OVERBOUGHT')

    # 4. 당일 급락 (-7% 이상) - 낙하하는 칼날
    change_pct = (curr['Close'] - prev['Close']) / prev['Close'] * 100
    if change_pct < -7:
        result['disqualified'] = True
        result['reasons'].append('FALLING_KNIFE')

    # 5. 거래대금 부족 (5억 미만)
    trading_value = curr['Close'] * curr['Volume']
    if trading_value < 500_000_000:
        result['disqualified'] = True
        result['reasons'].append('LOW_LIQUIDITY')

    # 6. 5일 연속 음봉
    recent_5 = df.tail(5)
    down_days = sum(1 for i in range(len(recent_5)) if recent_5.iloc[i]['Close'] < recent_5.iloc[i]['Open'])
    if down_days >= 5:
        result['disqualified'] = True
        result['reasons'].append('CONSECUTIVE_DOWN_5DAYS')

    return result


def _check_bounce_signals(df: pd.DataFrame) -> Dict:
    """
    반등 신호 분석 (최대 40점) - V8 핵심
    """
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else prev

    # 1. MACD 반전 신호 (최대 12점)
    if curr['macd'] > curr['macd_signal'] and prev['macd'] <= prev['macd_signal']:
        result['score'] += 12
        result['signals'].append('MACD_GOLDEN_CROSS')
    elif curr['macd_hist'] > 0 and prev['macd_hist'] <= 0:
        result['score'] += 8
        result['signals'].append('MACD_HIST_CROSS_UP')
    elif curr['macd_hist'] > prev['macd_hist'] > prev2['macd_hist']:
        result['score'] += 4
        result['signals'].append('MACD_HIST_RISING')

    # 2. RSI 과매도 탈출 (최대 10점)
    if curr['rsi'] > 30 and prev['rsi'] <= 30:
        result['score'] += 10
        result['signals'].append('RSI_OVERSOLD_EXIT')
    elif curr['rsi'] > 35 and prev['rsi'] <= 35 and curr['rsi'] < 50:
        result['score'] += 6
        result['signals'].append('RSI_RECOVERY')
    elif 25 < curr['rsi'] < 45 and curr['rsi'] > prev['rsi']:
        result['score'] += 3
        result['signals'].append('RSI_TURNING_UP')

    # 3. 스토캐스틱 바닥권 골든크로스 (최대 10점)
    stoch_cross = (curr['stoch_k'] > curr['stoch_d'] and
                   prev['stoch_k'] <= prev['stoch_d'])

    if stoch_cross and curr['stoch_k'] < 20:
        result['score'] += 10
        result['signals'].append('STOCH_GOLDEN_DEEP_OVERSOLD')
    elif stoch_cross and curr['stoch_k'] < 30:
        result['score'] += 7
        result['signals'].append('STOCH_GOLDEN_OVERSOLD')
    elif stoch_cross and curr['stoch_k'] < 50:
        result['score'] += 4
        result['signals'].append('STOCH_GOLDEN')

    # 4. 반등 양봉 (최대 8점)
    is_bullish = curr['Close'] > curr['Open']
    body_size = abs(curr['Close'] - curr['Open']) / curr['Open'] * 100

    if is_bullish and body_size > 3 and curr['vol_ratio'] > 1.5:
        result['score'] += 8
        result['signals'].append('STRONG_BOUNCE_CANDLE')
    elif is_bullish and body_size > 2 and curr['vol_ratio'] > 1.2:
        result['score'] += 5
        result['signals'].append('BOUNCE_CANDLE')
    elif is_bullish and curr['Close'] > prev['Close']:
        result['score'] += 2
        result['signals'].append('UP_DAY')

    result['score'] = min(40, result['score'])
    return result


def _check_energy_accumulation_v8(df: pd.DataFrame) -> Dict:
    """
    에너지 축적 분석 (최대 25점)
    """
    result = {'score': 0, 'signals': [], 'patterns': []}

    curr = df.iloc[-1]

    # 1. 볼린저 밴드 수축 (최대 10점)
    bb_squeeze_ratio = curr['bb_width'] / curr['bb_width_ma'] if curr['bb_width_ma'] > 0 else 1

    if bb_squeeze_ratio < 0.6:
        result['score'] += 10
        result['signals'].append('BB_EXTREME_SQUEEZE')
        result['patterns'].append('ENERGY_SQUEEZE')
    elif bb_squeeze_ratio < 0.75:
        result['score'] += 6
        result['signals'].append('BB_STRONG_SQUEEZE')
    elif bb_squeeze_ratio < 0.9:
        result['score'] += 3
        result['signals'].append('BB_SQUEEZE')

    # 2. ATR 수축 (최대 8점)
    atr_ratio = curr['atr'] / curr['atr_ma'] if curr['atr_ma'] > 0 else 1

    if atr_ratio < 0.7:
        result['score'] += 8
        result['signals'].append('ATR_EXTREME_CONTRACTION')
    elif atr_ratio < 0.85:
        result['score'] += 4
        result['signals'].append('ATR_CONTRACTION')

    # 3. VCP 패턴 (최대 7점)
    vcp = _detect_vcp_pattern(df)
    if vcp['detected']:
        result['score'] += 7
        result['signals'].append('VCP_PATTERN')
        result['patterns'].append('VCP')

    result['score'] = min(25, result['score'])
    return result


def _check_bottom_confirmation(df: pd.DataFrame) -> Dict:
    """
    바닥 확인 분석 (최대 20점) - V8 신규
    """
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 1. 볼린저 밴드 하단 터치 후 반등 (최대 8점)
    if prev['bb_position'] < 0.1 and curr['bb_position'] > 0.15:
        result['score'] += 8
        result['signals'].append('BB_LOWER_BOUNCE')
    elif curr['bb_position'] < 0.2 and curr['Close'] > prev['Close']:
        result['score'] += 4
        result['signals'].append('NEAR_BB_LOWER')

    # 2. 20일 최저가 근처에서 반등 (최대 6점)
    if curr['pos_in_range'] < 0.15 and curr['Close'] > prev['Close']:
        result['score'] += 6
        result['signals'].append('NEAR_20D_LOW_BOUNCE')
    elif curr['pos_in_range'] < 0.25:
        result['score'] += 3
        result['signals'].append('NEAR_20D_LOW')

    # 3. 저점 상승 패턴 (최대 6점)
    if len(df) >= 10:
        recent_10 = df.tail(10)
        lows = recent_10['Low'].values

        # 최근 저점이 이전 저점보다 높으면
        min_idx = np.argmin(lows)
        if min_idx > 3:  # 저점이 5일 이상 전
            recent_low = lows[-3:].min()
            old_low = lows[:min_idx+1].min()
            if recent_low > old_low:
                result['score'] += 6
                result['signals'].append('HIGHER_LOW')

    result['score'] = min(20, result['score'])
    return result


def _check_supply_v8(df: pd.DataFrame, investor_data: Optional[Dict]) -> Dict:
    """
    수급 분석 (최대 15점)
    """
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]

    # 1. OBV 다이버전스 (가격 하락 but OBV 상승) - 최대 8점
    if len(df) >= 20:
        recent_20 = df.tail(20)
        price_change = (curr['Close'] - recent_20.iloc[0]['Close']) / recent_20.iloc[0]['Close'] * 100
        obv_change = (curr['obv'] - recent_20.iloc[0]['obv'])

        # 가격은 하락했는데 OBV는 상승 = 매집 신호
        if price_change < -5 and obv_change > 0:
            result['score'] += 8
            result['signals'].append('OBV_BULLISH_DIVERGENCE')
        elif price_change < 0 and obv_change > 0:
            result['score'] += 4
            result['signals'].append('OBV_MILD_DIVERGENCE')

    # 2. OBV 상승세 (최대 4점)
    obv_slope = _calculate_obv_slope(df, 10)
    if obv_slope > 3:
        result['score'] += 4
        result['signals'].append('OBV_RISING')
    elif obv_slope > 0:
        result['score'] += 2
        result['signals'].append('OBV_POSITIVE')

    # 3. 기관/외국인 수급 (최대 3점)
    if investor_data:
        foreign_net = investor_data.get('foreign_net', 0)
        inst_net = investor_data.get('institution_net', 0)

        if foreign_net > 0 or inst_net > 0:
            result['score'] += 3
            result['signals'].append('INST_OR_FOREIGN_BUY')

    result['score'] = min(15, result['score'])
    return result


def _check_warnings_v8(df: pd.DataFrame) -> List[str]:
    """경고 신호"""
    warnings = []

    curr = df.iloc[-1]

    # 거래대금 중간
    trading_value = curr['Close'] * curr['Volume']
    if 500_000_000 <= trading_value < 1_000_000_000:
        warnings.append('MODERATE_LIQUIDITY')

    # 3~4일 연속 음봉
    recent_5 = df.tail(5)
    down_days = sum(1 for i in range(len(recent_5)) if recent_5.iloc[i]['Close'] < recent_5.iloc[i]['Open'])
    if 3 <= down_days <= 4:
        warnings.append('CONSECUTIVE_DOWN_DAYS')

    # MA60 많이 아래
    if pd.notna(curr['ma60']) and curr['Close'] < curr['ma60'] * 0.9:
        warnings.append('FAR_BELOW_MA60')

    return warnings


def _calculate_exit_strategy_v8(df: pd.DataFrame, score: int) -> Dict:
    """V8 청산 전략"""
    curr = df.iloc[-1]
    atr = curr['atr']
    close = curr['Close']

    # 점수에 따라 목표가/손절가 조정
    if score >= 70:
        target_mult = 1.8
        stop_mult = 0.9
        hold_days = 4
    elif score >= 55:
        target_mult = 1.5
        stop_mult = 0.8
        hold_days = 3
    elif score >= 45:
        target_mult = 1.3
        stop_mult = 0.7
        hold_days = 3
    else:
        target_mult = 1.0
        stop_mult = 0.6
        hold_days = 2

    target_price = close + (atr * target_mult)
    stop_price = close - (atr * stop_mult)
    trailing_trigger = close + (atr * 0.5)

    return {
        'entry_price': close,
        'target_price': round(target_price, 2),
        'stop_price': round(stop_price, 2),
        'target_pct': round((target_price - close) / close * 100, 2),
        'stop_pct': round((stop_price - close) / close * 100, 2),
        'risk_reward': round(target_mult / stop_mult, 2),
        'max_hold_days': hold_days,
        'trailing_trigger': round(trailing_trigger, 2),
        'atr': round(atr, 2),
        'atr_pct': round(atr / close * 100, 2),
    }


# ============================================================
# 헬퍼 함수들
# ============================================================

def _detect_vcp_pattern(df: pd.DataFrame) -> Dict:
    """VCP 패턴 감지"""
    result = {'detected': False}

    if len(df) < 40:
        return result

    try:
        recent = df.tail(40)

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

        range_contraction = ranges[3]['range'] < ranges[0]['range'] * 0.7
        lows_rising = ranges[3]['low'] > ranges[0]['low']
        vol_contraction = ranges[2]['vol'] < ranges[0]['vol'] * 0.7

        if range_contraction and lows_rising and vol_contraction:
            result['detected'] = True
    except:
        pass

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

def simulate_trade_v8(
    df: pd.DataFrame,
    entry_idx: int,
    exit_strategy: Dict,
    max_days: int = 3
) -> Dict:
    """V8 거래 시뮬레이션"""
    if entry_idx + 1 >= len(df):
        return {'success': False, 'reason': 'NO_DATA'}

    entry_day = df.iloc[entry_idx + 1]
    entry_price = entry_day['Open']

    prev_close = df.iloc[entry_idx]['Close']
    gap_pct = (entry_price - prev_close) / prev_close * 100
    if gap_pct >= 10:
        return {'success': False, 'reason': 'GAP_UP_SKIP', 'gap_pct': gap_pct}

    atr = df.iloc[entry_idx]['atr']
    target_price = entry_price + (atr * 1.5)
    stop_price = entry_price - (atr * 0.8)
    trailing_trigger = entry_price + (atr * 0.5)
    trailing_active = False

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

    for day in range(1, max_days + 1):
        day_idx = entry_idx + 1 + day
        if day_idx >= len(df):
            break

        day_data = df.iloc[day_idx]

        # 트레일링 스탑 활성화
        if day_data['High'] >= trailing_trigger and not trailing_active:
            trailing_active = True
            stop_price = max(stop_price, entry_price)

        # 목표가 도달
        if day_data['High'] >= target_price:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = target_price
            result['exit_reason'] = 'TARGET_HIT'
            result['hold_days'] = day
            break

        # 손절가 이탈
        if day_data['Low'] <= stop_price:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = stop_price
            result['exit_reason'] = 'TRAILING_STOP' if trailing_active else 'STOP_HIT'
            result['hold_days'] = day
            break

        # 2일차 손실 시 조기 청산
        if day >= 2 and day_data['Close'] < entry_price:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = day_data['Close']
            result['exit_reason'] = 'EARLY_EXIT'
            result['hold_days'] = day
            break

        # 마지막 날 종가 청산
        if day == max_days:
            result['exit_date'] = df.index[day_idx]
            result['exit_price'] = day_data['Close']
            result['exit_reason'] = 'TIME_EXIT'
            result['hold_days'] = day

    if result['exit_price']:
        result['pnl_pct'] = (result['exit_price'] - result['entry_price']) / result['entry_price'] * 100

    return result


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    np.random.seed(42)

    dates = pd.date_range(end='2026-01-24', periods=120, freq='D')

    base_price = 50000
    # 하락 후 반등 시나리오
    returns = np.concatenate([
        np.random.randn(80) * 0.02 - 0.005,  # 하락 추세
        np.random.randn(40) * 0.02 + 0.003   # 반등
    ])
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        'Open': prices * (1 - np.random.rand(120) * 0.01),
        'High': prices * (1 + np.random.rand(120) * 0.02),
        'Low': prices * (1 - np.random.rand(120) * 0.02),
        'Close': prices,
        'Volume': np.random.randint(100000, 1000000, 120)
    }, index=dates)

    result = calculate_score_v8(df)

    if result:
        print("=" * 60)
        print("V8 Contrarian Bounce (역발상 반등) 분석 결과")
        print("=" * 60)

        if result['disqualified']:
            print(f"\n[과락] {result['disqualify_reason']}")
        else:
            print(f"\n최종 점수: {result['score']}점")
            print(f"  - 반등 신호: {result['bounce_score']}/40")
            print(f"  - 에너지 축적: {result['energy_score']}/25")
            print(f"  - 바닥 확인: {result['bottom_score']}/20")
            print(f"  - 수급: {result['supply_score']}/15")
            print(f"  (참고) 추세: {result['trend_score']}/25, 모멘텀: {result['momentum_score']}/30")

            print(f"\n신호: {result['signals']}")
            print(f"패턴: {result['patterns']}")
            print(f"경고: {result['warnings']}")

            print(f"\n청산 전략:")
            exit_s = result['exit_strategy']
            print(f"  - 진입가: {exit_s['entry_price']:,.0f}")
            print(f"  - 목표가: {exit_s['target_price']:,.0f} (+{exit_s['target_pct']:.1f}%)")
            print(f"  - 손절가: {exit_s['stop_price']:,.0f} ({exit_s['stop_pct']:.1f}%)")
            print(f"  - 트레일링: {exit_s['trailing_trigger']:,.0f} 도달 시 본전 스탑")
            print(f"  - 최대 홀딩: {exit_s['max_hold_days']}일")
    else:
        print("분석 실패")
