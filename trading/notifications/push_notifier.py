"""
알림 전송 모듈

목적:
- auto_trader.py에서 알림 로직 분리
- 텔레그램 외 다른 채널 확장 가능
- 표준 알림 인터페이스 제공

지원 채널:
- Telegram (기본)
- Console (개발/테스트용)
"""

import os
import requests
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum


class AlertType(Enum):
    """알림 유형"""
    BUY = "buy"          # 매수 체결
    SELL = "sell"        # 매도 체결
    STOP_LOSS = "stop_loss"    # 손절
    TAKE_PROFIT = "take_profit"  # 익절
    SUGGESTION = "suggestion"    # 매수 제안
    WARNING = "warning"      # 경고
    INFO = "info"         # 정보
    ERROR = "error"        # 에러


@dataclass
class TradeAlert:
    """거래 알림 정보"""
    alert_type: AlertType
    stock_code: str
    stock_name: str
    quantity: int = 0
    price: int = 0
    profit_rate: Optional[float] = None
    reason: Optional[str] = None
    score: Optional[int] = None
    signals: List[str] = field(default_factory=list)
    additional_info: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def format_message(self) -> str:
        """기본 포맷 메시지 생성"""
        type_emoji = {
            AlertType.BUY: "🔵",
            AlertType.SELL: "🔴",
            AlertType.STOP_LOSS: "🛑",
            AlertType.TAKE_PROFIT: "💰",
            AlertType.SUGGESTION: "💡",
            AlertType.WARNING: "⚠️",
            AlertType.INFO: "ℹ️",
            AlertType.ERROR: "❌",
        }

        emoji = type_emoji.get(self.alert_type, "📢")
        action = self.alert_type.value.upper()

        lines = [f"{emoji} [{action}] {self.stock_name} ({self.stock_code})"]

        if self.quantity > 0:
            lines.append(f"수량: {self.quantity:,}주")
        if self.price > 0:
            lines.append(f"가격: {self.price:,}원")
        if self.profit_rate is not None:
            sign = "+" if self.profit_rate >= 0 else ""
            lines.append(f"수익률: {sign}{self.profit_rate*100:.2f}%")
        if self.score is not None:
            lines.append(f"점수: {self.score}점")
        if self.reason:
            lines.append(f"사유: {self.reason}")
        if self.signals:
            lines.append(f"신호: {', '.join(self.signals[:5])}")

        lines.append(f"시간: {self.timestamp.strftime('%H:%M:%S')}")

        return "\n".join(lines)


class BaseNotifier(ABC):
    """알림 전송 추상 베이스 클래스"""

    @abstractmethod
    def send_message(self, message: str) -> bool:
        """메시지 전송

        Args:
            message: 전송할 메시지

        Returns:
            성공 여부
        """
        pass

    def send_trade_alert(self, alert: TradeAlert) -> bool:
        """거래 알림 전송"""
        return self.send_message(alert.format_message())

    def send_buy_alert(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: int,
        score: Optional[int] = None,
        signals: Optional[List[str]] = None
    ) -> bool:
        """매수 알림"""
        alert = TradeAlert(
            alert_type=AlertType.BUY,
            stock_code=stock_code,
            stock_name=stock_name,
            quantity=quantity,
            price=price,
            score=score,
            signals=signals or []
        )
        return self.send_trade_alert(alert)

    def send_sell_alert(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: int,
        profit_rate: float,
        reason: str
    ) -> bool:
        """매도 알림"""
        alert_type = AlertType.SELL
        if "손절" in reason:
            alert_type = AlertType.STOP_LOSS
        elif "익절" in reason:
            alert_type = AlertType.TAKE_PROFIT

        alert = TradeAlert(
            alert_type=alert_type,
            stock_code=stock_code,
            stock_name=stock_name,
            quantity=quantity,
            price=price,
            profit_rate=profit_rate,
            reason=reason
        )
        return self.send_trade_alert(alert)

    def send_suggestion_alert(
        self,
        stock_code: str,
        stock_name: str,
        score: int,
        signals: List[str],
        target_price: Optional[int] = None,
        stop_loss_price: Optional[int] = None
    ) -> bool:
        """매수 제안 알림"""
        alert = TradeAlert(
            alert_type=AlertType.SUGGESTION,
            stock_code=stock_code,
            stock_name=stock_name,
            score=score,
            signals=signals,
            additional_info={
                'target_price': target_price,
                'stop_loss_price': stop_loss_price
            }
        )
        return self.send_trade_alert(alert)

    def send_warning(self, message: str) -> bool:
        """경고 메시지"""
        return self.send_message(f"⚠️ [WARNING] {message}")

    def send_error(self, message: str) -> bool:
        """에러 메시지"""
        return self.send_message(f"❌ [ERROR] {message}")

    def send_daily_summary(
        self,
        total_trades: int,
        total_profit: float,
        win_rate: float,
        holdings_count: int,
        best_trade: Optional[str] = None,
        worst_trade: Optional[str] = None
    ) -> bool:
        """일일 요약 알림"""
        lines = [
            "📊 [일일 매매 요약]",
            f"총 거래: {total_trades}건",
            f"수익: {total_profit:+,.0f}원",
            f"승률: {win_rate*100:.1f}%",
            f"보유 종목: {holdings_count}개",
        ]
        if best_trade:
            lines.append(f"최고: {best_trade}")
        if worst_trade:
            lines.append(f"최저: {worst_trade}")

        return self.send_message("\n".join(lines))


