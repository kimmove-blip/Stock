#!/usr/bin/env python3
"""
V1-V4 상위 30종목 일봉+분봉 데이터 추출기

추출 데이터:
- 전일점수, 전일종가, 전일상승률, 전일거래대금
- 시초가, 09:05 주가, 09:20 주가
- 09:05 거래량, 09:20 거래량
- 당일점수, 종가
"""

import os
import sys
import argparse
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import pandas as pd
import FinanceDataReader as fdr

from scoring import SCORING_FUNCTIONS
from config import OUTPUT_DIR

warnings.filterwarnings("ignore")

# 설정
MIN_MARKET_CAP = 30_000_000_000
MAX_MARKET_CAP = 1_000_000_000_000
MIN_TRADING_AMOUNT = 300_000_000
MAX_WORKERS = 5


def get_kis_client():
    """KIS 클라이언트 초기화"""
    try:
        from trading.trade_logger import TradeLogger
        from api.services.kis_client import KISClient

        logger = TradeLogger()
        api_key_data = logger.get_api_key_settings(2)

        if not api_key_data:
            return None

        return KISClient(
            app_key=api_key_data['app_key'],
            app_secret=api_key_data['app_secret'],
            is_virtual=False
        )
    except Exception as e:
        print(f"  KIS 클라이언트 초기화 실패: {e}")
        return None


def get_trading_days(num_days: int = 20) -> list:
    """과거 거래일 목록 (쌍으로 사용하므로 +1개 필요)"""
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=num_days * 2 + 30)).strftime('%Y-%m-%d')
        df = fdr.DataReader('KS11', start_date, end_date)
        if df is None or df.empty:
            return []
        trading_days = df.index.strftime('%Y-%m-%d').tolist()
        if len(trading_days) >= 2:
            trading_days = trading_days[:-2]
        # num_days + 1개 반환 (전일-당일 쌍을 만들기 위해)
        return trading_days[-(num_days + 1):]
    except Exception as e:
        print(f"[오류] 거래일 조회 실패: {e}")
        return []


def get_stock_list() -> pd.DataFrame:
    """스크리닝 대상 종목 목록"""
    try:
        krx = fdr.StockListing("KRX")
        df = krx[["Code", "Name", "Market", "Marcap", "Amount"]].copy()
        df["Code"] = df["Code"].astype(str).str.zfill(6)
        df = df[(df["Marcap"] >= MIN_MARKET_CAP) & (df["Marcap"] <= MAX_MARKET_CAP)]
        df = df[df["Amount"] >= MIN_TRADING_AMOUNT]

        exclude_keywords = ["스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지"]
        for kw in exclude_keywords:
            df = df[~df["Name"].str.contains(kw, case=False, na=False)]
        df = df[df["Code"].str[-1] == "0"]
        return df
    except:
        return pd.DataFrame()


def get_ohlcv(code: str, target_date: str) -> pd.DataFrame:
    """OHLCV 조회"""
    try:
        target = datetime.strptime(target_date, '%Y-%m-%d')
        start = (target - timedelta(days=150)).strftime('%Y-%m-%d')
        return fdr.DataReader(code, start, target_date)
    except:
        return None


def calculate_scores(df: pd.DataFrame) -> dict:
    """V1-V4 점수 계산"""
    results = {}
    for version, func in SCORING_FUNCTIONS.items():
        try:
            result = func(df)
            results[version] = result['score'] if result else 0
        except:
            results[version] = 0
    return results


def get_prev_day_data(code: str, prev_date: str) -> dict:
    """전일 데이터 (종가, 상승률, 거래대금)"""
    try:
        target = datetime.strptime(prev_date, '%Y-%m-%d')
        start = (target - timedelta(days=10)).strftime('%Y-%m-%d')
        df = fdr.DataReader(code, start, prev_date)
        if df is None or len(df) < 2:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        prev_close = int(curr['Close'])
        prev_return = ((curr['Close'] - prev['Close']) / prev['Close'] * 100) if prev['Close'] > 0 else 0
        prev_trading_value = int(curr['Close'] * curr['Volume'])

        return {
            'prev_close': prev_close,
            'prev_return': round(prev_return, 2),
            'prev_trading_value': prev_trading_value,
        }
    except:
        return None


