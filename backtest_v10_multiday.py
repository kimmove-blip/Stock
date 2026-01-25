#!/usr/bin/env python3
"""
V10 + 2~3일 보유 전략 (옵션 D)
- 익일 시가 매수 후 2~3일 보유
- 최적 보유 기간 탐색
"""
import pandas as pd
import numpy as np
from pykrx import stock
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 70)
print("  V10 + 다일 보유 전략 테스트")
print("=" * 70)

# =============================================================================
# 1. 데이터 수집
# =============================================================================
print("\n[1] 데이터 수집...")

end_date = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=400)).strftime('%Y%m%d')

from pykrx.website.krx.market.ticker import StockTicker
ticker_df = StockTicker().listed
ticker_df = ticker_df[ticker_df['시장'].isin(['STK', 'KSQ'])]
all_tickers = ticker_df.index.tolist()
print(f"    → {len(all_tickers)}개 종목")

all_data = {}
for i, ticker in enumerate(all_tickers):
    if (i + 1) % 500 == 0:
        print(f"    → {i+1}/{len(all_tickers)} 로딩 중...")
    try:
        df = stock.get_market_ohlcv(start_date, end_date, ticker)
        if len(df) >= 60:
            df['거래대금'] = df['거래량'] * df['종가']
            all_data[ticker] = df
    except:
        pass

print(f"    → {len(all_data)}개 종목 로드 완료")

# =============================================================================
# 2. V10 신호 + 다일 수익률 계산
# =============================================================================
print("\n[2] V10 신호 + 다일 수익률 계산...")

def check_v10_signal(df, i):
    """V10 신호 체크 (B필터)"""
    if i < 20:
        return False, {}

    today = df.iloc[i]

    # 거래대금 50억 이상
    if today['거래대금'] < 50_000_000_000:
        return False, {}

    # 당일 등락률 0~10%
    prev_close = df.iloc[i-1]['종가']
    day_change = (today['종가'] - prev_close) / prev_close * 100
    if not (0 <= day_change <= 10):
        return False, {}

    # 20일 평균 거래대금
    avg_volume_20 = df.iloc[i-20:i]['거래대금'].mean()
    vol_ratio = today['거래대금'] / avg_volume_20 if avg_volume_20 > 0 else 0

    # B필터 조건들
    ma5 = df.iloc[i-5:i+1]['종가'].mean()
    ma20 = df.iloc[i-20:i+1]['종가'].mean()

    b_filter = (
        vol_ratio >= 2.0 and           # 거래량 2배 이상
        today['종가'] > ma5 and        # 종가 > MA5
        ma5 > ma20                     # MA5 > MA20
    )

    if not b_filter:
        return False, {}

    return True, {
        'day_change': day_change,
        'vol_ratio': vol_ratio,
        'close': today['종가']
    }

results = []
print("    신호 스캔 중...")

for ticker, df in all_data.items():
    # 충분한 미래 데이터 필요 (최대 5일 보유)
    for i in range(60, len(df) - 6):
        date = df.index[i]

        # V10 신호 체크
        has_signal, info = check_v10_signal(df, i)
        if not has_signal:
            continue

        today_close = df.iloc[i]['종가']
        next_open = df.iloc[i + 1]['시가']  # 익일 시가 (매수가)

        # 다양한 보유 기간별 수익률 계산
        returns = {}

        # 익일 시가 대비 수익률
        for hold_days in [1, 2, 3, 4, 5]:
            if i + 1 + hold_days < len(df):
                # 보유 n일 후 종가
                exit_close = df.iloc[i + 1 + hold_days]['종가']
                ret = (exit_close - next_open) / next_open * 100
                returns[f'ret_{hold_days}d'] = ret

                # 보유 n일 후 시가 (장초 청산)
                if i + 1 + hold_days < len(df):
                    exit_open = df.iloc[i + 1 + hold_days]['시가']
                    ret_open = (exit_open - next_open) / next_open * 100
                    returns[f'ret_{hold_days}d_open'] = ret_open

        # 갭 수익률 (기존)
        gap_pct = (next_open - today_close) / today_close * 100

        result = {
            'date': date,
            'ticker': ticker,
            'day_change': info['day_change'],
            'vol_ratio': info['vol_ratio'],
            'close': today_close,
            'next_open': next_open,
            'gap_pct': gap_pct,
            **returns
        }
        results.append(result)

df_results = pd.DataFrame(results)
print(f"    → {len(df_results):,}개 신호 발생")

# =============================================================================
# 3. 보유 기간별 성과 분석
# =============================================================================
print("\n[3] 보유 기간별 성과 분석...")
print("-" * 70)

print("\n    [종가 청산 기준]")
print(f"    {'보유기간':^10} {'거래수':^8} {'승률':^10} {'평균수익':^10} {'중앙값':^10}")
print("    " + "-" * 50)

for hold in [1, 2, 3, 4, 5]:
    col = f'ret_{hold}d'
    if col in df_results.columns:
        valid = df_results[df_results[col].notna()]
        wins = len(valid[valid[col] > 0])
        win_rate = wins / len(valid) * 100 if len(valid) > 0 else 0
        avg_ret = valid[col].mean()
        median_ret = valid[col].median()
        print(f"    {hold}일 보유      {len(valid):^8} {win_rate:^9.1f}% {avg_ret:^9.3f}% {median_ret:^9.3f}%")

print("\n    [시가 청산 기준 (장초 매도)]")
print(f"    {'보유기간':^10} {'거래수':^8} {'승률':^10} {'평균수익':^10} {'중앙값':^10}")
print("    " + "-" * 50)

