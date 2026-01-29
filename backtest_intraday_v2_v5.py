#!/usr/bin/env python3
"""
인트라데이 스코어 기반 백테스트
- 데이터: output/intraday_scores/*.csv
- 조건: 20종목 보유한도, 종목당 10만원 투자
"""

import os
import glob
import pandas as pd
from datetime import datetime
from collections import defaultdict

# 설정
INTRADAY_DIR = '/home/kimhc/Stock/output/intraday_scores'
INVESTMENT_PER_STOCK = 100000  # 종목당 10만원
MAX_HOLDINGS = 20  # 최대 보유 종목 수
MAX_CHANGE_PCT = 15  # 당일 15% 이상 상승 종목 매수 제외


def load_all_csv():
    """모든 인트라데이 스코어 CSV 로드"""
    files = sorted(glob.glob(os.path.join(INTRADAY_DIR, '*.csv')))
    all_data = []

    for f in files:
        basename = os.path.basename(f)
        # 파일명: 20260127_1543.csv
        date_str = basename[:8]
        time_str = basename[9:13]

        try:
            df = pd.read_csv(f)
            df['datetime'] = f"{date_str}_{time_str}"
            df['date'] = date_str
            df['time'] = time_str
            all_data.append(df)
        except Exception as e:
            print(f"파일 로드 실패: {f} - {e}")

    if not all_data:
        return pd.DataFrame()

    combined = pd.concat(all_data, ignore_index=True)
    print(f"총 {len(files)}개 파일, {len(combined):,}개 레코드 로드")
    return combined


def backtest(data, score_col='v2', buy_threshold=60, sell_threshold=55):
    """
    백테스트 실행
    - score_col: 사용할 스코어 컬럼 (v1, v2, v3.5, v4, v5, v6, v7, v8, v9_prob, v10)
    - buy_threshold: 매수 기준점
    - sell_threshold: 매도 기준점 (이 점수 미만이면 매도)
    """
    holdings = {}  # {종목코드: {'buy_price': 가격, 'quantity': 수량, 'buy_time': 시간}}
    trades = []

    # 시간순 정렬
    datetimes = sorted(data['datetime'].unique())

    for dt in datetimes:
        snapshot = data[data['datetime'] == dt]

        # 1. 매도 체크 (보유 종목 중 스코어가 매도기준 미만인 것)
        to_sell = []
        for code, info in holdings.items():
            stock_data = snapshot[snapshot['code'] == code]
            if stock_data.empty:
                continue

            row = stock_data.iloc[0]
            score = row.get(score_col, 0) or 0

            if score < sell_threshold:
                sell_price = row['close']
                buy_price = info['buy_price']
                quantity = info['quantity']
                profit = (sell_price - buy_price) * quantity
                profit_rate = (sell_price / buy_price - 1) * 100 if buy_price > 0 else 0

                trades.append({
                    'datetime': dt,
                    'code': code,
                    'name': row.get('name', code),
                    'side': 'sell',
                    'price': sell_price,
                    'quantity': quantity,
                    'amount': sell_price * quantity,
                    'profit': profit,
                    'profit_rate': profit_rate,
                    'score': score,
                    'reason': f'{score_col} {score:.0f} < {sell_threshold}'
                })
                to_sell.append(code)

        for code in to_sell:
            del holdings[code]

        # 2. 매수 체크 (스코어가 매수기준 이상인 것)
        if len(holdings) < MAX_HOLDINGS:
            # 매수 후보: 스코어가 매수기준 이상, 당일 상승률 15% 미만, 미보유
            buy_candidates = snapshot[
                (snapshot[score_col] >= buy_threshold) &
                (snapshot['change_pct'] < MAX_CHANGE_PCT) &
                (~snapshot['code'].isin(holdings.keys()))
            ].copy()

            # 스코어 높은 순 정렬
            buy_candidates = buy_candidates.sort_values(score_col, ascending=False)

            slots_available = MAX_HOLDINGS - len(holdings)
            for _, row in buy_candidates.head(slots_available).iterrows():
                code = row['code']
                price = row['close']
                if price <= 0:
                    continue

                quantity = INVESTMENT_PER_STOCK // price
                if quantity <= 0:
                    continue

                holdings[code] = {
                    'buy_price': price,
                    'quantity': quantity,
                    'buy_time': dt
                }

                trades.append({
                    'datetime': dt,
                    'code': code,
                    'name': row.get('name', code),
                    'side': 'buy',
                    'price': price,
                    'quantity': quantity,
                    'amount': price * quantity,
                    'profit': 0,
                    'profit_rate': 0,
                    'score': row[score_col],
                    'reason': f'{score_col} {row[score_col]:.0f} >= {buy_threshold}'
                })

    # 미실현 손익 계산 (마지막 스냅샷 기준)
    last_snapshot = data[data['datetime'] == datetimes[-1]]
    unrealized_profit = 0
    invested_amount = 0

    for code, info in holdings.items():
        stock_data = last_snapshot[last_snapshot['code'] == code]
        if stock_data.empty:
            continue

        current_price = stock_data.iloc[0]['close']
        buy_price = info['buy_price']
        quantity = info['quantity']

        invested_amount += buy_price * quantity
        unrealized_profit += (current_price - buy_price) * quantity

    # 실현 손익 계산
    realized_profit = sum(t['profit'] for t in trades if t['side'] == 'sell')
    total_investment = sum(t['amount'] for t in trades if t['side'] == 'buy')

    return {
        'trades': trades,
        'holdings': holdings,
        'realized_profit': realized_profit,
        'unrealized_profit': unrealized_profit,
        'total_profit': realized_profit + unrealized_profit,
        'total_investment': total_investment,
        'invested_amount': invested_amount,
        'trade_count': len(trades)
    }


