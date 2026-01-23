"""
V5 스코어링 엔진 - 장대양봉 (Long Bullish Candle)

핵심 원리:
- "거래량은 주가의 선행 지표" - 세력의 매집과 이탈을 거래량으로 추적
- "에너지의 응축 후 발산" - 횡보/수축 구간 후 폭발적 상승 패턴 포착

스크리닝 기법 (6가지):
1. 거래량 급감 눌림목 (N자형 상승 패턴)
2. 볼린저 밴드 수축 후 돌파 준비
3. 이동평균선 밀집 정배열
4. OBV 다이버전스 (매집 신호)
5. RSI/MACD/스토캐스틱 모멘텀 신호
6. 매물대 분석
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List


def calculate_score_v5(df: pd.DataFrame) -> Optional[Dict]:
    """
    V5 스코어 계산 - 장대양봉 가능성 분석

    Args:
        df: OHLCV 데이터프레임 (최소 60일)

    Returns:
        점수 및 분석 결과 딕셔너리
    """
    if df is None or len(df) < 60:
        return None

    try:
        df = df.copy()

        # 기본 지표 계산
        df = _calculate_indicators(df)

        result = {
            'score': 0,
            'raw_score': 0,
            'pullback_score': 0,
            'bollinger_score': 0,
            'ma_score': 0,
            'obv_score': 0,
            'momentum_score': 0,
            'resistance_score': 0,
            'trend_score': 0,
            'signals': [],
            'patterns': [],
            'indicators': {},
            'warnings': [],
            'version': 'v5'
        }

        today = df.iloc[-1]

        # 기본 지표 저장
        result['indicators'] = {
            'close': today['Close'],
            'change_pct': today['candle_body_pct'],
            'volume': today['Volume'],
            'volume_ratio': today['vol_ratio'],
            'rsi': today['rsi'],
            'macd_hist': today['macd_hist'],
            'bb_width': today['bb_width'],
            'bb_position': today['bb_position'],
            'ma_convergence': today['ma_convergence'],
        }

        # 1. 눌림목 패턴 분석 (최대 30점)
        pullback = _check_pullback_pattern(df)
        result['pullback_score'] = pullback['score']
        result['raw_score'] += pullback['score']
        result['signals'].extend(pullback['signals'])
        if pullback['pattern_found']:
            result['patterns'].append('PULLBACK_PATTERN')

        # 2. 볼린저 밴드 분석 (최대 25점)
        bollinger = _check_bollinger_squeeze(df)
        result['bollinger_score'] = bollinger['score']
        result['raw_score'] += bollinger['score']
        result['signals'].extend(bollinger['signals'])
        if bollinger.get('breakout_ready'):
            result['patterns'].append('BB_BREAKOUT_READY')

        # 3. 이동평균선 분석 (최대 25점)
        ma = _check_ma_convergence(df)
        result['ma_score'] = ma['score']
        result['raw_score'] += ma['score']
        result['signals'].extend(ma['signals'])
        if ma.get('tight_aligned'):
            result['patterns'].append('MA_TIGHT_ALIGNED')

        # 4. OBV 다이버전스 분석 (최대 20점)
        obv = _check_obv_divergence(df)
        result['obv_score'] = obv['score']
        result['raw_score'] += obv['score']
        result['signals'].extend(obv['signals'])
        if obv.get('accumulation'):
            result['patterns'].append('OBV_ACCUMULATION')

        # 5. 모멘텀 신호 분석 (최대 25점)
        momentum = _check_momentum_signals(df)
        result['momentum_score'] = momentum['score']
        result['raw_score'] += momentum['score']
        result['signals'].extend(momentum['signals'])

        # 6. 매물대 분석 (최대 10점)
        resistance = _check_resistance(df)
        result['resistance_score'] = resistance['score']
        result['raw_score'] += resistance['score']
        result['signals'].extend(resistance['signals'])

        # 7. 추세 분석 (최대 10점)
        trend = _check_trend(df)
        result['trend_score'] = trend['score']
        result['raw_score'] += trend['score']
        result['signals'].extend(trend['signals'])
        result['warnings'].extend(trend.get('warnings', []))

        # 최종 점수 스케일링 (0-100)
        # 최대 raw_score = 30+25+25+20+25+10+10 = 145
        raw = result['raw_score']
        if raw <= 50:
            scaled = int(raw * 0.8)  # 0-40
        elif raw <= 90:
            scaled = 40 + int((raw - 50) * 1.0)  # 40-80
        else:
            scaled = 80 + int((raw - 90) * 0.4)  # 80-100

        result['score'] = max(0, min(100, scaled))

        return result

    except Exception as e:
        return None


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()

    # === 캔들 정보 ===
    df['candle_body'] = df['Close'] - df['Open']
    df['candle_body_pct'] = (df['Close'] - df['Open']) / df['Open'] * 100
    df['candle_range'] = df['High'] - df['Low']
    df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']

    # 장대양봉 기준: +7% 이상
    df['is_long_bullish'] = (df['candle_body_pct'] >= 7) & (df['candle_body'] > 0)
    df['is_doji'] = abs(df['candle_body_pct']) < 0.5

    # === 거래량 지표 ===
    df['vol_ma5'] = df['Volume'].rolling(5).mean()
    df['vol_ma20'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_ma20']
    df['vol_surge'] = df['Volume'] > df['Volume'].shift(1) * 2.0  # 2배 이상 폭증
    df['vol_shrink'] = df['Volume'] < df['Volume'].shift(1) * 0.5  # 50% 이하 급감

    # === 이동평균선 ===
    for p in [5, 10, 20, 60, 120]:
        df[f'ma{p}'] = df['Close'].rolling(p).mean()

    df['ma_aligned'] = (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20'])
    df['ma_convergence'] = df[['ma5', 'ma10', 'ma20']].std(axis=1) / df['Close'] * 100
    df['golden_cross_5_10'] = (df['ma5'] > df['ma10']) & (df['ma5'].shift(1) <= df['ma10'].shift(1))
    df['golden_cross_5_20'] = (df['ma5'] > df['ma20']) & (df['ma5'].shift(1) <= df['ma20'].shift(1))
    df['golden_cross_20_60'] = (df['ma20'] > df['ma60']) & (df['ma20'].shift(1) <= df['ma60'].shift(1))

    # === 볼린저 밴드 ===
    df['bb_middle'] = df['Close'].rolling(20).mean()
    df['bb_std'] = df['Close'].rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + df['bb_std'] * 2
    df['bb_lower'] = df['bb_middle'] - df['bb_std'] * 2
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
    df['bb_width_ma'] = df['bb_width'].rolling(20).mean()
    df['bb_position'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    df['bb_squeeze'] = df['bb_width'] < df['bb_width_ma']

    # === OBV ===
    df['obv'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    df['obv_ma20'] = df['obv'].rolling(20).mean()
    df['obv_trend'] = df['obv'] > df['obv_ma20']

    # === RSI ===
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))
    df['rsi_oversold_exit'] = (df['rsi'] > 30) & (df['rsi'].shift(1) <= 30)

    # === MACD ===
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    df['macd_golden_cross'] = (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1))
    df['macd_hist_positive'] = (df['macd_hist'] > 0) & (df['macd_hist'].shift(1) <= 0)

    # === 스토캐스틱 ===
    low14 = df['Low'].rolling(14).min()
    high14 = df['High'].rolling(14).max()
    df['stoch_k'] = 100 * (df['Close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    df['stoch_golden_cross'] = (df['stoch_k'] > df['stoch_d']) & (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1))

    # === 추세 ===
    df['uptrend'] = df['Close'] > df['ma20']
    df['strong_uptrend'] = df['uptrend'] & (df['ma20'] > df['ma60'])
    df['downtrend'] = df['Close'] < df['ma20']

    return df


def _find_recent_long_bullish(df: pd.DataFrame, days: int = 5) -> List[Dict]:
    """최근 N일 내 장대양봉 + 거래량 폭증 발생 확인"""
    events = []
    recent = df.tail(days + 1).head(days)

    for idx, row in recent.iterrows():
        # 장대양봉(+7%) + 거래량 2배 이상
        if row['is_long_bullish'] and row['vol_ratio'] >= 2.0:
            events.append({
                'date': idx,
                'close': row['Close'],
                'open': row['Open'],
                'change_pct': row['candle_body_pct'],
                'vol_ratio': row['vol_ratio'],
                'fib_38': row['Close'] - (row['Close'] - row['Open']) * 0.382,
                'fib_50': (row['Open'] + row['Close']) / 2,
                'fib_62': row['Close'] - (row['Close'] - row['Open']) * 0.618,
            })
    return events


def _check_pullback_pattern(df: pd.DataFrame) -> Dict:
    """눌림목 패턴 확인 (N자형 상승) - 최대 30점"""
    result = {'score': 0, 'signals': [], 'pattern_found': False}

    events = _find_recent_long_bullish(df, 5)
    if not events:
        return result

    today = df.iloc[-1]
    best_score = 0
    best_signals = []

    for event in events:
        score = 0
        signals = []

        # 1. 거래량 급감 (8점)
        if today['vol_ratio'] < 0.8:
            score += 8
            signals.append('VOL_SHRINK_PULLBACK')

        # 2. 단봉 캔들 (7점)
        if abs(today['candle_body_pct']) < 3:
            score += 7
            signals.append('SMALL_CANDLE')

        # 3. 피보나치 지지 (최대 10점)
        price = today['Close']
        if price >= event['fib_38']:
            score += 10
            signals.append('FIB_38_SUPPORT')
        elif price >= event['fib_50']:
            score += 8
            signals.append('FIB_50_SUPPORT')
        elif price >= event['fib_62']:
            score += 5
            signals.append('FIB_62_SUPPORT')

        # 4. OBV 상승 유지 (5점)
        if today['obv_trend']:
            score += 5
            signals.append('OBV_RISING_PULLBACK')

        if score > best_score:
            best_score = score
            best_signals = signals

    result['score'] = min(30, best_score)
    result['signals'] = best_signals
    result['pattern_found'] = best_score >= 15

    return result


def _check_bollinger_squeeze(df: pd.DataFrame) -> Dict:
    """볼린저 밴드 수축 패턴 - 최대 25점"""
    result = {'score': 0, 'signals': [], 'breakout_ready': False}

    today = df.iloc[-1]

    # 1. 극심한 밴드 수축 (10점)
    if today['bb_width'] < today['bb_width_ma'] * 0.7:
        result['score'] += 10
        result['signals'].append('BB_EXTREME_SQUEEZE')
    elif today['bb_squeeze']:
        result['score'] += 6
        result['signals'].append('BB_SQUEEZE')

    # 2. 상단 근접 (8점)
    if today['bb_position'] > 0.8:
        result['score'] += 8
        result['signals'].append('BB_UPPER_ZONE')
    elif today['bb_position'] > 0.7:
        result['score'] += 5
        result['signals'].append('BB_HIGH_ZONE')

    # 3. 돌파 준비 (7점)
    if today['bb_squeeze'] and today['bb_position'] > 0.7:
        result['score'] += 7
        result['signals'].append('BB_BREAKOUT_READY')
        result['breakout_ready'] = True

    result['score'] = min(25, result['score'])
    return result


def _check_ma_convergence(df: pd.DataFrame) -> Dict:
    """이동평균선 밀집 및 정배열 - 최대 25점"""
    result = {'score': 0, 'signals': [], 'tight_aligned': False}

    today = df.iloc[-1]

    # 1. 정배열 (8점)
    if today['ma_aligned']:
        result['score'] += 8
        result['signals'].append('MA_ALIGNED')

    # 2. 밀집 (7점)
    if today['ma_convergence'] < 2:
        result['score'] += 7
        result['signals'].append('MA_TIGHT')
        if today['ma_aligned']:
            result['tight_aligned'] = True

    # 3. 골든크로스 (최대 10점)
    if today['golden_cross_5_10']:
        result['score'] += 5
        result['signals'].append('GOLDEN_CROSS_5_10')
    if today['golden_cross_5_20']:
        result['score'] += 5
        result['signals'].append('GOLDEN_CROSS_5_20')

    # 4. 20일선/60일선 위 (3점)
    if today['Close'] > today['ma20']:
        result['score'] += 2
    if pd.notna(today['ma60']) and today['Close'] > today['ma60']:
        result['score'] += 1

    result['score'] = min(25, result['score'])
    return result


def _check_obv_divergence(df: pd.DataFrame, lookback: int = 10) -> Dict:
    """OBV 다이버전스 (매집 신호) - 최대 20점"""
    result = {'score': 0, 'signals': [], 'accumulation': False}

    recent = df.tail(lookback)
    today = df.iloc[-1]

    price_change = (recent['Close'].iloc[-1] - recent['Close'].iloc[0]) / recent['Close'].iloc[0] * 100
    obv_change = recent['obv'].iloc[-1] - recent['obv'].iloc[0]

    # 1. 강한 다이버전스 (12점)
    if price_change < -3 and obv_change > 0:
        result['score'] += 12
        result['signals'].append('OBV_STRONG_DIV')
        result['accumulation'] = True
    # 2. 일반 다이버전스 (8점)
    elif price_change <= 0 and obv_change > 0:
        result['score'] += 8
        result['signals'].append('OBV_DIVERGENCE')
        result['accumulation'] = True

    # 3. OBV 상승 추세 (5점)
    if today['obv_trend']:
        result['score'] += 5
        result['signals'].append('OBV_UPTREND')

    # 4. OBV 급증 (3점)
    obv_5d = df['obv'].tail(5)
    if len(obv_5d) >= 5 and obv_5d.iloc[-1] > obv_5d.iloc[0] * 1.1:
        result['score'] += 3
        result['signals'].append('OBV_SURGE')

    result['score'] = min(20, result['score'])
    return result


def _check_momentum_signals(df: pd.DataFrame) -> Dict:
    """RSI, MACD, 스토캐스틱 신호 - 최대 25점"""
    result = {'score': 0, 'signals': []}

    today = df.iloc[-1]

    # 1. RSI 과매도 탈출 (8점)
    if today['rsi_oversold_exit']:
        result['score'] += 8
        result['signals'].append('RSI_OVERSOLD_EXIT')
    elif 40 <= today['rsi'] <= 60:
        result['score'] += 3
        result['signals'].append('RSI_NEUTRAL')

    # 2. MACD 골든크로스 (8점)
    if today['macd_golden_cross']:
        result['score'] += 8
        result['signals'].append('MACD_GOLDEN_CROSS')

    # 3. MACD 히스토그램 양전환 (5점)
    if today['macd_hist_positive']:
        result['score'] += 5
        result['signals'].append('MACD_HIST_POSITIVE')

    # 4. 스토캐스틱 골든크로스 (5점)
    if today['stoch_golden_cross']:
        result['score'] += 5
        result['signals'].append('STOCH_GOLDEN_CROSS')

    # 5. 스토캐스틱 과매도 영역 탈출 (3점)
    if today['stoch_k'] > 20 and df.iloc[-2]['stoch_k'] <= 20:
        result['score'] += 3
        result['signals'].append('STOCH_OVERSOLD_EXIT')

    result['score'] = min(25, result['score'])
    return result


def _check_resistance(df: pd.DataFrame) -> Dict:
    """매물대(저항선) 분석 - 최대 10점"""
    result = {'score': 0, 'signals': []}

    today = df.iloc[-1]
    recent = df.tail(60)

    # 상방 5% 범위 내 고거래량 저항선 확인
    upper_range = today['Close'] * 1.05
    high_vol = recent[recent['vol_ratio'] > 1.5]

    nearby_resistance = False
    for _, row in high_vol.iterrows():
        if today['Close'] < row['High'] <= upper_range:
            nearby_resistance = True
            break

    # 1. 상방 매물대 없음 (6점)
    if not nearby_resistance:
        result['score'] += 6
        result['signals'].append('NO_RESISTANCE')

    # 2. 고점 근접도 (4점)
    distance_to_high = (recent['High'].max() - today['Close']) / today['Close'] * 100
    if distance_to_high < 5:
        result['score'] += 4
        result['signals'].append('NEAR_HIGH')
    elif distance_to_high < 10:
        result['score'] += 2

    result['score'] = min(10, result['score'])
    return result


def _check_trend(df: pd.DataFrame) -> Dict:
    """추세 분석 - 최대 10점"""
    result = {'score': 0, 'signals': [], 'warnings': []}

    today = df.iloc[-1]
    recent20 = df.tail(20)

    change_20d = (today['Close'] - recent20['Close'].iloc[0]) / recent20['Close'].iloc[0] * 100

    # 1. 강한 상승 추세 (6점)
    if today['strong_uptrend']:
        result['score'] += 6
        result['signals'].append('STRONG_UPTREND')
    elif today['uptrend']:
        result['score'] += 4
        result['signals'].append('UPTREND')

    # 2. SMA20 기울기 상승 (4점)
    sma20_slope = (today['ma20'] - df.iloc[-5]['ma20']) / df.iloc[-5]['ma20'] * 100
    if sma20_slope > 1:
        result['score'] += 4
        result['signals'].append('SMA20_RISING')
    elif sma20_slope > 0:
        result['score'] += 2

    # 경고 신호
    if today['downtrend']:
        result['warnings'].append('DOWNTREND_WARNING')
    if change_20d > 15:
        result['warnings'].append('OVERHEATED_20D')
    if change_20d < -10:
        result['warnings'].append('OVERSOLD_20D')

    result['score'] = min(10, result['score'])
    return result