def get_curr_day_data(code: str, curr_date: str) -> dict:
    """당일 데이터 (시가, 종가)"""
    try:
        target = datetime.strptime(curr_date, '%Y-%m-%d')
        start = (target - timedelta(days=5)).strftime('%Y-%m-%d')
        df = fdr.DataReader(code, start, curr_date)
        if df is None or df.empty:
            return None

        curr = df.iloc[-1]
        return {
            'open': int(curr['Open']),
            'close': int(curr['Close']),
        }
    except:
        return None


def get_minute_data(kis_client, code: str, target_date: str) -> dict:
    """분봉 데이터에서 09:05, 09:20 추출"""
    result = {
        'price_0905': None, 'price_0920': None,
        'vol_0905': None, 'vol_0920': None,
    }

    if kis_client is None:
        return result

    try:
        date_yyyymmdd = target_date.replace('-', '')
        minute_data = kis_client.get_minute_chart_by_date(code, date_yyyymmdd, '093000')

        if not minute_data:
            return result

        # 누적 거래량 계산
        cum_vol = 0
        for item in minute_data:
            cum_vol += item.get('volume', 0)
            time_str = item.get('time', '')

            if time_str >= '090500' and time_str <= '090559':
                result['price_0905'] = item.get('close')
                result['vol_0905'] = cum_vol
            if time_str >= '092000' and time_str <= '092059':
                result['price_0920'] = item.get('close')
                result['vol_0920'] = cum_vol

        return result
    except:
        return result


def analyze_stock_prev_day(stock_info: dict, prev_date: str) -> dict:
    """전일 기준 분석 (점수 계산)"""
    code = stock_info['Code']
    name = stock_info['Name']

    try:
        df = get_ohlcv(code, prev_date)
        if df is None or len(df) < 60:
            return None

        scores = calculate_scores(df)
        prev_data = get_prev_day_data(code, prev_date)

        if prev_data is None:
            return None

        return {
            'code': code, 'name': name,
            'prev_scores': scores,
            **prev_data
        }
    except:
        return None


def analyze_date_pair(prev_date: str, curr_date: str, kis_client, top_n: int = 30) -> dict:
    """전일-당일 쌍 분석"""
    print(f"\n[{prev_date} → {curr_date}] 분석...")

    stocks = get_stock_list()
    if stocks.empty:
        return None

    stock_list = stocks.to_dict('records')
    print(f"  1단계: {len(stock_list)}개 종목 전일점수 계산...")

    # 1단계: 전일 기준 점수 계산 (병렬)
    all_results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_stock_prev_day, s, prev_date): s for s in stock_list}
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_results.append(result)

    print(f"     → {len(all_results)}개 완료 ({time.time() - start_time:.1f}초)")

    # 2단계: 버전별 상위 N개 선정
    version_results = {'prev_date': prev_date, 'curr_date': curr_date}
    selected_codes = set()

    for version in SCORING_FUNCTIONS.keys():
        sorted_results = sorted(all_results, key=lambda x: x['prev_scores'].get(version, 0), reverse=True)[:top_n]
        for r in sorted_results:
            selected_codes.add(r['code'])
        version_results[f'{version}_stocks'] = sorted_results

    print(f"  2단계: 상위 {len(selected_codes)}개 종목 당일데이터 조회...")

    # 3단계: 당일 점수 및 분봉 조회 (중복 제거된 종목만)
    curr_score_cache = {}
    curr_data_cache = {}
    minute_cache = {}

    for i, code in enumerate(selected_codes):
        # 당일 점수 계산
        df = get_ohlcv(code, curr_date)
        if df is not None and len(df) >= 60:
            curr_score_cache[code] = calculate_scores(df)
        else:
            curr_score_cache[code] = {}

        # 당일 시가/종가
        curr_data_cache[code] = get_curr_day_data(code, curr_date)

        # 분봉 조회
        minute_cache[code] = get_minute_data(kis_client, code, curr_date)

        if (i + 1) % 20 == 0:
            print(f"     → {i + 1}/{len(selected_codes)}")
        time.sleep(0.15)  # API 속도 제한

    # 최종 결과 조합
    for version in SCORING_FUNCTIONS.keys():
        final_list = []
        for rank, r in enumerate(version_results[f'{version}_stocks'], 1):
            code = r['code']
            minute = minute_cache.get(code, {})
            curr_data = curr_data_cache.get(code) or {}
            curr_scores = curr_score_cache.get(code, {})

            final_list.append({
                'rank': rank,
                'code': code,
                'name': r['name'],
                'prev_score': r['prev_scores'].get(version, 0),
                'prev_close': r['prev_close'],
                'prev_return': r['prev_return'],
                'prev_trading_value': r['prev_trading_value'],
                'open': curr_data.get('open'),
                'price_0905': minute.get('price_0905'),
                'price_0920': minute.get('price_0920'),
                'vol_0905': minute.get('vol_0905'),
                'vol_0920': minute.get('vol_0920'),
                'curr_score': curr_scores.get(version, 0),
                'close': curr_data.get('close'),
            })
        version_results[version] = final_list
        del version_results[f'{version}_stocks']

    return version_results


