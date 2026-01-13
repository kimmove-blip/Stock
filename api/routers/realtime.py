"""
실시간 시세 API 라우터
한국투자증권 API를 통한 실시간 주가 조회
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


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
    단일 종목 실시간 시세 조회

    - **stock_code**: 종목코드 (6자리, 예: 005930)
    """
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

        return RealtimePrice(**price_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시세 조회 오류: {str(e)}")


@router.post("/prices", response_model=RealtimePriceList)
async def get_multiple_realtime_prices(stock_codes: List[str]):
    """
    여러 종목 실시간 시세 일괄 조회

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
        prices = kis.get_multiple_prices(stock_codes)

        return RealtimePriceList(
            prices=[RealtimePrice(**p) for p in prices],
            updated_at=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시세 조회 오류: {str(e)}")


@router.get("/top100-prices", response_model=RealtimePriceList)
async def get_top100_realtime_prices():
    """
    TOP100 종목의 실시간 시세 조회

    저장된 TOP100 종목의 현재가를 실시간으로 가져옵니다.
    """
    import json
    from pathlib import Path

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

        # 실시간 시세 조회
        prices = kis.get_multiple_prices(stock_codes[:100])

        return RealtimePriceList(
            prices=[RealtimePrice(**p) for p in prices],
            updated_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="TOP100 파일 파싱 오류")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시세 조회 오류: {str(e)}")
