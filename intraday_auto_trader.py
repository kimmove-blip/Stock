#!/usr/bin/env python3
"""
V1~V10 장중 스코어 기반 자동매매 메인 스크립트
10분마다 실행되어 매수/매도 신호 생성 및 주문 실행

개선사항 v1.1 (2026-01-27):
1. Market Regime Filter: KOSPI/KOSDAQ MA20 vs MA60 체크
2. Dynamic Exit Strategy: 스코어링 엔진의 ATR 기반 청산 전략 적용
3. V10 Real-time Enhancement: 대장주-종속주 전략 강화
4. Order Execution: 매도1호가 기반 주문 (시장가 대비 슬리피지 감소)
"""

import os
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading.trade_logger import TradeLogger
from trading.intraday.score_monitor import ScoreMonitor
from trading.intraday.strategy_engine import StrategyEngine
from trading.intraday.position_manager import PositionManager
from trading.intraday.exit_manager import ExitManager
from api.services.kis_client import KISClient

try:
    from pykrx import stock as pykrx_stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False


# 기본 설정
DEFAULT_CONFIG = {
    'strategies': {
        'v2_trend': {
            'enabled': True,
            'score_threshold': 65,   # V2>=65
            'max_positions': 10,
            'exit_rules': {
                'target_atr_mult': 1.0,  # 장중 청산용 (낮춤)
                'stop_atr_mult': 0.8,    # 장중 청산용 (낮춤)
                'time_stop_days': 1      # 당일 청산 원칙
            }
        },
        'v8_bounce': {
            'enabled': True,
            'score_threshold': 60,   # 하향 (70→60)
            'max_positions': 3,
            'exit_rules': {
                'target_atr_mult': 1.5,  # 상향 (1.2→1.5)
                'stop_atr_mult': 1.2,    # 하향 (0.6→1.2) - 역발상은 변동성 큼
                'time_stop_days': 2
            }
        },
        'v10_follower': {
            'enabled': True,
            'leader_min_change': 3.0,
            'max_positions': 3,
            'exit_rules': {
                'target_atr_mult': 1.5,  # 상향 (1.0→1.5)
                'stop_atr_mult': 1.0,    # 하향 (0.5→1.0)
                'time_stop_days': 3
            }
        }
    },
    'risk_management': {
        'max_total_positions': 15,
        'max_daily_trades': 20,
        'max_stock_ratio': 0.10,  # 종목당 최대 10%
        'min_cash_ratio': 0.20    # 최소 현금 20% 유지
    },
    'trading_hours': {
        'start': '09:10',
        'end': '15:20'
    },
    'market_regime': {
        'enabled': True,          # 시장 상황 필터 사용 여부
        'bullish_only': False,    # True면 상승장에서만 매수
        'check_both_markets': False  # True면 KOSPI/KOSDAQ 모두 체크
    },
    # v1.7 모멘텀 필터 (2026-01-27 백테스트 최종 결과)
    #
    # 최적 전략: V2>=65 + 거래대금 100억+
    # - 5개 종목, +7.68% 평균 (KOSPI 대비 +4.95%p)
    # - 거래대금 너무 높이면 오히려 손해 (1조+는 +2.98%에 불과)
    #
    'momentum_filter': {
        'enabled': True,
        'min_change_pct': 0.0,      # 모멘텀 필터 완화 (V2 스코어가 핵심)
        'max_change_pct': 15.0,     # 과열 방지
        'optimal_min': 3.0,         # 최적 구간 하한
        'optimal_max': 10.0,        # 최적 구간 상한
        'min_amount': 100_000_000_000,  # 최소 거래대금 100억 (최적값)
        'prefer_high_amount': False,    # 거래대금 높은 종목 우선 X
        'mega_cap_mode': False,         # 초대형주 모드 비활성화
    }
}


