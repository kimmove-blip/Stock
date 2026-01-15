"""
공지사항 API
- 전체 유저에게 공지 팝업 표시
- 관리자용 공지 관리
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_user_required
from api.services.dart_service import get_db_connection

KST = ZoneInfo("Asia/Seoul")

def get_kst_now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

router = APIRouter()


class AnnouncementCreate(BaseModel):
    title: str
    content: str
    type: str = "info"  # info, warning, error
    show_once: bool = False
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    type: str
    show_once: bool
    created_at: str


@router.get("", response_model=List[AnnouncementResponse])
async def get_active_announcements():
    """활성 공지사항 조회 (모든 유저)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT id, title, content, type, show_once, created_at
            FROM announcements
            WHERE is_active = 1
              AND (start_date IS NULL OR start_date <= ?)
              AND (end_date IS NULL OR end_date >= ?)
            ORDER BY created_at DESC
        """, (now, now))

        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "type": row["type"],
                "show_once": bool(row["show_once"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


@router.get("/admin/list")
async def admin_list_announcements(current_user: dict = Depends(get_current_user_required)):
    """관리자: 전체 공지사항 목록"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM announcements ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


@router.post("/admin")
async def admin_create_announcement(
    data: AnnouncementCreate,
    current_user: dict = Depends(get_current_user_required)
):
    """관리자: 공지사항 등록"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = get_kst_now()
        cursor.execute("""
            INSERT INTO announcements (title, content, type, show_once, start_date, end_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.title,
            data.content,
            data.type,
            1 if data.show_once else 0,
            data.start_date,
            data.end_date,
            now,
            now,
        ))
        conn.commit()

        return {"status": "success", "id": cursor.lastrowid, "message": "공지사항이 등록되었습니다"}


@router.put("/admin/{announcement_id}")
async def admin_update_announcement(
    announcement_id: int,
    data: AnnouncementCreate,
    current_user: dict = Depends(get_current_user_required)
):
    """관리자: 공지사항 수정"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE announcements
            SET title = ?, content = ?, type = ?, show_once = ?,
                start_date = ?, end_date = ?, updated_at = ?
            WHERE id = ?
        """, (
            data.title,
            data.content,
            data.type,
            1 if data.show_once else 0,
            data.start_date,
            data.end_date,
            get_kst_now(),
            announcement_id,
        ))
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다")

        return {"status": "success", "message": "공지사항이 수정되었습니다"}


@router.put("/admin/{announcement_id}/toggle")
async def admin_toggle_announcement(
    announcement_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """관리자: 공지사항 활성/비활성 토글"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE announcements
            SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END,
                updated_at = ?
            WHERE id = ?
        """, (get_kst_now(), announcement_id))
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다")

        return {"status": "success", "message": "공지사항 상태가 변경되었습니다"}


@router.delete("/admin/{announcement_id}")
async def admin_delete_announcement(
    announcement_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """관리자: 공지사항 삭제"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다")

        return {"status": "success", "message": "공지사항이 삭제되었습니다"}
