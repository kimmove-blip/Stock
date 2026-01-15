"""
문의하기 API 라우터
- 문의 접수 및 DB 저장
- 관리자 문의 관리
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os
import sys

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.db_manager import DatabaseManager
from api.dependencies import get_db, get_current_admin_required

router = APIRouter()


class ContactRequest(BaseModel):
    """문의 요청 모델"""
    message: str
    email: Optional[str] = None
    username: Optional[str] = None


class ContactResponse(BaseModel):
    """문의 응답 모델"""
    success: bool
    message: str


class ContactItem(BaseModel):
    """문의 항목 모델"""
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    message: str
    status: str
    admin_reply: Optional[str] = None
    created_at: str
    replied_at: Optional[str] = None


class ContactListResponse(BaseModel):
    """문의 목록 응답"""
    items: List[ContactItem]
    total: int
    pending_count: int


class ContactReplyRequest(BaseModel):
    """문의 답변 요청"""
    status: str  # pending, replied, resolved
    admin_reply: Optional[str] = None


@router.post("", response_model=ContactResponse)
async def submit_contact(
    contact: ContactRequest,
    db: DatabaseManager = Depends(get_db)
):
    """
    문의 접수

    문의 내용을 DB에 저장합니다.
    """
    if not contact.message or len(contact.message.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="문의 내용은 최소 10자 이상 입력해주세요."
        )

    try:
        # DB에 문의 저장
        contact_id = db.add_contact(
            message=contact.message,
            username=contact.username,
            email=contact.email
        )

        if contact_id:
            print(f"[Contact] 새 문의 접수: ID={contact_id}, 사용자={contact.username or '비로그인'}")
            return ContactResponse(
                success=True,
                message="문의가 정상적으로 접수되었습니다. 빠른 시일 내에 답변 드리겠습니다."
            )
        else:
            raise HTTPException(status_code=500, detail="문의 저장에 실패했습니다.")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Contact Error] {e}")
        raise HTTPException(status_code=500, detail="문의 처리 중 오류가 발생했습니다.")


# ========== 관리자 API ==========

@router.get("/admin/list", response_model=ContactListResponse)
async def get_contacts_admin(
    status: Optional[str] = None,
    limit: int = 50,
    admin: dict = Depends(get_current_admin_required),
    db: DatabaseManager = Depends(get_db)
):
    """
    [관리자] 문의 목록 조회

    - status: pending, replied, resolved (미지정시 전체)
    """
    try:
        contacts = db.get_contacts(status=status, limit=limit)
        pending_count = db.get_pending_contacts_count()

        items = []
        for c in contacts:
            items.append(ContactItem(
                id=c['id'],
                user_id=c.get('user_id'),
                username=c.get('username'),
                name=c.get('name'),
                email=c.get('email'),
                message=c['message'],
                status=c['status'],
                admin_reply=c.get('admin_reply'),
                created_at=c['created_at'],
                replied_at=c.get('replied_at')
            ))

        return ContactListResponse(
            items=items,
            total=len(items),
            pending_count=pending_count
        )

    except Exception as e:
        print(f"[Contact Admin Error] {e}")
        raise HTTPException(status_code=500, detail="문의 목록 조회 실패")


@router.get("/admin/{contact_id}", response_model=ContactItem)
async def get_contact_detail(
    contact_id: int,
    admin: dict = Depends(get_current_admin_required),
    db: DatabaseManager = Depends(get_db)
):
    """[관리자] 문의 상세 조회"""
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    return ContactItem(
        id=contact['id'],
        user_id=contact.get('user_id'),
        username=contact.get('username'),
        name=contact.get('name'),
        email=contact.get('email'),
        message=contact['message'],
        status=contact['status'],
        admin_reply=contact.get('admin_reply'),
        created_at=contact['created_at'],
        replied_at=contact.get('replied_at')
    )


@router.put("/admin/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    reply: ContactReplyRequest,
    admin: dict = Depends(get_current_admin_required),
    db: DatabaseManager = Depends(get_db)
):
    """[관리자] 문의 상태/답변 업데이트"""
    if reply.status not in ['pending', 'replied', 'resolved']:
        raise HTTPException(status_code=400, detail="유효하지 않은 상태입니다.")

    success = db.update_contact_status(
        contact_id=contact_id,
        status=reply.status,
        admin_reply=reply.admin_reply
    )

    if success:
        return ContactResponse(success=True, message="업데이트 완료")
    else:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
