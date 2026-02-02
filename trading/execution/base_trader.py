"""
트레이더 베이스 클래스

목적:
- auto_trader.py의 공통 로직 추출
- 모드별 트레이더 클래스의 기반
- 일관된 인터페이스 제공

사용법:
    class MyTrader(BaseTrader):
        def run(self) -> TradeResult:
            # 매매 로직 구현
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd

from trading.core.config import TradingConfig
from trading.core.exceptions import (
    TradingError,
    MarketClosedError,
    InsufficientFundsError,
)
from trading.risk_manager import RiskManager, TradingLimits
from trading.notifications import BaseNotifier, TelegramNotifier, ConsoleNotifier


@dataclass
class TradeResult:
    """매매 실행 결과"""
    success: bool
    mode: str  # 'auto', 'semi-auto', 'greenlight', 'intraday'
    buy_count: int = 0
    sell_count: int = 0
    buy_amount: int = 0
    sell_amount: int = 0
    realized_profit: int = 0
    suggestions_created: int = 0
    executed_suggestions: int = 0
    errors: List[str] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'mode': self.mode,
            'buy_count': self.buy_count,
            'sell_count': self.sell_count,
            'buy_amount': self.buy_amount,
            'sell_amount': self.sell_amount,
            'realized_profit': self.realized_profit,
            'suggestions_created': self.suggestions_created,
            'executed_suggestions': self.executed_suggestions,
            'errors': self.errors,
            'timestamp': self.timestamp.isoformat(),
        }


class BaseTrader(ABC):
    """트레이더 베이스 클래스"""

    # 장 운영 시간
    MARKET_OPEN = time(9, 0)
    MARKET_CLOSE = time(15, 30)

    # 매매 가능 시간 (09:10 ~ 15:20)
    TRADE_START = time(9, 10)
    TRADE_END = time(15, 20)

    def __init__(
        self,
        config: Optional[TradingConfig] = None,
        dry_run: bool = False,
        notifier: Optional[BaseNotifier] = None,
        user_id: Optional[int] = None,
    ):
        """
        Args:
            config: 트레이딩 설정
            dry_run: 테스트 모드 (실제 주문 X)
            notifier: 알림 전송자
            user_id: 사용자 ID
        """
        self.config = config or TradingConfig()
        self.dry_run = dry_run
        self.user_id = user_id

        # 알림 설정
        if notifier:
            self.notifier = notifier
        elif self.config.telegram_notify:
            self.notifier = TelegramNotifier(
                bot_token=self.config.telegram_bot_token,
                chat_id=self.config.telegram_chat_id
            )
        else:
            self.notifier = ConsoleNotifier()

        # 리스크 관리자
        self.risk_manager = RiskManager(TradingLimits(
            max_per_stock=self.config.max_per_stock,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            max_daily_trades=self.config.max_daily_trades,
            max_holdings=self.config.max_holdings,
            min_buy_score=self.config.min_buy_score,
            min_hold_score=self.config.min_hold_score,
        ))

        # 당일 거래 종목 (왕복매매 방지)
        self._today_traded: set = set()
        self._last_reset_date: Optional[datetime] = None

    @abstractmethod
    def run(self) -> TradeResult:
        """매매 실행 (서브클래스에서 구현)"""
        pass

    def check_market_hours(self) -> Tuple[bool, str]:
        """장 운영 시간 체크

        Returns:
            (거래 가능 여부, 사유)
        """
        now = datetime.now()
        current_time = now.time()

        # 주말 체크
        if now.weekday() >= 5:
            return False, "주말"

        # 장 시간 체크
        if current_time < self.MARKET_OPEN:
            return False, "장 시작 전"

        if current_time >= self.MARKET_CLOSE:
            return False, "장 마감"

        # 매매 가능 시간 체크
        if current_time < self.TRADE_START:
            return False, "매매 시작 전 (09:10 이후)"

        if current_time >= self.TRADE_END:
            return False, "매매 종료 (15:20 이후)"

        return True, "거래 가능"

    def reset_daily_state(self) -> None:
        """일일 상태 리셋 (날짜 변경 시)"""
        today = datetime.now().date()

        if self._last_reset_date != today:
            self._today_traded.clear()
            self._last_reset_date = today
            self.risk_manager.reset_daily_counter()

    def add_traded_stock(self, stock_code: str) -> None:
        """거래 종목 추가 (왕복매매 방지)"""
        self._today_traded.add(stock_code)

    def is_traded_today(self, stock_code: str) -> bool:
        """당일 거래 여부 확인"""
        return stock_code in self._today_traded

    def get_today_blacklist(self) -> set:
        """당일 거래 종목 집합"""
        return self._today_traded.copy()

    def calculate_position_size(
        self,
        price: int,
        investment_amount: Optional[int] = None
    ) -> int:
        """포지션 크기 계산

        Args:
            price: 현재가
            investment_amount: 투자 금액 (없으면 설정값 사용)

        Returns:
            매수 수량
        """
        if price <= 0:
            return 0

        amount = investment_amount or self.config.max_per_stock
        return amount // price

    def get_tick_size(self, price: int) -> int:
        """호가 단위 반환

        한국 주식시장 호가 단위:
        - ~1,000원: 1원
        - ~5,000원: 5원
        - ~10,000원: 10원
        - ~50,000원: 50원
        - ~100,000원: 100원
        - ~500,000원: 500원
        - 500,000원~: 1,000원
        """
        if price < 1000:
            return 1
        elif price < 5000:
            return 5
        elif price < 10000:
            return 10
        elif price < 50000:
            return 50
        elif price < 100000:
            return 100
        elif price < 500000:
            return 500
        else:
            return 1000

    def round_to_tick(self, price: int, round_down: bool = True) -> int:
        """호가 단위로 반올림/내림

        Args:
            price: 가격
            round_down: True면 내림, False면 올림
        """
        tick = self.get_tick_size(price)
        if round_down:
            return (price // tick) * tick
        else:
            return ((price + tick - 1) // tick) * tick

    def notify_buy(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: int,
        score: Optional[int] = None
    ) -> None:
        """매수 알림"""
        msg = f"🔵 [매수] {stock_name} ({stock_code})\n"
        msg += f"수량: {quantity:,}주 × {price:,}원\n"
        msg += f"금액: {quantity * price:,}원"
        if score:
            msg += f"\n점수: {score}점"

        self.notifier.send_message(msg)

    def notify_sell(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: int,
        profit_rate: float,
        reason: str
    ) -> None:
        """매도 알림"""
        emoji = "💰" if profit_rate >= 0 else "🔴"
        sign = "+" if profit_rate >= 0 else ""

        msg = f"{emoji} [매도] {stock_name} ({stock_code})\n"
        msg += f"수량: {quantity:,}주 × {price:,}원\n"
        msg += f"수익률: {sign}{profit_rate*100:.2f}%\n"
        msg += f"사유: {reason}"

        self.notifier.send_message(msg)

    def notify_error(self, message: str) -> None:
        """에러 알림"""
        self.notifier.send_error(message)

    def notify_summary(
        self,
        buy_count: int,
        sell_count: int,
        total_profit: int
    ) -> None:
        """일일 요약 알림"""
        sign = "+" if total_profit >= 0 else ""
        msg = f"📊 [일일 요약]\n"
        msg += f"매수: {buy_count}건\n"
        msg += f"매도: {sell_count}건\n"
        msg += f"실현손익: {sign}{total_profit:,}원"

        self.notifier.send_message(msg)

    def log(self, message: str, level: str = "INFO") -> None:
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = "[DRY-RUN] " if self.dry_run else ""
        print(f"[{timestamp}] {prefix}[{level}] {message}")


class TradingSession:
    """트레이딩 세션 컨텍스트 매니저

    사용법:
        with TradingSession(trader) as session:
            session.execute_buys(buy_list)
            session.execute_sells(sell_list)
    """

    def __init__(self, trader: BaseTrader):
        self.trader = trader
        self.result = TradeResult(success=True, mode='session')
        self._started_at = None

    def __enter__(self):
        self._started_at = datetime.now()
        self.trader.reset_daily_state()

        # 장 시간 체크
        can_trade, reason = self.trader.check_market_hours()
        if not can_trade and not self.trader.dry_run:
            raise MarketClosedError(f"거래 불가: {reason}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (datetime.now() - self._started_at).total_seconds()
        self.trader.log(f"세션 종료 (소요: {elapsed:.1f}초)")

        if exc_type is not None:
            self.result.success = False
            self.result.errors.append(str(exc_val))
            return False

        return True
