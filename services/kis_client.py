"""
한국투자증권 API 클라이언트
실시간 시세 조회 및 계좌 관리
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import threading

load_dotenv()

# 토큰 캐시 파일 경로 (단일 사용자용 - 환경변수 사용 시)
TOKEN_CACHE_FILE = Path(__file__).parent.parent.parent / ".kis_token_cache.json"
# 다중 사용자 토큰 캐시 (app_key별로 토큰 저장)
MULTI_TOKEN_CACHE_FILE = Path(__file__).parent.parent.parent / ".kis_multi_token_cache.json"
_token_lock = threading.Lock()

# 메모리 내 토큰 캐시 (앱 키별)
_memory_token_cache: Dict[str, Dict] = {}


class KISClient:
    """한국투자증권 Open API 클라이언트"""

    # API URL 설정
    VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자
    REAL_URL = "https://openapi.koreainvestment.com:9443"  # 실전투자

    # TR_ID 설정
    TR_IDS = {
        "virtual": {
            "buy": "VTTC0802U",   # 모의 매수
            "sell": "VTTC0801U",  # 모의 매도
            "cancel": "VTTC0803U",  # 모의 취소
            "balance": "VTTC8434R",  # 모의 잔고
            "pending": "VTTC8036R",  # 모의 미체결
        },
        "real": {
            "buy": "TTTC0802U",   # 실전 매수
            "sell": "TTTC0801U",  # 실전 매도
            "cancel": "TTTC0803U",  # 실전 취소
            "balance": "TTTC8434R",  # 실전 잔고
            "pending": "TTTC8036R",  # 실전 미체결
        }
    }

    def __init__(
        self,
        is_virtual: bool = True,
        app_key: str = None,
        app_secret: str = None,
        account_number: str = None,
        account_product_code: str = None,
        is_mock: bool = None  # is_virtual 별칭
    ):
        # is_mock이 전달되면 is_virtual 대신 사용
        if is_mock is not None:
            is_virtual = is_mock

        # 파라미터로 전달되면 사용, 아니면 환경변수 사용
        self.app_key = app_key or os.getenv("KIS_APP_KEY")
        self.app_secret = app_secret or os.getenv("KIS_APP_SECRET")
        self.account_no = account_number or os.getenv("KIS_ACCOUNT_NO")
        self.account_product_code = account_product_code or os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")

        self._access_token = None
        self._token_expires_at = None

        # 모의/실전 투자 설정
        self.is_virtual = is_virtual
        self.BASE_URL = self.VIRTUAL_URL if is_virtual else self.REAL_URL
        self.tr_ids = self.TR_IDS["virtual"] if is_virtual else self.TR_IDS["real"]

        if not all([self.app_key, self.app_secret]):
            raise ValueError("KIS API 키가 설정되지 않았습니다.")

        # 파라미터로 전달받은 경우 토큰 캐시 사용 안함
        self._use_custom_credentials = app_key is not None

        # 시작 시 캐시된 토큰 로드 (환경변수 사용 시에만)
        if not self._use_custom_credentials:
            self._load_cached_token()

    def _load_cached_token(self):
        """파일에서 캐시된 토큰 로드"""
        try:
            if TOKEN_CACHE_FILE.exists():
                with open(TOKEN_CACHE_FILE, 'r') as f:
                    cache = json.load(f)

                expires_at = datetime.fromisoformat(cache['expires_at'])
                # 만료 5분 전까지 유효하면 사용
                if datetime.now() < expires_at - timedelta(minutes=5):
                    self._access_token = cache['access_token']
                    self._token_expires_at = expires_at
        except Exception:
            pass  # 캐시 로드 실패 시 무시

    def _save_token_cache(self):
        """토큰을 파일에 캐시"""
        try:
            with _token_lock:
                cache = {
                    'access_token': self._access_token,
                    'expires_at': self._token_expires_at.isoformat()
                }
                with open(TOKEN_CACHE_FILE, 'w') as f:
                    json.dump(cache, f)
                # 보안을 위해 파일 권한 제한
                TOKEN_CACHE_FILE.chmod(0o600)
        except Exception:
            pass  # 캐시 저장 실패 시 무시

    def _get_cache_key(self) -> str:
        """토큰 캐시 키 생성 (app_key + is_virtual 조합)"""
        # bool로 변환하여 0/False, 1/True 불일치 방지
        return f"{self.app_key}_{bool(self.is_virtual)}"

    def _load_user_cached_token(self) -> bool:
        """사용자별 캐시된 토큰 로드 (메모리 + 파일)"""
        cache_key = self._get_cache_key()

        # 1. 메모리 캐시 확인
        if cache_key in _memory_token_cache:
            cached = _memory_token_cache[cache_key]
            expires_at = datetime.fromisoformat(cached['expires_at'])
            if datetime.now() < expires_at - timedelta(minutes=5):
                self._access_token = cached['access_token']
                self._token_expires_at = expires_at
                return True

        # 2. 파일 캐시 확인
        try:
            if MULTI_TOKEN_CACHE_FILE.exists():
                with open(MULTI_TOKEN_CACHE_FILE, 'r') as f:
                    all_cache = json.load(f)
                    if cache_key in all_cache:
                        cached = all_cache[cache_key]
                        expires_at = datetime.fromisoformat(cached['expires_at'])
                        if datetime.now() < expires_at - timedelta(minutes=5):
                            self._access_token = cached['access_token']
                            self._token_expires_at = expires_at
                            # 메모리 캐시에도 저장
                            _memory_token_cache[cache_key] = cached
                            print(f"[KIS] 토큰 캐시 로드 성공: {cache_key}")
                            return True
                        else:
                            print(f"[KIS] 토큰 캐시 만료: {cache_key}, expires={expires_at}")
                    else:
                        print(f"[KIS] 캐시 키 없음: {cache_key}, 기존 키: {list(all_cache.keys())}")
            else:
                print(f"[KIS] 캐시 파일 없음: {MULTI_TOKEN_CACHE_FILE}")
        except Exception as e:
            print(f"[KIS] 캐시 로드 에러: {e}")

        return False

    def _save_user_token_cache(self):
        """사용자별 토큰 캐시 저장 (메모리 + 파일)"""
        cache_key = self._get_cache_key()
        cache_data = {
            'access_token': self._access_token,
            'expires_at': self._token_expires_at.isoformat()
        }

        # 메모리 캐시에 저장
        _memory_token_cache[cache_key] = cache_data

        # 파일 캐시에 저장
        try:
            with _token_lock:
                all_cache = {}
                if MULTI_TOKEN_CACHE_FILE.exists():
                    with open(MULTI_TOKEN_CACHE_FILE, 'r') as f:
                        all_cache = json.load(f)

                all_cache[cache_key] = cache_data

                with open(MULTI_TOKEN_CACHE_FILE, 'w') as f:
                    json.dump(all_cache, f)
                MULTI_TOKEN_CACHE_FILE.chmod(0o600)
        except Exception:
            pass

    def _invalidate_token(self):
        """토큰 무효화 (캐시에서 삭제) - 토큰 만료 에러 시 호출"""
        cache_key = self._get_cache_key()

        # 메모리 토큰 초기화
        self._access_token = None
        self._token_expires_at = None

        # 메모리 캐시에서 삭제
        if cache_key in _memory_token_cache:
            del _memory_token_cache[cache_key]

        # 파일 캐시에서 삭제
        try:
            with _token_lock:
                if MULTI_TOKEN_CACHE_FILE.exists():
                    with open(MULTI_TOKEN_CACHE_FILE, 'r') as f:
                        all_cache = json.load(f)
                    if cache_key in all_cache:
                        del all_cache[cache_key]
                        with open(MULTI_TOKEN_CACHE_FILE, 'w') as f:
                            json.dump(all_cache, f)
                        print(f"[토큰] 만료된 토큰 캐시 삭제: {cache_key}")
        except Exception as e:
            print(f"[토큰] 캐시 삭제 실패: {e}")

    def _get_access_token(self) -> str:
        """OAuth 토큰 발급/갱신"""
        # 토큰이 유효하면 재사용
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token

        # 사용자별 캐시에서 토큰 로드 (커스텀 자격증명도 포함)
        if self._load_user_cached_token():
            return self._access_token

        # 환경변수 사용 시 기존 단일 캐시도 확인
        if not self._use_custom_credentials:
            self._load_cached_token()
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

            # 사용자별 토큰 캐시에 저장 (모든 사용자)
            self._save_user_token_cache()

            # 환경변수 사용 시 기존 단일 캐시에도 저장 (하위 호환성)
            if not self._use_custom_credentials:
                self._save_token_cache()

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

    def get_current_price(self, stock_code: str, retry_count: int = 2) -> Optional[Dict]:
        """
        주식 현재가 조회 (재시도 로직 포함)

        Args:
            stock_code: 종목코드 (6자리, 예: '005930')
            retry_count: 실패 시 재시도 횟수

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

        last_error = None
        for attempt in range(retry_count + 1):
            try:
                if attempt > 0:
                    time.sleep(0.3)  # 재시도 시 0.3초 대기

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
                last_error = e
                if attempt < retry_count:
                    continue  # 재시도

        print(f"현재가 조회 실패 [{stock_code}]: {str(last_error)}")
        return None

    def get_multiple_prices(self, stock_codes: List[str], max_workers: int = 10) -> List[Dict]:
        """
        여러 종목 현재가 일괄 조회 (병렬 처리)

        Args:
            stock_codes: 종목코드 리스트
            max_workers: 최대 동시 처리 스레드 수 (기본 10)

        Returns:
            현재가 정보 리스트
        """
        results = []

        # ThreadPoolExecutor로 병렬 처리 (API 제한 고려하여 max 10)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 모든 종목에 대해 future 생성
            futures = {
                executor.submit(self.get_current_price, code): code
                for code in stock_codes
            }

            # 완료된 순서대로 결과 수집
            for future in as_completed(futures):
                code = futures[future]
                try:
                    price_data = future.result()
                    if price_data:
                        results.append(price_data)
                except Exception as e:
                    print(f"가격 조회 실패 [{code}]: {e}")

        return results

    def get_investor_trend(self, stock_code: str, days: int = 5) -> Optional[Dict]:
        """
        투자자별 매매동향 조회 (기관/외국인 수급)

        Args:
            stock_code: 종목코드 (6자리)
            days: 조회 일수 (기본 5일)

        Returns:
            {
                'foreign_net': 외국인 순매수량 (최근 N일 합계),
                'institution_net': 기관 순매수량 (최근 N일 합계),
                'individual_net': 개인 순매수량,
                'foreign_ratio': 외국인 보유 비율,
                'daily': [일별 상세 데이터]
            }
        """
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor"

        # FHKST01010900: 주식 투자자별 매매동향
        headers = self._get_headers("FHKST01010900")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                print(f"투자자 동향 조회 오류: {data.get('msg1', '')}")
                return None

            output = data.get("output", [])

            if not output:
                return None

            # 최근 N일 데이터 집계
            foreign_net = 0
            institution_net = 0
            individual_net = 0
            daily_data = []

            for i, item in enumerate(output[:days]):
                # 외국인 순매수량 (빈 문자열 처리)
                frgn_ntby_str = item.get("frgn_ntby_qty", "0") or "0"
                frgn_ntby = int(frgn_ntby_str) if frgn_ntby_str.lstrip('-').isdigit() else 0
                # 기관 순매수량 (기관 = 금융투자 + 보험 + 투신 + 은행 + 기타금융 + 연기금 등)
                orgn_ntby_str = item.get("orgn_ntby_qty", "0") or "0"
                orgn_ntby = int(orgn_ntby_str) if orgn_ntby_str.lstrip('-').isdigit() else 0
                # 개인 순매수량
                prsn_ntby_str = item.get("prsn_ntby_qty", "0") or "0"
                prsn_ntby = int(prsn_ntby_str) if prsn_ntby_str.lstrip('-').isdigit() else 0

                foreign_net += frgn_ntby
                institution_net += orgn_ntby
                individual_net += prsn_ntby

                # 거래대금 파싱 (빈 문자열 처리)
                frgn_tr_str = item.get("frgn_ntby_tr_pbmn", "0") or "0"
                frgn_tr = int(frgn_tr_str) if frgn_tr_str.lstrip('-').isdigit() else 0

                daily_data.append({
                    "date": item.get("stck_bsop_date", ""),
                    "foreign_net": frgn_ntby,
                    "institution_net": orgn_ntby,
                    "individual_net": prsn_ntby,
                    "foreign_total": frgn_tr,  # 거래대금
                })

            # 외국인 보유비율 (첫 번째 데이터에서)
            frgn_rt_str = output[0].get("frgn_hldn_rt", "0") or "0" if output else "0"
            try:
                foreign_ratio = float(frgn_rt_str)
            except ValueError:
                foreign_ratio = 0

            return {
                "stock_code": stock_code,
                "foreign_net": foreign_net,
                "institution_net": institution_net,
                "individual_net": individual_net,
                "foreign_ratio": foreign_ratio,
                "days": days,
                "daily": daily_data
            }

        except requests.exceptions.RequestException as e:
            print(f"투자자 동향 조회 실패 [{stock_code}]: {str(e)}")
            return None

    def get_conclusion_trend(self, stock_code: str) -> Optional[Dict]:
        """
        주식 체결 추이 조회 (체결강도 포함)

        Args:
            stock_code: 종목코드 (6자리)

        Returns:
            {
                'buy_strength': 체결강도 (매수체결량/매도체결량 × 100),
                'buy_volume': 매수 체결량,
                'sell_volume': 매도 체결량,
                'total_volume': 총 체결량,
            }
        """
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-ccnl"

        # FHKST01010300: 주식현재가 체결
        headers = self._get_headers("FHKST01010300")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                return None

            output1 = data.get("output1", {})
            output2 = data.get("output2", [])

            if not output1:
                return None

            # 체결강도 계산 (output1에서 직접 가져오거나 output2에서 계산)
            # 체결강도 = 매수체결량 / 매도체결량 × 100
            seln_cntg_csnu = int(output1.get("seln_cntg_csnu", 0) or 0)  # 매도체결건수
            shnu_cntg_csnu = int(output1.get("shnu_cntg_csnu", 0) or 0)  # 매수체결건수
            seln_cntg_smtn = int(output1.get("seln_cntg_smtn", 0) or 0)  # 매도체결수량
            shnu_cntg_smtn = int(output1.get("shnu_cntg_smtn", 0) or 0)  # 매수체결수량

            # 체결강도 = 매수체결량 / 매도체결량 × 100
            if seln_cntg_smtn > 0:
                buy_strength = round(shnu_cntg_smtn / seln_cntg_smtn * 100, 1)
            else:
                buy_strength = 100.0 if shnu_cntg_smtn > 0 else 0.0

            return {
                "stock_code": stock_code,
                "buy_strength": buy_strength,
                "buy_volume": shnu_cntg_smtn,
                "sell_volume": seln_cntg_smtn,
                "buy_count": shnu_cntg_csnu,
                "sell_count": seln_cntg_csnu,
                "total_volume": shnu_cntg_smtn + seln_cntg_smtn,
            }

        except requests.exceptions.RequestException as e:
            print(f"체결 추이 조회 실패 [{stock_code}]: {str(e)}")
            return None

    def get_index_price(self, index_code: str = "0001") -> Optional[Dict]:
        """
        지수 현재가 조회 (코스피/코스닥)

        Args:
            index_code: 지수코드 (0001: 코스피, 1001: 코스닥)

        Returns:
            {
                'index_code': 지수코드,
                'current': 현재지수,
                'change': 전일대비,
                'change_rate': 등락률,
            }
        """
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"

        # FHPUP02100000: 국내주식 업종기간별 시세
        headers = self._get_headers("FHPUP02100000")
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": index_code
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                return None

            output = data.get("output", {})

            return {
                "index_code": index_code,
                "index_name": "KOSPI" if index_code == "0001" else "KOSDAQ",
                "current": float(output.get("bstp_nmix_prpr", 0) or 0),
                "change": float(output.get("bstp_nmix_prdy_vrss", 0) or 0),
                "change_rate": float(output.get("bstp_nmix_prdy_ctrt", 0) or 0),
            }

        except requests.exceptions.RequestException as e:
            print(f"지수 조회 실패 [{index_code}]: {str(e)}")
            return None

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

    def get_minute_chart(self, stock_code: str, target_date: str = None, time_unit: str = "1") -> Optional[List[Dict]]:
        """
        주식 분봉 데이터 조회

        Args:
            stock_code: 종목코드 (6자리)
            target_date: 조회 날짜 (YYYYMMDD 형식, None이면 오늘)
            time_unit: 분봉 단위 ("1": 1분, "5": 5분, "10": 10분, "30": 30분, "60": 60분)

        Returns:
            분봉 데이터 리스트 (시간 오름차순)
            [
                {
                    'time': '090500',      # 시간 (HHMMSS)
                    'open': 50000,         # 시가
                    'high': 50100,         # 고가
                    'low': 49900,          # 저가
                    'close': 50050,        # 종가
                    'volume': 12345,       # 거래량
                    'cum_volume': 123456,  # 누적거래량
                },
                ...
            ]
        """
        # 주식당일분봉조회 API
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"

        headers = self._get_headers("FHKST03010200")

        if target_date is None:
            target_date = datetime.now().strftime("%Y%m%d")

        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": "153000",  # 조회 종료 시간 (장 마감)
            "FID_PW_DATA_INCU_YN": "Y",    # 과거 데이터 포함 여부
        }

        try:
            all_data = []
            last_time = "153000"

            # 페이지네이션 (분봉 데이터가 많을 수 있음)
            for _ in range(10):  # 최대 10번 반복
                params["FID_INPUT_HOUR_1"] = last_time

                res = requests.get(url, headers=headers, params=params, timeout=10)
                res.raise_for_status()
                data = res.json()

                if data.get("rt_cd") != "0":
                    if all_data:
                        break
                    return None

                output2 = data.get("output2", [])
                if not output2:
                    break

                for item in output2:
                    stck_cntg_hour = item.get("stck_cntg_hour", "")
                    if not stck_cntg_hour:
                        continue

                    all_data.append({
                        "time": stck_cntg_hour,
                        "open": int(item.get("stck_oprc", 0)),
                        "high": int(item.get("stck_hgpr", 0)),
                        "low": int(item.get("stck_lwpr", 0)),
                        "close": int(item.get("stck_prpr", 0)),
                        "volume": int(item.get("cntg_vol", 0)),
                        "cum_volume": int(item.get("acml_vol", 0)),
                        "trading_value": int(item.get("acml_tr_pbmn", 0)),
                    })

                    last_time = stck_cntg_hour

                # 다음 페이지가 없으면 종료
                if len(output2) < 30:
                    break

                time.sleep(0.1)  # API 속도 제한

            # 시간순 정렬 (오름차순)
            all_data.sort(key=lambda x: x["time"])

            return all_data

        except requests.exceptions.RequestException as e:
            print(f"분봉 조회 실패 [{stock_code}]: {str(e)}")
            return None

    def get_minute_chart_by_date(self, stock_code: str, target_date: str, start_time: str = "090000") -> Optional[List[Dict]]:
        """
        특정 날짜의 분봉 데이터 조회 (주식일별분봉조회)

        Args:
            stock_code: 종목코드 (6자리)
            target_date: 조회 날짜 (YYYYMMDD 형식)
            start_time: 조회 시작 시간 (HHMMSS 형식, 기본 090000)

        Returns:
            분봉 데이터 리스트
        """
        # 주식일별분봉조회 API - TR ID: FHKST03010230
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"

        headers = self._get_headers("FHKST03010230")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": target_date,
            "FID_INPUT_HOUR_1": start_time,
            "FID_PW_DATA_INCU_YN": "N",
            "FID_FAKE_TICK_INCU_YN": "",  # 허봉 포함 여부 (공백 필수)
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                print(f"분봉 API 오류 [{stock_code}]: {data.get('msg1', '')}")
                return None

            output2 = data.get("output2", [])
            if not output2:
                return None

            result = []
            for item in output2:
                stck_cntg_hour = item.get("stck_cntg_hour", "")
                if not stck_cntg_hour:
                    continue

                result.append({
                    "date": item.get("stck_bsop_date", target_date),
                    "time": stck_cntg_hour,
                    "open": int(item.get("stck_oprc", 0)),
                    "high": int(item.get("stck_hgpr", 0)),
                    "low": int(item.get("stck_lwpr", 0)),
                    "close": int(item.get("stck_prpr", 0)),
                    "volume": int(item.get("cntg_vol", 0)),
                    "cum_volume": int(item.get("acml_vol", 0)),
                })

            # 시간순 정렬
            result.sort(key=lambda x: x["time"])
            return result

        except requests.exceptions.RequestException as e:
            print(f"일별 분봉 조회 실패 [{stock_code}] {target_date}: {str(e)}")
            return None

    def get_account_balance(self, _retry: bool = False, _retry_count: int = 0) -> Optional[Dict]:
        """
        계좌 잔고 조회

        Returns:
            계좌 잔고 정보
        """
        import time
        MAX_RETRIES = 3

        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"

        # 모의/실전에 따라 TR_ID 선택
        headers = self._get_headers(self.tr_ids["balance"])
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

            # 500 에러 처리
            if res.status_code == 500:
                try:
                    err_data = res.json()
                    # 토큰 만료
                    if err_data.get("msg_cd") == "EGW00123":
                        if not _retry:
                            print("[잔고조회] 토큰 만료 - 새 토큰 발급 후 재시도")
                            self._invalidate_token()
                            return self.get_account_balance(_retry=True, _retry_count=0)
                except:
                    pass

                # 일반 500 에러 - 재시도
                if _retry_count < MAX_RETRIES:
                    wait_time = (_retry_count + 1) * 2
                    print(f"[잔고조회] 서버 오류(500), {wait_time}초 후 재시도 ({_retry_count + 1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    return self.get_account_balance(_retry=_retry, _retry_count=_retry_count + 1)

            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                # 토큰 만료 에러 확인
                if data.get("msg_cd") == "EGW00123" and not _retry:
                    print("[잔고조회] 토큰 만료 - 새 토큰 발급 후 재시도")
                    self._invalidate_token()
                    return self.get_account_balance(_retry=True)
                print(f"잔고 조회 오류: {data.get('msg1', '')}")
                return None

            output1 = data.get("output1", [])
            output2 = data.get("output2", [])

            # 모의투자는 output1/output2가 실전과 반대 (2026-01-21 발견)
            # output 내용을 보고 자동 판단: pdno(종목코드)가 있으면 보유종목, dnca_tot_amt(예수금)가 있으면 잔고요약
            holdings_output = output1
            summary_output = output2

            if output1 and isinstance(output1, list) and len(output1) > 0:
                first_item = output1[0]
                # output1에 dnca_tot_amt가 있으면 잔고요약 → 모의투자이므로 swap
                if "dnca_tot_amt" in first_item:
                    holdings_output = output2
                    summary_output = output1

            holdings = []
            for item in holdings_output:
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
            if summary_output:
                s = summary_output[0] if isinstance(summary_output, list) else summary_output
                summary = {
                    "total_eval_amount": int(s.get("scts_evlu_amt", 0)),  # 주식 평가금액
                    "total_profit_loss": int(s.get("evlu_pfls_smtl_amt", 0)),
                    "cash_balance": int(s.get("dnca_tot_amt", 0)),  # 현재 예수금
                    "d2_cash_balance": int(s.get("prvs_rcdl_excc_amt", 0)),  # D+2 예수금
                    "profit_rate": float(s.get("asst_icdc_erng_rt", 0)) if s.get("asst_icdc_erng_rt") else 0
                }

            # 최대매수가능금액 조회
            max_buy_amt = self._get_max_buy_amount()
            if max_buy_amt is not None:
                summary["max_buy_amt"] = max_buy_amt

            return {
                "holdings": holdings,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            # 타임아웃이나 연결 에러 - 재시도
            if _retry_count < MAX_RETRIES:
                wait_time = (_retry_count + 1) * 2
                print(f"[잔고조회] 네트워크 오류, {wait_time}초 후 재시도 ({_retry_count + 1}/{MAX_RETRIES}): {str(e)}")
                time.sleep(wait_time)
                return self.get_account_balance(_retry=_retry, _retry_count=_retry_count + 1)
            print(f"잔고 조회 실패 (재시도 {MAX_RETRIES}회 후): {str(e)}")
            return None

    def _get_max_buy_amount(self) -> Optional[int]:
        """최대매수가능금액 조회"""
        try:
            url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
            tr_id = "VTTC8908R" if self.is_virtual else "TTTC8908R"
            headers = self._get_headers(tr_id)
            params = {
                "CANO": self.account_no,
                "ACNT_PRDT_CD": self.account_product_code,
                "PDNO": "005930",  # 삼성전자 (기준 종목)
                "ORD_UNPR": "0",
                "ORD_DVSN": "01",
                "CMA_EVLU_AMT_ICLD_YN": "N",
                "OVRS_ICLD_YN": "N",
            }
            res = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get("rt_cd") == "0":
                return int(data.get("output", {}).get("max_buy_amt", 0))
        except Exception as e:
            print(f"최대매수가능금액 조회 실패: {e}")
        return None

    def place_order(
        self,
        stock_code: str,
        side: str,
        quantity: int,
        price: int = 0,
        order_type: str = "01"
    ) -> Optional[Dict]:
        """
        주식 주문 실행

        Args:
            stock_code: 종목코드 (6자리)
            side: 주문 방향 ("buy" 또는 "sell")
            quantity: 주문 수량
            price: 주문 가격 (시장가일 때 0)
            order_type: 주문 구분 ("00": 지정가, "01": 시장가)

        Returns:
            주문 결과 딕셔너리
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        if side not in ["buy", "sell"]:
            raise ValueError("side는 'buy' 또는 'sell'이어야 합니다.")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

        tr_id = self.tr_ids["buy"] if side == "buy" else self.tr_ids["sell"]
        headers = self._get_headers(tr_id)

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "PDNO": stock_code,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }

        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                error_msg = data.get("msg1", "알 수 없는 오류")
                print(f"주문 실패: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "stock_code": stock_code,
                    "side": side,
                    "quantity": quantity,
                    "price": price
                }

            output = data.get("output", {})

            return {
                "success": True,
                "order_no": output.get("ODNO", ""),
                "order_time": output.get("ORD_TMD", ""),
                "stock_code": stock_code,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_type": "시장가" if order_type == "01" else "지정가",
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            print(f"주문 요청 실패 [{stock_code}]: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "stock_code": stock_code,
                "side": side,
                "quantity": quantity,
                "price": price
            }

    def cancel_order(
        self,
        order_no: str,
        stock_code: str,
        quantity: int,
        order_type: str = "01"
    ) -> Optional[Dict]:
        """
        주문 취소

        Args:
            order_no: 주문번호
            stock_code: 종목코드
            quantity: 취소 수량
            order_type: 원주문 구분

        Returns:
            취소 결과 딕셔너리
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/order-rvsecncl"

        tr_id = self.tr_ids["cancel"]
        headers = self._get_headers(tr_id)

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_no,
            "ORD_DVSN": order_type,
            "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }

        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                error_msg = data.get("msg1", "알 수 없는 오류")
                print(f"주문 취소 실패: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "order_no": order_no
                }

            output = data.get("output", {})

            return {
                "success": True,
                "cancel_order_no": output.get("ODNO", ""),
                "original_order_no": order_no,
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            print(f"주문 취소 요청 실패: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "order_no": order_no
            }

    def modify_order(
        self,
        order_no: str,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00"
    ) -> Optional[Dict]:
        """
        주문 정정

        Args:
            order_no: 원주문번호
            stock_code: 종목코드
            quantity: 정정 수량
            price: 정정 가격
            order_type: 주문 구분 ("00": 지정가, "01": 시장가)

        Returns:
            정정 결과 딕셔너리
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/order-rvsecncl"

        tr_id = self.tr_ids["cancel"]  # 정정/취소 동일 TR_ID 사용
        headers = self._get_headers(tr_id)

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_no,
            "ORD_DVSN": order_type,
            "RVSE_CNCL_DVSN_CD": "01",  # 01: 정정
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
            "QTY_ALL_ORD_YN": "N",
        }

        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                error_msg = data.get("msg1", "알 수 없는 오류")
                print(f"주문 정정 실패: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "order_no": order_no
                }

            output = data.get("output", {})

            return {
                "success": True,
                "new_order_no": output.get("ODNO", ""),
                "original_order_no": order_no,
                "quantity": quantity,
                "price": price,
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            print(f"주문 정정 요청 실패: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "order_no": order_no
            }

    def get_pending_orders(self) -> Optional[List[Dict]]:
        """
        미체결 주문 조회

        Returns:
            미체결 주문 리스트
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"

        tr_id = self.tr_ids["pending"]
        headers = self._get_headers(tr_id)
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0",
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                print(f"미체결 조회 오류: {data.get('msg1', '')}")
                return None

            output = data.get("output", [])

            pending_orders = []
            for item in output:
                pending_orders.append({
                    "order_no": item.get("odno", ""),
                    "stock_code": item.get("pdno", ""),
                    "stock_name": item.get("prdt_name", ""),
                    "side": "buy" if item.get("sll_buy_dvsn_cd") == "02" else "sell",
                    "order_qty": int(item.get("ord_qty", 0)),
                    "executed_qty": int(item.get("tot_ccld_qty", 0)),
                    "remaining_qty": int(item.get("ord_qty", 0)) - int(item.get("tot_ccld_qty", 0)),
                    "order_price": int(item.get("ord_unpr", 0)),
                    "order_time": item.get("ord_tmd", ""),
                })

            return pending_orders

        except requests.exceptions.RequestException as e:
            print(f"미체결 조회 실패: {str(e)}")
            return None

    def get_order_history(self, start_date: str = None, end_date: str = None) -> Optional[List[Dict]]:
        """
        체결 내역 조회 (연속조회 지원)

        Args:
            start_date: 조회 시작일 (YYYYMMDD)
            end_date: 조회 종료일 (YYYYMMDD)

        Returns:
            체결 내역 리스트
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        if not start_date:
            start_date = datetime.now().strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"

        # 모의/실전 TR_ID
        tr_id = "VTTC8001R" if self.is_virtual else "TTTC8001R"

        all_orders = []
        seen_order_nos = set()  # 중복 체크용
        ctx_area_fk100 = ""
        ctx_area_nk100 = ""
        tr_cont = ""  # 첫 요청은 빈 문자열
        max_pages = 10

        for page in range(max_pages):
            headers = self._get_headers(tr_id)
            # 연속조회 시 tr_cont 설정
            if page > 0:
                headers["tr_cont"] = "N"

            params = {
                "CANO": self.account_no,
                "ACNT_PRDT_CD": self.account_product_code,
                "INQR_STRT_DT": start_date,
                "INQR_END_DT": end_date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": ctx_area_fk100,
                "CTX_AREA_NK100": ctx_area_nk100,
            }

            try:
                res = requests.get(url, headers=headers, params=params, timeout=10)
                res.raise_for_status()
                data = res.json()

                if data.get("rt_cd") != "0":
                    print(f"체결 내역 조회 오류: {data.get('msg1', '')}")
                    break

                output = data.get("output1", [])

                for item in output:
                    order_no = item.get("odno", "")
                    # 중복 체크
                    if order_no in seen_order_nos:
                        continue
                    seen_order_nos.add(order_no)

                    all_orders.append({
                        "order_date": item.get("ord_dt", ""),
                        "order_time": item.get("ord_tmd", ""),
                        "order_no": order_no,
                        "stock_code": item.get("pdno", ""),
                        "stock_name": item.get("prdt_name", ""),
                        "side": "buy" if item.get("sll_buy_dvsn_cd") == "02" else "sell",
                        "order_qty": int(item.get("ord_qty", 0)),
                        "executed_qty": int(item.get("tot_ccld_qty", 0)),
                        "executed_price": int(float(item.get("avg_prvs", 0))),
                        "executed_amount": int(item.get("tot_ccld_amt", 0)),
                    })

                # 연속조회 키 업데이트
                ctx_area_fk100 = data.get("ctx_area_fk100", "").strip()
                ctx_area_nk100 = data.get("ctx_area_nk100", "").strip()
                tr_cont_resp = res.headers.get("tr_cont", "")

                # 더 이상 데이터가 없으면 종료
                # tr_cont가 "D" 또는 ""이면 마지막, "M" 또는 "F"이면 더 있음
                if not output or tr_cont_resp in ["D", ""] or not ctx_area_fk100:
                    break

                time.sleep(0.2)  # API 호출 간격

            except requests.exceptions.RequestException as e:
                print(f"체결 내역 조회 실패: {str(e)}")
                break

        return all_orders if all_orders else None

    def get_realized_profit(self, start_date: str = None, end_date: str = None) -> Optional[List[Dict]]:
        """
        기간별 실현손익 조회

        Args:
            start_date: 조회 시작일 (YYYYMMDD)
            end_date: 조회 종료일 (YYYYMMDD)

        Returns:
            종목별 실현손익 리스트
        """
        if not self.account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")

        if not start_date:
            start_date = datetime.now().strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-period-profit"

        # 모의투자는 지원 안함
        tr_id = "VTTC8715R" if self.is_virtual else "TTTC8715R"

        headers = self._get_headers(tr_id)
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "SORT_DVSN": "00",
            "PDNO": "",
            "INQR_STRT_DT": start_date,
            "INQR_END_DT": end_date,
            "CBLC_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") != "0":
                print(f"실현손익 조회 오류: {data.get('msg1', '')}")
                return None

            output = data.get("output1", [])
            results = []
            for item in output:
                results.append({
                    "stock_code": item.get("pdno", ""),
                    "stock_name": item.get("prdt_name", ""),
                    "sell_amount": int(item.get("sll_amt", 0)),
                    "buy_amount": int(item.get("buy_amt", 0)),
                    "realized_profit": int(item.get("rlzt_pfls", 0)),
                })

            return results

        except requests.exceptions.RequestException as e:
            print(f"실현손익 조회 실패: {str(e)}")
            return None


# 싱글톤 인스턴스
_kis_client: Optional[KISClient] = None
_kis_price_client: Optional[KISClient] = None  # 시세 조회 전용 (실전투자 URL 사용)


def get_kis_client() -> KISClient:
    """KIS 클라이언트 싱글톤 반환"""
    global _kis_client
    if _kis_client is None:
        _kis_client = KISClient()
    return _kis_client


def get_kis_client_for_prices() -> KISClient:
    """
    시세 조회 전용 KIS 클라이언트 반환 (실전투자 URL 사용)

    주의: 시세 조회는 모의투자/실전투자 상관없이 실전투자 URL을 사용해야 합니다.
    모의투자 URL로 시세 조회 시 일부 종목에서 500 에러가 발생합니다.
    """
    global _kis_price_client
    if _kis_price_client is None:
        _kis_price_client = KISClient(is_virtual=False)  # 실전투자 URL 사용
    return _kis_price_client
