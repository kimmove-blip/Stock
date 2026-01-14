"""
가치주 발굴 API 라우터
- 전체 KOSPI/KOSDAQ 대상 가치주 스크리닝
- 하루 한 번 daily_value_stocks.py로 생성된 JSON 사용
- PER, PBR, 배당률 기반 가치주 선별
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
import json

router = APIRouter()

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


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
    total_count: int


def get_latest_value_stocks_file() -> Optional[Path]:
    """최신 가치주 JSON 파일 찾기"""
    json_files = list(OUTPUT_DIR.glob("value_stocks_*.json"))
    if not json_files:
        return None
    return max(json_files, key=lambda x: x.stat().st_mtime)


def load_value_stocks_data() -> Optional[dict]:
    """가치주 데이터 로드"""
    json_file = get_latest_value_stocks_file()
    if not json_file:
        return None

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[가치주] JSON 로드 실패: {e}")
        return None


@router.get("", response_model=ValueStocksResponse)
async def get_value_stocks(
    limit: int = 100,
    market: Optional[str] = None,
    min_div: Optional[float] = None,
    max_per: Optional[float] = None,
    max_pbr: Optional[float] = None
):
    """
    가치주 목록 조회

    - limit: 최대 개수 (기본 100)
    - market: 시장 필터 (KOSPI/KOSDAQ)
    - min_div: 최소 배당률
    - max_per: 최대 PER
    - max_pbr: 최대 PBR
    """
    data = load_value_stocks_data()

    if not data or not data.get('stocks'):
        raise HTTPException(
            status_code=503,
            detail="가치주 데이터가 없습니다. 관리자에게 문의하세요."
        )

    stocks = data['stocks']

    # 필터링
    if market:
        stocks = [s for s in stocks if s.get('market') == market.upper()]

    if min_div is not None:
        stocks = [s for s in stocks if s.get('dividend_yield') and s['dividend_yield'] >= min_div]

    if max_per is not None:
        stocks = [s for s in stocks if s.get('per') and s['per'] <= max_per]

    if max_pbr is not None:
        stocks = [s for s in stocks if s.get('pbr') and s['pbr'] <= max_pbr]

    # limit 적용
    filtered_stocks = stocks[:limit]

    return ValueStocksResponse(
        items=[ValueStock(**s) for s in filtered_stocks],
        generated_at=data.get('generated_at', ''),
        criteria=data.get('criteria', {}),
        total_count=len(stocks)
    )


@router.get("/stats")
async def get_value_stocks_stats():
    """가치주 통계"""
    data = load_value_stocks_data()

    if not data or not data.get('stocks'):
        raise HTTPException(status_code=503, detail="가치주 데이터가 없습니다.")

    stocks = data['stocks']

    # 통계 계산
    kospi_count = len([s for s in stocks if s.get('market') == 'KOSPI'])
    kosdaq_count = len([s for s in stocks if s.get('market') == 'KOSDAQ'])

    high_div = [s for s in stocks if s.get('dividend_yield') and s['dividend_yield'] >= 5]
    low_per = [s for s in stocks if s.get('per') and s['per'] <= 5]
    low_pbr = [s for s in stocks if s.get('pbr') and s['pbr'] <= 0.5]

    return {
        "total": len(stocks),
        "by_market": {
            "KOSPI": kospi_count,
            "KOSDAQ": kosdaq_count
        },
        "highlights": {
            "high_dividend": len(high_div),
            "ultra_low_per": len(low_per),
            "ultra_low_pbr": len(low_pbr)
        },
        "generated_at": data.get('generated_at'),
        "criteria": data.get('criteria')
    }


@router.get("/top-dividend")
async def get_top_dividend_stocks(limit: int = 20):
    """고배당주 목록"""
    data = load_value_stocks_data()

    if not data or not data.get('stocks'):
        raise HTTPException(status_code=503, detail="가치주 데이터가 없습니다.")

    # 배당률 기준 정렬
    stocks = [s for s in data['stocks'] if s.get('dividend_yield') and s['dividend_yield'] > 0]
    stocks.sort(key=lambda x: x['dividend_yield'], reverse=True)

    return {
        "items": [ValueStock(**s) for s in stocks[:limit]],
        "generated_at": data.get('generated_at')
    }


@router.get("/low-per")
async def get_low_per_stocks(limit: int = 20):
    """저PER 종목"""
    data = load_value_stocks_data()

    if not data or not data.get('stocks'):
        raise HTTPException(status_code=503, detail="가치주 데이터가 없습니다.")

    # PER 기준 정렬
    stocks = [s for s in data['stocks'] if s.get('per') and s['per'] > 0]
    stocks.sort(key=lambda x: x['per'])

    return {
        "items": [ValueStock(**s) for s in stocks[:limit]],
        "generated_at": data.get('generated_at')
    }


@router.get("/low-pbr")
async def get_low_pbr_stocks(limit: int = 20):
    """저PBR 종목"""
    data = load_value_stocks_data()

    if not data or not data.get('stocks'):
        raise HTTPException(status_code=503, detail="가치주 데이터가 없습니다.")

    # PBR 기준 정렬
    stocks = [s for s in data['stocks'] if s.get('pbr') and s['pbr'] > 0]
    stocks.sort(key=lambda x: x['pbr'])

    return {
        "items": [ValueStock(**s) for s in stocks[:limit]],
        "generated_at": data.get('generated_at')
    }
