#!/usr/bin/env python3
"""
손절 기준별 1개월 백테스트
- 손절 10%, 6%, 손절없음 비교
"""

import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import OUTPUT_DIR
from technical_analyst import TechnicalAnalyst

def load_daily_scores(date_str):
    """특정 날짜의 스크리닝 점수 로드"""
    json_path = OUTPUT_DIR / f"top100_{date_str}.json"
    if not json_path.exists():
        return {}

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        scores = {}
        # stocks 배열에서 점수 추출
        for stock in data.get('stocks', []):
            code = stock.get('code')
            if code:
                scores[code] = {
                    'score': stock.get('score', 0),
                    'name': stock.get('name', code),
                    'close': stock.get('close', 0),
                    'change_pct': stock.get('change_pct', 0),
                }

        # all_scores에서 추가 점수 추출
        all_scores = data.get('screening_stats', {}).get('all_scores', {})
        for code, score in all_scores.items():
            if code not in scores:
                scores[code] = {'score': score, 'name': code, 'close': 0, 'change_pct': 0}

        return scores
    except:
        return {}


def get_stock_price_history(code, days=40):
    """종목의 과거 가격 데이터 조회"""
    analyst = TechnicalAnalyst()
    df = analyst.get_ohlcv(code, days=days)
    if df is None or len(df) == 0:
        return {}

    prices = {}
    for idx, row in df.iterrows():
        date_str = idx.strftime('%Y%m%d')
        prices[date_str] = {
            'open': row['Open'],
            'high': row['High'],
            'low': row['Low'],
            'close': row['Close'],
        }
    return prices


