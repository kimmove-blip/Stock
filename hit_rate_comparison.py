#!/usr/bin/env python3
"""
V1-V4 스코어링 버전별 적중률 비교 분석

각 스코어링 버전별로 상위 20종목을 선정하고,
20 거래일간의 적중률을 분석합니다.

사용법:
    python hit_rate_comparison.py              # 기본 실행 (20일, 상위 20종목)
    python hit_rate_comparison.py --days 10    # 10일간 분석
    python hit_rate_comparison.py --top 30     # 상위 30종목
"""

import os
import sys
import argparse
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import time

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

from scoring import (
    calculate_score_v1,
    calculate_score_v2,
    calculate_score_v3,
    calculate_score_v4,
    SCORING_FUNCTIONS,
)
from config import OUTPUT_DIR

warnings.filterwarnings("ignore")

# 설정
MIN_MARKET_CAP = 30_000_000_000  # 최소 시총 300억
MAX_MARKET_CAP = 1_000_000_000_000  # 최대 시총 1조
MIN_TRADING_AMOUNT = 300_000_000  # 최소 거래대금 3억
MAX_WORKERS = 5  # 병렬 처리 워커 수


def get_trading_days(num_days: int = 20) -> list:
    """
    과거 num_days 거래일 목록 조회

    Returns:
        list: 거래일 문자열 리스트 ['2026-01-20', '2026-01-17', ...]
    """
    try:
        # KOSPI 지수로 거래일 조회
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=num_days * 2 + 30)).strftime('%Y-%m-%d')

        df = fdr.DataReader('KS11', start_date, end_date)
        if df is None or df.empty:
            print("[오류] 거래일 조회 실패")
            return []

        # 오늘은 제외하고 과거 num_days일 선택 (결과를 확인하려면 다음날 데이터가 필요)
        trading_days = df.index.strftime('%Y-%m-%d').tolist()

        # 오늘과 어제 제외 (다음날 수익률 계산 위해)
        if len(trading_days) >= 2:
            trading_days = trading_days[:-2]

        return trading_days[-num_days:]
    except Exception as e:
        print(f"[오류] 거래일 조회 실패: {e}")
        return []


def get_stock_list_for_date(date_str: str) -> pd.DataFrame:
    """
    특정 날짜 기준 스크리닝 대상 종목 목록 조회
    """
    try:
        krx = fdr.StockListing("KRX")

        columns_needed = ["Code", "Name", "Market", "Marcap", "Volume", "Amount", "Close"]
        available_cols = [c for c in columns_needed if c in krx.columns]
        df = krx[available_cols].copy()

        # 종목코드 6자리 맞추기
        df["Code"] = df["Code"].astype(str).str.zfill(6)

        # 시가총액 필터
        if "Marcap" in df.columns:
            df = df[(df["Marcap"] >= MIN_MARKET_CAP) & (df["Marcap"] <= MAX_MARKET_CAP)]

        # 거래대금 필터
        if "Amount" in df.columns:
            df = df[df["Amount"] >= MIN_TRADING_AMOUNT]

        # 특수종목 제외
        exclude_keywords = [
            "스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지",
            "합병", "정리매매", "관리종목", "투자주의", "투자경고", "투자위험"
        ]
        for keyword in exclude_keywords:
            df = df[~df["Name"].str.contains(keyword, case=False, na=False)]

        # 우선주 제외
        df = df[df["Code"].str[-1] == "0"]

        return df
    except Exception as e:
        print(f"[오류] 종목 목록 조회 실패: {e}")
        return pd.DataFrame()


def get_ohlcv_for_date(code: str, target_date: str, days: int = 90) -> pd.DataFrame:
    """
    특정 날짜 기준 OHLCV 데이터 조회

    Args:
        code: 종목코드
        target_date: 분석 기준일 (YYYY-MM-DD)
        days: 조회할 과거 일수

    Returns:
        target_date까지의 OHLCV 데이터프레임
    """
    try:
        target = datetime.strptime(target_date, '%Y-%m-%d')
        start_date = (target - timedelta(days=days + 60)).strftime('%Y-%m-%d')

        df = fdr.DataReader(code, start_date, target_date)
        if df is None or df.empty:
            return None

        return df
    except Exception as e:
        return None


def get_next_day_return(code: str, target_date: str) -> tuple:
    """
    다음 거래일 수익률 계산

    Returns:
        (다음날 수익률 %, 다음날 종가)
    """
    try:
        target = datetime.strptime(target_date, '%Y-%m-%d')
        start_date = target_date
        end_date = (target + timedelta(days=7)).strftime('%Y-%m-%d')

        df = fdr.DataReader(code, start_date, end_date)
        if df is None or len(df) < 2:
            return None, None

        # target_date 종가와 다음날 종가
        base_price = df.iloc[0]['Close']
        next_price = df.iloc[1]['Close']

        return_pct = (next_price - base_price) / base_price * 100
        return return_pct, next_price
    except Exception as e:
        return None, None


