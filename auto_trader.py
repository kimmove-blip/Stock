#!/usr/bin/env python3
"""
자동매매 시스템

사용법:
    python auto_trader.py              # 1회 실행
    python auto_trader.py --dry-run    # 테스트 실행 (주문 X)
    python auto_trader.py --report     # 성과 리포트만 출력
    python auto_trader.py --all        # 전체 사용자 실행 (CSV 스코어 사용)

cron 설정 예시:
    # 장중 5분 간격 (record_intraday_scores.py가 CSV 생성 후 실행)
    3,8,13,18,23,28,33,38,43,48,53,58 9-15 * * 1-5 python auto_trader.py --all
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent))

from api.services.kis_client import KISClient
from trading.order_executor import OrderExecutor
from trading.risk_manager import RiskManager, TradingLimits
from trading.trade_logger import TradeLogger, BuySuggestionManager
from trading.nasdaq_monitor import get_adjusted_investment_amount
from technical_analyst import TechnicalAnalyst
from market_screener import MarketScreener
from config import AutoTraderConfig, TelegramConfig, OUTPUT_DIR, SIGNAL_NAMES_KR

# CSV 스코어 디렉토리
INTRADAY_SCORES_DIR = Path(__file__).parent / "output" / "intraday_scores"


def parse_condition(condition_str: str) -> list:
    """
    조건 문자열을 파싱하여 조건 리스트로 변환
    예: "V1>=60 AND V5>=50 AND V4>40" -> [{'score': 'v1', 'op': '>=', 'value': 60, 'connector': 'AND'}, ...]
    """
    import re
    if not condition_str:
        return []

    parts = re.split(r'\s+(AND|OR)\s+', condition_str, flags=re.IGNORECASE)
    conditions = []
    current_connector = 'AND'

    for part in parts:
        part = part.strip()
        if part.upper() in ('AND', 'OR'):
            current_connector = part.upper()
        else:
            match = re.match(r'^(V\d+)\s*(>=|<=|>|<|=)\s*(\d+)$', part, re.IGNORECASE)
            if match:
                conditions.append({
                    'score': match.group(1).lower(),  # v1, v2, v4, v5
                    'op': match.group(2),
                    'value': int(match.group(3)),
                    'connector': current_connector
                })
    return conditions


def evaluate_conditions(conditions: list, scores: dict) -> bool:
    """
    조건 리스트를 스코어 딕셔너리로 평가
    scores: {'v1': 70, 'v2': 60, 'v4': 45, 'v5': 55}
    """
    if not conditions:
        return False

    results = []
    connectors = []

    for cond in conditions:
        score_key = cond['score']
        score_value = scores.get(score_key, 0)
        op = cond['op']
        target = cond['value']

        if op == '>=':
            result = score_value >= target
        elif op == '<=':
            result = score_value <= target
        elif op == '>':
            result = score_value > target
        elif op == '<':
            result = score_value < target
        elif op == '=':
            result = score_value == target
        else:
            result = False

        results.append(result)
        if len(results) > 1:
            connectors.append(cond['connector'])

    # 조건 평가 (AND/OR 처리)
    if len(results) == 1:
        return results[0]

    # 순차적으로 평가
    final = results[0]
    for i, connector in enumerate(connectors):
        if connector == 'AND':
            final = final and results[i + 1]
        else:  # OR
            final = final or results[i + 1]

    return final


def load_scores_from_csv(max_age_minutes: int = 15) -> Optional[Tuple[List[Dict], Dict]]:
    """
    가장 최근 CSV 스코어 파일을 로드하여 MarketScreener 결과 형식으로 변환
    모든 스코어 버전(v1, v2, v5)을 로드하여 각 종목에 저장

    Args:
        max_age_minutes: CSV 파일 최대 허용 경과 시간 (분)

    Returns:
        (top_stocks, stats) 튜플 또는 None
    """
    if not INTRADAY_SCORES_DIR.exists():
        print(f"  [CSV] 스코어 디렉토리 없음: {INTRADAY_SCORES_DIR}")
        return None

    # 오늘 날짜의 CSV 파일 찾기 (최신순 정렬)
    today_str = datetime.now().strftime('%Y%m%d')
    csv_files = sorted(
        INTRADAY_SCORES_DIR.glob(f"{today_str}_*.csv"),
        reverse=True
    )

    if not csv_files:
        print(f"  [CSV] 오늘 날짜 CSV 파일 없음")
        return None

    latest_csv = csv_files[0]

    # 파일 경과 시간 체크
    filename = latest_csv.stem  # 20260129_0903
    try:
        file_time = datetime.strptime(filename, '%Y%m%d_%H%M')
        elapsed_minutes = (datetime.now() - file_time).total_seconds() / 60

        if elapsed_minutes > max_age_minutes:
            print(f"  [CSV] 파일이 오래됨: {filename} ({elapsed_minutes:.0f}분 전)")
            return None
    except ValueError:
        pass  # 파싱 실패 시 경과 시간 무시

    # CSV 로드
    try:
        df = pd.read_csv(latest_csv)
        print(f"  [CSV] 로드: {latest_csv.name} ({len(df)}개 종목)")
    except Exception as e:
        print(f"  [CSV] 로드 실패: {e}")
        return None

    # 필수 컬럼 확인
    required_cols = ['code', 'name', 'close']
    if not all(col in df.columns for col in required_cols):
        print(f"  [CSV] 필수 컬럼 부족: {required_cols}")
        return None

    # 지원하는 스코어 버전
    score_versions = ['v1', 'v2', 'v4', 'v5']

    # MarketScreener 형식으로 변환
    top_stocks = []
    all_scores = {}  # {code: {'v1': x, 'v2': y, 'v5': z}}

    for _, row in df.iterrows():
        code = str(row['code']).zfill(6)

        # 모든 스코어 버전 로드
        scores = {}
        for sv in score_versions:
            scores[sv] = int(row.get(sv, 0)) if sv in df.columns else 0

        score = scores.get('v5', 0)  # 기본 정렬용 (v5)
        all_scores[code] = scores  # 모든 버전 저장

        # 시그널 파싱
        signals_str = row.get('signals', '')
        signals = signals_str.split(',') if signals_str and pd.notna(signals_str) else []

        # 거래대금 (prev_amount 또는 amount)
        amount = int(row.get('prev_amount', 0) or row.get('amount', 0) or 0)

        # 체결강도 (100 이상이면 매수세 우위)
        buy_strength = float(row.get('buy_strength', 0) or 0)

        # 거래량 비율 (5일 평균 대비)
        volume_ratio = float(row.get('volume_ratio', 0) or 0)

        stock = {
            "code": code,
            "name": row.get('name', ''),
            "market": row.get('market', 'KOSDAQ'),
            "score": score,  # 기본값 v5
            "scores": scores,  # 모든 버전: {'v1': x, 'v2': y, 'v5': z}
            "signals": signals,
            "patterns": [],
            "close": int(row.get('close', 0)),
            "change_pct": float(row.get('change_pct', 0)),
            "amount": amount,  # 거래대금
            "buy_strength": buy_strength,  # 체결강도
            "volume_ratio": volume_ratio,  # 5일 평균 대비 거래량 비율
        }
        top_stocks.append(stock)

    # 점수 내림차순 정렬 (동점 시 거래대금 많은 순)
    top_stocks.sort(key=lambda x: (x['score'], x.get('amount', 0)), reverse=True)

    stats = {
        "all_scores": all_scores,
        "csv_source": str(latest_csv),
    }

    return (top_stocks, stats)


def get_tick_size(price: int) -> int:
    """주가에 따른 호가 단위 반환"""
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


def round_to_tick(price: int, round_down: bool = True) -> int:
    """호가 단위로 반올림/내림"""
    tick = get_tick_size(price)
    if round_down:
        return (price // tick) * tick  # 내림
    else:
        return ((price + tick - 1) // tick) * tick  # 올림


class TelegramNotifier:
    """푸시 알림 발송 (텔레그램 제거됨)"""

    def __init__(self, enabled: bool = True, user_id: int = None, **kwargs):
        # kwargs로 이전 호환성 유지 (bot_token, chat_id는 무시)
        self.enabled = enabled
        self.user_id = user_id  # 푸시 알림용

    def _save_to_db(self, stock_code: str, stock_name: str, alert_type: str, message: str):
        """알림 기록을 DB에 저장 (한국 시간)"""
        if not self.user_id:
            return
        try:
            from database.db_manager import DatabaseManager
            from datetime import datetime, timezone, timedelta
            db = DatabaseManager()
            # 한국 시간 (UTC+9)
            kst = timezone(timedelta(hours=9))
            now_kst = datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S')
            with db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO alert_history (user_id, stock_code, stock_name, alert_type, message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (self.user_id, stock_code, stock_name, alert_type, message, now_kst))
                conn.commit()
        except Exception as e:
            print(f"알림 기록 저장 실패: {e}")

    def notify_buy(self, stock_name: str, price: int, quantity: int, stock_code: str = None):
        """매수 체결 알림"""
        self._save_to_db(stock_code or "", stock_name, "매수 체결", f"{price:,}원 x {quantity}주")
        self.send_push("매수 체결", f"{stock_name} {price:,}원 x {quantity}주", f"/stock/{stock_code}" if stock_code else None)

    def notify_sell(self, stock_name: str, price: int, quantity: int, profit_rate: float, reason: str, stock_code: str = None):
        """매도 체결 알림"""
        rate_str = f"+{profit_rate*100:.1f}%" if profit_rate >= 0 else f"{profit_rate*100:.1f}%"
        self._save_to_db(stock_code or "", stock_name, "매도 체결", f"{price:,}원 ({rate_str}) - {reason}")
        self.send_push("매도 체결", f"{stock_name} {price:,}원 ({rate_str})", f"/stock/{stock_code}" if stock_code else None)

    def notify_stop_loss(self, stock_name: str, price: int, profit_rate: float, stock_code: str = None):
        """손절 알림"""
        self._save_to_db(stock_code or "", stock_name, "손절", f"{price:,}원 ({profit_rate*100:.1f}%)")
        self.send_push("손절", f"{stock_name} {price:,}원 ({profit_rate*100:.1f}%)", f"/stock/{stock_code}" if stock_code else None)

    def notify_signal(self, stock_name: str, signals: List[str], stock_code: str = None):
        """매도 신호 알림"""
        signals_kr = [SIGNAL_NAMES_KR.get(s, s) for s in signals]
        self._save_to_db(stock_code or "", stock_name, "매도 신호", ', '.join(signals_kr))
        self.send_push("매도 신호", f"{stock_name}: {', '.join(signals_kr[:2])}", f"/stock/{stock_code}" if stock_code else None)

    def notify_summary(self, buy_count: int, sell_count: int, total_profit: int):
        """일일 요약 알림 (체결 없으면 생략)"""
        if buy_count == 0 and sell_count == 0:
            return  # 체결 없으면 알림 안 보냄
        self._save_to_db("", "자동매매", "일일 요약", f"매수 {buy_count}건, 매도 {sell_count}건, 손익 {total_profit:+,}원")
        self.send_push("자동매매 완료", f"매수 {buy_count}건, 매도 {sell_count}건, 손익 {total_profit:+,}원")

    def notify_error(self, error_msg: str):
        """오류 알림 (DB 저장 안 함)"""
        pass  # 오류 알림은 제거

    def send_push(self, title: str, body: str, url: str = None):
        """앱 푸시 알림 전송"""
        if not self.enabled or not self.user_id:
            return

        try:
            from api.routers.push import send_push_to_user
            send_push_to_user(self.user_id, title, body, url)
        except Exception as e:
            print(f"푸시 알림 전송 실패: {e}")

    def notify_buy_suggestion(
        self,
        stock_name: str,
        stock_code: str,
        score: int,
        probability: float,
        confidence: float,
        current_price: int,
        recommended_price: int,
        target_price: int,
        stop_loss_price: int,
        signals: List[str],
        expire_hours: int = 24
    ):
        """매수 제안 알림 (semi-auto 모드)"""
        signals_kr = [SIGNAL_NAMES_KR.get(s, s) for s in signals[:2]]

        # DB 저장
        self._save_to_db(stock_code, stock_name, "매수 제안", f"{score}점 | 추천가 {recommended_price:,}원")

        # 푸시 알림
        push_body = f"{stock_name} {score}점 | 추천가 {recommended_price:,}원"
        self.send_push(
            title="📊 매수 제안",
            body=push_body,
            url=f"/stock/{stock_code}"
        )

    def notify_suggestion(self, stock_name: str, price: int, quantity: int, stock_code: str = None):
        """매수 제안 알림 (semi 모드)"""
        self._save_to_db(stock_code or "", stock_name, "매수 제안", f"{price:,}원 x {quantity}주")
        self.send_push("📊 매수 제안", f"{stock_name} {price:,}원 x {quantity}주", f"/auto-trade/suggestions" if stock_code else None)

    def notify_sell_signal(self, stock_name: str, reasons: str, stock_code: str = None):
        """매도 신호 알림 (semi 모드 - 실행 없이 알림만)"""
        self._save_to_db(stock_code or "", stock_name, "매도 신호", reasons)
        self.send_push("⚠️ 매도 신호", f"{stock_name}: {reasons}", f"/stock/{stock_code}" if stock_code else None)

    def notify_suggestion_executed(self, stock_name: str, price: int, quantity: int, stock_code: str = None):
        """제안 매수 실행 알림"""
        self._save_to_db(stock_code or "", stock_name, "제안 매수 완료", f"{price:,}원 x {quantity}주")
        self.send_push("제안 매수 완료", f"{stock_name} {price:,}원 x {quantity}주", f"/stock/{stock_code}" if stock_code else None)


class AutoTrader:
    """자동매매 시스템"""

    def __init__(self, dry_run: bool = False, user_id: int = None, user_config: dict = None):
        """
        Args:
            dry_run: True면 주문을 실제로 실행하지 않음
            user_id: 사용자 ID (다중 사용자 지원)
            user_config: 사용자별 설정 (API 키 등)
        """
        self.dry_run = dry_run
        self.user_id = user_id
        self.user_config = user_config or {}
        self.config = AutoTraderConfig

        # 사용자별 API 키가 있으면 사용, 없으면 환경변수 사용
        app_key = self.user_config.get('app_key')
        app_secret = self.user_config.get('app_secret')
        account_number = self.user_config.get('account_number')
        is_mock = self.user_config.get('is_mock', self.config.IS_VIRTUAL)

        # KIS 클라이언트 초기화
        if app_key and app_secret and account_number:
            self.kis_client = KISClient(
                is_virtual=is_mock,
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number
            )
        else:
            self.kis_client = KISClient(is_virtual=self.config.IS_VIRTUAL)

        # 모듈 초기화 - 순서 중요: logger를 먼저 초기화해야 사용자 설정 조회 가능
        self.logger = TradeLogger()
        self.executor = OrderExecutor(self.kis_client)

        # 사용자 설정에서 max_per_stock 가져오기 (DB 설정 > config 설정)
        user_settings = self.logger.get_auto_trade_settings(user_id) if user_id else None
        max_per_stock = self.config.MAX_PER_STOCK  # 기본값 (config에서)
        stop_loss_pct = self.config.STOP_LOSS_PCT
        max_holdings = self.config.MAX_HOLDINGS
        max_daily_trades = self.config.MAX_DAILY_TRADES
        max_hold_days = self.config.MAX_HOLD_DAYS
        min_buy_score = self.config.MIN_BUY_SCORE
        min_hold_score = self.config.MIN_HOLD_SCORE

        if user_settings:
            # 사용자 설정이 있으면 해당 값 사용
            if user_settings.get('max_per_stock'):
                max_per_stock = user_settings['max_per_stock']
                print(f"[AutoTrader] 사용자 {user_id} max_per_stock: {max_per_stock:,}원")

            if user_settings.get('stop_loss_rate'):
                stop_loss_pct = -abs(user_settings['stop_loss_rate']) / 100

            if user_settings.get('max_holdings'):
                max_holdings = user_settings['max_holdings']

            if user_settings.get('max_daily_trades'):
                max_daily_trades = user_settings['max_daily_trades']

            if user_settings.get('max_holding_days'):
                max_hold_days = user_settings['max_holding_days']

            if user_settings.get('min_buy_score'):
                min_buy_score = user_settings['min_buy_score']

            if user_settings.get('sell_score') is not None:
                min_hold_score = user_settings['sell_score']
                print(f"[AutoTrader] 사용자 {user_id} sell_score: {min_hold_score}점 (매도 기준)")

        self.risk_manager = RiskManager(TradingLimits(
            max_per_stock=max_per_stock,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=self.config.TAKE_PROFIT_PCT,
            max_daily_trades=max_daily_trades,
            max_holdings=max_holdings,
            max_hold_days=max_hold_days,
            min_buy_score=min_buy_score,
            min_hold_score=min_hold_score,
            min_volume_ratio=self.config.MIN_VOLUME_RATIO,
        ))
        self.suggestion_manager = BuySuggestionManager(user_id=user_id)
        self.analyst = TechnicalAnalyst()

        # 푸시 알림 설정 (텔레그램 제거됨)
        self.notifier = TelegramNotifier(
            user_id=user_id,
            enabled=not dry_run
        )

        # 모의투자 가상 잔고 초기화
        if is_mock:
            initial_cash = getattr(self.config, 'VIRTUAL_INITIAL_CASH', 100_000_000)
            self.logger.init_virtual_balance(initial_cash, user_id=user_id)

        # 실행 통계
        self.stats = {
            "buy_orders": [],
            "sell_orders": [],
            "total_profit": 0,
        }

    def _save_alert_history(self, stock_code: str, stock_name: str, alert_type: str, message: str):
        """알림 기록 저장"""
        if not self.user_id:
            return
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            with db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO alert_history (user_id, stock_code, stock_name, alert_type, message)
                    VALUES (?, ?, ?, ?, ?)
                """, (self.user_id, stock_code, stock_name, alert_type, message))
                conn.commit()
        except Exception as e:
            print(f"알림 기록 저장 실패: {e}")

    def load_analysis_results(self) -> Optional[List[Dict]]:
        """
        최신 분석 결과 로드

        Returns:
            종목 분석 결과 리스트
        """
        # 오늘 또는 가장 최근 분석 파일 찾기
        today = datetime.now()

        for days_back in range(7):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%Y%m%d")
            json_path = OUTPUT_DIR / f"top100_{date_str}.json"

            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"분석 결과 로드: {json_path.name}")
                return data.get("stocks", [])

        print("분석 결과 파일을 찾을 수 없습니다.")
        return None

    def filter_buy_candidates(self, stocks: List[Dict]) -> List[Dict]:
        """
        매수 후보 필터링

        Args:
            stocks: 분석 결과 종목 리스트

        Returns:
            필터링된 매수 후보 리스트
        """
        candidates = []

        for stock in stocks:
            score = stock.get("score", 0)
            signals = stock.get("signals", []) + stock.get("patterns", [])

            # 점수 조건 (사용자 설정 min_buy_score 사용)
            if score < self.risk_manager.limits.min_buy_score:
                continue

            # 거래량 조건
            volume_ratio = stock.get("indicators", {}).get("volume_ratio", 0)
            if volume_ratio < self.config.MIN_VOLUME_RATIO:
                continue

            # 15% 이상 상승 종목 제외 (V5 전략)
            change_pct = stock.get("change_pct", 0)
            if change_pct >= 15:
                continue

            # 신뢰도 높은 신호 포함 여부
            has_strong_signal = any(
                s in signals for s in self.config.STRONG_BUY_SIGNALS
            )
            if not has_strong_signal:
                continue

            # 추천 매수가 계산 (피보나치 61.8% 기반)
            current_price = int(stock.get("close", 0))
            stock_code = stock.get("code")
            indicators = stock.get("indicators", {})

            # bb_mid = 피보나치 61.8% 되돌림 (60일 고점 기준)
            fib_618 = indicators.get("bb_mid", current_price * 0.97)

            # 추천 매수가 = 피보나치 61.8% 지지선
            # 매수 밴드 상한 = 추천가 +5% (현재가가 추천가의 105% 이내면 매수)
            recommended_price = int(min(fib_618, current_price * 0.97))
            buy_band_high = int(recommended_price * 1.05)

            # 목표가 +20%, 손절가 -10%
            target_price = stock.get("target_price") or int(recommended_price * 1.20)
            stop_loss_price = int(recommended_price * 0.90)

            # 전일 등락률 (시초가 갭 전략용)
            change_pct = stock.get("change_pct", 0)

            candidates.append({
                "stock_code": stock_code,
                "stock_name": stock.get("name"),
                "market": stock.get("market", "KOSDAQ"),
                "score": score,
                "signals": signals,
                "volume_ratio": volume_ratio,
                "current_price": current_price,
                "change_pct": change_pct,  # 전일 등락률 (상한가 여부 판단용)
                "recommended_price": recommended_price,
                "buy_band_high": buy_band_high,
                "target_price": target_price,
                "stop_loss_price": stop_loss_price,
                "expected_return": stock.get("expected_return"),
                "amount": stock.get("amount", 0),  # 거래대금
            })

        # 점수순 정렬 (동점 시 거래대금 많은 순)
        candidates.sort(key=lambda x: (x["score"], x.get("amount", 0)), reverse=True)

        return candidates

    def get_current_signals(self, stock_code: str, analysis_stocks: List[Dict]) -> List[str]:
        """종목의 현재 신호 조회"""
        for stock in analysis_stocks:
            if stock.get("code") == stock_code:
                return stock.get("signals", []) + stock.get("patterns", [])
        return []

    def get_current_score(self, stock_code: str, analysis_stocks: List[Dict]) -> int:
        """종목의 현재 점수 조회 (TOP100에 없으면 실시간 분석)"""
        for stock in analysis_stocks:
            if stock.get("code") == stock_code:
                return stock.get("score", 50)

        # TOP100에 없으면 실시간 분석 수행
        return self._analyze_realtime(stock_code)

    def _analyze_realtime(self, stock_code: str) -> int:
        """보유 종목 실시간 분석 (TOP100에 없는 종목용) - 변별력 강화 버전 사용"""
        try:
            df = self.analyst.get_ohlcv(stock_code, days=120)
            if df is None or len(df) < 60:
                print(f"  [실시간 분석] {stock_code}: 데이터 부족 → 70점 (중립)")
                return 70

            # 변별력 강화 버전 사용 (래치 전략)
            result = self.analyst.analyze_trend_following_strict(df)
            if result:
                score = result.get("score", 70)
                signals = result.get("signals", [])
                print(f"  [실시간 분석-Strict] {stock_code}: {score}점 (신호: {len(signals)}개)")
                return score

            print(f"  [실시간 분석] {stock_code}: 분석 실패 → 70점 (중립)")
            return 70  # 분석 실패 시 중립값 (매도 조건 미충족)
        except Exception as e:
            print(f"  [실시간 분석] {stock_code}: 오류 ({e}) → 70점 (중립)")
            return 70  # 오류 시 중립값

    def get_sma20(self, stock_code: str) -> float:
        """종목의 20일 이동평균선 조회 (래치 전략용)"""
        try:
            df = self.analyst.get_ohlcv(stock_code, days=60)
            if df is None or len(df) < 20:
                return 0
            close_col = 'Close' if 'Close' in df.columns else 'close'
            sma20 = df[close_col].rolling(window=20).mean().iloc[-1]
            return sma20
        except:
            return 0

    # ==================== 시초가 갭 전략 ====================

    def is_limit_up_stock(self, change_pct: float) -> bool:
        """상한가 종목 여부 확인 (전일 등락률 기준)"""
        return change_pct >= self.config.LIMIT_UP_THRESHOLD

    def get_opening_gap(self, stock_code: str, prev_close: int = None) -> dict:
        """
        시초가 갭 계산 (동시호가 시간대에 예상 체결가 조회)

        Returns:
            {
                'prev_close': 전일 종가,
                'expected_open': 예상 시초가 (또는 현재가),
                'gap_pct': 갭 비율 (%),
                'is_premarket': 동시호가 시간대 여부
            }
        """
        now = datetime.now()
        is_premarket = (now.hour == 8 and now.minute >= 30) or (now.hour == 9 and now.minute == 0)

        # 현재가 조회 (동시호가 중에는 예상 체결가가 반환됨)
        price_data = self.executor.client.get_current_price(stock_code)

        if not price_data:
            return {'prev_close': 0, 'expected_open': 0, 'gap_pct': 0, 'is_premarket': is_premarket}

        # 전일 종가 (인자로 받거나 API에서 조회)
        if prev_close is None or prev_close <= 0:
            prev_close = price_data.get('prev_close', 0)

        # 예상 시초가 (동시호가 중) 또는 현재가 (장중)
        expected_open = price_data.get('current_price', 0)

        # 갭 계산
        if prev_close > 0:
            gap_pct = (expected_open - prev_close) / prev_close * 100
        else:
            gap_pct = 0

        return {
            'prev_close': prev_close,
            'expected_open': expected_open,
            'gap_pct': gap_pct,
            'is_premarket': is_premarket
        }

    def evaluate_gap_strategy(self, stock_code: str, stock_name: str,
                               yesterday_change_pct: float, prev_close: int = None) -> dict:
        """
        시초가 갭 전략 평가

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            yesterday_change_pct: 전일 등락률 (상한가 여부 판단용)
            prev_close: 전일 종가

        Returns:
            {
                'action': 'BUY' | 'SKIP' | 'WAIT',
                'reason': 판단 사유,
                'gap_pct': 갭 비율,
                'order_type': 'market' | 'limit',
                'order_price': 주문가 (지정가인 경우)
            }
        """
        if not self.config.GAP_STRATEGY_ENABLED:
            return {'action': 'BUY', 'reason': '갭전략 비활성화', 'gap_pct': 0, 'order_type': 'market'}

        # 갭 정보 조회
        gap_info = self.get_opening_gap(stock_code, prev_close)
        gap_pct = gap_info['gap_pct']

        is_limit_up = self.is_limit_up_stock(yesterday_change_pct)

        if is_limit_up:
            # === 상한가 종목 전략 ===
            if self.config.LIMIT_UP_GAP_MIN <= gap_pct <= self.config.LIMIT_UP_GAP_MAX:
                return {
                    'action': 'BUY',
                    'reason': f'상한가→갭 {gap_pct:.1f}% (적정)',
                    'gap_pct': gap_pct,
                    'order_type': 'market'
                }
            elif gap_pct > self.config.LIMIT_UP_GAP_MAX:
                return {
                    'action': 'SKIP',
                    'reason': f'상한가→갭 {gap_pct:.1f}% (과열, >{self.config.LIMIT_UP_GAP_MAX}%)',
                    'gap_pct': gap_pct,
                    'order_type': None
                }
            elif gap_pct < self.config.LIMIT_UP_GAP_MIN:
                return {
                    'action': 'SKIP',
                    'reason': f'상한가→갭 {gap_pct:.1f}% (모멘텀 약함, <{self.config.LIMIT_UP_GAP_MIN}%)',
                    'gap_pct': gap_pct,
                    'order_type': None
                }
        else:
            # === 일반 종목 전략 ===
            if self.config.NORMAL_GAP_MIN <= gap_pct <= self.config.NORMAL_GAP_IDEAL_MAX:
                # 황금 구간 (3~8%)
                return {
                    'action': 'BUY',
                    'reason': f'갭 {gap_pct:.1f}% (황금구간)',
                    'gap_pct': gap_pct,
                    'order_type': 'market'
                }
            elif self.config.NORMAL_GAP_IDEAL_MAX < gap_pct <= self.config.NORMAL_GAP_MAX:
                # 조심 구간 (8~10%) - 진입은 하되 주의
                return {
                    'action': 'BUY',
                    'reason': f'갭 {gap_pct:.1f}% (주의구간)',
                    'gap_pct': gap_pct,
                    'order_type': 'market'
                }
            elif gap_pct > self.config.NORMAL_GAP_MAX:
                # 과열 구간 (10% 초과) - 스킵
                return {
                    'action': 'SKIP',
                    'reason': f'갭 {gap_pct:.1f}% (과열, >{self.config.NORMAL_GAP_MAX}%)',
                    'gap_pct': gap_pct,
                    'order_type': None
                }
            elif 0 <= gap_pct < self.config.NORMAL_GAP_MIN:
                # 모멘텀 약함 (0~3%) - 돌파 대기 또는 스킵
                return {
                    'action': 'SKIP',
                    'reason': f'갭 {gap_pct:.1f}% (모멘텀 약함, <{self.config.NORMAL_GAP_MIN}%)',
                    'gap_pct': gap_pct,
                    'order_type': None
                }
            else:
                # 갭 하락 - 매수 금지
                return {
                    'action': 'SKIP',
                    'reason': f'갭 {gap_pct:.1f}% (갭하락, 매수금지)',
                    'gap_pct': gap_pct,
                    'order_type': None
                }

        # 기본값 (도달하지 않아야 함)
        return {'action': 'SKIP', 'reason': '판단 불가', 'gap_pct': gap_pct, 'order_type': None}

    def check_market_hours(self) -> bool:
        """장 운영 시간 체크"""
        now = datetime.now()

        # 주말 제외
        if now.weekday() >= 5:
            print("주말에는 거래하지 않습니다.")
            return False

        # 장 시간 체크 (09:00 ~ 15:30)
        market_open = now.replace(hour=9, minute=0, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)

        if now < market_open or now > market_close:
            print(f"장 운영 시간이 아닙니다. (현재: {now.strftime('%H:%M')})")
            return False

        return True

    def execute_sell_orders(self, sell_list: List[Dict]) -> List[Dict]:
        """
        매도 주문 실행

        Args:
            sell_list: 매도 대상 종목 리스트

        Returns:
            주문 결과 리스트
        """
        results = []

        for item in sell_list:
            stock_code = item["stock_code"]
            stock_name = item.get("stock_name", stock_code)
            quantity = item["quantity"]
            sell_reasons = item.get("sell_reasons", [])
            profit_rate = item.get("profit_rate", 0)

            print(f"\n매도: {stock_name} ({stock_code}) {quantity}주")
            print(f"  사유: {', '.join(sell_reasons)}")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "stock_code": stock_code, "dry_run": True}
            else:
                result = self.executor.place_sell_order(
                    stock_code=stock_code,
                    quantity=quantity
                )

            if result.get("success"):
                # 손익 계산 (수수료/세금 포함)
                sell_price = item.get("current_price", 0)
                avg_price = item.get("avg_price", sell_price)
                market = item.get("market", "KOSDAQ")

                # 수수료/세금 계산
                buy_amount = avg_price * quantity
                sell_amount = sell_price * quantity
                buy_commission = int(buy_amount * self.config.COMMISSION_RATE)
                sell_commission = int(sell_amount * self.config.COMMISSION_RATE)
                if market == "KOSPI":
                    sell_tax = int(sell_amount * self.config.TAX_RATE_KOSPI)
                else:
                    sell_tax = int(sell_amount * self.config.TAX_RATE_KOSDAQ)
                total_fees = buy_commission + sell_commission + sell_tax

                # 실현손익 = 매도금액 - 매수금액 - 수수료/세금
                realized_profit = sell_amount - buy_amount - total_fees
                realized_rate = (realized_profit / buy_amount * 100) if buy_amount > 0 else 0  # 퍼센트로 저장

                # 거래 기록
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="sell",
                    quantity=quantity,
                    price=sell_price,
                    order_no=result.get("order_no"),
                    trade_reason=", ".join(sell_reasons),
                    status="executed" if not self.dry_run else "dry_run",
                    profit_loss=realized_profit,
                    profit_rate=realized_rate,
                    user_id=self.user_id
                )

                # 보유 종목에서 제거
                if not self.dry_run:
                    # 모의투자 가상 잔고 업데이트 (매도)
                    if self.config.IS_VIRTUAL:
                        # 매도 후 현금 = 매도금액 - 매도수수료 - 세금
                        net_sell_amount = sell_amount - sell_commission - sell_tax
                        self.logger.update_virtual_balance_on_sell(net_sell_amount, buy_amount, realized_profit)

                    self.logger.remove_holding(stock_code)

                # 알림
                reason_str = sell_reasons[0] if sell_reasons else "조건 충족"
                if "손절" in reason_str:
                    self.notifier.notify_stop_loss(
                        stock_name, item.get("current_price", 0), profit_rate, stock_code
                    )
                else:
                    self.notifier.notify_sell(
                        stock_name, item.get("current_price", 0),
                        quantity, profit_rate, reason_str, stock_code
                    )

                self.stats["sell_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def execute_buy_orders(self, buy_list: List[Dict], investment_per_stock: int) -> List[Dict]:
        """
        매수 주문 실행 (시초가 갭 전략 적용)

        Args:
            buy_list: 매수 대상 종목 리스트
            investment_per_stock: 종목당 투자금액

        Returns:
            주문 결과 리스트
        """
        results = []

        for item in buy_list:
            stock_code = item["stock_code"]
            stock_name = item.get("stock_name", stock_code)

            # 전일 등락률 (상한가 여부 판단용)
            yesterday_change_pct = item.get("change_pct", 0)

            # 현재가 조회 (실시간)
            current_price = self.executor.get_current_price(stock_code)
            if not current_price or current_price <= 0:
                current_price = item.get("current_price", 0)

            if current_price <= 0:
                print(f"  {stock_name}: 가격 조회 실패")
                continue

            # === 급등주 제외 (15% 이상 상승 종목) ===
            # 스크리닝 결과의 change_pct 사용 (전일 대비 등락률)
            screening_change_pct = item.get("change_pct", 0)
            if screening_change_pct >= 15:
                print(f"  {stock_name}: 급등주 제외 ({screening_change_pct:+.1f}%)")
                continue

            # 실시간 가격으로도 재확인 (전일종가 기준)
            prev_close = item.get("current_price", 0)
            if prev_close > 0 and current_price > 0:
                realtime_change_pct = (current_price - prev_close) / prev_close * 100
                if realtime_change_pct >= 15:
                    print(f"  {stock_name}: 실시간 급등주 제외 ({realtime_change_pct:+.1f}%)")
                    continue

            # === 시초가 갭 전략 평가 ===
            prev_close = item.get("current_price", current_price)  # 전일 종가 (분석 시점 가격)
            gap_result = self.evaluate_gap_strategy(
                stock_code=stock_code,
                stock_name=stock_name,
                yesterday_change_pct=yesterday_change_pct,
                prev_close=prev_close
            )

            if gap_result['action'] == 'SKIP':
                print(f"  {stock_name}: 갭 전략 스킵 - {gap_result['reason']}")
                continue
            elif gap_result['action'] == 'WAIT':
                print(f"  {stock_name}: 갭 전략 대기 - {gap_result['reason']}")
                continue

            # 갭 전략 통과 시 로그
            print(f"  {stock_name}: 갭 전략 통과 - {gap_result['reason']}")

            # === 기존 매수밴드 체크 (갭 전략 비활성화 시 또는 추가 안전장치) ===
            if not self.config.GAP_STRATEGY_ENABLED:
                buy_band_high = item.get("buy_band_high", current_price)
                recommended_price = item.get("recommended_price", current_price)
                if current_price > buy_band_high:
                    print(f"  {stock_name}: 현재가 {current_price:,}원 > 매수밴드 {buy_band_high:,}원 - 대기")
                    continue

            quantity = investment_per_stock // current_price

            if quantity <= 0:
                print(f"  {stock_name}: 매수 가능 수량 없음")
                continue

            print(f"\n매수: {stock_name} ({stock_code})")
            print(f"  현재가: {current_price:,}원, 전일등락: {yesterday_change_pct:+.1f}%")
            print(f"  갭: {gap_result['gap_pct']:+.1f}%, 주문: 시장가")
            print(f"  수량: {quantity}주 = {current_price * quantity:,}원")
            print(f"  점수: {item.get('score')}, 신호: {len(item.get('signals', []))}개")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "stock_code": stock_code, "dry_run": True}
            else:
                result = self.executor.place_buy_order(
                    stock_code=stock_code,
                    quantity=quantity
                )

            if result.get("success"):
                # 거래 기록
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="buy",
                    quantity=quantity,
                    price=current_price,
                    order_no=result.get("order_no"),
                    trade_reason=f"점수 {item.get('score')}점",
                    status="executed" if not self.dry_run else "dry_run",
                    user_id=self.user_id
                )

                # 보유 종목 추가
                if not self.dry_run:
                    self.logger.add_holding(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        quantity=quantity,
                        avg_price=current_price,
                        buy_reason=f"점수 {item.get('score')}점",
                        market=item.get("market", "KOSDAQ")
                    )

                    # 모의투자 가상 잔고 업데이트 (매수 수수료 차감)
                    if self.config.IS_VIRTUAL:
                        buy_amount = current_price * quantity
                        buy_commission = int(buy_amount * self.config.COMMISSION_RATE)
                        self.logger.update_virtual_balance_on_buy(buy_amount + buy_commission)

                # 알림
                self.notifier.notify_buy(stock_name, current_price, quantity, stock_code)

                self.stats["buy_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def create_buy_suggestion(self, candidate: Dict) -> Optional[int]:
        """
        매수 제안 생성 및 텔레그램 알림

        Args:
            candidate: 매수 후보 종목 정보

        Returns:
            생성된 제안 ID 또는 None
        """
        stock_code = candidate.get("stock_code")
        stock_name = candidate.get("stock_name", stock_code)
        score = candidate.get("score", 0)
        signals = candidate.get("signals", [])

        # 이미 대기 중인 제안이 있으면 스킵
        if self.suggestion_manager.has_pending_for_stock(stock_code):
            print(f"  {stock_name}: 이미 대기 중인 제안 존재")
            return None

        # 미체결 매수 주문이 있는 종목은 스킵 (중복 주문 방지)
        pending_orders = getattr(self, '_pending_orders', []) or []
        total_assets = getattr(self, '_total_assets', 0)

        if pending_orders:
            for order in pending_orders:
                if order.get('stock_code') == stock_code and order.get('side') == 'buy':
                    pending_amount = int(order.get('order_qty', 0)) * int(order.get('order_price', 0))
                    pct = pending_amount / total_assets * 100 if total_assets > 0 else 0
                    print(f"  {stock_name}: 미체결 매수 주문 존재 ({pending_amount:,}원, {pct:.1f}%) - 스킵")
                    return None

        # 주가 데이터 가져와서 추천 매수가 계산
        try:
            df = self.analyst.get_ohlcv(stock_code, days=120)
            price_info = self.analyst.calculate_recommended_buy_price(
                df,
                target_profit_pct=self.config.TARGET_PROFIT_PCT,
                stop_loss_pct=self.config.SUGGESTED_STOP_LOSS_PCT,
                buy_band_pct=self.config.BUY_BAND_PCT
            )

            if not price_info:
                print(f"  {stock_name}: 추천 매수가 계산 실패")
                return None

            # 상승확률/신뢰도 계산
            prob_conf = self.analyst.calculate_probability_confidence(score, signals)

            # 매수 제안 생성
            suggestion_id = self.suggestion_manager.create_suggestion(
                stock_code=stock_code,
                stock_name=stock_name,
                score=score,
                probability=prob_conf.get('probability', 50),
                confidence=prob_conf.get('confidence', 50),
                current_price=price_info['current_price'],
                recommended_price=price_info['recommended_price'],
                target_price=price_info['target_price'],
                stop_loss_price=price_info['stop_loss_price'],
                buy_band_low=price_info['buy_band_low'],
                buy_band_high=price_info['buy_band_high'],
                signals=signals,
                expire_hours=self.config.SUGGESTION_EXPIRE_HOURS
            )

            # 텔레그램 알림
            self.notifier.notify_buy_suggestion(
                stock_name=stock_name,
                stock_code=stock_code,
                score=score,
                probability=prob_conf.get('probability', 50),
                confidence=prob_conf.get('confidence', 50),
                current_price=price_info['current_price'],
                recommended_price=price_info['recommended_price'],
                target_price=price_info['target_price'],
                stop_loss_price=price_info['stop_loss_price'],
                signals=signals,
                expire_hours=self.config.SUGGESTION_EXPIRE_HOURS
            )

            print(f"  {stock_name}: 매수 제안 생성 (ID: {suggestion_id})")
            print(f"    현재가: {price_info['current_price']:,}원")
            print(f"    추천가: {price_info['recommended_price']:,}원")
            print(f"    목표가: {price_info['target_price']:,}원")

            return suggestion_id

        except Exception as e:
            print(f"  {stock_name}: 매수 제안 생성 오류 - {e}")
            return None

    def execute_approved_suggestions(self, investment_per_stock: int) -> List[Dict]:
        """
        승인된 매수 제안 실행 (추천 매수가 이하일 때만)

        Args:
            investment_per_stock: 종목당 투자금액

        Returns:
            주문 결과 리스트
        """
        results = []
        approved = self.suggestion_manager.get_approved_suggestions()

        if not approved:
            return results

        print(f"\n승인된 제안 {len(approved)}개 확인 중...")

        for suggestion in approved:
            stock_code = suggestion['stock_code']
            stock_name = suggestion.get('stock_name', stock_code)
            recommended_price = suggestion.get('recommended_price', 0)
            buy_band_high = suggestion.get('buy_band_high', recommended_price)

            # 현재가 조회
            current_price = self.executor.get_current_price(stock_code)
            if not current_price:
                print(f"  {stock_name}: 현재가 조회 실패")
                continue

            # 매수 가격 및 방식 결정
            if current_price <= buy_band_high:
                # 현재가가 매수밴드 이하 → 시장가 매수
                order_price = 0
                order_type = "01"  # 시장가
                exec_price = current_price
                order_desc = "시장가"
            else:
                # 현재가가 매수밴드 초과 → 매수밴드 가격으로 지정가 주문
                # 호가 단위로 내림 (2201 → 2200)
                limit_price = round_to_tick(buy_band_high, round_down=True)
                order_price = limit_price
                order_type = "00"  # 지정가
                exec_price = limit_price
                order_desc = f"지정가 {limit_price:,}원"

            # 매수 수량 계산 (지정가 기준)
            quantity = investment_per_stock // exec_price
            if quantity <= 0:
                print(f"  {stock_name}: 매수 가능 수량 없음")
                continue

            print(f"\n[승인 제안 매수] {stock_name}")
            print(f"  추천가: {recommended_price:,}원 / 현재가: {current_price:,}원")
            print(f"  주문: {order_desc} x {quantity}주")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "stock_code": stock_code, "dry_run": True}
            else:
                result = self.executor.place_buy_order(
                    stock_code=stock_code,
                    quantity=quantity,
                    price=order_price,
                    order_type=order_type
                )

            if result.get("success"):
                # 지정가/시장가 구분
                is_limit_order = (order_type == "00")

                # 거래 기록 (지정가는 pending, 시장가는 executed)
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="buy",
                    quantity=quantity,
                    price=exec_price,
                    order_no=result.get("order_no"),
                    trade_reason=f"제안승인 (점수 {suggestion.get('score')}점) - {order_desc}",
                    status="pending" if is_limit_order else ("executed" if not self.dry_run else "dry_run"),
                    user_id=self.user_id
                )

                # 시장가 주문은 바로 체결 → 보유 종목 추가
                # 지정가 주문은 미체결 → 보유 종목 추가 안 함 (체결 시 별도 처리)
                if not self.dry_run and not is_limit_order:
                    self.logger.add_holding(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        quantity=quantity,
                        avg_price=exec_price,
                        buy_reason=f"제안승인 (점수 {suggestion.get('score')}점)",
                        market=suggestion.get("market", "KOSDAQ")
                    )

                    # 모의투자 가상 잔고 업데이트 (매수 수수료 차감)
                    if self.config.IS_VIRTUAL:
                        buy_amount = exec_price * quantity
                        buy_commission = int(buy_amount * self.config.COMMISSION_RATE)
                        self.logger.update_virtual_balance_on_buy(buy_amount + buy_commission)

                # 제안 실행 완료 처리 (주문 접수됨)
                self.suggestion_manager.mark_executed(suggestion['id'])

                # 알림
                if is_limit_order:
                    self.notifier.send_push(
                        title=f"📝 지정가 매수 주문: {stock_name}",
                        body=f"{exec_price:,}원 x {quantity}주 (미체결)",
                        url="/auto-trade/pending-orders"
                    )
                else:
                    self.notifier.notify_suggestion_executed(stock_name, exec_price, quantity)

                self.stats["buy_orders"].append(result)
                self.risk_manager.increment_trade_count()

            results.append(result)

        return results

    def run_semi_auto(self) -> Dict:
        """
        반자동 모드 실행 (매수 제안 생성)

        Returns:
            실행 결과 요약
        """
        print("\n" + "=" * 60)
        print("  반자동 매매 시스템 (Semi-Auto Mode)")
        print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  모드: {'모의투자' if self.config.IS_VIRTUAL else '실전투자'}")
        print("=" * 60)

        # 긴급 정지 체크
        if self.config.EMERGENCY_STOP:
            print("\n긴급 정지 상태입니다.")
            return {"status": "emergency_stop"}

        # 장 시간 체크 (dry_run이 아닐 때만)
        if not self.dry_run and not self.check_market_hours():
            return {"status": "market_closed"}

        # 1. 만료된 제안 정리
        print("\n[1] 만료 제안 정리 중...")
        expired_count = self.suggestion_manager.expire_old_suggestions()
        if expired_count > 0:
            print(f"  {expired_count}개 제안 만료 처리")

        # 2. 분석 결과 로드
        print("\n[2] 분석 결과 로드 중...")
        analysis_stocks = self.load_analysis_results()
        if not analysis_stocks:
            self.notifier.notify_error("분석 결과 파일을 찾을 수 없습니다.")
            return {"status": "no_data"}

        # 3. 계좌 잔고 조회
        print("\n[3] 계좌 잔고 조회 중...")
        balance = self.executor.get_account_balance()
        if not balance:
            self.notifier.notify_error("계좌 잔고 조회 실패")
            return {"status": "balance_error"}

        all_holdings = balance.get("holdings", [])
        # 수량 > 0인 종목만 필터링 (매도 완료된 종목 제외)
        holdings = [h for h in all_holdings if h.get("quantity", 0) > 0]
        summary = balance.get("summary", {})
        # 예수금: d2_cash_balance (실제 자산 기준)
        d2_cash = summary.get("d2_cash_balance", 0) or summary.get("cash_balance", 0)
        # 주문가능금액: max_buy_amt (미체결 제외)
        max_buy_amt = summary.get("max_buy_amt", 0) or d2_cash
        # 총자산: 평가금액 + d2 예수금 (고정)
        total_eval = summary.get("total_eval_amount", 0)
        total_assets = total_eval + d2_cash

        print(f"  예수금(D+2): {d2_cash:,}원")
        print(f"  주문가능금액: {max_buy_amt:,}원")
        print(f"  보유 종목: {len(holdings)}개 (수량>0 필터링)")

        # 미체결 주문 조회 (제안 생성 시 중복 체크용)
        self._pending_orders = self.executor.get_pending_orders()
        self._total_assets = total_assets
        self._investment_per_stock = self.risk_manager.calculate_investment_amount()
        if self._pending_orders:
            print(f"  미체결 주문: {len(self._pending_orders)}건")

        # 4. 보유 종목 매도 체크 - semi-auto에서는 매도 실행 안 함 (알림만)
        print("\n[4] 보유 종목 평가 중... (래치 전략 적용)")
        if holdings:
            current_prices = {}
            current_signals = {}
            current_scores = {}
            buy_dates = {}
            sma20_values = {}  # 래치 전략용 20일선

            for h in holdings:
                stock_code = h["stock_code"]
                current_prices[stock_code] = h.get("current_price", 0)
                current_signals[stock_code] = self.get_current_signals(stock_code, analysis_stocks)
                current_scores[stock_code] = self.get_current_score(stock_code, analysis_stocks)
                sma20_values[stock_code] = self.get_sma20(stock_code)  # 20일선 조회
                buy_date = self.logger.get_buy_date(stock_code)
                if buy_date:
                    buy_dates[stock_code] = buy_date

            sell_list = self.risk_manager.evaluate_holdings(
                holdings=holdings,
                current_prices=current_prices,
                current_signals=current_signals,
                buy_dates=buy_dates,
                current_scores=current_scores,
                sma20_values=sma20_values  # 래치 전략용
            )

            if sell_list:
                # semi-auto 모드에서는 매도 실행하지 않고 알림만 전송
                print(f"  ⚠️ 매도 신호 감지: {len(sell_list)}개 (semi-auto 모드에서는 자동 매도 안 함)")
                for item in sell_list:
                    stock_code = item.get('stock_code')
                    stock_name = item.get('stock_name', stock_code)
                    reasons = ', '.join(item.get('sell_reasons', []))
                    profit_rate = item.get('profit_rate', 0) * 100
                    print(f"    - {stock_name}: {reasons} ({profit_rate:+.1f}%)")
                    # 푸시 알림으로 매도 신호 전달 (사용자가 직접 판단)
                    self.notifier.send_push(
                        title=f"⚠️ 매도 신호: {stock_name}",
                        body=f"{reasons} ({profit_rate:+.1f}%)",
                        url=f"/auto-trade/manual"
                    )
                    # 알림 기록 저장
                    self._save_alert_history(stock_code, stock_name, "매도 신호", f"{reasons} ({profit_rate:+.1f}%)")
            else:
                print("  매도 대상 없음")

        # 5. 승인된 제안은 API에서 즉시 실행됨 (세미오토 원칙)
        # 주의: 세미오토 모드에서는 사용자가 앱에서 승인할 때만 주문이 실행됨
        # execute_approved_suggestions()는 호출하지 않음 (자동 매매 방지)
        print("\n[5] 세미오토 모드: 사용자 승인 시 API에서 즉시 주문 실행됨")
        print("  (스크립트에서 자동 주문 실행 안 함)")

        # 6. 새 매수 후보 → 제안 생성
        print("\n[6] 새 매수 제안 생성 중...")
        candidates = self.filter_buy_candidates(analysis_stocks)
        print(f"  매수 조건 충족 종목: {len(candidates)}개")

        # 현재 보유 종목과 리스크 관리 반영
        current_holdings = self.executor.get_holdings()

        # 당일 블랙리스트 조회 (왕복매매 방지)
        today_blacklist = self.logger.get_today_traded_stocks(self.user_id)
        if today_blacklist:
            print(f"  당일 거래 종목: {len(today_blacklist)}개 (재매수 제외)")

        filtered_candidates = self.risk_manager.filter_buy_candidates(
            candidates, current_holdings, today_blacklist
        )

        # 최대 대기 제안 수 체크
        pending = self.suggestion_manager.get_pending_suggestions()
        remaining_slots = self.config.MAX_PENDING_SUGGESTIONS - len(pending)

        new_suggestions = 0
        for candidate in filtered_candidates[:remaining_slots]:
            if self.create_buy_suggestion(candidate):
                new_suggestions += 1

        print(f"  새 매수 제안: {new_suggestions}개 생성")

        # 7. 일일 성과 저장
        print("\n[7] 성과 저장 중...")
        final_balance = self.executor.get_account_balance()
        if final_balance and self.user_id:
            final_holdings = final_balance.get("holdings", [])
            total_invested = sum(h.get("avg_price", 0) * h.get("quantity", 0) for h in final_holdings)
            total_profit = final_balance.get("summary", {}).get("total_profit_loss", 0)
            d2_cash = final_balance.get("summary", {}).get("d2_deposit", 0)
            holdings_value = final_balance.get("summary", {}).get("total_eval_amount", 0) - d2_cash

            self.logger.save_daily_performance(
                user_id=self.user_id,
                total_assets=final_balance.get("summary", {}).get("total_eval_amount", 0),
                d2_cash=d2_cash,
                holdings_value=holdings_value,
                total_invested=total_invested,
                total_profit=total_profit,
                holdings_count=len(final_holdings)
            )

        # 8. 완료
        print("\n[8] 완료")
        stats = self.suggestion_manager.get_statistics()
        buy_count = len(self.stats["buy_orders"])
        sell_count = len(self.stats["sell_orders"])

        result = {
            "status": "completed",
            "mode": "semi-auto",
            "buy_count": buy_count,
            "sell_count": sell_count,
            "new_suggestions": new_suggestions,
            "pending_suggestions": stats.get('pending', 0),
            "approved_suggestions": stats.get('approved', 0),
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n매수: {buy_count}건, 매도: {sell_count}건")
        print(f"대기 제안: {stats.get('pending', 0)}개, 승인 대기: {stats.get('approved', 0)}개")
        print("=" * 60)

        return result

    def run_greenlight(self) -> Dict:
        """
        Green Light 모드 실행 (AI 완전 자율 매매)

        특징:
        - LLM이 모든 매매 결정
        - 종목당 투자금액 제한 없음
        - 손절/익절 규칙 없음
        - TOP 100 유니버스 내에서만 거래
        - 모의투자 계좌 전용

        Returns:
            실행 결과 요약
        """
        from trading.llm_trader import LLMTrader

        print("\n" + "=" * 60)
        print("  GREEN LIGHT MODE - AI 자율 매매")
        print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 1. 모의투자 확인 (필수)
        is_mock = self.user_config.get('is_mock', True)
        if not is_mock:
            print("\n[ERROR] Green Light 모드는 모의투자에서만 사용 가능합니다.")
            return {"status": "error", "message": "모의투자에서만 사용 가능합니다."}

        # 2. LLM 설정 로드
        print("\n[1] LLM 설정 로드 중...")
        llm_settings = self.logger.get_llm_settings(self.user_id)
        if not llm_settings or not llm_settings.get('llm_api_key'):
            print("  LLM API 키가 설정되지 않았습니다.")
            return {"status": "error", "message": "LLM API 키를 설정해주세요."}

        provider = llm_settings.get('llm_provider', 'claude')
        api_key = llm_settings.get('llm_api_key')
        model = llm_settings.get('llm_model')
        print(f"  Provider: {provider}, Model: {model or 'default'}")

        # 3. LLM 트레이더 초기화
        try:
            llm_trader = LLMTrader(
                provider=provider,
                api_key=api_key,
                model=model,
                user_id=self.user_id
            )
        except Exception as e:
            print(f"  LLM 초기화 실패: {e}")
            return {"status": "error", "message": f"LLM 초기화 실패: {e}"}

        # 4. 계좌 잔고 조회
        print("\n[2] 계좌 잔고 조회 중...")
        balance = self.executor.get_account_balance()
        if not balance:
            print("  계좌 잔고 조회 실패")
            return {"status": "error", "message": "계좌 잔고 조회 실패"}

        holdings = [h for h in balance.get('holdings', []) if h.get('quantity', 0) > 0]
        summary = balance.get('summary', {})
        cash = summary.get('max_buy_amt', 0) or summary.get('d2_cash_balance', 0) or summary.get('cash_balance', 0)
        total_eval = summary.get('total_eval_amount', 0)
        total_assets = total_eval + cash

        print(f"  주문가능금액: {cash:,}원")
        print(f"  총 자산: {total_assets:,}원")
        print(f"  보유 종목: {len(holdings)}개")

        # 5. TOP 100 분석 결과 로드
        print("\n[3] TOP 100 분석 결과 로드 중...")
        analysis_stocks = self.load_analysis_results()
        if not analysis_stocks:
            print("  분석 결과 없음")
            return {"status": "error", "message": "분석 결과를 찾을 수 없습니다."}

        top100 = [
            {
                'code': s.get('code'),
                'name': s.get('name'),
                'score': s.get('score', 0),
                'price': s.get('price') or s.get('close', 0),
                'close': s.get('close', 0),
                'change_pct': s.get('change_pct', 0),  # 등락률 (상한가/하한가 판단용)
                'volume': s.get('volume', 0),
                'signals': s.get('signals', [])
            }
            for s in analysis_stocks[:100]
        ]
        top100_codes = [s['code'] for s in top100]
        print(f"  TOP 100 종목 로드 완료")

        # 6. 시장 정보 수집
        print("\n[4] 시장 정보 수집 중...")
        market_info = self._get_market_info()
        print(f"  코스피: {market_info.get('kospi', {}).get('index', 0):,.0f} ({market_info.get('kospi', {}).get('change_pct', 0):+.2f}%)")
        print(f"  코스닥: {market_info.get('kosdaq', {}).get('index', 0):,.0f} ({market_info.get('kosdaq', {}).get('change_pct', 0):+.2f}%)")

        # 7. 과거 피드백 수집
        print("\n[5] 과거 매매 피드백 수집 중...")
        past_feedback = self.logger.get_greenlight_feedback(self.user_id, limit=20)
        print(f"  과거 피드백: {len(past_feedback)}건")

        # 8. 컨텍스트 빌드
        print("\n[6] AI 컨텍스트 구성 중...")

        # 보유종목에 당일 등락률 추가 (분석 결과에서 조회)
        stock_change_map = {s.get('code'): s.get('change_pct', 0) for s in analysis_stocks}
        enriched_holdings = []
        for h in holdings:
            h_copy = dict(h)
            h_copy['change_pct'] = stock_change_map.get(h.get('stock_code'), 0)
            enriched_holdings.append(h_copy)

        portfolio = {
            'cash': cash,
            'total_assets': total_assets,
            'holdings': enriched_holdings
        }
        context = llm_trader.build_context(
            portfolio=portfolio,
            top100=top100,
            market_info=market_info,
            past_feedback=past_feedback
        )

        # 9. AI 결정 요청
        print("\n[7] AI에게 트레이딩 결정 요청 중...")
        result = llm_trader.get_trading_decisions(context)

        if result.get('error'):
            print(f"  AI 호출 실패: {result.get('error')}")
            return {"status": "error", "message": result.get('error')}

        print(f"  시장 분석: {result.get('market_analysis', '')[:100]}")
        print(f"  결정 수: {len(result.get('decisions', []))}개")

        # 10. 결정 유효성 검증
        decisions = result.get('decisions', [])
        valid_decisions = llm_trader.validate_decisions(decisions, portfolio, top100_codes)
        print(f"  유효 결정: {len(valid_decisions)}개")

        # 11. 결정 실행
        print("\n[8] 결정 실행 중...")
        executed_orders = []

        for d in valid_decisions:
            action = d.get('action')
            stock_code = d.get('stock_code')
            stock_name = d.get('stock_name', '')
            quantity = d.get('quantity', 0)
            reason = d.get('reason', '')
            confidence = d.get('confidence', 0.5)

            print(f"\n  {action} {stock_name}({stock_code}) x {quantity}주")
            print(f"  이유: {reason}")
            print(f"  신뢰도: {confidence:.1%}")

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 건너뜀")
                executed_orders.append({
                    **d,
                    'status': 'dry_run',
                    'order_no': None
                })
                continue

            try:
                if action == 'BUY':
                    order_result = self.executor.place_buy_order(
                        stock_code=stock_code,
                        quantity=quantity,
                        price=0,  # 시장가
                        order_type="market"
                    )
                elif action == 'SELL':
                    order_result = self.executor.place_sell_order(
                        stock_code=stock_code,
                        quantity=quantity,
                        price=0,  # 시장가
                        order_type="market"
                    )
                else:
                    continue

                if order_result and order_result.get('order_no'):
                    print(f"  주문 성공: {order_result.get('order_no')}")
                    executed_orders.append({
                        **d,
                        'status': 'executed',
                        'order_no': order_result.get('order_no')
                    })

                    # 거래 로그 기록
                    side = 'buy' if action == 'BUY' else 'sell'
                    self.logger.log_trade(
                        user_id=self.user_id,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        side=side,
                        quantity=quantity,
                        price=0,
                        order_no=order_result.get('order_no'),
                        trade_reason=f"[GreenLight] {reason} (신뢰도:{confidence:.0%})",
                        status='ordered'
                    )
                else:
                    print(f"  주문 실패: {order_result}")
                    executed_orders.append({
                        **d,
                        'status': 'failed',
                        'error': str(order_result)
                    })

            except Exception as e:
                print(f"  주문 오류: {e}")
                executed_orders.append({
                    **d,
                    'status': 'error',
                    'error': str(e)
                })

        # 12. 결정 이력 저장 (전체 프롬프트 포함)
        print("\n[9] 결정 이력 저장 중...")
        decision_id = self.logger.log_greenlight_decision(
            user_id=self.user_id,
            llm_provider=provider,
            prompt_summary=result.get('full_prompt', result.get('prompt_summary', '')),  # 전체 프롬프트 저장
            raw_response=result.get('raw_response', ''),
            decisions=valid_decisions,
            executed_orders=executed_orders,
            portfolio_snapshot=portfolio,
            market_context=market_info
        )
        print(f"  결정 ID: {decision_id}")

        # 결과 요약
        buy_count = sum(1 for d in executed_orders if d.get('action') == 'BUY' and d.get('status') == 'executed')
        sell_count = sum(1 for d in executed_orders if d.get('action') == 'SELL' and d.get('status') == 'executed')

        print("\n" + "=" * 60)
        print(f"  GREEN LIGHT 실행 완료")
        print(f"  매수: {buy_count}건, 매도: {sell_count}건")
        print("=" * 60)

        return {
            "status": "completed",
            "mode": "greenlight",
            "decision_id": decision_id,
            "market_analysis": result.get('market_analysis', ''),
            "risk_assessment": result.get('risk_assessment', ''),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "decisions": valid_decisions,
            "executed_orders": executed_orders,
            "timestamp": datetime.now().isoformat()
        }

    def _get_market_info(self) -> Dict:
        """시장 정보 (코스피/코스닥 지수) 조회"""
        try:
            import FinanceDataReader as fdr
            from datetime import timedelta

            today = datetime.now()
            start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

            # 코스피
            kospi_df = fdr.DataReader('KS11', start_date, end_date)
            if kospi_df is not None and len(kospi_df) >= 1:
                kospi_close = kospi_df.iloc[-1]['Close']
                if len(kospi_df) >= 2:
                    kospi_prev = kospi_df.iloc[-2]['Close']
                    kospi_change = (kospi_close - kospi_prev) / kospi_prev * 100
                else:
                    kospi_change = 0
            else:
                kospi_close, kospi_change = 0, 0

            # 코스닥
            kosdaq_df = fdr.DataReader('KQ11', start_date, end_date)
            if kosdaq_df is not None and len(kosdaq_df) >= 1:
                kosdaq_close = kosdaq_df.iloc[-1]['Close']
                if len(kosdaq_df) >= 2:
                    kosdaq_prev = kosdaq_df.iloc[-2]['Close']
                    kosdaq_change = (kosdaq_close - kosdaq_prev) / kosdaq_prev * 100
                else:
                    kosdaq_change = 0
            else:
                kosdaq_close, kosdaq_change = 0, 0

            return {
                'kospi': {'index': kospi_close, 'change_pct': kospi_change},
                'kosdaq': {'index': kosdaq_close, 'change_pct': kosdaq_change}
            }
        except Exception as e:
            print(f"시장 정보 조회 실패: {e}")
            return {
                'kospi': {'index': 0, 'change_pct': 0},
                'kosdaq': {'index': 0, 'change_pct': 0}
            }

    def run(self) -> Dict:
        """
        자동매매 실행 (모드에 따라 auto/semi-auto 분기)

        Returns:
            실행 결과 요약
        """
        # 사용자별 설정 확인 (DB 설정 > config 설정)
        trade_mode = getattr(self.config, 'TRADE_MODE', 'auto')
        trading_enabled = True  # 기본값

        if self.user_id:
            user_settings = self.logger.get_auto_trade_settings(self.user_id)
            if user_settings:
                # 중요: trading_enabled 체크 (비활성화면 실행 안 함)
                trading_enabled = bool(user_settings.get('trading_enabled', 0))
                if not trading_enabled:
                    print(f"[AutoTrader] user_id={self.user_id}: trading_enabled=0 → 실행 안 함")
                    return {"status": "disabled", "message": "자동매매가 비활성화되어 있습니다."}

                db_mode = user_settings.get('trade_mode', 'auto')
                # DB 값 변환: 'semi' -> 'semi-auto'
                if db_mode == 'semi':
                    trade_mode = 'semi-auto'
                elif db_mode == 'auto':
                    trade_mode = 'auto'
                elif db_mode == 'manual':
                    trade_mode = 'manual'
                elif db_mode == 'greenlight':
                    trade_mode = 'greenlight'

        # manual 모드면 실행 안함
        if trade_mode == 'manual':
            return {"status": "manual_mode", "message": "수동 모드입니다."}

        if trade_mode == 'semi-auto':
            return self.run_semi_auto()

        if trade_mode == 'greenlight':
            return self.run_greenlight()

        # 기존 auto 모드
        print("\n" + "=" * 60)
        print("  자동매매 시스템 시작 (Auto Mode)")
        print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  모드: {'모의투자' if self.config.IS_VIRTUAL else '실전투자'}")
        print(f"  DRY-RUN: {self.dry_run}")
        print("=" * 60)

        # 긴급 정지 체크
        if self.config.EMERGENCY_STOP:
            print("\n긴급 정지 상태입니다.")
            return {"status": "emergency_stop"}

        # 장 시간 체크 (dry_run이 아닐 때만)
        if not self.dry_run and not self.check_market_hours():
            return {"status": "market_closed"}

        # 거래 가능 여부 체크
        can_trade, reason = self.risk_manager.can_trade()
        if not can_trade:
            print(f"\n거래 불가: {reason}")
            return {"status": "trade_limit", "reason": reason}

        # 1. 분석 결과 로드
        print("\n[1] 분석 결과 로드 중...")
        analysis_stocks = self.load_analysis_results()
        if not analysis_stocks:
            self.notifier.notify_error("분석 결과 파일을 찾을 수 없습니다.")
            return {"status": "no_data"}

        # 2. 계좌 잔고 조회
        print("\n[2] 계좌 잔고 조회 중...")
        balance = self.executor.get_account_balance()
        if not balance:
            self.notifier.notify_error("계좌 잔고 조회 실패")
            return {"status": "balance_error"}

        all_holdings = balance.get("holdings", [])
        # 수량 > 0인 종목만 필터링 (매도 완료된 종목 제외)
        holdings = [h for h in all_holdings if h.get("quantity", 0) > 0]
        summary = balance.get("summary", {})
        # 예수금: d2_cash_balance (실제 자산 기준)
        d2_cash = summary.get("d2_cash_balance", 0) or summary.get("cash_balance", 0)
        # 주문가능금액: max_buy_amt (미체결 제외)
        max_buy_amt = summary.get("max_buy_amt", 0) or d2_cash
        # 총자산: 평가금액 + d2 예수금 (고정)
        total_eval = summary.get("total_eval_amount", 0)
        total_assets = total_eval + d2_cash

        print(f"  예수금(D+2): {d2_cash:,}원")
        print(f"  주문가능금액: {max_buy_amt:,}원")
        print(f"  보유 종목: {len(holdings)}개 (수량>0 필터링)")
        print(f"  총 자산: {total_assets:,}원")

        # 3. 보유 종목 매도 체크 (래치 전략 적용)
        print("\n[3] 보유 종목 평가 중... (래치 전략 적용)")
        if holdings:
            # 현재가, 신호, 점수, 20일선 조회
            current_prices = {}
            current_signals = {}
            current_scores = {}
            buy_dates = {}
            sma20_values = {}  # 래치 전략용 20일선

            for h in holdings:
                stock_code = h["stock_code"]
                current_prices[stock_code] = h.get("current_price", 0)
                current_signals[stock_code] = self.get_current_signals(stock_code, analysis_stocks)
                current_scores[stock_code] = self.get_current_score(stock_code, analysis_stocks)
                sma20_values[stock_code] = self.get_sma20(stock_code)  # 20일선 조회

                # DB에서 매수일 조회
                buy_date = self.logger.get_buy_date(stock_code)
                if buy_date:
                    buy_dates[stock_code] = buy_date

            # 매도 대상 선정 (래치 전략: 40점 미만 또는 20일선 이탈)
            sell_list = self.risk_manager.evaluate_holdings(
                holdings=holdings,
                current_prices=current_prices,
                current_signals=current_signals,
                buy_dates=buy_dates,
                current_scores=current_scores,
                sma20_values=sma20_values  # 래치 전략용
            )

            if sell_list:
                print(f"  매도 대상: {len(sell_list)}개")
                for item in sell_list:
                    print(f"    - {item['stock_name']}: {', '.join(item['sell_reasons'])}")

                # 매도 실행
                self.execute_sell_orders(sell_list)
            else:
                print("  매도 대상 없음")

        # 4. 매수 후보 필터링
        print("\n[4] 매수 후보 필터링 중...")
        candidates = self.filter_buy_candidates(analysis_stocks)
        print(f"  매수 조건 충족 종목: {len(candidates)}개")

        # 현재 보유 종목과 리스크 관리 반영
        current_holdings = self.executor.get_holdings()

        # 당일 블랙리스트 조회 (왕복매매 방지)
        today_blacklist = self.logger.get_today_traded_stocks(self.user_id)
        if today_blacklist:
            print(f"  당일 거래 종목: {len(today_blacklist)}개 (재매수 제외)")

        filtered_candidates = self.risk_manager.filter_buy_candidates(
            candidates, current_holdings, today_blacklist
        )
        print(f"  최종 매수 후보: {len(filtered_candidates)}개")

        # 5. 매수 실행
        if filtered_candidates:
            base_investment = self.risk_manager.calculate_investment_amount()

            # 나스닥 연동 투자금액 조정
            adjusted_investment, nasdaq_multiplier, nasdaq_change = get_adjusted_investment_amount(base_investment)
            investment_per_stock = adjusted_investment

            # 실제 주문금액은 min(종목당 투자금, 주문가능금액)
            actual_investment = min(investment_per_stock, max_buy_amt)
            print(f"\n[5] 매수 주문 실행 중...")
            if nasdaq_multiplier < 1.0:
                print(f"  [NASDAQ 조정] 기본: {base_investment:,}원 × {nasdaq_multiplier} = {investment_per_stock:,}원")
            print(f"  종목당 투자금: {investment_per_stock:,}원, 주문가능: {max_buy_amt:,}원 → 실제: {actual_investment:,}원")

            self.execute_buy_orders(filtered_candidates, actual_investment)
        else:
            print("\n[5] 매수할 종목이 없습니다.")

        # 6. 일일 성과 저장
        print("\n[6] 성과 저장 중...")
        final_balance = self.executor.get_account_balance()
        if final_balance and self.user_id:
            final_holdings = final_balance.get("holdings", [])
            total_invested = sum(h.get("avg_price", 0) * h.get("quantity", 0) for h in final_holdings)
            total_eval = sum(h.get("eval_amount", 0) for h in final_holdings)
            total_profit = final_balance.get("summary", {}).get("total_profit_loss", 0)
            d2_cash = final_balance.get("summary", {}).get("d2_deposit", 0)
            holdings_value = final_balance.get("summary", {}).get("total_eval_amount", 0) - d2_cash

            self.logger.save_daily_performance(
                user_id=self.user_id,
                total_assets=final_balance.get("summary", {}).get("total_eval_amount", 0),
                d2_cash=d2_cash,
                holdings_value=holdings_value,
                total_invested=total_invested,
                total_profit=total_profit,
                holdings_count=len(final_holdings)
            )

        # 7. 요약 알림
        print("\n[7] 완료")
        buy_count = len(self.stats["buy_orders"])
        sell_count = len(self.stats["sell_orders"])

        self.notifier.notify_summary(buy_count, sell_count, self.stats["total_profit"])

        result = {
            "status": "completed",
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_orders": self.stats["buy_orders"],
            "sell_orders": self.stats["sell_orders"],
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n매수: {buy_count}건, 매도: {sell_count}건")
        print("=" * 60)

        return result

    def print_report(self, days: int = 30):
        """성과 리포트 출력"""
        report = self.logger.export_report(days=days)
        print(report)

    def run_intraday(self, min_score: int = 75, screening_result: tuple = None, trade_mode: str = 'auto', score_version: str = 'v5', strategy: str = 'simple', buy_conditions: str = '', sell_conditions: str = '') -> Dict:
        """
        장중 10분 스크리닝 모드

        cron으로 10분마다 실행하여 신규 매수 후보를 찾고 자동 매수합니다.
        - 전종목 실시간 스크리닝 (strict 모드)
        - min_score점 이상 종목 자동 매수
        - 당일 블랙리스트 적용 (왕복매매 방지)

        Args:
            min_score: 최소 매수 점수
            screening_result: (top_stocks, stats) 튜플. 전달 시 스크리닝 건너뜀
            trade_mode: auto 또는 semi
            score_version: 스코어 버전 (v1, v2, v5)
            strategy: 전략 (simple, v1_composite, custom)
            buy_conditions: 매수 조건 문자열 (예: "V1>=60 AND V5>=50 AND V4>40")
            sell_conditions: 매도 조건 문자열 (예: "V4<=30 OR V1<=40")

        cron 예시: */10 9-14 * * 1-5 /path/to/python auto_trader.py --intraday
        """
        self.score_version = score_version  # 인스턴스 변수로 저장
        self.strategy = strategy  # 전략 저장
        self.buy_conditions = parse_condition(buy_conditions) if buy_conditions else []
        self.sell_conditions = parse_condition(sell_conditions) if sell_conditions else []
        print("\n" + "=" * 60)
        print(f"  장중 스크리닝 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 장 시간 체크 (09:00 ~ 15:20)
        now = datetime.now()
        market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=20, second=0, microsecond=0)

        if now < market_open or now > market_close:
            print(f"  장 운영 시간이 아닙니다. (09:00 ~ 15:20)")
            return {"status": "skipped", "reason": "outside_market_hours"}

        # 사용자 설정 확인
        if not self._check_trading_enabled():
            return {"status": "skipped", "reason": "trading_disabled"}

        # 1. 계좌 잔고 조회
        print("\n[1] 계좌 잔고 조회 중...")
        balance = self.executor.get_account_balance()
        if not balance:
            print("  계좌 잔고 조회 실패")
            return {"status": "error", "reason": "balance_fetch_failed"}

        all_holdings = balance.get("holdings", [])
        holdings = [h for h in all_holdings if h.get("quantity", 0) > 0]
        summary = balance.get("summary", {})
        # 예수금: d2_cash_balance (실제 자산 기준)
        d2_cash = summary.get("d2_cash_balance", 0) or summary.get("cash_balance", 0)
        # 주문가능금액: max_buy_amt (미체결 제외)
        max_buy_amt = summary.get("max_buy_amt", 0) or d2_cash
        # 총자산: 평가금액 + d2 예수금
        total_eval = summary.get("total_eval_amount", 0)
        total_assets = total_eval + d2_cash

        print(f"  예수금(D+2): {d2_cash:,}원")
        print(f"  주문가능금액: {max_buy_amt:,}원")
        print(f"  보유 종목: {len(holdings)}개")

        # 2. 보유 종목 매도 체크 (손절 + 점수 기반, 모두 사용자 설정)
        sell_count = 0
        if holdings:
            # 사용자 설정에서 sell_score, score_version, stop_loss_rate, min_buy_score 가져오기
            user_settings = self.logger.get_auto_trade_settings(self.user_id) or {}
            sell_score = user_settings.get('sell_score', 40)
            score_version = user_settings.get('score_version', 'v2')
            stop_loss_rate = abs(user_settings.get('stop_loss_rate', 7.0))  # 절대값 사용
            min_buy_score = user_settings.get('min_buy_score', 70)

            # 15:00 장마감 정리 매도 체크
            is_closing_time = now.hour == 15 and now.minute >= 0

            if is_closing_time:
                if self.buy_conditions:
                    cond_str = ' '.join([f"{c['score'].upper()}{c['op']}{c['value']}" + (f" {c['connector']}" if i < len(self.buy_conditions)-1 else "") for i, c in enumerate(self.buy_conditions)])
                    print(f"\n[2] 장마감 정리 매도 체크 중... (매수조건 미충족시 매도: {cond_str})")
                else:
                    hold_score = min_buy_score + 5
                    print(f"\n[2] 장마감 정리 매도 체크 중... (점수 <= {hold_score}점 또는 손절 -{stop_loss_rate}%)")
            elif self.sell_conditions:
                # 커스텀 매도 조건 사용
                cond_str = ' '.join([f"{c['score'].upper()}{c['op']}{c['value']}" + (f" {c['connector']}" if i < len(self.sell_conditions)-1 else "") for i, c in enumerate(self.sell_conditions)])
                print(f"\n[2] 보유 종목 매도 체크 중... (손절 -{stop_loss_rate}% 또는 {cond_str})")
            else:
                print(f"\n[2] 보유 종목 매도 체크 중... (손절 -{stop_loss_rate}% 또는 {score_version.upper()} <= {sell_score}점)")

            # CSV에서 점수 로드 (전체 스코어)
            scores_map = {}  # {code: {'v1': x, 'v2': y, 'v4': z, 'v5': w}}
            try:
                import glob
                import pandas as pd
                score_files = sorted(glob.glob(str(INTRADAY_SCORES_DIR / "*.csv")))
                if score_files:
                    latest_csv = score_files[-1]
                    df = pd.read_csv(latest_csv)
                    df['code'] = df['code'].astype(str).str.zfill(6)
                    for _, row in df.iterrows():
                        scores_map[row['code']] = {
                            'v1': int(row.get('v1', 0)),
                            'v2': int(row.get('v2', 0)),
                            'v4': int(row.get('v4', 0)),
                            'v5': int(row.get('v5', 0)),
                        }
            except Exception as e:
                print(f"  점수 로드 실패: {e}")

            sell_list = []
            for h in holdings:
                stock_code = h["stock_code"]
                stock_name = h.get("stock_name", stock_code)
                avg_price = h.get("avg_price", 0)
                current_price = h.get("current_price", 0)
                quantity = h.get("quantity", 0)

                if avg_price <= 0 or current_price <= 0:
                    continue

                profit_rate = (current_price - avg_price) / avg_price * 100
                stock_scores = scores_map.get(stock_code, {'v1': 50, 'v2': 50, 'v4': 50, 'v5': 50})
                current_score = stock_scores.get(score_version, 50)
                sell_reasons = []

                # 손절 체크 (사용자 설정 stop_loss_rate 사용)
                if profit_rate <= -stop_loss_rate:
                    sell_reasons.append(f"손절 ({profit_rate:.1f}% <= -{stop_loss_rate}%)")

                # 15:00 장마감 정리: 매수조건 미충족시 매도
                if is_closing_time:
                    if self.buy_conditions:
                        # 커스텀 매수조건 미충족시 매도
                        if not evaluate_conditions(self.buy_conditions, stock_scores):
                            cond_detail = f"V1={stock_scores['v1']}, V4={stock_scores['v4']}, V5={stock_scores['v5']}"
                            sell_reasons.append(f"장마감정리 매수조건 미충족 ({cond_detail})")
                    else:
                        # 기존 방식: 점수 <= (min_buy_score + 5)
                        hold_score = min_buy_score + 5
                        if current_score <= hold_score:
                            sell_reasons.append(f"장마감정리 {score_version.upper()} {current_score}점 <= {hold_score}점")
                # 커스텀 매도 조건 사용 (sell_conditions 설정 시)
                elif self.sell_conditions:
                    if evaluate_conditions(self.sell_conditions, stock_scores):
                        cond_detail = f"V1={stock_scores['v1']}, V4={stock_scores['v4']}, V5={stock_scores['v5']}"
                        sell_reasons.append(f"매도조건 충족 ({cond_detail})")
                # 일반 점수 기반 매도 (sell_score 이하) - 폴백
                elif current_score <= sell_score:
                    sell_reasons.append(f"{score_version.upper()} {current_score}점 <= {sell_score}점")

                if sell_reasons:
                    sell_list.append({
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "quantity": quantity,
                        "current_price": current_price,
                        "avg_price": avg_price,
                        "sell_reasons": sell_reasons
                    })

            if sell_list:
                print(f"  매도 대상: {len(sell_list)}개")
                for item in sell_list:
                    print(f"    - {item['stock_name']}: {', '.join(item['sell_reasons'])}")

                # 매도 실행
                if not self.dry_run:
                    self.execute_sell_orders(sell_list)
                    sell_count = len(sell_list)
                else:
                    print("  [DRY-RUN] 실제 매도 실행 안함")
            else:
                print("  매도 대상 없음")

        # 보유 종목 수 체크 제거 - 슬롯 무제한
        remaining_slots = 9999  # 무제한

        # 3. 전종목 스크리닝 (strict 모드) - ScreeningConfig 기준 사용
        from config import ScreeningConfig

        # screening_result가 전달되면 스크리닝 건너뛰기 (--all 모드에서 1회만 실행)
        if screening_result:
            top_stocks, stats = screening_result
            print(f"\n[3] 스크리닝 결과 재사용 ({len(top_stocks)}개 종목)")
        else:
            print(f"\n[3] 전종목 스크리닝 중 (strict 모드)...")
            print(f"  시총: {ScreeningConfig.MIN_MARKET_CAP/1e8:.0f}억 ~ {ScreeningConfig.MAX_MARKET_CAP/1e8:.0f}억")
            print(f"  거래대금: {ScreeningConfig.MIN_TRADING_AMOUNT/1e8:.0f}억 이상")
            screener = MarketScreener(max_workers=ScreeningConfig.MAX_WORKERS)
            top_stocks, stats = screener.run_full_screening(
                top_n=ScreeningConfig.TOP_N,
                mode="strict",
                min_marcap=ScreeningConfig.MIN_MARKET_CAP,
                max_marcap=ScreeningConfig.MAX_MARKET_CAP,
                min_amount=ScreeningConfig.MIN_TRADING_AMOUNT,
            )

        if not top_stocks:
            print("  스크리닝 결과 없음")
            return {"status": "completed", "buy_count": 0}

        if not screening_result:
            print(f"  스크리닝 완료: {len(top_stocks)}개 종목")

        # JSON 파일에 스크리닝 결과 저장 (진단 페이지 점수 동기화용)
        try:
            from config import OUTPUT_DIR
            import json
            import numpy as np

            def convert_value(v):
                """numpy 타입을 Python 기본 타입으로 변환"""
                if isinstance(v, (np.integer, np.int64, np.int32)):
                    return int(v)
                elif isinstance(v, (np.floating, np.float64, np.float32)):
                    return round(float(v), 4)
                elif isinstance(v, float):
                    return round(v, 4)
                return v

            today_str = now.strftime('%Y%m%d')
            json_path = OUTPUT_DIR / f"top100_{today_str}.json"

            # 기존 파일이 있으면 로드
            existing_data = {}
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)

            # 전종목 점수 (all_scores) 업데이트
            all_scores = stats.get('all_scores', {})
            # 기존 all_scores와 병합 (새로운 점수로 덮어쓰기)
            existing_all_scores = existing_data.get('screening_stats', {}).get('all_scores', {})
            existing_all_scores.update(all_scores)

            # stocks 리스트 생성
            stocks_list = []
            for r in top_stocks:
                stock = {
                    "rank": r.get("rank", 0),
                    "code": r.get("code"),
                    "name": r.get("name"),
                    "score": r.get("score"),
                    "signals": r.get("signals", []),
                    "close": int(r.get("close", 0)),
                    "change_pct": round(r.get("change_pct", 0), 2),
                    "marcap": int(r.get("marcap", 0)),
                    "amount": int(r.get("amount", 0)),
                }
                if "indicators" in r:
                    stock["indicators"] = {
                        k: convert_value(v) for k, v in r["indicators"].items()
                    }
                stocks_list.append(stock)

            # 저장할 데이터
            save_data = {
                "date": today_str,
                "updated_at": now.strftime('%Y-%m-%d %H:%M:%S'),
                "mode": "intraday_strict",
                "stocks": stocks_list,
                "screening_stats": {
                    **stats,
                    "all_scores": existing_all_scores
                }
            }

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)

            print(f"  JSON 저장 완료: {json_path.name}")
        except Exception as e:
            print(f"  JSON 저장 실패: {e}")

        # 4. 매수 후보 필터링 (점수 + 시간대별 거래량 조건)
        now = datetime.now()
        hour = now.hour

        # 15:00 이후 장마감 시간에는 신규 매수 금지 (매도만 실행)
        is_closing_time = hour == 15 and now.minute >= 0
        if is_closing_time:
            print(f"\n[4] 장마감 시간 ({now.strftime('%H:%M')}) - 신규 매수 없음")
            return {"status": "completed", "buy_count": 0}

        # 14:50 이후에는 매수 조건 강화 (+5점)
        is_pre_closing = hour == 14 and now.minute >= 50
        if is_pre_closing:
            min_score = min_score + 5
            print(f"  14:50 이후 매수 조건 강화: {min_score}점 이상")

        # 시간대별 volume_ratio 기준 (장 초반은 거래량 적어도 허용)
        if hour < 10:
            min_volume_ratio = 0.1  # 09시: 10%
        elif hour < 11:
            min_volume_ratio = 0.3  # 10시: 30%
        elif hour < 12:
            min_volume_ratio = 0.5  # 11시: 50%
        elif hour < 14:
            min_volume_ratio = 0.7  # 12~13시: 70%
        else:
            min_volume_ratio = 1.0  # 14시 이후: 100%

        # 전략별 필터링 조건 출력
        if self.buy_conditions:
            cond_str = buy_conditions if buy_conditions else f"{score_version.upper()}>={min_score}"
            print(f"\n[4] 매수 후보 필터링 중 (조건: {cond_str}, 거래량 >= {min_volume_ratio:.0%})...")
        else:
            print(f"\n[4] 매수 후보 필터링 중 ({score_version.upper()} >= {min_score}, 거래량 >= {min_volume_ratio:.0%})...")

        candidates = []
        volume_filtered_count = 0
        for stock in top_stocks:
            # 사용자의 score_version에 따른 점수 사용
            scores = stock.get("scores", {})
            score = scores.get(score_version, stock.get("score", 0))
            code = stock.get("code")
            name = stock.get("name")
            volume_ratio = stock.get("volume_ratio", 0)

            # 전략별 점수 조건
            if self.buy_conditions:
                # 커스텀 조건 사용
                if not evaluate_conditions(self.buy_conditions, scores):
                    continue
                # 정렬용 점수는 첫 번째 조건의 스코어 사용
                first_score_key = self.buy_conditions[0]['score'] if self.buy_conditions else 'v1'
                score = scores.get(first_score_key, 0)
            else:
                # 단순 전략: score_version >= min_score
                if score < min_score:
                    continue

            # 시간대별 거래량 조건
            if volume_ratio < min_volume_ratio:
                volume_filtered_count += 1
                continue

            # auto_trader 형식으로 변환
            candidates.append({
                "stock_code": code,
                "stock_name": name,
                "score": score,
                "scores": scores,  # 전체 스코어 저장 (매도 판단용)
                "signals": stock.get("signals", []),
                "current_price": int(stock.get("close", 0)),
                "change_pct": stock.get("change_pct", 0),
                "amount": stock.get("amount", 0),  # 전일 거래대금
                "volume_ratio": volume_ratio,  # 거래량 비율
            })

        # 점수순 정렬 (동점 시 거래대금 많은 순)
        candidates.sort(key=lambda x: (x["score"], x.get("amount", 0)), reverse=True)
        if volume_filtered_count > 0:
            print(f"  거래량 부족으로 제외: {volume_filtered_count}개")
        if strategy == 'v1_composite':
            print(f"  최종 V1복합 매수조건 충족 후보: {len(candidates)}개")
        else:
            print(f"  최종 {min_score}점 이상 후보: {len(candidates)}개")

        if not candidates:
            print("  매수 조건 충족 종목 없음")
            return {"status": "completed", "buy_count": 0}

        # 5. 당일 블랙리스트 및 보유 종목 필터링
        print("\n[5] 블랙리스트 및 보유 종목 필터링 중...")
        holding_codes = {h.get("stock_code") for h in holdings}
        today_blacklist = self.logger.get_today_traded_stocks(self.user_id)

        if today_blacklist:
            print(f"  당일 거래 종목: {len(today_blacklist)}개 (재매수 제외)")

        filtered_candidates = []
        for c in candidates:
            code = c.get("stock_code")
            name = c.get("stock_name")

            if code in holding_codes:
                print(f"  [{name}] 이미 보유 중 - 제외")
                continue
            if code in today_blacklist:
                print(f"  [{name}] 당일 거래 이력 - 재매수 제외")
                continue

            filtered_candidates.append(c)

            # 남은 슬롯만큼만 선택
            if len(filtered_candidates) >= remaining_slots:
                break

        print(f"  최종 매수 후보: {len(filtered_candidates)}개")

        if not filtered_candidates:
            return {"status": "completed", "buy_count": 0}

        # 6. 매수 실행 (점수 높은 순으로, 종목당 투자금 고정)
        print("\n[6] 매수 주문 실행 중...")
        base_investment = self.risk_manager.calculate_investment_amount()

        # 나스닥 연동 투자금액 조정
        adjusted_investment, nasdaq_multiplier, nasdaq_change = get_adjusted_investment_amount(base_investment)
        investment_per_stock = adjusted_investment

        if nasdaq_multiplier < 1.0:
            print(f"  [NASDAQ 조정] 기본: {base_investment:,}원 × {nasdaq_multiplier} = {investment_per_stock:,}원")
        print(f"  종목당 투자금: {investment_per_stock:,}원 (주문가능: {max_buy_amt:,}원)")

        remaining_cash = max_buy_amt  # 남은 주문가능금액 추적
        buy_count = 0
        for candidate in filtered_candidates:
            stock_code = candidate["stock_code"]
            stock_name = candidate["stock_name"]
            current_price = candidate["current_price"]
            score = candidate["score"]
            candidate_scores = candidate.get("scores", {})

            # 실시간 가격 조회
            live_price = self.executor.get_current_price(stock_code)
            if live_price and live_price > 0:
                current_price = live_price

            # 급등주 제외 (15% 이상 상승 종목)
            # 스크리닝 결과의 change_pct 사용 (전일 대비 등락률)
            screening_change_pct = candidate.get("change_pct", 0)
            if screening_change_pct >= 15:
                print(f"  {stock_name}: 급등주 제외 ({screening_change_pct:+.1f}%)")
                continue

            # 실시간 가격으로도 재확인 (전일종가 기준)
            prev_close = candidate.get("current_price", 0)
            if prev_close > 0 and current_price > 0:
                realtime_change_pct = (current_price - prev_close) / prev_close * 100
                if realtime_change_pct >= 15:
                    print(f"  {stock_name}: 실시간 급등주 제외 ({realtime_change_pct:+.1f}%)")
                    continue

            # 주문가능금액 부족 시 중단
            if remaining_cash < current_price:
                print(f"  주문가능금액 소진 ({remaining_cash:,}원) - 매수 중단")
                break

            quantity = investment_per_stock // current_price

            # 가용현금 부족 시에도 semi 모드는 시그널 기록
            if quantity <= 0:
                if trade_mode == 'semi':
                    # 종목당 투자금으로 수량 계산 (가용현금 무시)
                    quantity = investment_per_stock // current_price
                    if quantity <= 0:
                        quantity = 1  # 최소 1주
                    print(f"\n매수제안 (가용현금 부족): {stock_name} ({stock_code})")
                    print(f"  현재가: {current_price:,}원, 점수: {score}점")
                    print(f"  권장수량: {quantity}주 = {current_price * quantity:,}원")

                    suggestion_id = self.logger.add_buy_suggestion(
                        user_id=self.user_id,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        current_price=current_price,
                        quantity=quantity,
                        score=score,
                        reason=f"V1={candidate_scores.get('v1',0)},V4={candidate_scores.get('v4',0)},V5={candidate_scores.get('v5',0)} (가용현금부족)" if self.buy_conditions else f"장중스크리닝 {score}점 (가용현금 부족)",
                        signals=candidate.get("signals", [])
                    )
                    if suggestion_id:
                        buy_count += 1
                        print(f"  ✅ 매수 제안 저장 (suggestion_id={suggestion_id})")
                        self.notifier.notify_suggestion(stock_name, current_price, quantity, stock_code)
                    continue
                else:
                    print(f"  {stock_name}: 매수 가능 수량 없음")
                    continue

            print(f"\n매수{'제안' if trade_mode == 'semi' else ''}: {stock_name} ({stock_code})")
            print(f"  현재가: {current_price:,}원, 점수: {score}점")
            print(f"  수량: {quantity}주 = {current_price * quantity:,}원")

            # semi 모드: 제안만 저장 (실제 주문 X)
            if trade_mode == 'semi':
                suggestion_id = self.logger.add_buy_suggestion(
                    user_id=self.user_id,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    current_price=current_price,
                    quantity=quantity,
                    score=score,
                    reason=f"V1={candidate_scores.get('v1',0)},V4={candidate_scores.get('v4',0)},V5={candidate_scores.get('v5',0)}" if self.buy_conditions else f"장중스크리닝 {score}점",
                    signals=candidate.get("signals", [])
                )
                if suggestion_id:
                    buy_count += 1
                    print(f"  ✅ 매수 제안 저장 (suggestion_id={suggestion_id})")
                    # 제안 알림
                    self.notifier.notify_suggestion(stock_name, current_price, quantity, stock_code)
                continue

            if self.dry_run:
                print("  [DRY-RUN] 실제 주문 실행 안함")
                result = {"success": True, "dry_run": True}
            else:
                result = self.executor.place_buy_order(
                    stock_code=stock_code,
                    quantity=quantity
                )

            if result.get("success"):
                buy_count += 1
                order_amount = current_price * quantity
                remaining_cash -= order_amount  # 남은 주문가능금액 차감

                # 거래 기록
                self.logger.log_order(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    side="buy",
                    quantity=quantity,
                    price=current_price,
                    order_no=result.get("order_no"),
                    trade_reason=f"V1={candidate_scores.get('v1',0)},V4={candidate_scores.get('v4',0)},V5={candidate_scores.get('v5',0)}" if self.buy_conditions else f"장중스크리닝 {score}점",
                    status="executed" if not self.dry_run else "dry_run",
                    user_id=self.user_id
                )

                # 알림
                self.notifier.notify_buy(stock_name, current_price, quantity, stock_code)

                print(f"  매수 완료! (잔여: {remaining_cash:,}원)")

        print("\n" + "=" * 60)
        print(f"  장중 스크리닝 완료: 매도 {sell_count}건, 매수 {buy_count}건")
        print("=" * 60)

        return {
            "status": "completed",
            "sell_count": sell_count,
            "buy_count": buy_count,
            "screened_stocks": len(top_stocks),
            "candidates": len(candidates),
            "filtered": len(filtered_candidates),
            "timestamp": datetime.now().isoformat()
        }

    def _check_trading_enabled(self) -> bool:
        """사용자 설정에서 거래 활성화 여부 확인"""
        if self.user_id:
            user_settings = self.logger.get_auto_trade_settings(self.user_id)
            if user_settings:
                if not user_settings.get('trading_enabled', True):
                    print(f"  거래 비활성화 상태 (user_id={self.user_id})")
                    return False
        return True


