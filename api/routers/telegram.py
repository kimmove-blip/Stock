"""
텔레그램 알림 설정 API 라우터
- 자동 Chat ID 연동
- 알림 ON/OFF 설정
- 테스트 메시지 전송
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import sys
import os
import requests
import secrets
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager
from config import TelegramConfig

router = APIRouter()

# 인증 코드 저장 (메모리, 실제 서비스에서는 Redis 등 사용)
# {code: {"user_id": int, "created_at": float}}
pending_verifications = {}


class TelegramSettingsRequest(BaseModel):
    """텔레그램 설정 요청"""
    alerts_enabled: Optional[bool] = None


class TelegramSettingsResponse(BaseModel):
    """텔레그램 설정 응답"""
    chat_id: Optional[str] = None
    alerts_enabled: bool = False
    is_verified: bool = False


class TelegramVerifyResponse(BaseModel):
    """인증 코드 생성 응답"""
    code: str
    bot_link: str
    expires_in: int = 300  # 5분


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


def get_telegram_updates(offset: int = None) -> list:
    """텔레그램 업데이트(메시지) 조회"""
    try:
        api_url = f"https://api.telegram.org/bot{TelegramConfig.BOT_TOKEN}/getUpdates"
        params = {"timeout": 1}
        if offset:
            params["offset"] = offset

        response = requests.get(api_url, params=params, timeout=10)
        result = response.json()

        if result.get("ok"):
            return result.get("result", [])
        return []
    except Exception as e:
        print(f"[텔레그램] 업데이트 조회 실패: {e}")
        return []


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
        is_verified=bool(chat_id)
    )


@router.post("", response_model=TelegramSettingsResponse)
async def update_telegram_settings(
    settings: TelegramSettingsRequest,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """텔레그램 설정 업데이트 (알림 ON/OFF)"""
    user_id = current_user["id"]

    with db.get_connection() as conn:
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
        is_verified=bool(chat_id)
    )


@router.post("/generate-code", response_model=TelegramVerifyResponse)
async def generate_verification_code(
    current_user: dict = Depends(get_current_user_required)
):
    """인증 코드 생성 - 사용자가 봇에 보낼 코드"""
    user_id = current_user["id"]

    # 기존 코드 제거
    codes_to_remove = [code for code, data in pending_verifications.items()
                       if data["user_id"] == user_id]
    for code in codes_to_remove:
        del pending_verifications[code]

    # 새 코드 생성 (6자리)
    code = secrets.token_hex(3).upper()  # 예: A1B2C3

    pending_verifications[code] = {
        "user_id": user_id,
        "username": current_user.get("username", ""),
        "created_at": time.time()
    }

    # 봇 딥링크 (사용자가 클릭하면 봇 채팅이 열리고 /start CODE가 자동 입력됨)
    bot_username = "fa_hckim0402_bot"
    bot_link = f"https://t.me/{bot_username}?start={code}"

    return TelegramVerifyResponse(
        code=code,
        bot_link=bot_link,
        expires_in=300
    )


@router.post("/check-verification")
async def check_verification(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """인증 상태 확인 - 봇에서 메시지를 받았는지 체크"""
    user_id = current_user["id"]

    # 해당 사용자의 대기 중인 인증 코드 찾기
    user_code = None
    for code, data in pending_verifications.items():
        if data["user_id"] == user_id:
            # 5분 만료 체크
            if time.time() - data["created_at"] > 300:
                del pending_verifications[code]
                continue
            user_code = code
            break

    if not user_code:
        return {"verified": False, "message": "인증 코드가 없거나 만료되었습니다"}

    # 텔레그램 업데이트 확인
    updates = get_telegram_updates()

    for update in updates:
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not text or not chat_id:
            continue

        # /start CODE 형식 또는 그냥 /start 체크
        is_start_with_code = text.startswith("/start ") and text.replace("/start ", "").strip().upper() == user_code
        is_plain_start = text == "/start"

        if is_start_with_code or is_plain_start:
            # 인증 성공! Chat ID 저장
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE users SET telegram_chat_id = ?, telegram_alerts_enabled = 1 WHERE id = ?",
                    (chat_id, user_id)
                )
                conn.commit()

            # 대기 목록에서 제거
            del pending_verifications[user_code]

            # 환영 메시지 전송
            username = current_user.get("username", "사용자")
            welcome_msg = f"""<b>연동 완료!</b>

{username}님의 계정과 텔레그램이 연동되었습니다.

<b>알림 종류:</b>
- 보유종목 하락 알림
- 매도 신호 알림
- 손절 신호 알림

설정에서 알림을 켜시면 실시간 알림을 받으실 수 있습니다."""
            send_telegram_message(chat_id, welcome_msg)

            # 처리된 업데이트 확인 (offset 설정으로 다음 요청에서 제외)
            try:
                get_telegram_updates(offset=update.get("update_id", 0) + 1)
            except:
                pass

            return {
                "verified": True,
                "message": "텔레그램 연동이 완료되었습니다",
                "chat_id": chat_id
            }

    return {"verified": False, "message": "아직 인증되지 않았습니다. 봇에 메시지를 보내주세요."}


@router.post("/disconnect")
async def disconnect_telegram(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """텔레그램 연동 해제"""
    user_id = current_user["id"]

    with db.get_connection() as conn:
        conn.execute(
            "UPDATE users SET telegram_chat_id = NULL, telegram_alerts_enabled = 0 WHERE id = ?",
            (user_id,)
        )
        conn.commit()

    return {"success": True, "message": "텔레그램 연동이 해제되었습니다"}


@router.post("/test")
async def test_telegram(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """테스트 메시지 전송"""
    user = db.get_user_by_id(current_user["id"])
    chat_id = user.get("telegram_chat_id")

    if not chat_id:
        raise HTTPException(status_code=400, detail="텔레그램이 연동되지 않았습니다")

    message = f"""<b>테스트 메시지</b>

{current_user.get('username', '사용자')}님, 알림이 정상적으로 작동합니다!

<b>알림 종류:</b>
- 보유종목 하락 알림
- 매도 신호 알림
- 손절 신호 알림"""

    success = send_telegram_message(chat_id, message)

    if success:
        return {"success": True, "message": "테스트 메시지가 전송되었습니다"}
    else:
        raise HTTPException(status_code=500, detail="메시지 전송에 실패했습니다")
