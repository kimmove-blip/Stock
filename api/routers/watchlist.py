"""
관심종목 API 라우터
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.schemas.portfolio import WatchlistItemCreate, WatchlistItemResponse, WatchlistResponse
from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager
from api.routers.stocks import get_stock_libs


router = APIRouter()


def get_current_price(code: str) -> tuple:
    """현재가, 등락률 조회"""
    try:
        libs = get_stock_libs()
        if not libs:
            return None, None
        get_ohlcv = libs['get_ohlcv']
        ohlcv = get_ohlcv(code, 5)
        if ohlcv.empty or len(ohlcv) < 2:
            return None, None
        current = int(ohlcv.iloc[-1]['종가'])
        prev = int(ohlcv.iloc[-2]['종가'])
        change_rate = round((current - prev) / prev * 100, 2) if prev > 0 else 0
        return current, change_rate
    except:
        return None, None


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """관심종목 조회"""
    all_items = db.get_watchlists(current_user['id'])
    categories = db.get_watchlist_categories(current_user['id'])

    # 카테고리 필터링
    if category:
        items = [item for item in all_items if item['category'] == category]
    else:
        items = all_items

    # 현재가 추가
    watchlist_items = []
    for item in items:
        current_price, change_rate = get_current_price(item['stock_code'])
        watchlist_items.append(WatchlistItemResponse(
            id=hash(f"{current_user['id']}_{item['category']}_{item['stock_code']}") % 1000000,  # 임시 ID
            user_id=current_user['id'],
            stock_code=item['stock_code'],
            stock_name=item['stock_name'],
            category=item['category'],
            current_price=current_price,
            change_rate=change_rate
        ))

    return WatchlistResponse(
        total_count=len(watchlist_items),
        categories=categories,
        items=watchlist_items
    )


@router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    item: WatchlistItemCreate,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """관심종목 추가"""
    success = db.add_to_watchlist(
        user_id=current_user['id'],
        category=item.category or '기본',
        stock_code=item.stock_code,
        stock_name=item.stock_name
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 관심종목에 추가되어 있습니다"
        )

    current_price, change_rate = get_current_price(item.stock_code)

    return WatchlistItemResponse(
        id=hash(f"{current_user['id']}_{item.category}_{item.stock_code}") % 1000000,
        user_id=current_user['id'],
        stock_code=item.stock_code,
        stock_name=item.stock_name,
        category=item.category or '기본',
        memo=item.memo,
        current_price=current_price,
        change_rate=change_rate
    )


@router.delete("/{stock_code}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    stock_code: str,
    category: str = "기본",
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """관심종목 삭제"""
    db.remove_from_watchlist(
        user_id=current_user['id'],
        category=category,
        stock_code=stock_code
    )


@router.post("/category/{category_name}", status_code=status.HTTP_201_CREATED)
async def create_category(
    category_name: str,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """카테고리 생성 (빈 카테고리)"""
    # SQLite에서는 빈 카테고리를 별도로 저장하지 않음
    # 종목 추가 시 자동으로 카테고리가 생성됨
    return {"message": f"카테고리 '{category_name}'가 생성됩니다. 종목을 추가해주세요."}


@router.delete("/category/{category_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_name: str,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """카테고리 및 해당 종목 전체 삭제"""
    if category_name == '기본':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'기본' 카테고리는 삭제할 수 없습니다"
        )

    db.delete_watchlist_category(
        user_id=current_user['id'],
        category=category_name
    )


@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
async def clear_watchlist(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """관심종목 전체 삭제 (모든 카테고리)"""
    db.clear_watchlist(current_user['id'])
