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
                    stock_code TEXT UNIQUE NOT NULL,
                    stock_name TEXT,
                    quantity INTEGER NOT NULL,
                    avg_price INTEGER NOT NULL,
                    buy_date TEXT NOT NULL,
                    buy_reason TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 일별 성과 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT UNIQUE NOT NULL,
                    total_assets INTEGER,
                    total_invested INTEGER,
                    total_profit INTEGER,
                    profit_rate REAL,
                    buy_count INTEGER DEFAULT 0,
                    sell_count INTEGER DEFAULT 0,
                    holdings_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 매수 제안 테이블 (semi-auto 모드용)
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

            # 모의투자 가상 잔고 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS virtual_balance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    max_per_stock INTEGER DEFAULT 200000,
                    stop_loss_rate REAL DEFAULT 5.0,
                    take_profit_rate REAL DEFAULT 10.0,
                    trading_enabled BOOLEAN DEFAULT 1,
                    trading_start_time TEXT DEFAULT '09:00',
                    trading_end_time TEXT DEFAULT '15:20',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 인덱스 생성
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(trade_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_stock ON trade_log(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_stock ON holdings(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_status ON pending_buy_suggestions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_stock ON pending_buy_suggestions(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_key_user ON api_key_settings(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_settings_user ON auto_trade_settings(user_id)")

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
        profit_rate: float = None
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
                    trade_reason, status, profit_loss, profit_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                profit_rate
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

    def get_holdings(self) -> List[Dict]:
        """보유 종목 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings ORDER BY buy_date DESC")
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
        start_date: str = None,
        end_date: str = None,
        stock_code: str = None,
        side: str = None
    ) -> List[Dict]:
        """
        거래 내역 조회

        Args:
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            stock_code: 종목코드
            side: 매수/매도

        Returns:
            거래 내역 리스트
        """
        query = "SELECT * FROM trade_log WHERE 1=1"
        params = []

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
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict]:
        """
        성과 조회

        Args:
            start_date: 시작일
            end_date: 종료일

        Returns:
            일별 성과 리스트
        """
        query = "SELECT * FROM daily_performance WHERE 1=1"
        params = []

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

    def get_performance_summary(self, days: int = 30) -> Dict:
        """
        성과 요약

        Args:
            days: 조회 기간 (일)

        Returns:
            성과 요약 딕셔너리
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        performances = self.get_performance(start_date=start_date)

        if not performances:
            return {
                "period_days": days,
                "total_trades": 0,
                "total_profit": 0,
                "win_rate": 0,
                "avg_profit_rate": 0
            }

        # 기간 내 거래 내역
        trades = self.get_trade_history(start_date=start_date)
        executed_trades = [t for t in trades if t.get("status") == "executed"]

        # 수익/손실 거래 분리
        winning_trades = [t for t in executed_trades if (t.get("profit_loss") or 0) > 0]
        losing_trades = [t for t in executed_trades if (t.get("profit_loss") or 0) < 0]

        total_profit = sum(t.get("profit_loss") or 0 for t in executed_trades)
        win_rate = len(winning_trades) / len(executed_trades) if executed_trades else 0

        # 평균 수익률 계산
        profit_rates = [t.get("profit_rate") or 0 for t in executed_trades if t.get("profit_rate")]
        avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0

        return {
            "period_days": days,
            "total_trades": len(executed_trades),
            "buy_trades": len([t for t in executed_trades if t.get("side") == "buy"]),
            "sell_trades": len([t for t in executed_trades if t.get("side") == "sell"]),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "total_profit": total_profit,
            "win_rate": win_rate,
            "avg_profit_rate": avg_profit_rate,
            "latest_assets": performances[0].get("total_assets") if performances else 0,
            "latest_holdings": performances[0].get("holdings_count") if performances else 0
        }

    # ========== 모의투자 가상 잔고 관리 ==========

    def init_virtual_balance(self, initial_cash: int) -> bool:
        """
        모의투자 가상 잔고 초기화

        Args:
            initial_cash: 초기 자금

        Returns:
            성공 여부
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 기존 잔고가 있는지 확인
            cursor.execute("SELECT id FROM virtual_balance LIMIT 1")
            existing = cursor.fetchone()

            if existing:
                # 이미 초기화됨
                return False

            cursor.execute("""
                INSERT INTO virtual_balance (
                    initial_cash, current_cash, total_invested,
                    total_eval, total_profit, created_at, updated_at
                ) VALUES (?, ?, 0, 0, 0, ?, ?)
            """, (initial_cash, initial_cash, now.isoformat(), now.isoformat()))

            return True

    def get_virtual_balance(self) -> Optional[Dict]:
        """모의투자 가상 잔고 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM virtual_balance LIMIT 1")
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
                # 민감 정보 복호화
                result['app_key'] = decrypt_value(result.get('app_key', ''))
                result['app_secret'] = decrypt_value(result.get('app_secret', ''))
                result['account_number'] = decrypt_value(result.get('account_number', ''))
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

        # 민감 정보 암호화
        encrypted_app_key = encrypt_value(app_key)
        encrypted_app_secret = encrypt_value(app_secret)
        encrypted_account_number = encrypt_value(account_number)

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

    def get_real_account_balance(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        is_mock: bool = True
    ) -> Dict:
        """
        실제/모의 증권 계좌 잔고 조회 (KIS API)

        Returns:
            {
                'balance': { 'cash': int },
                'holdings': [...],
                'summary': { 'total_asset', 'total_purchase', 'total_evaluation', 'total_profit', 'profit_rate' }
            }
        """
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from api.services.kis_client import KISClient

            # KIS 클라이언트 생성 (모의/실전 구분)
            client = KISClient(
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number,
                account_product_code=account_product_code,
                is_mock=is_mock
            )

            # 계좌 잔고 조회
            balance_data = client.get_balance()

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
            raise Exception(f"계좌 조회 실패: {str(e)}")

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
        """자동매매 설정 저장"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO auto_trade_settings (
                    user_id, trade_mode, max_investment, max_per_stock,
                    stop_loss_rate, take_profit_rate, trading_enabled,
                    trading_start_time, trading_end_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                settings.get('trade_mode', 'manual'),
                settings.get('max_investment', 1000000),
                settings.get('max_per_stock', 200000),
                settings.get('stop_loss_rate', 5.0),
                settings.get('take_profit_rate', 10.0),
                1 if settings.get('trading_enabled', True) else 0,
                settings.get('trading_start_time', '09:00'),
                settings.get('trading_end_time', '15:20'),
                now.isoformat()
            ))
            return cursor.rowcount > 0

    # ========== 매수 제안 관리 (BuySuggestionManager 기능 통합) ==========

    def get_pending_suggestions(self) -> List[Dict]:
        """대기 중인 매수 제안 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, stock_code, stock_name, recommended_price as suggested_price,
                       1 as quantity, signals as reason, score, status, created_at
                FROM pending_buy_suggestions
                WHERE status = 'pending'
                ORDER BY score DESC, created_at DESC
            """)
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

    def get_approved_suggestions(self) -> List[Dict]:
        """승인된 매수 제안 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, stock_code, stock_name, recommended_price as suggested_price,
                       1 as quantity, signals as reason, score, status, created_at
                FROM pending_buy_suggestions
                WHERE status = 'approved'
                ORDER BY approved_at DESC
            """)
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

    def approve_suggestion(self, suggestion_id: int) -> bool:
        """매수 제안 승인"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'approved', approved_at = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), now.isoformat(), suggestion_id))

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


class BuySuggestionManager:
    """매수 제안 관리자 (semi-auto 모드용)"""

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: DB 파일 경로 (기본: database/auto_trade.db)
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "database" / "auto_trade.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)

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

            # 동일 종목 기존 pending 제안이 있으면 업데이트
            cursor.execute("""
                SELECT id FROM pending_buy_suggestions
                WHERE stock_code = ? AND status = 'pending'
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
                        stock_code, stock_name, score, probability, confidence,
                        current_price, recommended_price, target_price,
                        stop_loss_price, buy_band_low, buy_band_high,
                        signals, status, created_at, updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """, (
                    stock_code, stock_name, score, probability, confidence,
                    current_price, recommended_price, target_price,
                    stop_loss_price, buy_band_low, buy_band_high,
                    json.dumps(signals), now.isoformat(), now.isoformat(),
                    expires_at.isoformat()
                ))
                return cursor.lastrowid

    def get_pending_suggestions(self) -> List[Dict]:
        """대기 중인 매수 제안 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
        """승인된 매수 제안 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
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

    def approve_suggestion(self, suggestion_id: int) -> bool:
        """매수 제안 승인"""
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_buy_suggestions
                SET status = 'approved', approved_at = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now.isoformat(), now.isoformat(), suggestion_id))

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
        """해당 종목에 대기 중인 제안이 있는지 확인"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM pending_buy_suggestions
                WHERE stock_code = ? AND status IN ('pending', 'approved')
            """, (stock_code,))
            count = cursor.fetchone()[0]
            return count > 0

    def get_statistics(self) -> Dict:
        """제안 통계"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
