#!/usr/bin/env python3
"""
현재가 캐시 업데이트 스크립트 (네이버 금융 버전)
- 장중 5분마다 실행하여 DB에 현재가 캐시 저장
- 네이버 금융 polling API 사용 (빠르고 안정적)
"""

import sys
import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import DatabaseManager

NAVER_API_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def get_target_stock_codes():
    """업데이트 대상 종목코드 수집 (중복 제거)"""
    stock_codes = set()

    # 1. TOP100 종목
    output_dir = Path(__file__).parent / "output"
    today = datetime.now().strftime("%Y%m%d")
    top100_file = output_dir / f"top100_{today}.json"

    if not top100_file.exists():
        # 최근 파일 찾기
        import re
        pattern = re.compile(r'^top100_\d{8}\.json$')
        json_files = sorted(
            [f for f in output_dir.glob("top100_*.json") if pattern.match(f.name)],
            reverse=True
        )
        if json_files:
            top100_file = json_files[0]

    if top100_file.exists():
        try:
            with open(top100_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data = data.get('stocks', [])
                for item in data:
                    if 'code' in item:
                        stock_codes.add(item['code'])
        except Exception as e:
            print(f"TOP100 파일 읽기 실패: {e}")

    # 2. 사용자 포트폴리오 및 관심종목
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT DISTINCT stock_code FROM portfolios")
        for row in cursor.fetchall():
            stock_codes.add(row['stock_code'])

        cursor = conn.execute("SELECT DISTINCT stock_code FROM watchlists")
        for row in cursor.fetchall():
            stock_codes.add(row['stock_code'])

    return list(stock_codes)


def fetch_prices_from_naver(stock_codes: list, batch_size: int = 100) -> list:
    """네이버 금융에서 현재가 조회 (batch 처리)"""
    all_prices = []

    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        url = f"{NAVER_API_URL}/{','.join(batch)}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.ok:
                data = resp.json()
                items = data.get('datas', [])

                for item in items:
                    try:
                        # 가격 문자열에서 콤마 제거
                        def parse_price(val):
                            if val is None:
                                return None
                            if isinstance(val, (int, float)):
                                return int(val)
                            return int(str(val).replace(',', '').replace('원', '').strip() or 0)

                        def parse_float(val):
                            if val is None:
                                return None
                            if isinstance(val, (int, float)):
                                return float(val)
                            return float(str(val).replace(',', '').replace('%', '').strip() or 0)

                        def parse_volume(val):
                            if val is None:
                                return None
                            if isinstance(val, (int, float)):
                                return int(val)
                            s = str(val).replace(',', '').strip()
                            return int(s) if s else 0

                        def parse_trading_value(val):
                            """거래대금 파싱 (백만 단위)"""
                            if val is None:
                                return None
                            s = str(val).replace(',', '').replace('백만', '').strip()
                            try:
                                return int(float(s) * 1_000_000) if s else 0
                            except:
                                return 0

                        current_price = parse_price(item.get('closePrice'))
                        prev_close = current_price - parse_price(item.get('compareToPreviousClosePrice', 0)) if current_price else None

                        price_data = {
                            'stock_code': item.get('itemCode'),
                            'stock_name': item.get('stockName'),
                            'current_price': current_price,
                            'change': parse_price(item.get('compareToPreviousClosePrice')),
                            'change_rate': parse_float(item.get('fluctuationsRatio')),
                            'volume': parse_volume(item.get('accumulatedTradingVolume')),
                            'trading_value': parse_trading_value(item.get('accumulatedTradingValue')),
                            'open_price': parse_price(item.get('openPrice')),
                            'high_price': parse_price(item.get('highPrice')),
                            'low_price': parse_price(item.get('lowPrice')),
                            'prev_close': prev_close,
                        }
                        all_prices.append(price_data)
                    except Exception as e:
                        print(f"  파싱 오류 [{item.get('itemCode')}]: {e}")

        except Exception as e:
            print(f"  네이버 API 호출 실패: {e}")

    return all_prices


def update_price_cache():
    """현재가 캐시 업데이트"""
    start_time = time.time()
    print(f"\n{'='*50}")
    print(f"현재가 캐시 업데이트 (네이버 금융)")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    # 대상 종목 수집
    stock_codes = get_target_stock_codes()
    print(f"대상 종목 수: {len(stock_codes)}")

    if not stock_codes:
        print("업데이트할 종목이 없습니다.")
        return

    # 네이버에서 현재가 조회
    print(f"네이버 금융 조회 중...")
    prices = fetch_prices_from_naver(stock_codes)
    elapsed = time.time() - start_time
    print(f"조회 완료: {len(prices)}개 ({elapsed:.2f}초)")

    # DB에 저장
    if prices:
        db = DatabaseManager()
        db.bulk_upsert_price_cache(prices)
        print(f"DB 저장 완료")

    print(f"\n{'='*50}")
    print(f"완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"총 소요시간: {time.time() - start_time:.2f}초")
    print(f"{'='*50}")


def is_market_hours():
    """장중 시간인지 확인 (09:00 ~ 15:30)"""
    now = datetime.now()
    # 주말 제외
    if now.weekday() >= 5:
        return False

    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1530


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='현재가 캐시 업데이트 (네이버 금융)')
    parser.add_argument('--force', action='store_true', help='장중 시간 체크 무시')
    args = parser.parse_args()

    if args.force or is_market_hours():
        update_price_cache()
    else:
        print(f"장중 시간이 아닙니다. (현재: {datetime.now().strftime('%H:%M')})")
        print("--force 옵션으로 강제 실행 가능")
