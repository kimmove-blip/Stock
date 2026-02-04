#!/usr/bin/env python3
"""
분봉 데이터 수집기

한투 API `inquire-time-dailychartprice`를 사용하여 과거 분봉 데이터를 수집하고
Parquet 형식으로 저장합니다.

사용법:
    python ml_intraday/collect_minute_bars.py --days 60    # 60일치 수집
    python ml_intraday/collect_minute_bars.py --today      # 오늘 데이터만 수집
    python ml_intraday/collect_minute_bars.py --stock 005930  # 특정 종목만
"""

import os
import sys
import argparse
import time
import functools
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml_intraday.config import DATA_DIR, COLLECT_CONFIG

# 출력 즉시 플러시
print = functools.partial(print, flush=True)


def get_trading_days(days: int) -> List[str]:
    """최근 N 거래일 목록 반환 (YYYYMMDD 형식)"""
    try:
        from pykrx import stock
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        # pykrx에서 거래일 조회
        trading_days = stock.get_previous_business_days(start_date, end_date)
        trading_days = [d.strftime("%Y%m%d") for d in trading_days]

        # 최근 N일만
        return trading_days[-days:] if len(trading_days) > days else trading_days

    except Exception as e:
        print(f"[경고] pykrx 거래일 조회 실패: {e}")
        # 폴백: 주말 제외한 날짜 생성
        result = []
        current = datetime.now()
        while len(result) < days:
            if current.weekday() < 5:  # 월~금
                result.append(current.strftime("%Y%m%d"))
            current -= timedelta(days=1)
        return list(reversed(result))


def get_top_stocks(top_n: int = 500, min_amount: int = 5_000_000_000) -> List[Dict]:
    """
    거래대금 상위 종목 조회

    Returns:
        [{"code": "005930", "name": "삼성전자", "market": "KOSPI"}, ...]
    """
    try:
        from pykrx import stock
        from pykrx.website.krx.market.ticker import StockTicker

        # 어제 날짜 (오늘은 아직 데이터 없을 수 있음)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        # 종목 티커 정보
        ticker_df = StockTicker().listed
        ticker_df = ticker_df[ticker_df['시장'].isin(['STK', 'KSQ'])]

        # KOSPI + KOSDAQ 거래대금 조회
        kospi_amount = stock.get_market_ohlcv(yesterday, market="KOSPI")[['거래대금']]
        kosdaq_amount = stock.get_market_ohlcv(yesterday, market="KOSDAQ")[['거래대금']]

        all_amount = pd.concat([kospi_amount, kosdaq_amount])

        # 최소 거래대금 필터
        filtered = all_amount[all_amount['거래대금'] >= min_amount]

        # 거래대금 기준 정렬
        filtered = filtered.sort_values('거래대금', ascending=False)

        # 상위 N개
        top_codes = filtered.head(top_n).index.tolist()

        # 종목 정보 매핑
        result = []
        for code in top_codes:
            if code in ticker_df.index:
                info = ticker_df.loc[code]
                market = "KOSPI" if info['시장'] == 'STK' else "KOSDAQ"
                result.append({
                    "code": code,
                    "name": info.get('종목명', code),
                    "market": market,
                    "amount": int(filtered.loc[code, '거래대금']),
                })

        return result

    except Exception as e:
        print(f"[에러] 종목 목록 조회 실패: {e}")
        return []


def get_kis_client():
    """한투 API 클라이언트 생성"""
    try:
        from services.kis_client import KISClient

        app_key = os.getenv("KIS_APP_KEY")
        app_secret = os.getenv("KIS_APP_SECRET")

        if not app_key or not app_secret:
            print("[에러] KIS API 키가 설정되지 않았습니다.")
            print("       환경변수 KIS_APP_KEY, KIS_APP_SECRET 설정 필요")
            return None

        return KISClient(is_virtual=False)  # 실전 API로 시세 조회

    except Exception as e:
        print(f"[에러] KIS 클라이언트 초기화 실패: {e}")
        return None


