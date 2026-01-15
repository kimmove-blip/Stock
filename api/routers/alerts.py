"""
알림 기록 API 라우터
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager


router = APIRouter()


class AlertItem(BaseModel):
    """알림 항목"""
    stock_code: str
    alert_type: str
    message: Optional[str] = None
    created_at: str


class AlertListResponse(BaseModel):
    """알림 목록 응답"""
    items: List[AlertItem]
    total_count: int


@router.get("", response_model=AlertListResponse)
async def get_alert_history(
    days: int = 30,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """알림 기록 조회"""
    alerts = db.get_alert_history(current_user['id'], days=days)

    items = [
        AlertItem(
            stock_code=alert['stock_code'],
            alert_type=alert['alert_type'],
            message=alert.get('message'),
            created_at=str(alert['created_at'])
        )
        for alert in alerts
    ]

    return AlertListResponse(
        items=items,
        total_count=len(items)
    )


@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
async def clear_alert_history(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """알림 기록 전체 삭제"""
    db.clear_alert_history(current_user['id'])
