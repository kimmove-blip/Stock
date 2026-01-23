#!/usr/bin/env python3
"""
장대양봉(Long Bullish Candle) 스크리닝 프로그램 v2.0
====================================================

핵심 원리:
- "거래량은 주가의 선행 지표"
- "에너지의 응축 후 발산" 패턴 탐지

스크리닝 기법:
1. 거래량 급감 눌림목 포착 (N자형 상승 패턴)
2. 볼린저 밴드 수축 후 돌파 준비
3. 이동평균선 밀집 구간 돌파
4. OBV 다이버전스
5. RSI/MACD 신호

사용법:
1. yfinance 사용 (인터넷 필요):
   python long_bullish_screener_v2.py

2. CSV 파일 사용:
   screener = LongBullishCandleScreener(data_source='csv', csv_folder='./data')
   
Author: Claude
Date: 2025-01-24
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')


# =============================================================================
# 핵심 스크리닝 클래스
# =============================================================================

class LongBullishCandleScreener:
    """장대양봉 후보 종목 스크리닝 클래스"""
    
    def __init__(
        self, 
        lookback_days: int = 120,
        data_source: str = 'yfinance',
        csv_folder: str = './data'
    ):
        """
        Args:
            lookback_days: 분석에 사용할 과거 데이터 일수
            data_source: 'yfinance' 또는 'csv'
            csv_folder: CSV 파일이 있는 폴더 경로
        """
        self.lookback_days = lookback_days
        self.data_source = data_source
        self.csv_folder = Path(csv_folder)
        
        # 스크리닝 파라미터 (조정 가능)
        self.params = {
            'long_bullish_min_pct': 7,        # 장대양봉 최소 상승률 (%)
            'vol_surge_threshold': 2.0,        # 거래량 폭증 기준 (배수)
            'vol_shrink_threshold': 0.5,       # 거래량 급감 기준 (배수)
            'vol_ratio_low': 0.8,              # 눌림목 거래량 비율 기준
            'small_candle_threshold': 3,       # 단봉 기준 (%)
            'ma_convergence_threshold': 2,     # 이평선 밀집 기준 (%)
            'rsi_oversold': 30,                # RSI 과매도 기준
            'resistance_range_pct': 5,         # 매물대 탐색 범위 (%)
        }
        
    def set_param(self, key: str, value: float):
        """파라미터 설정"""
        if key in self.params:
            self.params[key] = value
        
    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """데이터 소스에 따라 데이터 가져오기"""
        if self.data_source == 'yfinance':
            return self._fetch_yfinance(ticker)
        elif self.data_source == 'csv':
            return self._fetch_csv(ticker)
        return None
    
    def _fetch_yfinance(self, ticker: str) -> Optional[pd.DataFrame]:
        """yfinance에서 데이터 가져오기"""
        try:
            import yfinance as yf
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date, end=end_date)
            return df if not df.empty and len(df) >= 20 else None
        except ImportError:
            print("❌ yfinance 미설치. pip install yfinance 실행 필요")
            return None
        except Exception as e:
            print(f"❌ 데이터 오류 ({ticker}): {e}")
            return None
    
    def _fetch_csv(self, ticker: str) -> Optional[pd.DataFrame]:
        """CSV 파일에서 데이터 가져오기"""
        try:
            clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
            for name in [ticker, clean_ticker, ticker.lower()]:
                path = self.csv_folder / f"{name}.csv"
                if path.exists():
                    df = pd.read_csv(path)
                    # 날짜 컬럼 처리
                    for col in ['Date', 'date', 'datetime', '날짜']:
                        if col in df.columns:
                            df[col] = pd.to_datetime(df[col])
                            df.set_index(col, inplace=True)
                            break
                    # 컬럼명 표준화
                    df.rename(columns={
                        'open': 'Open', 'high': 'High', 'low': 'Low',
                        'close': 'Close', 'volume': 'Volume',
                        '시가': 'Open', '고가': 'High', '저가': 'Low',
                        '종가': 'Close', '거래량': 'Volume'
                    }, inplace=True)
                    return df.tail(self.lookback_days) if len(df) >= 20 else None
            return None
        except Exception as e:
            print(f"❌ CSV 오류 ({ticker}): {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 계산"""
        df = df.copy()
        
        # === 캔들 정보 ===
        df['candle_body'] = df['Close'] - df['Open']
        df['candle_body_pct'] = (df['Close'] - df['Open']) / df['Open'] * 100
        df['candle_range'] = df['High'] - df['Low']
        df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        
        min_pct = self.params['long_bullish_min_pct']
        df['is_long_bullish'] = (df['candle_body_pct'] >= min_pct) & (df['candle_body'] > 0)
        df['is_doji'] = abs(df['candle_body_pct']) < 0.5
        
        # === 거래량 지표 ===
        df['vol_ma5'] = df['Volume'].rolling(5).mean()
        df['vol_ma20'] = df['Volume'].rolling(20).mean()
        df['vol_ratio'] = df['Volume'] / df['vol_ma20']
        df['vol_surge'] = df['Volume'] > df['Volume'].shift(1) * self.params['vol_surge_threshold']
        df['vol_shrink'] = df['Volume'] < df['Volume'].shift(1) * self.params['vol_shrink_threshold']
        
        # === 이동평균선 ===
        for p in [5, 10, 20, 60, 120]:
            df[f'ma{p}'] = df['Close'].rolling(p).mean()
        
        df['ma_aligned'] = (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20'])
        df['ma_convergence'] = df[['ma5', 'ma10', 'ma20']].std(axis=1) / df['Close'] * 100
        df['golden_cross_5_10'] = (df['ma5'] > df['ma10']) & (df['ma5'].shift(1) <= df['ma10'].shift(1))
        df['golden_cross_5_20'] = (df['ma5'] > df['ma20']) & (df['ma5'].shift(1) <= df['ma20'].shift(1))
        
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
        df['volatility'] = df['Close'].rolling(20).std() / df['Close'].rolling(20).mean() * 100
        
        return df
    
    def find_recent_long_bullish(self, df: pd.DataFrame, days: int = 3) -> List[Dict]:
        """최근 N일 내 장대양봉 발생 확인"""
        events = []
        recent = df.tail(days + 1).head(days)
        
        for idx, row in recent.iterrows():
            if row['is_long_bullish'] and row['vol_ratio'] >= self.params['vol_surge_threshold']:
                events.append({
                    'date': idx,
                    'close': row['Close'],
                    'open': row['Open'],
                    'change_pct': row['candle_body_pct'],
                    'vol_ratio': row['vol_ratio'],
                    'midpoint': (row['Open'] + row['Close']) / 2,
                    'fib_38': row['Close'] - (row['Close'] - row['Open']) * 0.382,
                    'fib_50': (row['Open'] + row['Close']) / 2,
                    'fib_62': row['Close'] - (row['Close'] - row['Open']) * 0.618,
                })
        return events
    
    def check_pullback_pattern(self, df: pd.DataFrame, event: Dict) -> Dict:
        """눌림목 패턴 확인 (N자형 상승)"""
        result = {'pattern_found': False, 'score': 0, 'details': [], 'fib_level': None}
        
        after_event = df[df.index > event['date']]
        if len(after_event) < 1:
            return result
        
        today = after_event.iloc[-1]
        
        # 1. 거래량 급감
        if today['vol_ratio'] < self.params['vol_ratio_low']:
            result['score'] += 25
            result['details'].append(f"거래량 급감 ({today['vol_ratio']*100:.0f}%)")
        
        # 2. 단봉 캔들
        if abs(today['candle_body_pct']) < self.params['small_candle_threshold']:
            result['score'] += 25
            result['details'].append(f"단봉 캔들 ({today['candle_body_pct']:.1f}%)")
        
        # 3. 피보나치 지지
        price = today['Close']
        if price >= event['fib_38']:
            result['score'] += 35
            result['fib_level'] = '38.2%'
        elif price >= event['fib_50']:
            result['score'] += 30
            result['fib_level'] = '50%'
        elif price >= event['fib_62']:
            result['score'] += 20
            result['fib_level'] = '61.8%'
        elif price >= event['open']:
            result['score'] += 15
            result['fib_level'] = '시가'
        
        if result['fib_level']:
            result['details'].append(f"{result['fib_level']} 지지")
        
        # 4. OBV 유지
        if today['obv_trend']:
            result['score'] += 15
            result['details'].append("OBV 상승 유지")
        
        result['pattern_found'] = result['score'] >= 50
        return result
    
    def check_bollinger_squeeze(self, df: pd.DataFrame) -> Dict:
        """볼린저 밴드 수축 패턴"""
        today = df.iloc[-1]
        result = {
            'squeeze': today['bb_squeeze'],
            'width': today['bb_width'],
            'position': today['bb_position'],
            'breakout_ready': today['bb_squeeze'] and today['bb_position'] > 0.7,
            'score': 0, 'details': []
        }
        
        if today['bb_width'] < today['bb_width_ma'] * 0.8:
            result['score'] += 35
            result['details'].append("극심한 밴드 수축")
        elif result['squeeze']:
            result['score'] += 25
            result['details'].append("밴드 수축")
        
        if result['position'] > 0.8:
            result['score'] += 20
            result['details'].append(f"상단 근접 ({result['position']*100:.0f}%)")
        elif result['position'] > 0.7:
            result['score'] += 15
            result['details'].append(f"상위권 ({result['position']*100:.0f}%)")
        
        if result['breakout_ready']:
            result['score'] += 25
            result['details'].append("돌파 준비")
        
        return result
    
    def check_ma_convergence(self, df: pd.DataFrame) -> Dict:
        """이동평균선 밀집 및 정배열"""
        today = df.iloc[-1]
        result = {
            'aligned': today['ma_aligned'],
            'convergence': today['ma_convergence'],
            'tight': today['ma_convergence'] < self.params['ma_convergence_threshold'],
            'golden_cross_5_10': today['golden_cross_5_10'],
            'golden_cross_5_20': today['golden_cross_5_20'],
            'above_ma20': today['Close'] > today['ma20'],
            'above_ma60': today['Close'] > today['ma60'] if pd.notna(today['ma60']) else False,
            'score': 0, 'details': []
        }
        
        if result['aligned']:
            result['score'] += 25
            result['details'].append("정배열")
        
        if result['tight']:
            result['score'] += 25
            result['details'].append(f"밀집 ({result['convergence']:.1f}%)")
        
        if result['golden_cross_5_10']:
            result['score'] += 25
            result['details'].append("5/10 골든크로스")
        
        if result['golden_cross_5_20']:
            result['score'] += 20
            result['details'].append("5/20 골든크로스")
        
        if result['above_ma20']:
            result['score'] += 10
            result['details'].append("20일선 위")
        
        if result['above_ma60']:
            result['score'] += 10
            result['details'].append("60일선 위")
        
        return result
    
    def check_obv_divergence(self, df: pd.DataFrame, lookback: int = 10) -> Dict:
        """OBV 다이버전스 (매집 신호)"""
        recent = df.tail(lookback)
        today = df.iloc[-1]
        
        price_change = (recent['Close'].iloc[-1] - recent['Close'].iloc[0]) / recent['Close'].iloc[0] * 100
        obv_change = recent['obv'].iloc[-1] - recent['obv'].iloc[0]
        
        result = {
            'price_change': price_change,
            'obv_rising': obv_change > 0,
            'divergence': price_change <= 0 and obv_change > 0,
            'accumulation': False,
            'score': 0, 'details': []
        }
        
        if price_change < -3 and obv_change > 0:
            result['accumulation'] = True
            result['score'] += 45
            result['details'].append(f"강한 매집 신호 (가격 {price_change:.1f}%↓, OBV↑)")
        elif result['divergence']:
            result['accumulation'] = True
            result['score'] += 35
            result['details'].append(f"매집 신호 (가격 {price_change:.1f}%, OBV↑)")
        
        if today['obv_trend']:
            result['score'] += 15
            result['details'].append("OBV 상승 추세")
        
        return result
    
    def check_momentum_signals(self, df: pd.DataFrame) -> Dict:
        """RSI, MACD, 스토캐스틱 신호"""
        today = df.iloc[-1]
        
        result = {
            'rsi': today['rsi'],
            'rsi_oversold_exit': today['rsi_oversold_exit'],
            'macd_golden_cross': today['macd_golden_cross'],
            'macd_hist': today['macd_hist'],
            'macd_hist_positive': today['macd_hist_positive'],
            'stoch_k': today['stoch_k'],
            'stoch_golden_cross': today['stoch_golden_cross'],
            'score': 0, 'details': []
        }
        
        if result['rsi_oversold_exit']:
            result['score'] += 30
            result['details'].append(f"RSI 과매도 탈출 ({result['rsi']:.0f})")
        elif 40 <= result['rsi'] <= 60:
            result['score'] += 10
            result['details'].append(f"RSI 중립 ({result['rsi']:.0f})")
        
        if result['macd_golden_cross']:
            result['score'] += 30
            result['details'].append("MACD 골든크로스")
        
        if result['macd_hist_positive']:
            result['score'] += 20
            result['details'].append("MACD 히스토그램 양전환")
        
        if result['stoch_golden_cross']:
            result['score'] += 20
            result['details'].append("스토캐스틱 골든크로스")
        
        return result
    
    def check_resistance(self, df: pd.DataFrame) -> Dict:
        """매물대(저항선) 분석"""
        today = df.iloc[-1]
        recent = df.tail(60)
        
        upper_range = today['Close'] * 1.05
        high_vol = recent[recent['vol_ratio'] > 1.5]
        
        nearby = False
        strength = 0
        for _, row in high_vol.iterrows():
            if today['Close'] < row['High'] <= upper_range:
                nearby = True
                strength += row['vol_ratio']
        
        distance = (recent['High'].max() - today['Close']) / today['Close'] * 100
        
        result = {
            'nearby': nearby,
            'strength': strength,
            'clear_path': not nearby,
            'distance_to_high': distance,
            'score': 0, 'details': []
        }
        
        if result['clear_path']:
            result['score'] += 25
            result['details'].append("상방 매물대 없음")
        elif strength < 2:
            result['score'] += 15
            result['details'].append("약한 매물대")
        
        if distance < 5:
            result['score'] += 15
            result['details'].append(f"고점 근접 ({distance:.1f}%)")
        elif distance > 20:
            result['score'] += 10
            result['details'].append(f"상승 여력 ({distance:.1f}%)")
        
        return result
    
    def check_trend(self, df: pd.DataFrame) -> Dict:
        """추세 분석"""
        today = df.iloc[-1]
        recent20 = df.tail(20)
        
        change_20d = (today['Close'] - recent20['Close'].iloc[0]) / recent20['Close'].iloc[0] * 100
        
        result = {
            'uptrend': today['uptrend'],
            'strong_uptrend': today['strong_uptrend'],
            'downtrend': today['downtrend'],
            'change_20d': change_20d,
            'volatility': today['volatility'],
            'score': 0, 'details': [], 'warnings': []
        }
        
        if result['strong_uptrend']:
            result['score'] += 25
            result['details'].append("강한 상승 추세")
        elif result['uptrend']:
            result['score'] += 15
            result['details'].append("상승 추세")
        
        if result['downtrend']:
            result['warnings'].append("⚠️ 하락 추세 - 기술적 반등 주의")
        
        if change_20d > 10:
            result['warnings'].append(f"⚠️ 20일 +{change_20d:.1f}% 과열 주의")
        
        return result
    
    def analyze_stock(self, ticker: str) -> Optional[Dict]:
        """종목 종합 분석"""
        df = self.fetch_data(ticker)
        if df is None:
            return None
        
        df = self.calculate_indicators(df)
        today = df.iloc[-1]
        
        analysis = {
            'ticker': ticker,
            'date': str(df.index[-1])[:10],
            'close': today['Close'],
            'change_pct': today['candle_body_pct'],
            'vol_ratio': today['vol_ratio'],
            'total_score': 0,
            'signals': [],
            'warnings': []
        }
        
        # 1. 눌림목 패턴
        events = self.find_recent_long_bullish(df, 3)
        pullback_score = 0
        pullback_details = []
        
        if events:
            analysis['recent_long_bullish'] = len(events)
            for event in events:
                pb = self.check_pullback_pattern(df, event)
                if pb['score'] > pullback_score:
                    pullback_score = pb['score']
                    pullback_details = pb['details']
                if pb['pattern_found']:
                    analysis['signals'].append(f"눌림목 패턴 ({pb['fib_level']} 지지)")
        else:
            analysis['recent_long_bullish'] = 0
        
        analysis['pullback'] = {'score': pullback_score, 'details': pullback_details}
        analysis['total_score'] += pullback_score
        
        # 2. 볼린저 밴드
        bb = self.check_bollinger_squeeze(df)
        analysis['bollinger'] = bb
        analysis['total_score'] += bb['score']
        if bb['breakout_ready']:
            analysis['signals'].append("볼린저 돌파 준비")
        
        # 3. 이동평균선
        ma = self.check_ma_convergence(df)
        analysis['ma'] = ma
        analysis['total_score'] += ma['score']
        if ma['golden_cross_5_10']:
            analysis['signals'].append("5/10 골든크로스")
        if ma['tight'] and ma['aligned']:
            analysis['signals'].append("이평선 밀집 정배열")
        
        # 4. OBV
        obv = self.check_obv_divergence(df)
        analysis['obv'] = obv
        analysis['total_score'] += obv['score']
        if obv['accumulation']:
            analysis['signals'].append("OBV 매집 신호")
        
        # 5. 모멘텀
        mom = self.check_momentum_signals(df)
        analysis['momentum'] = mom
        analysis['total_score'] += mom['score']
        if mom['macd_golden_cross']:
            analysis['signals'].append("MACD 골든크로스")
        if mom['rsi_oversold_exit']:
            analysis['signals'].append("RSI 과매도 탈출")
        
        # 6. 매물대
        res = self.check_resistance(df)
        analysis['resistance'] = res
        analysis['total_score'] += res['score']
        if res['clear_path']:
            analysis['signals'].append("상방 매물대 없음")
        
        # 7. 추세
        trend = self.check_trend(df)
        analysis['trend'] = trend
        analysis['total_score'] += trend['score']
        analysis['warnings'].extend(trend['warnings'])
        
        # 등급 결정
        score = analysis['total_score']
        if score >= 180:
            analysis['grade'] = 'A+'
            analysis['rec'] = '★★★★★ 매우 강력'
        elif score >= 150:
            analysis['grade'] = 'A'
            analysis['rec'] = '★★★★☆ 강력'
        elif score >= 120:
            analysis['grade'] = 'B+'
            analysis['rec'] = '★★★☆☆ 추천'
        elif score >= 90:
            analysis['grade'] = 'B'
            analysis['rec'] = '★★☆☆☆ 관심'
        elif score >= 60:
            analysis['grade'] = 'C'
            analysis['rec'] = '★☆☆☆☆ 관망'
        else:
            analysis['grade'] = 'D'
            analysis['rec'] = '☆☆☆☆☆ 비추천'
        
        return analysis
    
    def screen_stocks(self, tickers: List[str], min_score: int = 60) -> pd.DataFrame:
        """여러 종목 스크리닝"""
        results = []
        
        for i, ticker in enumerate(tickers):
            print(f"분석 중... {ticker} ({i+1}/{len(tickers)})")
            try:
                a = self.analyze_stock(ticker)
                if a and a['total_score'] >= min_score:
                    results.append({
                        '종목': a['ticker'],
                        '날짜': a['date'],
                        '종가': f"{a['close']:,.0f}",
                        '등락': f"{a['change_pct']:.1f}%",
                        '거래량': f"{a['vol_ratio']:.1f}x",
                        '점수': a['total_score'],
                        '등급': a['grade'],
                        '신호': ' | '.join(a['signals'][:3]) if a['signals'] else '-'
                    })
            except Exception as e:
                print(f"  → 실패: {e}")
        
        if not results:
            return pd.DataFrame()
        
        return pd.DataFrame(results).sort_values('점수', ascending=False)
    
    def print_report(self, a: Dict):
        """상세 분석 리포트 출력"""
        print("\n" + "="*70)
        print(f"📊 {a['ticker']} 장대양봉 가능성 분석")
        print("="*70)
        print(f"날짜: {a['date']} | 종가: {a['close']:,.0f} | 등락: {a['change_pct']:.1f}%")
        print(f"거래량 비율: {a['vol_ratio']:.2f}x (20일 평균 대비)")
        print("-"*70)
        print(f"\n🎯 총점: {a['total_score']}점 | {a['rec']}")
        
        if a['warnings']:
            print("\n⚠️ 주의:")
            for w in a['warnings']:
                print(f"  {w}")
        
        print("\n" + "-"*70)
        print("📌 세부 분석")
        print("-"*70)
        
        # 1. 눌림목
        print(f"\n1️⃣ 눌림목 패턴 (점수: {a['pullback']['score']})")
        if a['recent_long_bullish']:
            print(f"   최근 장대양봉: {a['recent_long_bullish']}회")
            for d in a['pullback']['details']:
                print(f"   ✓ {d}")
        else:
            print("   해당 없음")
        
        # 2. 볼린저
        bb = a['bollinger']
        print(f"\n2️⃣ 볼린저 밴드 (점수: {bb['score']})")
        print(f"   밴드폭: {bb['width']:.1f}% | 위치: {bb['position']*100:.0f}%")
        for d in bb['details']:
            print(f"   ✓ {d}")
        
        # 3. 이평선
        ma = a['ma']
        print(f"\n3️⃣ 이동평균선 (점수: {ma['score']})")
        print(f"   밀집도: {ma['convergence']:.1f}% | 정배열: {'예' if ma['aligned'] else '아니오'}")
        for d in ma['details']:
            print(f"   ✓ {d}")
        
        # 4. OBV
        obv = a['obv']
        print(f"\n4️⃣ OBV (점수: {obv['score']})")
        print(f"   10일 가격변화: {obv['price_change']:.1f}%")
        for d in obv['details']:
            print(f"   ✓ {d}")
        
        # 5. 모멘텀
        mom = a['momentum']
        print(f"\n5️⃣ 모멘텀 (점수: {mom['score']})")
        print(f"   RSI: {mom['rsi']:.0f} | MACD: {mom['macd_hist']:.4f}")
        for d in mom['details']:
            print(f"   ✓ {d}")
        
        # 6. 매물대
        res = a['resistance']
        print(f"\n6️⃣ 매물대 (점수: {res['score']})")
        print(f"   고점까지: {res['distance_to_high']:.1f}%")
        for d in res['details']:
            print(f"   ✓ {d}")
        
        # 7. 추세
        trend = a['trend']
        print(f"\n7️⃣ 추세 (점수: {trend['score']})")
        print(f"   20일 변화: {trend['change_20d']:.1f}% | 변동성: {trend['volatility']:.1f}%")
        for d in trend['details']:
            print(f"   ✓ {d}")
        
        # 신호 요약
        if a['signals']:
            print("\n" + "-"*70)
            print("🚀 감지된 신호:")
            for i, s in enumerate(a['signals'], 1):
                print(f"   {i}. {s}")
        
        print("\n" + "="*70)


# =============================================================================
# 샘플 종목 리스트
# =============================================================================

def get_kospi_tickers():
    """KOSPI 주요 종목"""
    return [
        '005930.KS', '000660.KS', '035420.KS', '005380.KS', '035720.KS',
        '051910.KS', '006400.KS', '068270.KS', '028260.KS', '105560.KS',
        '055550.KS', '034730.KS', '012330.KS', '066570.KS', '003550.KS',
        '096770.KS', '017670.KS', '030200.KS', '033780.KS', '009150.KS',
    ]

def get_kosdaq_tickers():
    """KOSDAQ 주요 종목"""
    return [
        '247540.KQ', '086520.KQ', '091990.KQ', '293490.KQ', '263750.KQ',
        '196170.KQ', '112040.KQ', '035900.KQ', '352820.KQ', '383220.KQ',
    ]

def get_us_tickers():
    """미국 주요 종목"""
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AMD',
        'NFLX', 'INTC', 'CRM', 'PYPL', 'SQ', 'SHOP', 'COIN',
    ]


