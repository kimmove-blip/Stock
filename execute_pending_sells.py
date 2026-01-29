#!/usr/bin/env python3
"""
pending_sell_suggestions 테이블의 매도 예약을 실행하는 스크립트
크론: 50 8 * * 1-5 (08:50 실행)
"""

import sys
import os
sys.path.insert(0, '/home/kimhc/Stock')

from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient
from datetime import datetime

def execute_pending_sells():
    logger = TradeLogger()

    # pending 상태의 매도 예약 조회
    pending_sells = logger.get_pending_sell_suggestions()

    if not pending_sells:
        print(f"[{datetime.now()}] 매도 예약 없음")
        return

    print(f"[{datetime.now()}] 매도 예약 {len(pending_sells)}건 발견")

    # 사용자별로 그룹핑
    user_sells = {}
    for sell in pending_sells:
        user_id = sell.get('user_id')
        if user_id not in user_sells:
            user_sells[user_id] = []
        user_sells[user_id].append(sell)

    for user_id, sells in user_sells.items():
        print(f"\n■ User {user_id} 매도 실행 ({len(sells)}건)")

        # API 키 조회
        api_key_data = logger.get_api_key_settings(user_id)
        if not api_key_data:
            print(f"  ⚠️ API 키 없음, 건너뜀")
            continue

        # 모의투자 제외 (실전만)
        if api_key_data.get('is_mock'):
            print(f"  ⚠️ 모의투자 계좌, 건너뜀")
            continue

        # KIS 클라이언트 생성
        client = KISClient(
            app_key=api_key_data['app_key'],
            app_secret=api_key_data['app_secret'],
            account_number=api_key_data['account_number'],
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_virtual=bool(api_key_data.get('is_mock', True))
        )

        for sell in sells:
            sell_id = sell.get('id')
            stock_code = sell.get('stock_code')
            stock_name = sell.get('stock_name')
            quantity = sell.get('quantity')

            if not stock_code or not quantity:
                print(f"  ⚠️ ID {sell_id}: 코드/수량 없음, 건너뜀")
                logger.update_pending_sell_status(sell_id, 'failed')
                continue

            try:
                # 시장가 매도 주문
                result = client.place_order(
                    stock_code=stock_code,
                    order_type='sell',
                    quantity=quantity,
                    price=0  # 시장가
                )

                if result.get('success'):
                    order_no = result.get('order_no', '')
                    print(f"  ✅ {stock_name} ({stock_code}): {quantity}주 매도 주문 완료 (주문번호: {order_no})")
                    logger.update_pending_sell_status(sell_id, 'executed')

                    # 거래 로그 기록
                    logger.log_trade(
                        user_id=user_id,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        side='sell',
                        quantity=quantity,
                        price=0,
                        order_no=order_no,
                        order_type='market',
                        trade_reason=sell.get('reason', 'V5 점수 하락 매도')
                    )
                else:
                    error_msg = result.get('message', '알 수 없는 오류')
                    print(f"  ❌ {stock_name} ({stock_code}): 매도 실패 - {error_msg}")
                    logger.update_pending_sell_status(sell_id, 'failed')

            except Exception as e:
                print(f"  ❌ {stock_name} ({stock_code}): 예외 발생 - {e}")
                logger.update_pending_sell_status(sell_id, 'failed')

if __name__ == '__main__':
    execute_pending_sells()
