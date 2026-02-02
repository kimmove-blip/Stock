"""
공통 지표 계산 모듈

목적:
- 스코어링 버전 간 지표 재계산 중복 제거
- LRU 캐시로 성능 최적화
- 표준화된 지표 계산 인터페이스

사용법:
    from scoring.indicators import calculate_base_indicators, IndicatorCache

    # 기본 지표 계산 (캐시 없음)
    df_with_indicators = calculate_base_indicators(df)

    # 캐시 사용 (배치 처리 시)
    cache = IndicatorCache(maxsize=100)
    df_with_indicators = cache.get_or_calculate(stock_code, df)
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from functools import lru_cache
from typing import Dict, Optional, Tuple
from datetime import datetime
from collections import OrderedDict
from dataclasses import dataclass, field


@dataclass
class IndicatorResult:
    """지표 계산 결과"""
    df: pd.DataFrame
    computed_at: datetime = field(default_factory=datetime.now)
    indicators_list: list = field(default_factory=list)

    def is_stale(self, max_age_seconds: int = 300) -> bool:
        """데이터 유효성 검사 (기본 5분)"""
        elapsed = (datetime.now() - self.computed_at).total_seconds()
        return elapsed > max_age_seconds


class IndicatorCache:
    """LRU 캐시로 지표 재계산 방지

    사용 예:
        cache = IndicatorCache(maxsize=500)

        # 배치 처리
        for code, df in stocks.items():
            df_ind = cache.get_or_calculate(code, df)
            # ... 스코어 계산

        # 캐시 상태 확인
        print(f"Hit rate: {cache.hit_rate:.1%}")
    """

    def __init__(self, maxsize: int = 500, ttl_seconds: int = 300):
        """
        Args:
            maxsize: 최대 캐시 항목 수
            ttl_seconds: 캐시 유효 시간 (초)
        """
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, IndicatorResult] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get_or_calculate(
        self,
        key: str,
        df: pd.DataFrame,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """캐시에서 조회하거나 새로 계산

        Args:
            key: 캐시 키 (종목코드)
            df: OHLCV DataFrame
            force_refresh: 강제 재계산 여부

        Returns:
            지표가 추가된 DataFrame
        """
        # 캐시 히트 확인
        if not force_refresh and key in self._cache:
            cached = self._cache[key]
            if not cached.is_stale(self.ttl_seconds):
                self._hits += 1
                # LRU 순서 갱신
                self._cache.move_to_end(key)
                return cached.df

        # 캐시 미스: 계산
        self._misses += 1
        df_with_indicators = calculate_base_indicators(df)

        # 캐시 저장
        self._cache[key] = IndicatorResult(
            df=df_with_indicators,
            indicators_list=list(df_with_indicators.columns)
        )
        self._cache.move_to_end(key)

        # 크기 제한 적용
        while len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

        return df_with_indicators

    def invalidate(self, key: str) -> bool:
        """특정 키 무효화"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """전체 캐시 초기화"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        """캐시 히트율"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> Dict:
        """캐시 통계"""
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


