"""
시장 지수 API 라우터
- 코스피/코스닥 실시간 지수
- pykrx 사용
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Tuple, Any
from datetime import datetime, timedelta
import asyncio
import time

router = APIRouter()

# 시장 지수 캐시 (5분 TTL)
_market_cache: Tuple[Any, float] = (None, 0)
_global_market_cache: Tuple[Any, float] = (None, 0)
_MARKET_CACHE_TTL = 300  # 5분


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
    코스피/코스닥 실시간 지수 조회 (5분 캐싱 + FinanceDataReader 사용)
    """
    global _market_cache

    # 캐시 확인
    cached_data, cached_time = _market_cache
    if cached_data and time.time() - cached_time < _MARKET_CACHE_TTL:
        return cached_data

    try:
        import FinanceDataReader as fdr

        today = datetime.now()
        start_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        indices = []

        # 코스피 (KS11)
        try:
            df = fdr.DataReader('KS11', start_date, end_date)
            if df is not None and len(df) >= 2:
                current = df.iloc[-1]
                prev = df.iloc[-2]

                kospi_value = float(current['Close'])
                prev_value = float(prev['Close'])
                kospi_change = kospi_value - prev_value
                kospi_rate = (kospi_change / prev_value) * 100

                # 거래대금 (Amount 컬럼)
                trading_value = int(current['Amount']) if 'Amount' in df.columns else 0

                indices.append(IndexData(
                    name="코스피",
                    code="KS11",
                    value=round(kospi_value, 2),
                    change=round(kospi_change, 2),
                    change_rate=round(kospi_rate, 2),
                    positive=kospi_change >= 0,
                    volume=int(current['Volume']) if 'Volume' in df.columns else None,
                    trading_value=trading_value // 100000000 if trading_value else None
                ))
        except Exception as e:
            print(f"[Market] 코스피 조회 실패: {e}")

        # 코스닥 (KQ11)
        try:
            df = fdr.DataReader('KQ11', start_date, end_date)
            if df is not None and len(df) >= 2:
                current = df.iloc[-1]
                prev = df.iloc[-2]

                kosdaq_value = float(current['Close'])
                prev_value = float(prev['Close'])
                kosdaq_change = kosdaq_value - prev_value
                kosdaq_rate = (kosdaq_change / prev_value) * 100

                trading_value = int(current['Amount']) if 'Amount' in df.columns else 0

                indices.append(IndexData(
                    name="코스닥",
                    code="KQ11",
                    value=round(kosdaq_value, 2),
                    change=round(kosdaq_change, 2),
                    change_rate=round(kosdaq_rate, 2),
                    positive=kosdaq_change >= 0,
                    volume=int(current['Volume']) if 'Volume' in df.columns else None,
                    trading_value=trading_value // 100000000 if trading_value else None
                ))
        except Exception as e:
            print(f"[Market] 코스닥 조회 실패: {e}")

        # 시장 정보 (기본값)
        market_info = MarketInfo()

        if not indices:
            raise HTTPException(status_code=500, detail="지수 데이터를 가져올 수 없습니다")

        result = MarketResponse(
            indices=indices,
            market_info=market_info,
            updated_at=datetime.now().isoformat(),
            market_status=get_market_status()
        )

        # 캐시 저장
        _market_cache = (result, time.time())
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Market Error] {e}")
        raise HTTPException(status_code=500, detail="시장 데이터 조회 실패")


@router.get("/kospi")
async def get_kospi_detail():
    """코스피 상세 정보"""
    result = await get_market_indices()
    kospi = next((i for i in result.indices if i.code == "KS11"), None)
    if not kospi:
        raise HTTPException(status_code=404, detail="코스피 데이터 없음")
    return kospi


@router.get("/kosdaq")
async def get_kosdaq_detail():
    """코스닥 상세 정보"""
    result = await get_market_indices()
    kosdaq = next((i for i in result.indices if i.code == "KQ11"), None)
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
    해외 주요 지수 및 환율 조회 (5분 캐싱)
    - 미국: S&P500, NASDAQ, DOW
    - 아시아: 니케이225, 항셍
    - 환율: USD/KRW, EUR/KRW, JPY/KRW
    """
    global _global_market_cache
    import math

    # 캐시 확인
    cached_data, cached_time = _global_market_cache
    if cached_data and time.time() - cached_time < _MARKET_CACHE_TTL:
        return cached_data

    def safe_float(val, default=0.0):
        """NaN, inf 처리"""
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return default
            return f
        except:
            return default

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
                    current = safe_float(df.iloc[-1]['Close'])
                    prev = safe_float(df.iloc[-2]['Close'])

                    if current == 0 or prev == 0:
                        continue

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
                    current = safe_float(df.iloc[-1]['Close'])
                    prev = safe_float(df.iloc[-2]['Close'])

                    if current == 0 or prev == 0:
                        continue

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

        result = GlobalMarketResponse(
            indices=indices,
            currencies=currencies,
            updated_at=datetime.now().isoformat()
        )

        # 캐시 저장
        _global_market_cache = (result, time.time())
        return result

    except Exception as e:
        print(f"[Global Market Error] {e}")
        raise HTTPException(status_code=500, detail="해외 시장 데이터 조회 실패")