def run_backtest(stop_loss_pct, days=30, initial_capital=10000000, max_holdings=10, buy_amount=1000000):
    """
    백테스트 실행

    Args:
        stop_loss_pct: 손절 기준 (예: -10, -6, None=손절없음)
        days: 백테스트 기간 (일)
        initial_capital: 초기 자본금
        max_holdings: 최대 보유 종목 수
        buy_amount: 종목당 투자금
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # 상태 변수
    cash = initial_capital
    holdings = {}  # {code: {name, quantity, avg_price, buy_date}}
    trades = []  # 거래 기록
    daily_values = []  # 일별 평가금액

    # 가격 캐시
    price_cache = {}

    def get_price(code, date_str):
        """특정 날짜의 종가 조회"""
        if code not in price_cache:
            price_cache[code] = get_stock_price_history(code, days=60)
        return price_cache[code].get(date_str, {}).get('close', 0)

    # 날짜별 시뮬레이션
    current_date = start_date
    prev_scores = {}

    while current_date <= end_date:
        date_str = current_date.strftime('%Y%m%d')

        # 주말 스킵
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        # 당일 스크리닝 점수 로드
        daily_scores = load_daily_scores(date_str)

        if not daily_scores:
            current_date += timedelta(days=1)
            prev_scores = daily_scores
            continue

        # 1. 매도 체크 (손절, 점수 하락)
        sell_list = []
        for code, holding in list(holdings.items()):
            current_price = get_price(code, date_str)
            if current_price <= 0:
                continue

            avg_price = holding['avg_price']
            profit_rate = (current_price - avg_price) / avg_price * 100
            current_score = daily_scores.get(code, {}).get('score', 50)

            sell_reason = None

            # 손절 체크
            if stop_loss_pct is not None and profit_rate <= stop_loss_pct:
                sell_reason = f"손절({profit_rate:.1f}%)"

            # 점수 하락 체크 (40점 미만)
            if current_score < 40:
                sell_reason = f"점수하락({current_score}점)"

            if sell_reason:
                sell_list.append({
                    'code': code,
                    'name': holding['name'],
                    'quantity': holding['quantity'],
                    'buy_price': avg_price,
                    'sell_price': current_price,
                    'profit_rate': profit_rate,
                    'reason': sell_reason,
                })

        # 매도 실행
        for sell in sell_list:
            code = sell['code']
            sell_amount = sell['sell_price'] * sell['quantity']
            cash += sell_amount

            trades.append({
                'date': date_str,
                'side': 'sell',
                'code': code,
                'name': sell['name'],
                'quantity': sell['quantity'],
                'price': sell['sell_price'],
                'amount': sell_amount,
                'profit_rate': sell['profit_rate'],
                'reason': sell['reason'],
            })

            del holdings[code]

        # 2. 매수 체크
        if len(holdings) < max_holdings and cash >= buy_amount:
            # 80점 이상 종목
            candidates = []
            for code, info in daily_scores.items():
                score = info.get('score', 0)
                if score >= 80:
                    candidates.append((code, info, score, "80+"))
                elif score >= 75:
                    # 연속성 체크 (이전 점수 75점 이상)
                    prev_score = prev_scores.get(code, {}).get('score', 0)
                    if prev_score >= 75:
                        candidates.append((code, info, score, f"75+(이전{prev_score})"))

            # 점수 높은 순 정렬
            candidates.sort(key=lambda x: x[2], reverse=True)

            for code, info, score, reason in candidates:
                if code in holdings:
                    continue
                if len(holdings) >= max_holdings:
                    break
                if cash < buy_amount:
                    break

                current_price = get_price(code, date_str)
                if current_price <= 0:
                    continue

                # 상한가 체크 (30% 이상 상승)
                change_pct = info.get('change_pct', 0)
                if change_pct >= 29:
                    continue

                quantity = int(buy_amount / current_price)
                if quantity <= 0:
                    continue

                buy_cost = current_price * quantity
                cash -= buy_cost

                holdings[code] = {
                    'name': info.get('name', code),
                    'quantity': quantity,
                    'avg_price': current_price,
                    'buy_date': date_str,
                }

                trades.append({
                    'date': date_str,
                    'side': 'buy',
                    'code': code,
                    'name': info.get('name', code),
                    'quantity': quantity,
                    'price': current_price,
                    'amount': buy_cost,
                    'reason': f"{reason} {score}점",
                })

        # 일별 평가금액 계산
        eval_amount = 0
        for code, holding in holdings.items():
            current_price = get_price(code, date_str)
            if current_price > 0:
                eval_amount += current_price * holding['quantity']

        total_value = cash + eval_amount
        daily_values.append({
            'date': date_str,
            'cash': cash,
            'eval_amount': eval_amount,
            'total_value': total_value,
            'holdings_count': len(holdings),
        })

        prev_scores = daily_scores
        current_date += timedelta(days=1)

    # 최종 결과 계산
    final_value = daily_values[-1]['total_value'] if daily_values else initial_capital
    total_profit = final_value - initial_capital
    total_return = (total_profit / initial_capital) * 100

    # 거래 통계
    buy_trades = [t for t in trades if t['side'] == 'buy']
    sell_trades = [t for t in trades if t['side'] == 'sell']

    win_trades = [t for t in sell_trades if t.get('profit_rate', 0) > 0]
    lose_trades = [t for t in sell_trades if t.get('profit_rate', 0) <= 0]

    win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

    avg_win = sum(t.get('profit_rate', 0) for t in win_trades) / len(win_trades) if win_trades else 0
    avg_lose = sum(t.get('profit_rate', 0) for t in lose_trades) / len(lose_trades) if lose_trades else 0

    return {
        'stop_loss': stop_loss_pct,
        'initial_capital': initial_capital,
        'final_value': final_value,
        'total_profit': total_profit,
        'total_return': total_return,
        'buy_count': len(buy_trades),
        'sell_count': len(sell_trades),
        'win_count': len(win_trades),
        'lose_count': len(lose_trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_lose': avg_lose,
        'final_holdings': len(holdings),
        'trades': trades,
        'daily_values': daily_values,
    }


def main():
    print("=" * 60)
    print("  1개월 백테스트: 손절 기준별 수익률 비교")
    print("=" * 60)
    print()

    # 백테스트 설정
    days = 30
    initial_capital = 10000000  # 1천만원
    max_holdings = 10
    buy_amount = 1000000  # 종목당 100만원

    print(f"[설정]")
    print(f"  기간: 최근 {days}일")
    print(f"  초기자본: {initial_capital:,}원")
    print(f"  최대보유: {max_holdings}종목")
    print(f"  종목당투자: {buy_amount:,}원")
    print()

    # 3가지 시나리오 백테스트
    scenarios = [
        (-10, "손절 -10%"),
        (-6, "손절 -6%"),
        (None, "손절 없음"),
    ]

    results = []
    for stop_loss, name in scenarios:
        print(f"[{name}] 백테스트 실행 중...")
        result = run_backtest(
            stop_loss_pct=stop_loss,
            days=days,
            initial_capital=initial_capital,
            max_holdings=max_holdings,
            buy_amount=buy_amount,
        )
        result['scenario_name'] = name
        results.append(result)
        print(f"  완료: 수익률 {result['total_return']:+.2f}%")

    # 결과 리포트
    print()
    print("=" * 60)
    print("  백테스트 결과 비교")
    print("=" * 60)
    print()

    print(f"{'시나리오':<12} {'최종자산':>14} {'수익금':>12} {'수익률':>8} {'승률':>8} {'매수':>6} {'매도':>6}")
    print("-" * 70)

    for r in results:
        print(f"{r['scenario_name']:<12} {r['final_value']:>14,}원 {r['total_profit']:>+12,}원 {r['total_return']:>+7.2f}% {r['win_rate']:>7.1f}% {r['buy_count']:>6} {r['sell_count']:>6}")

    print()
    print("=" * 60)
    print("  상세 분석")
    print("=" * 60)

    for r in results:
        print(f"\n[{r['scenario_name']}]")
        print(f"  초기자본: {r['initial_capital']:,}원")
        print(f"  최종자산: {r['final_value']:,}원")
        print(f"  수익금: {r['total_profit']:+,}원 ({r['total_return']:+.2f}%)")
        print(f"  매수: {r['buy_count']}회, 매도: {r['sell_count']}회")
        print(f"  승/패: {r['win_count']}/{r['lose_count']} (승률 {r['win_rate']:.1f}%)")
        if r['avg_win'] != 0 or r['avg_lose'] != 0:
            print(f"  평균수익: +{r['avg_win']:.1f}%, 평균손실: {r['avg_lose']:.1f}%")
        print(f"  현재보유: {r['final_holdings']}종목")

    # 최고 수익 시나리오
    best = max(results, key=lambda x: x['total_return'])
    print()
    print("=" * 60)
    print(f"  최고 수익 시나리오: {best['scenario_name']} ({best['total_return']:+.2f}%)")
    print("=" * 60)

    return results


if __name__ == "__main__":
    main()
