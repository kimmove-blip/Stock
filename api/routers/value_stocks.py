"""
가치주 발굴 API 라우터
- 대형우량주 포함
- PER, PBR, 배당률 기반 가치주 선별
- pykrx 사용 (KIS API 대체)
- 하루 단위 캐싱
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

router = APIRouter()


def get_naver_fundamental(code: str) -> dict:
    """네이버 금융에서 PER, PBR 조회"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')

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
            if len(values) >= 3:
                return {
                    'per': values[0] if values[0] and values[0] > 0 else None,
                    'pbr': values[2] if values[2] and values[2] > 0 else None,
                    'div': values[3] if len(values) > 3 and values[3] else None
                }
        return {'per': None, 'pbr': None, 'div': None}
    except Exception as e:
        print(f"[가치주] 네이버 펀더멘털 조회 실패 [{code}]: {e}")
        return {'per': None, 'pbr': None, 'div': None}

# 캐시 저장소
_cache = {
    "data": None,
    "date": None
}


class ValueStock(BaseModel):
    """가치주 모델"""
    code: str
    name: str
    market: Optional[str] = None
    current_price: int
    change_rate: float
    per: Optional[float] = None
    pbr: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[int] = None  # 억원
    score: int
    tags: List[str] = []


class ValueStocksResponse(BaseModel):
    """가치주 목록 응답"""
    items: List[ValueStock]
    generated_at: str
    criteria: dict


# 대표 우량주 목록 (시가총액 상위 + 가치주 후보)
VALUE_STOCK_CODES = [
    "005930", "000660", "005380", "005490", "035420",
    "000270", "051910", "006400", "035720", "028260",
    "105560", "055550", "086790", "316140", "017670",
    "030200", "032830", "003550", "066570", "034730",
    "015760", "096770", "009150", "018260", "000810",
    "033780", "003490", "036570", "011170", "010130",
    "004020", "000720", "003410", "010950", "024110",
    "078930", "036460", "047050", "010140", "009540",
]


def get_recent_trading_date():
    """최근 거래일 반환"""
    from pykrx import stock
    today = datetime.now()

    for i in range(7):
        check_date = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = stock.get_market_ohlcv(check_date, market="KOSPI")
            # 데이터가 있고 필수 컬럼이 있는지 확인
            if not df.empty and '종가' in df.columns:
                return check_date
        except:
            continue
    return (today - timedelta(days=1)).strftime("%Y%m%d")


