"""
포지션 관리 모듈
ATR 기반 목표가/손절가 계산, 트레일링 스탑, 포지션 한도 관리
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager


class PositionManager:
    """장중 포지션 관리자"""

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: DB 파일 경로 (기본: database/auto_trade.db)
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "database" / "auto_trade.db"
        self.db_path = Path(db_path)
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
        """장중 포지션 테이블 초기화"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 장중 포지션 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intraday_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    strategy TEXT,
                    entry_time TEXT,
                    entry_price INTEGER,
                    quantity INTEGER,
                    entry_score INTEGER,
                    atr_at_entry REAL,
                    target_price INTEGER,
                    stop_price INTEGER,
                    trailing_stop_price INTEGER,
                    trailing_high_price INTEGER,
                    max_hold_until TEXT,
                    status TEXT DEFAULT 'open',
                    exit_time TEXT,
                    exit_price INTEGER,
                    exit_reason TEXT,
                    realized_pnl INTEGER,
                    realized_pnl_rate REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 인덱스
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_intraday_pos_user ON intraday_positions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_intraday_pos_status ON intraday_positions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_intraday_pos_code ON intraday_positions(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_intraday_pos_strategy ON intraday_positions(strategy)")

    def calculate_atr(
        self,
        high_prices: List[float],
        low_prices: List[float],
        close_prices: List[float],
        period: int = 14
    ) -> float:
        """
        ATR (Average True Range) 계산

        Args:
            high_prices: 고가 리스트 (최근 period+1일)
            low_prices: 저가 리스트
            close_prices: 종가 리스트
            period: ATR 기간

        Returns:
            ATR 값
        """
        if len(high_prices) < period + 1:
            # 데이터 부족 시 단순 변동폭 사용
            if high_prices and low_prices:
                return sum(high_prices[-5:]) / 5 - sum(low_prices[-5:]) / 5
            return 0

        true_ranges = []
        for i in range(1, len(close_prices)):
            high = high_prices[i]
            low = low_prices[i]
            prev_close = close_prices[i - 1]

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # 최근 period개의 TR 평균
        return sum(true_ranges[-period:]) / period

    def calculate_exit_prices(
        self,
        entry_price: int,
        atr: float,
        strategy: str,
        strategy_config: Dict = None
    ) -> Dict:
        """
        ATR 기반 목표가/손절가 계산

        Args:
            entry_price: 진입가
            atr: ATR 값
            strategy: 전략명 (v2_trend, v8_bounce, v10_follower)
            strategy_config: 전략별 설정

        Returns:
            {'target_price': int, 'stop_price': int, 'trailing_start': int}
        """
        # 기본 설정
        default_config = {
            'v2_trend': {
                'target_atr_mult': 1.5,
                'stop_atr_mult': 0.8,
                'trailing_start_atr': 0.5
            },
            'v8_bounce': {
                'target_atr_mult': 1.2,
                'stop_atr_mult': 0.6,
                'trailing_start_atr': 0.4
            },
            'v10_follower': {
                'target_atr_mult': 1.0,
                'stop_atr_mult': 0.5,
                'trailing_start_atr': 0.3
            }
        }

        config = default_config.get(strategy, default_config['v2_trend'])
        if strategy_config:
            config.update(strategy_config)

        target_mult = config.get('target_atr_mult', 1.5)
        stop_mult = config.get('stop_atr_mult', 0.8)
        trailing_mult = config.get('trailing_start_atr', 0.5)

        # ATR이 0이면 기본 비율 사용
        if atr <= 0:
            atr = entry_price * 0.03  # 3% 기본 변동폭

        target_price = int(entry_price + atr * target_mult)
        stop_price = int(entry_price - atr * stop_mult)
        trailing_start = int(entry_price + atr * trailing_mult)

        return {
            'target_price': target_price,
            'stop_price': stop_price,
            'trailing_start': trailing_start
        }

    def open_position(
        self,
        user_id: int,
        stock_code: str,
        stock_name: str,
        strategy: str,
        entry_price: int,
        quantity: int,
        entry_score: int = 0,
        atr: float = 0,
        max_hold_days: int = 3,
        strategy_config: Dict = None
    ) -> int:
        """
        새 포지션 오픈

        Args:
            user_id: 사용자 ID
            stock_code: 종목코드
            stock_name: 종목명
            strategy: 전략명
            entry_price: 진입가
            quantity: 수량
            entry_score: 진입 시점 스코어
            atr: ATR 값
            max_hold_days: 최대 보유일
            strategy_config: 전략별 설정

        Returns:
            생성된 포지션 ID
        """
        now = datetime.now()
        max_hold_until = (now + timedelta(days=max_hold_days)).isoformat()

        # 목표가/손절가 계산
        exit_prices = self.calculate_exit_prices(entry_price, atr, strategy, strategy_config)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO intraday_positions (
                    user_id, stock_code, stock_name, strategy,
                    entry_time, entry_price, quantity, entry_score,
                    atr_at_entry, target_price, stop_price,
                    trailing_stop_price, trailing_high_price,
                    max_hold_until, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """, (
                user_id, stock_code, stock_name, strategy,
                now.isoformat(), entry_price, quantity, entry_score,
                atr, exit_prices['target_price'], exit_prices['stop_price'],
                None, entry_price,  # trailing 초기화
                max_hold_until
            ))
            return cursor.lastrowid

    def close_position(
        self,
        position_id: int,
        exit_price: int,
        exit_reason: str
    ) -> bool:
        """
        포지션 청산

        Args:
            position_id: 포지션 ID
            exit_price: 청산가
            exit_reason: 청산 사유 (TARGET, STOP, TRAILING, TIME, MANUAL)

        Returns:
            성공 여부
        """
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 기존 포지션 조회
            cursor.execute("SELECT * FROM intraday_positions WHERE id = ?", (position_id,))
            row = cursor.fetchone()

            if not row:
                return False

            entry_price = row['entry_price']
            quantity = row['quantity']

            # 손익 계산
            realized_pnl = (exit_price - entry_price) * quantity
            realized_pnl_rate = (exit_price - entry_price) / entry_price * 100 if entry_price > 0 else 0

            cursor.execute("""
                UPDATE intraday_positions
                SET status = 'closed',
                    exit_time = ?,
                    exit_price = ?,
                    exit_reason = ?,
                    realized_pnl = ?,
                    realized_pnl_rate = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                now.isoformat(), exit_price, exit_reason,
                realized_pnl, realized_pnl_rate, now.isoformat(),
                position_id
            ))
            return True

    def get_open_positions(self, user_id: int, strategy: str = None) -> List[Dict]:
        """
        오픈 포지션 조회

        Args:
            user_id: 사용자 ID
            strategy: 전략 필터 (None이면 전체)

        Returns:
            포지션 리스트
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if strategy:
                cursor.execute("""
                    SELECT * FROM intraday_positions
                    WHERE user_id = ? AND status = 'open' AND strategy = ?
                    ORDER BY entry_time DESC
                """, (user_id, strategy))
            else:
                cursor.execute("""
                    SELECT * FROM intraday_positions
                    WHERE user_id = ? AND status = 'open'
                    ORDER BY entry_time DESC
                """, (user_id,))

            return [dict(row) for row in cursor.fetchall()]

    def get_position_by_code(self, user_id: int, stock_code: str) -> Optional[Dict]:
        """
        종목코드로 오픈 포지션 조회

        Args:
            user_id: 사용자 ID
            stock_code: 종목코드

        Returns:
            포지션 정보 또는 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM intraday_positions
                WHERE user_id = ? AND stock_code = ? AND status = 'open'
            """, (user_id, stock_code))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_trailing_stop(
        self,
        position_id: int,
        current_price: int,
        trailing_pct: float = 0.02  # 2% 트레일링
    ) -> Optional[int]:
        """
        트레일링 스탑 업데이트

        Args:
            position_id: 포지션 ID
            current_price: 현재가
            trailing_pct: 트레일링 비율

        Returns:
            새 트레일링 스탑가 또는 None (업데이트 없음)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM intraday_positions WHERE id = ?", (position_id,))
            row = cursor.fetchone()

            if not row or row['status'] != 'open':
                return None

            trailing_high = row['trailing_high_price'] or row['entry_price']
            current_trailing_stop = row['trailing_stop_price']

            # 신고가 갱신 시
            if current_price > trailing_high:
                new_trailing_high = current_price
                new_trailing_stop = int(current_price * (1 - trailing_pct))

                # 기존 트레일링보다 높을 때만 업데이트 (절대 내리지 않음)
                if current_trailing_stop is None or new_trailing_stop > current_trailing_stop:
                    cursor.execute("""
                        UPDATE intraday_positions
                        SET trailing_high_price = ?,
                            trailing_stop_price = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (new_trailing_high, new_trailing_stop, datetime.now().isoformat(), position_id))

                    return new_trailing_stop

            return current_trailing_stop

    def count_open_positions(self, user_id: int, strategy: str = None) -> int:
        """
        오픈 포지션 수 카운트

        Args:
            user_id: 사용자 ID
            strategy: 전략 필터

        Returns:
            포지션 수
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if strategy:
                cursor.execute("""
                    SELECT COUNT(*) FROM intraday_positions
                    WHERE user_id = ? AND status = 'open' AND strategy = ?
                """, (user_id, strategy))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM intraday_positions
                    WHERE user_id = ? AND status = 'open'
                """, (user_id,))

            return cursor.fetchone()[0]

    def count_today_trades(self, user_id: int) -> int:
        """
        오늘 거래 횟수 카운트 (매수+매도)

        Args:
            user_id: 사용자 ID

        Returns:
            오늘 거래 횟수
        """
        today = datetime.now().strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 오늘 오픈된 포지션 + 오늘 청산된 포지션
            cursor.execute("""
                SELECT COUNT(*) FROM intraday_positions
                WHERE user_id = ? AND (
                    entry_time LIKE ? OR exit_time LIKE ?
                )
            """, (user_id, f'{today}%', f'{today}%'))

            return cursor.fetchone()[0]

    def check_position_limits(
        self,
        user_id: int,
        strategy: str,
        max_positions: int,
        max_total_positions: int = 15,
        max_daily_trades: int = 20
    ) -> Dict:
        """
        포지션 한도 체크

        Args:
            user_id: 사용자 ID
            strategy: 전략명
            max_positions: 전략별 최대 포지션
            max_total_positions: 총 최대 포지션
            max_daily_trades: 일일 최대 거래

        Returns:
            {'can_open': bool, 'reason': str, 'current_count': int}
        """
        strategy_count = self.count_open_positions(user_id, strategy)
        total_count = self.count_open_positions(user_id)
        today_trades = self.count_today_trades(user_id)

        if strategy_count >= max_positions:
            return {
                'can_open': False,
                'reason': f'{strategy} 전략 최대 포지션 도달 ({strategy_count}/{max_positions})',
                'current_count': strategy_count
            }

        if total_count >= max_total_positions:
            return {
                'can_open': False,
                'reason': f'총 최대 포지션 도달 ({total_count}/{max_total_positions})',
                'current_count': total_count
            }

        if today_trades >= max_daily_trades:
            return {
                'can_open': False,
                'reason': f'일일 최대 거래 도달 ({today_trades}/{max_daily_trades})',
                'current_count': today_trades
            }

        return {
            'can_open': True,
            'reason': 'OK',
            'current_count': strategy_count
        }

    def has_position(self, user_id: int, stock_code: str) -> bool:
        """
        특정 종목 포지션 보유 여부

        Args:
            user_id: 사용자 ID
            stock_code: 종목코드

        Returns:
            보유 여부
        """
        return self.get_position_by_code(user_id, stock_code) is not None

    def get_performance_summary(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict:
        """
        성과 요약

        Args:
            user_id: 사용자 ID
            days: 조회 기간 (일)

        Returns:
            성과 통계
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as loss_count,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl_rate) as avg_pnl_rate,
                    MAX(realized_pnl_rate) as max_win_rate,
                    MIN(realized_pnl_rate) as max_loss_rate
                FROM intraday_positions
                WHERE user_id = ? AND status = 'closed' AND exit_time >= ?
            """, (user_id, since))

            row = cursor.fetchone()

            if not row or row['total_trades'] == 0:
                return {
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'avg_pnl_rate': 0
                }

            total = row['total_trades']
            wins = row['win_count'] or 0

            return {
                'total_trades': total,
                'win_count': wins,
                'loss_count': row['loss_count'] or 0,
                'win_rate': wins / total * 100 if total > 0 else 0,
                'total_pnl': row['total_pnl'] or 0,
                'avg_pnl_rate': row['avg_pnl_rate'] or 0,
                'max_win_rate': row['max_win_rate'] or 0,
                'max_loss_rate': row['max_loss_rate'] or 0
            }

    def get_strategy_performance(
        self,
        user_id: int,
        strategy: str,
        days: int = 30
    ) -> Dict:
        """
        전략별 성과

        Args:
            user_id: 사용자 ID
            strategy: 전략명
            days: 조회 기간

        Returns:
            전략 성과 통계
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as win_count,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl_rate) as avg_pnl_rate
                FROM intraday_positions
                WHERE user_id = ? AND strategy = ? AND status = 'closed' AND exit_time >= ?
            """, (user_id, strategy, since))

            row = cursor.fetchone()

            if not row or row['total_trades'] == 0:
                return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0}

            return {
                'strategy': strategy,
                'total_trades': row['total_trades'],
                'win_rate': (row['win_count'] or 0) / row['total_trades'] * 100,
                'total_pnl': row['total_pnl'] or 0,
                'avg_pnl_rate': row['avg_pnl_rate'] or 0
            }


if __name__ == "__main__":
    # 테스트
    pm = PositionManager()

    # ATR 계산 테스트
    highs = [100, 102, 105, 103, 107, 110, 108, 112, 115, 113, 118, 120, 117, 122, 125]
    lows = [95, 97, 100, 98, 102, 105, 103, 107, 110, 108, 113, 115, 112, 117, 120]
    closes = [98, 100, 103, 101, 105, 108, 106, 110, 113, 111, 116, 118, 115, 120, 123]

    atr = pm.calculate_atr(highs, lows, closes)
    print(f"ATR: {atr:.2f}")

    # 목표가/손절가 계산 테스트
    exit_prices = pm.calculate_exit_prices(10000, atr * 100, 'v2_trend')
    print(f"목표가: {exit_prices['target_price']}, 손절가: {exit_prices['stop_price']}")
