#!/usr/bin/env python3
"""
V9 갭상승 종목 시초가 매도 스크립트
- auto 모드 계좌의 V9 전략 종목을 시초가에 전량 매도
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient


def get_auto_users():
    """auto 모드 사용자 목록 조회"""
    logger = TradeLogger()
    with logger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM auto_trade_settings WHERE trade_mode = 'auto'")
        return [row['user_id'] for row in cursor.fetchall()]


def get_holdings(user_id):
    """사용자 보유종목 조회"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return []

    account_data = logger.get_real_account_balance(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=bool(api_key_data.get('is_mock', True))
    )

    return [h for h in account_data.get('holdings', []) if h.get('quantity', 0) > 0]


def sell_all_holdings(user_id, dry_run=False):
    """보유종목 전량 시초가 매도"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        print(f"  [user {user_id}] API 키 없음")
        return []

    client = KISClient(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        is_virtual=bool(api_key_data.get('is_mock', True))
    )

    holdings = get_holdings(user_id)
    results = []

    for h in holdings:
        stock_code = h.get('stock_code')
        stock_name = h.get('stock_name')
        quantity = h.get('quantity', 0)

        if quantity <= 0:
            continue

        print(f"  [user {user_id}] {stock_name}({stock_code}) {quantity}주 매도 주문...")

        if dry_run:
            print(f"    [DRY RUN] 매도 주문 스킵")
            results.append({'stock_name': stock_name, 'quantity': quantity, 'status': 'dry_run'})
            continue

        try:
            # 시장가 매도 주문
            result = client.place_order(
                stock_code=stock_code,
                order_type='sell',
                quantity=quantity,
                price=0,  # 시장가
                order_dv='01'  # 시장가 주문
            )

            if result and result.get('rt_cd') == '0':
                order_no = result.get('output', {}).get('ODNO', '')
                print(f"    매도 주문 성공: 주문번호 {order_no}")

                # DB 기록
                logger.log_trade(
                    user_id=user_id,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side='sell',
                    quantity=quantity,
                    price=0,
                    order_no=order_no,
                    status='pending',
                    trade_reason='V9 갭상승 시초가 매도'
                )

                results.append({'stock_name': stock_name, 'quantity': quantity, 'status': 'ordered', 'order_no': order_no})
            else:
                msg = result.get('msg1', '') if result else 'Unknown error'
                print(f"    매도 주문 실패: {msg}")
                results.append({'stock_name': stock_name, 'quantity': quantity, 'status': 'failed', 'error': msg})

        except Exception as e:
            print(f"    매도 주문 에러: {e}")
            results.append({'stock_name': stock_name, 'quantity': quantity, 'status': 'error', 'error': str(e)})

    return results


def check_pending_orders(user_id):
    """미체결 주문 확인"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return []

    client = KISClient(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        is_virtual=bool(api_key_data.get('is_mock', True))
    )

    pending = client.get_pending_orders()
    return pending or []


def check_execution_status(user_id):
    """체결 상태 확인"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return []

    client = KISClient(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        is_virtual=bool(api_key_data.get('is_mock', True))
    )

    today = datetime.now().strftime('%Y%m%d')
    orders = client.get_order_history(start_date=today, end_date=today)
    return orders or []


def main():
    parser = argparse.ArgumentParser(description='V9 갭상승 종목 시초가 매도')
    parser.add_argument('--sell', action='store_true', help='매도 주문 실행')
    parser.add_argument('--check-pending', action='store_true', help='미체결 주문 확인')
    parser.add_argument('--check-executed', action='store_true', help='체결 상태 확인')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드 (실제 주문 안함)')
    parser.add_argument('--user-id', type=int, help='특정 사용자만 실행')
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"V9 갭상승 시초가 매도 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # auto 모드 사용자 조회
    if args.user_id:
        users = [args.user_id]
    else:
        users = get_auto_users()

    print(f"대상 사용자: {users}\n")

    for user_id in users:
        print(f"\n--- User {user_id} ---")

        if args.sell:
            print("\n[매도 주문]")
            results = sell_all_holdings(user_id, dry_run=args.dry_run)
            for r in results:
                print(f"  {r.get('stock_name')}: {r.get('status')}")

        if args.check_pending:
            print("\n[미체결 내역]")
            pending = check_pending_orders(user_id)
            if pending:
                for p in pending:
                    print(f"  {p.get('stock_name', p.get('pdno'))}: {p.get('order_qty')}주 @ {p.get('order_price')}원")
            else:
                print("  미체결 없음")

        if args.check_executed:
            print("\n[오늘 체결 내역]")
            orders = check_execution_status(user_id)
            if orders:
                for o in orders:
                    side = '매도' if o.get('side') == 'sell' else '매수'
                    name = o.get('stock_name', o.get('pdno'))
                    qty = o.get('order_qty') or o.get('tot_ccld_qty', 0)
                    price = o.get('executed_price') or o.get('avg_prvs') or 0
                    print(f"  {side} {name}: {qty}주 @ {price:,}원")
            else:
                print("  체결 내역 없음")

    print(f"\n{'='*50}")
    print("완료")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
