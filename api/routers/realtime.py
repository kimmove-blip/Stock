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
    """KIS 클라이언트 가져오기 (시세 조회 전용 - 실전투자 URL 사용)"""
    global _kis_client
    if _kis_client is None:
        try:
            from api.services.kis_client import get_kis_client_for_prices
            _kis_client = get_kis_client_for_prices()
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
        # [중요] 장 시작 전(07:00~09:00) 등락률 0 처리
        now = datetime.now()
        if 7 <= now.hour < 9:
            cached = cached.copy()
            cached['change_rate'] = 0.0
            cached['change'] = 0
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

        # [중요] 장 시작 전(07:00~09:00) 등락률 0 처리
        now = datetime.now()
        if 7 <= now.hour < 9:
            price_data['change_rate'] = 0.0
            price_data['change'] = 0

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

        # [중요] 장 시작 전(07:00~09:00) 등락률 0 처리
        now = datetime.now()
        if 7 <= now.hour < 9:
            for p in all_prices:
                p['change_rate'] = 0.0
                p['change'] = 0

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

    # 오늘 또는 최근 TOP100 파일 찾기 (top100_YYYYMMDD.json 형식만)
    import re
    top100_file = output_dir / f"top100_{today}.json"
    if not top100_file.exists():
        # 최근 파일 찾기 (v4, strict, trend 등 제외)
        pattern = re.compile(r'^top100_(\d{8})\.json$')
        json_files = []
        for f in output_dir.glob("top100_*.json"):
            if pattern.match(f.name):
                json_files.append(f)
        json_files = sorted(json_files, reverse=True)
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

        # 데이터 형식 처리 (dict with 'stocks' key or list)
        if isinstance(top100_data, dict):
            stocks_list = top100_data.get('stocks', [])
        else:
            stocks_list = top100_data

        # 종목코드 추출
        stock_codes = [item["code"] for item in stocks_list if "code" in item]

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

        # ========================================================
        # [중요] 장 시작 전 등락률 0 처리 규칙
        # - 07:00 ~ 09:00 사이에는 무조건 change_rate를 0으로
        # - 관련 문서: CLAUDE.md "장 시작 전 데이터 처리 규칙" 참조
        # ========================================================
        now = datetime.now()
        is_before_market = 7 <= now.hour < 9
        if is_before_market:
            for p in all_prices:
                p['change_rate'] = 0.0
                p['change'] = 0

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


# ==================== 캐시된 현재가 API (하이브리드) ====================

class CachedPrice(BaseModel):
    """캐시된 가격 응답 모델"""
    stock_code: str
    stock_name: Optional[str] = None
    current_price: Optional[int] = None
    change: Optional[int] = None
    change_rate: Optional[float] = None
    volume: Optional[int] = None
    trading_value: Optional[int] = None
    open_price: Optional[int] = None
    high_price: Optional[int] = None
    low_price: Optional[int] = None
    prev_close: Optional[int] = None
    updated_at: Optional[str] = None


class CachedPriceResponse(BaseModel):
    """캐시된 가격 목록 응답"""
    prices: List[CachedPrice]
    cache_updated_at: Optional[str] = None
    cache_count: int = 0


@router.get("/cached/price/{stock_code}", response_model=CachedPrice)
async def get_cached_price(stock_code: str):
    """
    단일 종목 캐시된 현재가 조회 (DB 캐시)

    - **stock_code**: 종목코드 (6자리)
    """
    from database.db_manager import DatabaseManager
    db = DatabaseManager()

    cached = db.get_cached_price(stock_code)
    if not cached:
        raise HTTPException(status_code=404, detail=f"종목 {stock_code}의 캐시된 시세가 없습니다")

    # [중요] 장 시작 전(07:00~09:00) 등락률 0 처리
    now = datetime.now()
    if 7 <= now.hour < 9:
        cached = cached.copy()
        cached['change_rate'] = 0.0
        cached['change'] = 0

    return CachedPrice(**cached)


@router.post("/cached/prices", response_model=CachedPriceResponse)
async def get_cached_prices(stock_codes: List[str]):
    """
    여러 종목 캐시된 현재가 조회 (DB 캐시)

    - **stock_codes**: 종목코드 리스트
    """
    from database.db_manager import DatabaseManager
    db = DatabaseManager()

    cached_list = db.get_cached_prices(stock_codes)
    last_updated = db.get_price_cache_updated_at()
    cache_count = db.get_price_cache_count()

    # [중요] 장 시작 전(07:00~09:00) 등락률 0 처리
    now = datetime.now()
    if 7 <= now.hour < 9:
        for p in cached_list:
            p['change_rate'] = 0.0
            p['change'] = 0

    return CachedPriceResponse(
        prices=[CachedPrice(**p) for p in cached_list],
        cache_updated_at=last_updated,
        cache_count=cache_count
    )


@router.get("/cached/status")
async def get_cache_status():
    """
    현재가 캐시 상태 조회
    """
    from database.db_manager import DatabaseManager
    db = DatabaseManager()

    last_updated = db.get_price_cache_updated_at()
    count = db.get_price_cache_count()

    return {
        "cache_count": count,
        "last_updated": last_updated,
        "status": "ok" if count > 0 else "empty"
    }


@router.get("/hybrid/prices", response_model=CachedPriceResponse)
async def get_hybrid_prices(codes: str = Query(..., description="쉼표로 구분된 종목코드")):
    """
    하이브리드 현재가 조회

    1. 캐시된 가격 먼저 반환 (빠름)
    2. 캐시 미스 종목은 실시간 조회 후 캐시 저장

    - **codes**: 쉼표로 구분된 종목코드 (예: 005930,000660,035720)
    """
    from database.db_manager import DatabaseManager
    db = DatabaseManager()

    stock_codes = [c.strip() for c in codes.split(',') if c.strip()]
    if len(stock_codes) > 100:
        raise HTTPException(status_code=400, detail="최대 100개 종목까지 조회 가능")

    # 캐시에서 조회
    cached_list = db.get_cached_prices(stock_codes)
    cached_codes = {p['stock_code'] for p in cached_list}

    # 캐시 미스 종목
    missing_codes = [c for c in stock_codes if c not in cached_codes]

    # 캐시 미스 종목 실시간 조회
    if missing_codes:
        kis = get_kis()
        if kis:
            try:
                new_prices = kis.get_multiple_prices(missing_codes)
                if new_prices:
                    # 캐시에 저장
                    db.bulk_upsert_price_cache(new_prices)
                    # 결과에 추가
                    for p in new_prices:
                        cached_list.append(p)
            except Exception as e:
                print(f"[Hybrid] 실시간 조회 실패: {e}")

    last_updated = db.get_price_cache_updated_at()
    cache_count = db.get_price_cache_count()

    # [중요] 장 시작 전(07:00~09:00) 등락률 0 처리
    now = datetime.now()
    if 7 <= now.hour < 9:
        for p in cached_list:
            p['change_rate'] = 0.0
            p['change'] = 0

    return CachedPriceResponse(
        prices=[CachedPrice(**p) for p in cached_list],
        cache_updated_at=last_updated,
        cache_count=cache_count
    )