def get_active_users() -> List[Dict]:
    """
    자동매매가 활성화된 모든 사용자 조회

    Returns:
        [{'user_id': int, 'trade_mode': str, 'is_mock': bool}, ...]
    """
    from trading.trade_logger import TradeLogger
    logger = TradeLogger()

    with logger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                ats.user_id,
                ats.trade_mode,
                aks.is_mock,
                aks.account_number
            FROM auto_trade_settings ats
            JOIN api_key_settings aks ON ats.user_id = aks.user_id
            WHERE ats.trading_enabled = 1
              AND aks.app_key IS NOT NULL
        """)
        rows = cursor.fetchall()

    return [dict(row) for row in rows]


def run_for_all_users(dry_run: bool = False, min_score: int = 75):
    """모든 활성화된 사용자에 대해 자동매매 실행 (CSV 스코어 사용)

    Args:
        dry_run: 테스트 모드 (주문 X)
        min_score: 최소 매수 점수
    """
    from trading.trade_logger import TradeLogger

    # 장중 자동매매 제외 사용자 (user 7: 모의투자)
    EXCLUDED_USERS = [7]

    print("\n" + "=" * 70)
    print("  AUTO TRADER - 전체 사용자 실행 모드 (CSV)")
    print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    users = get_active_users()

    # 제외 사용자 필터링
    original_count = len(users)
    users = [u for u in users if u['user_id'] not in EXCLUDED_USERS]
    if original_count != len(users):
        print(f"\n[!] 제외된 사용자: {EXCLUDED_USERS}")

    print(f"\n[1] 활성화된 사용자: {len(users)}명")

    if not users:
        print("  활성화된 사용자가 없습니다.")
        return

    for user in users:
        print(f"  - user_id={user['user_id']}, mode={user['trade_mode']}, mock={user['is_mock']}")

    # CSV 스코어 로드 (스크리닝 없이 CSV만 사용)
    screening_result = None
    semi_auto_users = [u for u in users if u['trade_mode'] in ('semi', 'auto')]
    if semi_auto_users:
        print(f"\n[2] CSV 스코어 로드 중...")
        screening_result = load_scores_from_csv(max_age_minutes=15)
        if screening_result:
            top_stocks, stats = screening_result
            print(f"  CSV 로드 완료: {len(top_stocks)}개 종목")
        else:
            print(f"  [ERROR] CSV 로드 실패 - 최근 15분 내 CSV 파일 없음")
            print(f"  record_intraday_scores.py가 실행 중인지 확인하세요.")
            return

    results = []

    for user in users:
        user_id = user['user_id']
        trade_mode = user['trade_mode']

        print(f"\n{'='*60}")
        print(f"[USER {user_id}] 처리 시작 (mode={trade_mode})")
        print(f"{'='*60}")

        try:
            # 사용자별 설정 로드
            logger = TradeLogger()
            api_key_data = logger.get_api_key_settings(user_id)

            if not api_key_data:
                print(f"  API 키 없음 - 건너뜀")
                continue

            user_config = {
                'app_key': api_key_data.get('app_key'),
                'app_secret': api_key_data.get('app_secret'),
                'account_number': api_key_data.get('account_number'),
                'account_product_code': api_key_data.get('account_product_code', '01'),
                'is_mock': bool(api_key_data.get('is_mock', True))
            }

            # 사용자별 자동매매 설정 조회
            user_settings = logger.get_auto_trade_settings(user_id) or {}
            user_min_score = user_settings.get('min_buy_score', min_score)
            user_sell_score = user_settings.get('sell_score', 40)
            user_score_version = user_settings.get('score_version', 'v2')
            user_strategy = user_settings.get('strategy', 'simple')
            user_buy_conditions = user_settings.get('buy_conditions', '')
            user_sell_conditions = user_settings.get('sell_conditions', '')

            if user_buy_conditions:
                print(f"  설정: 매수({user_buy_conditions}) / 매도({user_sell_conditions})")
            else:
                print(f"  설정: {user_score_version.upper()} min_buy={user_min_score}점, sell={user_sell_score}점")

            trader = AutoTrader(
                dry_run=dry_run,
                user_id=user_id,
                user_config=user_config
            )

            # trade_mode에 따라 다른 실행
            if trade_mode == 'greenlight':
                result = trader.run_greenlight()
            elif trade_mode in ('auto', 'semi'):
                result = trader.run_intraday(
                    min_score=user_min_score,
                    screening_result=screening_result,
                    trade_mode=trade_mode,
                    score_version=user_score_version,
                    strategy=user_strategy,
                    buy_conditions=user_buy_conditions,
                    sell_conditions=user_sell_conditions
                )
            else:
                print(f"  지원하지 않는 모드: {trade_mode}")
                continue

            results.append({
                'user_id': user_id,
                'trade_mode': trade_mode,
                'result': result
            })

        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'user_id': user_id,
                'trade_mode': trade_mode,
                'result': {'status': 'error', 'message': str(e)}
            })

    # 결과 요약
    print("\n" + "=" * 70)
    print("  실행 결과 요약")
    print("=" * 70)

    for r in results:
        status = r['result'].get('status', 'unknown')
        buy = r['result'].get('buy_count', 0)
        sell = r['result'].get('sell_count', 0)
        print(f"  user_id={r['user_id']}: {status} (매수:{buy}, 매도:{sell})")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="자동매매 시스템")
    parser.add_argument("--dry-run", action="store_true", help="테스트 실행 (실제 주문 X)")
    parser.add_argument("--report", action="store_true", help="성과 리포트만 출력")
    parser.add_argument("--days", type=int, default=30, help="리포트 조회 기간 (기본: 30일)")
    parser.add_argument("--intraday", action="store_true", help="장중 10분 스크리닝 모드")
    parser.add_argument("--min-score", type=int, default=75, help="장중 스크리닝 최소 점수 (기본: 75)")
    parser.add_argument("--user-id", type=int, help="사용자 ID (장중 스크리닝용)")
    parser.add_argument("--all", action="store_true", help="모든 활성화된 사용자 실행 (CSV 스코어 사용)")
    args = parser.parse_args()

    # --all 옵션: 모든 활성화된 사용자 실행 (CSV 스코어만 사용)
    if args.all:
        run_for_all_users(dry_run=args.dry_run, min_score=args.min_score)
        return

    # user_id가 지정되면 해당 사용자 설정 사용
    user_config = None
    if args.user_id:
        logger = TradeLogger()
        api_key_data = logger.get_api_key_settings(args.user_id)
        if api_key_data:
            user_config = {
                'app_key': api_key_data.get('app_key'),
                'app_secret': api_key_data.get('app_secret'),
                'account_number': api_key_data.get('account_number'),
                'account_product_code': api_key_data.get('account_product_code', '01'),
                'is_mock': bool(api_key_data.get('is_mock', True))
            }

    trader = AutoTrader(dry_run=args.dry_run, user_id=args.user_id, user_config=user_config)

    if args.report:
        trader.print_report(days=args.days)
    elif args.intraday:
        # 장중 10분 스크리닝 모드
        # user_id가 지정된 경우 trade_mode, min_buy_score 조회
        trade_mode = 'auto'
        min_score = args.min_score
        if args.user_id:
            logger = TradeLogger()
            settings = logger.get_auto_trade_settings(args.user_id)
            if settings:
                db_mode = settings.get('trade_mode', 'auto')
                trade_mode = db_mode if db_mode in ('semi', 'auto') else 'auto'
                # 사용자 설정의 min_buy_score 적용
                user_min_score = settings.get('min_buy_score')
                if user_min_score is not None:
                    min_score = user_min_score
                    print(f"[AutoTrader] 사용자 {args.user_id} min_buy_score: {min_score}점")
        trader.run_intraday(min_score=min_score, trade_mode=trade_mode)
    else:
        trader.run()


if __name__ == "__main__":
    main()
