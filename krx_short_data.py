"""
KRX 공매도/대차잔고 조회 모듈

데이터 소스:
- KRX 정보데이터시스템 (data.krx.co.kr)
- 네이버 금융 공매도 정보

데이터:
- short_volume: 공매도 거래량
- short_ratio: 공매도 비중 (%)
- balance: 대차잔고 (주)
- balance_change: 대차잔고 증감
- balance_change_pct: 대차잔고 증감률 (%)
"""

import requests
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import time


# API 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
REQUEST_TIMEOUT = 10  # 초


def get_short_data_naver(stock_code: str, days: int = 10) -> Optional[Dict]:
    """
    네이버 금융에서 공매도 정보 조회

    Args:
        stock_code: 종목코드 (6자리)
        days: 조회할 일수 (기본 10일)

    Returns:
        {
            'short_ratio': 최근 공매도 비중 (%),
            'short_volume': 최근 공매도 거래량,
            'balance': 대차잔고,
            'balance_change_pct': 대차잔고 변동률 (%),
            'daily': 일별 데이터
        }
    """
    try:
        # 네이버 금융 공매도 API (비공식)
        url = f"https://m.stock.naver.com/api/stock/{stock_code}/short-sale"
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            return None

        data = response.json()

        if not data:
            return None

        # 최근 데이터 추출
        recent_data = data[:days] if isinstance(data, list) else []

        if not recent_data:
            return None

        # 최신 데이터
        latest = recent_data[0] if recent_data else {}
        oldest = recent_data[-1] if len(recent_data) > 1 else latest

        # 공매도 비중
        short_ratio = float(latest.get('shortSellingRatio', 0))

        # 공매도 거래량
        short_volume = int(latest.get('shortSellingQuantity', 0))

        # 대차잔고 (주)
        balance = int(latest.get('lendingBalance', 0))
        balance_oldest = int(oldest.get('lendingBalance', 0))

        # 대차잔고 변동률
        balance_change_pct = 0
        if balance_oldest > 0:
            balance_change_pct = (balance - balance_oldest) / balance_oldest * 100

        # 일별 데이터
        daily = []
        for d in recent_data:
            daily.append({
                'date': d.get('localDate', ''),
                'short_volume': int(d.get('shortSellingQuantity', 0)),
                'short_ratio': float(d.get('shortSellingRatio', 0)),
                'balance': int(d.get('lendingBalance', 0)),
            })

        return {
            'short_ratio': short_ratio,
            'short_volume': short_volume,
            'balance': balance,
            'balance_change_pct': balance_change_pct,
            'daily': daily,
        }

    except Exception as e:
        return None


def get_short_data_krx(stock_code: str, days: int = 10) -> Optional[Dict]:
    """
    KRX에서 공매도 정보 조회 (백업용)

    KRX 정보데이터시스템 API 사용
    - 공매도 종합 현황
    - 대차거래 현황

    Args:
        stock_code: 종목코드 (6자리)
        days: 조회할 일수

    Returns:
        공매도 정보 딕셔너리
    """
    try:
        # KRX API 호출
        # 주의: KRX API는 별도 인증 필요할 수 있음
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y%m%d')

        # KRX 공매도 종합정보 API
        url = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

        params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT05601",
            "locale": "ko_KR",
            "tboxisuCd_finder_srtpdsrt": f"{stock_code}/",
            "isuCd": f"KR7{stock_code}000",
            "isuCd2": f"KR7{stock_code}000",
            "strtDd": start_date,
            "endDd": end_date,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
        }

        response = requests.get(url, params=params, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
        }, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            return None

        data = response.json()
        output = data.get('OutBlock_1', [])

        if not output:
            return None

        # 데이터 파싱
        daily = []
        for row in output[:days]:
            daily.append({
                'date': row.get('TRD_DD', ''),
                'short_volume': int(row.get('CVSRTSELL_TRDVOL', '0').replace(',', '')),
                'short_ratio': float(row.get('CVSRTSELL_TRDVOL_RT', '0').replace(',', '')),
                'balance': 0,  # 대차잔고는 별도 API 필요
            })

        if not daily:
            return None

        latest = daily[0]
        oldest = daily[-1] if len(daily) > 1 else latest

        return {
            'short_ratio': latest['short_ratio'],
            'short_volume': latest['short_volume'],
            'balance': 0,
            'balance_change_pct': 0,
            'daily': daily,
        }

    except Exception as e:
        return None


