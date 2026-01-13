"""
텔레그램 알림 설정 API 라우터
- Chat ID 등록/검증
- 알림 ON/OFF 설정
- 테스트 메시지 전송
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import sys
import os
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager
from config import TelegramConfig

router = APIRouter()


class TelegramSettingsRequest(BaseModel):
    """텔레그램 설정 요청"""
    chat_id: Optional[str] = None
    alerts_enabled: Optional[bool] = None


class TelegramSettingsResponse(BaseModel):
    """텔레그램 설정 응답"""
    chat_id: Optional[str] = None
    alerts_enabled: bool = False
    is_verified: bool = False


class TelegramTestRequest(BaseModel):
    """텔레그램 테스트 요청"""
    chat_id: str


def send_telegram_message(chat_id: str, message: str) -> bool:
    """텔레그램 메시지 전송"""
    try:
        api_url = f"https://api.telegram.org/bot{TelegramConfig.BOT_TOKEN}/sendMessage"
        response = requests.post(
            api_url,
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        return response.json().get("ok", False)
    except Exception as e:
        print(f"[텔레그램] 메시지 전송 실패: {e}")
        return False


@router.get("", response_model=TelegramSettingsResponse)
async def get_telegram_settings(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """텔레그램 설정 조회"""
    user = db.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    chat_id = user.get("telegram_chat_id")
    alerts_enabled = user.get("telegram_alerts_enabled", False)

    return TelegramSettingsResponse(
        chat_id=chat_id,
        alerts_enabled=bool(alerts_enabled),
        is_verified=bool(chat_id and alerts_enabled)
    )


@router.post("", response_model=TelegramSettingsResponse)
async def update_telegram_settings(
    settings: TelegramSettingsRequest,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """텔레그램 설정 업데이트"""
    user_id = current_user["id"]

    with db.get_connection() as conn:
        if settings.chat_id is not None:
            conn.execute(
                "UPDATE users SET telegram_chat_id = ? WHERE id = ?",
                (settings.chat_id, user_id)
            )

        if settings.alerts_enabled is not None:
            conn.execute(
                "UPDATE users SET telegram_alerts_enabled = ? WHERE id = ?",
                (1 if settings.alerts_enabled else 0, user_id)
            )

        conn.commit()

    user = db.get_user_by_id(user_id)
    chat_id = user.get("telegram_chat_id")
    alerts_enabled = user.get("telegram_alerts_enabled", False)

    return TelegramSettingsResponse(
        chat_id=chat_id,
        alerts_enabled=bool(alerts_enabled),
        is_verified=bool(chat_id and alerts_enabled)
    )


@router.post("/test")
async def test_telegram(
    request: TelegramTestRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """텔레그램 테스트 메시지 전송"""
    message = f"""<b>주식 알림 서비스 연동 테스트</b>

안녕하세요, {current_user.get('username', '사용자')}님!
텔레그램 알림이 정상적으로 연동되었습니다.

<b>알림 종류:</b>
- 보유종목 하락 알림
- 매도 신호 알림
- 손절 신호 알림

설정에서 알림을 켜시면 실시간 알림을 받으실 수 있습니다."""

    success = send_telegram_message(request.chat_id, message)

    if success:
        return {"success": True, "message": "테스트 메시지가 전송되었습니다"}
    else:
        raise HTTPException(
            status_code=400,
            detail="메시지 전송에 실패했습니다. Chat ID를 확인해주세요."
        )


@router.post("/verify")
async def verify_telegram(
    request: TelegramTestRequest,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """텔레그램 Chat ID 검증 및 저장"""
    user_id = current_user["id"]

    # 테스트 메시지 전송
    message = f"""<b>텔레그램 연동 완료!</b>

{current_user.get('username', '사용자')}님의 계정과 연동되었습니다.
이제 주식 알림을 받으실 수 있습니다.

<b>알림을 받으려면:</b>
앱 설정에서 '알림 받기'를 켜주세요."""

    success = send_telegram_message(request.chat_id, message)

    if success:
        # Chat ID 저장 및 알림 활성화
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE users SET telegram_chat_id = ?, telegram_alerts_enabled = 1 WHERE id = ?",
                (request.chat_id, user_id)
            )
            conn.commit()

        return {
            "success": True,
            "message": "텔레그램이 연동되었습니다",
            "chat_id": request.chat_id,
            "alerts_enabled": True
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Chat ID가 올바르지 않습니다. 봇에게 먼저 메시지를 보내주세요."
        )
