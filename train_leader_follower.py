#!/usr/bin/env python3
"""
V10 Leader-Follower 상관관계 학습기

시가총액 상위 종목들의 실제 가격 데이터를 분석하여
상관관계가 높은 대장주-종속주 쌍을 자동으로 찾아 저장합니다.

사용법:
    python train_leader_follower.py              # 기본 학습 (6개월, 상위 500종목)
    python train_leader_follower.py --months 12  # 12개월 데이터
    python train_leader_follower.py --top 300    # 상위 300종목만
    python train_leader_follower.py --min-corr 0.6  # 상관계수 0.6 이상만
"""

import os
import sys
import json
import pickle
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import numpy as np
from pykrx import stock as pykrx
import FinanceDataReader as fdr

# 프로젝트 경로
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# 업종 코드 매핑 (KRX 업종)
SECTOR_MAP = {
    "반도체": ["반도체", "전자부품", "IT부품"],
    "2차전지": ["2차전지", "배터리", "에너지저장"],
    "바이오": ["바이오", "제약", "헬스케어", "의료"],
    "금융": ["은행", "증권", "보험", "금융"],
    "자동차": ["자동차", "자동차부품"],
    "조선": ["조선", "해운"],
    "건설": ["건설", "건설자재"],
    "화학": ["화학", "정유"],
    "철강": ["철강", "비철금속"],
    "유통": ["유통", "소매"],
    "식품": ["식품", "음료"],
    "통신": ["통신", "미디어"],
    "전력": ["전력", "가스", "에너지"],
}


def get_market_cap_ranking(date: str = None, top_n: int = 500) -> pd.DataFrame:
    """시가총액 상위 종목 조회 (FinanceDataReader 사용)"""
    print(f"[1/5] 시가총액 상위 {top_n}개 종목 조회 중...")

    try:
        # FinanceDataReader로 KRX 전체 종목 가져오기
        krx = fdr.StockListing("KRX")

        # 시가총액 컬럼 확인
        if 'Marcap' not in krx.columns:
            print("    → Marcap 컬럼이 없습니다.")
            return pd.DataFrame()

        # 시가총액 기준 정렬
        krx = krx.sort_values('Marcap', ascending=False)

        # 상위 N개 선택
        top_stocks = krx.head(top_n).copy()

        # 컬럼 정리
        top_stocks['ticker'] = top_stocks['Code'].astype(str).str.zfill(6)
        top_stocks['name'] = top_stocks['Name']
        top_stocks['시가총액'] = top_stocks['Marcap']

        print(f"    → {len(top_stocks)}개 종목 조회 완료")
        return top_stocks

    except Exception as e:
        print(f"    → 종목 조회 실패: {e}")
        return pd.DataFrame()


def get_price_data(tickers: list, months: int = 6) -> dict:
    """가격 데이터 조회"""
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=months * 30 + 30)).strftime('%Y%m%d')

    print(f"[2/5] {len(tickers)}개 종목 가격 데이터 조회 중 ({months}개월)...")

    price_data = {}
    failed = 0

    for i, ticker in enumerate(tickers):
        try:
            df = pykrx.get_market_ohlcv_by_date(start_date, end_date, ticker)
            if len(df) >= 60:  # 최소 60거래일
                df = df.rename(columns={
                    '시가': 'Open', '고가': 'High', '저가': 'Low',
                    '종가': 'Close', '거래량': 'Volume'
                })
                # 일별 수익률 계산
                df['returns'] = df['Close'].pct_change()
                price_data[ticker] = df
        except Exception as e:
            failed += 1

        if (i + 1) % 50 == 0:
            print(f"    → {i + 1}/{len(tickers)} 완료 (유효: {len(price_data)})")

    print(f"    → 총 {len(price_data)}개 종목 데이터 수집 완료 (실패: {failed})")
    return price_data