def collect_minute_bars_for_stock(
    kis_client,
    stock_code: str,
    target_date: str,
    start_time: str = "090000"
) -> Optional[pd.DataFrame]:
    """
    특정 종목의 특정 날짜 분봉 데이터 수집

    Args:
        kis_client: KIS API 클라이언트
        stock_code: 종목코드
        target_date: 대상 날짜 (YYYYMMDD)
        start_time: 시작 시간 (HHMMSS)

    Returns:
        분봉 데이터 DataFrame
    """
    try:
        data = kis_client.get_minute_chart_by_date(
            stock_code=stock_code,
            target_date=target_date,
            start_time=start_time
        )

        if not data:
            return None

        df = pd.DataFrame(data)

        # 필수 컬럼 확인
        required_cols = ['date', 'time', 'open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            return None

        # 종목코드 추가
        df['code'] = stock_code

        # 시간 정렬
        df = df.sort_values('time').reset_index(drop=True)

        return df

    except Exception as e:
        # API 속도 제한 등 에러 시 None 반환
        return None


def aggregate_to_5min(df: pd.DataFrame) -> pd.DataFrame:
    """
    1분봉을 5분봉으로 집계

    Args:
        df: 1분봉 데이터 (time 컬럼: HHMMSS 형식)

    Returns:
        5분봉 데이터
    """
    if df is None or df.empty:
        return df

    # 5분 단위 그룹 생성
    def get_5min_group(time_str: str) -> str:
        h = int(time_str[:2])
        m = int(time_str[2:4])
        m_5 = (m // 5) * 5
        return f"{h:02d}{m_5:02d}00"

    df = df.copy()
    df['time_5m'] = df['time'].apply(get_5min_group)

    # 5분 단위로 집계
    agg_dict = {
        'date': 'first',
        'code': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }

    # cum_volume이 있으면 마지막 값 사용
    if 'cum_volume' in df.columns:
        agg_dict['cum_volume'] = 'last'

    df_5m = df.groupby('time_5m').agg(agg_dict).reset_index()
    df_5m = df_5m.rename(columns={'time_5m': 'time'})

    return df_5m


def save_minute_bars(df: pd.DataFrame, date: str):
    """분봉 데이터를 Parquet 파일로 저장"""
    if df is None or df.empty:
        return

    # 날짜별 디렉토리 생성
    date_dir = DATA_DIR / date
    date_dir.mkdir(parents=True, exist_ok=True)

    # 종목별로 저장
    for code, group in df.groupby('code'):
        file_path = date_dir / f"{code}.parquet"
        group.to_parquet(file_path, index=False)


def collect_all_stocks_for_date(
    kis_client,
    stocks: List[Dict],
    target_date: str,
    use_5min: bool = True
) -> pd.DataFrame:
    """
    특정 날짜의 모든 종목 분봉 데이터 수집

    Args:
        kis_client: KIS API 클라이언트
        stocks: 종목 리스트
        target_date: 대상 날짜
        use_5min: 5분봉으로 집계 여부

    Returns:
        전체 종목 분봉 데이터
    """
    all_data = []
    success_count = 0
    fail_count = 0

    api_sleep = COLLECT_CONFIG["api_sleep"]

    for i, stock in enumerate(stocks):
        code = stock["code"]

        # API 호출
        df = collect_minute_bars_for_stock(kis_client, code, target_date)

        if df is not None and not df.empty:
            # 5분봉 집계
            if use_5min:
                df = aggregate_to_5min(df)

            all_data.append(df)
            success_count += 1
        else:
            fail_count += 1

        # 진행 상황 출력 (50개마다)
        if (i + 1) % 50 == 0:
            print(f"    {i+1}/{len(stocks)} 완료 (성공: {success_count}, 실패: {fail_count})")

        # API 속도 제한
        time.sleep(api_sleep)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


def collect_historical_data(days: int = 60, top_n: int = 500):
    """
    과거 N일치 분봉 데이터 수집

    Args:
        days: 수집할 거래일 수
        top_n: 상위 종목 수
    """
    print("=" * 60)
    print("  분봉 데이터 수집기")
    print("=" * 60)

    # KIS 클라이언트 초기화
    print("\n[1] 한투 API 초기화...")
    kis_client = get_kis_client()
    if not kis_client:
        return

    # 종목 목록 조회
    print(f"\n[2] 거래대금 상위 {top_n}개 종목 조회...")
    min_amount = COLLECT_CONFIG["min_trading_amount"]
    stocks = get_top_stocks(top_n, min_amount)
    print(f"    {len(stocks)}개 종목 선정")

    if not stocks:
        print("[에러] 종목 조회 실패")
        return

    # 거래일 목록
    print(f"\n[3] 최근 {days} 거래일 조회...")
    trading_days = get_trading_days(days)
    print(f"    {len(trading_days)}일: {trading_days[0]} ~ {trading_days[-1]}")

    # 이미 수집된 날짜 확인
    existing_dates = set()
    for date_dir in DATA_DIR.iterdir():
        if date_dir.is_dir() and len(list(date_dir.glob("*.parquet"))) > 0:
            existing_dates.add(date_dir.name)

    # 수집이 필요한 날짜만 필터
    dates_to_collect = [d for d in trading_days if d not in existing_dates]
    print(f"    이미 수집됨: {len(existing_dates)}일")
    print(f"    수집 필요: {len(dates_to_collect)}일")

    if not dates_to_collect:
        print("\n모든 데이터가 이미 수집되어 있습니다.")
        return

    # 날짜별 수집
    print(f"\n[4] 분봉 데이터 수집 시작...")
    total_start = time.time()

    for i, date in enumerate(dates_to_collect):
        print(f"\n  [{i+1}/{len(dates_to_collect)}] {date} 수집 중...")
        start_time = time.time()

        df = collect_all_stocks_for_date(kis_client, stocks, date, use_5min=True)

        if not df.empty:
            save_minute_bars(df, date)
            elapsed = time.time() - start_time
            print(f"    저장 완료: {len(df)}행, {elapsed:.1f}초")
        else:
            print(f"    [경고] 데이터 없음")

    total_elapsed = time.time() - total_start
    print(f"\n[완료] 총 소요시간: {total_elapsed/60:.1f}분")


def collect_today():
    """오늘 데이터만 수집 (크론용)"""
    print("=" * 60)
    print("  오늘 분봉 데이터 수집")
    print("=" * 60)

    today = datetime.now().strftime("%Y%m%d")

    # 장 시간 확인
    now = datetime.now()
    if now.hour < 16:  # 16시 이전이면 경고
        print(f"[경고] 현재 시각: {now.strftime('%H:%M')} - 장 종료 후 실행을 권장합니다.")

    # KIS 클라이언트 초기화
    kis_client = get_kis_client()
    if not kis_client:
        return

    # 종목 목록
    stocks = get_top_stocks(
        COLLECT_CONFIG["top_stocks"],
        COLLECT_CONFIG["min_trading_amount"]
    )
    print(f"\n{len(stocks)}개 종목 분봉 수집...")

    # 수집
    df = collect_all_stocks_for_date(kis_client, stocks, today, use_5min=True)

    if not df.empty:
        save_minute_bars(df, today)
        print(f"\n[완료] {today} 저장: {len(df)}행")
    else:
        print(f"\n[경고] {today} 데이터 없음")


def collect_single_stock(stock_code: str, days: int = 60):
    """특정 종목의 분봉 데이터 수집"""
    print(f"종목 {stock_code} 분봉 데이터 수집...")

    kis_client = get_kis_client()
    if not kis_client:
        return

    trading_days = get_trading_days(days)

    all_data = []
    for date in trading_days:
        df = collect_minute_bars_for_stock(kis_client, stock_code, date)
        if df is not None and not df.empty:
            df = aggregate_to_5min(df)
            all_data.append(df)
            print(f"  {date}: {len(df)}행")
        time.sleep(COLLECT_CONFIG["api_sleep"])

    if all_data:
        result = pd.concat(all_data, ignore_index=True)
        print(f"\n총 {len(result)}행 수집 완료")
        return result

    return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="분봉 데이터 수집기")
    parser.add_argument("--days", type=int, default=60, help="수집할 거래일 수")
    parser.add_argument("--top", type=int, default=500, help="거래대금 상위 종목 수")
    parser.add_argument("--today", action="store_true", help="오늘 데이터만 수집")
    parser.add_argument("--stock", type=str, help="특정 종목만 수집 (종목코드)")

    args = parser.parse_args()

    if args.stock:
        collect_single_stock(args.stock, args.days)
    elif args.today:
        collect_today()
    else:
        collect_historical_data(args.days, args.top)


if __name__ == "__main__":
    main()
