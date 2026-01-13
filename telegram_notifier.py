"""
텔레그램 알림 모듈
- 포트폴리오 하락 알림 전송
"""

import requests
from datetime import datetime, timezone, timedelta
from config import TelegramConfig, SIGNAL_NAMES_KR

# 한국 시간대 (UTC+9)
KST = timezone(timedelta(hours=9))


def get_kst_now():
    """한국 시간 반환"""
    return datetime.now(KST)


class TelegramNotifier:
    """텔레그램 봇 메시지 전송 클래스"""

    def __init__(self, bot_token=None):
        self.bot_token = bot_token or TelegramConfig.BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
        """텔레그램 메시지 전송"""
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": parse_mode
                },
                timeout=10
            )
            return response.json().get("ok", False)
        except Exception as e:
            print(f"[텔레그램] 메시지 전송 실패: {e}")
            return False

    def verify_chat_id(self, chat_id: str) -> bool:
        """Chat ID 검증 (테스트 메시지 전송)"""
        test_message = "🔔 주식 알림 서비스 연동 테스트입니다.\n정상적으로 수신되었습니다!"
        return self.send_message(chat_id, test_message)

    def send_alert(self, chat_id: str, alert_type: str, stock_data: dict) -> bool:
        """알림 유형별 메시지 전송"""
        if alert_type == "sell_signal":
            message = self.format_sell_alert(stock_data)
        elif alert_type == "stop_loss":
            message = self.format_stoploss_alert(stock_data)
        elif alert_type == "decline_pattern":
            message = self.format_decline_alert(stock_data)
        else:
            message = self.format_generic_alert(stock_data)

        return self.send_message(chat_id, message)

    @staticmethod
    def format_sell_alert(stock: dict) -> str:
        """매도 신호 알림 메시지"""
        signals_kr = [SIGNAL_NAMES_KR.get(s, s) for s in stock.get('danger_signals', [])]
        signals_text = '\n'.join(f"• {s}" for s in signals_kr[:5])

        return f"""📉 <b>[매도 신호]</b> {stock['name']} ({stock['code']})

💰 현재가: {stock['current_price']:,}원 ({stock['change_pct']:+.1f}%)
📊 수익률: {stock['profit_rate']:+.1f}%
🎯 기술점수: {stock['score']}점

⚠️ 감지된 신호:
{signals_text}

💡 <b>의견: {stock['opinion']}</b>
→ {stock.get('reason', '수익 실현 검토')}

━━━━━━━━━━━━━━━
🕐 {get_kst_now().strftime('%Y-%m-%d %H:%M')}"""

    @staticmethod
    def format_stoploss_alert(stock: dict) -> str:
        """손절 신호 알림 메시지"""
        return f"""🚨 <b>[손절 신호]</b> {stock['name']} ({stock['code']})

⚠️ 손실률: {stock['profit_rate']:.1f}%
💰 현재가: {stock['current_price']:,}원
📉 매수가: {stock['buy_price']:,}원
📊 기술점수: {stock['score']}점

💡 <b>의견: {stock['opinion']}</b>
→ {stock.get('reason', '추가 하락 위험')}

⛔ 손절 검토가 필요합니다.

━━━━━━━━━━━━━━━
🕐 {get_kst_now().strftime('%Y-%m-%d %H:%M')}"""

    @staticmethod
    def format_decline_alert(stock: dict) -> str:
        """하락 징후 알림 메시지"""
        signals_kr = [SIGNAL_NAMES_KR.get(s, s) for s in stock.get('danger_signals', [])]
        signals_text = '\n'.join(f"• {s}" for s in signals_kr[:5])

        return f"""⚠️ <b>[하락 징후]</b> {stock['name']} ({stock['code']})

💰 현재가: {stock['current_price']:,}원 ({stock['change_pct']:+.1f}%)
📊 기술점수: {stock['score']}점

🔻 위험 신호 {len(stock.get('danger_signals', []))}개 감지:
{signals_text}

💡 추세를 주시하세요.

━━━━━━━━━━━━━━━
🕐 {get_kst_now().strftime('%Y-%m-%d %H:%M')}"""

    @staticmethod
    def format_generic_alert(stock: dict) -> str:
        """일반 알림 메시지"""
        return f"""📢 <b>[알림]</b> {stock['name']} ({stock['code']})

💰 현재가: {stock['current_price']:,}원
📊 기술점수: {stock['score']}점
💡 의견: {stock.get('opinion', '관망')}

━━━━━━━━━━━━━━━
🕐 {get_kst_now().strftime('%Y-%m-%d %H:%M')}"""

    def send_daily_summary(self, chat_id: str, alerts_sent: list) -> bool:
        """일일 요약 알림 전송"""
        if not alerts_sent:
            return True

        summary_lines = []
        for alert in alerts_sent[:10]:
            emoji = {'sell_signal': '📉', 'stop_loss': '🚨', 'decline_pattern': '⚠️'}.get(alert['type'], '📢')
            summary_lines.append(f"{emoji} {alert['name']} ({alert['code']})")

        summary_text = '\n'.join(summary_lines)

        message = f"""📋 <b>[오늘의 알림 요약]</b>

총 {len(alerts_sent)}건의 알림이 발생했습니다.

{summary_text}

━━━━━━━━━━━━━━━
🕐 {get_kst_now().strftime('%Y-%m-%d %H:%M')}"""

        return self.send_message(chat_id, message)


# 단독 실행 테스트
if __name__ == "__main__":
    notifier = TelegramNotifier()

    # 테스트 데이터
    test_stock = {
        'code': '005930',
        'name': '삼성전자',
        'current_price': 72000,
        'buy_price': 65000,
        'profit_rate': 10.8,
        'change_pct': -2.1,
        'score': 35,
        'opinion': '매도',
        'reason': '수익 실현 권장',
        'danger_signals': ['DEAD_CROSS_5_20', 'RSI_OVERBOUGHT', 'CMF_STRONG_OUTFLOW']
    }

    # 테스트 전송 (config의 기본 chat_id로)
    print("테스트 메시지 전송 중...")
    result = notifier.send_alert(TelegramConfig.CHAT_ID, "sell_signal", test_stock)
    print(f"전송 결과: {'성공' if result else '실패'}")
