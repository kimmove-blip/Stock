#!/usr/bin/env python3
"""
target_stocks.xlsx 파일에 V1-V4 점수 채우기
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from scoring import SCORING_FUNCTIONS

INPUT_FILE = '/home/kimhc/Stock/output/target_stocks.xlsx'
OUTPUT_FILE = '/home/kimhc/Stock/output/target_stocks_filled.xlsx'


def get_ohlcv(code: str, target_date: str) -> pd.DataFrame:
    """OHLCV 조회"""
    try:
        code_str = str(code).zfill(6)
        target = datetime.strptime(target_date, '%Y-%m-%d')
        start = (target - timedelta(days=150)).strftime('%Y-%m-%d')
        return fdr.DataReader(code_str, start, target_date)
    except:
        return None


def calculate_scores(df: pd.DataFrame) -> dict:
    """V1-V4 점수 계산"""
    results = {}
    for version, func in SCORING_FUNCTIONS.items():
        try:
            result = func(df)
            results[version] = result['score'] if result else None
        except:
            results[version] = None
    return results


def process_stock_date(args):
    """단일 종목-날짜 처리"""
    code, date_str = args
    try:
        df = get_ohlcv(code, date_str)
        if df is None or len(df) < 60:
            return code, date_str, {}
        scores = calculate_scores(df)
        return code, date_str, scores
    except:
        return code, date_str, {}


def main():
    print(f"\n{'='*60}")
    print(f"  target_stocks.xlsx V1-V4 점수 채우기")
    print(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # 원본 파일 로드
    xlsx = pd.ExcelFile(INPUT_FILE)
    sheets = {}
    for version in ['V1', 'V2', 'V3', 'V4']:
        sheets[version] = pd.read_excel(xlsx, sheet_name=version)

    # 종목 코드와 날짜 목록 추출
    df_v1 = sheets['V1']
    codes = df_v1['code'].tolist()
    date_cols = [c for c in df_v1.columns if c not in ['code', 'name']]

    print(f"종목 수: {len(codes)}")
    print(f"날짜 수: {len(date_cols)}")
    print(f"총 계산: {len(codes) * len(date_cols):,}개\n")

    # 모든 (종목, 날짜) 조합 생성
    tasks = [(code, date) for code in codes for date in date_cols]

    # 결과 저장용 딕셔너리 {(code, date): {v1: score, v2: score, ...}}
    results = {}

    # 병렬 처리
    start_time = time.time()
    completed = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_stock_date, task): task for task in tasks}

        for future in as_completed(futures):
            code, date_str, scores = future.result()
            results[(code, date_str)] = scores
            completed += 1

            if completed % 500 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                print(f"  진행: {completed:,}/{len(tasks):,} ({completed/len(tasks)*100:.1f}%) | "
                      f"속도: {rate:.1f}/초 | 남은시간: {remaining/60:.1f}분")

    print(f"\n점수 계산 완료: {time.time() - start_time:.1f}초")

    # 결과를 시트에 채우기
    print("\n시트 업데이트 중...")
    for version in ['V1', 'V2', 'V3', 'V4']:
        version_lower = version.lower()
        df = sheets[version]

        for idx, row in df.iterrows():
            code = row['code']
            for date_col in date_cols:
                scores = results.get((code, date_col), {})
                score = scores.get(version_lower)
                if score is not None:
                    df.at[idx, date_col] = score

    # 저장
    print(f"\n저장 중: {OUTPUT_FILE}")
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        for version in ['V1', 'V2', 'V3', 'V4']:
            sheets[version].to_excel(writer, sheet_name=version, index=False)

    print(f"\n{'='*60}")
    print(f"  완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  저장: {OUTPUT_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
