#!/usr/bin/env python3
"""
자동매매 스케줄러 (다중 사용자 지원)
- 장 시간 동안 10분마다 자동매매 실행
- 08:50 ~ 15:20 (평일만)
- 장 종료 후 자동 종료
- 자동매매 활성화된 모든 사용자 순회 실행
"""
import os
import time
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auto_trader import AutoTrader
from trading.trade_logger import TradeLogger

PRE_MARKET = (7, 0)     # 장 시작 전 1회 실행 (07:00)
MARKET_OPEN = (9, 0)    # 장중 10분 간격 시작 (09:00)
MARKET_CLOSE = (15, 20) # 장 마감 전 매매 (15:20)
RUN_INTERVAL = 600      # 10분마다 체크 (초)

def is_pre_market_time():
    """장 시작 전 실행 시간인지 (07:00~07:10)"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return now.hour == 7 and now.minute < 10

def is_market_hours():
    """장 시간인지 확인 (09:00~15:20)"""
    now = datetime.now()
    # 주말 제외
    if now.weekday() >= 5:
        return False
    # 시간 체크
    current_minutes = now.hour * 60 + now.minute
    open_minutes = MARKET_OPEN[0] * 60 + MARKET_OPEN[1]
    close_minutes = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    return open_minutes <= current_minutes <= close_minutes

def run_for_all_users():
    """모든 자동매매 활성화 사용자에 대해 실행"""
    logger = TradeLogger()
    users = logger.get_auto_trade_users()

    if not users:
        print("  자동매매 활성화된 사용자 없음")
        return

    print(f"  {len(users)}명 사용자 자동매매 실행")

    for user in users:
        user_id = user['id']
        user_name = user.get('name', user.get('username', f'User{user_id}'))

        try:
            print(f"\n  [{user_name}] 자동매매 시작...")
            trader = AutoTrader(
                dry_run=False,
                user_id=user_id,
                user_config={
                    'app_key': user['app_key'],
                    'app_secret': user['app_secret'],
                    'account_number': user['account_number'],
                    'account_product_code': user.get('account_product_code', '01'),
                    'is_mock': user.get('is_mock', False),
                    'telegram_chat_id': user.get('telegram_chat_id'),
                }
            )
            result = trader.run()
            print(f"  [{user_name}] 결과: {result.get('status')}")
        except Exception as e:
            print(f"  [{user_name}] 오류: {e}")

def main():
    print(f"[{datetime.now()}] 자동매매 스케줄러 시작 (다중 사용자)")
    print(f"  - 07:00 1회 실행")
    print(f"  - 09:00~15:20 10분 간격 실행")

    has_run_today = False       # 장중 실행 여부
    pre_market_done = False     # 07시 실행 완료 여부

    while True:
        now = datetime.now()

        # 주말이면 종료
        if now.weekday() >= 5:
            print(f"[{now}] 주말 - 스케줄러 종료")
            break

        # 07:00 장 시작 전 1회 실행
        if is_pre_market_time() and not pre_market_done:
            print(f"\n[{now}] 장 시작 전 자동매매 실행 (07:00)")
            run_for_all_users()
            pre_market_done = True
            time.sleep(RUN_INTERVAL)
            continue

        # 09:00~15:20 장중 10분 간격 실행
        if is_market_hours():
            has_run_today = True
            print(f"\n[{now}] 자동매매 실행")
            run_for_all_users()
        else:
            # 장 종료 후 자동 종료
            if has_run_today:
                print(f"[{now}] 장 종료 - 자동매매 스케줄러 종료")
                break
            else:
                # 장 시작 전이면 대기
                print(f"[{now}] 대기 중... (07:00 또는 09:00 시작)")

        # 10분 대기
        time.sleep(RUN_INTERVAL)

    # PID 파일 정리
    if os.path.exists('.auto_trader.pid'):
        os.remove('.auto_trader.pid')

    print(f"[{datetime.now()}] 스케줄러 정상 종료")

if __name__ == "__main__":
    main()
