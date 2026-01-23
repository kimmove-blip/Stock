"""
거래 기록 모듈
거래 내역 저장 및 성과 분석 + 매수 제안 관리
"""

import sqlite3
import json
import os
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager
from enum import Enum
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def get_encryption_key() -> bytes:
    """암호화 키 생성/조회 (환경변수 또는 파일 기반)"""
    # 환경변수에서 키 조회
    env_key = os.environ.get('AUTO_TRADE_ENCRYPTION_KEY')
    if env_key:
        return env_key.encode()

    # 키 파일 경로
    key_file = Path(__file__).parent.parent / "database" / ".encryption_key"

    if key_file.exists():
        return key_file.read_bytes()

    # 새 키 생성
    key = Fernet.generate_key()
    key_file.parent.mkdir(exist_ok=True)
    key_file.write_bytes(key)
    # 파일 권한 설정 (소유자만 읽기/쓰기)
    os.chmod(key_file, 0o600)
    return key


def encrypt_value(value: str) -> str:
    """값 암호화"""
    if not value:
        return value
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception:
        # 암호화 실패 시 원본 반환 (개발 환경 등)
        return value


def decrypt_value(encrypted_value: str) -> str:
    """값 복호화"""
    if not encrypted_value:
        return encrypted_value
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decoded = base64.urlsafe_b64decode(encrypted_value.encode())
        decrypted = f.decrypt(decoded)
        return decrypted.decode()
    except Exception:
        # 복호화 실패 시 원본 반환 (이미 평문이거나 다른 키로 암호화된 경우)
        return encrypted_value


class SuggestionStatus(Enum):
    """매수 제안 상태"""
    PENDING = "pending"      # 대기 중
    APPROVED = "approved"    # 승인됨
    REJECTED = "rejected"    # 거부됨
    EXPIRED = "expired"      # 만료됨
    EXECUTED = "executed"    # 매수 완료