def calculate_all_correlations(price_data: dict, min_corr: float = 0.4) -> pd.DataFrame:
    """모든 종목 쌍의 상관계수 계산"""
    tickers = list(price_data.keys())
    n = len(tickers)

    print(f"[3/5] {n}개 종목 간 상관계수 계산 중 ({n*(n-1)//2} 쌍)...")

    # 수익률 데이터프레임 생성
    returns_dict = {}
    for ticker in tickers:
        returns_dict[ticker] = price_data[ticker]['returns'].dropna()

    returns_df = pd.DataFrame(returns_dict)

    # 상관계수 행렬 계산
    corr_matrix = returns_df.corr()

    # 상관계수 쌍 추출
    pairs = []
    for i, ticker1 in enumerate(tickers):
        for j, ticker2 in enumerate(tickers):
            if i >= j:  # 중복 제거
                continue

            corr = corr_matrix.loc[ticker1, ticker2]
            if pd.notna(corr) and corr >= min_corr:
                pairs.append({
                    'ticker1': ticker1,
                    'ticker2': ticker2,
                    'correlation': round(corr, 4)
                })

    pairs_df = pd.DataFrame(pairs)
    pairs_df = pairs_df.sort_values('correlation', ascending=False)

    print(f"    → 상관계수 {min_corr} 이상: {len(pairs_df)}쌍 발견")
    return pairs_df


def classify_leader_follower(pairs_df: pd.DataFrame, market_caps: pd.DataFrame) -> pd.DataFrame:
    """시가총액 기준으로 대장주/종속주 분류"""
    print(f"[4/5] 대장주-종속주 분류 중...")

    cap_dict = market_caps.set_index('ticker')['시가총액'].to_dict()
    name_dict = market_caps.set_index('ticker')['name'].to_dict()

    results = []
    for _, row in pairs_df.iterrows():
        t1, t2, corr = row['ticker1'], row['ticker2'], row['correlation']

        cap1 = cap_dict.get(t1, 0)
        cap2 = cap_dict.get(t2, 0)

        # 시가총액이 큰 쪽이 대장주
        if cap1 >= cap2:
            leader, follower = t1, t2
            leader_cap, follower_cap = cap1, cap2
        else:
            leader, follower = t2, t1
            leader_cap, follower_cap = cap2, cap1

        # 시가총액 비율 (대장주 대비 종속주)
        cap_ratio = follower_cap / leader_cap if leader_cap > 0 else 0

        results.append({
            'leader_code': leader,
            'leader_name': name_dict.get(leader, leader),
            'leader_cap': leader_cap,
            'follower_code': follower,
            'follower_name': name_dict.get(follower, follower),
            'follower_cap': follower_cap,
            'correlation': corr,
            'cap_ratio': round(cap_ratio, 4)
        })

    results_df = pd.DataFrame(results)
    print(f"    → {len(results_df)}개 대장주-종속주 쌍 분류 완료")
    return results_df


def build_reference(classified_df: pd.DataFrame, min_corr: float = 0.5) -> dict:
    """최종 레퍼런스 생성"""
    print(f"[5/5] 레퍼런스 생성 중 (상관계수 {min_corr} 이상)...")

    # 상관계수 필터링
    filtered = classified_df[classified_df['correlation'] >= min_corr].copy()

    # 대장주별로 종속주 그룹핑
    leader_map = defaultdict(list)

    for _, row in filtered.iterrows():
        leader_map[row['leader_code']].append({
            'code': row['follower_code'],
            'name': row['follower_name'],
            'correlation': row['correlation'],
            'cap_ratio': row['cap_ratio']
        })

    # 대장주별 종속주 정렬 (상관계수 높은 순)
    for leader in leader_map:
        leader_map[leader] = sorted(
            leader_map[leader],
            key=lambda x: x['correlation'],
            reverse=True
        )[:10]  # 대장주당 최대 10개 종속주

    # 종속주 → 대장주 역매핑
    follower_to_leader = {}
    for leader, followers in leader_map.items():
        leader_name = filtered[filtered['leader_code'] == leader]['leader_name'].iloc[0] \
            if len(filtered[filtered['leader_code'] == leader]) > 0 else leader

        for f in followers:
            if f['code'] not in follower_to_leader:
                follower_to_leader[f['code']] = []
            follower_to_leader[f['code']].append({
                'leader_code': leader,
                'leader_name': leader_name,
                'correlation': f['correlation']
            })

    # 메타데이터
    reference = {
        'version': '1.0',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'min_correlation': min_corr,
        'total_leaders': len(leader_map),
        'total_followers': len(follower_to_leader),
        'total_pairs': len(filtered),
        'leader_to_followers': dict(leader_map),
        'follower_to_leaders': follower_to_leader,
        'all_pairs': filtered.to_dict('records')
    }

    print(f"    → 대장주 {len(leader_map)}개, 종속주 {len(follower_to_leader)}개")
    return reference


