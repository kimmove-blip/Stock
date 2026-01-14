#!/usr/bin/env python3
"""
매일 장마감 후 실행: 가치주 스크리닝

전체 KOSPI/KOSDAQ 종목 대상으로:
- PER < 10
- PBR < 1.5
- 배당수익률 > 2%
조건을 만족하는 종목 발굴

사용법:
    python daily_value_stocks.py              # 기본 실행
    python daily_value_stocks.py --top 50     # 상위 50개만
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import time

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "output"


def get_naver_fundamental(code: str) -> dict:
    """네이버 금융에서 PER, PBR, 배당수익률 조회"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')

        result = {'per': None, 'pbr': None, 'div': None}

        # PER/PBR/배당률 테이블
        table = soup.find('table', {'class': 'per_table'})
        if table:
            tds = table.find_all('td')
            values = []
            for td in tds:
                em = td.find('em')
                if em:
                    val = em.get_text(strip=True)
                    try:
                        values.append(float(val.replace(',', '')))
                    except:
                        values.append(None)

            # 순서: PER, 추정PER, PBR, 배당수익률
            if len(values) >= 4:
                result['per'] = values[0] if values[0] and values[0] > 0 else None
                result['pbr'] = values[2] if values[2] and values[2] > 0 else None
                result['div'] = values[3] if values[3] and values[3] > 0 else None

        return result
    except Exception as e:
        return {'per': None, 'pbr': None, 'div': None}


