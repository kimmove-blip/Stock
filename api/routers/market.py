"""
시장 지수 API 라우터
- 코스피/코스닥 실시간 지수
- pykrx 사용
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import asyncio

router = APIRouter()


class IndexData(BaseModel):
    """지수 데이터"""
    name: str
    code: str
    value: float
    change: float
    change_rate: float
    positive: bool
    volume: Optional[int] = None
    trading_value: Optional[int] = None  # 거래대금 (억원)


class MarketInfo(BaseModel):
    """시장 정보"""
    total_volume: Optional[str] = None  # 총 거래량
    total_value: Optional[str] = None   # 총 거래대금
    advancing: Optional[int] = None     # 상승 종목 수
    declining: Optional[int] = None     # 하락 종목 수
    unchanged: Optional[int] = None     # 보합 종목 수


class MarketResponse(BaseModel):
    """시장 응답"""
    indices: List[IndexData]
    market_info: MarketInfo
    updated_at: str
    market_status: str  # open, closed, pre-market


def get_market_status() -> str:
    """장 상태 확인"""
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    # 주말
    if weekday >= 5:
        return "closed"

    # 장전 (09:00 이전)
    if hour < 9:
        return "pre-market"

    # 장중 (09:00 ~ 15:30)
    if hour < 15 or (hour == 15 and minute <= 30):
        return "open"

    return "closed"


def format_number(num: float) -> str:
    """숫자 포맷팅"""
    if num >= 1_0000_0000_0000:  # 조
        return f"{num / 1_0000_0000_0000:.1f}조"
    elif num >= 1_0000_0000:  # 억
        return f"{num / 1_0000_0000:.1f}억"
    elif num >= 1_0000:  # 만
        return f"{num / 1_0000:.1f}만"
    return f"{num:,.0f}"


@router.get("", response_model=MarketResponse)
async def get_market_indices():
    """
    코스피/코스닥 실시간 지수 조회
    """
    try:
        from pykrx import stock

        # 오늘 날짜 (장 마감 전이면 전일 데이터)
        today = datetime.now()

        # 최근 거래일 찾기 (주말/공휴일 제외)
        for i in range(7):
            check_date = (today - timedelta(days=i)).strftime("%Y%m%d")
            try:
                kospi = stock.get_index_ohlcv(check_date, check_date, "1001")
                if not kospi.empty:
                    target_date = check_date
                    break
            except:
                continue
        else:
            raise HTTPException(status_code=500, detail="거래일 데이터를 찾을 수 없습니다")

        # 전일 데이터 (비교용)
        prev_date = None
        for i in range(1, 10):
            check_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
            try:
                prev_kospi = stock.get_index_ohlcv(check_date, check_date, "1001")
                if not prev_kospi.empty:
                    prev_date = check_date
                    break
            except:
                continue

        indices = []

        # 코스피 (1001)
        try:
            kospi = stock.get_index_ohlcv(target_date, target_date, "1001")
            if not kospi.empty:
                kospi_value = float(kospi.iloc[-1]['종가'])
                kospi_volume = int(kospi.iloc[-1]['거래량']) if '거래량' in kospi.columns else 0
                kospi_trading = int(kospi.iloc[-1]['거래대금']) if '거래대금' in kospi.columns else 0

                # 전일 대비
                kospi_change = 0
                kospi_rate = 0
                if prev_date:
                    prev_kospi = stock.get_index_ohlcv(prev_date, prev_date, "1001")
                    if not prev_kospi.empty:
                        prev_value = float(prev_kospi.iloc[-1]['종가'])
                        kospi_change = kospi_value - prev_value
                        kospi_rate = (kospi_change / prev_value) * 100

                indices.append(IndexData(
                    name="코스피",
                    code="1001",
                    value=round(kospi_value, 2),
                    change=round(kospi_change, 2),
                    change_rate=round(kospi_rate, 2),
                    positive=kospi_change >= 0,
                    volume=kospi_volume,
                    trading_value=kospi_trading // 100000000 if kospi_trading else None  # 억원
                ))
        except Exception as e:
            print(f"[Market] 코스피 조회 실패: {e}")

        # 코스닥 (2001)
        try:
            kosdaq = stock.get_index_ohlcv(target_date, target_date, "2001")
            if not kosdaq.empty:
                kosdaq_value = float(kosdaq.iloc[-1]['종가'])
                kosdaq_volume = int(kosdaq.iloc[-1]['거래량']) if '거래량' in kosdaq.columns else 0
                kosdaq_trading = int(kosdaq.iloc[-1]['거래대금']) if '거래대금' in kosdaq.columns else 0

                # 전일 대비
                kosdaq_change = 0
                kosdaq_rate = 0
                if prev_date:
                    prev_kosdaq = stock.get_index_ohlcv(prev_date, prev_date, "2001")
                    if not prev_kosdaq.empty:
                        prev_value = float(prev_kosdaq.iloc[-1]['종가'])
                        kosdaq_change = kosdaq_value - prev_value
                        kosdaq_rate = (kosdaq_change / prev_value) * 100

                indices.append(IndexData(
                    name="코스닥",
                    code="2001",
                    value=round(kosdaq_value, 2),
                    change=round(kosdaq_change, 2),
                    change_rate=round(kosdaq_rate, 2),
                    positive=kosdaq_change >= 0,
                    volume=kosdaq_volume,
                    trading_value=kosdaq_trading // 100000000 if kosdaq_trading else None
                ))
        except Exception as e:
            print(f"[Market] 코스닥 조회 실패: {e}")

        # 시장 정보 (등락 종목 수)
        market_info = MarketInfo()
        try:
            # 코스피 등락 현황
            kospi_stocks = stock.get_market_ohlcv(target_date, market="KOSPI")
            if not kospi_stocks.empty:
                kospi_stocks['변화'] = kospi_stocks['종가'] - kospi_stocks['시가']
                advancing = len(kospi_stocks[kospi_stocks['등락률'] > 0])
                declining = len(kospi_stocks[kospi_stocks['등락률'] < 0])
                unchanged = len(kospi_stocks[kospi_stocks['등락률'] == 0])

                total_volume = kospi_stocks['거래량'].sum()
                total_value = kospi_stocks['거래대금'].sum()

                market_info = MarketInfo(
                    total_volume=format_number(total_volume) + "주",
                    total_value=format_number(total_value),
                    advancing=advancing,
                    declining=declining,
                    unchanged=unchanged
                )
        except Exception as e:
            print(f"[Market] 시장 정보 조회 실패: {e}")

        if not indices:
            raise HTTPException(status_code=500, detail="지수 데이터를 가져올 수 없습니다")

        return MarketResponse(
            indices=indices,
            market_info=market_info,
            updated_at=datetime.now().isoformat(),
            market_status=get_market_status()
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Market Error] {e}")
        raise HTTPException(status_code=500, detail="시장 데이터 조회 실패")


@router.get("/kospi")
async def get_kospi_detail():
    """코스피 상세 정보"""
    result = await get_market_indices()
    kospi = next((i for i in result.indices if i.code == "1001"), None)
    if not kospi:
        raise HTTPException(status_code=404, detail="코스피 데이터 없음")
    return kospi


@router.get("/kosdaq")
async def get_kosdaq_detail():
    """코스닥 상세 정보"""
    result = await get_market_indices()
    kosdaq = next((i for i in result.indices if i.code == "2001"), None)
    if not kosdaq:
        raise HTTPException(status_code=404, detail="코스닥 데이터 없음")
    return kosdaq


# ========== 해외 지수 ==========

class GlobalIndexData(BaseModel):
    """해외 지수 데이터"""
    name: str
    symbol: str
    country: str
    value: float
    change: float
    change_rate: float
    positive: bool


class CurrencyData(BaseModel):
    """환율 데이터"""
    name: str
    symbol: str
    value: float
    change: float
    positive: bool


class GlobalMarketResponse(BaseModel):
    """해외 시장 응답"""
    indices: List[GlobalIndexData]
    currencies: List[CurrencyData]
    updated_at: str


@router.get("/global", response_model=GlobalMarketResponse)
async def get_global_markets():
    """
    해외 주요 지수 및 환율 조회
    - 미국: S&P500, NASDAQ, DOW
    - 아시아: 니케이225, 항셍
    - 환율: USD/KRW, EUR/KRW, JPY/KRW
    """
    try:
        import FinanceDataReader as fdr
        from datetime import datetime, timedelta

        indices = []
        currencies = []

        # 최근 거래일 (미국 기준)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)

        # 해외 지수 심볼 매핑
        global_indices = [
            ("S&P 500", "US500", "미국"),
            ("NASDAQ", "IXIC", "미국"),
            ("DOW", "DJI", "미국"),
            ("NIKKEI 225", "JP225", "일본"),
            ("Hang Seng", "HSI", "홍콩"),
        ]

        for name, symbol, country in global_indices:
            try:
                df = fdr.DataReader(symbol, start_date, end_date)
                if df is not None and len(df) >= 2:
                    current = float(df.iloc[-1]['Close'])
                    prev = float(df.iloc[-2]['Close'])
                    change = current - prev
                    change_rate = (change / prev) * 100

                    indices.append(GlobalIndexData(
                        name=name,
                        symbol=symbol,
                        country=country,
                        value=round(current, 2),
                        change=round(change, 2),
                        change_rate=round(change_rate, 2),
                        positive=change >= 0
                    ))
            except Exception as e:
                print(f"[Global] {name} 조회 실패: {e}")

        # 환율
        currency_list = [
            ("USD/KRW", "USD/KRW"),
            ("EUR/KRW", "EUR/KRW"),
            ("JPY/KRW", "JPY/KRW"),
        ]

        for name, symbol in currency_list:
            try:
                df = fdr.DataReader(symbol, start_date, end_date)
                if df is not None and len(df) >= 2:
                    current = float(df.iloc[-1]['Close'])
                    prev = float(df.iloc[-2]['Close'])
                    change = current - prev

                    currencies.append(CurrencyData(
                        name=name,
                        symbol=symbol,
                        value=round(current, 2),
                        change=round(change, 2),
                        positive=change >= 0
                    ))
            except Exception as e:
                print(f"[Global] {name} 환율 조회 실패: {e}")

        return GlobalMarketResponse(
            indices=indices,
            currencies=currencies,
            updated_at=datetime.now().isoformat()
        )

    except Exception as e:
        print(f"[Global Market Error] {e}")
        raise HTTPException(status_code=500, detail="해외 시장 데이터 조회 실패")
