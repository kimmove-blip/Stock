"""
인증 API 라우터
- 회원가입, 로그인, 사용자 정보 조회, Google OAuth
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

from api.schemas.user import UserCreate, UserLogin, UserResponse, Token
from api.auth.jwt_handler import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_token_expiry_seconds
)
from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager

# Google OAuth
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Google OAuth 설정
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


class GoogleLoginRequest(BaseModel):
    """Google 로그인 요청"""
    credential: str  # Google ID 토큰


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # 분당 5회 제한
async def register(request: Request, user: UserCreate, db: DatabaseManager = Depends(get_db)):
    """회원가입 (Rate Limited: 분당 5회)"""
    # 중복 확인
    if db.get_user_by_username(user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 사용 중인 아이디입니다"
        )

    if user.email and db.get_user_by_email(user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 사용 중인 이메일입니다"
        )

    # 사용자 생성
    password_hash = get_password_hash(user.password)
    user_id = db.create_user(
        email=user.email or f"{user.username}@placeholder.local",
        username=user.username,
        password_hash=password_hash,
        name=user.name or user.username,
        email_subscription=False
    )

    return UserResponse(
        id=user_id,
        username=user.username,
        email=user.email,
        name=user.name or user.username,
        email_subscription=False
    )


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")  # 분당 10회 제한
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: DatabaseManager = Depends(get_db)):
    """로그인 (JWT 토큰 발급) - Rate Limited: 분당 10회"""
    user = db.get_user_by_username(form_data.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 마지막 로그인 시간 업데이트
    db.update_last_login(user['id'])

    # JWT 토큰 생성
    access_token = create_access_token(
        data={"sub": user['username'], "user_id": user['id']}
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=get_token_expiry_seconds()
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user_required)):
    """현재 로그인한 사용자 정보"""
    return UserResponse(
        id=current_user['id'],
        username=current_user['username'],
        email=current_user.get('email'),
        name=current_user.get('name'),
        email_subscription=bool(current_user.get('email_subscription', 0)),
        is_admin=bool(current_user.get('is_admin', 0)),
        auto_trade_enabled=bool(current_user.get('auto_trade_enabled', 0)),
        profile_picture=current_user.get('profile_picture'),
        score_version=current_user.get('score_version', 'v2')
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: dict = Depends(get_current_user_required)):
    """토큰 갱신"""
    access_token = create_access_token(
        data={"sub": current_user['username'], "user_id": current_user['id']}
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=get_token_expiry_seconds()
    )


class UserSettingsUpdate(BaseModel):
    """사용자 설정 업데이트"""
    email_subscription: bool = None
    score_version: str = None  # AI 스코어 엔진 버전 (v1, v2, v3.5, v4, v5, v6, v7, v8)


@router.put("/settings", response_model=UserResponse)
async def update_user_settings(
    settings: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """사용자 설정 업데이트"""
    user_id = current_user['id']

    with db.get_connection() as conn:
        if settings.email_subscription is not None:
            conn.execute(
                "UPDATE users SET email_subscription = ? WHERE id = ?",
                (1 if settings.email_subscription else 0, user_id)
            )
        if settings.score_version is not None:
            # 유효한 버전인지 확인
            valid_versions = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']
            if settings.score_version in valid_versions:
                conn.execute(
                    "UPDATE users SET score_version = ? WHERE id = ?",
                    (settings.score_version, user_id)
                )
                # 자동매매 설정에도 동기화 (auto_trade.db)
                try:
                    from trading.trade_logger import TradeLogger
                    trade_logger = TradeLogger()
                    existing = trade_logger.get_auto_trade_settings(user_id)
                    if existing:
                        existing['score_version'] = settings.score_version
                        trade_logger.save_auto_trade_settings(user_id, existing)
                except Exception as e:
                    print(f"[Auth] auto_trade_settings 동기화 실패: {e}")
        conn.commit()

    user = db.get_user_by_id(user_id)

    return UserResponse(
        id=user['id'],
        username=user['username'],
        email=user.get('email'),
        name=user.get('name'),
        email_subscription=bool(user.get('email_subscription', 0)),
        is_admin=bool(user.get('is_admin', 0)),
        score_version=user.get('score_version', 'v2')
    )


@router.post("/google", response_model=Token)
@limiter.limit("10/minute")  # 분당 10회 제한
async def google_login(request: Request, login_request: GoogleLoginRequest, db: DatabaseManager = Depends(get_db)):
    """Google 로그인 - Rate Limited: 분당 10회"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google 로그인이 설정되지 않았습니다"
        )

    try:
        # Google ID 토큰 검증 (시간 오차 60초 허용)
        idinfo = id_token.verify_oauth2_token(
            login_request.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=60
        )

        # 이메일, 이름, 프로필 사진 추출
        email = idinfo.get('email')
        name = idinfo.get('name', email.split('@')[0])
        google_id = idinfo.get('sub')
        picture = idinfo.get('picture')  # 구글 프로필 사진 URL

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이메일 정보를 가져올 수 없습니다"
            )

        # 기존 사용자 확인
        user = db.get_user_by_email(email)

        if not user:
            # 새 사용자 생성
            username = email.split('@')[0]  # 이메일 앞부분을 사용자명으로
            base_username = username
            counter = 1

            # 중복 사용자명 처리
            while db.get_user_by_username(username):
                username = f"{base_username}{counter}"
                counter += 1

            # 랜덤 비밀번호 생성 (Google 로그인만 사용)
            import secrets
            random_password = secrets.token_urlsafe(32)
            password_hash = get_password_hash(random_password)

            user_id = db.create_user(
                email=email,
                username=username,
                password_hash=password_hash,
                name=name,
                email_subscription=False
            )

            user = db.get_user_by_email(email)

        # 마지막 로그인 시간 업데이트
        db.update_last_login(user['id'])

        # 프로필 사진 업데이트 (매 로그인 시 최신 사진으로 갱신)
        if picture:
            db.update_profile_picture(user['id'], picture)

        # JWT 토큰 생성
        access_token = create_access_token(
            data={"sub": user['username'], "user_id": user['id']}
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=get_token_expiry_seconds()
        )

    except ValueError as e:
        # 서버 로그에만 상세 기록 (사용자에게는 노출 안함)
        print(f"[Google Login Error] {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 인증에 실패했습니다"
        )
    except Exception as e:
        print(f"[Google Login Error] {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google 로그인 처리 중 오류가 발생했습니다"
        )