def get_stock_price_info(code: str) -> dict:
    """네이버 금융에서 현재가, 등락률, 시가총액 조회"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')

        result = {'price': None, 'change_rate': None, 'market_cap': None, 'name': None}

        # 종목명
        title = soup.find('div', {'class': 'wrap_company'})
        if title:
            h2 = title.find('h2')
            if h2:
                result['name'] = h2.get_text(strip=True).split('\n')[0]

        # 현재가
        price_tag = soup.find('p', {'class': 'no_today'})
        if price_tag:
            span = price_tag.find('span', {'class': 'blind'})
            if span:
                try:
                    result['price'] = int(span.get_text().replace(',', ''))
                except:
                    pass

        # 등락률
        rate_tag = soup.find('p', {'class': 'no_exday'})
        if rate_tag:
            spans = rate_tag.find_all('span', {'class': 'blind'})
            if len(spans) >= 2:
                try:
                    rate_text = spans[1].get_text().replace('%', '').replace(',', '')
                    result['change_rate'] = float(rate_text)
                    # 하락인지 확인
                    if 'nv_down' in str(rate_tag) or 'ico_down' in str(rate_tag):
                        result['change_rate'] = -abs(result['change_rate'])
                except:
                    pass

        # 시가총액
        table = soup.find('table', {'class': 'no_info'})
        if table:
            tds = table.find_all('td')
            for td in tds:
                text = td.get_text(strip=True)
                if '조' in text or '억' in text:
                    try:
                        # 시가총액 파싱 (예: "1,234억" or "12조 3,456억")
                        text = text.replace(',', '').replace(' ', '')
                        if '조' in text:
                            parts = text.split('조')
                            jo = int(parts[0]) * 10000  # 억 단위로 변환
                            if '억' in parts[1]:
                                eok = int(parts[1].replace('억', ''))
                                result['market_cap'] = jo + eok
                            else:
                                result['market_cap'] = jo
                        elif '억' in text:
                            result['market_cap'] = int(text.replace('억', ''))
                        break
                    except:
                        pass

        return result
    except Exception as e:
        return {'price': None, 'change_rate': None, 'market_cap': None, 'name': None}


def analyze_stock(code: str) -> dict:
    """개별 종목 가치주 분석"""
    try:
        # 가격 정보 조회
        price_info = get_stock_price_info(code)
        if not price_info['price'] or price_info['price'] <= 0:
            return None

        # 펀더멘털 조회
        fund = get_naver_fundamental(code)

        # 가치주 조건 필터링
        per = fund['per']
        pbr = fund['pbr']
        div = fund['div']

        # 최소 조건: PER 또는 PBR 중 하나는 있어야 함
        if per is None and pbr is None:
            return None

        # PER 조건 (0 < PER <= 15)
        if per is not None and (per <= 0 or per > 15):
            return None

        # PBR 조건 (0 < PBR <= 1.5)
        if pbr is not None and (pbr <= 0 or pbr > 1.5):
            return None

        # 점수 계산 (기본 0점에서 시작, 최대 100점)
        score = 0
        tags = []

        # PER 점수 (최대 35점) - 낮을수록 좋음
        if per is not None:
            if per <= 3:
                score += 35
                tags.append("초저PER")
            elif per <= 5:
                score += 30
                tags.append("저PER")
            elif per <= 7:
                score += 25
            elif per <= 10:
                score += 20
            elif per <= 15:
                score += 10

        # PBR 점수 (최대 35점) - 낮을수록 좋음
        if pbr is not None:
            if pbr <= 0.3:
                score += 35
                tags.append("초저PBR")
            elif pbr <= 0.5:
                score += 30
                tags.append("저PBR")
            elif pbr <= 0.7:
                score += 25
            elif pbr <= 1.0:
                score += 20
            elif pbr <= 1.5:
                score += 10

        # 배당률 점수 (최대 30점)
        if div is not None and div > 0:
            if div >= 7:
                score += 30
                tags.append("초고배당")
            elif div >= 5:
                score += 25
                tags.append("고배당")
            elif div >= 4:
                score += 20
                tags.append("배당주")
            elif div >= 3:
                score += 15
                tags.append("배당주")
            elif div >= 2:
                score += 10

        # 시가총액 분류
        market_cap = price_info.get('market_cap')
        if market_cap:
            if market_cap >= 100000:  # 10조 이상
                tags.append("대형주")
            elif market_cap >= 10000:  # 1조 이상
                tags.append("중형주")
            elif market_cap >= 1000:  # 1000억 이상
                tags.append("소형주")

        # 최소 점수 필터 (30점 미만은 제외)
        if score < 30:
            return None

        return {
            "code": code,
            "name": price_info.get('name', code),
            "current_price": price_info['price'],
            "change_rate": round(price_info.get('change_rate') or 0, 2),
            "per": round(per, 2) if per else None,
            "pbr": round(pbr, 2) if pbr else None,
            "dividend_yield": round(div, 2) if div else None,
            "market_cap": market_cap,
            "score": min(score, 100),
            "tags": tags
        }

    except Exception as e:
        return None


def get_all_stock_codes():
    """전체 KOSPI/KOSDAQ 종목 코드 조회"""
    try:
        import FinanceDataReader as fdr

        # KOSPI + KOSDAQ 종목 조회
        kospi = fdr.StockListing('KOSPI')
        kosdaq = fdr.StockListing('KOSDAQ')

        codes = []

        # KOSPI
        for _, row in kospi.iterrows():
            code = str(row.get('Code', row.get('Symbol', ''))).zfill(6)
            if len(code) == 6 and code.isdigit():
                codes.append(('KOSPI', code))

        # KOSDAQ
        for _, row in kosdaq.iterrows():
            code = str(row.get('Code', row.get('Symbol', ''))).zfill(6)
            if len(code) == 6 and code.isdigit():
                codes.append(('KOSDAQ', code))

        return codes

    except Exception as e:
        print(f"[오류] 종목 목록 조회 실패: {e}")
        return []


def run_value_screening(top_n: int = 100, max_workers: int = 10):
    """가치주 스크리닝 실행"""
    print("\n" + "=" * 70)
    print(f"  가치주 스크리닝")
    print(f"  실행시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  조건: PER <= 15, PBR <= 1.5")
    print("=" * 70)

    # 전체 종목 코드 조회
    print("\n[1/3] 종목 목록 조회 중...")
    all_codes = get_all_stock_codes()
    print(f"      총 {len(all_codes)}개 종목")

    # 병렬 분석
    print(f"\n[2/3] 가치주 분석 중... (병렬 {max_workers}개)")
    value_stocks = []
    processed = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_stock, code): (market, code)
                   for market, code in all_codes}

        for future in as_completed(futures):
            processed += 1
            market, code = futures[future]

            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed
                remaining = (len(all_codes) - processed) / rate
                print(f"      {processed}/{len(all_codes)} 완료 ({rate:.1f}/초, 남은시간: {remaining/60:.1f}분)")

            try:
                result = future.result()
                if result:
                    result['market'] = market
                    value_stocks.append(result)
            except Exception as e:
                pass

    # 점수순 정렬
    value_stocks.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n[3/3] 결과: {len(value_stocks)}개 가치주 발굴")

    return value_stocks[:top_n]


def save_results(results: list, top_n: int = 100):
    """결과 저장"""
    OUTPUT_DIR.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")

    # JSON 저장
    json_path = OUTPUT_DIR / f"value_stocks_{today}.json"
    json_data = {
        "generated_at": datetime.now().isoformat(),
        "criteria": {
            "per_max": 15,
            "pbr_max": 1.5,
            "total_scanned": "all",
        },
        "count": len(results),
        "stocks": results
    }

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"\n[저장] {json_path}")
    print(f"       {len(results)}개 종목 저장 완료")

    return json_path


def main():
    parser = argparse.ArgumentParser(description="가치주 스크리닝")
    parser.add_argument("--top", type=int, default=100, help="상위 N개 (기본: 100)")
    parser.add_argument("--workers", type=int, default=10, help="병렬 처리 수 (기본: 10)")
    args = parser.parse_args()

    # 스크리닝 실행
    results = run_value_screening(top_n=args.top, max_workers=args.workers)

    if results:
        # 결과 저장
        save_results(results, top_n=args.top)

        # 상위 10개 출력
        print("\n" + "=" * 70)
        print("  상위 10개 가치주")
        print("=" * 70)
        for i, stock in enumerate(results[:10], 1):
            tags = " ".join(stock['tags'][:3])
            print(f"  {i:2}. {stock['name'][:10]:<10} ({stock['code']}) "
                  f"PER:{stock['per'] or '-':>5} PBR:{stock['pbr'] or '-':>4} "
                  f"배당:{stock['dividend_yield'] or '-':>4}% [{tags}]")

        print("\n완료!")
    else:
        print("\n[오류] 가치주를 찾지 못했습니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
