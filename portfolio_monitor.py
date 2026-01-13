#!/usr/bin/env python3
"""
포트폴리오 모니터링 스크립트
- 사용자 포트폴리오를 분석하여 하락 징후 감지 시 텔레그램 알림 전송
- 크론으로 장중 30분마다 실행

사용법:
    python portfolio_monitor.py           # 기본 실행
    python portfolio_monitor.py --test    # 테스트 모드 (알림 전송 안 함)
    python portfolio_monitor.py --force   # 장외 시간에도 실행
"""

import argparse
from datetime import datetime, time
import sys
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from database.db_manager import DatabaseManager
from portfolio_advisor import PortfolioAdvisor
from telegram_notifier import TelegramNotifier
from config import SignalCategories


class PortfolioMonitor:
    """포트폴리오 하락 감지 및 알림"""

    # 위험 신호 목록
    DANGER_SIGNALS = [
        'DEAD_CROSS_5_20', 'DEAD_CROSS_20_60',
        'RSI_OVERBOUGHT', 'BEARISH_ENGULFING', 'EVENING_STAR',
        'CMF_STRONG_OUTFLOW', 'MFI_OVERBOUGHT', 'BB_UPPER_BREAK',
        'CCI_OVERBOUGHT', 'WILLR_OVERBOUGHT'
    ]

    def __init__(self, test_mode=False):
        self.db = DatabaseManager()
        self.advisor = PortfolioAdvisor()
        self.notifier = TelegramNotifier()
        self.test_mode = test_mode
        self.alerts_sent = []

    def is_market_hours(self) -> bool:
        """장중 시간 확인 (평일 09:00~15:30)"""
        now = datetime.now()

        # 주말 제외
        if now.weekday() >= 5:
            return False

        market_open = time(9, 0)
        market_close = time(15, 30)
        current_time = now.time()

        return market_open <= current_time <= market_close

    def get_alert_users(self) -> list:
        """텔레그램 알림 활성화된 사용자 조회"""
        return self.db.get_users_with_telegram_enabled()

    def analyze_stock(self, code: str, buy_price: float) -> dict:
        """단일 종목 분석"""
        return self.advisor.analyze_stock(code, buy_price)

    def detect_alert_type(self, analysis: dict, profit_rate: float) -> tuple:
        """
        알림 유형 감지 - 의견 기반으로만 알림

        Returns:
            (alert_type, should_alert): 알림 유형과 알림 발송 여부
        """
        if analysis is None:
            return None, False

        opinion = analysis.get('opinion', '')

        # 매도 의견일 때만 알림
        if opinion in ['강력매도', '매도']:
            return 'sell_signal', True

        # 손절 의견일 때만 알림
        if opinion in ['손절', '손절검토']:
            return 'stop_loss', True

        return None, False

    def process_user_portfolio(self, user: dict) -> list:
        """
        사용자 포트폴리오 분석 및 알림 처리

        Returns:
            list: 전송된 알림 목록
        """
        user_id = user['id']
        chat_id = user['telegram_chat_id']
        username = user.get('username', 'unknown')

        print(f"\n[사용자] {username} (ID: {user_id})")

        # 포트폴리오 조회
        portfolio = self.db.get_portfolio(user_id)
        if not portfolio:
            print("    → 포트폴리오 없음")
            return []

        print(f"    → {len(portfolio)}개 종목 분석 중...")

        alerts = []

        for item in portfolio:
            code = item['stock_code']
            name = item.get('stock_name', code)
            buy_price = item.get('buy_price', 0)

            # 분석
            analysis = self.analyze_stock(code, buy_price)
            if analysis is None:
                continue

            # 수익률 계산
            current_price = analysis['current_price']
            if buy_price > 0:
                profit_rate = ((current_price - buy_price) / buy_price) * 100
            else:
                profit_rate = 0

            # 알림 유형 감지
            alert_type, should_alert = self.detect_alert_type(analysis, profit_rate)

            if not should_alert:
                continue

            # 중복 알림 체크
            if self.db.was_alert_sent_today(user_id, code, alert_type):
                print(f"    → [{name}] {alert_type} 이미 전송됨 (오늘)")
                continue

            # 위험 신호 추출
            danger_signals = [s for s in (analysis.get('signals', []) or []) if s in self.DANGER_SIGNALS]

            # 알림 데이터 구성
            stock_data = {
                'code': code,
                'name': name,
                'current_price': int(current_price),
                'buy_price': int(buy_price),
                'profit_rate': profit_rate,
                'change_pct': analysis.get('indicators', {}).get('change_pct', 0),
                'score': analysis['score'],
                'opinion': analysis.get('opinion', ''),
                'reason': analysis.get('reason', ''),
                'danger_signals': danger_signals
            }

            # 알림 전송
            if self.test_mode:
                print(f"    → [테스트] {name}: {alert_type} 알림 (전송 안 함)")
            else:
                success = self.notifier.send_alert(chat_id, alert_type, stock_data)
                if success:
                    # 알림 기록 저장
                    self.db.add_alert_history(user_id, code, alert_type, f"{name}: {analysis.get('opinion', '')}")
                    print(f"    → [{name}] {alert_type} 알림 전송 완료")
                    alerts.append({
                        'code': code,
                        'name': name,
                        'type': alert_type
                    })
                else:
                    print(f"    → [{name}] 알림 전송 실패")

        return alerts

    def run(self, force=False):
        """모니터링 실행"""
        print("=" * 60)
        print(f"  포트폴리오 모니터링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 장중 시간 확인
        if not force and not self.is_market_hours():
            print("\n[스킵] 장외 시간입니다. --force 옵션으로 강제 실행 가능")
            return

        # 알림 활성화된 사용자 조회
        users = self.get_alert_users()
        if not users:
            print("\n[알림] 텔레그램 알림이 활성화된 사용자가 없습니다.")
            return

        print(f"\n[대상] {len(users)}명의 사용자 포트폴리오 분석")

        # 각 사용자 포트폴리오 분석
        total_alerts = []
        for user in users:
            try:
                alerts = self.process_user_portfolio(user)
                total_alerts.extend(alerts)
            except Exception as e:
                print(f"    [오류] 사용자 {user.get('username', 'unknown')} 처리 실패: {e}")

        # 결과 요약
        print("\n" + "=" * 60)
        print(f"  모니터링 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  총 알림 발송: {len(total_alerts)}건")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='포트폴리오 하락 모니터링')
    parser.add_argument('--test', action='store_true', help='테스트 모드 (알림 전송 안 함)')
    parser.add_argument('--force', action='store_true', help='장외 시간에도 실행')

    args = parser.parse_args()

    monitor = PortfolioMonitor(test_mode=args.test)
    monitor.run(force=args.force)


if __name__ == "__main__":
    main()