for hold in [1, 2, 3, 4, 5]:
    col = f'ret_{hold}d_open'
    if col in df_results.columns:
        valid = df_results[df_results[col].notna()]
        wins = len(valid[valid[col] > 0])
        win_rate = wins / len(valid) * 100 if len(valid) > 0 else 0
        avg_ret = valid[col].mean()
        median_ret = valid[col].median()
        print(f"    {hold}일 보유      {len(valid):^8} {win_rate:^9.1f}% {avg_ret:^9.3f}% {median_ret:^9.3f}%")

# =============================================================================
# 4. 거래량 조건별 최적 보유 기간
# =============================================================================
print("\n[4] 거래량 조건별 최적 보유 기간...")
print("-" * 70)

for vol_min in [2.0, 3.0, 4.0, 5.0]:
    sub = df_results[df_results['vol_ratio'] >= vol_min]
    if len(sub) < 10:
        continue

    print(f"\n    [거래량 {vol_min}배 이상: {len(sub)}건]")

    best_ret = -999
    best_hold = 0

    for hold in [1, 2, 3, 4, 5]:
        col = f'ret_{hold}d'
        if col in sub.columns:
            valid = sub[sub[col].notna()]
            if len(valid) > 0:
                avg_ret = valid[col].mean()
                wins = len(valid[valid[col] > 0])
                win_rate = wins / len(valid) * 100
                print(f"      {hold}일: 승률 {win_rate:.1f}%, 수익률 {avg_ret:.3f}%")

                if avg_ret > best_ret:
                    best_ret = avg_ret
                    best_hold = hold

    print(f"      → 최적: {best_hold}일 보유 (수익률 {best_ret:.3f}%)")

# =============================================================================
# 5. 손절/익절 전략 시뮬레이션
# =============================================================================
print("\n[5] 손절/익절 전략 시뮬레이션...")
print("-" * 70)

# 2일 보유 기준으로 손절/익절 테스트
def simulate_with_stops(df, stop_loss, take_profit):
    """손절/익절 적용 시뮬레이션"""
    returns = []

    for _, row in df.iterrows():
        entry = row['next_open']

        # 1일차 종가 체크
        if f'ret_1d' in row and pd.notna(row['ret_1d']):
            ret_1d = row['ret_1d']

            if ret_1d <= stop_loss:
                returns.append(stop_loss)
                continue
            if ret_1d >= take_profit:
                returns.append(take_profit)
                continue

        # 2일차 종가
        if f'ret_2d' in row and pd.notna(row['ret_2d']):
            returns.append(row['ret_2d'])
        else:
            returns.append(0)

    return returns

print("\n    [2일 보유 + 손절/익절]")
print(f"    {'손절':^8} {'익절':^8} {'승률':^10} {'평균수익':^10}")
print("    " + "-" * 40)

for sl in [-3, -5, -7]:
    for tp in [3, 5, 7, 10]:
        rets = simulate_with_stops(df_results, sl, tp)
        wins = sum(1 for r in rets if r > 0)
        win_rate = wins / len(rets) * 100 if rets else 0
        avg_ret = np.mean(rets) if rets else 0
        print(f"    {sl}%      {tp}%      {win_rate:^9.1f}% {avg_ret:^9.3f}%")

# =============================================================================
# 6. 결과 저장
# =============================================================================
print("\n[6] 결과 저장...")

output_path = '/home/kimhc/Stock/output/v10_multiday_backtest.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    df_results.to_excel(writer, sheet_name='전체신호', index=False)

    # 보유기간별 통계
    hold_stats = []
    for hold in [1, 2, 3, 4, 5]:
        col = f'ret_{hold}d'
        if col in df_results.columns:
            valid = df_results[df_results[col].notna()]
            wins = len(valid[valid[col] > 0])
            hold_stats.append({
                '보유기간': f'{hold}일',
                '거래수': len(valid),
                '승률': wins / len(valid) * 100 if len(valid) > 0 else 0,
                '평균수익률': valid[col].mean(),
                '중앙값': valid[col].median(),
                '최대수익': valid[col].max(),
                '최대손실': valid[col].min()
            })

    pd.DataFrame(hold_stats).to_excel(writer, sheet_name='보유기간별통계', index=False)

print(f"    → 저장 완료: {output_path}")

# =============================================================================
# 결과 요약
# =============================================================================
print("\n" + "=" * 70)
print("  결과 요약")
print("=" * 70)

# 최적 보유 기간 찾기
best_hold = 1
best_ret = df_results['ret_1d'].mean() if 'ret_1d' in df_results.columns else 0

for hold in [2, 3, 4, 5]:
    col = f'ret_{hold}d'
    if col in df_results.columns:
        avg = df_results[col].mean()
        if avg > best_ret:
            best_ret = avg
            best_hold = hold

col = f'ret_{best_hold}d'
valid = df_results[df_results[col].notna()]
wins = len(valid[valid[col] > 0])
win_rate = wins / len(valid) * 100 if len(valid) > 0 else 0

print(f"""
  갭 수익 (기존):
    - 평균 수익률: {df_results['gap_pct'].mean():.3f}%
    - 승률: {len(df_results[df_results['gap_pct'] > 0]) / len(df_results) * 100:.1f}%

  최적 보유 기간: {best_hold}일
    - 거래 수: {len(valid)}건
    - 승률: {win_rate:.1f}%
    - 평균 수익률: {best_ret:.3f}%
""")

print("=" * 70)