class TelegramNotifier(BaseNotifier):
    """텔레그램 알림 전송"""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True
    ):
        """
        Args:
            bot_token: 텔레그램 봇 토큰
            chat_id: 채팅 ID
            enabled: 활성화 여부
        """
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
        self.enabled = enabled
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_message(self, message: str) -> bool:
        """텔레그램으로 메시지 전송"""
        if not self.enabled:
            return True

        if not self.bot_token or not self.chat_id:
            print("텔레그램 설정 누락 (bot_token 또는 chat_id)")
            return False

        try:
            response = requests.post(
                self.api_url,
                data={
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                },
                timeout=10
            )

            if response.status_code == 200:
                return True
            else:
                print(f"텔레그램 전송 실패: {response.status_code}")
                return False

        except Exception as e:
            print(f"텔레그램 전송 오류: {e}")
            return False

    def send_with_buttons(
        self,
        message: str,
        buttons: List[List[Dict[str, str]]]
    ) -> bool:
        """인라인 버튼과 함께 메시지 전송

        Args:
            message: 메시지
            buttons: [[{text, callback_data}]] 형식의 버튼 배열
        """
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        try:
            import json
            response = requests.post(
                self.api_url,
                data={
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'HTML',
                    'reply_markup': json.dumps({
                        'inline_keyboard': buttons
                    })
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"텔레그램 버튼 전송 오류: {e}")
            return False


class ConsoleNotifier(BaseNotifier):
    """콘솔 출력 알림 (개발/테스트용)"""

    def __init__(self, prefix: str = "[NOTIFY]"):
        self.prefix = prefix

    def send_message(self, message: str) -> bool:
        """콘솔에 메시지 출력"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"{self.prefix} [{timestamp}]")
        print(message)
        print("-" * 40)
        return True


class MultiNotifier(BaseNotifier):
    """복수 채널 알림"""

    def __init__(self, notifiers: List[BaseNotifier]):
        self.notifiers = notifiers

    def send_message(self, message: str) -> bool:
        """모든 채널로 메시지 전송"""
        results = []
        for notifier in self.notifiers:
            results.append(notifier.send_message(message))
        return all(results)

    def add_notifier(self, notifier: BaseNotifier) -> None:
        """알림 채널 추가"""
        self.notifiers.append(notifier)


def get_notifier(
    notifier_type: str = 'telegram',
    config: Optional[Dict] = None
) -> BaseNotifier:
    """알림 인스턴스 팩토리

    Args:
        notifier_type: 'telegram', 'console', 'multi'
        config: 설정 딕셔너리

    Returns:
        BaseNotifier 인스턴스
    """
    config = config or {}

    if notifier_type == 'telegram':
        return TelegramNotifier(
            bot_token=config.get('bot_token'),
            chat_id=config.get('chat_id'),
            enabled=config.get('enabled', True)
        )
    elif notifier_type == 'console':
        return ConsoleNotifier(
            prefix=config.get('prefix', '[NOTIFY]')
        )
    elif notifier_type == 'multi':
        notifiers = []
        if config.get('telegram'):
            notifiers.append(get_notifier('telegram', config['telegram']))
        if config.get('console'):
            notifiers.append(get_notifier('console', config['console']))
        return MultiNotifier(notifiers)
    else:
        return ConsoleNotifier()


# 전역 인스턴스 (싱글톤 패턴)
_default_notifier: Optional[BaseNotifier] = None


def get_default_notifier() -> BaseNotifier:
    """기본 알림 인스턴스 반환"""
    global _default_notifier
    if _default_notifier is None:
        # 환경변수에서 텔레그램 설정 확인
        if os.environ.get('TELEGRAM_BOT_TOKEN'):
            _default_notifier = TelegramNotifier()
        else:
            _default_notifier = ConsoleNotifier()
    return _default_notifier


def set_default_notifier(notifier: BaseNotifier) -> None:
    """기본 알림 인스턴스 설정"""
    global _default_notifier
    _default_notifier = notifier


def send_notification(message: str) -> bool:
    """기본 알림 채널로 메시지 전송"""
    return get_default_notifier().send_message(message)
