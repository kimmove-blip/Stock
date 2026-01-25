#!/usr/bin/env python3
"""
V10 갭상승 예측 엔진 (A+B 결합)
- A: 갭상승 크기(%) 예측 (회귀 모델)
- B: 손실 제한 필터 (급등 후 차익실현, RSI 과매수, 거래량 급감 제외)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pykrx import stock
import warnings
warnings.filterwarnings('ignore')

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
import xgboost as xgb

import sys
import functools
print = functools.partial(print, flush=True)

print("=" * 70)
print("  V10 갭상승 예측 엔진 (A: 크기예측 + B: 손실필터)")
print("=" * 70)
print()

# =============================================================================
# 1. 데이터 수집
# =============================================================================
print("[1] 데이터 수집...")

end_date = "20260123"
start_date = "20250123"

# StockTicker를 직접 사용하여 종목 리스트 가져오기
from pykrx.website.krx.market.ticker import StockTicker
ticker_df = StockTicker().listed
# KOSPI(STK)와 KOSDAQ(KSQ)만 필터링
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

trading_days = stock.get_market_ohlcv(start_date, end_date, "005930").index.tolist()
print(f"    → {len(trading_days)}개 거래일")

# =============================================================================
# 2. 피처 생성 (B: 손실 필터용 피처 포함)
# =============================================================================
print("\n[2] 피처 생성...")

def calculate_features(df, idx):
    """전일 데이터 기반 피처 계산 + 손실 필터용 피처"""
    if idx < 20:
        return None

    row = df.iloc[idx]
    prev_rows = df.iloc[idx-20:idx]

    o, h, l, c, v = row['시가'], row['고가'], row['저가'], row['종가'], row['거래량']

    if o == 0 or c == 0 or v == 0:
        return None

    features = {}

    # === 기본 캔들 피처 ===
    body = abs(c - o)
    total_range = h - l if h > l else 1

    features['close_pos'] = (c - l) / total_range if total_range > 0 else 0.5
    features['close_high'] = (c - l) / (h - l) if h > l else 0.5
    features['is_bull'] = 1 if c > o else 0
    features['body_ratio'] = body / total_range if total_range > 0 else 0
    features['upper_wick'] = (h - max(o, c)) / total_range if total_range > 0 else 0
    features['lower_wick'] = (min(o, c) - l) / total_range if total_range > 0 else 0

    # === 당일 등락률 ===
    prev_close = df.iloc[idx-1]['종가'] if idx > 0 else c
    features['day_change'] = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0

    # === 이동평균 대비 ===
    ma5 = prev_rows['종가'].tail(5).mean()
    ma20 = prev_rows['종가'].mean()
    features['dist_ma5'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0
    features['dist_ma20'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

    # === 거래량 피처 ===
    avg_vol = prev_rows['거래량'].mean()
    features['vol_ratio'] = v / avg_vol if avg_vol > 0 else 1

    # B필터: 거래량 감소 여부 (최근 3일 평균 vs 이전 10일 평균)
    recent_vol = df.iloc[idx-3:idx]['거래량'].mean() if idx >= 3 else v
    older_vol = df.iloc[idx-10:idx-3]['거래량'].mean() if idx >= 10 else avg_vol
    features['vol_declining'] = 1 if recent_vol < older_vol * 0.7 else 0

    # === RSI ===
    changes = prev_rows['종가'].diff().dropna()
    gains = changes[changes > 0].sum()
    losses = abs(changes[changes < 0].sum())
    if gains + losses > 0:
        features['rsi'] = gains / (gains + losses) * 100
    else:
        features['rsi'] = 50

    # B필터: RSI 과매수 여부
    features['rsi_overbought'] = 1 if features['rsi'] > 70 else 0

    # === 연속 양봉 ===
    recent_5 = df.iloc[idx-5:idx]
    features['consec_bull'] = sum(1 for i in range(len(recent_5))
                                   if recent_5.iloc[i]['종가'] > recent_5.iloc[i]['시가'])

    # === 정배열 여부 ===
    ma5_val = df.iloc[idx-5:idx]['종가'].mean()
    ma10_val = df.iloc[idx-10:idx]['종가'].mean()
    ma20_val = df.iloc[idx-20:idx]['종가'].mean()
    features['aligned'] = 1 if c > ma5_val > ma10_val > ma20_val else 0

    # === 고저점 대비 ===
    high_20d = prev_rows['고가'].max()
    low_20d = prev_rows['저가'].min()
    features['near_high_20d'] = c / high_20d if high_20d > 0 else 0
    features['from_low_20d'] = (c - low_20d) / low_20d * 100 if low_20d > 0 else 0

    # === 변동성 ===
    features['volatility'] = prev_rows['종가'].pct_change().std() * 100

    # === 거래대금 ===
    features['trade_value'] = row['거래량'] * c / 100000000

    # B필터: 급등 여부 (전일 +15% 이상)
    features['is_surge'] = 1 if features['day_change'] >= 15 else 0

    # B필터: 2일 연속 급등 여부
    if idx >= 2:
        prev_prev_close = df.iloc[idx-2]['종가']
        two_day_change = (c - prev_prev_close) / prev_prev_close * 100 if prev_prev_close > 0 else 0
        features['two_day_surge'] = 1 if two_day_change >= 20 else 0
    else:
        features['two_day_surge'] = 0

    return features

# 학습 데이터 생성
samples = []
print("    피처 추출 중...")

for ticker, df in all_data.items():
    for i in range(21, len(df) - 1):
        features = calculate_features(df, i)
        if features is None:
            continue

        # 기본 필터 (거래대금 50억+, 등락률 -15%~25%)
        if features['trade_value'] < 50:
            continue
        if not (-15 <= features['day_change'] <= 25):
            continue

        # 타겟: 다음날 갭
        today_close = df.iloc[i]['종가']
        next_open = df.iloc[i + 1]['시가']
        gap_pct = (next_open - today_close) / today_close * 100

        features['gap_pct'] = gap_pct
        features['ticker'] = ticker
        features['date'] = df.index[i]

        samples.append(features)

df_samples = pd.DataFrame(samples)
print(f"    → {len(df_samples):,}개 샘플 생성")

if len(df_samples) == 0:
    print("    ⚠ 샘플이 없습니다. 종료합니다.")
    exit()

# 갭 분포
print(f"\n    갭 분포:")
print(f"    → 평균: {df_samples['gap_pct'].mean():.3f}%")
print(f"    → 1%+ 갭상승: {(df_samples['gap_pct'] >= 1).sum():,}건 ({(df_samples['gap_pct'] >= 1).mean()*100:.1f}%)")
print(f"    → 2%+ 갭상승: {(df_samples['gap_pct'] >= 2).sum():,}건 ({(df_samples['gap_pct'] >= 2).mean()*100:.1f}%)")

# =============================================================================
# 3. 모델 학습
# =============================================================================
print("\n[3] 모델 학습...")

feature_cols = ['close_pos', 'close_high', 'is_bull', 'body_ratio', 'upper_wick',
                'lower_wick', 'day_change', 'dist_ma5', 'dist_ma20', 'vol_ratio',
                'rsi', 'consec_bull', 'aligned', 'near_high_20d', 'from_low_20d',
                'volatility']

X = df_samples[feature_cols].values
y = df_samples['gap_pct'].values

# 시간순 분할
split_idx = int(len(X) * 0.7)
X_train, X_test = X[:split_idx], X[split_idx:]
y_train, y_test = y[:split_idx], y[split_idx:]
df_test = df_samples.iloc[split_idx:].copy()

print(f"    학습: {len(X_train):,}개, 테스트: {len(X_test):,}개")

# XGBoost 모델
model = xgb.XGBRegressor(n_estimators=100, max_depth=5, random_state=42, verbosity=0)
model.fit(X_train, y_train)

pred = model.predict(X_test)
mae = mean_absolute_error(y_test, pred)
print(f"    MAE: {mae:.4f}")

df_test['pred_gap'] = pred

# =============================================================================
# 4. A+B 결합 백테스트
# =============================================================================
print("\n[4] A+B 결합 백테스트...")
print("-" * 70)
print(f"    {'조건':<40} {'거래수':>8} {'승률':>8} {'평균수익':>10}")
print("-" * 70)

tax_rate = 0.00203

results = []

# 테스트할 조건 조합
conditions = [
    ("기준: 예측갭 >= 1%", lambda df: df['pred_gap'] >= 1.0),
    ("+ B1: 급등(+15%) 제외", lambda df: (df['pred_gap'] >= 1.0) & (df['is_surge'] == 0)),
    ("+ B2: RSI>70 제외", lambda df: (df['pred_gap'] >= 1.0) & (df['is_surge'] == 0) & (df['rsi_overbought'] == 0)),
    ("+ B3: 거래량감소 제외", lambda df: (df['pred_gap'] >= 1.0) & (df['is_surge'] == 0) & (df['rsi_overbought'] == 0) & (df['vol_declining'] == 0)),
    ("+ B4: 2일급등 제외", lambda df: (df['pred_gap'] >= 1.0) & (df['is_surge'] == 0) & (df['rsi_overbought'] == 0) & (df['vol_declining'] == 0) & (df['two_day_surge'] == 0)),
]

for name, condition in conditions:
    filtered = df_test[condition(df_test)].copy()

    if len(filtered) == 0:
        print(f"    {name:<40} {'N/A':>8}")
        continue

    filtered['return'] = filtered['gap_pct'] - (tax_rate * 100)

    trades = len(filtered)
    wins = (filtered['gap_pct'] > 0).sum()
    win_rate = wins / trades * 100
    avg_return = filtered['return'].mean()

    results.append({
        'condition': name,
        'trades': trades,
        'wins': wins,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'total_return': filtered['return'].sum()
    })

    print(f"    {name:<40} {trades:>8,} {win_rate:>7.1f}% {avg_return:>9.3f}%")

# =============================================================================
# 5. 예측갭 임계값 + B필터 조합
# =============================================================================
print("\n[5] 예측갭 임계값별 + B필터 전체 적용...")
print("-" * 70)

for threshold in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
    # B필터 전체 적용
    filtered = df_test[
        (df_test['pred_gap'] >= threshold) &
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
        'condition': f'예측갭>={threshold}% + B필터',
        'trades': trades,
        'wins': wins,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'total_return': filtered['return'].sum()
    })

    print(f"    예측갭 >= {threshold}% + B필터: {trades:,}건, 승률 {win_rate:.1f}%, 평균수익 {avg_return:.3f}%")

# =============================================================================
# 6. 최적 조건 월별 성과
# =============================================================================
print("\n[6] 최적 조건 (예측갭>=1% + B필터) 월별 성과...")
print("-" * 70)

optimal = df_test[
    (df_test['pred_gap'] >= 1.0) &
    (df_test['is_surge'] == 0) &
    (df_test['rsi_overbought'] == 0) &
    (df_test['vol_declining'] == 0) &
    (df_test['two_day_surge'] == 0)
].copy()

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
# 7. 결과 저장
# =============================================================================
print("\n[7] 결과 저장...")

output_path = "/home/kimhc/Stock/output/v10_combined_backtest.xlsx"

with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    pd.DataFrame(results).to_excel(writer, sheet_name='조건별_성과', index=False)
    monthly.to_excel(writer, sheet_name='월별_성과', index=False)

    # 피처 중요도
    importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    importance.to_excel(writer, sheet_name='피처_중요도', index=False)

    # 상세 거래
    detail = optimal[['date', 'ticker', 'pred_gap', 'gap_pct', 'return',
                      'day_change', 'vol_ratio', 'rsi']].sort_values('date')
    detail.to_excel(writer, sheet_name='거래_상세', index=False)

print(f"    → 저장 완료: {output_path}")

# =============================================================================
# 최종 요약
# =============================================================================
print("\n" + "=" * 70)
print("  V10 결과 요약 (A: 갭크기예측 + B: 손실필터)")
print("=" * 70)

# 최고 수익 조건 찾기
best = max(results, key=lambda x: x['avg_return'])
optimal_trades = len(optimal)
optimal_wins = (optimal['gap_pct'] > 0).sum()
optimal_win_rate = optimal_wins / optimal_trades * 100 if optimal_trades > 0 else 0
optimal_avg_return = optimal['return'].mean() if optimal_trades > 0 else 0

print(f"""
  최적 조건: {best['condition']}
    - 거래 수: {best['trades']:,}건
    - 승률: {best['win_rate']:.1f}%
    - 평균 수익률: {best['avg_return']:.3f}%
    - 총 수익률: {best['total_return']:.2f}%

  비교:
    - V9 (85%+ 확률): 485건, 62.5% 승률, +0.70% 수익률
    - V10 (A+B 결합): {best['trades']:,}건, {best['win_rate']:.1f}% 승률, {best['avg_return']:.3f}% 수익률
""")
print("=" * 70)
