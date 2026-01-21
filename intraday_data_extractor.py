#!/usr/bin/env python3
"""
V1-V4 상위 종목 장중 데이터 추출기

각 스코어링 버전의 상위 20종목에 대해 장중 데이터를 추출합니다.

추출 데이터:
- 전일 거래대금
- 당일 시초가
- 당일 09:05 주가/누적거래량
- 당일 09:20 주가/누적거래량
- 고가, 저가, 종가, 거래량, 거래대금

사용법:
    python intraday_data_extractor.py              # 기본 실행 (20일)
    python intraday_data_extractor.py --days 10    # 10일간
"""

import os
import sys
import argparse
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

from scoring import SCORING_FUNCTIONS
from config import OUTPUT_DIR
from trading.trade_logger import TradeLogger

warnings.filterwarnings("ignore")

# 설정
MIN_MARKET_CAP = 30_000_000_000
MAX_MARKET_CAP = 1_000_000_000_000
MIN_TRADING_AMOUNT = 300_000_000
MAX_WORKERS = 5


def get_kis_client():
    """KIS 클라이언트 초기화 (실전투자용)"""
    try:
        # 사용자 2번 (실전투자)의 API 키 사용
        logger = TradeLogger()
        api_key_data = logger.get_api_key_settings(2)

        if not api_key_data or not api_key_data.get('app_key'):
            print("[오류] API 키 설정을 찾을 수 없습니다.")
            return None

        from api.services.kis_client import KISClient
        client = KISClient(
            app_key=api_key_data['app_key'],
            app_secret=api_key_data['app_secret'],
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_virtual=False  # 실전투자
        )
        return client
    except Exception as e:
        print(f"[오류] KIS 클라이언트 초기화 실패: {e}")
        return None


def get_trading_days(num_days: int = 20) -> list:
    """과거 거래일 목록 조회"""
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=num_days * 2 + 30)).strftime('%Y-%m-%d')

        df = fdr.DataReader('KS11', start_date, end_date)
        if df is None or df.empty:
            return []

        trading_days = df.index.strftime('%Y-%m-%d').tolist()

        # 오늘과 어제 제외
        if len(trading_days) >= 2:
            trading_days = trading_days[:-2]

        return trading_days[-num_days:]
    except Exception as e:
        print(f"[오류] 거래일 조회 실패: {e}")
        return []


def get_stock_list() -> pd.DataFrame:
    """스크리닝 대상 종목 목록"""
    try:
        krx = fdr.StockListing("KRX")
        columns_needed = ["Code", "Name", "Market", "Marcap", "Amount"]
        available_cols = [c for c in columns_needed if c in krx.columns]
        df = krx[available_cols].copy()
        df["Code"] = df["Code"].astype(str).str.zfill(6)

        if "Marcap" in df.columns:
            df = df[(df["Marcap"] >= MIN_MARKET_CAP) & (df["Marcap"] <= MAX_MARKET_CAP)]
        if "Amount" in df.columns:
            df = df[df["Amount"] >= MIN_TRADING_AMOUNT]

        # 특수종목/우선주 제외
        exclude_keywords = ["스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지"]
        for kw in exclude_keywords:
            df = df[~df["Name"].str.contains(kw, case=False, na=False)]
        df = df[df["Code"].str[-1] == "0"]

        return df
    except Exception as e:
        print(f"[오류] 종목 목록 조회 실패: {e}")
        return pd.DataFrame()


def get_ohlcv_for_date(code: str, target_date: str, days: int = 90) -> pd.DataFrame:
    """특정 날짜 기준 OHLCV 조회"""
    try:
        target = datetime.strptime(target_date, '%Y-%m-%d')
        start_date = (target - timedelta(days=days + 60)).strftime('%Y-%m-%d')
        df = fdr.DataReader(code, start_date, target_date)
        return df if df is not None and not df.empty else None
    except:
        return None


def calculate_all_versions_score(df: pd.DataFrame) -> dict:
    """모든 버전 점수 계산"""
    results = {}
    for version, func in SCORING_FUNCTIONS.items():
        try:
            result = func(df)
            results[version] = result['score'] if result else 0
        except:
            results[version] = 0
    return results


