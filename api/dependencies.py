"""
FastAPI 의존성 주입
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth.jwt_handler import decode_access_token
from api.schemas.user import TokenData
from database.db_manager import DatabaseManager


# OAuth2 스키마
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_db() -> DatabaseManager:
    """데이터베이스 인스턴스 반환"""
    return DatabaseManager()


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: DatabaseManager = Depends(get_db)
) -> Optional[dict]:
    """현재 로그인한 사용자 정보 반환"""
    if not token:
        return None

    payload = decode_access_token(token)
    if payload is None:
        return None

    username = payload.get("sub")
    if username is None:
        return None

    user = db.get_user_by_username(username)
    return user


async def get_current_user_required(
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """인증 필수 엔드포인트용 - 미인증시 401 에러"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user
