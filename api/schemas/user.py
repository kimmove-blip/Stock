"""
사용자 관련 Pydantic 스키마
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """사용자 기본 정보"""
    username: str = Field(..., min_length=3, max_length=50, description="사용자 아이디")
    email: Optional[EmailStr] = Field(None, description="이메일 주소")


class UserCreate(UserBase):
    """회원가입 요청"""
    password: str = Field(..., min_length=6, description="비밀번호")
    name: Optional[str] = Field(None, description="이름")


class UserLogin(BaseModel):
    """로그인 요청"""
    username: str = Field(..., description="사용자 아이디")
    password: str = Field(..., description="비밀번호")


class UserResponse(UserBase):
    """사용자 응답"""
    id: int
    name: Optional[str] = None
    email_subscription: bool = False
    is_admin: bool = False
    auto_trade_enabled: bool = False
    profile_picture: Optional[str] = None
    score_version: str = "v5"  # AI 스코어 엔진 버전
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT 토큰 응답"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="토큰 만료 시간 (초)")


class TokenData(BaseModel):
    """토큰 페이로드 데이터"""
    username: Optional[str] = None
    user_id: Optional[int] = None
