"""
가치주 발굴 API 라우터
- 대형우량주 포함
- PER, PBR, 배당률 기반 가치주 선별
- pykrx 사용 (KIS API 대체)
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter()


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
            if not df.empty:
                return check_date
        except:
            continue
    return today.strftime("%Y%m%d")


@router.get("", response_model=ValueStocksResponse)
async def get_value_stocks(limit: int = 30):
    """
    가치주 목록 조회 - pykrx 사용
    """
    try:
        from pykrx import stock

        target_date = get_recent_trading_date()

        # 전체 시장 데이터 한번에 가져오기
        kospi_ohlcv = stock.get_market_ohlcv(target_date, market="KOSPI")
        kosdaq_ohlcv = stock.get_market_ohlcv(target_date, market="KOSDAQ")

        # PER, PBR, 배당률 데이터
        kospi_fund = stock.get_market_fundamental(target_date, market="KOSPI")
        kosdaq_fund = stock.get_market_fundamental(target_date, market="KOSDAQ")

        # 시가총액 데이터
        kospi_cap = stock.get_market_cap(target_date, market="KOSPI")
        kosdaq_cap = stock.get_market_cap(target_date, market="KOSDAQ")

        value_stocks = []

        for code in VALUE_STOCK_CODES:
            try:
                # KOSPI에서 찾기
                if code in kospi_ohlcv.index:
                    ohlcv = kospi_ohlcv.loc[code]
                    fund = kospi_fund.loc[code] if code in kospi_fund.index else None
                    cap = kospi_cap.loc[code] if code in kospi_cap.index else None
                    market = "KOSPI"
                # KOSDAQ에서 찾기
                elif code in kosdaq_ohlcv.index:
                    ohlcv = kosdaq_ohlcv.loc[code]
                    fund = kosdaq_fund.loc[code] if code in kosdaq_fund.index else None
                    cap = kosdaq_cap.loc[code] if code in kosdaq_cap.index else None
                    market = "KOSDAQ"
                else:
                    continue

                current_price = int(ohlcv['종가'])
                if current_price <= 0:
                    continue

                change_rate = float(ohlcv['등락률']) if '등락률' in ohlcv else 0

                # 펀더멘털 데이터
                per = float(fund['PER']) if fund is not None and 'PER' in fund and fund['PER'] > 0 else None
                pbr = float(fund['PBR']) if fund is not None and 'PBR' in fund and fund['PBR'] > 0 else None
                div_yield = float(fund['DIV']) if fund is not None and 'DIV' in fund else None

                # 시가총액 (억원)
                market_cap = int(cap['시가총액'] / 100000000) if cap is not None and '시가총액' in cap else None

                # 가치주 필터링 (PER, PBR 기준 완화)
                # PER: 0 < PER <= 30 또는 없음
                # PBR: 0 < PBR <= 5 또는 없음
                if per is not None and (per <= 0 or per > 30):
                    continue
                if pbr is not None and (pbr <= 0 or pbr > 5):
                    continue

                # 종목명 조회
                name = stock.get_market_ticker_name(code)

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

                value_stocks.append(ValueStock(
                    code=code,
                    name=name,
                    market=market,
                    current_price=current_price,
                    change_rate=round(change_rate, 2),
                    per=round(per, 2) if per else None,
                    pbr=round(pbr, 2) if pbr else None,
                    dividend_yield=round(div_yield, 2) if div_yield else None,
                    market_cap=market_cap,
                    score=min(score, 100),
                    tags=tags
                ))

            except Exception as e:
                print(f"가치주 조회 실패 [{code}]: {e}")
                continue

        # 점수 순 정렬
        value_stocks.sort(key=lambda x: x.score, reverse=True)

        if not value_stocks:
            raise HTTPException(status_code=500, detail="가치주 데이터를 가져올 수 없습니다. 잠시 후 다시 시도해주세요.")

        return ValueStocksResponse(
            items=value_stocks[:limit],
            generated_at=datetime.now().isoformat(),
            criteria={
                "per_max": 30,
                "pbr_max": 5,
                "source": "pykrx",
                "includes_large_cap": True,
                "date": target_date
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Value Stocks Error] {e}")
        raise HTTPException(status_code=500, detail="가치주 데이터 조회 실패")
