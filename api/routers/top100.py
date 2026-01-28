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
    import re
    if not os.path.exists(OUTPUT_DIR):
        return None

    # top100_YYYYMMDD.json 형식만 매칭 (test, trend, strict 등 제외)
    pattern = re.compile(r'^top100_(\d{8})\.json$')
    files = []
    for f in os.listdir(OUTPUT_DIR):
        match = pattern.match(f)
        if match:
            files.append((match.group(1), f))  # (날짜, 파일명)

    if not files:
        return None

    # 날짜순 정렬 (내림차순)
    files.sort(reverse=True)
    return os.path.join(OUTPUT_DIR, files[0][1])


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
        print(f"[TOP100 Error] {e}")
        raise HTTPException(status_code=500, detail="데이터 파일 읽기 중 오류가 발생했습니다")

    # 캐시된 현재가 로드 (장중에만 사용)
    cached_prices = {}
    try:
        from database.db_manager import DatabaseManager
        db = DatabaseManager()

        # 장중(09:00~15:30)에만 캐시 사용
        now = datetime.now()
        is_market_hours = 9 <= now.hour < 16  # 09:00 ~ 15:59

        if is_market_hours:
            all_cached = db.get_cached_prices()

            # 오늘 09:00 이후의 캐시만 사용 (장 시작 전 캐시 제외)
            today_market_start = now.replace(hour=9, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
            for p in all_cached:
                updated = p.get('updated_at', '')
                # updated_at이 오늘 장 시작 이후인 경우만 사용
                if updated and updated >= today_market_start:
                    cached_prices[p['stock_code']] = p
    except Exception as e:
        print(f"[TOP100] 캐시 로드 실패: {e}")

    # 파일명에서 날짜 추출
    filename = os.path.basename(filepath)
    file_date = filename.replace('top100_', '').replace('.json', '')

    # ========================================================
    # [중요] 장 시작 전 등락률 0 처리 규칙
    # - 07:00 ~ 09:00 사이에는 무조건 등락률(change_rate)을 0으로 표시
    # - 이유: 전날 등락률이 오늘 데이터처럼 보이는 혼란 방지
    # - 관련 문서: CLAUDE.md "장 시작 전 데이터 처리 규칙" 참조
    # ========================================================
    now = datetime.now()
    is_before_market = 7 <= now.hour < 9  # 07:00 ~ 08:59

    # 데이터 형식 처리 (dict with 'stocks' key or list)
    if isinstance(raw_data, dict):
        stocks_data = raw_data.get('stocks', [])
    else:
        stocks_data = raw_data

    items = []
    for i, stock in enumerate(stocks_data[:100], 1):
        stock_code = stock.get('code', stock.get('종목코드', ''))

        # 캐시된 현재가 우선 사용
        cached = cached_prices.get(stock_code, {})

        # 현재가 처리 (캐시 → JSON 순서)
        current_price = cached.get('current_price') or stock.get('current_price') or stock.get('현재가') or stock.get('close')
        if current_price is not None:
            current_price = int(current_price)

        # indicators에서 RSI, MACD, change_pct 추출
        indicators = stock.get('indicators', {})

        # 등락률 처리 (장 시작 전에는 0으로 표시)
        if is_before_market:
            change_rate = 0.0
        else:
            change_rate = cached.get('change_rate') or stock.get('change_pct') or indicators.get('change_pct')
            if change_rate is not None:
                change_rate = round(float(change_rate), 2)
        rsi = stock.get('rsi') or stock.get('RSI') or indicators.get('rsi')
        macd = stock.get('macd_signal') or indicators.get('macd')

        # signals에서 VOLUME_SURGE 확인
        signals = stock.get('signals', [])
        volume_surge = 'VOLUME_SURGE' in signals

        # 의견 계산 (신호 기반)
        opinion = stock.get('opinion', stock.get('의견'))
        if not opinion:
            score = stock.get('score', 0)
            has_caution = any(s in signals for s in ['OVERBOUGHT', 'DEATH_CROSS', 'BEARISH_DIVERGENCE'])
            has_strong = any(s in signals for s in ['GOLDEN_CROSS', 'MACD_GOLDEN_CROSS', 'RSI_OVERSOLD', 'BULLISH_DIVERGENCE'])

            if has_caution:
                opinion = "주의"
            elif score >= 70 and has_strong:
                opinion = "적극 매수"
            elif score >= 50:
                opinion = "매수"
            else:
                opinion = "관망"

        items.append(Top100Item(
            rank=i,
            code=stock_code,
            name=stock.get('name', stock.get('종목명', '')),
            score=stock.get('score', stock.get('점수', 0)),
            opinion=opinion,
            current_price=current_price,
            change_rate=change_rate,
            rsi=round(rsi, 1) if rsi else None,
            macd_signal=round(macd, 2) if macd else None,
            volume_surge=volume_surge
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
