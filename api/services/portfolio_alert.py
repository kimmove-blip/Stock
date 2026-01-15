"""
포트폴리오 알림 서비스
- 사용자 포트폴리오 상태 모니터링
- 텔레그램 알림 발송
- 푸시 알림 발송
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DatabaseManager

# VAPID 설정
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:admin@example.com")

# 마지막 알림 상태 저장 (메모리)
# {user_id: {stock_code: {'opinion': str, 'profit_loss_rate': float, 'last_alert': datetime}}}
_last_status = {}


def send_telegram_message(chat_id: str, message: str) -> bool:
    """텔레그램 메시지 전송"""
    import requests
    from config import TelegramConfig

    try:
        api_url = f"https://api.telegram.org/bot{TelegramConfig.BOT_TOKEN}/sendMessage"
        response = requests.post(
            api_url,
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        return response.json().get("ok", False)
    except Exception as e:
        print(f"[텔레그램] 메시지 전송 실패: {e}")
        return False


def send_push_notification(subscription: dict, title: str, body: str, url: str = None) -> bool:
    """푸시 알림 전송"""
    try:
        from pywebpush import webpush, WebPushException

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-72x72.png",
            "url": url or "/"
        })

        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"]
                }
            },
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_EMAIL}
        )
        return True
    except Exception as e:
        print(f"[푸시] 알림 전송 실패: {e}")
        return False


def send_push_to_user(db: DatabaseManager, user_id: int, title: str, body: str, url: str = None) -> int:
    """사용자의 모든 구독에 푸시 알림 전송"""
    subscriptions = db.get_all_push_subscriptions_for_user(user_id)
    success_count = 0

    for sub in subscriptions:
        if send_push_notification(sub, title, body, url):
            success_count += 1

    return success_count


def analyze_stock_for_alert(code: str) -> dict:
    """종목 분석 (알림용)"""
    try:
        import FinanceDataReader as fdr
        from pykrx import stock as krx

        # OHLCV 데이터
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        ohlcv = krx.get_market_ohlcv(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            code
        )

        if ohlcv is None or ohlcv.empty:
            return None

        current_price = int(ohlcv.iloc[-1]['종가'])

        # 컬럼명 변환
        ohlcv = ohlcv.rename(columns={
            '시가': 'Open',
            '고가': 'High',
            '저가': 'Low',
            '종가': 'Close',
            '거래량': 'Volume'
        })

        # 기술적 분석
        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()
        result = analyst.analyze_full(ohlcv)

        if result is None:
            score_tuple = analyst.analyze(ohlcv)
            score = score_tuple[0] if isinstance(score_tuple, tuple) else 50
        else:
            score = result.get('score', 50)

        # 의견 결정
        if score >= 70:
            opinion = '매수'
        elif score >= 50:
            opinion = '관망'
        elif score >= 30:
            opinion = '주의'
        else:
            opinion = '하락 신호'

        return {
            'current_price': current_price,
            'opinion': opinion,
            'score': score
        }

    except Exception as e:
        print(f"[알림] 분석 실패 [{code}]: {e}")
        return None


def check_portfolio_alerts():
    """포트폴리오 알림 체크 및 발송"""
    global _last_status

    print(f"[알림] 포트폴리오 알림 체크 시작: {datetime.now()}")

    try:
        db = DatabaseManager()

        # 알림 활성화된 사용자 조회 (텔레그램 또는 푸시)
        with db.get_connection() as conn:
            users = conn.execute("""
                SELECT id, username, telegram_chat_id, telegram_alerts_enabled, push_alerts_enabled
                FROM users
                WHERE (telegram_alerts_enabled = 1 AND telegram_chat_id IS NOT NULL)
                   OR push_alerts_enabled = 1
                AND is_active = 1
            """).fetchall()

        if not users:
            print("[알림] 알림 활성화된 사용자 없음")
            return

        print(f"[알림] {len(users)}명 사용자 체크")

        for user in users:
            user_id = user['id']
            username = user['username']
            chat_id = user['telegram_chat_id']
            telegram_enabled = user['telegram_alerts_enabled']
            push_enabled = user['push_alerts_enabled']

            # 사용자 포트폴리오 조회
            portfolio = db.get_portfolio(user_id)
            if not portfolio:
                continue

            # 사용자별 상태 초기화
            if user_id not in _last_status:
                _last_status[user_id] = {}

            alerts_to_send = []

            for item in portfolio:
                code = item['stock_code']
                name = item['stock_name'] or code
                buy_price = item['buy_price'] or 0
                quantity = item['quantity'] or 1

                # 분석 실행
                result = analyze_stock_for_alert(code)
                if not result:
                    continue

                current_price = result['current_price']
                opinion = result['opinion']
                score = result['score']

                # 수익률 계산
                if buy_price > 0:
                    profit_loss_rate = round((current_price - buy_price) / buy_price * 100, 2)
                else:
                    profit_loss_rate = 0

                # 이전 상태
                last = _last_status[user_id].get(code, {})
                last_opinion = last.get('opinion')
                last_alert_time = last.get('last_alert')

                # 중복 알림 방지 (같은 종목에 대해 1시간 내 재알림 안함)
                if last_alert_time:
                    time_diff = datetime.now() - last_alert_time
                    if time_diff < timedelta(hours=1):
                        continue

                # 알림 조건 체크
                should_alert = False
                alert_reason = ""

                # 1. 의견이 '하락 신호'로 변경됨
                if opinion == '하락 신호' and last_opinion != '하락 신호':
                    should_alert = True
                    alert_reason = "하락 신호 감지"

                # 2. 의견이 '주의'로 변경됨
                elif opinion == '주의' and last_opinion not in ['주의', '하락 신호', None]:
                    should_alert = True
                    alert_reason = "주의 신호 감지"

                # 3. 손실률이 -5% 이하로 하락
                elif profit_loss_rate <= -5 and last.get('profit_loss_rate', 0) > -5:
                    should_alert = True
                    alert_reason = "손실률 -5% 돌파"

                # 4. 손실률이 -10% 이하로 하락
                elif profit_loss_rate <= -10 and last.get('profit_loss_rate', 0) > -10:
                    should_alert = True
                    alert_reason = "손실률 -10% 돌파"

                if should_alert:
                    alerts_to_send.append({
                        'code': code,
                        'name': name,
                        'reason': alert_reason,
                        'opinion': opinion,
                        'score': score,
                        'current_price': current_price,
                        'profit_loss_rate': profit_loss_rate
                    })

                # 상태 업데이트
                _last_status[user_id][code] = {
                    'opinion': opinion,
                    'profit_loss_rate': profit_loss_rate,
                    'last_alert': datetime.now() if should_alert else last_alert_time
                }

            # 알림 발송
            if alerts_to_send:
                for alert in alerts_to_send:
                    # 텔레그램 메시지 (HTML 형식)
                    telegram_message = f"""<b>📊 포트폴리오 알림</b>

