#!/usr/bin/env python3
"""
V10 + 시장 상황 필터 (옵션 C)
- KOSPI 지수 상승 추세일 때만 매매
- 시장 하락장에서는 매매 자제
"""
import pandas as pd
import numpy as np
from pykrx import stock
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 70)
print("  V10 + 시장 상황 필터 테스트")
print("=" * 70)

# =============================================================================
# 1. 데이터 수집
# =============================================================================
print("\n[1] 데이터 수집...")

end_date = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=400)).strftime('%Y%m%d')

# KOSPI 지수 데이터
print("    → KOSPI 지수 로딩...")
try:
    kospi = stock.get_index_ohlcv_by_date(start_date, end_date, "1001")  # KOSPI
except:
    # 대안: 개별 주식 기반으로 시장 추세 추정
    kospi = stock.get_market_ohlcv(start_date, end_date, "005930")  # 삼성전자로 대체
kospi['ma5'] = kospi['종가'].rolling(5).mean()
kospi['ma20'] = kospi['종가'].rolling(20).mean()
kospi['ma60'] = kospi['종가'].rolling(60).mean()

# 시장 상태 판단
kospi['market_trend'] = 'neutral'
kospi.loc[kospi['종가'] > kospi['ma20'], 'market_trend'] = 'bullish'
kospi.loc[kospi['종가'] < kospi['ma20'], 'market_trend'] = 'bearish'

# 강한 상승장 (종가 > MA20 > MA60)
kospi['strong_bull'] = (kospi['종가'] > kospi['ma20']) & (kospi['ma20'] > kospi['ma60'])

# 5일 수익률
kospi['kospi_5d_ret'] = kospi['종가'].pct_change(5) * 100

print(f"    → KOSPI 데이터: {len(kospi)}일")

# 개별 종목 데이터
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
# 2. V10 신호 + 시장 필터 백테스트
# =============================================================================
print("\n[2] V10 신호 + 시장 필터 백테스트...")

def check_v10_signal(df, i):
    """V10 신호 체크 (2%+갭 + B필터)"""
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
    for i in range(60, len(df) - 1):
        date = df.index[i]

        # V10 신호 체크
        has_signal, info = check_v10_signal(df, i)
        if not has_signal:
            continue

        # 시장 상황 확인
        if date not in kospi.index:
            continue

        market_row = kospi.loc[date]
        market_trend = market_row['market_trend']
        strong_bull = market_row['strong_bull']
        kospi_5d_ret = market_row['kospi_5d_ret']

        # 익일 갭 계산
        today_close = df.iloc[i]['종가']
        next_open = df.iloc[i + 1]['시가']
        gap_pct = (next_open - today_close) / today_close * 100

        results.append({
            'date': date,
            'ticker': ticker,
            'day_change': info['day_change'],
            'vol_ratio': info['vol_ratio'],
            'gap_pct': gap_pct,
            'gap_up': 1 if gap_pct > 0 else 0,
            'market_trend': market_trend,
            'strong_bull': strong_bull,
            'kospi_5d_ret': kospi_5d_ret
        })

df_results = pd.DataFrame(results)
print(f"    → {len(df_results):,}개 신호 발생")

# =============================================================================
# 3. 시장 필터별 성과 분석
# =============================================================================
print("\n[3] 시장 필터별 성과 분석...")
print("-" * 70)

def calc_stats(df_sub, label):
    if len(df_sub) == 0:
        return None
    wins = len(df_sub[df_sub['gap_pct'] > 0])
    win_rate = wins / len(df_sub) * 100
    avg_ret = df_sub['gap_pct'].mean()
    return {
        'label': label,
        'count': len(df_sub),
        'win_rate': win_rate,
        'avg_ret': avg_ret
    }

stats_list = []

# 기준선: V10 전체
base = calc_stats(df_results, 'V10 전체 (기준)')
stats_list.append(base)
print(f"\n    V10 전체 (기준): {base['count']}건, 승률 {base['win_rate']:.1f}%, 수익률 {base['avg_ret']:.3f}%")

# 시장 추세별
print("\n    [시장 추세별]")
for trend in ['bullish', 'neutral', 'bearish']:
    sub = df_results[df_results['market_trend'] == trend]
    if len(sub) > 0:
        s = calc_stats(sub, f'시장 {trend}')
        stats_list.append(s)
        print(f"    시장 {trend}: {s['count']}건, 승률 {s['win_rate']:.1f}%, 수익률 {s['avg_ret']:.3f}%")

