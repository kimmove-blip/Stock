"""
인기 종목 API 라우터
- 실제 거래량 상위 종목
- 상승률/하락률 상위 종목
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date
import json
from pathlib import Path

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent


class PopularStock(BaseModel):
    """인기 종목 모델"""
    rank: int
    code: str
    name: str
    current_price: int
    change: int
    change_rate: float
    volume: int
    market: Optional[str] = None


class PopularStocksResponse(BaseModel):
    """인기 종목 응답"""
    items: List[PopularStock]
    category: str
    generated_at: str
    source: str


def get_volume_leaders_fdr():
    """FinanceDataReader로 거래량 상위 종목 조회"""
    try:
        import FinanceDataReader as fdr

        # 오늘 날짜 KOSPI, KOSDAQ 데이터
        today = date.today().strftime('%Y-%m-%d')

        stocks = []

        # KOSPI 종목
        try:
            kospi = fdr.StockListing('KOSPI')
            if not kospi.empty and 'Volume' in kospi.columns:
                kospi = kospi.nlargest(30, 'Volume')
                for _, row in kospi.iterrows():
                    stocks.append({
                        'code': row.get('Code', ''),
                        'name': row.get('Name', ''),
                        'current_price': int(row.get('Close', 0)),
                        'change': int(row.get('Changes', 0)),
                        'change_rate': float(row.get('ChagesRatio', 0)),
                        'volume': int(row.get('Volume', 0)),
                        'market': 'KOSPI'
                    })
        except Exception as e:
            print(f"KOSPI 조회 실패: {e}")

        # KOSDAQ 종목
        try:
            kosdaq = fdr.StockListing('KOSDAQ')
            if not kosdaq.empty and 'Volume' in kosdaq.columns:
                kosdaq = kosdaq.nlargest(30, 'Volume')
                for _, row in kosdaq.iterrows():
                    stocks.append({
                        'code': row.get('Code', ''),
                        'name': row.get('Name', ''),
                        'current_price': int(row.get('Close', 0)),
                        'change': int(row.get('Changes', 0)),
                        'change_rate': float(row.get('ChagesRatio', 0)),
                        'volume': int(row.get('Volume', 0)),
                        'market': 'KOSDAQ'
                    })
        except Exception as e:
            print(f"KOSDAQ 조회 실패: {e}")

        # 거래량 순 정렬
        stocks.sort(key=lambda x: x['volume'], reverse=True)
        return stocks[:30]

    except Exception as e:
        print(f"FDR 조회 실패: {e}")
        return None


def get_volume_leaders_pykrx():
    """pykrx로 거래량 상위 종목 조회"""
    try:
        from pykrx import stock

        today = date.today().strftime('%Y%m%d')

        stocks = []

        # KOSPI
        try:
            kospi_df = stock.get_market_ohlcv(today, market="KOSPI")
            if not kospi_df.empty:
                kospi_df = kospi_df.nlargest(20, '거래량')
                for code, row in kospi_df.iterrows():
                    name = stock.get_market_ticker_name(code)
                    stocks.append({
                        'code': code,
                        'name': name,
                        'current_price': int(row['종가']),
                        'change': int(row['종가'] - row['시가']),
                        'change_rate': round((row['종가'] - row['시가']) / row['시가'] * 100, 2) if row['시가'] > 0 else 0,
                        'volume': int(row['거래량']),
                        'market': 'KOSPI'
                    })
        except Exception as e:
            print(f"pykrx KOSPI 실패: {e}")

        # KOSDAQ
        try:
            kosdaq_df = stock.get_market_ohlcv(today, market="KOSDAQ")
            if not kosdaq_df.empty:
                kosdaq_df = kosdaq_df.nlargest(20, '거래량')
                for code, row in kosdaq_df.iterrows():
                    name = stock.get_market_ticker_name(code)
                    stocks.append({
                        'code': code,
                        'name': name,
                        'current_price': int(row['종가']),
                        'change': int(row['종가'] - row['시가']),
                        'change_rate': round((row['종가'] - row['시가']) / row['시가'] * 100, 2) if row['시가'] > 0 else 0,
                        'volume': int(row['거래량']),
                        'market': 'KOSDAQ'
                    })
        except Exception as e:
            print(f"pykrx KOSDAQ 실패: {e}")

        stocks.sort(key=lambda x: x['volume'], reverse=True)
        return stocks[:30]

    except Exception as e:
        print(f"pykrx 조회 실패: {e}")
        return None


def get_from_top100_cache():
    """TOP100 캐시에서 데이터 가져오기 (폴백)"""
    try:
        json_files = list(PROJECT_ROOT.glob("output/top100_*.json"))
        if not json_files:
            return None

        latest = max(json_files, key=lambda x: x.stat().st_mtime)
        with open(latest) as f:
            data = json.load(f)

        items = data.get('items', [])
        stocks = []
        for item in items:
            stocks.append({
                'code': item.get('code', ''),
                'name': item.get('name', ''),
                'current_price': item.get('current_price', 0),
                'change': item.get('change', 0),
                'change_rate': item.get('change_rate', 0),
                'volume': item.get('volume', 0),
                'market': item.get('market')
            })

        return stocks
    except Exception as e:
        print(f"TOP100 캐시 로드 실패: {e}")
        return None


@router.get("/volume", response_model=PopularStocksResponse)
async def get_volume_leaders(limit: int = 20):
    """거래량 상위 종목 조회"""
    stocks = None
    source = "unknown"

    # 1. pykrx 시도
    stocks = get_volume_leaders_pykrx()
    if stocks:
        source = "pykrx"

    # 2. FDR 시도
    if not stocks:
        stocks = get_volume_leaders_fdr()
        if stocks:
            source = "FinanceDataReader"

    # 3. TOP100 캐시 폴백
    if not stocks:
        stocks = get_from_top100_cache()
        if stocks:
            stocks.sort(key=lambda x: x.get('volume', 0), reverse=True)
            source = "TOP100 Cache"

    if not stocks:
        raise HTTPException(status_code=503, detail="거래량 데이터를 가져올 수 없습니다")

    items = []
    for idx, s in enumerate(stocks[:limit]):
        items.append(PopularStock(
            rank=idx + 1,
            code=s['code'],
            name=s['name'],
            current_price=s['current_price'],
            change=s.get('change', 0),
            change_rate=s.get('change_rate', 0),
            volume=s.get('volume', 0),
            market=s.get('market')
        ))

    return PopularStocksResponse(
        items=items,
        category="volume",
        generated_at=datetime.now().isoformat(),
        source=source
    )


@router.get("/gainers", response_model=PopularStocksResponse)
async def get_top_gainers(limit: int = 20):
    """상승률 상위 종목 조회"""
    stocks = get_volume_leaders_pykrx() or get_volume_leaders_fdr() or get_from_top100_cache()

    if not stocks:
        raise HTTPException(status_code=503, detail="데이터를 가져올 수 없습니다")

    # 상승률 순 정렬
    stocks.sort(key=lambda x: x.get('change_rate', 0), reverse=True)

    items = []
    for idx, s in enumerate(stocks[:limit]):
        items.append(PopularStock(
            rank=idx + 1,
            code=s['code'],
            name=s['name'],
            current_price=s['current_price'],
            change=s.get('change', 0),
            change_rate=s.get('change_rate', 0),
            volume=s.get('volume', 0),
            market=s.get('market')
        ))

    return PopularStocksResponse(
        items=items,
        category="gainers",
        generated_at=datetime.now().isoformat(),
        source="market data"
    )


@router.get("/losers", response_model=PopularStocksResponse)
async def get_top_losers(limit: int = 20):
    """하락률 상위 종목 조회"""
    stocks = get_volume_leaders_pykrx() or get_volume_leaders_fdr() or get_from_top100_cache()

    if not stocks:
        raise HTTPException(status_code=503, detail="데이터를 가져올 수 없습니다")

    # 하락률 순 정렬 (낮은 순)
    stocks.sort(key=lambda x: x.get('change_rate', 0))

    items = []
    for idx, s in enumerate(stocks[:limit]):
        items.append(PopularStock(
            rank=idx + 1,
            code=s['code'],
            name=s['name'],
            current_price=s['current_price'],
            change=s.get('change', 0),
            change_rate=s.get('change_rate', 0),
            volume=s.get('volume', 0),
            market=s.get('market')
        ))

    return PopularStocksResponse(
        items=items,
        category="losers",
        generated_at=datetime.now().isoformat(),
        source="market data"
    )