def save_reference(reference: dict, output_dir: str = None):
    """레퍼런스 저장"""
    if output_dir is None:
        output_dir = MODELS_DIR

    # Pickle 저장
    pkl_path = os.path.join(output_dir, 'v10_leader_follower_reference.pkl')
    with open(pkl_path, 'wb') as f:
        pickle.dump(reference, f)

    # JSON 저장 (읽기용)
    json_path = os.path.join(output_dir, 'v10_leader_follower_reference.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(reference, f, ensure_ascii=False, indent=2)

    print(f"\n[저장 완료]")
    print(f"  - Pickle: {pkl_path}")
    print(f"  - JSON: {json_path}")

    return pkl_path, json_path


def print_summary(reference: dict):
    """요약 출력"""
    print("\n" + "=" * 70)
    print("V10 Leader-Follower 레퍼런스 요약")
    print("=" * 70)
    print(f"생성 시간: {reference['created_at']}")
    print(f"최소 상관계수: {reference['min_correlation']}")
    print(f"총 대장주: {reference['total_leaders']}개")
    print(f"총 종속주: {reference['total_followers']}개")
    print(f"총 쌍: {reference['total_pairs']}개")

    # 상위 대장주 (종속주 많은 순)
    print("\n[상위 대장주 (종속주 수 기준)]")
    leader_counts = [
        (k, len(v), reference['all_pairs'][0]['leader_name']
         if any(p['leader_code'] == k for p in reference['all_pairs']) else k)
        for k, v in reference['leader_to_followers'].items()
    ]
    leader_counts.sort(key=lambda x: x[1], reverse=True)

    for code, count, _ in leader_counts[:15]:
        # 이름 찾기
        name = code
        for pair in reference['all_pairs']:
            if pair['leader_code'] == code:
                name = pair['leader_name']
                break
        print(f"  {name} ({code}): 종속주 {count}개")

    # 상관계수 분포
    print("\n[상관계수 분포]")
    correlations = [p['correlation'] for p in reference['all_pairs']]
    print(f"  평균: {np.mean(correlations):.3f}")
    print(f"  최대: {np.max(correlations):.3f}")
    print(f"  최소: {np.min(correlations):.3f}")
    print(f"  0.7 이상: {sum(1 for c in correlations if c >= 0.7)}쌍")
    print(f"  0.6~0.7: {sum(1 for c in correlations if 0.6 <= c < 0.7)}쌍")
    print(f"  0.5~0.6: {sum(1 for c in correlations if 0.5 <= c < 0.6)}쌍")


def main():
    parser = argparse.ArgumentParser(description='V10 Leader-Follower 상관관계 학습')
    parser.add_argument('--months', type=int, default=6, help='분석 기간 (개월, 기본: 6)')
    parser.add_argument('--top', type=int, default=500, help='분석 대상 종목 수 (기본: 500)')
    parser.add_argument('--min-corr', type=float, default=0.5, help='최소 상관계수 (기본: 0.5)')
    parser.add_argument('--calc-corr', type=float, default=0.4, help='계산 시 최소 상관계수 (기본: 0.4)')
    args = parser.parse_args()

    print("=" * 70)
    print("V10 Leader-Follower 상관관계 학습 시작")
    print("=" * 70)
    print(f"분석 기간: {args.months}개월")
    print(f"대상 종목: 시가총액 상위 {args.top}개")
    print(f"최소 상관계수: {args.min_corr}")
    print()

    # 1. 시가총액 상위 종목 조회
    market_caps = get_market_cap_ranking(top_n=args.top)
    tickers = market_caps['ticker'].tolist()

    # 2. 가격 데이터 수집
    price_data = get_price_data(tickers, months=args.months)

    # 3. 상관계수 계산
    pairs_df = calculate_all_correlations(price_data, min_corr=args.calc_corr)

    # 4. 대장주-종속주 분류
    classified_df = classify_leader_follower(pairs_df, market_caps)

    # 5. 레퍼런스 생성
    reference = build_reference(classified_df, min_corr=args.min_corr)

    # 6. 저장
    save_reference(reference)

    # 7. 요약 출력
    print_summary(reference)

    print("\n" + "=" * 70)
    print("학습 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