class IntradayAutoTrader:
    """장중 자동매매 실행기"""

    def __init__(
        self,
        config: dict = None,
        dry_run: bool = False,
        verbose: bool = True
    ):
        """
        Args:
            config: 설정 딕셔너리
            dry_run: True면 실제 주문 없이 시뮬레이션
            verbose: 상세 로그 출력
        """
        self.config = config or DEFAULT_CONFIG
        self.dry_run = dry_run
        self.verbose = verbose

        # 모듈 초기화
        self.logger = TradeLogger()
        self.monitor = ScoreMonitor()
        self.engine = StrategyEngine(self.config.get('strategies'))
        self.pm = PositionManager()
        self.em = ExitManager(self.pm)

        # KIS 클라이언트 캐시 (user_id -> client)
        self._kis_clients = {}

        # 시장 상황 캐시
        self._market_regime = None
        self._market_regime_time = None

        # 손절 종목 블랙리스트 (당일 재진입 금지)
        # {user_id: {stock_code: stop_time}}
        self._stopped_stocks = {}

    def log(self, msg: str, level: str = 'INFO'):
        """로그 출력"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if self.verbose or level in ['ERROR', 'WARNING']:
            print(f"[{timestamp}] [{level}] {msg}")

    def is_trading_hours(self) -> bool:
        """거래 시간대 체크"""
        now = datetime.now()
        hours = self.config.get('trading_hours', {})

        start_str = hours.get('start', '09:10')
        end_str = hours.get('end', '15:20')

        try:
            start_time = datetime.strptime(start_str, '%H:%M').time()
            end_time = datetime.strptime(end_str, '%H:%M').time()
            current_time = now.time()

            return start_time <= current_time <= end_time
        except ValueError:
            return True  # 파싱 실패 시 허용

    def get_market_regime(self, force_refresh: bool = False) -> dict:
        """
        시장 상황(레짐) 체크 - KOSPI/KOSDAQ MA20 vs MA60 비교

        네이버 금융에서 지수 데이터 조회 (HTML 스크래핑)

        Returns:
            {
                'kospi': {'ma20': float, 'ma60': float, 'trend': 'bullish'|'bearish'|'neutral'},
                'kosdaq': {'ma20': float, 'ma60': float, 'trend': 'bullish'|'bearish'|'neutral'},
                'can_trade': bool,
                'reason': str
            }
        """
        import requests
        import pandas as pd
        from io import StringIO

        # 캐시 확인 (10분 유효)
        now = datetime.now()
        if not force_refresh and self._market_regime_time:
            elapsed = (now - self._market_regime_time).total_seconds()
            if elapsed < 600 and self._market_regime:  # 10분
                return self._market_regime

        result = {
            'kospi': {'ma20': 0, 'ma60': 0, 'trend': 'neutral', 'current': 0},
            'kosdaq': {'ma20': 0, 'ma60': 0, 'trend': 'neutral', 'current': 0},
            'can_trade': True,
            'reason': 'OK'
        }

        def get_naver_index_data(symbol: str) -> dict:
            """
            네이버 금융에서 지수 데이터 조회 (HTML 스크래핑)

            Args:
                symbol: 'KOSPI' 또는 'KOSDAQ'

            Returns:
                {'current': float, 'ma20': float, 'ma60': float, 'trend': str}
            """
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                # 80일치 데이터 수집 (페이지당 약 6일)
                all_data = []
                for page in range(1, 15):  # 최대 14페이지 (약 84일)
                    url = f"https://finance.naver.com/sise/sise_index_day.naver?code={symbol}&page={page}"
                    response = requests.get(url, headers=headers, timeout=10)
                    response.encoding = 'euc-kr'

                    dfs = pd.read_html(StringIO(response.text))
                    if dfs and len(dfs) > 0:
                        df = dfs[0].dropna(subset=['날짜'])
                        if df.empty:
                            break

                        for _, row in df.iterrows():
                            try:
                                close_val = row['체결가']
                                if isinstance(close_val, str):
                                    close_val = float(close_val.replace(',', ''))
                                all_data.append({
                                    'date': row['날짜'],
                                    'close': close_val
                                })
                            except (ValueError, TypeError):
                                continue

                    if len(all_data) >= 70:
                        break

                if len(all_data) < 60:
                    return {'current': 0, 'ma20': 0, 'ma60': 0, 'trend': 'neutral'}

                # DataFrame 생성 (최신순 -> 과거순 정렬 필요)
                df = pd.DataFrame(all_data)
                df = df.iloc[::-1].reset_index(drop=True)  # 과거 -> 최신 순으로

                df['MA20'] = df['close'].rolling(window=20).mean()
                df['MA60'] = df['close'].rolling(window=60).mean()

                latest = df.iloc[-1]
                current = latest['close']
                ma20 = latest['MA20']
                ma60 = latest['MA60']

                # MA60이 계산되지 않으면 (데이터 부족)
                if pd.isna(ma60):
                    ma60 = ma20 * 0.99 if not pd.isna(ma20) else 0

                # 추세 판단
                if ma20 > ma60 * 1.01:  # 1% 이상 위
                    trend = 'bullish'
                elif ma20 < ma60 * 0.99:  # 1% 이상 아래
                    trend = 'bearish'
                else:
                    trend = 'neutral'

                return {
                    'current': float(current),
                    'ma20': float(ma20) if not pd.isna(ma20) else 0,
                    'ma60': float(ma60) if not pd.isna(ma60) else 0,
                    'trend': trend
                }

            except Exception as e:
                self.log(f"네이버 {symbol} 지수 조회 실패: {e}", 'WARNING')
                return {'current': 0, 'ma20': 0, 'ma60': 0, 'trend': 'neutral'}

        try:
            # KOSPI 지수 조회
            result['kospi'] = get_naver_index_data('KOSPI')

            # KOSDAQ 지수 조회
            result['kosdaq'] = get_naver_index_data('KOSDAQ')

            # 거래 가능 여부 판단
            regime_config = self.config.get('market_regime', {})

            if regime_config.get('enabled', True):
                if regime_config.get('check_both_markets', False):
                    # 둘 다 하락장이면 매수 제한
                    if result['kospi']['trend'] == 'bearish' and result['kosdaq']['trend'] == 'bearish':
                        result['can_trade'] = False
                        result['reason'] = 'KOSPI/KOSDAQ 모두 하락장 (MA20 < MA60)'
                else:
                    # KOSPI 기준
                    if result['kospi']['trend'] == 'bearish':
                        if regime_config.get('bullish_only', False):
                            result['can_trade'] = False
                            result['reason'] = 'KOSPI 하락장 (MA20 < MA60), 매수 제한'
                        else:
                            result['reason'] = 'KOSPI 하락장 주의 (V8 역발상 전략만 권장)'

        except Exception as e:
            self.log(f"시장 상황 조회 실패: {e}", 'ERROR')

        # 캐시 업데이트
        self._market_regime = result
        self._market_regime_time = now

        return result

    def get_ask_price(self, user_id: int, stock_code: str) -> int:
        """
        매도1호가 (ask price) 조회 - 슬리피지 최소화된 매수가

        Args:
            user_id: 사용자 ID
            stock_code: 종목코드

        Returns:
            매도1호가 (없으면 0)
        """
        try:
            client = self.get_kis_client(user_id)
            result = client.get_current_price(stock_code)
            if result:
                # 매도1호가 = 현재 시장에서 살 수 있는 최저가
                ask_price = result.get('ask_price1', result.get('ask_price', 0))
                if ask_price and int(ask_price) > 0:
                    return int(ask_price)
                # 없으면 현재가 사용
                return int(result.get('current_price', 0))
        except Exception as e:
            self.log(f"매도1호가 조회 실패 ({stock_code}): {e}", 'ERROR')
        return 0

    def _apply_momentum_filter(self, signals: list, df, config: dict) -> list:
        """
        v1.6: 모멘텀 필터 적용 (2026-01-27 백테스트 결과 기반)

        분석 결과:
        - 아침 20%+ 급등 종목: 평균 -25%p 폭락 → 절대 제외
        - 거래대금 100억+ 필터: +1.26% 평균
        - 거래대금 1조+ 필터: +2.98% 평균 (KOSPI 대비 +0.25%p)
        - 결론: 초대형주 집중 전략이 가장 안정적

        Args:
            signals: 원본 시그널 리스트
            df: 스코어 DataFrame
            config: 모멘텀 필터 설정

        Returns:
            필터링된 시그널 리스트
        """
        if not signals or df is None or df.empty:
            return signals

        min_change = config.get('min_change_pct', 3.0)
        max_change = config.get('max_change_pct', 10.0)
        optimal_min = config.get('optimal_min', 3.0)
        optimal_max = config.get('optimal_max', 8.0)
        min_amount = config.get('min_amount', 500_000_000_000)
        mega_cap_mode = config.get('mega_cap_mode', True)
        mega_cap_threshold = 1_000_000_000_000  # 1조

        filtered = []
        excluded_overheated = []
        excluded_low_momentum = []
        excluded_low_amount = []

        for sig in signals:
            code = sig['code']
            row = df[df['code'] == code]

            if row.empty:
                filtered.append(sig)  # 데이터 없으면 통과
                continue

            row = row.iloc[0]
            change_pct = row.get('change_pct', 0)
            amount = row.get('amount', row.get('prev_amount', 0))

            # 1. 과열 종목 제외 (10%+ 급등 - 강화)
            if change_pct > max_change:
                excluded_overheated.append((sig['name'], change_pct))
                continue

            # 2. 모멘텀 부족 종목 제외 (최소 등락률 미달)
            if change_pct < min_change:
                excluded_low_momentum.append((sig['name'], change_pct))
                continue

            # 3. 거래대금 필터
            if amount < min_amount:
                excluded_low_amount.append((sig['name'], amount / 1e8))
                continue

            # 4. 모멘텀 스코어 계산
            if optimal_min <= change_pct <= optimal_max:
                sig['momentum_score'] = 1.0  # 최적 구간
            elif min_change <= change_pct < optimal_min:
                sig['momentum_score'] = 0.7  # 양호
            else:
                sig['momentum_score'] = 0.5  # 상한 근처

            # 5. v1.6 mega_cap_mode: 1조+ 종목에 보너스
            if mega_cap_mode and amount >= mega_cap_threshold:
                sig['momentum_score'] += 0.5  # 초대형주 보너스
                sig['is_mega_cap'] = True
            else:
                sig['is_mega_cap'] = False

            sig['change_pct'] = change_pct
            sig['amount'] = amount
            filtered.append(sig)

        # 로그 출력
        if excluded_overheated:
            self.log(f"모멘텀 필터: 과열 제외 {len(excluded_overheated)}개 - "
                    f"{', '.join([f'{n}({c:+.1f}%)' for n, c in excluded_overheated[:3]])}")
        if excluded_low_momentum:
            self.log(f"모멘텀 필터: 모멘텀 부족 {len(excluded_low_momentum)}개")
        if excluded_low_amount:
            self.log(f"모멘텀 필터: 거래대금 부족 {len(excluded_low_amount)}개")

        # 거래대금 높은 순으로 정렬 (mega_cap 우선, 모멘텀 스코어 → 거래대금 순)
        if config.get('prefer_high_amount', True):
            filtered.sort(key=lambda x: (
                x.get('momentum_score', 0),
                x.get('amount', 0)
            ), reverse=True)

        mega_count = sum(1 for s in filtered if s.get('is_mega_cap', False))
        self.log(f"모멘텀 필터: {len(signals)}개 → {len(filtered)}개 통과 (초대형주 {mega_count}개)")
        return filtered

    def get_atr_from_scores(self, df, stock_code: str) -> float:
        """
        스코어 데이터에서 ATR 값 추출

        Args:
            df: 스코어 DataFrame
            stock_code: 종목코드

        Returns:
            ATR 값 (없으면 0)
        """
        if df is None or df.empty:
            return 0

        row = df[df['code'] == stock_code]
        if row.empty:
            return 0

        row = row.iloc[0]

        # 스코어링 엔진에서 계산된 ATR 값 (있으면)
        atr = row.get('atr', 0)
        if atr and atr > 0:
            return float(atr)

        # ATR 컬럼이 없으면 고가-저가 기반 추정
        high = row.get('high', 0)
        low = row.get('low', 0)
        close = row.get('close', 0)

        if high > 0 and low > 0 and close > 0:
            # 당일 변동폭 기반 추정 (단일 봉이므로 정확하지 않음)
            return max((high - low), close * 0.03)

        return close * 0.03 if close > 0 else 0  # 3% 기본 변동폭

    def get_kis_client(self, user_id: int) -> KISClient:
        """사용자별 KIS 클라이언트 반환 (캐싱)"""
        if user_id in self._kis_clients:
            return self._kis_clients[user_id]

        # API 키 조회
        api_key_data = self.logger.get_api_key_settings(user_id)
        if not api_key_data:
            raise ValueError(f"User {user_id}: API 키 설정 없음")

        client = KISClient(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_virtual=bool(api_key_data.get('is_mock', True))
        )

        self._kis_clients[user_id] = client
        return client

    def get_current_price(self, user_id: int, stock_code: str) -> int:
        """현재가 조회"""
        try:
            client = self.get_kis_client(user_id)
            result = client.get_current_price(stock_code)
            if result:
                return int(result.get('current_price', 0))
        except Exception as e:
            self.log(f"현재가 조회 실패 ({stock_code}): {e}", 'ERROR')
        return 0

    def get_auto_users(self) -> list:
        """auto 모드 사용자 목록 조회"""
        with self.logger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id FROM auto_trade_settings
                WHERE trade_mode = 'auto' AND trading_enabled = 1
            """)
            return [row['user_id'] for row in cursor.fetchall()]

    def get_user_settings(self, user_id: int) -> dict:
        """사용자 자동매매 설정 조회"""
        settings = self.logger.get_auto_trade_settings(user_id)
        return settings or {}

    def get_account_info(self, user_id: int) -> dict:
        """계좌 정보 조회"""
        try:
            api_key_data = self.logger.get_api_key_settings(user_id)
            if not api_key_data:
                return {}

            return self.logger.get_real_account_balance(
                app_key=api_key_data.get('app_key'),
                app_secret=api_key_data.get('app_secret'),
                account_number=api_key_data.get('account_number'),
                account_product_code=api_key_data.get('account_product_code', '01'),
                is_mock=bool(api_key_data.get('is_mock', True))
            )
        except Exception as e:
            self.log(f"계좌 정보 조회 실패 (User {user_id}): {e}", 'ERROR')
            return {}

    def process_exits(self, user_id: int) -> list:
        """
        청산 조건 체크 및 실행

        Args:
            user_id: 사용자 ID

        Returns:
            청산 결과 리스트
        """
        self.log(f"User {user_id}: 청산 조건 체크...")

        def price_getter(code):
            return self.get_current_price(user_id, code)

        def order_executor(code, side, qty, price):
            if self.dry_run:
                return {'success': True, 'order_no': 'DRY-RUN'}
            client = self.get_kis_client(user_id)
            return client.place_order(code, side, qty, price, order_type='01')

        # 청산 대상 체크
        exit_list = self.em.check_all_positions(user_id, price_getter)

        if not exit_list:
            self.log(f"User {user_id}: 청산 대상 없음")
            return []

        self.log(f"User {user_id}: 청산 대상 {len(exit_list)}개")

        # 청산 실행
        results = self.em.execute_exits(exit_list, order_executor, self.dry_run)

        for r in results:
            if r['executed']:
                self.log(f"  청산: {r['stock_code']} {r['stock_name']} "
                        f"@{r['exit_price']:,}원 ({r['exit_reason']}) "
                        f"수익률: {r['pnl_rate']:.2f}%")

                # 손절 종목 기록 (당일 재진입 금지)
                if r['exit_reason'] == 'STOP':
                    if user_id not in self._stopped_stocks:
                        self._stopped_stocks[user_id] = {}
                    self._stopped_stocks[user_id][r['stock_code']] = datetime.now().isoformat()
                    self.log(f"  → {r['stock_code']} 당일 재진입 금지 등록")

                # 거래 로그 기록
                if not self.dry_run:
                    self.logger.log_order(
                        stock_code=r['stock_code'],
                        stock_name=r['stock_name'],
                        side='sell',
                        quantity=r['quantity'],
                        price=r['exit_price'],
                        order_no=r.get('order_no'),
                        trade_reason=f"장중자동매매-{r['exit_reason']}",
                        status='ordered',
                        user_id=user_id
                    )

        return results

    def process_entries(self, user_id: int, df, market_regime: dict = None) -> list:
        """
        매수 시그널 체크 및 실행

        Args:
            user_id: 사용자 ID
            df: 스코어 DataFrame
            market_regime: 시장 상황 (None이면 자동 조회)

        Returns:
            매수 결과 리스트
        """
        self.log(f"User {user_id}: 매수 시그널 체크...")

        # 1. 시장 상황 체크 (Market Regime Filter)
        if market_regime is None:
            market_regime = self.get_market_regime()

        regime_config = self.config.get('market_regime', {})
        if regime_config.get('enabled', True) and not market_regime.get('can_trade', True):
            self.log(f"User {user_id}: 시장 상황 불리 - {market_regime.get('reason')}", 'WARNING')
            if regime_config.get('bullish_only', False):
                return []
            # 하락장에서는 V8 역발상만 허용
            self.log(f"User {user_id}: 하락장 모드 - V8 역발상 전략만 허용")

        # 사용자 설정 조회
        settings = self.get_user_settings(user_id)
        if not settings:
            self.log(f"User {user_id}: 설정 없음, 스킵", 'WARNING')
            return []

        # 계좌 정보 조회
        account = self.get_account_info(user_id)
        if not account:
            self.log(f"User {user_id}: 계좌 정보 없음, 스킵", 'WARNING')
            return []

        # 현금 잔고
        cash_balance = account.get('summary', {}).get('cash_balance', 0)
        if isinstance(cash_balance, str):
            cash_balance = int(cash_balance.replace(',', ''))

        # 최대 투자금 및 종목당 비율
        max_investment = settings.get('max_investment', cash_balance)
        stock_ratio = settings.get('stock_ratio', 5) / 100  # %를 비율로

        risk_config = self.config.get('risk_management', {})
        min_cash_ratio = risk_config.get('min_cash_ratio', 0.20)

        # 최소 현금 유지 체크
        available_cash = int(cash_balance * (1 - min_cash_ratio))
        insufficient_cash = available_cash < 500000  # 50만원 미만 플래그

        # 포지션 한도 체크
        max_total = risk_config.get('max_total_positions', 15)
        max_daily = risk_config.get('max_daily_trades', 20)

        limit_check = self.pm.check_position_limits(
            user_id, 'all', max_total, max_total, max_daily
        )

        if not limit_check['can_open']:
            self.log(f"User {user_id}: {limit_check['reason']}")
            return []

        # 이미 보유 중인 종목 제외
        open_positions = self.pm.get_open_positions(user_id)
        exclude_codes = [p['stock_code'] for p in open_positions]

        # 기존 holdings 테이블 종목도 제외
        existing_holdings = self.logger.get_holdings(user_id)
        exclude_codes.extend([h['stock_code'] for h in existing_holdings])

        # 당일 손절 종목 제외 (재진입 금지)
        today = datetime.now().strftime('%Y-%m-%d')
        user_stopped = self._stopped_stocks.get(user_id, {})
        for code, stop_time in user_stopped.items():
            if stop_time.startswith(today):
                exclude_codes.append(code)

        exclude_codes = list(set(exclude_codes))

        # 시장 상황에 따른 전략 필터링
        context = {'market_regime': market_regime}
        if market_regime.get('kospi', {}).get('trend') == 'bearish':
            # 하락장에서는 V8 역발상만 허용
            context['allowed_strategies'] = ['v8_bounce']
            self.log(f"User {user_id}: 하락장 - V8 전략만 활성화")

        # 최적 시그널 조회
        signals = self.engine.get_best_signals(
            df,
            context=context,
            exclude_codes=exclude_codes,
            max_total=max_total - len(exclude_codes)
        )

        # 하락장 전략 필터
        if context.get('allowed_strategies'):
            signals = [s for s in signals if s.get('strategy_name') in context['allowed_strategies']]

        # v1.2: 모멘텀 필터 적용
        mom_config = self.config.get('momentum_filter', {})
        if mom_config.get('enabled', True):
            signals = self._apply_momentum_filter(signals, df, mom_config)

        if not signals:
            self.log(f"User {user_id}: 매수 시그널 없음")
            return []

        self.log(f"User {user_id}: 매수 후보 {len(signals)}개")

        # 시그널 상세 기록 (실제 매수 여부와 무관하게)
        for sig in signals[:10]:  # 상위 10개만 로그
            self.log(f"  - {sig['code']} {sig['name']}: V2={sig.get('score', 0)} "
                     f"신뢰도={sig.get('confidence', 0):.2f} 가격={sig.get('price', 0):,}원")

        # 가용현금 부족 시 시그널 기록만 하고 실제 매수 안 함
        if insufficient_cash:
            self.log(f"User {user_id}: 가용 현금 부족 ({available_cash:,}원) - 매수 스킵")
            # 시그널 정보를 결과에 포함 (executed=False)
            skipped_results = []
            for sig in signals[:5]:
                skipped_results.append({
                    'stock_code': sig['code'],
                    'stock_name': sig['name'],
                    'strategy': sig.get('strategy_name', 'v2_trend'),
                    'score': sig.get('score', 0),
                    'price': sig.get('price', 0),
                    'executed': False,
                    'reason': '가용현금 부족'
                })
            return skipped_results

        results = []
        total_bought = 0

        for sig in signals:
            # 포지션 한도 재체크
            strategy_name = sig.get('strategy_name', 'v2_trend')
            strategy_config = self.config.get('strategies', {}).get(strategy_name, {})
            max_positions = strategy_config.get('max_positions', 5)

            limit_check = self.pm.check_position_limits(
                user_id, strategy_name, max_positions, max_total, max_daily
            )

            if not limit_check['can_open']:
                continue

            # 종목당 투자금 계산
            stock_amount = int(min(max_investment * stock_ratio, available_cash - total_bought))
            if stock_amount < 100000:  # 10만원 미만이면 스킵
                continue

            # 2. 개선된 가격 조회 - 매도1호가 사용
            # (시장가 주문 시에도 실제 체결될 가격에 가까움)
            current_price = sig.get('price', 0)
            if current_price <= 0:
                # 매도1호가 우선 조회
                current_price = self.get_ask_price(user_id, sig['code'])
                if current_price <= 0:
                    # 없으면 현재가 조회
                    current_price = self.get_current_price(user_id, sig['code'])

            if current_price <= 0:
                continue

            # 수량 계산
            quantity = stock_amount // current_price
            if quantity <= 0:
                continue

            # 3. Dynamic Exit Strategy: ATR 값 추출
            atr = self.get_atr_from_scores(df, sig['code'])
            if atr <= 0:
                # 기본 ATR (3% 변동폭)
                atr = current_price * 0.03

            result = {
                'stock_code': sig['code'],
                'stock_name': sig['name'],
                'strategy': strategy_name,
                'price': current_price,
                'quantity': quantity,
                'amount': current_price * quantity,
                'score': sig['score'],
                'confidence': sig['confidence'],
                'atr': atr,
                'executed': False,
                'order_no': None
            }

            # 주문 실행
            if self.dry_run:
                exit_prices = self.pm.calculate_exit_prices(
                    current_price, atr, strategy_name, strategy_config.get('exit_rules')
                )
                self.log(f"  [DRY-RUN] 매수: {sig['code']} {sig['name']} "
                        f"{quantity}주 @{current_price:,}원 "
                        f"({strategy_name}, 신뢰도={sig['confidence']:.2f})")
                self.log(f"    목표가: {exit_prices['target_price']:,}원, "
                        f"손절가: {exit_prices['stop_price']:,}원 (ATR={atr:,.0f})")
                result['executed'] = True
                result['target_price'] = exit_prices['target_price']
                result['stop_price'] = exit_prices['stop_price']
            else:
                try:
                    client = self.get_kis_client(user_id)
                    # 4. 개선된 주문: 시장가(01) 대신 지정가(00) + 매도1호가 사용 고려
                    # 현재는 시장가 유지 (체결 확실성 우선)
                    order_result = client.place_order(
                        sig['code'], 'buy', quantity, 0, order_type='01'
                    )

                    if order_result and order_result.get('success'):
                        result['executed'] = True
                        result['order_no'] = order_result.get('order_no')

                        # 포지션 오픈 (ATR 포함)
                        self.pm.open_position(
                            user_id=user_id,
                            stock_code=sig['code'],
                            stock_name=sig['name'],
                            strategy=strategy_name,
                            entry_price=current_price,
                            quantity=quantity,
                            entry_score=sig['score'],
                            atr=atr,  # ATR 값 전달
                            max_hold_days=strategy_config.get('exit_rules', {}).get('time_stop_days', 3),
                            strategy_config=strategy_config.get('exit_rules')
                        )

                        # 거래 로그 기록
                        self.logger.log_order(
                            stock_code=sig['code'],
                            stock_name=sig['name'],
                            side='buy',
                            quantity=quantity,
                            price=current_price,
                            order_no=result['order_no'],
                            trade_reason=f"장중자동매매-{strategy_name}",
                            status='ordered',
                            user_id=user_id
                        )

                        self.log(f"  매수: {sig['code']} {sig['name']} "
                                f"{quantity}주 @{current_price:,}원 (ATR={atr:,.0f})")

                except Exception as e:
                    self.log(f"  매수 실패 ({sig['code']}): {e}", 'ERROR')
                    result['error'] = str(e)

            results.append(result)
            total_bought += result['amount']

            # 일일 거래 한도 체크
            if self.pm.count_today_trades(user_id) >= max_daily:
                break

        return results

    def run_once(self, user_id: int = None) -> dict:
        """
        단일 실행 (특정 사용자 또는 전체)

        Args:
            user_id: 특정 사용자 ID (None이면 전체)

        Returns:
            실행 결과
        """
        self.log("=" * 50)
        self.log("장중 자동매매 실행 시작")

        if not self.is_trading_hours():
            self.log("거래 시간 외입니다.", 'WARNING')
            return {'status': 'skipped', 'reason': '거래 시간 외'}

        # 최신 스코어 로드
        df = self.monitor.get_latest_scores()
        if df is None or df.empty:
            self.log("스코어 데이터 없음", 'ERROR')
            return {'status': 'error', 'reason': '스코어 데이터 없음'}

        timestamp = self.monitor.get_file_timestamp()
        self.log(f"스코어 타임스탬프: {timestamp}")

        # 시장 상황 체크 (Market Regime Filter)
        market_regime = self.get_market_regime()
        self.log(f"시장 상황: KOSPI={market_regime['kospi']['trend']}, "
                f"KOSDAQ={market_regime['kosdaq']['trend']}")
        if not market_regime.get('can_trade', True):
            self.log(f"시장 상황 경고: {market_regime.get('reason')}", 'WARNING')

        # 대상 사용자
        if user_id:
            users = [user_id]
        else:
            users = self.get_auto_users()

        if not users:
            self.log("auto 모드 사용자 없음")
            return {'status': 'skipped', 'reason': 'auto 모드 사용자 없음'}

        self.log(f"대상 사용자: {users}")

        results = {
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'market_regime': market_regime,
            'users': {}
        }

        for uid in users:
            self.log(f"\n--- User {uid} 처리 ---")

            user_result = {
                'exits': [],
                'entries': []
            }

            try:
                # 1. 청산 처리
                exits = self.process_exits(uid)
                user_result['exits'] = exits

                # 2. 매수 처리 (시장 상황 전달)
                entries = self.process_entries(uid, df, market_regime)
                user_result['entries'] = entries

            except Exception as e:
                self.log(f"User {uid} 처리 실패: {e}", 'ERROR')
                user_result['error'] = str(e)

            results['users'][uid] = user_result

        self.log("\n장중 자동매매 실행 완료")
        self.log("=" * 50)

        return results

    def generate_report(self, results: dict, save_to_file: bool = True) -> str:
        """
        실행 결과 요약 리포트 생성

        Args:
            results: run_once 실행 결과
            save_to_file: 파일 저장 여부

        Returns:
            리포트 문자열
        """
        now = datetime.now()
        lines = []

        # 헤더
        lines.append("=" * 60)
        lines.append(f"  장중 자동매매 실행 리포트")
        lines.append(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")

        # 상태
        status = results.get('status', 'unknown')
        lines.append(f"실행 상태: {status}")

        if status == 'skipped':
            lines.append(f"사유: {results.get('reason', '')}")
            lines.append("")
            report = "\n".join(lines)
            if save_to_file:
                self._save_report(report, now)
            return report

        # 스코어 정보
        score_timestamp = self.monitor.get_file_timestamp()
        if score_timestamp:
            lines.append(f"스코어 시간: {score_timestamp.strftime('%H:%M')}")

        # 시장 상황 정보 (Market Regime)
        market_regime = results.get('market_regime', {})
        if market_regime:
            kospi = market_regime.get('kospi', {})
            kosdaq = market_regime.get('kosdaq', {})
            lines.append("")
            lines.append("-" * 40)
            lines.append("시장 상황 (Market Regime)")
            lines.append("-" * 40)
            lines.append(f"  KOSPI: {kospi.get('trend', 'N/A'):8s} "
                        f"(MA20: {kospi.get('ma20', 0):,.0f}, MA60: {kospi.get('ma60', 0):,.0f})")
            lines.append(f"  KOSDAQ: {kosdaq.get('trend', 'N/A'):8s} "
                        f"(MA20: {kosdaq.get('ma20', 0):,.0f}, MA60: {kosdaq.get('ma60', 0):,.0f})")
            if not market_regime.get('can_trade', True):
                lines.append(f"  ⚠️ {market_regime.get('reason', '')}")
        lines.append("")

        # 사용자별 결과
        users_data = results.get('users', {})
        total_exits = 0
        total_entries = 0
        total_exit_pnl = 0

        for user_id, user_result in users_data.items():
            lines.append(f"[User {user_id}]")

            # 청산 결과
            exits = user_result.get('exits', [])
            if exits:
                lines.append(f"  청산: {len(exits)}건")
                for ex in exits:
                    pnl_rate = ex.get('pnl_rate', 0)
                    pnl_sign = "+" if pnl_rate >= 0 else ""
                    lines.append(f"    - {ex.get('stock_code')} {ex.get('stock_name', ''):10s} "
                               f"@{ex.get('exit_price', 0):,}원 ({ex.get('exit_reason')}) "
                               f"{pnl_sign}{pnl_rate:.2f}%")
                    total_exit_pnl += (ex.get('exit_price', 0) - ex.get('entry_price', 0)) * ex.get('quantity', 0)
                total_exits += len(exits)
            else:
                lines.append("  청산: 없음")

            # 매수 결과
            entries = user_result.get('entries', [])
            if entries:
                executed = [e for e in entries if e.get('executed')]
                lines.append(f"  매수: {len(executed)}건")
                for en in executed:
                    lines.append(f"    - {en.get('stock_code')} {en.get('stock_name', ''):10s} "
                               f"{en.get('quantity')}주 @{en.get('price', 0):,}원 "
                               f"({en.get('strategy')}, 신뢰도={en.get('confidence', 0):.2f})")
                total_entries += len(executed)
            else:
                lines.append("  매수: 없음")

            # 에러
            if 'error' in user_result:
                lines.append(f"  에러: {user_result['error']}")

            lines.append("")

        # 요약
        lines.append("-" * 40)
        lines.append("요약")
        lines.append("-" * 40)
        lines.append(f"  총 청산: {total_exits}건")
        lines.append(f"  총 매수: {total_entries}건")
        if total_exits > 0:
            lines.append(f"  청산 손익: {total_exit_pnl:+,}원")
        lines.append("")

        # 현재 포지션 현황
        lines.append("-" * 40)
        lines.append("현재 오픈 포지션")
        lines.append("-" * 40)

        for user_id in users_data.keys():
            positions = self.pm.get_open_positions(int(user_id))
            if positions:
                lines.append(f"[User {user_id}] {len(positions)}개 포지션")
                for pos in positions[:5]:  # 최대 5개만 표시
                    lines.append(f"  - {pos['stock_code']} {pos['stock_name']:10s} "
                               f"{pos['quantity']}주 @{pos['entry_price']:,}원 "
                               f"({pos['strategy']})")
                if len(positions) > 5:
                    lines.append(f"  ... 외 {len(positions) - 5}개")
            else:
                lines.append(f"[User {user_id}] 없음")

        lines.append("")
        lines.append("=" * 60)

        report = "\n".join(lines)

        # 파일 저장
        if save_to_file:
            self._save_report(report, now)

        return report

    def _save_report(self, report: str, timestamp: datetime):
        """리포트 파일 저장"""
        report_dir = Path(__file__).parent / "output" / "intraday_reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        # 파일명: intraday_report_YYYYMMDD_HHMM.txt
        filename = f"intraday_report_{timestamp.strftime('%Y%m%d_%H%M')}.txt"
        filepath = report_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)

        self.log(f"리포트 저장: {filepath}")

        # 일별 요약 파일에도 추가
        daily_file = report_dir / f"daily_{timestamp.strftime('%Y%m%d')}.txt"
        with open(daily_file, 'a', encoding='utf-8') as f:
            f.write(report)
            f.write("\n\n")

    def get_daily_summary(self, date: str = None) -> dict:
        """
        일별 거래 요약

        Args:
            date: 날짜 (YYYYMMDD). None이면 오늘

        Returns:
            일별 요약 딕셔너리
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')

        date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

        summary = {
            'date': date_str,
            'users': {}
        }

        with self.pm._get_connection() as conn:
            cursor = conn.cursor()

            # 오늘 오픈된 포지션
            cursor.execute("""
                SELECT user_id, strategy,
                       COUNT(*) as count,
                       SUM(entry_price * quantity) as total_amount
                FROM intraday_positions
                WHERE entry_time LIKE ?
                GROUP BY user_id, strategy
            """, (f"{date_str}%",))

            for row in cursor.fetchall():
                user_id = str(row['user_id'])
                if user_id not in summary['users']:
                    summary['users'][user_id] = {'entries': {}, 'exits': {}}
                summary['users'][user_id]['entries'][row['strategy']] = {
                    'count': row['count'],
                    'amount': row['total_amount']
                }

            # 오늘 청산된 포지션
            cursor.execute("""
                SELECT user_id, strategy, exit_reason,
                       COUNT(*) as count,
                       SUM(realized_pnl) as total_pnl,
                       AVG(realized_pnl_rate) as avg_pnl_rate
                FROM intraday_positions
                WHERE exit_time LIKE ? AND status = 'closed'
                GROUP BY user_id, strategy, exit_reason
            """, (f"{date_str}%",))

            for row in cursor.fetchall():
                user_id = str(row['user_id'])
                if user_id not in summary['users']:
                    summary['users'][user_id] = {'entries': {}, 'exits': {}}

                key = f"{row['strategy']}_{row['exit_reason']}"
                summary['users'][user_id]['exits'][key] = {
                    'count': row['count'],
                    'total_pnl': row['total_pnl'],
                    'avg_pnl_rate': row['avg_pnl_rate']
                }

        return summary

    def run_continuous(self, interval_minutes: int = 10):
        """
        연속 실행 (테스트용)

        Args:
            interval_minutes: 실행 간격 (분)
        """
        import time

        self.log("연속 실행 모드 시작")
        self.log(f"실행 간격: {interval_minutes}분")

        while True:
            try:
                result = self.run_once()
                # 리포트 생성
                report = self.generate_report(result)
                print(report)
            except Exception as e:
                self.log(f"실행 에러: {e}", 'ERROR')

            self.log(f"\n다음 실행까지 {interval_minutes}분 대기...")
            time.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(
        description='V1~V10 장중 스코어 기반 자동매매'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='시뮬레이션 모드 (실제 주문 없음)'
    )
    parser.add_argument(
        '--user', '-u',
        type=int,
        default=None,
        help='특정 사용자 ID만 실행'
    )
    parser.add_argument(
        '--continuous', '-c',
        action='store_true',
        help='연속 실행 모드'
    )
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=10,
        help='연속 실행 간격 (분)'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='간단한 로그만 출력'
    )
    parser.add_argument(
        '--config', '-f',
        type=str,
        default=None,
        help='설정 파일 경로 (JSON)'
    )

    args = parser.parse_args()

    # 설정 로드
    config = DEFAULT_CONFIG.copy()
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                custom_config = json.load(f)
                config.update(custom_config)
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")

    # 트레이더 생성
    trader = IntradayAutoTrader(
        config=config,
        dry_run=args.dry_run,
        verbose=not args.quiet
    )

    if args.dry_run:
        print("=" * 50)
        print("*** DRY-RUN 모드 ***")
        print("실제 주문이 실행되지 않습니다.")
        print("=" * 50)

    if args.continuous:
        trader.run_continuous(args.interval)
    else:
        result = trader.run_once(args.user)

        # 리포트 생성 및 출력
        report = trader.generate_report(result)
        print("\n" + report)


if __name__ == "__main__":
    main()