<b>{alert['name']}</b> ({alert['code']})

⚠️ <b>{alert['reason']}</b>

• 현재가: {alert['current_price']:,}원
• 수익률: {alert['profit_loss_rate']:+.2f}%
• AI 점수: {alert['score']}점
• 상태: {alert['opinion']}

<i>※ 본 알림은 참고용이며, 투자 판단은 본인의 책임입니다.</i>"""

                    # 푸시 알림용 간단 메시지
                    push_title = f"📊 {alert['name']} - {alert['reason']}"
                    push_body = f"현재가: {alert['current_price']:,}원 | 수익률: {alert['profit_loss_rate']:+.2f}% | {alert['opinion']}"

                    telegram_success = False
                    push_success = False

                    # 텔레그램 알림 발송
                    if telegram_enabled and chat_id:
                        telegram_success = send_telegram_message(chat_id, telegram_message)
                        if telegram_success:
                            print(f"[텔레그램] 전송 성공: {username} - {alert['name']}")

                    # 푸시 알림 발송
                    if push_enabled:
                        push_count = send_push_to_user(
                            db, user_id, push_title, push_body,
                            url=f"/stock/{alert['code']}"
                        )
                        if push_count > 0:
                            push_success = True
                            print(f"[푸시] 전송 성공: {username} - {alert['name']} ({push_count}개 기기)")

                    # 알림 기록 저장 (하나라도 성공하면)
                    if telegram_success or push_success:
                        with db.get_connection() as conn:
                            conn.execute("""
                                INSERT INTO alert_history (user_id, stock_code, alert_type, message)
                                VALUES (?, ?, ?, ?)
                            """, (user_id, alert['code'], alert['reason'], telegram_message))
                            conn.commit()
                    else:
                        print(f"[알림] 전송 실패: {username} - {alert['name']}")

        print(f"[알림] 포트폴리오 알림 체크 완료: {datetime.now()}")

    except Exception as e:
        print(f"[알림] 오류: {e}")
        import traceback
        traceback.print_exc()


def run_portfolio_alert_check():
    """포트폴리오 알림 체크 (스레드에서 호출)"""
    try:
        check_portfolio_alerts()
    except Exception as e:
        print(f"[알림] 실행 오류: {e}")


if __name__ == "__main__":
    # 테스트 실행
    check_portfolio_alerts()
