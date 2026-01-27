#!/usr/bin/env python3
"""
V10 Leader-Follower 캐치업 기회 분석기

학습된 레퍼런스를 기반으로 대장주 움직임을 감지하고
캐치업 기회가 있는 종속주를 찾습니다.

사용법:
    python predict_leader_follower.py              # 기본 분석 (대장주 +3% 이상)
    python predict_leader_follower.py --min 2      # 대장주 +2% 이상일 때 분석
    python predict_leader_follower.py --top 10     # 상위 10개만 출력
    python predict_leader_follower.py --info       # 레퍼런스 정보 출력
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
    get_reference_info,
    get_all_leaders,
    get_all_followers,
    load_reference,
)


def get_today_changes(tickers: list) -> dict:
    """금일 등락률 조회"""
    today = datetime.now().strftime('%Y%m%d')

    # 장 시작 전이면 전일 데이터 사용
    now = datetime.now()
    if now.hour < 9:
        today = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

    changes = {}

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 시세 조회 중... ({len(tickers)}개 종목)")

    for i, ticker in enumerate(tickers):
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

        if (i + 1) % 100 == 0:
            print(f"    → {i + 1}/{len(tickers)} 완료")

    return changes


def print_reference_info():
    """레퍼런스 정보 출력"""
    info = get_reference_info()

    print("=" * 70)
    print("V10 Leader-Follower 레퍼런스 정보")
    print("=" * 70)

    if not info.get('loaded'):
        print(f"오류: {info.get('error')}")
        print("\n레퍼런스 생성 방법:")
        print("  python train_leader_follower.py")
        return

    print(f"버전: {info['version']}")
    print(f"생성 시간: {info['created_at']}")
    print(f"최소 상관계수: {info['min_correlation']}")
    print(f"총 대장주: {info['total_leaders']}개")
    print(f"총 종속주: {info['total_followers']}개")
    print(f"총 쌍: {info['total_pairs']}개")


def main():
    parser = argparse.ArgumentParser(description='V10 대장주-종속주 캐치업 기회 분석')
    parser.add_argument('--min', type=float, default=3.0, help='대장주 최소 상승률 (기본: 3.0)')
    parser.add_argument('--max', type=float, default=2.0, help='종속주 최대 상승률 (기본: 2.0)')
    parser.add_argument('--top', type=int, default=20, help='출력할 종목 수 (기본: 20)')
    parser.add_argument('--info', action='store_true', help='레퍼런스 정보만 출력')
    args = parser.parse_args()

    # 레퍼런스 정보 출력
    if args.info:
        print_reference_info()
        return

    # 레퍼런스 확인
    ref = load_reference()
    if ref is None:
        print("=" * 70)
        print("V10 레퍼런스 파일이 없습니다!")
        print("=" * 70)
        print("\n먼저 레퍼런스를 생성하세요:")
        print("  python train_leader_follower.py")
        print("\n옵션:")
        print("  --months 6    # 분석 기간 (기본 6개월)")
        print("  --top 500     # 분석 종목 수 (기본 500개)")
        print("  --min-corr 0.5  # 최소 상관계수 (기본 0.5)")
        return

    print("=" * 70)
    print("V10 Leader-Follower 캐치업 기회 분석")
    print("=" * 70)
    print(f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"조건: 대장주 +{args.min}% 이상, 종속주 +{args.max}% 이하")
    print(f"레퍼런스: {ref['total_leaders']}개 대장주, {ref['total_followers']}개 종속주")
    print()

    # 모든 관련 종목 시세 조회
    all_leaders = get_all_leaders()
    all_followers = get_all_followers()
    all_tickers = list(set(all_leaders + all_followers))

    today_changes = get_today_changes(all_tickers)

    # 대장주 움직임 확인
    print("\n[대장주 움직임]")
    active_leaders = []
    for leader in all_leaders:
        change = today_changes.get(leader, 0)
        if change >= args.min:
            # 대장주 이름 찾기
            name = leader
            for pair in ref.get('all_pairs', []):
                if pair['leader_code'] == leader:
                    name = pair['leader_name']
                    break
            active_leaders.append((leader, name, change))
            print(f"  ★ {name}({leader}) +{change:.1f}%")

    if not active_leaders:
        print(f"  대장주 중 +{args.min}% 이상 상승한 종목이 없습니다.")

    # 캐치업 기회 분석
    print("\n[캐치업 기회 종목]")
    opportunities = get_follower_opportunities(
        today_changes,
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
        print(f"\n  {i}. {opp['follower_name']} ({opp['follower_code']})")
        print(f"     대장주: {opp['leader_name']} +{opp['leader_change']:.1f}%")
        print(f"     종속주: +{opp['follower_change']:.1f}%")
        print(f"     캐치업 갭: +{opp['catchup_gap']:.1f}% (예상 상승 여력)")
        print(f"     상관계수: {opp['correlation']:.2f}")
        print(f"     V10 점수: {opp['score']}점")

    # 요약
    print("\n" + "=" * 70)
    print(f"총 {len(opportunities)}개 캐치업 기회 발견 (상위 {min(args.top, len(opportunities))}개 표시)")

    # 대장주별 집계
    leader_counts = {}
    for opp in opportunities:
        leader = opp['leader_name']
        leader_counts[leader] = leader_counts.get(leader, 0) + 1

    print("\n[대장주별 기회 수]")
    for leader, count in sorted(leader_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  - {leader}: {count}개")


if __name__ == "__main__":
    main()
