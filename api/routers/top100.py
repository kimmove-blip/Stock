"""
AI 추천 TOP 100 API 라우터
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.schemas.stock import Top100Item, Top100Response


router = APIRouter()

# TOP 100 결과 저장 경로
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'output')


def get_latest_top100_file() -> Optional[str]:
    """가장 최근 TOP 100 JSON 파일 찾기"""
    if not os.path.exists(OUTPUT_DIR):
        return None

    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('top100_') and f.endswith('.json')]
    if not files:
        return None

    # 날짜순 정렬
    files.sort(reverse=True)
    return os.path.join(OUTPUT_DIR, files[0])


def get_top100_file_by_date(date_str: str) -> Optional[str]:
    """특정 날짜의 TOP 100 파일 찾기"""
    filename = f"top100_{date_str}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    return filepath if os.path.exists(filepath) else None


@router.get("", response_model=Top100Response)
async def get_top100(
    date: Optional[str] = Query(None, description="조회 날짜 (YYYYMMDD), 미입력시 최신")
):
    """오늘의 AI 추천 TOP 100"""
    if date:
        filepath = get_top100_file_by_date(date)
        if not filepath:
            raise HTTPException(status_code=404, detail=f"{date} 날짜의 추천 데이터가 없습니다")
    else:
        filepath = get_latest_top100_file()
        if not filepath:
            raise HTTPException(status_code=404, detail="추천 데이터가 없습니다")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 읽기 오류: {str(e)}")

    # 파일명에서 날짜 추출
    filename = os.path.basename(filepath)
    file_date = filename.replace('top100_', '').replace('.json', '')

    # 데이터 형식 처리 (dict with 'stocks' key or list)
    if isinstance(raw_data, dict):
        stocks_data = raw_data.get('stocks', [])
    else:
        stocks_data = raw_data

    items = []
    for i, stock in enumerate(stocks_data[:100], 1):
        # 현재가 처리
        current_price = stock.get('current_price') or stock.get('현재가') or stock.get('close')
        if current_price is not None:
            current_price = int(current_price)

        # 등락률 처리
        change_rate = stock.get('change_rate') or stock.get('등락률') or stock.get('change_pct')

        items.append(Top100Item(
            rank=i,
            code=stock.get('code', stock.get('종목코드', '')),
            name=stock.get('name', stock.get('종목명', '')),
            score=stock.get('score', stock.get('점수', 0)),
            opinion=stock.get('opinion', stock.get('의견', '관망')),
            current_price=current_price,
            change_rate=change_rate,
            rsi=stock.get('rsi', stock.get('RSI')),
            macd_signal=stock.get('macd_signal', stock.get('MACD시그널')),
            volume_surge=stock.get('volume_surge', stock.get('거래량급증'))
        ))

    return Top100Response(
        date=file_date,
        total_count=len(items),
        items=items
    )


@router.get("/history", response_model=List[dict])
async def get_top100_history(
    days: int = Query(7, ge=1, le=30, description="조회 기간 (일)")
):
    """과거 TOP 100 이력"""
    if not os.path.exists(OUTPUT_DIR):
        return []

    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('top100_') and f.endswith('.json')]
    files.sort(reverse=True)

    history = []
    for filename in files[:days]:
        date_str = filename.replace('top100_', '').replace('.json', '')
        filepath = os.path.join(OUTPUT_DIR, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # 데이터 형식 처리
            if isinstance(raw_data, dict):
                stocks_data = raw_data.get('stocks', [])
                total_count = raw_data.get('total_count', len(stocks_data))
            else:
                stocks_data = raw_data
                total_count = len(stocks_data)

            # 상위 5개만 포함
            top5 = []
            for i, stock in enumerate(stocks_data[:5], 1):
                top5.append({
                    'rank': i,
                    'code': stock.get('code', stock.get('종목코드', '')),
                    'name': stock.get('name', stock.get('종목명', '')),
                    'score': stock.get('score', stock.get('점수', 0))
                })

            history.append({
                'date': date_str,
                'total_count': total_count,
                'top5': top5
            })
        except:
            continue

    return history


@router.get("/stock/{code}")
async def get_stock_history(
    code: str,
    days: int = Query(30, ge=1, le=90, description="조회 기간 (일)")
):
    """특정 종목의 TOP 100 진입 이력"""
    if not os.path.exists(OUTPUT_DIR):
        return {"code": code, "history": []}

    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('top100_') and f.endswith('.json')]
    files.sort(reverse=True)

    history = []
    for filename in files[:days]:
        date_str = filename.replace('top100_', '').replace('.json', '')
        filepath = os.path.join(OUTPUT_DIR, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # 데이터 형식 처리
            if isinstance(raw_data, dict):
                stocks_data = raw_data.get('stocks', [])
            else:
                stocks_data = raw_data

            for i, stock in enumerate(stocks_data, 1):
                stock_code = stock.get('code', stock.get('종목코드', ''))
                if stock_code == code:
                    history.append({
                        'date': date_str,
                        'rank': i,
                        'score': stock.get('score', stock.get('점수', 0)),
                        'opinion': stock.get('opinion', stock.get('의견', ''))
                    })
                    break
        except:
            continue

    return {
        "code": code,
        "appearances": len(history),
        "history": history
    }
