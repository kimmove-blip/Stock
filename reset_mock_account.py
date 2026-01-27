#!/usr/bin/env python3
"""
모의계좌 보유종목 전량 매도 스크립트
장 시작 후 실행하여 현금 확보
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient


def reset_mock_account(user_id: int = 7, dry_run: bool = False):
    """
    모의계좌 보유종목 전량 매도

    Args:
        user_id: 사용자 ID (기본: 7)
        dry_run: True면 실제 매도 없이 시뮬레이션
    """
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)

    if not api_key_data:
        print(f"User {user_id}: API 키 설정 없음")
        return

    if not api_key_data.get('is_mock'):
        print(f"User {user_id}: 모의투자 계좌가 아닙니다!")
        return

    client = KISClient(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_virtual=True
    )

    # 잔고 조회
    balance = client.get_account_balance()
    holdings = balance.get('holdings', [])
    summary = balance.get('summary', {})

    print("=" * 50)
    print(f"모의계좌 리셋 (User {user_id})")
    print("=" * 50)
    print(f"현금 잔고: {summary.get('cash_balance', 0):,}원")
    print(f"총 평가액: {summary.get('total_eval_amount', 0):,}원")
    print()

    if not holdings:
        print("보유 종목 없음")
        return

    print(f"보유 종목 ({len([h for h in holdings if h.get('quantity', 0) > 0])}개) 전량 매도:")
    print()

    success_count = 0
    fail_count = 0

    for h in holdings:
        code = h.get('stock_code')
        name = h.get('stock_name', '')
        qty = h.get('quantity', 0)

        if qty <= 0:
            continue

        print(f"  {code} {name:15s} {qty:5d}주 ... ", end='')

        if dry_run:
            print("[DRY-RUN] 스킵")
            continue

        try:
            result = client.place_order(code, 'sell', qty, 0, order_type='01')
            if result and result.get('success'):
                print(f"성공 (주문번호: {result.get('order_no')})")
                success_count += 1
            else:
                error = result.get('error', 'Unknown error')
                print(f"실패: {error}")
                fail_count += 1
        except Exception as e:
            print(f"에러: {e}")
            fail_count += 1

        # API 속도 제한 (모의투자 2건/초)
        time.sleep(0.6)

    print()
    print("-" * 50)
    print(f"결과: 성공 {success_count}건, 실패 {fail_count}건")

    if success_count > 0 and not dry_run:
        print()
        print("체결 대기 중... (5초)")
        time.sleep(5)

        # 잔고 재조회
        balance = client.get_account_balance()
        summary = balance.get('summary', {})
        print()
        print(f"매도 후 현금 잔고: {summary.get('cash_balance', 0):,}원")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='모의계좌 보유종목 전량 매도')
    parser.add_argument('--user', '-u', type=int, default=7, help='사용자 ID')
    parser.add_argument('--dry-run', '-d', action='store_true', help='시뮬레이션 모드')

    args = parser.parse_args()

    reset_mock_account(args.user, args.dry_run)
