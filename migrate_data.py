#!/usr/bin/env python3
"""
기존 데이터를 새 DB로 마이그레이션하는 스크립트

기존 데이터:
- watchlist.json → DB watchlists 테이블
- output/my_portfolio.xlsx → DB portfolios 테이블

사용법:
    python migrate_data.py                    # 기본 실행 (admin 계정 생성)
    python migrate_data.py --username myuser  # 특정 사용자로 마이그레이션
"""

import argparse
import json
import os
import pandas as pd
import streamlit_authenticator as stauth
from pathlib import Path
from database import DatabaseManager


def migrate_watchlist(db, user_id, watchlist_file="watchlist.json"):
    """관심종목 마이그레이션"""
    if not os.path.exists(watchlist_file):
        print(f"[건너뜀] 관심종목 파일 없음: {watchlist_file}")
        return 0

    with open(watchlist_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 리스트 형태인 경우 (구버전)
    if isinstance(data, list):
        data = {"기본": data}

    count = 0
    for category, stocks in data.items():
        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            if code:
                if db.add_to_watchlist(user_id, category, code, name):
                    count += 1
                    print(f"  [추가] {category} - {name} ({code})")

    return count


def migrate_portfolio(db, user_id, portfolio_file="output/my_portfolio.xlsx"):
    """포트폴리오 마이그레이션"""
    if not os.path.exists(portfolio_file):
        print(f"[건너뜀] 포트폴리오 파일 없음: {portfolio_file}")
        return 0

    try:
        # 잔고 시트가 있으면 사용
        xl = pd.ExcelFile(portfolio_file)
        if '잔고' in xl.sheet_names:
            df = pd.read_excel(portfolio_file, sheet_name='잔고')
        else:
            df = pd.read_excel(portfolio_file)
    except Exception as e:
        print(f"[오류] 포트폴리오 파일 읽기 실패: {e}")
        return 0

    count = 0
    for _, row in df.iterrows():
        code = str(row.get('종목코드', '')).zfill(6)
        if not code or code == '000000':
            continue

        name = row.get('종목명', '')
        buy_price = float(row.get('매수가', 0))
        qty = int(row.get('잔고수량', row.get('수량', 1)))
        buy_date = row.get('최종매수일', row.get('매수일'))
        # Timestamp를 문자열로 변환
        if pd.notna(buy_date):
            buy_date = str(buy_date)[:10] if hasattr(buy_date, 'strftime') else str(buy_date)[:10]
        else:
            buy_date = None

        if qty > 0:  # 잔고수량 0인 항목 제외
            db.add_portfolio_item(user_id, code, name, buy_price, qty, buy_date)
            count += 1
            print(f"  [추가] {name} ({code}) - {qty}주 @ {buy_price:,.0f}원")

    return count


def create_initial_user(db, username="admin", password="admin123", email="admin@example.com", name="관리자"):
    """초기 관리자 계정 생성"""
    # 이미 존재하는지 확인
    existing = db.get_user_by_username(username)
    if existing:
        print(f"[정보] 사용자 '{username}'이(가) 이미 존재합니다.")
        return existing['id']

    # 비밀번호 해싱 (streamlit-authenticator 0.4.x API)
    hasher = stauth.Hasher()
    password_hash = hasher.hash(password)

    # 사용자 생성
    user_id = db.create_user(email, username, password_hash, name)
    print(f"[생성] 사용자 생성됨: {username} (ID: {user_id})")
    print(f"       이메일: {email}")
    print(f"       비밀번호: {password}")

    return user_id


def main():
    parser = argparse.ArgumentParser(description="기존 데이터를 DB로 마이그레이션")
    parser.add_argument('--username', default='admin', help='마이그레이션할 사용자 이름')
    parser.add_argument('--password', default='admin123', help='초기 비밀번호')
    parser.add_argument('--email', default='admin@example.com', help='이메일')
    parser.add_argument('--name', default='관리자', help='표시 이름')
    parser.add_argument('--watchlist', default='watchlist.json', help='관심종목 파일')
    parser.add_argument('--portfolio', default='output/my_portfolio.xlsx', help='포트폴리오 파일')

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  데이터 마이그레이션")
    print("=" * 60)

    # DB 초기화
    db = DatabaseManager()
    print(f"\n[DB] 데이터베이스: {db.db_path}")

    # 사용자 생성/확인
    print("\n[1] 사용자 확인/생성")
    user_id = create_initial_user(db, args.username, args.password, args.email, args.name)

    # 관심종목 마이그레이션
    print("\n[2] 관심종목 마이그레이션")
    watchlist_count = migrate_watchlist(db, user_id, args.watchlist)
    print(f"    → {watchlist_count}개 종목 추가됨")

    # 포트폴리오 마이그레이션
    print("\n[3] 포트폴리오 마이그레이션")
    portfolio_count = migrate_portfolio(db, user_id, args.portfolio)
    print(f"    → {portfolio_count}개 종목 추가됨")

    print("\n" + "=" * 60)
    print("  마이그레이션 완료!")
    print("=" * 60)
    print(f"\n로그인 정보:")
    print(f"  아이디: {args.username}")
    print(f"  비밀번호: {args.password}")
    print("\n")


if __name__ == "__main__":
    main()
