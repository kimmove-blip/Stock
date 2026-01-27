#!/usr/bin/env python3
"""
V10 Leader-Follower 캐치업 기회 분석기

실시간으로 대장주 움직임을 감지하고 캐치업 기회가 있는 종속주를 찾습니다.

사용법:
    python predict_leader_follower.py              # 기본 분석 (대장주 +3% 이상)
    python predict_leader_follower.py --min 2      # 대장주 +2% 이상일 때 분석
    python predict_leader_follower.py --top 10     # 상위 10개만 출력
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# 프로젝트 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from pykrx import stock as pykrx

from scoring.score_v10_leader_follower import (
    get_follower_opportunities,
    THEME_STOCK_MAP,
    calculate_score_v10,
    _find_stock_theme,
)


def get_today_changes(tickers: list) -> dict:
    """금일 등락률 조회"""
    today = datetime.now().strftime('%Y%m%d')

    # 장 시작 전이면 전일 데이터 사용
    now = datetime.now()
    if now.hour < 9:
        today = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

    changes = {}

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 시세 조회 중...")

    for ticker in tickers:
        try:
            df = pykrx.get_market_ohlcv_by_date(
                fromdate=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                todate=today,
                ticker=ticker
            )
            if len(df) >= 2:
                # 금일 등락률
                close = df['종가'].iloc[-1]
                prev_close = df['종가'].iloc[-2]
                change_pct = (close - prev_close) / prev_close * 100
                changes[ticker] = round(change_pct, 2)
            else:
                changes[ticker] = 0.0
        except Exception as e:
            changes[ticker] = 0.0

    return changes


def get_ohlcv_data(tickers: list, days: int = 60) -> dict:
    """OHLCV 데이터 조회 (상관계수 계산용)"""
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days + 30)).strftime('%Y%m%d')

    market_data = {}

    for ticker in tickers:
        try:
            df = pykrx.get_market_ohlcv_by_date(
                fromdate=start_date,
                todate=end_date,
                ticker=ticker
            )
            if len(df) >= 30:
                df = df.rename(columns={
                    '시가': 'Open',
                    '고가': 'High',
                    '저가': 'Low',
                    '종가': 'Close',
                    '거래량': 'Volume'
                })
                market_data[ticker] = df
        except Exception:
            pass

    return market_data


def get_all_theme_tickers() -> list:
    """테마 매핑에 있는 모든 종목코드"""
    tickers = set()

    for theme_data in THEME_STOCK_MAP.values():
        for leader in theme_data['leaders']:
            tickers.add(leader['code'])
        for follower in theme_data['followers']:
            tickers.add(follower['code'])

    return list(tickers)


def main():
    parser = argparse.ArgumentParser(description='V10 대장주-종속주 캐치업 기회 분석')
    parser.add_argument('--min', type=float, default=3.0, help='대장주 최소 상승률 (기본: 3.0)')
    parser.add_argument('--max', type=float, default=2.0, help='종속주 최대 상승률 (기본: 2.0)')
    parser.add_argument('--top', type=int, default=20, help='출력할 종목 수 (기본: 20)')
    parser.add_argument('--corr', action='store_true', help='상관계수 실제 계산 (느림)')
    args = parser.parse_args()

    print("=" * 70)
    print("V10 Leader-Follower 캐치업 기회 분석")
    print("=" * 70)
    print(f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"조건: 대장주 +{args.min}% 이상, 종속주 +{args.max}% 이하")
    print()

    # 모든 테마 종목 시세 조회
    all_tickers = get_all_theme_tickers()
    today_changes = get_today_changes(all_tickers)

    # 상관계수 계산용 데이터 (선택)
    market_data = None
    if args.corr:
        print("[상관계수 계산을 위한 OHLCV 조회 중...]")
        market_data = get_ohlcv_data(all_tickers)

    # 대장주 움직임 확인
    print("\n[대장주 움직임]")
    for theme_name, theme_data in THEME_STOCK_MAP.items():
        for leader in theme_data['leaders']:
            change = today_changes.get(leader['code'], 0)
            if change >= args.min:
                print(f"  ★ {theme_name}: {leader['name']}({leader['code']}) +{change:.1f}%")

    # 캐치업 기회 분석
    print("\n[캐치업 기회 종목]")
    opportunities = get_follower_opportunities(
        today_changes,
        market_data=market_data,
        min_leader_change=args.min,
        max_follower_change=args.max
    )

    if not opportunities:
        print("  캐치업 기회가 있는 종목이 없습니다.")
        print(f"  (대장주 중 +{args.min}% 이상 상승한 종목이 없거나,")
        print(f"   종속주가 이미 +{args.max}% 이상 따라갔습니다)")
        return

    # 상위 N개 출력
    for i, opp in enumerate(opportunities[:args.top], 1):
        print(f"\n  {i}. {opp['follower_name']} ({opp['follower_code']}) [{opp['theme']}]")
        print(f"     대장주: {opp['leader_name']} +{opp['leader_change']:.1f}%")
        print(f"     종속주: +{opp['follower_change']:.1f}%")
        print(f"     캐치업 갭: +{opp['catchup_gap']:.1f}% (예상 상승 여력)")
        print(f"     상관계수: {opp['correlation']:.2f}")
        print(f"     V10 점수: {opp['score']}점")

    # 요약
    print("\n" + "=" * 70)
    print(f"총 {len(opportunities)}개 캐치업 기회 발견 (상위 {min(args.top, len(opportunities))}개 표시)")

    # 테마별 집계
    theme_counts = {}
    for opp in opportunities:
        theme = opp['theme']
        theme_counts[theme] = theme_counts.get(theme, 0) + 1

    print("\n[테마별 기회 수]")
    for theme, count in sorted(theme_counts.items(), key=lambda x: -x[1]):
        print(f"  - {theme}: {count}개")


if __name__ == "__main__":
    main()
