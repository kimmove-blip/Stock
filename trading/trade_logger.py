"""
거래 기록 모듈
거래 내역 저장 및 성과 분석
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager


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

            # 인덱스 생성
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(trade_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_stock ON trade_log(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_stock ON holdings(stock_code)")

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
        status: str = "pending"
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
                    trade_reason, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                status
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
        buy_reason: str = None
    ):
        """
        보유 종목 추가/업데이트

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            quantity: 수량
            avg_price: 평균매수가
            buy_reason: 매수사유
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO holdings (
                    stock_code, stock_name, quantity, avg_price,
                    buy_date, buy_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                stock_code,
                stock_name,
                quantity,
                avg_price,
                now.strftime("%Y-%m-%d"),
                buy_reason,
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
