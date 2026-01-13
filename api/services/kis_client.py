"""
한국투자증권 API 클라이언트
실시간 시세 조회 및 계좌 관리
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()


class KISClient:
    """한국투자증권 Open API 클라이언트"""

    # API 기본 URL (실전투자)
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    # 모의투자용: "https://openapivts.koreainvestment.com:29443"

    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY")
        self.app_secret = os.getenv("KIS_APP_SECRET")
        self.account_no = os.getenv("KIS_ACCOUNT_NO")
        self.account_product_code = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")

        self._access_token = None
        self._token_expires_at = None

        if not all([self.app_key, self.app_secret]):
            raise ValueError("KIS API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

    def _get_access_token(self) -> str:
        """OAuth 토큰 발급/갱신"""
        # 토큰이 유효하면 재사용
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token

        url = f"{self.BASE_URL}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }

        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            res.raise_for_status()
            data = res.json()

            self._access_token = data["access_token"]
            # 토큰 유효시간은 보통 24시간
            expires_in = int(data.get("expires_in", 86400))
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            return self._access_token

        except requests.exceptions.RequestException as e:
            raise Exception(f"토큰 발급 실패: {str(e)}")

    def _get_headers(self, tr_id: str) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        token = self._get_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    def get_current_price(self, stock_code: str) -> Optional[Dict]:
        """
        주식 현재가 조회

        Args:
            stock_code: 종목코드 (6자리, 예: '005930')

        Returns:
            현재가 정보 딕셔너리
        """
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"

        # FHKST01010100: 주식 현재가 시세
        headers = self._get_headers("FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식, ETF, ETN
            "FID_INPUT_ISCD": stock_code
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                print(f"API 오류: {data.get('msg1', '알 수 없는 오류')}")
                return None

            output = data.get("output", {})

            return {
                "stock_code": stock_code,
                "stock_name": output.get("hts_kor_isnm", ""),  # 종목명
                "current_price": int(output.get("stck_prpr", 0)),  # 현재가
                "change": int(output.get("prdy_vrss", 0)),  # 전일대비
                "change_rate": float(output.get("prdy_ctrt", 0)),  # 등락률
                "change_sign": output.get("prdy_vrss_sign", ""),  # 부호 (1:상한, 2:상승, 3:보합, 4:하한, 5:하락)
                "volume": int(output.get("acml_vol", 0)),  # 누적거래량
                "trading_value": int(output.get("acml_tr_pbmn", 0)),  # 누적거래대금
                "open_price": int(output.get("stck_oprc", 0)),  # 시가
                "high_price": int(output.get("stck_hgpr", 0)),  # 고가
                "low_price": int(output.get("stck_lwpr", 0)),  # 저가
                "prev_close": int(output.get("stck_sdpr", 0)),  # 전일종가
                "per": float(output.get("per", 0)) if output.get("per") else None,  # PER
                "pbr": float(output.get("pbr", 0)) if output.get("pbr") else None,  # PBR
                "market_cap": int(output.get("hts_avls", 0)),  # 시가총액(억)
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            print(f"현재가 조회 실패 [{stock_code}]: {str(e)}")
            return None

    def get_multiple_prices(self, stock_codes: List[str]) -> List[Dict]:
        """
        여러 종목 현재가 일괄 조회

        Args:
            stock_codes: 종목코드 리스트

        Returns:
            현재가 정보 리스트
        """
        results = []

        for code in stock_codes:
            price_data = self.get_current_price(code)
            if price_data:
                results.append(price_data)
            # API 호출 제한 방지 (초당 20회 제한)
            time.sleep(0.05)

        return results

    def get_daily_price(self, stock_code: str, period: str = "D", count: int = 30) -> Optional[List[Dict]]:
        """
        주식 일별 시세 조회

        Args:
            stock_code: 종목코드
            period: 기간 (D:일, W:주, M:월)
            count: 조회 개수

        Returns:
            일별 시세 리스트
        """
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"

        headers = self._get_headers("FHKST01010400")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_PERIOD_DIV_CODE": period,
            "FID_ORG_ADJ_PRC": "0"  # 0: 수정주가, 1: 원주가
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                return None

            output = data.get("output", [])

            prices = []
            for item in output[:count]:
                prices.append({
                    "date": item.get("stck_bsop_date", ""),  # 날짜
                    "close": int(item.get("stck_clpr", 0)),  # 종가
                    "open": int(item.get("stck_oprc", 0)),  # 시가
                    "high": int(item.get("stck_hgpr", 0)),  # 고가
                    "low": int(item.get("stck_lwpr", 0)),  # 저가
                    "volume": int(item.get("acml_vol", 0)),  # 거래량
                    "change": int(item.get("prdy_vrss", 0)),  # 전일대비
                    "change_rate": float(item.get("prdy_ctrt", 0))  # 등락률
                })

            return prices

        except requests.exceptions.RequestException as e:
            print(f"일별 시세 조회 실패 [{stock_code}]: {str(e)}")
            return None

    def get_account_balance(self) -> Optional[Dict]:
        """
        계좌 잔고 조회

        Returns:
            계좌 잔고 정보
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"

        # TTTC8434R: 주식 잔고 조회
        headers = self._get_headers("TTTC8434R")
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                print(f"잔고 조회 오류: {data.get('msg1', '')}")
                return None

            output1 = data.get("output1", [])  # 보유종목
            output2 = data.get("output2", [])  # 계좌 요약

            holdings = []
            for item in output1:
                holdings.append({
                    "stock_code": item.get("pdno", ""),
                    "stock_name": item.get("prdt_name", ""),
                    "quantity": int(item.get("hldg_qty", 0)),
                    "avg_price": int(float(item.get("pchs_avg_pric", 0))),
                    "current_price": int(item.get("prpr", 0)),
                    "eval_amount": int(item.get("evlu_amt", 0)),
                    "profit_loss": int(item.get("evlu_pfls_amt", 0)),
                    "profit_rate": float(item.get("evlu_pfls_rt", 0))
                })

            summary = {}
            if output2:
                s = output2[0]
                summary = {
                    "total_eval_amount": int(s.get("tot_evlu_amt", 0)),
                    "total_profit_loss": int(s.get("evlu_pfls_smtl_amt", 0)),
                    "cash_balance": int(s.get("dnca_tot_amt", 0)),
                    "profit_rate": float(s.get("tot_evlu_pfls_rt", 0)) if s.get("tot_evlu_pfls_rt") else 0
                }

            return {
                "holdings": holdings,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            print(f"잔고 조회 실패: {str(e)}")
            return None


# 싱글톤 인스턴스
_kis_client: Optional[KISClient] = None


def get_kis_client() -> KISClient:
    """KIS 클라이언트 싱글톤 반환"""
    global _kis_client
    if _kis_client is None:
        _kis_client = KISClient()
    return _kis_client