# 강한 상승장만
print("\n    [강한 상승장 필터]")
strong = df_results[df_results['strong_bull'] == True]
s = calc_stats(strong, '강한 상승장 (종가>MA20>MA60)')
stats_list.append(s)
print(f"    강한 상승장: {s['count']}건, 승률 {s['win_rate']:.1f}%, 수익률 {s['avg_ret']:.3f}%")

# KOSPI 5일 수익률 기준
print("\n    [KOSPI 5일 수익률 기준]")
for threshold in [0, 1, 2, 3]:
    sub = df_results[df_results['kospi_5d_ret'] > threshold]
    if len(sub) > 0:
        s = calc_stats(sub, f'KOSPI 5일 > {threshold}%')
        stats_list.append(s)
        print(f"    KOSPI 5일 > {threshold}%: {s['count']}건, 승률 {s['win_rate']:.1f}%, 수익률 {s['avg_ret']:.3f}%")

# 복합 조건
print("\n    [복합 조건]")

# 상승장 + 거래량 3배
cond1 = df_results[(df_results['market_trend'] == 'bullish') & (df_results['vol_ratio'] >= 3.0)]
if len(cond1) > 0:
    s = calc_stats(cond1, '상승장 + 거래량3배')
    stats_list.append(s)
    print(f"    상승장 + 거래량3배: {s['count']}건, 승률 {s['win_rate']:.1f}%, 수익률 {s['avg_ret']:.3f}%")

# 강한 상승장 + 거래량 3배
cond2 = df_results[(df_results['strong_bull'] == True) & (df_results['vol_ratio'] >= 3.0)]
if len(cond2) > 0:
    s = calc_stats(cond2, '강한상승장 + 거래량3배')
    stats_list.append(s)
    print(f"    강한상승장 + 거래량3배: {s['count']}건, 승률 {s['win_rate']:.1f}%, 수익률 {s['avg_ret']:.3f}%")

# KOSPI 5일 > 2% + 거래량 3배
cond3 = df_results[(df_results['kospi_5d_ret'] > 2) & (df_results['vol_ratio'] >= 3.0)]
if len(cond3) > 0:
    s = calc_stats(cond3, 'KOSPI5일>2% + 거래량3배')
    stats_list.append(s)
    print(f"    KOSPI5일>2% + 거래량3배: {s['count']}건, 승률 {s['win_rate']:.1f}%, 수익률 {s['avg_ret']:.3f}%")

# =============================================================================
# 4. 월별 성과 (최적 조건)
# =============================================================================
print("\n[4] 최적 조건 월별 성과...")
print("-" * 70)

# 최적 조건: 상승장 + 거래량 3배
best_df = df_results[(df_results['market_trend'] == 'bullish') & (df_results['vol_ratio'] >= 3.0)].copy()

if len(best_df) > 0:
    best_df['month'] = best_df['date'].dt.to_period('M')
    monthly = best_df.groupby('month').agg({
        'gap_pct': ['count', lambda x: (x > 0).sum() / len(x) * 100, 'mean', 'sum']
    }).round(3)
    monthly.columns = ['거래수', '승률', '평균수익', '총수익']

    print(f"\n    {'월':^12} {'거래수':^8} {'승률':^10} {'평균수익':^10} {'총수익':^10}")
    print("    " + "-" * 50)
    for idx, row in monthly.iterrows():
        print(f"    {str(idx):^12} {int(row['거래수']):^8} {row['승률']:^9.1f}% {row['평균수익']:^9.3f}% {row['총수익']:^9.2f}%")

# =============================================================================
# 5. 결과 저장
# =============================================================================
print("\n[5] 결과 저장...")

output_path = '/home/kimhc/Stock/output/v10_market_filter_backtest.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    df_results.to_excel(writer, sheet_name='전체신호', index=False)

    if len(best_df) > 0:
        best_df.to_excel(writer, sheet_name='최적조건', index=False)

    # 통계 요약
    stats_df = pd.DataFrame(stats_list)
    stats_df.to_excel(writer, sheet_name='통계요약', index=False)

print(f"    → 저장 완료: {output_path}")

# =============================================================================
# 결과 요약
# =============================================================================
print("\n" + "=" * 70)
print("  결과 요약")
print("=" * 70)

print(f"""
  V10 전체 (기준):
    - 거래 수: {base['count']}건
    - 승률: {base['win_rate']:.1f}%
    - 평균 수익률: {base['avg_ret']:.3f}%
""")

if len(cond1) > 0:
    s1 = calc_stats(cond1, '')
    print(f"""  상승장 + 거래량3배:
    - 거래 수: {s1['count']}건
    - 승률: {s1['win_rate']:.1f}%
    - 평균 수익률: {s1['avg_ret']:.3f}%
""")

print("=" * 70)
