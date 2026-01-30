#!/usr/bin/env python3
"""
갭 예측 모델 학습 V2 (백테스트와 동일한 피처)
"""
import pandas as pd
import numpy as np
from pykrx import stock
from pykrx.website.krx.market.ticker import StockTicker
from sklearn.ensemble import RandomForestClassifier
import pickle
import warnings
import functools
warnings.filterwarnings('ignore')

print = functools.partial(print, flush=True)

print("=" * 50)
print("  갭 예측 모델 학습 V2")
print("=" * 50)

# 5년치 데이터
end_date = "20260130"
start_date = "20210130"

print("\n[1] 데이터 수집...")
ticker_df = StockTicker().listed
ticker_df = ticker_df[ticker_df['시장'].isin(['STK', 'KSQ'])]
tickers = ticker_df.index.tolist()
print(f"    {len(tickers)}개 종목")

all_data = {}
for i, ticker in enumerate(tickers):
    if (i + 1) % 500 == 0:
        print(f"    {i+1}/{len(tickers)}...")
    try:
        df = stock.get_market_ohlcv(start_date, end_date, ticker)
        if len(df) >= 60:
            all_data[ticker] = df
    except:
        pass
print(f"    {len(all_data)}개 로드 완료")

# 백테스트와 동일한 피처 계산 함수
def calculate_features(df, idx):
    if idx < 20:
        return None

    row = df.iloc[idx]
    prev_rows = df.iloc[idx-20:idx]

    o, h, l, c, v = row['시가'], row['고가'], row['저가'], row['종가'], row['거래량']

    if o == 0 or c == 0 or v == 0:
        return None

    features = {}

    # 캔들 피처
    body = abs(c - o)
    total_range = h - l if h > l else 1

    features['close_pos'] = (c - l) / total_range if total_range > 0 else 0.5
    features['close_high'] = (c - l) / (h - l) if h > l else 0.5
    features['is_bull'] = 1 if c > o else 0
    features['body_ratio'] = body / total_range if total_range > 0 else 0
    features['upper_wick'] = (h - max(o, c)) / total_range if total_range > 0 else 0
    features['lower_wick'] = (min(o, c) - l) / total_range if total_range > 0 else 0

    # 등락률
    prev_close = df.iloc[idx-1]['종가']
    features['day_change'] = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0

    # 이동평균 거리
    ma5 = prev_rows['종가'].tail(5).mean()
    ma20 = prev_rows['종가'].mean()
    features['dist_ma5'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0
    features['dist_ma20'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

    # 거래량 비율
    avg_vol = prev_rows['거래량'].mean()
    features['vol_ratio'] = v / avg_vol if avg_vol > 0 else 1

    # 거래량 감소 여부
    recent_vol = prev_rows['거래량'].tail(5).mean()
    older_vol = prev_rows['거래량'].head(15).mean()
    features['vol_declining'] = 1 if recent_vol < older_vol * 0.7 else 0

    # RSI
    changes = prev_rows['종가'].diff()
    gains = changes.where(changes > 0, 0).mean()
    losses = (-changes.where(changes < 0, 0)).mean()
    features['rsi'] = gains / (gains + losses) * 100 if gains + losses > 0 else 50
    features['rsi_overbought'] = 1 if features['rsi'] > 70 else 0

    # 연속 양봉
    recent_5 = df.iloc[idx-4:idx+1]
    features['consec_bull'] = sum(1 for i in range(len(recent_5))
                                   if recent_5.iloc[i]['종가'] > recent_5.iloc[i]['시가'])

    # 이동평균 정배열
    ma5_val = df.iloc[idx-4:idx+1]['종가'].mean()
    ma10_val = df.iloc[idx-9:idx+1]['종가'].mean()
    ma20_val = df.iloc[idx-19:idx+1]['종가'].mean()
    features['aligned'] = 1 if c > ma5_val > ma10_val > ma20_val else 0

    # 20일 고점/저점 대비
    high_20d = prev_rows['고가'].max()
    low_20d = prev_rows['저가'].min()
    features['near_high_20d'] = c / high_20d if high_20d > 0 else 0
    features['from_low_20d'] = (c - low_20d) / low_20d * 100 if low_20d > 0 else 0

    # 변동성
    features['volatility'] = prev_rows['종가'].pct_change().std() * 100

    # 거래대금 (억 단위)
    features['trade_value'] = row['거래량'] * c / 100000000

    # 급등 여부
    features['is_surge'] = 1 if features['day_change'] >= 15 else 0

    # 2일 연속 급등
    if idx >= 2:
        prev_prev_close = df.iloc[idx-2]['종가']
        two_day_change = (c - prev_prev_close) / prev_prev_close * 100
        features['two_day_surge'] = 1 if two_day_change >= 20 else 0
    else:
        features['two_day_surge'] = 0

    return features

print("\n[2] 학습 데이터 생성...")
samples = []
for ticker, df in all_data.items():
    for i in range(21, len(df) - 1):
        features = calculate_features(df, i)
        if features is None:
            continue
        if features['trade_value'] < 50:
            continue
        if not (-15 <= features['day_change'] <= 25):
            continue

        today_close = df.iloc[i]['종가']
        next_open = df.iloc[i + 1]['시가']
        gap_pct = (next_open - today_close) / today_close * 100

        features['gap_up'] = 1 if gap_pct > 0 else 0
        samples.append(features)

df_train = pd.DataFrame(samples)
print(f"    {len(df_train):,}개 샘플")

print("\n[3] 모델 학습...")
fcols = [c for c in df_train.columns if c != 'gap_up']
X, y = df_train[fcols], df_train['gap_up']

model = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    min_samples_leaf=20,
    random_state=42,
    n_jobs=-1
)
model.fit(X, y)

print("\n[4] 모델 저장...")
with open('/home/kimhc/Stock/models/gap_model_v9.pkl', 'wb') as f:
    pickle.dump({'model': model, 'features': fcols}, f)

print("    저장 완료: models/gap_model_v9.pkl")
print(f"    피처 수: {len(fcols)}개")
print(f"    피처: {fcols}")
print("=" * 50)
