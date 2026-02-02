#!/usr/bin/env python3
"""
계좌 조회 스크립트
사용법: python check_account.py [user_id]
"""

import sys
import glob
import pandas as pd
import requests
from pathlib import Path
from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient

INTRADAY_SCORES_DIR = Path("/home/kimhc/Stock/output/intraday_scores")

def load_scores():
    """최신 스코어 CSV에서 점수 로드"""
    scores_map = {}
    try:
        score_files = sorted(glob.glob(str(INTRADAY_SCORES_DIR / "*.csv")))
        if score_files:
            latest_csv = score_files[-1]
            df = pd.read_csv(latest_csv)
            df['code'] = df['code'].astype(str).str.zfill(6)
            for _, row in df.iterrows():
                scores_map[row['code']] = {
                    'v1': int(row.get('v1', 0)),
                    'v2': int(row.get('v2', 0)),
                    'v4': int(row.get('v4', 0)),
                    'v5': int(row.get('v5', 0)),
                }
            print(f"스코어 로드: {Path(latest_csv).name}")
    except Exception as e:
        print(f"스코어 로드 실패: {e}")
    return scores_map

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

    # 잔고 조회 API 직접 호출 (페이지네이션 지원)
    token = client._get_access_token()

    all_holdings = []
    ctx_area_fk100 = ""
    ctx_area_nk100 = ""
    page = 1
    account_summary = None

    import time

    while True:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": client.app_key,
            "appsecret": client.app_secret,
            "tr_id": "VTTC8434R" if is_mock else "TTTC8434R",
            "tr_cont": "" if page == 1 else "N",  # 첫 요청은 빈값, 이후는 N
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
            "CTX_AREA_FK100": ctx_area_fk100,
            "CTX_AREA_NK100": ctx_area_nk100,
        }

        resp = requests.get(
            f"{client.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=headers,
            params=params
        )
        data = resp.json()

        # 응답 헤더에서 연속조회 여부 확인
        tr_cont = resp.headers.get('tr_cont', '')

        # output1: 보유종목, output2: 계좌요약 (실전/모의 동일)
        # 계좌 요약 (첫 페이지에서만 저장)
        if page == 1 and data.get('output2'):
            summary_data = data['output2']
            account_summary = summary_data[0] if isinstance(summary_data, list) else summary_data

        # 보유종목 추가
        holdings = data.get('output1', [])
        all_holdings.extend(holdings)

        # 연속조회 키 업데이트
        ctx_area_fk100 = data.get('ctx_area_fk100', '').strip()
        ctx_area_nk100 = data.get('ctx_area_nk100', '').strip()

        print(f"  페이지 {page}: {len(holdings)}건 조회 (tr_cont={tr_cont}, fk={ctx_area_fk100[:10] if ctx_area_fk100 else 'N/A'})")

        # 연속조회 종료 조건
        # tr_cont가 'M' 또는 'F'이고, ctx_area_fk100이 있으면 계속 조회
        # tr_cont='D'는 Done (마지막 페이지)
        if tr_cont not in ('M', 'F') or not ctx_area_fk100:
            break

        page += 1
        if page > 10:  # 무한루프 방지
            print("  경고: 최대 페이지 도달")
            break

        time.sleep(0.5)  # 속도 제한

    # 계좌 요약 출력
    if account_summary:
        s = account_summary
        print(f"\n=== 계좌 요약 ===")
        print(f"D+2 예수금: {int(s.get('nxdy_excc_amt', 0)):,}원")
        print(f"출금가능금액: {int(s.get('prvs_rcdl_excc_amt', 0)):,}원")
        print(f"총 평가금액: {int(s.get('tot_evlu_amt', 0)):,}원")
        print(f"유가증권 평가: {int(s.get('scts_evlu_amt', 0)):,}원")
        print(f"총 매입금액: {int(s.get('pchs_amt_smtl_amt', 0)):,}원")
        print(f"총 손익: {int(s.get('evlu_pfls_smtl_amt', 0)):+,}원")

    # 스코어 로드
    scores_map = load_scores()

    # 보유종목 필터 (수량 > 0)
    active = [h for h in all_holdings if int(h.get('hldg_qty', 0)) > 0]

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

            # 스코어 조회
            score_info = scores_map.get(code, {})
            v2_score = score_info.get('v2', '-')

            print(f"  {code} {name}: {qty}주 @{avg_price:,}원 → {current_price:,}원 ({profit_rate:+.2f}%) V2:{v2_score}")
    else:
        print("\n보유종목 없음")

if __name__ == "__main__":
    main()
