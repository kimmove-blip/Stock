import os
import requests
import pandas as pd
from dotenv import load_dotenv

# 1. 환경 변수 로드 (.env 파일에서 API 키 가져오기)
load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

class FundamentalAnalyst:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://opendart.fss.or.kr/api"

    def get_financials(self, corp_code, year, reprt_code="11011"):
        """
        DART 단일회사 주요계정 API 호출
        reprt_code: 11011(사업보고서), 11012(반기), 11013(1분기), 11014(3분기)
        """
        url = f"{self.base_url}/fnlttSinglAcnt.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": reprt_code
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            if data['status'] != '000':
                print(f"Error: {data.get('message')}")
                return None
            
            # 데이터를 사용하기 쉽게 DataFrame으로 변환
            df = pd.DataFrame(data['list'])
            
            # 숫자 데이터 전처리 (콤마 제거 및 숫자 변환)
            df['thstrm_amount'] = df['thstrm_amount'].str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            
            return df
            
        except Exception as e:
            print(f"API 요청 중 에러 발생: {e}")
            return None

    def analyze(self, df):
        """재무 데이터로 펀더멘털 점수 산출"""
        if df is None or df.empty:
            return 0, ["데이터 없음"]

        # 필요한 계정 과목 추출 (연결 재무제표 기준)
        # fs_div: CFS(연결), OFS(개별) -> 보통 연결을 봅니다.
        df = df[df['fs_div'] == 'CFS']

        def get_value(account_nm):
            # 계정명으로 값 찾기 (여러 개일 경우 첫 번째 것)
            row = df[df['account_nm'] == account_nm]
            if not row.empty:
                return row.iloc[0]['thstrm_amount']
            return 0

        # 데이터 추출
        current_assets = get_value('유동자산')
        current_liab = get_value('유동부채')
        total_assets = get_value('자산총계')
        total_liab = get_value('부채총계')
        total_equity = get_value('자본총계')
        revenue = get_value('매출액')
        op_income = get_value('영업이익')

        score = 0
        reasons = []
        details = {} # 상세 수치 저장

        # 1. 유동비율 (유동자산 / 유동부채 * 100)
        # 단기 상환 능력 평가
        if current_liab > 0:
            liquidity_ratio = (current_assets / current_liab) * 100
            details['유동비율'] = f"{liquidity_ratio:.2f}%"

            if liquidity_ratio >= 200:
                score += 5
                reasons.append("[+] 유동비율 우수 (200% 이상)")
            elif liquidity_ratio < 100:
                reasons.append("[!] 유동비율 위험 (100% 미만)")

        # 2. 부채비율 (부채총계 / 자본총계 * 100)
        # 자본 구조 안정성 평가
        if total_equity > 0:
            debt_ratio = (total_liab / total_equity) * 100
            details['부채비율'] = f"{debt_ratio:.2f}%"

            if debt_ratio < 100:
                score += 5
                reasons.append("[+] 부채비율 건전 (100% 미만)")
            elif debt_ratio > 200:
                score -= 5
                reasons.append("[!] 부채비율 과다 (200% 초과)")

        # 3. 영업이익률 (영업이익 / 매출액 * 100)
        # 비즈니스 수익성 평가
        if revenue > 0:
            op_margin = (op_income / revenue) * 100
            details['영업이익률'] = f"{op_margin:.2f}%"

            if op_margin > 0:
                score += 10
                reasons.append(f"[+] 흑자 경영 (이익률 {op_margin:.1f}%)")
            else:
                score -= 10
                reasons.append("[-] 영업 적자 상태")

        return score, reasons, details

# --- 실행부 ---
if __name__ == "__main__":
    analyst = FundamentalAnalyst(DART_API_KEY)
    
    # 주의: DART API는 '종목코드(005930)'가 아닌 8자리 '고유번호'를 사용합니다.
    # 삼성전자 고유번호: 00126380
    target_corp_code = "00126380" 
    target_year = "2023" # 최신 사업보고서 기준
    
    print(f"[SEARCH] 삼성전자({target_year}) 펀더멘털 분석 시작...")
    
    financial_data = analyst.get_financials(target_corp_code, target_year)
    
    if financial_data is not None:
        final_score, diag_reasons, diag_details = analyst.analyze(financial_data)
        
        print("\n" + "="*30)
        print(f"[REPORT] 분석 결과 리포트 (점수: {final_score}/20)")
        print("="*30)
        print("[상세 지표]")
        for k, v in diag_details.items():
            print(f"- {k}: {v}")
        
        print("\n[진단 코멘트]")
        for reason in diag_reasons:
            print(reason)
    else:
        print("데이터를 가져오지 못했습니다.")