def get_short_data(stock_code: str, days: int = 10) -> Optional[Dict]:
    """
    공매도 정보 조회 (네이버 우선, KRX 백업)

    Args:
        stock_code: 종목코드 (6자리)
        days: 조회할 일수

    Returns:
        {
            'short_ratio': 공매도 비중 (%),
            'short_volume': 공매도 거래량,
            'balance': 대차잔고,
            'balance_change_pct': 대차잔고 변동률 (%),
            'daily': 일별 데이터
        }
    """
    # 네이버 금융 우선
    result = get_short_data_naver(stock_code, days)

    if result:
        return result

    # KRX 백업
    return get_short_data_krx(stock_code, days)


def analyze_short_covering_risk(stock_code: str, days: int = 10) -> Dict:
    """
    숏커버링 위험도 분석

    Args:
        stock_code: 종목코드
        days: 분석 기간

    Returns:
        {
            'risk_level': 'high' | 'medium' | 'low' | 'none',
            'short_ratio': 공매도 비중,
            'balance_change_pct': 대차잔고 변동률,
            'signals': 감지된 신호,
        }
    """
    result = {
        'risk_level': 'none',
        'short_ratio': 0,
        'balance_change_pct': 0,
        'signals': [],
    }

    short_data = get_short_data(stock_code, days)

    if not short_data:
        return result

    short_ratio = short_data.get('short_ratio', 0)
    balance_change = short_data.get('balance_change_pct', 0)

    result['short_ratio'] = short_ratio
    result['balance_change_pct'] = balance_change

    # 위험도 분석

    # 1. 공매도 비중 5% 이상 + 대차잔고 20% 이상 급감 = 숏스퀴즈 위험
    if short_ratio >= 5 and balance_change <= -20:
        result['risk_level'] = 'high'
        result['signals'].append('SHORT_SQUEEZE_RISK')

    # 2. 대차잔고 30% 이상 급감 = 숏커버링 진행
    elif balance_change <= -30:
        result['risk_level'] = 'high'
        result['signals'].append('MASSIVE_SHORT_COVERING')

    # 3. 대차잔고 20% 이상 급감 = 숏커버링 가능성
    elif balance_change <= -20:
        result['risk_level'] = 'medium'
        result['signals'].append('SHORT_COVERING_POSSIBLE')

    # 4. 대차잔고 10% 이상 급감 = 주의
    elif balance_change <= -10:
        result['risk_level'] = 'low'
        result['signals'].append('SHORT_REDUCTION')

    # 5. 공매도 비중 급등 = 역방향 신호
    if short_ratio >= 10:
        result['signals'].append('HIGH_SHORT_RATIO')

    return result


def get_short_data_batch(stock_codes: List[str], days: int = 10, max_workers: int = 5) -> Dict[str, Dict]:
    """
    여러 종목의 공매도 정보 일괄 조회

    Args:
        stock_codes: 종목코드 리스트
        days: 조회할 일수
        max_workers: 병렬 처리 워커 수

    Returns:
        {종목코드: 공매도정보} 딕셔너리
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(get_short_data, code, days): code
            for code in stock_codes
        }

        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                result = future.result()
                if result:
                    results[code] = result
            except Exception:
                pass

            # Rate limiting
            time.sleep(0.1)

    return results


# 테스트
if __name__ == "__main__":
    print("=== 공매도 정보 조회 테스트 ===\n")

    # 테스트 종목
    test_stocks = ['005930', '000660', '035720']

    for code in test_stocks:
        print(f"\n--- {code} ---")

        # 공매도 정보 조회
        short_data = get_short_data(code, days=10)

        if short_data:
            print(f"공매도 비중: {short_data['short_ratio']:.2f}%")
            print(f"공매도 거래량: {short_data['short_volume']:,}")
            print(f"대차잔고: {short_data['balance']:,}")
            print(f"대차잔고 변동률: {short_data['balance_change_pct']:.2f}%")

            # 숏커버링 위험도
            risk = analyze_short_covering_risk(code)
            print(f"숏커버링 위험도: {risk['risk_level']}")
            if risk['signals']:
                print(f"신호: {', '.join(risk['signals'])}")
        else:
            print("데이터 조회 실패")

    # 일괄 조회 테스트
    print("\n=== 일괄 조회 테스트 ===")
    start = time.time()
    batch_results = get_short_data_batch(test_stocks)
    elapsed = time.time() - start
    print(f"조회 완료: {len(batch_results)}개 ({elapsed:.2f}초)")