@router.delete("/delete-account")
async def delete_account(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """계정 삭제 (모든 관련 데이터 포함)"""
    user_id = current_user['id']
    username = current_user['username']

    try:
        # 사용자 및 관련 데이터 삭제
        db.delete_user(user_id)
        print(f"[Account Deleted] User: {username} (ID: {user_id})")
        return {"message": "계정이 성공적으로 삭제되었습니다"}
    except Exception as e:
        print(f"[Delete Account Error] User: {username}, Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="계정 삭제 중 오류가 발생했습니다"
        )


class AutoTradeSettingRequest(BaseModel):
    """자동매매 권한 설정 요청 (관리자용)"""
    user_id: int
    enabled: bool


@router.put("/admin/auto-trade")
async def set_user_auto_trade(
    setting: AutoTradeSettingRequest,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """사용자 자동매매 권한 설정 (관리자 전용)"""
    # 관리자 권한 확인
    if not current_user.get('is_admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다"
        )

    # 대상 사용자 확인
    target_user = db.get_user_by_id(setting.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다"
        )

    # 자동매매 권한 설정
    db.set_auto_trade_enabled(setting.user_id, setting.enabled)

    return {
        "message": f"자동매매 권한이 {'활성화' if setting.enabled else '비활성화'}되었습니다",
        "user_id": setting.user_id,
        "auto_trade_enabled": setting.enabled
    }
