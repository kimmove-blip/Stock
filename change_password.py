#!/usr/bin/env python3
"""
비밀번호 변경 스크립트
사용법: python change_password.py
"""

import sys
sys.path.insert(0, '.')

import streamlit_authenticator as stauth
from database import DatabaseManager

def main():
    db = DatabaseManager()

    print("=" * 40)
    print("  비밀번호 변경 스크립트")
    print("=" * 40)

    # 등록된 사용자 목록 표시
    users = db.get_all_users()
    if not users:
        print("\n등록된 사용자가 없습니다.")
        return

    print("\n[등록된 사용자 목록]")
    for i, user in enumerate(users, 1):
        print(f"  {i}. {user['username']} ({user['name']}) - {user['email']}")

    print()
    choice = input("비밀번호를 변경할 사용자 (번호 또는 아이디): ").strip()

    # 번호 또는 아이디로 사용자 찾기
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(users):
            user = users[idx]
            username = user['username']
        else:
            print(f"\n오류: 잘못된 번호입니다.")
            return
    else:
        username = choice
        user = db.get_user_by_username(username)
        if not user:
            print(f"\n오류: '{username}' 사용자를 찾을 수 없습니다.")
            return

    print(f"\n사용자 확인: {user['name']} ({user['email']})")

    new_password = input("새 비밀번호: ").strip()
    if len(new_password) < 4:
        print("\n오류: 비밀번호는 4자 이상이어야 합니다.")
        return

    confirm = input("새 비밀번호 확인: ").strip()
    if new_password != confirm:
        print("\n오류: 비밀번호가 일치하지 않습니다.")
        return

    # 비밀번호 해시 및 저장
    password_hash = stauth.Hasher.hash(new_password)
    db.update_password(username, password_hash)

    print(f"\n'{username}' 사용자의 비밀번호가 변경되었습니다.")

if __name__ == "__main__":
    main()