def calculate_all_versions_score(df: pd.DataFrame) -> dict:
    """
    모든 버전의 점수 계산

    Returns:
        {
            'v1': {'score': 65, 'signals': [...]},
            'v2': {'score': 72, 'signals': [...]},
            ...
        }
    """
    results = {}

    for version, func in SCORING_FUNCTIONS.items():
        try:
            result = func(df)
            if result:
                results[version] = {
                    'score': result['score'],
                    'signals': result.get('signals', []),
                }
            else:
                results[version] = {'score': 0, 'signals': []}
        except Exception as e:
            results[version] = {'score': 0, 'signals': []}

    return results


def analyze_single_stock(stock_info: dict, target_date: str) -> dict:
    """
    단일 종목 분석 (병렬 처리용)
    """
    code = stock_info['Code']
    name = stock_info['Name']

    try:
        # OHLCV 조회
        df = get_ohlcv_for_date(code, target_date, days=90)
        if df is None or len(df) < 60:
            return None

        # 모든 버전 점수 계산
        scores = calculate_all_versions_score(df)

        # 다음날 수익률
        next_return, next_close = get_next_day_return(code, target_date)

        return {
            'code': code,
            'name': name,
            'market': stock_info.get('Market', ''),
            'close': float(df.iloc[-1]['Close']),
            'scores': scores,
            'next_return': next_return,
            'next_close': next_close,
        }
    except Exception as e:
        return None


def analyze_date(date_str: str, top_n: int = 20) -> dict:
    """
    특정 날짜의 버전별 상위 종목 분석

    Returns:
        {
            'date': '2026-01-20',
            'v1': [{'code': '005930', 'name': '삼성전자', 'score': 85, 'next_return': 2.3}, ...],
            'v2': [...],
            'v3': [...],
            'v4': [...]
        }
    """
    print(f"\n[{date_str}] 분석 시작...")

    # 종목 목록 조회
    stocks = get_stock_list_for_date(date_str)
    if stocks.empty:
        print(f"  → 종목 없음")
        return None

    stock_list = stocks.to_dict('records')
    print(f"  → {len(stock_list)}개 종목 분석 중...")

    # 병렬 분석
    all_results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(analyze_single_stock, stock, date_str): stock
            for stock in stock_list
        }

        for future in as_completed(futures):
            result = future.result()
            if result is not None and result['next_return'] is not None:
                all_results.append(result)

    elapsed = time.time() - start_time
    print(f"  → {len(all_results)}개 종목 완료 ({elapsed:.1f}초)")

    # 버전별 상위 N개 선정
    version_results = {'date': date_str}

    for version in SCORING_FUNCTIONS.keys():
        # 점수 기준 정렬
        sorted_results = sorted(
            all_results,
            key=lambda x: x['scores'].get(version, {}).get('score', 0),
            reverse=True
        )[:top_n]

        version_results[version] = [
            {
                'code': r['code'],
                'name': r['name'],
                'market': r['market'],
                'close': r['close'],
                'score': r['scores'].get(version, {}).get('score', 0),
                'signals': r['scores'].get(version, {}).get('signals', []),
                'next_return': r['next_return'],
            }
            for r in sorted_results
        ]

        # 간단한 통계 출력
        returns = [r['next_return'] for r in sorted_results if r['next_return'] is not None]
        if returns:
            avg_return = sum(returns) / len(returns)
            up_count = sum(1 for r in returns if r > 0)
            print(f"  → {version.upper()}: 평균 {avg_return:+.2f}%, 상승 {up_count}/{len(returns)}개")

    return version_results