def get_daily_data(code: str, target_date: str) -> dict:
    """
    특정 날짜의 일봉 데이터 조회

    Returns:
        {
            'prev_trading_value': 전일 거래대금,
            'open': 시가,
            'high': 고가,
            'low': 저가,
            'close': 종가,
            'volume': 거래량,
            'trading_value': 거래대금,
        }
    """
    try:
        target = datetime.strptime(target_date, '%Y-%m-%d')
        start_date = (target - timedelta(days=10)).strftime('%Y-%m-%d')
        end_date = target_date

        df = fdr.DataReader(code, start_date, end_date)
        if df is None or len(df) < 2:
            return None

        # 당일 데이터
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        return {
            'prev_trading_value': int(prev['Close'] * prev['Volume']),
            'open': int(curr['Open']),
            'high': int(curr['High']),
            'low': int(curr['Low']),
            'close': int(curr['Close']),
            'volume': int(curr['Volume']),
            'trading_value': int(curr['Close'] * curr['Volume']),
        }
    except Exception as e:
        return None


def get_intraday_data(kis_client, code: str, target_date: str) -> dict:
    """
    특정 날짜의 분봉 데이터에서 09:05, 09:20 시점 추출

    Returns:
        {
            'price_0905': 09:05 주가,
            'price_0920': 09:20 주가,
            'cum_vol_0905': 09:05 누적거래량,
            'cum_vol_0920': 09:20 누적거래량,
        }
    """
    result = {
        'price_0905': None,
        'price_0920': None,
        'cum_vol_0905': None,
        'cum_vol_0920': None,
    }

    if kis_client is None:
        return result

    try:
        # YYYYMMDD 형식으로 변환
        date_yyyymmdd = target_date.replace('-', '')

        # 분봉 데이터 조회
        minute_data = kis_client.get_minute_chart_by_date(code, date_yyyymmdd)

        if not minute_data:
            # 당일 분봉 조회 시도
            minute_data = kis_client.get_minute_chart(code)

        if not minute_data:
            return result

        # 09:05, 09:20 시점 찾기
        for item in minute_data:
            time_str = item.get('time', '')

            # 09:05 근처 (090500 ~ 090559)
            if time_str.startswith('0905'):
                result['price_0905'] = item.get('close')
                result['cum_vol_0905'] = item.get('cum_volume')

            # 09:20 근처 (092000 ~ 092059)
            if time_str.startswith('0920'):
                result['price_0920'] = item.get('close')
                result['cum_vol_0920'] = item.get('cum_volume')

        return result

    except Exception as e:
        return result


def analyze_single_stock(stock_info: dict, target_date: str, kis_client) -> dict:
    """단일 종목 분석"""
    code = stock_info['Code']
    name = stock_info['Name']

    try:
        # OHLCV 조회 (점수 계산용)
        df = get_ohlcv_for_date(code, target_date)
        if df is None or len(df) < 60:
            return None

        # 버전별 점수 계산
        scores = calculate_all_versions_score(df)

        # 일봉 데이터
        daily = get_daily_data(code, target_date)
        if daily is None:
            return None

        # 분봉 데이터 (09:05, 09:20)
        intraday = get_intraday_data(kis_client, code, target_date)

        return {
            'code': code,
            'name': name,
            'scores': scores,
            'prev_trading_value': daily['prev_trading_value'],
            'open': daily['open'],
            'high': daily['high'],
            'low': daily['low'],
            'close': daily['close'],
            'volume': daily['volume'],
            'trading_value': daily['trading_value'],
            'price_0905': intraday['price_0905'],
            'price_0920': intraday['price_0920'],
            'cum_vol_0905': intraday['cum_vol_0905'],
            'cum_vol_0920': intraday['cum_vol_0920'],
        }
    except Exception as e:
        return None