def run_grid_search(data, score_col='v2'):
    """그리드 서치로 최적 매수/매도 기준 탐색"""
    results = []

    if score_col == 'v9_prob':
        buy_range = range(40, 75, 5)  # 40% ~ 70%
        sell_range = range(25, 50, 5)  # 25% ~ 45%
    else:
        buy_range = range(55, 85, 5)  # 55점 ~ 80점
        sell_range = range(35, 65, 5)  # 35점 ~ 60점

    for buy_th in buy_range:
        for sell_th in sell_range:
            if sell_th >= buy_th:
                continue

            result = backtest(data, score_col, buy_th, sell_th)

            total_profit = result['total_profit']
            total_investment = result['total_investment']
            profit_rate = (total_profit / total_investment * 100) if total_investment > 0 else 0

            results.append({
                'score_col': score_col,
                'buy_threshold': buy_th,
                'sell_threshold': sell_th,
                'total_profit': total_profit,
                'total_investment': total_investment,
                'profit_rate': profit_rate,
                'trade_count': result['trade_count'],
                'holdings_count': len(result['holdings'])
            })

    return sorted(results, key=lambda x: x['profit_rate'], reverse=True)


def main():
    print("=" * 60)
    print("인트라데이 스코어 백테스트")
    print(f"보유한도: {MAX_HOLDINGS}종목, 종목당: {INVESTMENT_PER_STOCK:,}원")
    print("=" * 60)

    data = load_all_csv()
    if data.empty:
        print("데이터 없음")
        return

    print(f"\n분석 기간: {data['date'].min()} ~ {data['date'].max()}")
    print(f"분석 시간대: {data['time'].min()} ~ {data['time'].max()}")

    # 각 버전별 최적 조합 탐색
    score_columns = ['v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9_prob']

    all_results = []

    print("\n" + "=" * 60)
    print("버전별 최적 조합 탐색 중...")
    print("=" * 60)

    for score_col in score_columns:
        if score_col not in data.columns:
            print(f"{score_col} 컬럼 없음, 건너뜀")
            continue

        results = run_grid_search(data, score_col)
        if results:
            best = results[0]
            all_results.append(best)
            print(f"\n[{score_col}] 최적: 매수 {best['buy_threshold']}점, 매도 {best['sell_threshold']}점")
            print(f"  → 수익률: {best['profit_rate']:.2f}%, 손익: {best['total_profit']:,.0f}원, 거래: {best['trade_count']}회")

    # 전체 순위
    all_results.sort(key=lambda x: x['profit_rate'], reverse=True)

    print("\n" + "=" * 60)
    print("전체 순위 (상위 10개)")
    print("=" * 60)
    print(f"{'순위':>4} {'버전':>8} {'매수':>6} {'매도':>6} {'수익률':>10} {'손익':>14} {'거래':>6}")
    print("-" * 60)

    for i, r in enumerate(all_results[:10], 1):
        print(f"{i:>4} {r['score_col']:>8} {r['buy_threshold']:>6} {r['sell_threshold']:>6} "
              f"{r['profit_rate']:>9.2f}% {r['total_profit']:>13,.0f}원 {r['trade_count']:>6}회")

    # 상세 결과 (1위)
    if all_results:
        best = all_results[0]
        print("\n" + "=" * 60)
        print(f"1위 상세 결과: {best['score_col']} {best['buy_threshold']}/{best['sell_threshold']}")
        print("=" * 60)

        result = backtest(data, best['score_col'], best['buy_threshold'], best['sell_threshold'])

        # 매수/매도 내역
        buy_trades = [t for t in result['trades'] if t['side'] == 'buy']
        sell_trades = [t for t in result['trades'] if t['side'] == 'sell']

        print(f"\n총 거래: {len(result['trades'])}회 (매수 {len(buy_trades)}회, 매도 {len(sell_trades)}회)")
        print(f"실현 손익: {result['realized_profit']:,.0f}원")
        print(f"미실현 손익: {result['unrealized_profit']:,.0f}원")
        print(f"총 손익: {result['total_profit']:,.0f}원")
        print(f"총 투자금: {result['total_investment']:,.0f}원")
        print(f"수익률: {best['profit_rate']:.2f}%")
        print(f"현재 보유: {len(result['holdings'])}종목")

        # 수익 매도 / 손실 매도
        profit_sells = [t for t in sell_trades if t['profit'] >= 0]
        loss_sells = [t for t in sell_trades if t['profit'] < 0]

        print(f"\n수익 매도: {len(profit_sells)}회, 손실 매도: {len(loss_sells)}회")
        print(f"승률: {len(profit_sells) / len(sell_trades) * 100:.1f}%" if sell_trades else "매도 없음")


if __name__ == '__main__':
    main()