def calculate_statistics(results: list) -> dict:
    """
    버전별 통계 계산

    Returns:
        {
            'v1': {'avg_return': 1.23, 'up_ratio': 52.5, 'max_up': 15.3, 'max_down': -8.2, 'total_count': 400},
            ...
        }
    """
    stats = {}

    for version in SCORING_FUNCTIONS.keys():
        all_returns = []

        for day_result in results:
            if day_result is None:
                continue
            for stock in day_result.get(version, []):
                if stock['next_return'] is not None:
                    all_returns.append(stock['next_return'])

        if all_returns:
            up_count = sum(1 for r in all_returns if r > 0)
            stats[version] = {
                'avg_return': sum(all_returns) / len(all_returns),
                'up_ratio': up_count / len(all_returns) * 100,
                'max_up': max(all_returns),
                'max_down': min(all_returns),
                'total_count': len(all_returns),
                'median_return': sorted(all_returns)[len(all_returns) // 2],
            }
        else:
            stats[version] = {
                'avg_return': 0,
                'up_ratio': 0,
                'max_up': 0,
                'max_down': 0,
                'total_count': 0,
                'median_return': 0,
            }

    return stats


def save_to_excel(results: list, stats: dict, output_path: str):
    """
    결과를 Excel 파일로 저장

    시트 구성:
    - 요약: 버전별 통계 비교표
    - V1_상세, V2_상세, V3_상세, V4_상세: 각 버전 상위20 일별 상세
    """
    print(f"\n[저장] Excel 파일 생성 중: {output_path}")

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # 1. 요약 시트
        summary_data = []
        for version, s in stats.items():
            summary_data.append({
                '버전': version.upper(),
                '평균수익률(%)': round(s['avg_return'], 2),
                '중앙값(%)': round(s['median_return'], 2),
                '상승비율(%)': round(s['up_ratio'], 1),
                '최고상승(%)': round(s['max_up'], 1),
                '최고하락(%)': round(s['max_down'], 1),
                '총 선정수': s['total_count'],
            })

        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='요약', index=False)

        # 2. 버전별 상세 시트
        for version in SCORING_FUNCTIONS.keys():
            detail_data = []

            for day_result in results:
                if day_result is None:
                    continue

                date_str = day_result['date']

                for i, stock in enumerate(day_result.get(version, []), 1):
                    detail_data.append({
                        '날짜': date_str,
                        '순위': i,
                        '종목코드': stock['code'],
                        '종목명': stock['name'],
                        '시장': stock['market'],
                        '점수': stock['score'],
                        '종가': int(stock['close']),
                        '다음날수익률(%)': round(stock['next_return'], 2) if stock['next_return'] else '',
                        '신호': ', '.join(stock['signals'][:5]),
                    })

            detail_df = pd.DataFrame(detail_data)
            detail_df.to_excel(writer, sheet_name=f'{version.upper()}_상세', index=False)

    print(f"  → 저장 완료!")


def print_final_summary(stats: dict):
    """최종 결과 요약 출력"""
    print("\n" + "=" * 70)
    print("  V1-V4 스코어링 버전별 적중률 비교 결과")
    print("=" * 70)

    # 평균 수익률 기준 정렬
    sorted_versions = sorted(stats.items(), key=lambda x: x[1]['avg_return'], reverse=True)

    print(f"\n{'버전':^6} {'평균수익률':>10} {'중앙값':>8} {'상승비율':>10} {'최고상승':>10} {'최고하락':>10} {'선정수':>8}")
    print("-" * 70)

    for version, s in sorted_versions:
        print(f"{version.upper():^6} {s['avg_return']:>9.2f}% {s['median_return']:>7.2f}% "
              f"{s['up_ratio']:>9.1f}% {s['max_up']:>9.1f}% {s['max_down']:>9.1f}% {s['total_count']:>7}")

    # 최고 버전 출력
    best_version = sorted_versions[0][0]
    best_stats = sorted_versions[0][1]
    print("\n" + "-" * 70)
    print(f"★ 최고 성과 버전: {best_version.upper()}")
    print(f"   평균 수익률: {best_stats['avg_return']:.2f}%, 상승 비율: {best_stats['up_ratio']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='V1-V4 스코어링 버전별 적중률 비교')
    parser.add_argument('--days', type=int, default=20, help='분석할 거래일 수 (기본: 20)')
    parser.add_argument('--top', type=int, default=20, help='버전별 상위 종목 수 (기본: 20)')
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(f"  V1-V4 스코어링 버전별 적중률 비교 분석")
    print(f"  분석 기간: {args.days} 거래일, 버전별 상위 {args.top}종목")
    print(f"  실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. 거래일 목록 조회
    print("\n[1/4] 거래일 목록 조회 중...")
    trading_days = get_trading_days(args.days)
    if not trading_days:
        print("[오류] 거래일 조회 실패")
        return

    print(f"  → {len(trading_days)}일 분석 예정: {trading_days[0]} ~ {trading_days[-1]}")

    # 2. 날짜별 분석
    print(f"\n[2/4] 날짜별 분석 시작...")
    all_results = []

    for i, date_str in enumerate(trading_days, 1):
        print(f"\n--- [{i}/{len(trading_days)}] ---")
        result = analyze_date(date_str, top_n=args.top)
        all_results.append(result)

        # API 부하 방지
        if i < len(trading_days):
            time.sleep(1)

    # 3. 통계 계산
    print(f"\n[3/4] 통계 계산 중...")
    stats = calculate_statistics(all_results)

    # 4. 결과 저장
    print(f"\n[4/4] 결과 저장 중...")
    output_filename = f"hit_rate_v1_v4_comparison_{datetime.now().strftime('%Y%m%d')}.xlsx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    save_to_excel(all_results, stats, output_path)

    # 최종 요약
    print_final_summary(stats)

    print(f"\n결과 파일: {output_path}")


if __name__ == "__main__":
    main()