class TradeLogger:
    """거래 기록기"""

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: DB 파일 경로 (기본: database/auto_trade.db)
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "database" / "auto_trade.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """DB 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """DB 테이블 초기화"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 거래 내역 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    trade_date TEXT NOT NULL,
                    trade_time TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price INTEGER,
                    amount INTEGER,
                    order_no TEXT,
                    order_type TEXT,
                    trade_reason TEXT,
                    status TEXT DEFAULT 'pending',
                    profit_loss INTEGER,
                    profit_rate REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 보유 종목 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    quantity INTEGER NOT NULL,
                    avg_price INTEGER NOT NULL,
                    buy_date TEXT NOT NULL,
                    buy_reason TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, stock_code)
                )
            """)

            # 일별 성과 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    trade_date TEXT NOT NULL,
                    total_assets INTEGER,
                    total_invested INTEGER,
                    total_profit INTEGER,
                    profit_rate REAL,
                    buy_count INTEGER DEFAULT 0,
                    sell_count INTEGER DEFAULT 0,
                    holdings_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, trade_date)
                )
            """)

            # 매수 제안 테이블 (semi-auto 모드용)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_buy_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    score INTEGER,
                    probability REAL,
                    confidence REAL,
                    current_price INTEGER,
                    recommended_price INTEGER,
                    target_price INTEGER,
                    stop_loss_price INTEGER,
                    buy_band_low INTEGER,
                    buy_band_high INTEGER,
                    signals TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT,
                    approved_at TEXT,
                    executed_at TEXT
                )
            """)

            # 모의투자 가상 잔고 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS virtual_balance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    initial_cash INTEGER NOT NULL,
                    current_cash INTEGER NOT NULL,
                    total_invested INTEGER DEFAULT 0,
                    total_eval INTEGER DEFAULT 0,
                    total_profit INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # API 키 설정 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_key_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    app_key TEXT NOT NULL,
                    app_secret TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    account_product_code TEXT DEFAULT '01',
                    is_mock BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 자동매매 설정 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_trade_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    trade_mode TEXT DEFAULT 'manual',
                    max_investment INTEGER DEFAULT 1000000,
                    stock_ratio INTEGER DEFAULT 5,
                    stop_loss_rate REAL DEFAULT -7.0,
                    min_buy_score INTEGER DEFAULT 70,
                    sell_score INTEGER DEFAULT 40,
                    max_holdings INTEGER DEFAULT 10,
                    max_daily_trades INTEGER DEFAULT 10,
                    max_holding_days INTEGER DEFAULT 14,
                    trading_enabled BOOLEAN DEFAULT 1,
                    trading_start_time TEXT DEFAULT '09:00',
                    trading_end_time TEXT DEFAULT '15:20',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 새 컬럼 추가 (기존 테이블 호환)
            new_columns = [
                ("stock_ratio", "INTEGER DEFAULT 5"),
                ("min_buy_score", "INTEGER DEFAULT 70"),
                ("sell_score", "INTEGER DEFAULT 40"),
                ("max_holdings", "INTEGER DEFAULT 10"),
                ("max_daily_trades", "INTEGER DEFAULT 10"),
                ("max_holding_days", "INTEGER DEFAULT 14"),
                # Green Light 모드용 LLM 설정
                ("llm_provider", "TEXT"),  # claude/openai/gemini
                ("llm_api_key", "TEXT"),   # 암호화 저장
                ("llm_model", "TEXT"),     # 사용할 모델명
            ]
            for col_name, col_type in new_columns:
                try:
                    cursor.execute(f"ALTER TABLE auto_trade_settings ADD COLUMN {col_name} {col_type}")
                except:
                    pass  # 이미 존재하는 컬럼

            # Green Light AI 결정 이력 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS greenlight_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    decision_time TEXT,
                    llm_provider TEXT,
                    prompt_summary TEXT,
                    raw_response TEXT,
                    decisions_json TEXT,
                    executed_orders_json TEXT,
                    portfolio_snapshot TEXT,
                    market_context TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Green Light AI 학습용 피드백 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS greenlight_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    decision_id INTEGER,
                    stock_code TEXT,
                    action TEXT,
                    entry_price INTEGER,
                    exit_price INTEGER,
                    profit_rate REAL,
                    holding_days INTEGER,
                    ai_confidence REAL,
                    feedback_note TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Green Light 인덱스
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_greenlight_decisions_user ON greenlight_decisions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_greenlight_feedback_user ON greenlight_feedback(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_greenlight_feedback_decision ON greenlight_feedback(decision_id)")

            # user_id 컬럼 추가 (기존 테이블 호환 - 다중 사용자 지원)
            user_id_tables = [
                "trade_log",
                "holdings",
                "daily_performance",
                "pending_buy_suggestions",
                "virtual_balance",
            ]
            for table in user_id_tables:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
                except:
                    pass  # 이미 존재하는 컬럼

            # 인덱스 생성
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(trade_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_stock ON trade_log(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_user ON trade_log(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_stock ON holdings(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_user ON holdings(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_status ON pending_buy_suggestions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_stock ON pending_buy_suggestions(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_user ON pending_buy_suggestions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_key_user ON api_key_settings(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_settings_user ON auto_trade_settings(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_perf_user ON daily_performance(user_id)")

    def log_order(
        self,
        stock_code: str,
        stock_name: str,
        side: str,
        quantity: int,
        price: int = 0,
        order_no: str = None,
        order_type: str = "시장가",
        trade_reason: str = None,
        status: str = "pending",
        profit_loss: int = None,
        profit_rate: float = None,
        user_id: int = None
    ) -> int:
        """
        주문 기록

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            side: 매수/매도 (buy/sell)
            quantity: 수량
            price: 가격
            order_no: 주문번호
            order_type: 주문유형
            trade_reason: 거래 사유
            status: 상태 (pending, executed, cancelled)
            profit_loss: 실현 손익 (매도 시)
            profit_rate: 수익률 (매도 시)
            user_id: 사용자 ID

        Returns:
            생성된 레코드 ID
        """
        now = datetime.now()
        amount = price * quantity if price else 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_log (
                    trade_date, trade_time, stock_code, stock_name,
                    side, quantity, price, amount, order_no, order_type,
                    trade_reason, status, profit_loss, profit_rate, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                stock_code,
                stock_name,
                side,
                quantity,
                price,
                amount,
                order_no,
                order_type,
                trade_reason,
                status,
                profit_loss,
                profit_rate,
                user_id
            ))
            return cursor.lastrowid

    def update_order_status(
        self,
        order_no: str,
        status: str,
        executed_price: int = None,
        profit_loss: int = None,
        profit_rate: float = None
    ):
        """
        주문 상태 업데이트

        Args:
            order_no: 주문번호
            status: 새 상태
            executed_price: 체결가
            profit_loss: 손익 금액
            profit_rate: 손익률
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if executed_price:
                cursor.execute("""
                    UPDATE trade_log
                    SET status = ?, price = ?, amount = price * quantity,
                        profit_loss = ?, profit_rate = ?
                    WHERE order_no = ?
                """, (status, executed_price, profit_loss, profit_rate, order_no))
            else:
                cursor.execute("""
                    UPDATE trade_log
                    SET status = ?, profit_loss = ?, profit_rate = ?
                    WHERE order_no = ?
                """, (status, profit_loss, profit_rate, order_no))

    def add_holding(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        avg_price: int,
        buy_reason: str = None,
        market: str = "KOSDAQ"
    ):
        """
        보유 종목 추가/업데이트

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            quantity: 수량
            avg_price: 평균매수가
            buy_reason: 매수사유
            market: 시장 구분 (KOSPI/KOSDAQ)
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO holdings (
                    stock_code, stock_name, quantity, avg_price,
                    buy_date, buy_reason, market, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stock_code,
                stock_name,
                quantity,
                avg_price,
                now.strftime("%Y-%m-%d"),
                buy_reason,
                market,
                now.isoformat()
            ))

    def remove_holding(self, stock_code: str):
        """보유 종목 삭제"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM holdings WHERE stock_code = ?", (stock_code,))

    def get_holdings(self, user_id: int = None) -> List[Dict]:
        """보유 종목 조회"""
        # user_id가 없으면 빈 리스트 반환 (보안)
        if user_id is None:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings WHERE user_id = ? ORDER BY buy_date DESC", (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_holding(self, stock_code: str) -> Optional[Dict]:
        """특정 보유 종목 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings WHERE stock_code = ?", (stock_code,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_buy_date(self, stock_code: str) -> Optional[datetime]:
        """종목 매수일 조회"""
        holding = self.get_holding(stock_code)
        if holding and holding.get("buy_date"):
            return datetime.strptime(holding["buy_date"], "%Y-%m-%d")
        return None

    def get_trade_history(
        self,
        user_id: int = None,
        start_date: str = None,
        end_date: str = None,
        stock_code: str = None,
        side: str = None
    ) -> List[Dict]:
        """
        거래 내역 조회

        Args:
            user_id: 사용자 ID (None이면 빈 리스트 반환)
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            stock_code: 종목코드
            side: 매수/매도

        Returns:
            거래 내역 리스트
        """
        # user_id가 없으면 빈 리스트 반환 (보안)
        if user_id is None:
            return []

        query = "SELECT * FROM trade_log WHERE user_id = ?"
        params = [user_id]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        if stock_code:
            query += " AND stock_code = ?"
            params.append(stock_code)
        if side:
            query += " AND side = ?"
            params.append(side)

        query += " ORDER BY trade_date DESC, trade_time DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_today_trades(self) -> List[Dict]:
        """오늘 거래 내역 조회"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_trade_history(start_date=today, end_date=today)

    def get_trade_count_today(self) -> int:
        """오늘 거래 횟수"""
        trades = self.get_today_trades()
        return len([t for t in trades if t.get("status") == "executed"])

    def get_today_traded_stocks(self, user_id: int) -> set:
        """
        당일 거래한 종목 코드 집합 반환 (블랙리스트용)

        매수/매도 여부 상관없이 오늘 거래된 모든 종목을 반환합니다.
        장중 10분 스크리닝 시 같은 종목 왕복매매 방지용.

        Args:
            user_id: 사용자 ID

        Returns:
            오늘 거래한 종목 코드 집합 (set)
        """
        if user_id is None:
            return set()

        today = datetime.now().strftime("%Y-%m-%d")

        query = """
            SELECT DISTINCT stock_code
            FROM trade_log
            WHERE user_id = ?
              AND trade_date = ?
              AND status = 'executed'
        """

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id, today))
            rows = cursor.fetchall()
            return {row['stock_code'] for row in rows}

    def save_daily_performance(
        self,
        total_assets: int,
        total_invested: int,
        total_profit: int,
        holdings_count: int
    ):
        """
        일별 성과 저장

        Args:
            total_assets: 총 자산
            total_invested: 총 투자금액
            total_profit: 총 손익
            holdings_count: 보유 종목 수
        """
        today = datetime.now().strftime("%Y-%m-%d")
        profit_rate = total_profit / total_invested if total_invested > 0 else 0

        # 오늘 거래 횟수 계산
        today_trades = self.get_today_trades()
        buy_count = len([t for t in today_trades if t.get("side") == "buy" and t.get("status") == "executed"])
        sell_count = len([t for t in today_trades if t.get("side") == "sell" and t.get("status") == "executed"])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO daily_performance (
                    trade_date, total_assets, total_invested, total_profit,
                    profit_rate, buy_count, sell_count, holdings_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                today,
                total_assets,
                total_invested,
                total_profit,
                profit_rate,
                buy_count,
                sell_count,
                holdings_count
            ))

    def get_performance(
        self,
        user_id: int = None,
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict]:
        """
        성과 조회

        Args:
            user_id: 사용자 ID (None이면 빈 리스트 반환)
            start_date: 시작일
            end_date: 종료일

        Returns:
            일별 성과 리스트
        """
        # user_id가 없으면 빈 리스트 반환 (보안)
        if user_id is None:
            return []

        query = "SELECT * FROM daily_performance WHERE user_id = ?"
        params = [user_id]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_performance_summary(self, user_id: int = None, days: int = 30) -> Dict:
        """
        성과 요약

        Args:
            user_id: 사용자 ID
            days: 조회 기간 (일)

        Returns:
            성과 요약 딕셔너리
        """
        empty_result = {
            "period_days": days,
            "total_trades": 0,
            "total_profit": 0,
            "win_rate": 0,
            "avg_profit_rate": 0,
            "buy_count": 0,
            "sell_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "max_profit": 0,
            "max_loss": 0,
            "daily_summary": []
        }

        # user_id가 없으면 빈 결과 반환
        if user_id is None:
            return empty_result

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        performances = self.get_performance(user_id=user_id, start_date=start_date)

        if not performances:
            return empty_result

        # 기간 내 거래 내역
        trades = self.get_trade_history(user_id=user_id, start_date=start_date)
        executed_trades = [t for t in trades if t.get("status") == "executed"]

        # 수익/손실 거래 분리
        winning_trades = [t for t in executed_trades if (t.get("profit_loss") or 0) > 0]
        losing_trades = [t for t in executed_trades if (t.get("profit_loss") or 0) < 0]

        total_profit = sum(t.get("profit_loss") or 0 for t in executed_trades)
        win_rate = len(winning_trades) / len(executed_trades) if executed_trades else 0

        # 평균 수익률 계산
        profit_rates = [t.get("profit_rate") or 0 for t in executed_trades if t.get("profit_rate")]
        avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0

        # 최대 수익/손실
        max_profit = max([t.get("profit_loss") or 0 for t in executed_trades]) if executed_trades else 0
        max_loss = min([t.get("profit_loss") or 0 for t in executed_trades]) if executed_trades else 0

        return {
            "period_days": days,
            "total_trades": len(executed_trades),
            "buy_count": len([t for t in executed_trades if t.get("side") == "buy"]),
            "sell_count": len([t for t in executed_trades if t.get("side") == "sell"]),
            "win_count": len(winning_trades),
            "loss_count": len(losing_trades),
            "total_profit": total_profit,
            "win_rate": win_rate,
            "avg_profit_rate": avg_profit_rate,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "latest_assets": performances[0].get("total_assets") if performances else 0,
            "latest_holdings": performances[0].get("holdings_count") if performances else 0,
            "daily_summary": performances[:7] if performances else []
        }

    # ========== 모의투자 가상 잔고 관리 ==========

    def init_virtual_balance(self, initial_cash: int, user_id: int = None) -> bool:
        """
        모의투자 가상 잔고 초기화

        Args:
            initial_cash: 초기 자금
            user_id: 사용자 ID

        Returns:
            성공 여부
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 기존 잔고가 있는지 확인
            if user_id:
                cursor.execute("SELECT id FROM virtual_balance WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT id FROM virtual_balance LIMIT 1")
            existing = cursor.fetchone()

            if existing:
                # 이미 초기화됨
                return False

            cursor.execute("""
                INSERT INTO virtual_balance (
                    user_id, initial_cash, current_cash, total_invested,
                    total_eval, total_profit, created_at, updated_at
                ) VALUES (?, ?, ?, 0, 0, 0, ?, ?)
            """, (user_id, initial_cash, initial_cash, now.isoformat(), now.isoformat()))

            return True

    def get_virtual_balance(self, user_id: int = None) -> Optional[Dict]:
        """모의투자 가상 잔고 조회"""
        # user_id가 없으면 None 반환 (보안)
        if user_id is None:
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM virtual_balance WHERE user_id = ? LIMIT 1", (user_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def update_virtual_balance_on_buy(self, amount: int) -> bool:
        """
        매수 시 가상 잔고 업데이트

        Args:
            amount: 매수 금액 (가격 * 수량)

        Returns:
            성공 여부
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 현재 잔고 확인
            cursor.execute("SELECT id, current_cash FROM virtual_balance LIMIT 1")
            row = cursor.fetchone()

            if not row:
                return False

            current_cash = row['current_cash']

            # 현금이 부족하면 실패
            if current_cash < amount:
                return False

            # 현금 차감, 투자금액 증가
            cursor.execute("""
                UPDATE virtual_balance
                SET current_cash = current_cash - ?,
                    total_invested = total_invested + ?,
                    updated_at = ?
                WHERE id = ?
            """, (amount, amount, now.isoformat(), row['id']))

            return True

    def update_virtual_balance_on_sell(self, net_sell_amount: int, buy_amount: int, realized_profit: int = None) -> bool:
        """
        매도 시 가상 잔고 업데이트

        Args:
            net_sell_amount: 순 매도 금액 (매도금액 - 매도수수료 - 세금)
            buy_amount: 매수 금액 (평균단가 * 수량)
            realized_profit: 실현 손익 (수수료/세금 차감 후, None이면 자동 계산)

        Returns:
            성공 여부
        """
        now = datetime.now()
        # realized_profit이 전달되면 사용, 아니면 기존 방식으로 계산
        profit = realized_profit if realized_profit is not None else (net_sell_amount - buy_amount)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM virtual_balance LIMIT 1")
            row = cursor.fetchone()

            if not row:
                return False

            # 현금 증가, 투자금액 감소, 손익 누적
            cursor.execute("""
                UPDATE virtual_balance
                SET current_cash = current_cash + ?,
                    total_invested = total_invested - ?,
                    total_profit = total_profit + ?,
                    updated_at = ?
                WHERE id = ?
            """, (net_sell_amount, buy_amount, profit, now.isoformat(), row['id']))

            return True

    def update_virtual_eval(self, total_eval: int) -> bool:
        """
        보유 주식 평가금액 업데이트

        Args:
            total_eval: 총 평가금액

        Returns:
            성공 여부
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM virtual_balance LIMIT 1")
            row = cursor.fetchone()

            if not row:
                return False

            cursor.execute("""
                UPDATE virtual_balance
                SET total_eval = ?, updated_at = ?
                WHERE id = ?
            """, (total_eval, now.isoformat(), row['id']))

            return True

    def get_virtual_summary(self) -> Dict:
        """
        모의투자 잔고 요약

        Returns:
            {
                'initial_cash': 초기 자금,
                'current_cash': 현재 현금,
                'total_invested': 투자원금,
                'total_eval': 평가금액,
                'total_assets': 총 자산 (현금 + 평가금액),
                'total_profit': 실현 손익,
                'unrealized_profit': 미실현 손익
            }
        """
        balance = self.get_virtual_balance()

        if not balance:
            return {
                'initial_cash': 0,
                'current_cash': 0,
                'total_invested': 0,
                'total_eval': 0,
                'total_assets': 0,
                'total_profit': 0,
                'unrealized_profit': 0
            }

        total_assets = balance['current_cash'] + balance['total_eval']
        unrealized_profit = balance['total_eval'] - balance['total_invested']

        return {
            'initial_cash': balance['initial_cash'],
            'current_cash': balance['current_cash'],
            'total_invested': balance['total_invested'],
            'total_eval': balance['total_eval'],
            'total_assets': total_assets,
            'total_profit': balance['total_profit'],
            'unrealized_profit': unrealized_profit
        }

    def reset_virtual_balance(self, initial_cash: int) -> bool:
        """
        모의투자 가상 잔고 리셋

        Args:
            initial_cash: 초기 자금

        Returns:
            성공 여부
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 기존 잔고 삭제
            cursor.execute("DELETE FROM virtual_balance")

            # 새로 생성
            cursor.execute("""
                INSERT INTO virtual_balance (
                    initial_cash, current_cash, total_invested,
                    total_eval, total_profit, created_at, updated_at
                ) VALUES (?, ?, 0, 0, 0, ?, ?)
            """, (initial_cash, initial_cash, now.isoformat(), now.isoformat()))

            return True

    def export_report(self, output_path: str = None, days: int = 30) -> str:
        """
        리포트 출력

        Args:
            output_path: 출력 파일 경로
            days: 조회 기간

        Returns:
            리포트 문자열
        """
        summary = self.get_performance_summary(days)
        trades = self.get_trade_history(
            start_date=(datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        )

        report_lines = [
            "=" * 60,
            f"자동매매 성과 리포트 (최근 {days}일)",
            "=" * 60,
            "",
            f"총 거래 횟수: {summary['total_trades']}회",
            f"  - 매수: {summary['buy_trades']}회",
            f"  - 매도: {summary['sell_trades']}회",
            "",
            f"승률: {summary['win_rate']*100:.1f}%",
            f"  - 수익 거래: {summary['winning_trades']}회",
            f"  - 손실 거래: {summary['losing_trades']}회",
            "",
            f"총 손익: {summary['total_profit']:,}원",
            f"평균 수익률: {summary['avg_profit_rate']*100:.2f}%",
            "",
            f"현재 자산: {summary['latest_assets']:,}원",
            f"보유 종목: {summary['latest_holdings']}개",
            "",
            "-" * 60,
            "최근 거래 내역",
            "-" * 60,
        ]

        for trade in trades[:20]:
            side_kr = "매수" if trade.get("side") == "buy" else "매도"
            report_lines.append(
                f"{trade.get('trade_date')} {trade.get('trade_time')} | "
                f"{trade.get('stock_name', trade.get('stock_code'))} {side_kr} "
                f"{trade.get('quantity')}주 @ {trade.get('price'):,}원"
            )

        report = "\n".join(report_lines)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)

        return report

    # ========== API 키 관리 ==========

    def get_api_key_settings(self, user_id: int = None) -> Optional[Dict]:
        """API 키 설정 조회 (복호화)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM api_key_settings WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT * FROM api_key_settings LIMIT 1")
            row = cursor.fetchone()

            if row:
                result = dict(row)
                # 민감 정보 복호화 및 공백/개행 문자 제거
                result['app_key'] = decrypt_value(result.get('app_key', '')).strip()
                result['app_secret'] = decrypt_value(result.get('app_secret', '')).strip()
                result['account_number'] = decrypt_value(result.get('account_number', '')).strip()
                return result
            return None

    def save_api_key_settings(
        self,
        user_id: int,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        is_mock: bool = True
    ) -> bool:
        """API 키 설정 저장 (암호화)"""
        now = datetime.now()

        # 공백/개행 문자 제거 후 암호화
        encrypted_app_key = encrypt_value(app_key.strip())
        encrypted_app_secret = encrypt_value(app_secret.strip())
        encrypted_account_number = encrypt_value(account_number.strip())

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO api_key_settings (
                    user_id, app_key, app_secret, account_number,
                    account_product_code, is_mock, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, encrypted_app_key, encrypted_app_secret, encrypted_account_number,
                account_product_code, is_mock, now.isoformat()
            ))
            return cursor.rowcount > 0

    def delete_api_key_settings(self, user_id: int = None) -> bool:
        """API 키 설정 삭제"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("DELETE FROM api_key_settings WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("DELETE FROM api_key_settings")
            return cursor.rowcount > 0

    def get_auto_trade_users(self) -> List[Dict]:
        """자동매매 활성화된 모든 사용자와 API 키 조회"""
        users = []
        stock_db_path = Path(__file__).parent.parent / "database" / "stock_data.db"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # stock_data.db를 attach하여 users 테이블 접근
            cursor.execute(f"ATTACH DATABASE '{stock_db_path}' AS stock_db")

            # auto_trade_enabled 유저 중 API 키가 설정되고 trading_enabled=1인 유저만 조회
            # 중요: auto_trade_settings.trading_enabled=1이어야만 자동매매 실행
            cursor.execute("""
                SELECT u.id, u.username, u.name, u.telegram_chat_id,
                       a.app_key, a.app_secret, a.account_number,
                       a.account_product_code, a.is_mock
                FROM stock_db.users u
                JOIN api_key_settings a ON u.id = a.user_id
                JOIN auto_trade_settings s ON u.id = s.user_id
                WHERE u.auto_trade_enabled = 1 AND u.is_active = 1
                  AND s.trading_enabled = 1
            """)
            rows = cursor.fetchall()

            for row in rows:
                user_data = dict(row)
                # 민감 정보 복호화
                user_data['app_key'] = decrypt_value(user_data.get('app_key', '')).strip()
                user_data['app_secret'] = decrypt_value(user_data.get('app_secret', '')).strip()
                user_data['account_number'] = decrypt_value(user_data.get('account_number', '')).strip()
                users.append(user_data)

            cursor.execute("DETACH DATABASE stock_db")

        return users

    def get_real_account_balance(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        is_mock: bool = True,
        max_retries: int = 3
    ) -> Dict:
        """
        실제/모의 증권 계좌 잔고 조회 (KIS API)

        Args:
            max_retries: 최대 재시도 횟수 (기본 3회)

        Returns:
            {
                'balance': { 'cash': int },
                'holdings': [...],
                'summary': { 'total_asset', 'total_purchase', 'total_evaluation', 'total_profit', 'profit_rate' }
            }
        """
        import time
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from api.services.kis_client import KISClient

        last_error = None

        for attempt in range(max_retries):
            try:
                # KIS 클라이언트 생성 (모의/실전 구분)
                client = KISClient(
                    app_key=app_key,
                    app_secret=app_secret,
                    account_number=account_number,
                    account_product_code=account_product_code,
                    is_mock=is_mock
                )

                # 계좌 잔고 조회
                balance_data = client.get_account_balance()

                if not balance_data:
                    return {
                        'balance': {'cash': 0},
                        'holdings': [],
                        'summary': {
                            'total_asset': 0,
                            'total_purchase': 0,
                            'total_evaluation': 0,
                            'total_profit': 0,
                            'profit_rate': 0
                        }
                    }

                return balance_data

            except Exception as e:
                last_error = e
                error_str = str(e)

                # 500 에러 또는 일시적 오류인 경우 재시도
                if "500" in error_str or "Server Error" in error_str or "timeout" in error_str.lower():
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2초, 4초, 6초...
                        print(f"[KIS] 일시적 오류, {wait_time}초 후 재시도 ({attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue

                # 다른 에러는 바로 raise
                raise Exception(f"계좌 조회 실패: {error_str}")

        # 모든 재시도 실패
        raise Exception(f"계좌 조회 실패 (재시도 {max_retries}회 후): {str(last_error)}")

    def place_order(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        stock_code: str = "",
        side: str = "buy",
        quantity: int = 0,
        price: int = 0,
        order_type: str = "market",
        is_mock: bool = True
    ) -> Dict:
        """
        주식 주문 실행 (KIS API)

        Args:
            app_key: API 앱키
            app_secret: API 시크릿
            account_number: 계좌번호
            account_product_code: 상품코드
            stock_code: 종목코드
            side: 매수/매도 (buy/sell)
            quantity: 수량
            price: 가격 (0이면 시장가)
            order_type: 주문유형 (limit: 지정가, market: 시장가)
            is_mock: 모의투자 여부

        Returns:
            {'success': bool, 'order_id': str, 'message': str}
        """
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from api.services.kis_client import KISClient

            client = KISClient(
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number,
                account_product_code=account_product_code,
                is_mock=is_mock
            )

            # order_type 변환 (limit -> 00, market -> 01)
            kis_order_type = "00" if order_type == "limit" else "01"

            result = client.place_order(
                stock_code=stock_code,
                side=side,
                quantity=quantity,
                price=price,
                order_type=kis_order_type
            )

            if result and result.get('success'):
                return {
                    'success': True,
                    'order_id': result.get('order_id', ''),
                    'message': result.get('message', '주문 접수 완료')
                }
            else:
                return {
                    'success': False,
                    'order_id': '',
                    'message': result.get('message', '주문 실패') if result else '주문 실패'
                }

        except Exception as e:
            return {
                'success': False,
                'order_id': '',
                'message': f"주문 실패: {str(e)}"
            }

    def get_pending_orders(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        is_mock: bool = True
    ) -> Dict:
        """
        미체결 주문 조회 (KIS API)

        Returns:
            {'orders': [...]}
        """
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from api.services.kis_client import KISClient

            client = KISClient(
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number,
                account_product_code=account_product_code,
                is_mock=is_mock
            )

            orders = client.get_pending_orders()

            if not orders:
                return {'orders': []}

            return {'orders': orders}

        except Exception as e:
            raise Exception(f"미체결 조회 실패: {str(e)}")

    def modify_order(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        order_no: str = "",
        stock_code: str = "",
        quantity: int = 0,
        price: int = 0,
        order_type: str = "00",  # 00: 지정가, 01: 시장가
        is_mock: bool = True
    ) -> Dict:
        """
        주문 정정 (KIS API)

        Args:
            order_no: 원주문번호
            stock_code: 종목코드
            quantity: 정정 수량
            price: 정정 가격
            order_type: 주문 구분 ("00": 지정가, "01": 시장가)

        Returns:
            {'success': bool, 'new_order_no': str, 'message': str}
        """
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from api.services.kis_client import KISClient

            client = KISClient(
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number,
                account_product_code=account_product_code,
                is_mock=is_mock
            )

            result = client.modify_order(
                order_no=order_no,
                stock_code=stock_code,
                quantity=quantity,
                price=price,
                order_type=order_type
            )

            if result and result.get('success'):
                return {
                    'success': True,
                    'new_order_no': result.get('new_order_no', ''),
                    'message': '주문 정정 완료'
                }
            else:
                return {
                    'success': False,
                    'new_order_no': '',
                    'message': result.get('error', '주문 정정 실패') if result else '주문 정정 실패'
                }

        except Exception as e:
            return {
                'success': False,
                'new_order_no': '',
                'message': f"주문 정정 실패: {str(e)}"
            }

    def cancel_order(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        order_id: str = "",
        is_mock: bool = True
    ) -> Dict:
        """
        주문 취소 (KIS API)

        Args:
            order_id: 원주문번호

        Returns:
            {'success': bool, 'message': str}
        """
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from api.services.kis_client import KISClient

            client = KISClient(
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number,
                account_product_code=account_product_code,
                is_mock=is_mock
            )

            # 미체결 주문에서 해당 주문 정보 조회
            pending_orders = client.get_pending_orders()
            target_order = None
            if pending_orders:
                for order in pending_orders:
                    if order.get('order_no') == order_id:
                        target_order = order
                        break

            if not target_order:
                return {
                    'success': False,
                    'message': '해당 주문을 찾을 수 없습니다.'
                }

            stock_code = target_order.get('stock_code', '')
            quantity = target_order.get('remaining_qty', 0) or target_order.get('order_qty', 0)

            result = client.cancel_order(
                order_no=order_id,
                stock_code=stock_code,
                quantity=quantity,
                order_type="00"
            )

            if result and result.get('success'):
                return {
                    'success': True,
                    'message': '주문 취소 완료'
                }
            else:
                return {
                    'success': False,
                    'message': result.get('error', '주문 취소 실패') if result else '주문 취소 실패'
                }

        except Exception as e:
            return {
                'success': False,
                'message': f"주문 취소 실패: {str(e)}"
            }

    # ========== 자동매매 설정 관리 ==========

    def get_auto_trade_settings(self, user_id: int = None) -> Optional[Dict]:
        """자동매매 설정 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM auto_trade_settings WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT * FROM auto_trade_settings LIMIT 1")
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Boolean 변환
                result['trading_enabled'] = bool(result.get('trading_enabled', 1))
                return result
            return None

    def save_auto_trade_settings(self, user_id: int, settings: Dict) -> bool:
        """자동매매 설정 저장 (LLM 설정 포함)"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 기존 LLM 설정 조회 (덮어쓰기 방지)
            cursor.execute("""
                SELECT llm_provider, llm_api_key, llm_model
                FROM auto_trade_settings WHERE user_id = ?
            """, (user_id,))
            existing = cursor.fetchone()

            # LLM 설정: 새 값이 있으면 사용, 없으면 기존 값 유지
            llm_provider = settings.get('llm_provider') or (existing['llm_provider'] if existing else None)
            llm_api_key = settings.get('llm_api_key') or (existing['llm_api_key'] if existing else None)
            llm_model = settings.get('llm_model') or (existing['llm_model'] if existing else None)

            cursor.execute("""
                INSERT OR REPLACE INTO auto_trade_settings (
                    user_id, trade_mode, max_per_stock,
                    stop_loss_rate, min_buy_score, sell_score,
                    trading_enabled, initial_investment,
                    llm_provider, llm_api_key, llm_model,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                settings.get('trade_mode', 'manual'),
                settings.get('max_per_stock', 200000),
                settings.get('stop_loss_rate', -7.0),
                settings.get('min_buy_score', 70),
                settings.get('sell_score', 40),
                1 if settings.get('trading_enabled', True) else 0,
                settings.get('initial_investment', 0),
                llm_provider,
                llm_api_key,
                llm_model,
                now.isoformat()
            ))
            return cursor.rowcount > 0

    # ========== 매수 제안 관리 (BuySuggestionManager 기능 통합) ==========

    def get_suggestion(self, suggestion_id: int) -> Optional[Dict]:
        """특정 매수 제안 조회 (ID로)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pending_buy_suggestions WHERE id = ?
            """, (suggestion_id,))
            row = cursor.fetchone()

            if row:
                item = dict(row)
                if item.get('signals'):
                    try:
                        item['signals'] = json.loads(item['signals'])
                    except:
                        pass
                return item
            return None

    def mark_executed(self, suggestion_id: int) -> bool:
        """매수 제안 실행 완료 처리"""
        now = datetime.now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'executed', executed_at = ?, updated_at = ?
                WHERE id = ?
            """, (now.isoformat(), now.isoformat(), suggestion_id))
            return cursor.rowcount > 0

    def log_trade(self, user_id: int, stock_code: str, stock_name: str, side: str,
                  quantity: int, price: int, order_no: str = None,
                  trade_reason: str = None, status: str = 'ordered') -> int:
        """거래 로그 기록"""
        now = datetime.now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_log (user_id, stock_code, stock_name, side, quantity, price,
                                       amount, order_no, trade_reason, status, trade_date, trade_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, stock_code, stock_name, side, quantity, price,
                  quantity * price, order_no, trade_reason, status,
                  now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'), now.isoformat()))
            return cursor.lastrowid

    def get_pending_suggestions(self, user_id: int = None) -> List[Dict]:
        """대기 중인 매수 제안 목록 조회"""
        # user_id가 없으면 빈 리스트 반환 (보안)
        if user_id is None:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, stock_code, stock_name, recommended_price as suggested_price,
                       1 as quantity, signals as reason, score, status, created_at
                FROM pending_buy_suggestions
                WHERE status = 'pending' AND user_id = ?
                ORDER BY score DESC, created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                # signals(reason)이 JSON이면 파싱
                if item.get('reason'):
                    try:
                        signals = json.loads(item['reason'])
                        if isinstance(signals, list):
                            item['reason'] = ', '.join(signals[:3])  # 최대 3개 신호만 표시
                    except:
                        pass
                results.append(item)

            return results

    def get_approved_suggestions(self, user_id: int = None) -> List[Dict]:
        """승인된 매수 제안 목록 조회"""
        # user_id가 없으면 빈 리스트 반환 (보안)
        if user_id is None:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, stock_code, stock_name, recommended_price as suggested_price,
                       1 as quantity, signals as reason, score, status, created_at
                FROM pending_buy_suggestions
                WHERE status = 'approved' AND user_id = ?
                ORDER BY approved_at DESC
            """, (user_id,))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                if item.get('reason'):
                    try:
                        signals = json.loads(item['reason'])
                        if isinstance(signals, list):
                            item['reason'] = ', '.join(signals[:3])
                    except:
                        pass
                results.append(item)

            return results

    def get_executed_suggestions(self, user_id: int = None) -> List[Dict]:
        """체결된 매수 제안 목록 조회"""
        # user_id가 없으면 빈 리스트 반환 (보안)
        if user_id is None:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, stock_code, stock_name, recommended_price as suggested_price,
                       1 as quantity, signals as reason, score, status, created_at
                FROM pending_buy_suggestions
                WHERE status = 'executed' AND user_id = ?
                ORDER BY executed_at DESC
                LIMIT 50
            """, (user_id,))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                if item.get('reason'):
                    try:
                        signals = json.loads(item['reason'])
                        if isinstance(signals, list):
                            item['reason'] = ', '.join(signals[:3])
                    except:
                        pass
                results.append(item)

            return results

    # ========== 매도 제안 관리 (TradeLogger) ==========

    def get_pending_sell_suggestions(self, user_id: int = None) -> List[Dict]:
        """대기 중인 매도 제안 목록 조회"""
        if user_id is None:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, stock_code, stock_name, quantity, avg_price,
                       suggested_price, current_price, profit_rate, reason,
                       status, created_at
                FROM pending_sell_suggestions
                WHERE status = 'pending' AND user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_approved_sell_suggestions(self, user_id: int = None) -> List[Dict]:
        """승인된 매도 제안 목록 조회"""
        if user_id is None:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, stock_code, stock_name, quantity, avg_price,
                       suggested_price, current_price, profit_rate, reason,
                       status, custom_price, is_market_order, created_at
                FROM pending_sell_suggestions
                WHERE status = 'approved' AND user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def approve_sell_suggestion(self, suggestion_id: int, custom_price: int = None, is_market_order: bool = False) -> bool:
        """매도 제안 승인"""
        now = datetime.now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_sell_suggestions
                SET status = 'approved', approved_at = ?, updated_at = ?,
                    custom_price = ?, is_market_order = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), now.isoformat(), custom_price, 1 if is_market_order else 0, suggestion_id))
            return cursor.rowcount > 0

    def reject_sell_suggestion(self, suggestion_id: int) -> bool:
        """매도 제안 거부"""
        now = datetime.now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_sell_suggestions
                SET status = 'rejected', updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), suggestion_id))
            return cursor.rowcount > 0

    def approve_suggestion(self, suggestion_id: int, custom_price: int = None, is_market_order: bool = False) -> bool:
        """매수 제안 승인

        Args:
            suggestion_id: 제안 ID
            custom_price: 사용자 지정 매수가 (지정가 주문 시)
            is_market_order: True면 시장가, False면 지정가
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'approved', approved_at = ?, updated_at = ?,
                    custom_price = ?, is_market_order = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), now.isoformat(), custom_price, 1 if is_market_order else 0, suggestion_id))

            return cursor.rowcount > 0

    def reject_suggestion(self, suggestion_id: int) -> bool:
        """매수 제안 거부"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'rejected', updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), suggestion_id))

            return cursor.rowcount > 0

    def get_statistics(self) -> Dict:
        """거래 통계 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 전체 거래 수
            cursor.execute("SELECT COUNT(*) FROM trade_log WHERE status = 'executed'")
            total_trades = cursor.fetchone()[0]

            # 매도 거래 중 수익/손실 분리
            cursor.execute("""
                SELECT
                    COUNT(CASE WHEN profit_rate > 0 THEN 1 END) as win_count,
                    COUNT(CASE WHEN profit_rate < 0 THEN 1 END) as loss_count,
                    COALESCE(SUM(profit_loss), 0) as total_profit,
                    COALESCE(AVG(profit_rate), 0) as avg_profit_rate
                FROM trade_log
                WHERE side = 'sell' AND status = 'executed'
            """)
            row = cursor.fetchone()

            win_count = row[0] or 0
            loss_count = row[1] or 0
            total_profit = row[2] or 0
            avg_profit_rate = row[3] or 0

            sell_count = win_count + loss_count
            win_rate = (win_count / sell_count * 100) if sell_count > 0 else 0

            return {
                'total_trades': total_trades,
                'win_count': win_count,
                'loss_count': loss_count,
                'win_rate': win_rate,
                'total_profit': total_profit,
                'avg_profit_rate': avg_profit_rate
            }

    def get_trade_reasons_by_order_nos(self, order_nos: List[str], user_id: int = None) -> Dict[str, Dict]:
        """
        주문번호 목록으로 매매 사유 조회

        Args:
            order_nos: 주문번호 리스트
            user_id: 사용자 ID

        Returns:
            {order_no: {'trade_reason': str, 'profit_loss': int, 'profit_rate': float}, ...}
        """
        if not order_nos:
            return {}

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?' for _ in order_nos])

            if user_id:
                query = f"""
                    SELECT order_no, trade_reason, profit_loss, profit_rate, created_at
                    FROM trade_log
                    WHERE order_no IN ({placeholders}) AND user_id = ?
                """
                cursor.execute(query, order_nos + [user_id])
            else:
                query = f"""
                    SELECT order_no, trade_reason, profit_loss, profit_rate, created_at
                    FROM trade_log
                    WHERE order_no IN ({placeholders})
                """
                cursor.execute(query, order_nos)

            rows = cursor.fetchall()

            result = {}
            for row in rows:
                row_dict = dict(row)
                order_no = row_dict.get('order_no')
                if order_no:
                    result[order_no] = {
                        'trade_reason': row_dict.get('trade_reason'),
                        'profit_loss': row_dict.get('profit_loss'),
                        'profit_rate': row_dict.get('profit_rate'),
                        'created_at': row_dict.get('created_at')
                    }

            return result

    # ========== Green Light 모드 관련 메서드 ==========

    def get_llm_settings(self, user_id: int) -> Optional[Dict]:
        """LLM 설정 조회 (복호화)"""
        if not user_id:
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT llm_provider, llm_api_key, llm_model
                FROM auto_trade_settings
                WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()

            if row and row['llm_api_key']:
                return {
                    'llm_provider': row['llm_provider'],
                    'llm_api_key': decrypt_value(row['llm_api_key']),
                    'llm_model': row['llm_model']
                }
            return None

    def save_llm_settings(self, user_id: int, provider: str, api_key: str, model: str) -> bool:
        """LLM 설정 저장 (암호화)"""
        now = datetime.now()
        encrypted_api_key = encrypt_value(api_key.strip()) if api_key else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 기존 설정이 있는지 확인
            cursor.execute("SELECT id FROM auto_trade_settings WHERE user_id = ?", (user_id,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE auto_trade_settings
                    SET llm_provider = ?, llm_api_key = ?, llm_model = ?, updated_at = ?
                    WHERE user_id = ?
                """, (provider, encrypted_api_key, model, now.isoformat(), user_id))
            else:
                cursor.execute("""
                    INSERT INTO auto_trade_settings (user_id, llm_provider, llm_api_key, llm_model, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, provider, encrypted_api_key, model, now.isoformat()))

            return cursor.rowcount > 0

    def log_greenlight_decision(
        self,
        user_id: int,
        llm_provider: str,
        prompt_summary: str,
        raw_response: str,
        decisions: List[Dict],
        executed_orders: List[Dict],
        portfolio_snapshot: Dict,
        market_context: Dict
    ) -> int:
        """Green Light AI 결정 기록"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO greenlight_decisions (
                    user_id, decision_time, llm_provider, prompt_summary,
                    raw_response, decisions_json, executed_orders_json,
                    portfolio_snapshot, market_context, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                now.isoformat(),
                llm_provider,
                prompt_summary,
                raw_response,
                json.dumps(decisions, ensure_ascii=False),
                json.dumps(executed_orders, ensure_ascii=False),
                json.dumps(portfolio_snapshot, ensure_ascii=False),
                json.dumps(market_context, ensure_ascii=False),
                now.isoformat()
            ))
            return cursor.lastrowid

    def get_greenlight_decisions(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Green Light AI 결정 이력 조회"""
        if not user_id:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM greenlight_decisions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                # JSON 파싱
                for field in ['decisions_json', 'executed_orders_json', 'portfolio_snapshot', 'market_context']:
                    if item.get(field):
                        try:
                            item[field] = json.loads(item[field])
                        except:
                            pass
                results.append(item)

            return results

    def record_greenlight_feedback(
        self,
        user_id: int,
        decision_id: int,
        stock_code: str,
        action: str,
        entry_price: int,
        exit_price: int,
        holding_days: int,
        ai_confidence: float = None
    ) -> int:
        """Green Light 매매 결과 피드백 기록"""
        now = datetime.now()
        profit_rate = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        feedback_note = "좋은결정" if profit_rate > 0 else "나쁜결정"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO greenlight_feedback (
                    user_id, decision_id, stock_code, action,
                    entry_price, exit_price, profit_rate, holding_days,
                    ai_confidence, feedback_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, decision_id, stock_code, action,
                entry_price, exit_price, profit_rate, holding_days,
                ai_confidence, feedback_note, now.isoformat()
            ))
            return cursor.lastrowid

    def get_greenlight_feedback(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Green Light 과거 피드백 조회 (AI 학습용)"""
        if not user_id:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*, d.market_context
                FROM greenlight_feedback f
                LEFT JOIN greenlight_decisions d ON f.decision_id = d.id
                WHERE f.user_id = ?
                ORDER BY f.created_at DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                if item.get('market_context'):
                    try:
                        item['market_context'] = json.loads(item['market_context'])
                    except:
                        pass
                results.append(item)

            return results


class BuySuggestionManager:
    """매수 제안 관리자 (semi-auto 모드용)"""

    def __init__(self, db_path: str = None, user_id: int = None):
        """
        Args:
            db_path: DB 파일 경로 (기본: database/auto_trade.db)
            user_id: 사용자 ID (다중 사용자 지원)
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "database" / "auto_trade.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.user_id = user_id

        # TradeLogger와 동일한 DB 사용 (테이블 생성은 TradeLogger에서 담당)
        self._ensure_table()

    @contextmanager
    def _get_connection(self):
        """DB 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_table(self):
        """테이블 존재 확인 및 생성"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_buy_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    score INTEGER,
                    probability REAL,
                    confidence REAL,
                    current_price INTEGER,
                    recommended_price INTEGER,
                    target_price INTEGER,
                    stop_loss_price INTEGER,
                    buy_band_low INTEGER,
                    buy_band_high INTEGER,
                    signals TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT,
                    approved_at TEXT,
                    executed_at TEXT
                )
            """)

    def add_buy_suggestion(
        self,
        user_id: int,
        stock_code: str,
        stock_name: str,
        current_price: int,
        quantity: int,
        score: int,
        reason: str = None,
        signals: List[str] = None,
        expire_hours: int = 24
    ) -> int:
        """
        장중 스크리닝 매수 제안 추가 (semi-auto 모드용)

        Args:
            user_id: 사용자 ID
            stock_code: 종목코드
            stock_name: 종목명
            current_price: 현재가
            quantity: 수량
            score: 점수
            reason: 제안 사유
            signals: 신호 리스트
            expire_hours: 만료 시간 (시간)

        Returns:
            생성된 제안 ID
        """
        now = datetime.now()
        expires_at = now + timedelta(hours=expire_hours)
        signals_json = json.dumps(signals or [])

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 동일 종목 + 동일 사용자 기존 pending 제안이 있으면 업데이트
            cursor.execute("""
                SELECT id FROM pending_buy_suggestions
                WHERE stock_code = ? AND status = 'pending' AND user_id = ?
            """, (stock_code, user_id))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE pending_buy_suggestions
                    SET score = ?, current_price = ?, recommended_price = ?,
                        signals = ?, updated_at = ?, expires_at = ?
                    WHERE id = ?
                """, (
                    score, current_price, current_price,
                    signals_json, now.isoformat(), expires_at.isoformat(),
                    existing['id']
                ))
                conn.commit()
                return existing['id']
            else:
                cursor.execute("""
                    INSERT INTO pending_buy_suggestions (
                        user_id, stock_code, stock_name, score,
                        current_price, recommended_price,
                        signals, status, created_at, updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """, (
                    user_id, stock_code, stock_name, score,
                    current_price, current_price,
                    signals_json, now.isoformat(), now.isoformat(),
                    expires_at.isoformat()
                ))
                conn.commit()
                return cursor.lastrowid

    def create_suggestion(
        self,
        stock_code: str,
        stock_name: str,
        score: int,
        probability: float,
        confidence: float,
        current_price: int,
        recommended_price: int,
        target_price: int,
        stop_loss_price: int,
        buy_band_low: int,
        buy_band_high: int,
        signals: List[str],
        expire_hours: int = 24
    ) -> int:
        """
        매수 제안 생성

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            score: 분석 점수
            probability: 상승 확률 (%)
            confidence: 신뢰도 (%)
            current_price: 현재가
            recommended_price: 추천 매수가
            target_price: 목표가
            stop_loss_price: 손절가
            buy_band_low: 매수 밴드 하단
            buy_band_high: 매수 밴드 상단
            signals: 신호 리스트
            expire_hours: 만료 시간 (시간)

        Returns:
            생성된 제안 ID
        """
        now = datetime.now()
        expires_at = now + timedelta(hours=expire_hours)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 동일 종목 + 동일 사용자 기존 pending 제안이 있으면 업데이트
            if self.user_id:
                cursor.execute("""
                    SELECT id FROM pending_buy_suggestions
                    WHERE stock_code = ? AND status = 'pending' AND user_id = ?
                """, (stock_code, self.user_id))
            else:
                cursor.execute("""
                    SELECT id FROM pending_buy_suggestions
                    WHERE stock_code = ? AND status = 'pending' AND user_id IS NULL
                """, (stock_code,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE pending_buy_suggestions
                    SET score = ?, probability = ?, confidence = ?,
                        current_price = ?, recommended_price = ?,
                        target_price = ?, stop_loss_price = ?,
                        buy_band_low = ?, buy_band_high = ?,
                        signals = ?, updated_at = ?, expires_at = ?
                    WHERE id = ?
                """, (
                    score, probability, confidence,
                    current_price, recommended_price,
                    target_price, stop_loss_price,
                    buy_band_low, buy_band_high,
                    json.dumps(signals), now.isoformat(), expires_at.isoformat(),
                    existing['id']
                ))
                return existing['id']
            else:
                cursor.execute("""
                    INSERT INTO pending_buy_suggestions (
                        user_id, stock_code, stock_name, score, probability, confidence,
                        current_price, recommended_price, target_price,
                        stop_loss_price, buy_band_low, buy_band_high,
                        signals, status, created_at, updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """, (
                    self.user_id, stock_code, stock_name, score, probability, confidence,
                    current_price, recommended_price, target_price,
                    stop_loss_price, buy_band_low, buy_band_high,
                    json.dumps(signals), now.isoformat(), now.isoformat(),
                    expires_at.isoformat()
                ))
                return cursor.lastrowid

    def get_pending_suggestions(self) -> List[Dict]:
        """대기 중인 매수 제안 목록 조회 (사용자별)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # user_id로 필터링하여 사용자별 제안만 조회
            if self.user_id:
                cursor.execute("""
                    SELECT * FROM pending_buy_suggestions
                    WHERE status = 'pending' AND user_id = ?
                    ORDER BY score DESC, created_at DESC
                """, (self.user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM pending_buy_suggestions
                    WHERE status = 'pending'
                    ORDER BY score DESC, created_at DESC
                """)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                if item.get('signals'):
                    item['signals'] = json.loads(item['signals'])
                results.append(item)

            return results

    def get_approved_suggestions(self) -> List[Dict]:
        """승인된 매수 제안 목록 조회 (사용자별)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # user_id로 필터링하여 사용자별 제안만 조회
            if self.user_id:
                cursor.execute("""
                    SELECT * FROM pending_buy_suggestions
                    WHERE status = 'approved' AND user_id = ?
                    ORDER BY approved_at DESC
                """, (self.user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM pending_buy_suggestions
                    WHERE status = 'approved'
                    ORDER BY approved_at DESC
                """)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item = dict(row)
                if item.get('signals'):
                    item['signals'] = json.loads(item['signals'])
                results.append(item)

            return results

    def get_suggestion(self, suggestion_id: int) -> Optional[Dict]:
        """특정 매수 제안 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pending_buy_suggestions WHERE id = ?
            """, (suggestion_id,))
            row = cursor.fetchone()

            if row:
                item = dict(row)
                if item.get('signals'):
                    item['signals'] = json.loads(item['signals'])
                return item
            return None

    def approve_suggestion_v2(self, suggestion_id: int, custom_price: int = None, is_market_order: bool = False) -> bool:
        """매수 제안 승인 (v2 - 별도 메서드, 사용되지 않음)"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'approved', approved_at = ?, updated_at = ?,
                    custom_price = ?, is_market_order = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), now.isoformat(), custom_price, 1 if is_market_order else 0, suggestion_id))

            return cursor.rowcount > 0

    def reject_suggestion_v2(self, suggestion_id: int) -> bool:
        """매수 제안 거부 (v2 - 별도 메서드, 사용되지 않음)"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'rejected', updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), suggestion_id))

            return cursor.rowcount > 0

    def mark_executed(self, suggestion_id: int) -> bool:
        """매수 제안 실행 완료 처리"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'executed', executed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'approved'
            """, (now.isoformat(), now.isoformat(), suggestion_id))

            return cursor.rowcount > 0

    def expire_old_suggestions(self) -> int:
        """만료된 제안 처리"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'expired', updated_at = ?
                WHERE status = 'pending' AND expires_at < ?
            """, (now.isoformat(), now.isoformat()))

            return cursor.rowcount

    def has_pending_for_stock(self, stock_code: str) -> bool:
        """해당 종목에 대기 중인 제안 또는 당일 거부된 제안이 있는지 확인 (사용자별)"""
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # user_id로 필터링하여 사용자별로 제안 관리
            # pending/approved 상태이거나, 당일 rejected된 경우 True 반환
            if self.user_id:
                cursor.execute("""
                    SELECT COUNT(*) FROM pending_buy_suggestions
                    WHERE stock_code = ? AND user_id = ? AND (
                        status IN ('pending', 'approved')
                        OR (status = 'rejected' AND date(updated_at) = ?)
                    )
                """, (stock_code, self.user_id, today))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM pending_buy_suggestions
                    WHERE stock_code = ? AND (
                        status IN ('pending', 'approved')
                        OR (status = 'rejected' AND date(updated_at) = ?)
                    )
                """, (stock_code, today))
            count = cursor.fetchone()[0]
            return count > 0

    def get_statistics(self) -> Dict:
        """제안 통계 (사용자별)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # user_id로 필터링하여 사용자별 통계
            if self.user_id:
                cursor.execute("""
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM pending_buy_suggestions
                    WHERE user_id = ?
                    GROUP BY status
                """, (self.user_id,))
            else:
                cursor.execute("""
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM pending_buy_suggestions
                    GROUP BY status
                """)
            rows = cursor.fetchall()

            stats = {
                'pending': 0,
                'approved': 0,
                'rejected': 0,
                'expired': 0,
                'executed': 0
            }
            for row in rows:
                stats[row['status']] = row['count']

            stats['total'] = sum(stats.values())
            return stats

    def cleanup_old_records(self, days: int = 30):
        """오래된 기록 정리 (pending/approved 제외)"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM pending_buy_suggestions
                WHERE status IN ('rejected', 'expired', 'executed')
                  AND updated_at < ?
            """, (cutoff,))

            return cursor.rowcount

    # ========== 매도 제안 관리 ==========

    def get_pending_sell_suggestions(self, user_id: int = None) -> List[Dict]:
        """대기 중인 매도 제안 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT id, user_id, stock_code, stock_name, quantity, avg_price,
                           suggested_price, current_price, profit_rate, reason,
                           status, created_at
                    FROM pending_sell_suggestions
                    WHERE status = 'pending' AND user_id = ?
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT id, user_id, stock_code, stock_name, quantity, avg_price,
                           suggested_price, current_price, profit_rate, reason,
                           status, created_at
                    FROM pending_sell_suggestions
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def get_approved_sell_suggestions(self, user_id: int = None) -> List[Dict]:
        """승인된 매도 제안 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT id, user_id, stock_code, stock_name, quantity, avg_price,
                           suggested_price, current_price, profit_rate, reason,
                           status, custom_price, is_market_order, created_at
                    FROM pending_sell_suggestions
                    WHERE status = 'approved' AND user_id = ?
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT id, user_id, stock_code, stock_name, quantity, avg_price,
                           suggested_price, current_price, profit_rate, reason,
                           status, custom_price, is_market_order, created_at
                    FROM pending_sell_suggestions
                    WHERE status = 'approved'
                    ORDER BY created_at DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def approve_sell_suggestion(self, suggestion_id: int, custom_price: int = None, is_market_order: bool = False) -> bool:
        """매도 제안 승인

        Args:
            suggestion_id: 제안 ID
            custom_price: 사용자 지정 매도가 (지정가 주문 시)
            is_market_order: True면 시장가, False면 지정가
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_sell_suggestions
                SET status = 'approved', approved_at = ?, updated_at = ?,
                    custom_price = ?, is_market_order = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), now.isoformat(), custom_price, 1 if is_market_order else 0, suggestion_id))

            return cursor.rowcount > 0

    def reject_sell_suggestion(self, suggestion_id: int) -> bool:
        """매도 제안 거부"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_sell_suggestions
                SET status = 'rejected', updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), suggestion_id))

            return cursor.rowcount > 0

    def add_sell_suggestion(self, user_id: int, stock_code: str, stock_name: str,
                           quantity: int, avg_price: int, suggested_price: int,
                           profit_rate: float, reason: str) -> int:
        """매도 제안 추가"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pending_sell_suggestions
                (user_id, stock_code, stock_name, quantity, avg_price,
                 suggested_price, current_price, profit_rate, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, stock_code, stock_name, quantity, avg_price,
                  suggested_price, suggested_price, profit_rate, reason, now.isoformat()))

            return cursor.lastrowid

    def get_trade_reasons_by_order_nos(self, order_nos: List[str], user_id: int = None) -> Dict[str, Dict]:
        """
        주문번호 목록으로 매매 사유 조회

        Args:
            order_nos: 주문번호 리스트
            user_id: 사용자 ID

        Returns:
            {order_no: {'trade_reason': str, 'ai_score': float, ...}, ...}
        """
        if not order_nos:
            return {}

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?' for _ in order_nos])

            if user_id:
                query = f"""
                    SELECT order_no, trade_reason, profit_loss, profit_rate, created_at
                    FROM trade_log
                    WHERE order_no IN ({placeholders}) AND user_id = ?
                """
                cursor.execute(query, order_nos + [user_id])
            else:
                query = f"""
                    SELECT order_no, trade_reason, profit_loss, profit_rate, created_at
                    FROM trade_log
                    WHERE order_no IN ({placeholders})
                """
                cursor.execute(query, order_nos)

            rows = cursor.fetchall()

            result = {}
            for row in rows:
                row_dict = dict(row)
                order_no = row_dict.get('order_no')
                if order_no:
                    result[order_no] = {
                        'trade_reason': row_dict.get('trade_reason'),
                        'profit_loss': row_dict.get('profit_loss'),
                        'profit_rate': row_dict.get('profit_rate'),
                        'created_at': row_dict.get('created_at')
                    }

            return result