def analyze_date(date_str: str, kis_client, top_n: int = 20) -> dict:
    """특정 날짜 분석"""
    print(f"\n[{date_str}] 분석 시작...")

    stocks = get_stock_list()
    if stocks.empty:
        return None

    stock_list = stocks.to_dict('records')
    print(f"  → {len(stock_list)}개 종목 분석 중...")

    # 병렬 분석
    all_results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(analyze_single_stock, stock, date_str, kis_client): stock
            for stock in stock_list
        }

        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                all_results.append(result)

    elapsed = time.time() - start_time
    print(f"  → {len(all_results)}개 종목 완료 ({elapsed:.1f}초)")

    # 버전별 상위 N개 선정
    version_results = {'date': date_str}

    for version in SCORING_FUNCTIONS.keys():
        sorted_results = sorted(
            all_results,
            key=lambda x: x['scores'].get(version, 0),
            reverse=True
        )[:top_n]

        version_results[version] = [
            {
                'code': r['code'],
                'name': r['name'],
                'score': r['scores'].get(version, 0),
                'prev_trading_value': r['prev_trading_value'],
                'open': r['open'],
                'price_0905': r['price_0905'],
                'price_0920': r['price_0920'],
                'cum_vol_0905': r['cum_vol_0905'],
                'cum_vol_0920': r['cum_vol_0920'],
                'high': r['high'],
                'low': r['low'],
                'close': r['close'],
                'volume': r['volume'],
                'trading_value': r['trading_value'],
            }
            for r in sorted_results
        ]

    return version_results


def save_to_excel(results: list, output_path: str):
    """Excel 저장"""
    print(f"\n[저장] {output_path}")

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for version in SCORING_FUNCTIONS.keys():
            data = []

            for day_result in results:
                if day_result is None:
                    continue

                date_str = day_result['date']

                for i, stock in enumerate(day_result.get(version, []), 1):
                    data.append({
                        '날짜': date_str,
                        '순위': i,
                        '종목코드': stock['code'],
                        '종목명': stock['name'],
                        '점수': stock['score'],
                        '전일거래대금(억)': round(stock['prev_trading_value'] / 1e8, 1) if stock['prev_trading_value'] else '',
                        '시가': stock['open'],
                        '09:05주가': stock['price_0905'] if stock['price_0905'] else '',
                        '09:20주가': stock['price_0920'] if stock['price_0920'] else '',
                        '09:05누적거래량': stock['cum_vol_0905'] if stock['cum_vol_0905'] else '',
                        '09:20누적거래량': stock['cum_vol_0920'] if stock['cum_vol_0920'] else '',
                        '고가': stock['high'],
                        '저가': stock['low'],
                        '종가': stock['close'],
                        '거래량': stock['volume'],
                        '거래대금(억)': round(stock['trading_value'] / 1e8, 1),
                    })

            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=f'{version.upper()}_상세', index=False)

    print("  → 저장 완료!")


def main():
    parser = argparse.ArgumentParser(description='V1-V4 상위 종목 장중 데이터 추출')
    parser.add_argument('--days', type=int, default=20, help='분석할 거래일 수')
    parser.add_argument('--top', type=int, default=20, help='버전별 상위 종목 수')
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(f"  V1-V4 상위 종목 장중 데이터 추출")
    print(f"  분석 기간: {args.days} 거래일, 버전별 상위 {args.top}종목")
    print(f"  실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # KIS 클라이언트 초기화
    print("\n[1/4] KIS 클라이언트 초기화...")
    kis_client = get_kis_client()
    if kis_client:
        print("  → 초기화 성공 (분봉 데이터 조회 가능)")
    else:
        print("  → 초기화 실패 (분봉 데이터 없이 진행)")

    # 거래일 목록
    print("\n[2/4] 거래일 목록 조회...")
    trading_days = get_trading_days(args.days)
    if not trading_days:
        print("[오류] 거래일 조회 실패")
        return

    print(f"  → {len(trading_days)}일: {trading_days[0]} ~ {trading_days[-1]}")

    # 날짜별 분석
    print(f"\n[3/4] 날짜별 분석...")
    all_results = []

    for i, date_str in enumerate(trading_days, 1):
        print(f"\n--- [{i}/{len(trading_days)}] ---")
        result = analyze_date(date_str, kis_client, top_n=args.top)
        all_results.append(result)

        if i < len(trading_days):
            time.sleep(1)

    # 저장
    print(f"\n[4/4] 결과 저장...")
    output_filename = f"intraday_data_v1_v4_{datetime.now().strftime('%Y%m%d')}.xlsx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    save_to_excel(all_results, output_path)

    print(f"\n결과 파일: {output_path}")


if __name__ == "__main__":
    main()
