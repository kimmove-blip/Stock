"""
가치주 발굴 API 라우터
- 대형우량주 포함
- PER, PBR, 배당률 기반 가치주 선별
- KIS API 사용
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json
from pathlib import Path

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent


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
    market_cap: Optional[int] = None
    score: int
    tags: List[str] = []


class ValueStocksResponse(BaseModel):
    """가치주 목록 응답"""
    items: List[ValueStock]
    generated_at: str
    criteria: dict


# 대표 우량주 목록 (시가총액 상위 + 가치주 후보) - 코드:종목명 매핑
VALUE_STOCK_NAMES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "005380": "현대차",
    "005490": "POSCO홀딩스",
    "035420": "NAVER",
    "000270": "기아",
    "051910": "LG화학",
    "006400": "삼성SDI",
    "035720": "카카오",
    "028260": "삼성물산",
    "105560": "KB금융",
    "055550": "신한지주",
    "086790": "하나금융지주",
    "316140": "우리금융지주",
    "017670": "SK텔레콤",
    "030200": "KT",
    "032830": "삼성생명",
    "003550": "LG",
    "066570": "LG전자",
    "034730": "SK",
    "015760": "한국전력",
    "096770": "SK이노베이션",
    "009150": "삼성전기",
    "018260": "삼성에스디에스",
    "000810": "삼성화재",
    "033780": "KT&G",
    "003490": "대한항공",
    "036570": "엔씨소프트",
    "011170": "롯데케미칼",
    "010130": "고려아연",
    "004020": "현대제철",
    "000720": "현대건설",
    "003410": "쌍용C&E",
    "010950": "S-Oil",
    "024110": "기업은행",
    "078930": "GS",
    "036460": "한국가스공사",
    "047050": "포스코인터내셔널",
    "010140": "삼성중공업",
    "009540": "한국조선해양",
}

VALUE_STOCK_CANDIDATES = list(VALUE_STOCK_NAMES.keys())


def get_stock_name(code: str) -> str:
    """종목명 조회"""
    # TOP100 JSON에서 조회
    try:
        json_files = list(PROJECT_ROOT.glob("output/top100_*.json"))
        if json_files:
            latest = max(json_files, key=lambda x: x.stat().st_mtime)
            with open(latest) as f:
                data = json.load(f)
                for item in data.get('items', []):
                    if item.get('code') == code:
                        return item.get('name', code)
    except:
        pass

    # FDR에서 조회
    try:
        import FinanceDataReader as fdr
        krx = fdr.StockListing("KRX")
        match = krx[krx['Code'] == code]
        if not match.empty:
            return match.iloc[0]['Name']
    except:
        pass

    return code


@router.get("", response_model=ValueStocksResponse)
async def get_value_stocks(limit: int = 30):
    """
    가치주 목록 조회 - KIS API 사용
    """
    try:
        from api.services.kis_client import KISClient
        kis = KISClient()
    except Exception as e:
        print(f"[Value Stocks Error] {e}")
        raise HTTPException(status_code=503, detail="시세 API 서비스를 이용할 수 없습니다")

    value_stocks = []

    for code in VALUE_STOCK_CANDIDATES:
        try:
            # KIS API로 현재가 조회 (PER, PBR 포함)
            data = kis.get_current_price(code)
            if not data:
                continue

            current_price = data.get('current_price', 0)
            if current_price <= 0:
                continue

            per = data.get('per')
            pbr = data.get('pbr')
            change_rate = data.get('change_rate', 0)
            market_cap = data.get('market_cap', 0)  # 억원

            # 가치주 필터: PER과 PBR이 있고, 적정 범위 내
            # PER: 0 < PER <= 20 (흑자 기업)
            # PBR: 0 < PBR <= 3
            if per is None or per <= 0 or per > 20:
                continue
            if pbr is None or pbr <= 0 or pbr > 3:
                continue

            # 종목명 조회 (매핑 우선)
            name = VALUE_STOCK_NAMES.get(code) or data.get('stock_name') or get_stock_name(code)

            # 가치 점수 계산
            score = 50
            tags = []

            # PER 점수
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
            if pbr <= 0.5:
                score += 25
                tags.append("초저PBR")
            elif pbr <= 1:
                score += 20
                tags.append("저PBR")
            elif pbr <= 1.5:
                score += 10
                tags.append("적정PBR")

            # 대형주 가산점
            if market_cap and market_cap >= 100000:  # 10조 이상
                score += 10
                tags.append("대형주")
            elif market_cap and market_cap >= 10000:  # 1조 이상
                score += 5
                tags.append("중형주")

            value_stocks.append(ValueStock(
                code=code,
                name=name,
                market=None,
                current_price=current_price,
                change_rate=round(change_rate, 2),
                per=round(per, 2) if per else None,
                pbr=round(pbr, 2) if pbr else None,
                dividend_yield=None,  # KIS API에서 제공 안함
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
            "per_max": 20,
            "pbr_max": 3,
            "source": "KIS API",
            "includes_large_cap": True
        }
    )
