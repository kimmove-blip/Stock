"""
SQLite 데이터베이스 관리 모듈
- 사용자, 관심종목, 포트폴리오 CRUD
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager


class DatabaseManager:
    """SQLite 데이터베이스 관리 클래스"""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent / "stock_data.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """테이블 생성"""
        with self.get_connection() as conn:
            conn.executescript("""
                -- 사용자 테이블
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                );

                -- 관심종목 테이블
                CREATE TABLE IF NOT EXISTS watchlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL DEFAULT '기본',
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, category, stock_code)
                );

                -- 포트폴리오 테이블
                CREATE TABLE IF NOT EXISTS portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    buy_price REAL NOT NULL DEFAULT 0,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    buy_date DATE,
                    memo TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                -- 인덱스
                CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);
                CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            """)
            conn.commit()

    # ==================== 사용자 관련 ====================

    def get_all_users(self):
        """모든 사용자 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, email, username, password_hash, name, created_at, is_active FROM users WHERE is_active = 1"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_user_by_username(self, username):
        """username으로 사용자 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email):
        """email로 사용자 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_user(self, email, username, password_hash, name):
        """사용자 생성"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, username, password_hash, name) VALUES (?, ?, ?, ?)",
                (email, username, password_hash, name)
            )
            conn.commit()
            return cursor.lastrowid

    def update_password(self, username, new_password_hash):
        """비밀번호 업데이트"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (new_password_hash, username)
            )
            conn.commit()

    def update_last_login(self, user_id):
        """마지막 로그인 시간 업데이트"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now(), user_id)
            )
            conn.commit()

    # ==================== 관심종목 관련 ====================

    def get_watchlists(self, user_id):
        """사용자의 모든 관심종목 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT category, stock_code, stock_name FROM watchlists WHERE user_id = ? ORDER BY category, added_at",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_watchlist_categories(self, user_id):
        """사용자의 관심종목 카테고리 목록"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT category FROM watchlists WHERE user_id = ? ORDER BY category",
                (user_id,)
            )
            categories = [row['category'] for row in cursor.fetchall()]
            if not categories:
                categories = ['기본']
            return categories

    def add_to_watchlist(self, user_id, category, stock_code, stock_name):
        """관심종목 추가"""
        with self.get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO watchlists (user_id, category, stock_code, stock_name) VALUES (?, ?, ?, ?)",
                    (user_id, category, stock_code, stock_name)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # 이미 존재

    def remove_from_watchlist(self, user_id, category, stock_code):
        """관심종목 삭제"""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM watchlists WHERE user_id = ? AND category = ? AND stock_code = ?",
                (user_id, category, stock_code)
            )
            conn.commit()

    def create_watchlist_category(self, user_id, category):
        """새 카테고리 생성 (빈 카테고리 - 기본 더미 항목 추가)"""
        # SQLite에서 빈 카테고리를 만들 수 없으므로, 카테고리만 생성하는 방법은
        # 실제로 종목 추가 시 자동으로 생성됨
        pass

    def delete_watchlist_category(self, user_id, category):
        """카테고리 및 해당 종목 전체 삭제"""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM watchlists WHERE user_id = ? AND category = ?",
                (user_id, category)
            )
            conn.commit()

    def move_watchlist_item(self, user_id, stock_code, from_category, to_category):
        """관심종목 카테고리 이동"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE watchlists SET category = ? WHERE user_id = ? AND category = ? AND stock_code = ?",
                (to_category, user_id, from_category, stock_code)
            )
            conn.commit()

    # ==================== 포트폴리오 관련 ====================

    def get_portfolio(self, user_id):
        """사용자의 포트폴리오 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, stock_code, stock_name, buy_price, quantity, buy_date, memo FROM portfolios WHERE user_id = ? ORDER BY created_at",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_portfolio_item(self, user_id, stock_code, stock_name, buy_price, quantity, buy_date=None, memo=None):
        """포트폴리오 항목 추가"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO portfolios (user_id, stock_code, stock_name, buy_price, quantity, buy_date, memo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, stock_code, stock_name, buy_price, quantity, buy_date, memo)
            )
            conn.commit()
            return cursor.lastrowid

    def update_portfolio_item(self, item_id, **kwargs):
        """포트폴리오 항목 수정"""
        if not kwargs:
            return

        allowed_fields = {'stock_code', 'stock_name', 'buy_price', 'quantity', 'buy_date', 'memo'}
        fields = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields:
            return

        fields['updated_at'] = datetime.now()

        set_clause = ', '.join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [item_id]

        with self.get_connection() as conn:
            conn.execute(
                f"UPDATE portfolios SET {set_clause} WHERE id = ?",
                values
            )
            conn.commit()

    def delete_portfolio_item(self, item_id):
        """포트폴리오 항목 삭제"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM portfolios WHERE id = ?", (item_id,))
            conn.commit()

    def clear_portfolio(self, user_id):
        """사용자의 포트폴리오 전체 삭제"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM portfolios WHERE user_id = ?", (user_id,))
            conn.commit()

    def bulk_add_portfolio(self, user_id, items):
        """포트폴리오 일괄 추가"""
        with self.get_connection() as conn:
            for item in items:
                conn.execute(
                    "INSERT INTO portfolios (user_id, stock_code, stock_name, buy_price, quantity, buy_date) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, item['stock_code'], item.get('stock_name', ''),
                     item.get('buy_price', 0), item.get('quantity', 1), item.get('buy_date'))
                )
            conn.commit()