# =============================================================================
# 샘플 데이터 생성 (테스트용)
# =============================================================================

def generate_sample_data(days: int = 120) -> pd.DataFrame:
    """테스트용 샘플 데이터 생성"""
    np.random.seed(42)
    
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 기본 추세 생성
    trend = np.cumsum(np.random.randn(days) * 0.5) + 100
    
    # 장대양봉 이벤트 삽입 (최근 3일 전에)
    trend[-3] = trend[-4] + 8  # 8% 상승
    trend[-2] = trend[-3] - 1  # 소폭 하락
    trend[-1] = trend[-2] + 0.5  # 횡보
    
    data = {
        'Open': trend - np.random.rand(days) * 2,
        'Close': trend,
        'High': trend + np.random.rand(days) * 3,
        'Low': trend - np.random.rand(days) * 3,
    }
    
    # 거래량 생성
    base_vol = 1000000
    vol = np.random.randint(int(base_vol*0.5), int(base_vol*1.5), days)
    vol[-3] = base_vol * 3  # 장대양봉 날 거래량 폭증
    vol[-2] = base_vol * 0.4  # 거래량 급감
    vol[-1] = base_vol * 0.5
    data['Volume'] = vol
    
    df = pd.DataFrame(data, index=dates)
    df['Open'] = df['Open'].clip(lower=df['Low'])
    df['Close'] = df['Close'].clip(lower=df['Low'], upper=df['High'])
    
    return df