def save_to_excel(results: list, output_path: str):
    """Excel 저장"""
    print(f"\n[저장] {output_path}")

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for version in SCORING_FUNCTIONS.keys():
            data = []
            for day_result in results:
                if not day_result:
                    continue
                prev_date = day_result['prev_date']
                curr_date = day_result['curr_date']

                for stock in day_result.get(version, []):
                    data.append({
                        '전일': prev_date,
                        '당일': curr_date,
                        '순위': stock['rank'],
                        '종목코드': stock['code'],
                        '종목명': stock['name'],
                        '전일점수': stock['prev_score'],
                        '전일종가': stock['prev_close'],
                        '전일상승률(%)': stock['prev_return'],
                        '전일거래대금(억)': round(stock['prev_trading_value'] / 1e8, 1),
                        '시가': stock['open'] or '',
                        '09:05주가': stock['price_0905'] or '',
                        '09:20주가': stock['price_0920'] or '',
                        '09:05거래량': stock['vol_0905'] or '',
                        '09:20거래량': stock['vol_0920'] or '',
                        '당일점수': stock['curr_score'],
                        '종가': stock['close'] or '',
                    })
            pd.DataFrame(data).to_excel(writer, sheet_name=f'{version.upper()}_상세', index=False)

    print("  → 저장 완료!")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=20)
    parser.add_argument('--top', type=int, default=30)
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print(f"  V1-V4 상위 {args.top}종목 데이터 추출")
    print(f"  기간: {args.days}일, 실행: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    kis_client = get_kis_client()
    print(f"\n[KIS] {'연결 성공' if kis_client else '연결 실패 (분봉 없이 진행)'}")

    trading_days = get_trading_days(args.days)
    if len(trading_days) < 2:
        print("[오류] 거래일 부족")
        return

    # 쌍 생성: (day0, day1), (day1, day2), ...
    day_pairs = [(trading_days[i], trading_days[i+1]) for i in range(len(trading_days) - 1)]
    print(f"[거래일] {len(day_pairs)}쌍: {day_pairs[0][0]} ~ {day_pairs[-1][1]}")

    all_results = []
    for i, (prev_date, curr_date) in enumerate(day_pairs, 1):
        print(f"\n=== [{i}/{len(day_pairs)}] ===")
        result = analyze_date_pair(prev_date, curr_date, kis_client, args.top)
        all_results.append(result)
        if i < len(day_pairs):
            time.sleep(1)

    output_file = f"daily_data_v1_v4_{datetime.now().strftime('%Y%m%d')}.xlsx"
    save_to_excel(all_results, os.path.join(OUTPUT_DIR, output_file))
    print(f"\n완료: output/{output_file}")


if __name__ == "__main__":
    main()
