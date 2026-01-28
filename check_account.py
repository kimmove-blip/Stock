#!/usr/bin/env python3
"""
계좌 조회 스크립트
사용법: python check_account.py [user_id]
"""

import sys
import requests
from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient

def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 17

    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)

    if not api_key_data:
        print(f"User {user_id}: API 키 설정 없음")
        return

    print(f"=== User {user_id} 계좌 정보 ===")
    print(f"계좌번호: {api_key_data.get('account_number')}")
    print(f"모의투자: {'예' if api_key_data.get('is_mock') else '아니오'}")

    # KIS 클라이언트
    is_mock = bool(api_key_data.get('is_mock', False))
    client = KISClient(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=is_mock
    )

    # 잔고 조회 API 직접 호출
    token = client._get_access_token()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": client.app_key,
        "appsecret": client.app_secret,
        "tr_id": "VTTC8434R" if is_mock else "TTTC8434R",
    }

    params = {
        "CANO": api_key_data.get('account_number'),
        "ACNT_PRDT_CD": "01",
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    resp = requests.get(
        f"{client.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance",
        headers=headers,
        params=params
    )
    data = resp.json()

    # output2: 계좌 요약
    if data.get('output2'):
        s = data['output2'][0] if isinstance(data['output2'], list) else data['output2']
        print(f"\n=== 계좌 요약 ===")
        print(f"D+2 예수금: {int(s.get('nxdy_excc_amt', 0)):,}원")
        print(f"출금가능금액: {int(s.get('prvs_rcdl_excc_amt', 0)):,}원")
        print(f"총 평가금액: {int(s.get('tot_evlu_amt', 0)):,}원")
        print(f"유가증권 평가: {int(s.get('scts_evlu_amt', 0)):,}원")
        print(f"총 매입금액: {int(s.get('pchs_amt_smtl_amt', 0)):,}원")
        print(f"총 손익: {int(s.get('evlu_pfls_smtl_amt', 0)):+,}원")

    # output1: 보유종목
    holdings = data.get('output1', [])
    active = [h for h in holdings if int(h.get('hldg_qty', 0)) > 0]

    if active:
        print(f"\n=== 보유종목 ({len(active)}개) ===")
        for h in active:
            code = h.get('pdno', '')
            name = h.get('prdt_name', '')
            qty = int(h.get('hldg_qty', 0))
            avg_price = int(float(h.get('pchs_avg_pric', 0)))
            current_price = int(h.get('prpr', 0))
            profit_rate = float(h.get('evlu_pfls_rt', 0))
            eval_amt = int(h.get('evlu_amt', 0))
            print(f"  {code} {name}: {qty}주 @{avg_price:,}원 → {current_price:,}원 ({profit_rate:+.2f}%) 평가금액: {eval_amt:,}원")
    else:
        print("\n보유종목 없음")

if __name__ == "__main__":
    main()
