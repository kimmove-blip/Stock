"""
위험 관리 모듈
손절/익절, 포지션 관리, 거래 검증
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TradingLimits:
    """거래 한도 설정"""
    max_position_pct: float = 0.05       # 종목당 최대 포지션 비율 (5%)
    stop_loss_pct: float = -0.07         # 손절 비율 (-7%)
    take_profit_pct: float = None        # 익절 비율 (None=비활성화, 신호 기반 매도)
    max_daily_trades: int = 10           # 일일 최대 거래 횟수
    max_holdings: int = 10               # 최대 보유 종목 수
    max_hold_days: int = 10              # 최대 보유 기간 (일)
    min_buy_score: int = 80              # 최소 매수 점수
    min_hold_score: int = 40             # 최소 보유 점수 (이하 시 매도)
    min_volume_ratio: float = 1.0        # 최소 거래량 비율 (20일 평균 대비)


class RiskManager:
    """위험 관리자"""

    def __init__(self, limits: TradingLimits = None):
        """
        Args:
            limits: 거래 한도 설정
        """
        self.limits = limits or TradingLimits()
        self.daily_trade_count = 0
        self.last_trade_date = None

    def reset_daily_counter(self):
        """일일 거래 카운터 리셋"""
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.daily_trade_count = 0
            self.last_trade_date = today

    def increment_trade_count(self):
        """거래 카운터 증가"""
        self.reset_daily_counter()
        self.daily_trade_count += 1

    def can_trade(self) -> Tuple[bool, str]:
        """
        거래 가능 여부 확인

        Returns:
            (거래 가능 여부, 사유)
        """
        self.reset_daily_counter()

        if self.daily_trade_count >= self.limits.max_daily_trades:
            return False, f"일일 최대 거래 횟수 초과 ({self.limits.max_daily_trades}회)"

        return True, "거래 가능"

    def check_stop_loss(
        self,
        avg_price: int,
        current_price: int
    ) -> Tuple[bool, float]:
        """
        손절 여부 확인

        Args:
            avg_price: 평균 매수가
            current_price: 현재가

        Returns:
            (손절 필요 여부, 수익률)
        """
        if avg_price <= 0:
            return False, 0.0

        profit_rate = (current_price - avg_price) / avg_price

        if profit_rate <= self.limits.stop_loss_pct:
            return True, profit_rate

        return False, profit_rate

    def check_take_profit(
        self,
        avg_price: int,
        current_price: int
    ) -> Tuple[bool, float]:
        """
        익절 여부 확인

        Args:
            avg_price: 평균 매수가
            current_price: 현재가

        Returns:
            (익절 필요 여부, 수익률)
        """
        if avg_price <= 0:
            return False, 0.0

        profit_rate = (current_price - avg_price) / avg_price

        # 익절 비활성화 시 (None) 항상 False 반환
        if self.limits.take_profit_pct is None:
            return False, profit_rate

        if profit_rate >= self.limits.take_profit_pct:
            return True, profit_rate

        return False, profit_rate

    def check_max_hold_days(
        self,
        buy_date: datetime,
        current_date: datetime = None
    ) -> Tuple[bool, int]:
        """
        최대 보유 기간 초과 여부 확인

        Args:
            buy_date: 매수일
            current_date: 현재일 (기본: 오늘)

        Returns:
            (기간 초과 여부, 보유 일수)
        """
        if current_date is None:
            current_date = datetime.now()

        hold_days = (current_date - buy_date).days

        if hold_days >= self.limits.max_hold_days:
            return True, hold_days

        return False, hold_days

    def calculate_position_size(
        self,
        total_assets: int,
        current_price: int
    ) -> int:
        """
        포지션 크기 계산

        Args:
            total_assets: 총 자산
            current_price: 현재가

        Returns:
            매수 가능 수량
        """
        if current_price <= 0:
            return 0

        max_investment = int(total_assets * self.limits.max_position_pct)
        quantity = max_investment // current_price

        return quantity

    def calculate_investment_amount(self, total_assets: int) -> int:
        """
        종목당 투자 금액 계산

        Args:
            total_assets: 총 자산

        Returns:
            종목당 투자 금액
        """
        return int(total_assets * self.limits.max_position_pct)

    def validate_buy_signal(
        self,
        stock_data: Dict,
        current_holdings_count: int
    ) -> Tuple[bool, str]:
        """
        매수 신호 검증

        Args:
            stock_data: 종목 데이터 (score, signals, volume_ratio 등)
            current_holdings_count: 현재 보유 종목 수

        Returns:
            (매수 가능 여부, 사유)
        """
        # 보유 종목 수 체크
        if current_holdings_count >= self.limits.max_holdings:
            return False, f"최대 보유 종목 수 초과 ({self.limits.max_holdings}개)"

        # 점수 체크
        score = stock_data.get("score", 0)
        if score < self.limits.min_buy_score:
            return False, f"매수 점수 미달 ({score} < {self.limits.min_buy_score})"

        # 거래량 체크
        volume_ratio = stock_data.get("volume_ratio", 0)
        if volume_ratio < self.limits.min_volume_ratio:
            return False, f"거래량 부족 (평균 대비 {volume_ratio:.1f}배)"

        return True, "매수 가능"

    def check_score_drop(self, current_score: int) -> Tuple[bool, int]:
        """
        점수 하락 여부 확인 (래치 전략: 40점 미만 시 극단적 모멘텀 붕괴)

        Args:
            current_score: 현재 점수

        Returns:
            (매도 필요 여부, 현재 점수)
        """
        if current_score < self.limits.min_hold_score:  # 40점 미만
            return True, current_score
        return False, current_score

    def check_ma_breach(self, current_price: float, sma20: float) -> Tuple[bool, str]:
        """
        20일 이동평균선 이탈 여부 확인 (래치 전략)

        Args:
            current_price: 현재가
            sma20: 20일 이동평균선

        Returns:
            (매도 필요 여부, 사유)
        """
        if sma20 <= 0:
            return False, ""

        if current_price < sma20:
            breach_pct = (current_price - sma20) / sma20 * 100
            return True, f"20일선 이탈 ({breach_pct:.1f}%)"
        return False, ""

    def check_sell_signals(self, signals: List[str], current_score: int = None) -> Tuple[bool, List[str]]:
        """
        매도 신호 체크

        Args:
            signals: 현재 신호 리스트
            current_score: 현재 점수 (있으면 점수 기반 필터링)

        Returns:
            (매도 필요 여부, 매도 사유 리스트)
        """
        sell_signals = []

        # 강력 매도 신호 목록
        strong_sell_signals = {
            "RSI_OVERBOUGHT": "RSI 과매수 (>80)",
            "MACD_DEAD_CROSS": "MACD 데드크로스",
            "DEAD_CROSS_5_20": "단기 데드크로스 (5/20일)",
            "DEAD_CROSS_20_60": "중기 데드크로스 (20/60일)",
            "BB_UPPER_BREAK": "볼린저밴드 상단 이탈",
            "BEARISH_ENGULFING": "하락장악형",
            "EVENING_STAR": "저녁별형",
            "MA_REVERSE_ALIGNED": "이평선 역배열",
            "SUPERTREND_SELL": "슈퍼트렌드 매도전환",
            "PSAR_SELL_SIGNAL": "PSAR 매도신호",
        }

        for signal in signals:
            if signal in strong_sell_signals:
                sell_signals.append(strong_sell_signals[signal])

        # 점수 기반 필터링: 70점 이상이면 매도 신호 무시
        # (손절, 점수하락, 보유기간 초과는 별도 체크되므로 여기서는 신호만 무시)
        if current_score is not None and current_score >= 70:
            return False, sell_signals  # 신호 있어도 매도 안 함

        # 3개 이상 매도 신호 발생 시 매도
        if len(sell_signals) >= 3:
            return True, sell_signals

        return False, sell_signals

    def evaluate_holdings(
        self,
        holdings: List[Dict],
        current_prices: Dict[str, int],
        current_signals: Dict[str, List[str]] = None,
        buy_dates: Dict[str, datetime] = None,
        current_scores: Dict[str, int] = None,
        sma20_values: Dict[str, float] = None
    ) -> List[Dict]:
        """
        보유 종목 평가 및 매도 대상 선정 (래치 전략 적용)

        Args:
            holdings: 보유 종목 리스트
            current_prices: 종목별 현재가 {stock_code: price}
            current_signals: 종목별 현재 신호 {stock_code: [signals]}
            buy_dates: 종목별 매수일 {stock_code: datetime}
            current_scores: 종목별 현재 점수 {stock_code: score}
            sma20_values: 종목별 20일 이평선 {stock_code: sma20} (래치 전략용)

        Returns:
            매도 대상 종목 리스트 (사유 포함)
        """
        sell_list = []

        for holding in holdings:
            stock_code = holding.get("stock_code")
            stock_name = holding.get("stock_name", stock_code)
            avg_price = holding.get("avg_price", 0)
            quantity = holding.get("quantity", 0)
            current_price = current_prices.get(stock_code, holding.get("current_price", 0))

            sell_reasons = []

            # 1. 손절 체크 (최우선)
            is_stop_loss, profit_rate = self.check_stop_loss(avg_price, current_price)
            if is_stop_loss:
                sell_reasons.append(f"손절 ({profit_rate*100:.1f}%)")

            # 2. 익절 체크 (설정된 경우에만)
            is_take_profit, profit_rate = self.check_take_profit(avg_price, current_price)
            if is_take_profit:
                sell_reasons.append(f"익절 ({profit_rate*100:.1f}%)")

            # 3. 최대 보유 기간 체크 - 래치 전략에서는 비활성화
            # (추세가 끝날 때까지 보유, 시간 기반 청산 안 함)
            # if buy_dates and stock_code in buy_dates:
            #     is_expired, hold_days = self.check_max_hold_days(buy_dates[stock_code])
            #     if is_expired:
            #         sell_reasons.append(f"보유기간 초과 ({hold_days}일)")

            # === 래치 전략 매도 조건 ===

            # 4. 극단적 점수 하락 체크 (40점 미만)
            if current_scores and stock_code in current_scores:
                score = current_scores[stock_code]
                is_score_drop, current_score = self.check_score_drop(score)
                if is_score_drop:
                    sell_reasons.append(f"극단적 점수 하락 ({current_score}점)")

            # 5. 20일선 이탈 체크 (래치 전략 핵심)
            if sma20_values and stock_code in sma20_values:
                sma20 = sma20_values[stock_code]
                is_ma_breach, ma_reason = self.check_ma_breach(current_price, sma20)
                if is_ma_breach:
                    sell_reasons.append(ma_reason)

            # 6. 매도 신호 체크 (점수 70점 이상이면 무시)
            # 래치 전략에서는 신호 기반 매도를 줄이고, 위의 조건들에 집중
            if current_signals and stock_code in current_signals:
                signals = current_signals[stock_code]
                score = current_scores.get(stock_code, 50) if current_scores else 50
                should_sell, signal_reasons = self.check_sell_signals(signals, score)
                if should_sell:
                    sell_reasons.extend(signal_reasons)

            # 매도 대상 추가
            if sell_reasons:
                sell_list.append({
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "quantity": quantity,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "market": holding.get("market", "KOSDAQ"),
                    "profit_rate": (current_price - avg_price) / avg_price if avg_price > 0 else 0,
                    "sell_reasons": sell_reasons
                })

        return sell_list

    def filter_buy_candidates(
        self,
        candidates: List[Dict],
        current_holdings: List[Dict],
        today_blacklist: set = None
    ) -> List[Dict]:
        """
        매수 후보 필터링

        Args:
            candidates: 매수 후보 종목 리스트
            current_holdings: 현재 보유 종목 리스트
            today_blacklist: 당일 거래한 종목 코드 집합 (왕복매매 방지)

        Returns:
            필터링된 매수 후보 리스트
        """
        # 이미 보유 중인 종목 코드
        holding_codes = {h.get("stock_code") for h in current_holdings}

        # 당일 블랙리스트 (없으면 빈 집합)
        blacklist = today_blacklist or set()

        # 남은 매수 가능 종목 수
        remaining_slots = self.limits.max_holdings - len(current_holdings)

        if remaining_slots <= 0:
            return []

        filtered = []
        for candidate in candidates:
            stock_code = candidate.get("stock_code")

            # 이미 보유 중인 종목 제외
            if stock_code in holding_codes:
                continue

            # 당일 이미 거래한 종목 제외 (왕복매매 방지)
            if stock_code in blacklist:
                print(f"  [{candidate.get('stock_name', stock_code)}] 당일 거래 이력 - 재매수 제외")
                continue

            # 매수 조건 검증
            is_valid, reason = self.validate_buy_signal(
                candidate, len(current_holdings) + len(filtered)
            )

            if is_valid:
                filtered.append(candidate)

            # 남은 슬롯만큼만 선택
            if len(filtered) >= remaining_slots:
                break

        return filtered

    def get_risk_summary(
        self,
        holdings: List[Dict],
        total_assets: int
    ) -> Dict:
        """
        리스크 요약 정보

        Args:
            holdings: 보유 종목 리스트
            total_assets: 총 자산

        Returns:
            리스크 요약 딕셔너리
        """
        total_invested = sum(
            h.get("avg_price", 0) * h.get("quantity", 0)
            for h in holdings
        )
        total_eval = sum(
            h.get("current_price", 0) * h.get("quantity", 0)
            for h in holdings
        )
        total_profit = total_eval - total_invested

        return {
            "holdings_count": len(holdings),
            "max_holdings": self.limits.max_holdings,
            "total_invested": total_invested,
            "total_eval": total_eval,
            "total_profit": total_profit,
            "profit_rate": total_profit / total_invested if total_invested > 0 else 0,
            "cash_ratio": (total_assets - total_invested) / total_assets if total_assets > 0 else 0,
            "daily_trades_remaining": self.limits.max_daily_trades - self.daily_trade_count,
        }