def calculate_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기본 기술적 지표 일괄 계산

    계산되는 지표:
    - 이동평균선: SMA_5, SMA_10, SMA_20, SMA_60, SMA_120
    - RSI: RSI (14일)
    - MACD: MACD, MACDs, MACDh
    - 볼린저밴드: BBL, BBM, BBU, BB_WIDTH, BB_POSITION
    - 거래량: VOL_MA5, VOL_MA20, VOL_RATIO
    - OBV: OBV, OBV_MA
    - ATR: ATR
    - Supertrend: SUPERTREND, SUPERTRENDd
    - Stochastic: STOCH_K, STOCH_D
    - StochRSI: STOCHRSI_K, STOCHRSI_D

    Args:
        df: OHLCV DataFrame (컬럼: Open, High, Low, Close, Volume)

    Returns:
        지표가 추가된 DataFrame
    """
    if df is None or len(df) < 20:
        return df

    df = df.copy()

    # === 이동평균선 ===
    df['SMA_5'] = ta.sma(df['Close'], length=5)
    df['SMA_10'] = ta.sma(df['Close'], length=10)
    df['SMA_20'] = ta.sma(df['Close'], length=20)
    df['SMA_60'] = ta.sma(df['Close'], length=60)
    df['SMA_120'] = ta.sma(df['Close'], length=120)

    # 이평선 정배열/역배열 상태
    if len(df) >= 60:
        df['MA_ALIGNED'] = (
            (df['SMA_5'] > df['SMA_20']) &
            (df['SMA_20'] > df['SMA_60'])
        )
        df['MA_REVERSE_ALIGNED'] = (
            (df['SMA_5'] < df['SMA_20']) &
            (df['SMA_20'] < df['SMA_60'])
        )

    # 20일선 기울기 (5일 변화율)
    if len(df) >= 6:
        df['SMA20_SLOPE'] = (df['SMA_20'] - df['SMA_20'].shift(5)) / df['SMA_20'].shift(5) * 100

    # === RSI ===
    df['RSI'] = ta.rsi(df['Close'], length=14)

    # === MACD ===
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    if macd is not None:
        # 컬럼명 표준화
        macd_cols = macd.columns.tolist()
        for col in macd_cols:
            if 'MACD_' in col and 'MACDh' not in col and 'MACDs' not in col:
                df['MACD'] = macd[col]
            elif 'MACDs_' in col:
                df['MACDs'] = macd[col]
            elif 'MACDh_' in col:
                df['MACDh'] = macd[col]

    # === 볼린저밴드 ===
    bb = ta.bbands(df['Close'], length=20, std=2)
    if bb is not None:
        bb_cols = bb.columns.tolist()
        for col in bb_cols:
            if 'BBL_' in col:
                df['BBL'] = bb[col]
            elif 'BBM_' in col:
                df['BBM'] = bb[col]
            elif 'BBU_' in col:
                df['BBU'] = bb[col]
            elif 'BBB_' in col:  # Bandwidth
                df['BB_WIDTH'] = bb[col]

        # BB 위치 (0=하단, 1=상단)
        if 'BBL' in df.columns and 'BBU' in df.columns:
            bb_range = df['BBU'] - df['BBL']
            df['BB_POSITION'] = np.where(
                bb_range > 0,
                (df['Close'] - df['BBL']) / bb_range,
                0.5
            )

    # === 거래량 지표 ===
    df['VOL_MA5'] = ta.sma(df['Volume'], length=5)
    df['VOL_MA20'] = ta.sma(df['Volume'], length=20)
    df['VOL_RATIO'] = np.where(
        df['VOL_MA20'] > 0,
        df['Volume'] / df['VOL_MA20'],
        1.0
    )

    # === OBV ===
    obv = ta.obv(df['Close'], df['Volume'])
    if obv is not None:
        df['OBV'] = obv
        df['OBV_MA'] = ta.sma(obv, length=20)

    # === ATR ===
    atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    if atr is not None:
        df['ATR'] = atr

    # === Supertrend ===
    try:
        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        if st is not None:
            for col in st.columns:
                if 'SUPERT_' in col:
                    df['SUPERTREND'] = st[col]
                elif 'SUPERTd_' in col:
                    df['SUPERTRENDd'] = st[col]
    except:
        pass

    # === Stochastic ===
    try:
        stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3)
        if stoch is not None:
            for col in stoch.columns:
                if 'STOCHk_' in col:
                    df['STOCH_K'] = stoch[col]
                elif 'STOCHd_' in col:
                    df['STOCH_D'] = stoch[col]
    except:
        pass

    # === StochRSI ===
    try:
        stochrsi = ta.stochrsi(df['Close'], length=14, rsi_length=14, k=3, d=3)
        if stochrsi is not None:
            for col in stochrsi.columns:
                if 'STOCHRSIk_' in col:
                    df['STOCHRSI_K'] = stochrsi[col]
                elif 'STOCHRSId_' in col:
                    df['STOCHRSI_D'] = stochrsi[col]
    except:
        pass

    # === 캔들 정보 ===
    df['CANDLE_BODY'] = df['Close'] - df['Open']
    df['CANDLE_BODY_PCT'] = (df['Close'] - df['Open']) / df['Open'] * 100
    df['CANDLE_RANGE'] = df['High'] - df['Low']
    df['UPPER_SHADOW'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['LOWER_SHADOW'] = df[['Open', 'Close']].min(axis=1) - df['Low']

    # === 거래대금 ===
    df['TRADING_VALUE'] = df['Close'] * df['Volume']

    return df


def calculate_projected_volume(df: pd.DataFrame) -> Tuple[int, float]:
    """장중 예상 거래량 계산

    Args:
        df: OHLCV DataFrame

    Returns:
        (예상 거래량, 거래량 비율)
    """
    now = datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    curr_vol = int(df.iloc[-1]['Volume'])

    if now < market_open or now >= market_close:
        # 장외 시간: 현재 거래량 그대로
        vol_ma = df['VOL_MA20'].iloc[-1] if 'VOL_MA20' in df.columns else df['Volume'].tail(20).mean()
        ratio = curr_vol / vol_ma if vol_ma > 0 else 1.0
        return curr_vol, ratio

    # 장중: 예상 거래량 계산
    total_minutes = 390  # 6시간 30분
    elapsed_minutes = max(1, (now - market_open).total_seconds() / 60)

    # 장 초반 보정 (거래량 편중)
    if elapsed_minutes < 60:
        projection_factor = (total_minutes / elapsed_minutes) * 0.7
    else:
        projection_factor = total_minutes / elapsed_minutes

    projected_vol = int(curr_vol * projection_factor)

    vol_ma = df['VOL_MA20'].iloc[-1] if 'VOL_MA20' in df.columns else df['Volume'].tail(20).mean()
    ratio = projected_vol / vol_ma if vol_ma > 0 else 1.0

    return projected_vol, ratio


def check_ma_status(df: pd.DataFrame) -> Dict:
    """이평선 상태 분석

    Returns:
        {
            'status': 'aligned' | 'reverse_aligned' | 'partial',
            'sma5': float,
            'sma20': float,
            'sma60': float,
            'sma20_slope': float,
            'distance_to_sma20': float (%)
        }
    """
    result = {
        'status': 'partial',
        'sma5': None,
        'sma20': None,
        'sma60': None,
        'sma20_slope': None,
        'distance_to_sma20': None,
    }

    if len(df) < 60:
        return result

    curr = df.iloc[-1]

    sma5 = curr.get('SMA_5') or df['Close'].tail(5).mean()
    sma20 = curr.get('SMA_20') or df['Close'].tail(20).mean()
    sma60 = curr.get('SMA_60') or df['Close'].tail(60).mean()

    result['sma5'] = sma5
    result['sma20'] = sma20
    result['sma60'] = sma60

    # 상태 판정
    if sma5 > sma20 > sma60:
        result['status'] = 'aligned'
    elif sma5 < sma20 < sma60:
        result['status'] = 'reverse_aligned'
    else:
        result['status'] = 'partial'

    # 기울기
    if 'SMA20_SLOPE' in df.columns:
        result['sma20_slope'] = curr['SMA20_SLOPE']
    elif len(df) >= 6:
        sma20_5d_ago = df['SMA_20'].iloc[-6] if 'SMA_20' in df.columns else df['Close'].iloc[-6:-1].mean()
        if pd.notna(sma20_5d_ago) and sma20_5d_ago > 0:
            result['sma20_slope'] = (sma20 - sma20_5d_ago) / sma20_5d_ago * 100

    # 현재가와 20일선 거리
    close = curr['Close']
    if sma20 > 0:
        result['distance_to_sma20'] = (close - sma20) / sma20 * 100

    return result


def check_rsi_status(df: pd.DataFrame) -> Dict:
    """RSI 상태 분석

    Returns:
        {
            'rsi': float,
            'prev_rsi': float,
            'zone': 'oversold' | 'healthy' | 'sweet_spot' | 'overbought' | 'extreme',
            'trend': 'rising' | 'falling' | 'neutral'
        }
    """
    result = {
        'rsi': None,
        'prev_rsi': None,
        'zone': 'neutral',
        'trend': 'neutral',
    }

    if 'RSI' not in df.columns or len(df) < 2:
        return result

    curr_rsi = df.iloc[-1]['RSI']
    prev_rsi = df.iloc[-2]['RSI']

    result['rsi'] = curr_rsi
    result['prev_rsi'] = prev_rsi

    # 구간 판정
    if pd.isna(curr_rsi):
        return result

    if curr_rsi < 30:
        result['zone'] = 'oversold'
    elif curr_rsi < 50:
        result['zone'] = 'low'
    elif curr_rsi < 60:
        result['zone'] = 'healthy'
    elif curr_rsi <= 75:
        result['zone'] = 'sweet_spot'
    elif curr_rsi <= 85:
        result['zone'] = 'overbought'
    else:
        result['zone'] = 'extreme'

    # 추세 판정
    if pd.notna(prev_rsi):
        if curr_rsi > prev_rsi + 2:
            result['trend'] = 'rising'
        elif curr_rsi < prev_rsi - 2:
            result['trend'] = 'falling'

    return result


def check_volume_status(df: pd.DataFrame) -> Dict:
    """거래량 상태 분석

    Returns:
        {
            'volume': int,
            'vol_ma20': float,
            'vol_ratio': float,
            'projected_volume': int,
            'projected_ratio': float,
            'trading_value': int,
            'trading_value_억': float,
            'level': 'low' | 'normal' | 'high' | 'surge' | 'explosion'
        }
    """
    result = {
        'volume': 0,
        'vol_ma20': 0,
        'vol_ratio': 1.0,
        'projected_volume': 0,
        'projected_ratio': 1.0,
        'trading_value': 0,
        'trading_value_억': 0,
        'level': 'normal',
    }

    if len(df) < 20:
        return result

    curr = df.iloc[-1]
    result['volume'] = int(curr['Volume'])

    if 'VOL_MA20' in df.columns:
        result['vol_ma20'] = curr['VOL_MA20']
    else:
        result['vol_ma20'] = df['Volume'].tail(20).mean()

    if 'VOL_RATIO' in df.columns:
        result['vol_ratio'] = curr['VOL_RATIO']
    elif result['vol_ma20'] > 0:
        result['vol_ratio'] = result['volume'] / result['vol_ma20']

    # 예상 거래량
    projected, proj_ratio = calculate_projected_volume(df)
    result['projected_volume'] = projected
    result['projected_ratio'] = proj_ratio

    # 거래대금
    if 'TRADING_VALUE' in df.columns:
        result['trading_value'] = int(curr['TRADING_VALUE'])
    else:
        result['trading_value'] = int(curr['Close'] * curr['Volume'])
    result['trading_value_억'] = result['trading_value'] / 100_000_000

    # 레벨 판정
    ratio = result['projected_ratio']
    if ratio >= 5.0:
        result['level'] = 'explosion'
    elif ratio >= 3.0:
        result['level'] = 'surge'
    elif ratio >= 2.0:
        result['level'] = 'high'
    elif ratio >= 1.0:
        result['level'] = 'normal'
    else:
        result['level'] = 'low'

    return result


def detect_obv_divergence(df: pd.DataFrame, lookback: int = 30) -> Dict:
    """OBV 다이버전스 감지

    Returns:
        {
            'bullish_divergence': bool,  # 가격 하락 + OBV 상승 (매집)
            'bearish_divergence': bool,  # 가격 상승 + OBV 하락 (분배)
            'days': int
        }
    """
    result = {'bullish_divergence': False, 'bearish_divergence': False, 'days': 0}

    if 'OBV' not in df.columns or len(df) < lookback:
        return result

    recent = df.tail(lookback)

    # 가격 저점/고점 찾기
    price_lows = []
    price_highs = []

    for i in range(2, len(recent) - 2):
        # 저점 (주변 4일 중 최저)
        if (recent['Low'].iloc[i] < recent['Low'].iloc[i-1] and
            recent['Low'].iloc[i] < recent['Low'].iloc[i-2] and
            recent['Low'].iloc[i] < recent['Low'].iloc[i+1] and
            recent['Low'].iloc[i] < recent['Low'].iloc[i+2]):
            price_lows.append({
                'idx': i,
                'price': recent['Low'].iloc[i],
                'obv': recent['OBV'].iloc[i]
            })

        # 고점
        if (recent['High'].iloc[i] > recent['High'].iloc[i-1] and
            recent['High'].iloc[i] > recent['High'].iloc[i-2] and
            recent['High'].iloc[i] > recent['High'].iloc[i+1] and
            recent['High'].iloc[i] > recent['High'].iloc[i+2]):
            price_highs.append({
                'idx': i,
                'price': recent['High'].iloc[i],
                'obv': recent['OBV'].iloc[i]
            })

    # 불리시 다이버전스: 가격 저점 하락, OBV 저점 상승
    if len(price_lows) >= 2:
        prev, curr = price_lows[-2], price_lows[-1]
        if curr['price'] < prev['price'] and curr['obv'] > prev['obv']:
            result['bullish_divergence'] = True
            result['days'] = curr['idx'] - prev['idx']

    # 베어리시 다이버전스: 가격 고점 상승, OBV 고점 하락
    if len(price_highs) >= 2:
        prev, curr = price_highs[-2], price_highs[-1]
        if curr['price'] > prev['price'] and curr['obv'] < prev['obv']:
            result['bearish_divergence'] = True
            result['days'] = curr['idx'] - prev['idx']

    return result


def detect_vcp_pattern(df: pd.DataFrame) -> Dict:
    """VCP (Volatility Contraction Pattern) 감지

    Returns:
        {
            'detected': bool,
            'contraction_pct': float,  # 수축률 (%)
            'vol_breakout': bool  # 거래량 돌파 여부
        }
    """
    result = {'detected': False, 'contraction_pct': 0, 'vol_breakout': False}

    if len(df) < 40:
        return result

    recent = df.tail(40)

    # 4개의 10일 구간
    ranges = []
    for i in range(4):
        start = i * 10
        end = start + 10
        period = recent.iloc[start:end]
        ranges.append({
            'high': period['High'].max(),
            'low': period['Low'].min(),
            'vol': period['Volume'].mean(),
            'range': period['High'].max() - period['Low'].min()
        })

    # VCP 조건
    # 1. 가격 범위 수축 (30%+ 감소)
    range_contraction = ranges[3]['range'] < ranges[0]['range'] * 0.7
    # 2. 저점 상승
    lows_rising = ranges[3]['low'] > ranges[0]['low']
    # 3. 거래량 수축
    vol_contraction = ranges[2]['vol'] < ranges[0]['vol'] * 0.7
    # 4. 최근 거래량 확대
    vol_expansion = ranges[3]['vol'] > ranges[2]['vol']

    if range_contraction and lows_rising and vol_contraction:
        result['detected'] = True
        result['contraction_pct'] = (1 - ranges[3]['range'] / ranges[0]['range']) * 100
        result['vol_breakout'] = vol_expansion

    return result


# 전역 캐시 인스턴스 (모듈 레벨)
_global_cache: Optional[IndicatorCache] = None


def get_global_cache(maxsize: int = 500) -> IndicatorCache:
    """전역 캐시 인스턴스 반환 (싱글톤)"""
    global _global_cache
    if _global_cache is None:
        _global_cache = IndicatorCache(maxsize=maxsize)
    return _global_cache


def clear_global_cache() -> None:
    """전역 캐시 초기화"""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear()
