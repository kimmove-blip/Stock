#!/usr/bin/env python3
"""
분석용 데이터 생성 스크립트

1. V1~V8 종목별 일자별 점수
2. 종목별 일자별 주가 데이터
"""

import os
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

# 프로젝트 루트
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from scoring import (
    calculate_score_v1, calculate_score_v2, calculate_score_v3,
    calculate_score_v3_5, calculate_score_v4, calculate_score_v5,
    calculate_score_v6, calculate_score_v7, calculate_score_v8
)


def load_stock_list() -> pd.DataFrame:
    """종목 리스트 로드"""
    print("[1] 종목 리스트 로딩...")
    krx = fdr.StockListing("KRX")
    df = krx[['Code', 'Name', 'Market', 'Marcap']].copy()
    df['Code'] = df['Code'].astype(str).str.zfill(6)

    # 시총 필터 (300억 ~ 1조)
    df = df[df['Marcap'] >= 30_000_000_000]
    df = df[df['Marcap'] <= 1_000_000_000_000]

    # 제외 종목
    exclude_keywords = ['스팩', 'SPAC', '리츠', 'ETF', 'ETN', '인버스', '레버리지']
    for kw in exclude_keywords:
        df = df[~df['Name'].str.contains(kw, case=False, na=False)]

    # 우선주 제외
    df = df[df['Code'].str[-1] == '0']

    print(f"    → {len(df):,}개 종목")
    return df


def load_stock_data(codes: List[str], names: Dict[str, str],
                    start_date: str, end_date: str, max_workers: int = 20) -> Dict[str, pd.DataFrame]:
    """종목 데이터 로드"""
    print("\n[2] 종목 데이터 로딩...")
    cache = {}

    def fetch(code):
        try:
            # 스코어링용 추가 데이터 (120일 전부터)
            extended_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=150)).strftime('%Y-%m-%d')
            df = fdr.DataReader(code, extended_start, end_date)
            if df is not None and len(df) >= 60:
                df = df[df['Volume'] > 0]
                if len(df) >= 60:
                    return (code, df)
        except Exception as e:
            pass
        return None

    from concurrent.futures import TimeoutError as FuturesTimeoutError

    success = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch, code): code for code in codes}
        for i, future in enumerate(as_completed(futures, timeout=300), 1):
            try:
                result = future.result(timeout=10)
                if result:
                    cache[result[0]] = result[1]
                    success += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            if i % 100 == 0:
                print(f"    → {i}/{len(codes)} 처리 ({success} 성공, {failed} 실패)")

    print(f"    → {len(cache):,}개 종목 로드 완료")
    return cache


def get_trading_days(start_date: str, end_date: str) -> List[datetime]:
    """거래일 목록"""
    print("\n[3] 거래일 조회...")
    kospi = fdr.DataReader('KS11', start_date, end_date)
    days = kospi.index.tolist()
    print(f"    → {len(days)}개 거래일")
    return days


def calculate_all_scores(df: pd.DataFrame) -> Dict[str, Optional[int]]:
    """모든 버전 스코어 계산"""
    scores = {
        'v1': None, 'v2': None, 'v3': None, 'v3_5': None,
        'v4': None, 'v5': None, 'v6': None, 'v7': None, 'v8': None
    }

    try:
        r = calculate_score_v1(df)
        if r: scores['v1'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v2(df)
        if r: scores['v2'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v3(df)
        if r: scores['v3'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v3_5(df)
        if r: scores['v3_5'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v4(df)
        if r: scores['v4'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v5(df)
        if r: scores['v5'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v6(df)
        if r: scores['v6'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v7(df)
        if r: scores['v7'] = r.get('score')
    except: pass

    try:
        r = calculate_score_v8(df)
        if r: scores['v8'] = r.get('score')
    except: pass

    return scores


def generate_data(months: int = 3):
    """데이터 생성"""
    # 기간 설정
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=months * 30)

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    print("=" * 70)
    print("  분석용 데이터 생성")
    print("=" * 70)
    print(f"  기간: {start_str} ~ {end_str} ({months}개월)")
    print("=" * 70)

    # 종목 리스트
    stock_df = load_stock_list()
    codes = stock_df['Code'].tolist()
    names = dict(zip(stock_df['Code'], stock_df['Name']))

    # 데이터 로드
    cache = load_stock_data(codes, names, start_str, end_str)

    # 거래일
    trading_days = get_trading_days(start_str, end_str)

    # ========== 1. 주가 데이터 생성 ==========
    print("\n[4] 주가 데이터 생성 중...")
    price_rows = []

    for code, df in cache.items():
        name = names.get(code, code)
        for trade_date in trading_days:
            if trade_date in df.index:
                row = df.loc[trade_date]
                price_rows.append({
                    '일자': trade_date.strftime('%Y-%m-%d'),
                    '종목코드': code,
                    '종목명': name,
                    '시가': int(row['Open']),
                    '고가': int(row['High']),
                    '저가': int(row['Low']),
                    '종가': int(row['Close']),
                    '거래량': int(row['Volume']),
                    '거래대금': int(row.get('Amount', row['Volume'] * row['Close'])),
                    '등락률': round((row['Close'] - row['Open']) / row['Open'] * 100, 2) if row['Open'] > 0 else 0,
                })

    price_df = pd.DataFrame(price_rows)
    print(f"    → {len(price_df):,}행 생성")

    # ========== 2. 스코어 데이터 생성 ==========
    print("\n[5] 스코어 데이터 생성 중...")
    score_rows = []
    total = len(cache) * len(trading_days)
    processed = 0

    for code, df in cache.items():
        name = names.get(code, code)
        for trade_date in trading_days:
            processed += 1
            if processed % 1000 == 0:
                print(f"    → {processed:,}/{total:,} 처리 ({processed/total*100:.1f}%)")

            try:
                df_until = df[df.index <= trade_date]
                if len(df_until) < 60:
                    continue

                if trade_date not in df_until.index:
                    continue

                scores = calculate_all_scores(df_until)
                score_rows.append({
                    '일자': trade_date.strftime('%Y-%m-%d'),
                    '종목코드': code,
                    '종목명': name,
                    'v1': scores['v1'],
                    'v2': scores['v2'],
                    'v3': scores['v3'],
                    'v3.5': scores['v3_5'],
                    'v4': scores['v4'],
                    'v5': scores['v5'],
                    'v6': scores['v6'],
                    'v7': scores['v7'],
                    'v8': scores['v8'],
                })
            except:
                continue

    score_df = pd.DataFrame(score_rows)
    print(f"    → {len(score_df):,}행 생성")

    # ========== 저장 ==========
    print("\n[6] 저장 중...")
    today = datetime.now().strftime('%Y%m%d')
    output_dir = os.path.join(project_root, 'output')

    # 주가 데이터
    price_path = os.path.join(output_dir, f'price_data_{months}m_{today}.xlsx')
    price_df.to_excel(price_path, index=False)
    print(f"    → 주가 데이터: {price_path}")

    # 스코어 데이터
    score_path = os.path.join(output_dir, f'score_data_{months}m_{today}.xlsx')
    score_df.to_excel(score_path, index=False)
    print(f"    → 스코어 데이터: {score_path}")

    print("\n" + "=" * 70)
    print("  완료!")
    print("=" * 70)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=3, help='기간 (개월)')
    args = parser.parse_args()

    generate_data(months=args.months)
