"""
Streamlit 인증 모듈
- streamlit-authenticator 래퍼
- DB 연동
"""

import streamlit as st
import streamlit_authenticator as stauth
from pathlib import Path
import os
import secrets

# 상위 디렉토리의 database 모듈 import
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager


class StockAuthenticator:
    """주식 분석 시스템 인증 클래스"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = self._build_config()
        self.authenticator = self._create_authenticator()

    def _get_cookie_key(self):
        """쿠키 암호화 키 (환경변수 또는 자동 생성)"""
        key = os.getenv('AUTH_COOKIE_KEY')
        if not key:
            # 키가 없으면 세션 기반으로 임시 키 사용
            if 'auth_cookie_key' not in st.session_state:
                st.session_state['auth_cookie_key'] = secrets.token_hex(32)
            key = st.session_state['auth_cookie_key']
        return key

    def _build_config(self):
        """DB에서 사용자 정보를 읽어 config 생성"""
        users = self.db.get_all_users()

        credentials = {
            'usernames': {}
        }

        for user in users:
            credentials['usernames'][user['username']] = {
                'email': user['email'],
                'name': user['name'],
                'password': user['password_hash'],
                'failed_login_attempts': 0,
                'logged_in': False
            }

        return {
            'credentials': credentials,
            'cookie': {
                'name': 'stock_auth_cookie',
                'key': self._get_cookie_key(),
                'expiry_days': 30
            },
            'pre-authorized': {
                'emails': []
            }
        }

    def _create_authenticator(self):
        """Authenticator 객체 생성"""
        return stauth.Authenticate(
            self.config['credentials'],
            self.config['cookie']['name'],
            self.config['cookie']['key'],
            self.config['cookie']['expiry_days']
        )

    def login(self):
        """로그인 위젯 표시"""
        try:
            self.authenticator.login(
                fields={
                    'Form name': '로그인',
                    'Username': '아이디',
                    'Password': '비밀번호',
                    'Login': '로그인'
                }
            )
        except Exception as e:
            st.error(f"로그인 오류: {e}")

    def logout(self, location='sidebar'):
        """로그아웃"""
        self.authenticator.logout('로그아웃', location=location)

    def register_user(self):
        """회원가입 위젯 (직접 구현)"""
        with st.form("register_form"):
            st.subheader("회원가입")
            name = st.text_input("이름")
            email = st.text_input("이메일")
            username = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            password2 = st.text_input("비밀번호 확인", type="password")

            submitted = st.form_submit_button("가입하기", type="primary", use_container_width=True)

            if submitted:
                # 유효성 검사
                if not all([name, email, username, password, password2]):
                    return False, "모든 필드를 입력해주세요."
                if password != password2:
                    return False, "비밀번호가 일치하지 않습니다."
                if len(password) < 4:
                    return False, "비밀번호는 4자 이상이어야 합니다."
                if self.db.get_user_by_username(username):
                    return False, "이미 사용 중인 아이디입니다."

                # 비밀번호 해시
                password_hash = stauth.Hasher.hash(password)

                # DB에 저장
                self.db.create_user(email, username, password_hash, name)

                # config 갱신
                self.refresh_config()

                return True, "회원가입이 완료되었습니다!"

        return False, None

    def reset_password(self):
        """비밀번호 재설정"""
        if not self.is_authenticated:
            return False, "로그인이 필요합니다"

        try:
            if self.authenticator.reset_password(
                st.session_state['username'],
                fields={
                    'Form name': '비밀번호 변경',
                    'Current password': '현재 비밀번호',
                    'New password': '새 비밀번호',
                    'Repeat password': '새 비밀번호 확인',
                    'Reset': '변경하기'
                }
            ):
                # DB 업데이트
                username = st.session_state['username']
                new_hash = self.config['credentials']['usernames'][username]['password']
                self.db.update_password(username, new_hash)
                return True, "비밀번호가 변경되었습니다"
        except stauth.ResetError as e:
            return False, str(e)
        except Exception as e:
            return False, f"비밀번호 변경 오류: {e}"

        return False, None

    @property
    def is_authenticated(self):
        """인증 여부 확인"""
        return st.session_state.get('authentication_status') == True

    @property
    def authentication_status(self):
        """인증 상태 반환 (True/False/None)"""
        return st.session_state.get('authentication_status')

    @property
    def current_username(self):
        """현재 로그인한 username"""
        if self.is_authenticated:
            return st.session_state.get('username')
        return None

    @property
    def current_name(self):
        """현재 로그인한 사용자 이름"""
        if self.is_authenticated:
            return st.session_state.get('name')
        return None

    def get_user_id(self):
        """현재 로그인한 사용자의 DB ID"""
        if self.is_authenticated:
            username = st.session_state.get('username')
            user = self.db.get_user_by_username(username)
            if user:
                # 마지막 로그인 시간 업데이트
                self.db.update_last_login(user['id'])
                return user['id']
        return None

    def refresh_config(self):
        """설정 새로고침 (회원가입 후)"""
        self.config = self._build_config()
        self.authenticator = self._create_authenticator()