# =============================================================================
# 메인 실행
# =============================================================================

if __name__ == "__main__":
    print("="*70)
    print("📈 장대양봉 스크리닝 프로그램 v2.0")
    print("="*70)
    print("\n분석 기준:")
    print("  1. 거래량 급감 눌림목 (N자형 상승)")
    print("  2. 볼린저 밴드 수축 돌파")
    print("  3. 이동평균선 밀집 정배열")
    print("  4. OBV 다이버전스 (매집 신호)")
    print("  5. RSI/MACD 모멘텀")
    print("  6. 매물대 분석")
    print("-"*70)
    
    print("\n분석 모드 선택:")
    print("  1. 한국 KOSPI")
    print("  2. 한국 KOSDAQ")
    print("  3. 미국 주요 종목")
    print("  4. 직접 입력")
    print("  5. 단일 종목 상세 분석")
    print("  6. 샘플 데이터 테스트")
    
    choice = input("\n선택 (1-6): ").strip()
    
    screener = LongBullishCandleScreener(lookback_days=120)
    
    if choice == '1':
        tickers = get_kospi_tickers()
    elif choice == '2':
        tickers = get_kosdaq_tickers()
    elif choice == '3':
        tickers = get_us_tickers()
    elif choice == '4':
        inp = input("종목 코드 (쉼표 구분): ")
        tickers = [t.strip() for t in inp.split(',')]
    elif choice == '5':
        ticker = input("종목 코드 (예: 005930.KS, AAPL): ").strip() or 'AAPL'
        a = screener.analyze_stock(ticker)
        if a:
            screener.print_report(a)
        else:
            print(f"❌ {ticker} 데이터 없음")
        exit()
    elif choice == '6':
        # 샘플 데이터 테스트
        print("\n📋 샘플 데이터로 테스트 실행...")
        sample_df = generate_sample_data(120)
        
        # 임시로 데이터 주입
        class SampleScreener(LongBullishCandleScreener):
            def __init__(self, sample_data):
                super().__init__()
                self.sample_data = sample_data
            
            def fetch_data(self, ticker):
                return self.sample_data
        
        test_screener = SampleScreener(sample_df)
        a = test_screener.analyze_stock('SAMPLE')
        if a:
            test_screener.print_report(a)
        exit()
    else:
        print("기본값(미국)으로 진행")
        tickers = get_us_tickers()
    
    print(f"\n{len(tickers)}개 종목 분석 시작...\n")
    results = screener.screen_stocks(tickers, min_score=50)
    
    if not results.empty:
        print("\n" + "="*70)
        print("🏆 장대양봉 후보 (50점 이상)")
        print("="*70)
        print(results.to_string(index=False))
        
        if len(results) > 0:
            top = results.iloc[0]['종목']
            print(f"\n\n📊 최고점 종목 상세: {top}")
            top_a = screener.analyze_stock(top)
            if top_a:
                screener.print_report(top_a)
    else:
        print("\n⚠️ 조건 충족 종목 없음")
    
    print("\n" + "="*70)
    print("분석 완료!")
    print("="*70)
