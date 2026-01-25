#!/usr/bin/env python3
"""
V10 + 확률 80% 조건 테스트
- V9의 확률 기반 분류 모델 + V10의 B필터 결합
"""

import pandas as pd
import numpy as np
from pykrx import stock
from pykrx.website.krx.market.ticker import StockTicker
import warnings
warnings.filterwarnings('ignore')

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
import xgboost as xgb

import functools
print = functools.partial(print, flush=True)

print("=" * 70)
print("  V10 + 확률 80% 조건 테스트")
print("=" * 70)
print()

# =============================================================================
# 1. 데이터 수집
# =============================================================================
print("[1] 데이터 수집...")

end_date = "20260123"
start_date = "20250123"

ticker_df = StockTicker().listed
ticker_df = ticker_df[ticker_df['시장'].isin(['STK', 'KSQ'])]
tickers = ticker_df.index.tolist()
print(f"    → {len(tickers)}개 종목")

all_data = {}
for i, ticker in enumerate(tickers):
    if (i + 1) % 500 == 0:
        print(f"    → {i+1}/{len(tickers)} 로딩 중...")
    try:
        df = stock.get_market_ohlcv(start_date, end_date, ticker)
        if len(df) >= 60:
            all_data[ticker] = df
    except:
        pass

print(f"    → {len(all_data)}개 종목 로드 완료")

