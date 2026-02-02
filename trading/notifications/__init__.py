"""
트레이딩 알림 모듈

사용법:
    from trading.notifications import TelegramNotifier, get_notifier

    # 텔레그램 알림
    notifier = TelegramNotifier(bot_token, chat_id)
    notifier.send_message("매수 체결: 삼성전자 10주")

    # 팩토리 함수
    notifier = get_notifier('telegram', config)
    notifier.send_trade_alert(trade_info)
"""

from .push_notifier import (
    BaseNotifier,
    TelegramNotifier,
    ConsoleNotifier,
    get_notifier,
    TradeAlert,
)

__all__ = [
    'BaseNotifier',
    'TelegramNotifier',
    'ConsoleNotifier',
    'get_notifier',
    'TradeAlert',
]
