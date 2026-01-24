"""
V7 스코어링 엔진 - Trend Momentum Predictor (추세 모멘텀 예측기)

V6 백테스트 분석 결과 반영:
- TARGET_HIT 비율 23.9% → 손익분기 33.1% 미달
- 경고 신호 무시로 인한 손실
- 추세 역행 진입으로 인한 손실

핵심 개선:
1. 추세 필터 추가 (60일선 위만 진입)
2. 경고 → 과락 격상 (RESISTANCE_NEARBY 등)
3. 목표가 낮춤 (ATR×2 → ×1.5)
4. 손절폭 좁힘 (ATR×1 → ×0.8)
5. 시간 손절 단축 (5일 → 3일)
6. 모멘텀 가중치 상향

점수 체계 (100점 만점):
- 추세 확인 (25점): 정배열, 이평선 위
- 모멘텀 전환 (30점): MACD, RSI, 스토캐스틱
- 에너지 축적 (25점): BB수축, ATR수축, VCP
- 수급/지지 (20점): OBV, 이평선 지지

청산 전략:
- 목표가: 진입가 + ATR × 1.5
- 손절가: 진입가 - ATR × 0.8
- 시간 손절: 최대 3일 홀딩
- 트레일링 스탑: ATR×0.5 수익 시 본전 스탑

투자 적격: 60점 이상
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List


def calculate_score_v7(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None
) -> Optional[Dict]:
    """
    V7 점수 계산 - Trend Momentum Predictor
    
    Args:
        df: OHLCV 데이터프레임 (최소 120일 권장)
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
            'trend_score': 0,
            'momentum_score': 0,
            'energy_score': 0,
            'support_score': 0,
            'signals': [],
            'patterns': [],
            'indicators': {},
            'exit_strategy': {},
            'warnings': [],
            'disqualified': False,
            'disqualify_reason': None,
            'hold_days': 3,
            'version': 'v7'
        }
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # ========== 선행 과락 체크 (필터) ==========
        disqualify = _check_disqualification_v7(df)
        if disqualify['disqualified']:
            result['disqualified'] = True
            result['disqualify_reason'] = disqualify['reasons']
            result['signals'].append('DISQUALIFIED')
            return result
        
        # 기본 지표 저장
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
        
        # ========== 1. 추세 확인 (최대 25점) ==========
        trend = _check_trend_confirmation(df)
        result['trend_score'] = trend['score']
        result['signals'].extend(trend['signals'])
        
        # ========== 2. 모멘텀 전환 (최대 30점) ==========
        momentum = _check_momentum_reversal_v7(df)
        result['momentum_score'] = momentum['score']
        result['signals'].extend(momentum['signals'])
        
        # ========== 3. 에너지 축적 (최대 25점) ==========
        energy = _check_energy_accumulation_v7(df)
        result['energy_score'] = energy['score']
        result['signals'].extend(energy['signals'])
        result['patterns'].extend(energy.get('patterns', []))
        
        # ========== 4. 수급/지지 (최대 20점) ==========
        support = _check_support_supply_v7(df, investor_data)
        result['support_score'] = support['score']
        result['signals'].extend(support['signals'])
        
        # ========== 경고 신호 ==========
        warnings = _check_warnings_v7(df)
        result['warnings'].extend(warnings)
        
        # ========== 최종 점수 ==========
        total = (result['trend_score'] + result['momentum_score'] + 
                 result['energy_score'] + result['support_score'])
        result['score'] = max(0, min(100, total))
        
        # ========== 청산 전략 계산 ==========
        result['exit_strategy'] = _calculate_exit_strategy_v7(df, result['score'])
        
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
        print(f"V7 점수 계산 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()
    
    # === 이동평균선 ===
    for p in [5, 10, 20, 60, 120]:
        df[f'ma{p}'] = df['Close'].rolling(p, min_periods=1).mean()
    
    # 이평선 상태
    df['ma_aligned'] = (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20']) & (df['ma20'] > df['ma60'])
    df['ma_partial'] = (df['Close'] > df['ma20']) & (df['ma20'] > df['ma60'])
    
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
    
    return df


def _check_disqualification_v7(df: pd.DataFrame) -> Dict:
    """
    V7 과락 조건 체크 (강화됨)
    """
    result = {'disqualified': False, 'reasons': []}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 1. 60일선 아래 (추세 역행) - NEW
    if pd.notna(curr['ma60']) and curr['Close'] < curr['ma60'] * 0.98:
        result['disqualified'] = True
        result['reasons'].append('BELOW_MA60')
    
    # 2. 강한 역배열 (5 < 10 < 20이고 20일선 아래 5% 이상)
    if curr['Close'] < curr['ma20'] * 0.95:
        if curr['ma5'] < curr['ma10'] < curr['ma20']:
            result['disqualified'] = True
            result['reasons'].append('STRONG_REVERSE_ALIGNMENT')
    
    # 3. RSI 극단적 과매수 (85 이상)
    if curr['rsi'] > 85:
        result['disqualified'] = True
        result['reasons'].append('RSI_EXTREME_OVERBOUGHT')
    
    # 4. 천장 신호 (BB 상단 이탈 + 거래량 3배)
    if curr['bb_position'] > 1.1 and curr['vol_ratio'] > 3:
        result['disqualified'] = True
        result['reasons'].append('POSSIBLE_CLIMAX_TOP')
    
    # 5. 당일 급락 (-5% 이상)
    change_pct = (curr['Close'] - prev['Close']) / prev['Close'] * 100
    if change_pct < -5:
        result['disqualified'] = True
        result['reasons'].append('SHARP_DECLINE')
    
    # 6. 상방 매물대 존재 - NEW (경고 → 과락)
    resistance = _check_nearby_resistance(df)
    if resistance['exists']:
        # 매물대가 목표가 (ATR×1.5) 이내에 있으면 과락
        atr = curr['atr']
        target_zone = curr['Close'] * 1.05  # 5% 이내
        if resistance['level'] and resistance['level'] <= target_zone:
            result['disqualified'] = True
            result['reasons'].append('RESISTANCE_IN_TARGET_ZONE')
    
    # 7. 4일 연속 음봉 - NEW (경고 → 과락)
    recent_5 = df.tail(5)
    down_days = sum(1 for i in range(len(recent_5)) if recent_5.iloc[i]['Close'] < recent_5.iloc[i]['Open'])
    if down_days >= 4:
        result['disqualified'] = True
        result['reasons'].append('CONSECUTIVE_DOWN_4DAYS')
    
    # 8. 거래대금 심각하게 부족 (10억 미만) - NEW (경고 → 과락)
    trading_value = curr['Close'] * curr['Volume']
    if trading_value < 1_000_000_000:
        result['disqualified'] = True
        result['reasons'].append('SEVERE_LOW_LIQUIDITY')
    
    return result


def _check_trend_confirmation(df: pd.DataFrame) -> Dict:
    """
    추세 확인 (최대 25점) - NEW
    """
    result = {'score': 0, 'signals': []}
    
    curr = df.iloc[-1]
    
    # 1. 완전 정배열 (5 > 10 > 20 > 60) +15점
    if curr['ma_aligned']:
        result['score'] += 15
        result['signals'].append('FULL_ALIGNMENT')
    # 부분 정배열 (Close > 20 > 60) +10점
    elif curr['ma_partial']:
        result['score'] += 10
        result['signals'].append('PARTIAL_ALIGNMENT')
    
    # 2. 20일선 위 +5점
    if pd.notna(curr['ma20']) and curr['Close'] > curr['ma20']:
        result['score'] += 5
        result['signals'].append('ABOVE_MA20')
    
    # 3. 60일선 위 +5점
    if pd.notna(curr['ma60']) and curr['Close'] > curr['ma60']:
        result['score'] += 5
        result['signals'].append('ABOVE_MA60')
    
    result['score'] = min(25, result['score'])
    return result


def _check_momentum_reversal_v7(df: pd.DataFrame) -> Dict:
    """
    모멘텀 전환 분석 (최대 30점) - 강화
    """
    result = {'score': 0, 'signals': []}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else prev
    
    # 1. MACD 골든크로스 +10점
    if curr['macd'] > curr['macd_signal'] and prev['macd'] <= prev['macd_signal']:
        result['score'] += 10
        result['signals'].append('MACD_GOLDEN_CROSS')
    # MACD 히스토그램 상승 전환 +6점
    elif curr['macd_hist'] > 0 and prev['macd_hist'] <= 0:
        result['score'] += 6
        result['signals'].append('MACD_HIST_CROSS_UP')
    # MACD 히스토그램 상승 중 +3점
    elif curr['macd_hist'] > prev['macd_hist'] > prev2['macd_hist']:
        result['score'] += 3
        result['signals'].append('MACD_HIST_RISING')
    
    # 2. RSI 과매도 탈출 +8점
    if curr['rsi'] > 30 and prev['rsi'] <= 30:
        result['score'] += 8
        result['signals'].append('RSI_OVERSOLD_EXIT')
    # RSI 상승 전환 (30~50 구간에서) +4점
    elif 30 < curr['rsi'] < 50 and curr['rsi'] > prev['rsi']:
        result['score'] += 4
        result['signals'].append('RSI_TURNING_UP')
    
    # 3. 스토캐스틱 바닥권 골든크로스 +7점
    stoch_cross = (curr['stoch_k'] > curr['stoch_d'] and 
                   prev['stoch_k'] <= prev['stoch_d'])
    
    if stoch_cross and curr['stoch_k'] < 30:
        result['score'] += 7
        result['signals'].append('STOCH_GOLDEN_OVERSOLD')
    elif stoch_cross and curr['stoch_k'] < 50:
        result['score'] += 4
        result['signals'].append('STOCH_GOLDEN')
    
    # 4. 거래량 급증 양봉 +5점
    if (curr['Close'] > curr['Open'] and 
        curr['vol_ratio'] > 2.0 and 
        curr['Close'] > prev['Close']):
        result['score'] += 5
        result['signals'].append('VOLUME_SURGE_BULLISH')
    
    result['score'] = min(30, result['score'])
    return result


def _check_energy_accumulation_v7(df: pd.DataFrame) -> Dict:
    """
    에너지 축적 분석 (최대 25점) - 조정
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
        result['signals'].append('ATR_CONTRACTION')
    elif atr_ratio < 0.85:
        result['score'] += 4
        result['signals'].append('ATR_SHRINKING')
    
    # 3. VCP 패턴 (최대 7점)
    vcp = _detect_vcp_pattern(df)
    if vcp['detected']:
        result['score'] += 7
        result['signals'].append('VCP_PATTERN')
        result['patterns'].append('VCP')
    
    result['score'] = min(25, result['score'])
    return result


def _check_support_supply_v7(df: pd.DataFrame, investor_data: Optional[Dict]) -> Dict:
    """
    수급/지지 분석 (최대 20점)
    """
    result = {'score': 0, 'signals': []}
    
    curr = df.iloc[-1]
    
    # 1. OBV 상승 (최대 8점)
    obv_change = _calculate_obv_slope(df, 10)
    if obv_change > 5:
        result['score'] += 8
        result['signals'].append('OBV_STRONG_RISING')
    elif obv_change > 0:
        result['score'] += 4
        result['signals'].append('OBV_RISING')
    
    # 2. 이평선 지지 (최대 7점)
    ma_support = _check_ma_support(df)
    if ma_support['ma20_support']:
        result['score'] += 4
        result['signals'].append('MA20_SUPPORT')
    if ma_support['ma60_support']:
        result['score'] += 3
        result['signals'].append('MA60_SUPPORT')
    
    # 3. 기관/외국인 수급 (최대 5점)
    if investor_data:
        foreign_net = investor_data.get('foreign_net', 0)
        inst_net = investor_data.get('institution_net', 0)
        
        if foreign_net > 0 and inst_net > 0:
            result['score'] += 5
            result['signals'].append('INST_FOREIGN_BOTH_BUY')
        elif foreign_net > 0 or inst_net > 0:
            result['score'] += 3
            result['signals'].append('INST_OR_FOREIGN_BUY')
    
    result['score'] = min(20, result['score'])
    return result


def _check_warnings_v7(df: pd.DataFrame) -> List[str]:
    """
    경고 신호 체크 (정보성, 과락은 아님)
    """
    warnings = []
    
    curr = df.iloc[-1]
    
    # 1. 거래대금 적당히 부족 (10~20억)
    trading_value = curr['Close'] * curr['Volume']
    if 1_000_000_000 <= trading_value < 2_000_000_000:
        warnings.append('MODERATE_LOW_LIQUIDITY')
    
    # 2. 20일 급등 후
    recent_20 = df.tail(20)
    change_20d = (curr['Close'] - recent_20.iloc[0]['Close']) / recent_20.iloc[0]['Close'] * 100
    if change_20d > 30:
        warnings.append('OVEREXTENDED_20D')
    
    # 3. 2~3일 연속 음봉
    recent_5 = df.tail(5)
    down_days = sum(1 for i in range(len(recent_5)) if recent_5.iloc[i]['Close'] < recent_5.iloc[i]['Open'])
    if down_days == 3:
        warnings.append('CONSECUTIVE_DOWN_3DAYS')
    
    return warnings


def _calculate_exit_strategy_v7(df: pd.DataFrame, score: int) -> Dict:
    """
    V7 청산 전략 계산 (개선)
    """
    curr = df.iloc[-1]
    atr = curr['atr']
    close = curr['Close']
    
    # V7: 목표 낮춤, 손절 좁힘, 기간 단축
    if score >= 80:
        target_mult = 1.8
        stop_mult = 0.9
        hold_days = 4
    elif score >= 70:
        target_mult = 1.5
        stop_mult = 0.8
        hold_days = 3
    elif score >= 60:
        target_mult = 1.3
        stop_mult = 0.7
        hold_days = 3
    else:
        target_mult = 1.0
        stop_mult = 0.6
        hold_days = 2
    
    target_price = close + (atr * target_mult)
    stop_price = close - (atr * stop_mult)
    
    # 트레일링 스탑 레벨 (ATR×0.5 수익 시 본전)
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


def _check_nearby_resistance(df: pd.DataFrame) -> Dict:
    """상방 매물대 체크"""
    result = {'exists': False, 'level': None}
    
    if len(df) < 60:
        return result
    
    curr = df.iloc[-1]
    close = curr['Close']
    
    recent = df.tail(60)
    high_vol_days = recent[recent['vol_ratio'] > 2.0]
    
    upper_bound = close * 1.08  # 8% 이내
    
    for idx, row in high_vol_days.iterrows():
        if close < row['High'] <= upper_bound:
            result['exists'] = True
            result['level'] = row['High']
            break
    
    return result


def _check_ma_support(df: pd.DataFrame) -> Dict:
    """이평선 지지 체크"""
    result = {
        'ma20_support': False,
        'ma60_support': False,
    }
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    close = curr['Close']
    low = curr['Low']
    
    ma20 = curr['ma20']
    if pd.notna(ma20):
        touch_ma20 = low <= ma20 * 1.02 and close >= ma20 * 0.98
        if touch_ma20:
            result['ma20_support'] = True
    
    ma60 = curr['ma60']
    if pd.notna(ma60):
        touch_ma60 = low <= ma60 * 1.03 and close >= ma60 * 0.97
        if touch_ma60:
            result['ma60_support'] = True
    
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

def simulate_trade_v7(
    df: pd.DataFrame,
    entry_idx: int,
    exit_strategy: Dict,
    max_days: int = 3
) -> Dict:
    """
    V7 거래 시뮬레이션 (트레일링 스탑 포함)
    """
    if entry_idx + 1 >= len(df):
        return {'success': False, 'reason': 'NO_DATA'}
    
    entry_day = df.iloc[entry_idx + 1]
    entry_price = entry_day['Open']
    
    prev_close = df.iloc[entry_idx]['Close']
    gap_pct = (entry_price - prev_close) / prev_close * 100
    if gap_pct >= 10:  # 갭업 10% 이상 스킵 (낮춤)
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
        
        # 트레일링 스탑 활성화 체크
        if day_data['High'] >= trailing_trigger and not trailing_active:
            trailing_active = True
            stop_price = max(stop_price, entry_price)  # 본전 스탑
        
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
    returns = np.random.randn(120) * 0.02
    prices = base_price * np.cumprod(1 + returns)
    
    df = pd.DataFrame({
        'Open': prices * (1 - np.random.rand(120) * 0.01),
        'High': prices * (1 + np.random.rand(120) * 0.02),
        'Low': prices * (1 - np.random.rand(120) * 0.02),
        'Close': prices,
        'Volume': np.random.randint(100000, 1000000, 120)
    }, index=dates)
    
    result = calculate_score_v7(df)
    
    if result:
        print("=" * 60)
        print("V7 Trend Momentum Predictor 분석 결과")
        print("=" * 60)
        
        if result['disqualified']:
            print(f"\n❌ 과락: {result['disqualify_reason']}")
        else:
            print(f"\n최종 점수: {result['score']}점")
            print(f"  - 추세 확인: {result['trend_score']}/25")
            print(f"  - 모멘텀 전환: {result['momentum_score']}/30")
            print(f"  - 에너지 축적: {result['energy_score']}/25")
            print(f"  - 수급/지지: {result['support_score']}/20")
            
            print(f"\n신호: {result['signals']}")
            print(f"패턴: {result['patterns']}")
            print(f"경고: {result['warnings']}")
            
            print(f"\n청산 전략:")
            exit_s = result['exit_strategy']
            print(f"  - 진입가: {exit_s['entry_price']:,.0f}")
            print(f"  - 목표가: {exit_s['target_price']:,.0f} (+{exit_s['target_pct']:.1f}%)")
            print(f"  - 손절가: {exit_s['stop_price']:,.0f} ({exit_s['stop_pct']:.1f}%)")
            print(f"  - 손익비: {exit_s['risk_reward']:.1f}")
            print(f"  - 트레일링: {exit_s['trailing_trigger']:,.0f} 도달 시 본전 스탑")
            print(f"  - 최대 홀딩: {exit_s['max_hold_days']}일")
    else:
        print("분석 실패")