def fetch_value_stocks_data():
    """가치주 데이터 조회 (실제 API 호출) - 개별 종목 조회 방식"""
    from pykrx import stock

    today = datetime.now()
    # 최근 5일 범위로 조회 (개별 종목용)
    start_date = (today - timedelta(days=7)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    value_stocks = []

    for code in VALUE_STOCK_CODES:
        try:
            # 개별 종목 OHLCV 조회
            ohlcv_df = stock.get_market_ohlcv(start_date, end_date, code)
            if ohlcv_df.empty:
                continue

            # 최신 데이터 사용
            ohlcv = ohlcv_df.iloc[-1]
            target_date = ohlcv_df.index[-1].strftime("%Y%m%d")

            current_price = int(ohlcv['종가'])
            if current_price <= 0:
                continue

            change_rate = float(ohlcv['등락률']) if '등락률' in ohlcv else 0

            # 종목명 조회
            name = stock.get_market_ticker_name(code)

            # 펀더멘털 데이터 (네이버 금융에서 조회)
            fund_data = get_naver_fundamental(code)
            per = fund_data['per']
            pbr = fund_data['pbr']
            div_yield = fund_data['div']

            # 시가총액 조회 (pykrx가 안되면 None)
            market_cap = None
            try:
                cap_df = stock.get_market_cap(start_date, end_date, code)
                if not cap_df.empty and '시가총액' in cap_df.columns:
                    cap = cap_df.iloc[-1]
                    market_cap = int(cap['시가총액'] / 100000000)
            except:
                pass

            # 시장 구분
            market = "KOSPI"  # 기본값

            # 가치주 필터링 (PER, PBR 기준 완화)
            if per is not None and (per <= 0 or per > 30):
                continue
            if pbr is not None and (pbr <= 0 or pbr > 5):
                continue

            # 점수 계산
            score = 50
            tags = []

            # PER 점수
            if per is not None:
                if per <= 5:
                    score += 25
                    tags.append("초저PER")
                elif per <= 8:
                    score += 20
                    tags.append("저PER")
                elif per <= 12:
                    score += 10
                    tags.append("적정PER")

            # PBR 점수
            if pbr is not None:
                if pbr <= 0.5:
                    score += 25
                    tags.append("초저PBR")
                elif pbr <= 1:
                    score += 20
                    tags.append("저PBR")
                elif pbr <= 1.5:
                    score += 10
                    tags.append("적정PBR")

            # 배당률 점수
            if div_yield is not None and div_yield > 0:
                if div_yield >= 5:
                    score += 15
                    tags.append("고배당")
                elif div_yield >= 3:
                    score += 10
                    tags.append("배당주")

            # 대형주 가산점
            if market_cap:
                if market_cap >= 100000:  # 10조 이상
                    score += 10
                    tags.append("대형주")
                elif market_cap >= 10000:  # 1조 이상
                    score += 5
                    tags.append("중형주")

            value_stocks.append({
                "code": code,
                "name": name,
                "market": market,
                "current_price": current_price,
                "change_rate": round(change_rate, 2),
                "per": round(per, 2) if per else None,
                "pbr": round(pbr, 2) if pbr else None,
                "dividend_yield": round(div_yield, 2) if div_yield else None,
                "market_cap": market_cap,
                "score": min(score, 100),
                "tags": tags
            })

        except Exception as e:
            print(f"가치주 조회 실패 [{code}]: {e}")
            continue

    # 점수 순 정렬
    value_stocks.sort(key=lambda x: x["score"], reverse=True)

    return {
        "items": value_stocks,
        "generated_at": datetime.now().isoformat(),
        "target_date": end_date
    }


@router.get("", response_model=ValueStocksResponse)
async def get_value_stocks(limit: int = 30, refresh: bool = False):
    """
    가치주 목록 조회 - 하루 단위 캐싱

    - refresh=true: 캐시 무시하고 새로 조회
    """
    global _cache

    today = datetime.now().strftime("%Y%m%d")

    # 캐시가 있고, 오늘 날짜이고, refresh가 아니면 캐시 반환
    if _cache["data"] and _cache["date"] == today and not refresh:
        cached = _cache["data"]
        return ValueStocksResponse(
            items=[ValueStock(**item) for item in cached["items"][:limit]],
            generated_at=cached["generated_at"],
            criteria={
                "per_max": 30,
                "pbr_max": 5,
                "source": "pykrx (캐시)",
                "includes_large_cap": True,
                "date": cached["target_date"]
            }
        )

    # 새로 조회
    try:
        print(f"[가치주] 새로 데이터 조회 중... (날짜: {today})")
        data = fetch_value_stocks_data()

        if not data["items"]:
            raise HTTPException(status_code=500, detail="가치주 데이터를 가져올 수 없습니다. 잠시 후 다시 시도해주세요.")

        # 캐시 저장
        _cache["data"] = data
        _cache["date"] = today

        print(f"[가치주] 데이터 캐싱 완료 - {len(data['items'])}개 종목")

        return ValueStocksResponse(
            items=[ValueStock(**item) for item in data["items"][:limit]],
            generated_at=data["generated_at"],
            criteria={
                "per_max": 30,
                "pbr_max": 5,
                "source": "pykrx",
                "includes_large_cap": True,
                "date": data["target_date"]
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Value Stocks Error] {e}")

        # 에러 발생 시 이전 캐시가 있으면 그것을 반환
        if _cache["data"]:
            print("[가치주] 에러 발생, 이전 캐시 반환")
            cached = _cache["data"]
            return ValueStocksResponse(
                items=[ValueStock(**item) for item in cached["items"][:limit]],
                generated_at=cached["generated_at"],
                criteria={
                    "per_max": 30,
                    "pbr_max": 5,
                    "source": "pykrx (이전 캐시)",
                    "includes_large_cap": True,
                    "date": cached["target_date"]
                }
            )

        raise HTTPException(status_code=500, detail="가치주 데이터 조회 실패")


@router.get("/refresh")
async def refresh_value_stocks():
    """가치주 데이터 강제 새로고침"""
    return await get_value_stocks(refresh=True)
