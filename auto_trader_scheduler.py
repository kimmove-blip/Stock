#!/usr/bin/env python3
"""
자동매매 스케줄러
- 장 시간 동안 주기적으로 자동매매 실행
- 08:50 ~ 15:20 (평일만)
"""
import time
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auto_trader import AutoTrader

MARKET_OPEN = (8, 50)   # 장 시작 전 매매 (08:50)
MARKET_CLOSE = (15, 20) # 장 마감 전 매매 (15:20)
RUN_INTERVAL = 3600     # 1시간마다 체크 (초)

def is_market_hours():
    """장 시간인지 확인"""
    now = datetime.now()
    # 주말 제외
    if now.weekday() >= 5:
        return False
    # 시간 체크
    current_minutes = now.hour * 60 + now.minute
    open_minutes = MARKET_OPEN[0] * 60 + MARKET_OPEN[1]
    close_minutes = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    return open_minutes <= current_minutes <= close_minutes

def main():
    print(f"[{datetime.now()}] 자동매매 스케줄러 시작")
    last_run_date = None

    while True:
        now = datetime.now()
        today = now.date()

        # 장 시간이고, 오늘 아직 실행 안 했으면 실행
        if is_market_hours() and last_run_date != today:
            print(f"\n[{now}] 자동매매 실행")
            try:
                trader = AutoTrader(dry_run=False)
                result = trader.run()
                print(f"결과: {result.get('status')}")
                last_run_date = today
            except Exception as e:
                print(f"오류: {e}")

        # 대기
        time.sleep(RUN_INTERVAL)

if __name__ == "__main__":
    main()
