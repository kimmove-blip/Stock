"""
관리자 API 라우터
- 회원 목록 조회
- 회원 관리
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.dependencies import get_db, get_current_admin_required
from database.db_manager import DatabaseManager

router = APIRouter()


class UserInfo(BaseModel):
    """회원 정보"""
    id: int
    email: str
    username: str
    name: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    email_subscription: bool = False
    telegram_enabled: bool = False
    portfolio_count: int = 0
    watchlist_count: int = 0


class UserListResponse(BaseModel):
    """회원 목록 응답"""
    users: List[UserInfo]
    total: int


@router.get("/users", response_model=UserListResponse)
async def get_all_users(
    current_user: dict = Depends(get_current_admin_required),
    db: DatabaseManager = Depends(get_db)
):
    """전체 회원 목록 조회 (관리자 전용)"""
    with db.get_connection() as conn:
        # 모든 사용자 조회
        cursor = conn.execute("""
            SELECT
                u.id, u.email, u.username, u.name,
                u.created_at, u.last_login, u.is_active, u.is_admin,
                u.email_subscription, u.telegram_alerts_enabled,
                (SELECT COUNT(*) FROM portfolios WHERE user_id = u.id) as portfolio_count,
                (SELECT COUNT(*) FROM watchlists WHERE user_id = u.id) as watchlist_count
            FROM users u
            ORDER BY COALESCE(u.last_login, u.created_at) DESC
        """)
        rows = cursor.fetchall()

    users = []
    for row in rows:
        users.append(UserInfo(
            id=row['id'],
            email=row['email'] or '',
            username=row['username'],
            name=row['name'] or '',
            created_at=row['created_at'] if row['created_at'] else None,
            last_login=row['last_login'] if row['last_login'] else None,
            is_active=bool(row['is_active']),
            is_admin=bool(row['is_admin']),
            email_subscription=bool(row['email_subscription']),
            telegram_enabled=bool(row['telegram_alerts_enabled']),
            portfolio_count=row['portfolio_count'] or 0,
            watchlist_count=row['watchlist_count'] or 0
        ))

    return UserListResponse(users=users, total=len(users))


class UserUpdateRequest(BaseModel):
    """회원 정보 수정 요청"""
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: dict = Depends(get_current_admin_required),
    db: DatabaseManager = Depends(get_db)
):
    """회원 정보 수정 (관리자 전용)"""
    # 자기 자신 비활성화 방지
    if user_id == current_user['id'] and request.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자기 자신을 비활성화할 수 없습니다"
        )

    with db.get_connection() as conn:
        if request.is_admin is not None:
            conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if request.is_admin else 0, user_id)
            )
        if request.is_active is not None:
            conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if request.is_active else 0, user_id)
            )
        conn.commit()

    return {"message": "회원 정보가 수정되었습니다"}


@router.get("/stats")
async def get_admin_stats(
    current_user: dict = Depends(get_current_admin_required),
    db: DatabaseManager = Depends(get_db)
):
    """관리자 대시보드 통계 (관리자 전용)"""
    with db.get_connection() as conn:
        # 총 회원수
        total_users = conn.execute("SELECT COUNT(*) as count FROM users WHERE is_active = 1").fetchone()['count']

        # 오늘 가입한 회원수
        today_users = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE date(created_at) = date('now')"
        ).fetchone()['count']

        # 이메일 구독자 수
        email_subscribers = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE email_subscription = 1 AND is_active = 1"
        ).fetchone()['count']

        # 텔레그램 구독자 수
        telegram_subscribers = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE telegram_alerts_enabled = 1 AND is_active = 1"
        ).fetchone()['count']

        # 대기 중인 문의 수
        pending_contacts = conn.execute(
            "SELECT COUNT(*) as count FROM contacts WHERE status = 'pending'"
        ).fetchone()['count']

    return {
        "total_users": total_users,
        "today_users": today_users,
        "email_subscribers": email_subscribers,
        "telegram_subscribers": telegram_subscribers,
        "pending_contacts": pending_contacts
    }