# =============================================================================
# 2. 피처 생성
# =============================================================================
print("\n[2] 피처 생성...")

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

    # 당일 등락률
    prev_close = df.iloc[idx-1]['종가'] if idx > 0 else c
    features['day_change'] = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0

    # 이동평균 대비
    ma5 = prev_rows['종가'].tail(5).mean()
    ma20 = prev_rows['종가'].mean()
    features['dist_ma5'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0
    features['dist_ma20'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

    # 거래량 피처
    avg_vol = prev_rows['거래량'].mean()
    features['vol_ratio'] = v / avg_vol if avg_vol > 0 else 1

    # 거래량 감소 여부
    recent_vol = df.iloc[idx-3:idx]['거래량'].mean() if idx >= 3 else v
    older_vol = df.iloc[idx-10:idx-3]['거래량'].mean() if idx >= 10 else avg_vol
    features['vol_declining'] = 1 if recent_vol < older_vol * 0.7 else 0

    # RSI
    changes = prev_rows['종가'].diff().dropna()
    gains = changes[changes > 0].sum()
    losses = abs(changes[changes < 0].sum())
    features['rsi'] = gains / (gains + losses) * 100 if gains + losses > 0 else 50
    features['rsi_overbought'] = 1 if features['rsi'] > 70 else 0

    # 연속 양봉
    recent_5 = df.iloc[idx-5:idx]
    features['consec_bull'] = sum(1 for i in range(len(recent_5))
                                   if recent_5.iloc[i]['종가'] > recent_5.iloc[i]['시가'])

    # 정배열 여부
    ma5_val = df.iloc[idx-5:idx]['종가'].mean()
    ma10_val = df.iloc[idx-10:idx]['종가'].mean()
    ma20_val = df.iloc[idx-20:idx]['종가'].mean()
    features['aligned'] = 1 if c > ma5_val > ma10_val > ma20_val else 0

    # 고저점 대비
    high_20d = prev_rows['고가'].max()
    low_20d = prev_rows['저가'].min()
    features['near_high_20d'] = c / high_20d if high_20d > 0 else 0
    features['from_low_20d'] = (c - low_20d) / low_20d * 100 if low_20d > 0 else 0

    # 변동성
    features['volatility'] = prev_rows['종가'].pct_change().std() * 100

    # 거래대금
    features['trade_value'] = row['거래량'] * c / 100000000

    # B필터용
    features['is_surge'] = 1 if features['day_change'] >= 15 else 0

    if idx >= 2:
        prev_prev_close = df.iloc[idx-2]['종가']
        two_day_change = (c - prev_prev_close) / prev_prev_close * 100 if prev_prev_close > 0 else 0
        features['two_day_surge'] = 1 if two_day_change >= 20 else 0
    else:
        features['two_day_surge'] = 0

    return features

samples = []
print("    피처 추출 중...")

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

        features['gap_pct'] = gap_pct
        features['gap_up'] = 1 if gap_pct > 0 else 0  # 분류용 타겟
        features['ticker'] = ticker
        features['date'] = df.index[i]

        samples.append(features)

df_samples = pd.DataFrame(samples)
print(f"    → {len(df_samples):,}개 샘플 생성")

# =============================================================================
# 3. 분류 모델 학습 (확률 예측)
# =============================================================================
print("\n[3] 분류 모델 학습 (확률 예측)...")

feature_cols = ['close_pos', 'close_high', 'is_bull', 'body_ratio', 'upper_wick',
                'lower_wick', 'day_change', 'dist_ma5', 'dist_ma20', 'vol_ratio',
                'rsi', 'consec_bull', 'aligned', 'near_high_20d', 'from_low_20d',
                'volatility']

X = df_samples[feature_cols].values
y = df_samples['gap_up'].values  # 분류 타겟

split_idx = int(len(X) * 0.7)
X_train, X_test = X[:split_idx], X[split_idx:]
y_train, y_test = y[:split_idx], y[split_idx:]
df_test = df_samples.iloc[split_idx:].copy()

print(f"    학습: {len(X_train):,}개, 테스트: {len(X_test):,}개")

# XGBoost 분류 모델
model = xgb.XGBClassifier(n_estimators=100, max_depth=5, random_state=42, verbosity=0)
model.fit(X_train, y_train)

# 확률 예측
proba = model.predict_proba(X_test)[:, 1]
df_test['prob'] = proba

print(f"    → 모델 학습 완료")

# =============================================================================
# 4. 확률 임계값별 + B필터 백테스트
# =============================================================================
print("\n[4] 확률 임계값별 + B필터 백테스트...")
print("-" * 70)

tax_rate = 0.00203

results = []

# 확률만 적용
print("\n    [확률만 적용]")
for prob_thresh in [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]:
    filtered = df_test[df_test['prob'] >= prob_thresh].copy()
    if len(filtered) == 0:
        continue

    filtered['return'] = filtered['gap_pct'] - (tax_rate * 100)
    trades = len(filtered)
    wins = (filtered['gap_pct'] > 0).sum()
    win_rate = wins / trades * 100
    avg_return = filtered['return'].mean()

    results.append({
        'condition': f'확률>={int(prob_thresh*100)}%',
        'trades': trades,
        'win_rate': win_rate,
        'avg_return': avg_return
    })
    print(f"    확률 >= {int(prob_thresh*100)}%: {trades:,}건, 승률 {win_rate:.1f}%, 수익률 {avg_return:.3f}%")

# 확률 + B필터 전체
print("\n    [확률 + B필터 전체]")
for prob_thresh in [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]:
    filtered = df_test[
        (df_test['prob'] >= prob_thresh) &
        (df_test['is_surge'] == 0) &
        (df_test['rsi_overbought'] == 0) &
        (df_test['vol_declining'] == 0) &
        (df_test['two_day_surge'] == 0)
    ].copy()

    if len(filtered) == 0:
        continue

    filtered['return'] = filtered['gap_pct'] - (tax_rate * 100)
    trades = len(filtered)
    wins = (filtered['gap_pct'] > 0).sum()
    win_rate = wins / trades * 100
    avg_return = filtered['return'].mean()

    results.append({
        'condition': f'확률>={int(prob_thresh*100)}% + B필터',
        'trades': trades,
        'win_rate': win_rate,
        'avg_return': avg_return
    })
    print(f"    확률 >= {int(prob_thresh*100)}% + B필터: {trades:,}건, 승률 {win_rate:.1f}%, 수익률 {avg_return:.3f}%")

# =============================================================================
# 5. 80% 확률 + B필터 월별 성과
# =============================================================================
print("\n[5] 80% 확률 + B필터 월별 성과...")
print("-" * 70)

optimal = df_test[
    (df_test['prob'] >= 0.80) &
    (df_test['is_surge'] == 0) &
    (df_test['rsi_overbought'] == 0) &
    (df_test['vol_declining'] == 0) &
    (df_test['two_day_surge'] == 0)
].copy()

if len(optimal) > 0:
    optimal['return'] = optimal['gap_pct'] - (tax_rate * 100)
    optimal['month'] = pd.to_datetime(optimal['date']).dt.to_period('M')

    monthly = optimal.groupby('month').agg({
        'return': ['count', 'mean', 'sum'],
        'gap_pct': lambda x: (x > 0).sum()
    }).reset_index()

    monthly.columns = ['month', 'trades', 'avg_return', 'total_return', 'wins']
    monthly['win_rate'] = monthly['wins'] / monthly['trades'] * 100

    print(f"    {'월':^10} {'거래수':>8} {'승률':>8} {'평균수익':>10} {'총수익':>10}")
    print("    " + "-" * 50)

    for _, row in monthly.iterrows():
        print(f"    {str(row['month']):^10} {row['trades']:>8,} {row['win_rate']:>7.1f}% "
              f"{row['avg_return']:>9.3f}% {row['total_return']:>9.2f}%")

# =============================================================================
# 6. 결과 저장
# =============================================================================
print("\n[6] 결과 저장...")

output_path = "/home/kimhc/Stock/output/v10_prob80_backtest.xlsx"

with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    pd.DataFrame(results).to_excel(writer, sheet_name='조건별_성과', index=False)
    if len(optimal) > 0:
        monthly.to_excel(writer, sheet_name='월별_성과', index=False)
        detail = optimal[['date', 'ticker', 'prob', 'gap_pct', 'return',
                          'day_change', 'vol_ratio', 'rsi']].sort_values('date')
        detail.to_excel(writer, sheet_name='거래_상세', index=False)

print(f"    → 저장 완료: {output_path}")

# =============================================================================
# 최종 요약
# =============================================================================
print("\n" + "=" * 70)
print("  결과 요약")
print("=" * 70)

# 80% + B필터 결과
result_80 = [r for r in results if r['condition'] == '확률>=80% + B필터']
if result_80:
    r = result_80[0]
    print(f"""
  80% 확률 + B필터:
    - 거래 수: {r['trades']:,}건
    - 승률: {r['win_rate']:.1f}%
    - 평균 수익률: {r['avg_return']:.3f}%

  비교:
    - V9 (85%+ 확률): 485건, 62.5% 승률, +0.70% 수익률
    - V10 (2%+갭 + B필터): 76건, 68.4% 승률, +1.41% 수익률
    - V10 (80%확률 + B필터): {r['trades']:,}건, {r['win_rate']:.1f}% 승률, {r['avg_return']:.3f}% 수익률
""")
print("=" * 70)
