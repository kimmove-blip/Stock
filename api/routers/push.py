"""
웹 푸시 알림 설정 API 라우터
- 푸시 구독 등록/해제
- 알림 ON/OFF 설정
- 테스트 알림 전송
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager

router = APIRouter()

# VAPID 키 로드
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:admin@example.com")


class PushSubscriptionKeys(BaseModel):
    """푸시 구독 키"""
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    """푸시 구독 요청"""
    endpoint: str
    keys: PushSubscriptionKeys


class PushSettingsResponse(BaseModel):
    """푸시 설정 응답"""
    enabled: bool = False
    subscription_count: int = 0
    vapid_public_key: str = ""


class PushSettingsUpdate(BaseModel):
    """푸시 설정 업데이트"""
    enabled: bool


def send_push_notification(subscription: dict, title: str, body: str, url: str = None) -> bool:
    """푸시 알림 전송"""
    try:
        from pywebpush import webpush, WebPushException

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-72x72.png",
            "url": url or "/"
        })

        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"]
                }
            },
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_EMAIL}
        )
        return True
    except Exception as e:
        print(f"[푸시] 알림 전송 실패: {e}")
        return False


def send_push_to_user(user_id: int, title: str, body: str, url: str = None) -> int:
    """특정 사용자에게 푸시 알림 전송 (외부 호출용)

    Args:
        user_id: 사용자 ID
        title: 알림 제목
        body: 알림 내용
        url: 클릭 시 이동할 URL

    Returns:
        성공한 알림 개수
    """
    try:
        db = DatabaseManager()
        subscriptions = db.get_all_push_subscriptions_for_user(user_id)

        if not subscriptions:
            print(f"[푸시] user_id={user_id}: 등록된 구독 없음")
            return 0

        success_count = 0
        for sub in subscriptions:
            if send_push_notification(sub, title, body, url):
                success_count += 1

        print(f"[푸시] user_id={user_id}: {success_count}/{len(subscriptions)}개 전송 성공")
        return success_count
    except Exception as e:
        print(f"[푸시] user_id={user_id} 전송 오류: {e}")
        return 0


@router.get("", response_model=PushSettingsResponse)
async def get_push_settings(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """푸시 알림 설정 조회"""
    settings = db.get_push_settings(current_user["id"])

    return PushSettingsResponse(
        enabled=settings["enabled"],
        subscription_count=settings["subscription_count"],
        vapid_public_key=VAPID_PUBLIC_KEY
    )


@router.post("/subscribe")
async def subscribe_push(
    subscription: PushSubscriptionRequest,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """푸시 알림 구독"""
    user_id = current_user["id"]

    # 구독 정보 저장
    sub_id = db.add_push_subscription(
        user_id=user_id,
        endpoint=subscription.endpoint,
        p256dh=subscription.keys.p256dh,
        auth=subscription.keys.auth
    )

    return {
        "success": True,
        "message": "푸시 알림이 활성화되었습니다",
        "subscription_id": sub_id
    }


@router.delete("/unsubscribe")
async def unsubscribe_push(
    endpoint: Optional[str] = None,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """푸시 알림 구독 해제"""
    user_id = current_user["id"]

    db.remove_push_subscription(user_id, endpoint)

    return {
        "success": True,
        "message": "푸시 알림이 비활성화되었습니다"
    }


@router.post("/settings")
async def update_push_settings(
    settings: PushSettingsUpdate,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """푸시 알림 설정 업데이트"""
    user_id = current_user["id"]

    db.update_push_settings(user_id, settings.enabled)

    return {
        "success": True,
        "enabled": settings.enabled
    }


@router.post("/test")
async def test_push(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """테스트 푸시 알림 전송"""
    user_id = current_user["id"]
    subscriptions = db.get_all_push_subscriptions_for_user(user_id)

    if not subscriptions:
        raise HTTPException(
            status_code=400,
            detail="등록된 푸시 구독이 없습니다. 먼저 알림을 활성화해주세요."
        )

    username = current_user.get("name") or current_user.get("username", "사용자")
    success_count = 0

    for sub in subscriptions:
        if send_push_notification(
            sub,
            title="테스트 알림",
            body=f"{username}님, 알림이 정상적으로 작동합니다!",
            url="/"
        ):
            success_count += 1

    if success_count > 0:
        return {
            "success": True,
            "message": f"테스트 알림이 전송되었습니다 ({success_count}개)"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="알림 전송에 실패했습니다. 브라우저 알림 권한을 확인해주세요."
        )


@router.get("/vapid-key")
async def get_vapid_key():
    """VAPID 공개키 조회 (인증 불필요)"""
    return {"vapid_public_key": VAPID_PUBLIC_KEY}
