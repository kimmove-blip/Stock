"""
문의하기 API 라우터
- 문의 접수 및 이메일 전송
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

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


def send_contact_email(contact: ContactRequest) -> bool:
    """문의 내용을 관리자에게 이메일 전송"""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    admin_email = os.getenv("SENDER_EMAIL")  # 관리자 이메일 (본인에게)

    if not all([sender_email, sender_password]):
        print("이메일 설정이 없습니다")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = admin_email
        msg['Subject'] = f"[AI주식분석] 새로운 문의 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        body = f"""
새로운 문의가 접수되었습니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
접수 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
사용자: {contact.username or '비로그인'}
이메일: {contact.email or '미입력'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

문의 내용:
{contact.message}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        print(f"문의 이메일 전송 완료: {contact.username}")
        return True

    except Exception as e:
        print(f"이메일 전송 실패: {e}")
        return False


@router.post("", response_model=ContactResponse)
async def submit_contact(contact: ContactRequest):
    """
    문의 접수

    문의 내용을 관리자 이메일로 전송합니다.
    """
    if not contact.message or len(contact.message.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="문의 내용은 최소 10자 이상 입력해주세요."
        )

    # 이메일 전송
    success = send_contact_email(contact)

    if success:
        return ContactResponse(
            success=True,
            message="문의가 정상적으로 접수되었습니다. 빠른 시일 내에 답변 드리겠습니다."
        )
    else:
        # 이메일 실패해도 일단 성공으로 처리 (로그에 기록됨)
        return ContactResponse(
            success=True,
            message="문의가 접수되었습니다."
        )
