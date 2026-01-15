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
                    is_active BOOLEAN DEFAULT 1,
                    is_admin BOOLEAN DEFAULT 0
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

                -- 알림 기록 테이블
                CREATE TABLE IF NOT EXISTS alert_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stock_code TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                -- 문의 테이블
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    email TEXT,
                    message TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    admin_reply TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    replied_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                -- 인덱스
                CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);
                CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_alert_history_user ON alert_history(user_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_daily ON alert_history(user_id, stock_code, alert_type, date(created_at));
                CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
            """)
            conn.commit()

            # 기존 users 테이블에 telegram 컬럼 추가 (마이그레이션)
            self._migrate_telegram_columns(conn)

    def _migrate_telegram_columns(self, conn):
        """users 테이블에 telegram 관련 컬럼 추가 (마이그레이션)"""
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'telegram_chat_id' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_chat_id TEXT")

        if 'telegram_alerts_enabled' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_alerts_enabled BOOLEAN DEFAULT 0")

        if 'email_subscription' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN email_subscription BOOLEAN DEFAULT 0")

        if 'is_admin' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")

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
        """username으로 사용자 조회 (대소문자 무시)"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
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

    def create_user(self, email, username, password_hash, name, email_subscription=False):
        """사용자 생성"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, username, password_hash, name, email_subscription) VALUES (?, ?, ?, ?, ?)",
                (email, username, password_hash, name, 1 if email_subscription else 0)
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

    def is_admin(self, user_id):
        """사용자가 관리자인지 확인"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT is_admin FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            return bool(row['is_admin']) if row else False

    def set_admin(self, user_id, is_admin=True):
        """관리자 권한 설정"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, user_id)
            )
            conn.commit()
            return True

    def get_user_by_id(self, user_id):
        """ID로 사용자 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_user(self, user_id):
        """사용자 및 모든 관련 데이터 삭제 (CASCADE로 자동 삭제)"""
        with self.get_connection() as conn:
            # 사용자 삭제 (watchlists, portfolios, alert_history는 CASCADE로 자동 삭제)
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True

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

    def clear_watchlist(self, user_id):
        """사용자의 모든 관심종목 삭제"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM watchlists WHERE user_id = ?", (user_id,))
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

    # ==================== 텔레그램 알림 설정 ====================

    def update_telegram_settings(self, user_id, chat_id, enabled):
        """텔레그램 설정 업데이트"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET telegram_chat_id = ?, telegram_alerts_enabled = ? WHERE id = ?",
                (chat_id, 1 if enabled else 0, user_id)
            )
            conn.commit()

    def get_telegram_settings(self, user_id):
        """텔레그램 설정 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT telegram_chat_id, telegram_alerts_enabled FROM users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'chat_id': row['telegram_chat_id'] or '',
                    'enabled': bool(row['telegram_alerts_enabled'])
                }
            return {'chat_id': '', 'enabled': False}

    def get_users_with_telegram_enabled(self):
        """텔레그램 알림이 활성화된 사용자 목록"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, username, name, telegram_chat_id FROM users WHERE telegram_alerts_enabled = 1 AND telegram_chat_id IS NOT NULL AND is_active = 1"
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 알림 기록 ====================

    def add_alert_history(self, user_id, stock_code, alert_type, message=None):
        """알림 기록 추가"""
        with self.get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO alert_history (user_id, stock_code, alert_type, message) VALUES (?, ?, ?, ?)",
                    (user_id, stock_code, alert_type, message)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # 오늘 이미 알림 전송됨

    def was_alert_sent_today(self, user_id, stock_code, alert_type):
        """오늘 해당 알림이 이미 전송되었는지 확인"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM alert_history WHERE user_id = ? AND stock_code = ? AND alert_type = ? AND date(created_at) = date('now')",
                (user_id, stock_code, alert_type)
            )
            return cursor.fetchone() is not None

    def get_alert_history(self, user_id, days=7):
        """사용자의 최근 알림 기록 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT stock_code, alert_type, message, created_at FROM alert_history WHERE user_id = ? AND created_at >= datetime('now', ? || ' days') ORDER BY created_at DESC",
                (user_id, -days)
            )
            return [dict(row) for row in cursor.fetchall()]

    def clear_alert_history(self, user_id):
        """사용자의 모든 알림 기록 삭제"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM alert_history WHERE user_id = ?", (user_id,))
            conn.commit()

    # ==================== 이메일 구독 ====================

    def get_email_subscribers(self):
        """이메일 구독자 목록 (이메일 주소 리스트)"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT email FROM users WHERE email_subscription = 1 AND is_active = 1"
            )
            return [row['email'] for row in cursor.fetchall()]

    def update_email_subscription(self, user_id, subscribed):
        """이메일 구독 설정 변경"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET email_subscription = ? WHERE id = ?",
                (1 if subscribed else 0, user_id)
            )
            conn.commit()

    def get_email_subscription(self, user_id):
        """이메일 구독 상태 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT email_subscription FROM users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return bool(row['email_subscription']) if row else False

    # ==================== 문의 관련 ====================

    def add_contact(self, message, user_id=None, username=None, email=None):
        """문의 추가"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO contacts (user_id, username, email, message) VALUES (?, ?, ?, ?)",
                (user_id, username, email, message)
            )
            conn.commit()
            return cursor.lastrowid

    def get_contacts(self, status=None, limit=50):
        """문의 목록 조회 (관리자용)"""
        with self.get_connection() as conn:
            base_query = """
                SELECT c.*, u.name
                FROM contacts c
                LEFT JOIN users u ON c.user_id = u.id
            """
            if status:
                cursor = conn.execute(
                    f"{base_query} WHERE c.status = ? ORDER BY c.created_at DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor = conn.execute(
                    f"{base_query} ORDER BY c.created_at DESC LIMIT ?",
                    (limit,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_contact_by_id(self, contact_id):
        """특정 문의 조회"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT c.*, u.name
                   FROM contacts c
                   LEFT JOIN users u ON c.user_id = u.id
                   WHERE c.id = ?""",
                (contact_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_contact_status(self, contact_id, status, admin_reply=None):
        """문의 상태 업데이트"""
        with self.get_connection() as conn:
            if admin_reply:
                conn.execute(
                    "UPDATE contacts SET status = ?, admin_reply = ?, replied_at = ? WHERE id = ?",
                    (status, admin_reply, datetime.now(), contact_id)
                )
            else:
                conn.execute(
                    "UPDATE contacts SET status = ? WHERE id = ?",
                    (status, contact_id)
                )
            conn.commit()

    def get_pending_contacts_count(self):
        """대기 중인 문의 수"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM contacts WHERE status = 'pending'"
            )
            return cursor.fetchone()['count']
