"""
실시간 시세 API 라우터
한국투자증권 API를 통한 실시간 주가 조회
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Tuple, Any
from pydantic import BaseModel
from datetime import datetime
import time

router = APIRouter()

# 실시간 시세 캐시 (30초 TTL)
_realtime_cache: Dict[str, Tuple[Any, float]] = {}
_REALTIME_CACHE_TTL = 30  # 30초
_top100_cache: Tuple[Any, float] = (None, 0)  # TOP100 전체 캐시


def get_cached_realtime(code: str) -> Optional[Dict]:
    """캐시된 실시간 시세 조회"""
    if code in _realtime_cache:
        data, timestamp = _realtime_cache[code]
        if time.time() - timestamp < _REALTIME_CACHE_TTL:
            return data
        del _realtime_cache[code]
    return None


def set_realtime_cache(code: str, data: Dict):
    """실시간 시세 캐시 저장"""
    _realtime_cache[code] = (data, time.time())
    # 캐시 크기 제한 (200개)
    if len(_realtime_cache) > 200:
        # 가장 오래된 항목 삭제
        oldest = min(_realtime_cache.items(), key=lambda x: x[1][1])
        del _realtime_cache[oldest[0]]


class RealtimePrice(BaseModel):
    """실시간 가격 응답 모델"""
    stock_code: str
    stock_name: str
    current_price: int
    change: int
    change_rate: float
    volume: int
    trading_value: int
    open_price: int
    high_price: int
    low_price: int
    prev_close: int
    per: Optional[float] = None
    pbr: Optional[float] = None
    market_cap: Optional[int] = None
    timestamp: str


class RealtimePriceList(BaseModel):
    """여러 종목 실시간 가격 응답"""
    prices: List[RealtimePrice]
    updated_at: str


# KIS 클라이언트 지연 로딩
_kis_client = None


def get_kis():
    """KIS 클라이언트 가져오기"""
    global _kis_client
    if _kis_client is None:
        try:
            from api.services.kis_client import get_kis_client
            _kis_client = get_kis_client()
        except Exception as e:
            print(f"KIS 클라이언트 초기화 실패: {e}")
            _kis_client = "error"
    return _kis_client if _kis_client != "error" else None


@router.get("/price/{stock_code}", response_model=RealtimePrice)
async def get_realtime_price(stock_code: str):
    """
    단일 종목 실시간 시세 조회 (30초 캐싱)

    - **stock_code**: 종목코드 (6자리, 예: 005930)
    """
    # 캐시 확인
    cached = get_cached_realtime(stock_code)
    if cached:
        return RealtimePrice(**cached)

    kis = get_kis()
    if kis is None:
        raise HTTPException(
            status_code=503,
            detail="한국투자증권 API 서비스를 이용할 수 없습니다. API 키를 확인하세요."
        )

    try:
        price_data = kis.get_current_price(stock_code)

        if price_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {stock_code}의 시세를 조회할 수 없습니다."
            )

        # 캐시 저장
        set_realtime_cache(stock_code, price_data)
        return RealtimePrice(**price_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Realtime Error] {e}")
        raise HTTPException(status_code=500, detail="시세 조회 중 오류가 발생했습니다")


@router.post("/prices", response_model=RealtimePriceList)
async def get_multiple_realtime_prices(stock_codes: List[str]):
    """
    여러 종목 실시간 시세 일괄 조회 (30초 캐싱 + 병렬 처리)

    - **stock_codes**: 종목코드 리스트 (최대 100개)
    """
    if len(stock_codes) > 100:
        raise HTTPException(
            status_code=400,
            detail="한 번에 최대 100개 종목까지 조회 가능합니다."
        )

    kis = get_kis()
    if kis is None:
        raise HTTPException(
            status_code=503,
            detail="한국투자증권 API 서비스를 이용할 수 없습니다."
        )

    try:
        # 캐시된 것과 새로 조회할 것 분리
        cached_prices = []
        codes_to_fetch = []

        for code in stock_codes:
            cached = get_cached_realtime(code)
            if cached:
                cached_prices.append(cached)
            else:
                codes_to_fetch.append(code)

        # 새로 조회할 종목만 API 호출 (병렬 처리)
        new_prices = []
        if codes_to_fetch:
            new_prices = kis.get_multiple_prices(codes_to_fetch)
            # 새로 조회한 것 캐시에 저장
            for p in new_prices:
                set_realtime_cache(p['stock_code'], p)

        # 캐시 + 새로 조회한 것 합치기
        all_prices = cached_prices + new_prices

        return RealtimePriceList(
            prices=[RealtimePrice(**p) for p in all_prices],
            updated_at=datetime.now().isoformat()
        )

    except Exception as e:
        print(f"[Realtime Error] {e}")
        raise HTTPException(status_code=500, detail="시세 조회 중 오류가 발생했습니다")


@router.get("/top100-prices", response_model=RealtimePriceList)
async def get_top100_realtime_prices():
    """
    TOP100 종목의 실시간 시세 조회 (30초 캐싱 + 병렬 처리)

    저장된 TOP100 종목의 현재가를 실시간으로 가져옵니다.
    """
    global _top100_cache
    import json
    from pathlib import Path

    # TOP100 전체 캐시 확인 (30초)
    cached_data, cached_time = _top100_cache
    if cached_data and time.time() - cached_time < _REALTIME_CACHE_TTL:
        return cached_data

    # TOP100 데이터에서 종목코드 추출
    output_dir = Path(__file__).parent.parent.parent / "output"
    today = datetime.now().strftime("%Y%m%d")

    # 오늘 또는 최근 TOP100 파일 찾기
    top100_file = output_dir / f"top100_{today}.json"
    if not top100_file.exists():
        # 최근 파일 찾기
        json_files = sorted(output_dir.glob("top100_*.json"), reverse=True)
        if json_files:
            top100_file = json_files[0]
        else:
            raise HTTPException(
                status_code=404,
                detail="TOP100 데이터 파일을 찾을 수 없습니다."
            )

    try:
        with open(top100_file, "r", encoding="utf-8") as f:
            top100_data = json.load(f)

        # 종목코드 추출
        stock_codes = [item["code"] for item in top100_data if "code" in item]

        if not stock_codes:
            raise HTTPException(
                status_code=404,
                detail="TOP100 데이터에서 종목코드를 찾을 수 없습니다."
            )

        kis = get_kis()
        if kis is None:
            raise HTTPException(
                status_code=503,
                detail="한국투자증권 API 서비스를 이용할 수 없습니다."
            )

        # 캐시된 것과 새로 조회할 것 분리
        cached_prices = []
        codes_to_fetch = []

        for code in stock_codes[:100]:
            cached = get_cached_realtime(code)
            if cached:
                cached_prices.append(cached)
            else:
                codes_to_fetch.append(code)

        # 새로 조회할 종목만 API 호출 (병렬 처리)
        new_prices = []
        if codes_to_fetch:
            new_prices = kis.get_multiple_prices(codes_to_fetch)
            # 새로 조회한 것 캐시에 저장
            for p in new_prices:
                set_realtime_cache(p['stock_code'], p)

        # 캐시 + 새로 조회한 것 합치기
        all_prices = cached_prices + new_prices

        result = RealtimePriceList(
            prices=[RealtimePrice(**p) for p in all_prices],
            updated_at=datetime.now().isoformat()
        )

        # TOP100 전체 결과 캐시
        _top100_cache = (result, time.time())
        return result

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="TOP100 파일 파싱 오류")
    except Exception as e:
        print(f"[Realtime Error] {e}")
        raise HTTPException(status_code=500, detail="시세 조회 중 오류가 발생했습니다")
