"""
RiskManager 테스트

테스트 항목:
1. 손절 조건 검증
2. 익절 조건 검증
3. 최대 보유종목 제한 검증
4. 일일 거래 횟수 제한 검증
5. 매수 신호 검증
6. 보유 종목 평가
"""

import pytest
from datetime import datetime, timedelta

from trading.risk_manager import RiskManager, TradingLimits


class TestTradingLimits:
    """TradingLimits 테스트"""

    def test_default_values(self):
        """기본값 확인"""
        limits = TradingLimits()

        assert limits.max_per_stock == 200000
        assert limits.stop_loss_pct == -0.07
        assert limits.take_profit_pct is None
        assert limits.max_daily_trades == 10
        assert limits.max_holdings == 20
        assert limits.min_buy_score == 80
        assert limits.min_hold_score == 40
        assert limits.min_volume_ratio == 1.0

    def test_custom_values(self):
        """커스텀 값 설정"""
        limits = TradingLimits(
            max_per_stock=500000,
            stop_loss_pct=-0.10,
            take_profit_pct=0.20,
            max_holdings=30,
        )

        assert limits.max_per_stock == 500000
        assert limits.stop_loss_pct == -0.10
        assert limits.take_profit_pct == 0.20
        assert limits.max_holdings == 30


class TestRiskManagerStopLoss:
    """RiskManager 손절 테스트"""

    def test_stop_loss_triggered(self, trading_limits):
        """손절 조건 충족 시 True"""
        rm = RiskManager(trading_limits)

        # -7% 손절 설정, -10% 하락
        avg_price = 10000
        current_price = 9000  # -10%

        is_stop, profit_rate = rm.check_stop_loss(avg_price, current_price)

        assert is_stop is True
        assert profit_rate == pytest.approx(-0.10, rel=0.01)

    def test_stop_loss_not_triggered(self, trading_limits):
        """손절 조건 미충족 시 False"""
        rm = RiskManager(trading_limits)

        # -7% 손절 설정, -5% 하락
        avg_price = 10000
        current_price = 9500  # -5%

        is_stop, profit_rate = rm.check_stop_loss(avg_price, current_price)

        assert is_stop is False
        assert profit_rate == pytest.approx(-0.05, rel=0.01)

    def test_stop_loss_at_boundary(self, trading_limits):
        """손절 경계값 테스트"""
        rm = RiskManager(trading_limits)

        avg_price = 10000
        current_price = 9300  # 정확히 -7%

        is_stop, profit_rate = rm.check_stop_loss(avg_price, current_price)

        assert is_stop is True  # 경계값 포함
        assert profit_rate == pytest.approx(-0.07, rel=0.01)

    def test_stop_loss_zero_avg_price(self, trading_limits):
        """평균가 0일 때"""
        rm = RiskManager(trading_limits)

        is_stop, profit_rate = rm.check_stop_loss(0, 10000)

        assert is_stop is False
        assert profit_rate == 0.0

    def test_stop_loss_negative_price(self, trading_limits):
        """음수 가격일 때"""
        rm = RiskManager(trading_limits)

        is_stop, profit_rate = rm.check_stop_loss(-10000, 9000)

        assert is_stop is False


class TestRiskManagerTakeProfit:
    """RiskManager 익절 테스트"""

    def test_take_profit_triggered(self, trading_limits):
        """익절 조건 충족 시 True"""
        rm = RiskManager(trading_limits)

        # 15% 익절 설정, +20% 상승
        avg_price = 10000
        current_price = 12000  # +20%

        is_take, profit_rate = rm.check_take_profit(avg_price, current_price)

        assert is_take is True
        assert profit_rate == pytest.approx(0.20, rel=0.01)

    def test_take_profit_not_triggered(self, trading_limits):
        """익절 조건 미충족 시 False"""
        rm = RiskManager(trading_limits)

        # 15% 익절 설정, +10% 상승
        avg_price = 10000
        current_price = 11000  # +10%

        is_take, profit_rate = rm.check_take_profit(avg_price, current_price)

        assert is_take is False
        assert profit_rate == pytest.approx(0.10, rel=0.01)

    def test_take_profit_disabled(self):
        """익절 비활성화 (None)"""
        limits = TradingLimits(take_profit_pct=None)
        rm = RiskManager(limits)

        avg_price = 10000
        current_price = 15000  # +50%

        is_take, profit_rate = rm.check_take_profit(avg_price, current_price)

        assert is_take is False  # 비활성화 시 항상 False
        assert profit_rate == pytest.approx(0.50, rel=0.01)


class TestRiskManagerCanTrade:
    """RiskManager 거래 가능 여부 테스트"""

    def test_can_trade_initial(self, trading_limits):
        """초기 상태에서 거래 가능"""
        rm = RiskManager(trading_limits)

        can, reason = rm.can_trade()

        assert can is True
        assert reason == "거래 가능"

    def test_daily_limit_reached(self, trading_limits):
        """일일 거래 횟수 초과"""
        rm = RiskManager(trading_limits)

        # 10회 거래 실행
        for _ in range(trading_limits.max_daily_trades):
            rm.increment_trade_count()

        can, reason = rm.can_trade()

        assert can is False
        assert "일일 최대 거래 횟수" in reason

    def test_daily_counter_reset(self, trading_limits):
        """일자 변경 시 카운터 리셋"""
        rm = RiskManager(trading_limits)

        # 어제 거래 10회
        rm.daily_trade_count = 10
        rm.last_trade_date = datetime.now().date() - timedelta(days=1)

        # 오늘 첫 거래
        rm.reset_daily_counter()

        assert rm.daily_trade_count == 0


class TestRiskManagerValidateBuy:
    """RiskManager 매수 신호 검증 테스트"""

    def test_valid_buy_signal(self, trading_limits, buy_candidates):
        """유효한 매수 신호"""
        rm = RiskManager(trading_limits)

        stock_data = buy_candidates[0]  # score=85, volume_ratio=2.5
        current_holdings = 5

        is_valid, reason = rm.validate_buy_signal(stock_data, current_holdings)

        assert is_valid is True
        assert reason == "매수 가능"

    def test_max_holdings_exceeded(self, trading_limits, buy_candidates):
        """최대 보유종목 초과"""
        rm = RiskManager(trading_limits)

        stock_data = buy_candidates[0]
        current_holdings = trading_limits.max_holdings  # 이미 20개 보유

        is_valid, reason = rm.validate_buy_signal(stock_data, current_holdings)

        assert is_valid is False
        assert "최대 보유 종목 수 초과" in reason

    def test_low_score_rejected(self, trading_limits, buy_candidates):
        """낮은 점수 거부"""
        rm = RiskManager(trading_limits)

        stock_data = buy_candidates[3]  # score=55
        current_holdings = 5

        is_valid, reason = rm.validate_buy_signal(stock_data, current_holdings)

        assert is_valid is False
        assert "매수 점수 미달" in reason

    def test_low_volume_rejected(self, trading_limits):
        """낮은 거래량 거부"""
        rm = RiskManager(trading_limits)

        stock_data = {
            "score": 90,
            "volume_ratio": 0.5,  # 1.0 미만
        }
        current_holdings = 5

        is_valid, reason = rm.validate_buy_signal(stock_data, current_holdings)

        assert is_valid is False
        assert "거래량 부족" in reason


class TestRiskManagerScoreDrop:
    """RiskManager 점수 하락 테스트"""

    def test_score_drop_triggered(self, trading_limits):
        """극단적 점수 하락 감지"""
        rm = RiskManager(trading_limits)

        # min_hold_score=40, 현재 점수=35
        should_sell, score = rm.check_score_drop(35)

        assert should_sell is True
        assert score == 35

    def test_score_drop_not_triggered(self, trading_limits):
        """점수 유지"""
        rm = RiskManager(trading_limits)

        should_sell, score = rm.check_score_drop(50)

        assert should_sell is False
        assert score == 50

    def test_score_drop_at_boundary(self, trading_limits):
        """경계값 테스트"""
        rm = RiskManager(trading_limits)

        # min_hold_score=40
        should_sell, score = rm.check_score_drop(40)

        assert should_sell is True  # 40 이하면 매도


class TestRiskManagerMABreach:
    """RiskManager 이평선 이탈 테스트"""

    def test_ma_breach_detected(self, trading_limits):
        """20일선 이탈 감지"""
        rm = RiskManager(trading_limits)

        current_price = 9500
        sma20 = 10000

        is_breach, reason = rm.check_ma_breach(current_price, sma20)

        assert is_breach is True
        assert "20일선 이탈" in reason

    def test_ma_above(self, trading_limits):
        """20일선 위 유지"""
        rm = RiskManager(trading_limits)

        current_price = 10500
        sma20 = 10000

        is_breach, reason = rm.check_ma_breach(current_price, sma20)

        assert is_breach is False
        assert reason == ""

    def test_ma_zero(self, trading_limits):
        """SMA20이 0일 때"""
        rm = RiskManager(trading_limits)

        is_breach, reason = rm.check_ma_breach(10000, 0)

        assert is_breach is False


class TestRiskManagerEvaluateHoldings:
    """RiskManager 보유 종목 평가 테스트"""

    def test_evaluate_stop_loss(self, trading_limits, stop_loss_holding):
        """손절 대상 식별"""
        rm = RiskManager(trading_limits)

        holdings = [stop_loss_holding]
        current_prices = {"000000": stop_loss_holding["current_price"]}

        sell_list = rm.evaluate_holdings(holdings, current_prices)

        assert len(sell_list) == 1
        assert any("손절" in r for r in sell_list[0]["sell_reasons"])

    def test_evaluate_score_drop(self, trading_limits, sample_holdings):
        """점수 하락 대상 식별"""
        rm = RiskManager(trading_limits)

        holdings = sample_holdings
        current_prices = {h["stock_code"]: h["current_price"] for h in holdings}
        current_scores = {
            "005930": 60,
            "035420": 30,  # 점수 하락
            "247540": 50,
        }

        sell_list = rm.evaluate_holdings(
            holdings, current_prices, current_scores=current_scores
        )

        # 035420이 매도 대상
        sold_codes = [s["stock_code"] for s in sell_list]
        assert "035420" in sold_codes

    def test_evaluate_multiple_reasons(self, trading_limits):
        """복수 매도 사유"""
        rm = RiskManager(trading_limits)

        holdings = [{
            "stock_code": "TEST01",
            "stock_name": "테스트종목",
            "quantity": 10,
            "avg_price": 10000,
            "current_price": 8500,  # -15% (손절)
            "market": "KOSDAQ",
        }]
        current_prices = {"TEST01": 8500}
        current_scores = {"TEST01": 30}  # 점수 하락
        sma20_values = {"TEST01": 9500}  # 20일선 이탈

        sell_list = rm.evaluate_holdings(
            holdings, current_prices,
            current_scores=current_scores,
            sma20_values=sma20_values
        )

        assert len(sell_list) == 1
        # 손절, 점수하락, 이평선 이탈 중 일부 발생
        assert len(sell_list[0]["sell_reasons"]) >= 1


class TestRiskManagerFilterCandidates:
    """RiskManager 매수 후보 필터링 테스트"""

    def test_filter_basic(self, trading_limits, buy_candidates, sample_holdings):
        """기본 필터링"""
        rm = RiskManager(trading_limits)

        filtered = rm.filter_buy_candidates(buy_candidates, sample_holdings)

        # 저점수 종목은 제외
        codes = [c["stock_code"] for c in filtered]
        assert "LOW001" not in codes

    def test_filter_already_holding(self, trading_limits, buy_candidates):
        """이미 보유 중인 종목 제외"""
        rm = RiskManager(trading_limits)

        # 373220을 이미 보유 중
        holdings = [{"stock_code": "373220", "stock_name": "LG에너지솔루션"}]

        filtered = rm.filter_buy_candidates(buy_candidates, holdings)

        codes = [c["stock_code"] for c in filtered]
        assert "373220" not in codes

    def test_filter_max_holdings_reached(self, trading_limits, buy_candidates):
        """최대 보유종목 도달 시 빈 리스트"""
        rm = RiskManager(trading_limits)

        # 이미 20개 보유
        holdings = [{"stock_code": f"CODE{i:03d}"} for i in range(20)]

        filtered = rm.filter_buy_candidates(buy_candidates, holdings)

        assert len(filtered) == 0

    def test_filter_blacklist(self, trading_limits, buy_candidates):
        """당일 블랙리스트 적용"""
        rm = RiskManager(trading_limits)

        holdings = []
        blacklist = {"373220", "000270"}  # 당일 거래한 종목

        filtered = rm.filter_buy_candidates(buy_candidates, holdings, blacklist)

        codes = [c["stock_code"] for c in filtered]
        assert "373220" not in codes
        assert "000270" not in codes


class TestRiskManagerPositionSize:
    """RiskManager 포지션 크기 계산 테스트"""

    def test_position_size_normal(self, trading_limits):
        """정상 포지션 크기"""
        rm = RiskManager(trading_limits)

        # 200,000원 / 10,000원 = 20주
        quantity = rm.calculate_position_size(10000)

        assert quantity == 20

    def test_position_size_high_price(self, trading_limits):
        """고가 주식"""
        rm = RiskManager(trading_limits)

        # 200,000원 / 500,000원 = 0주
        quantity = rm.calculate_position_size(500000)

        assert quantity == 0

    def test_position_size_zero_price(self, trading_limits):
        """가격 0일 때"""
        rm = RiskManager(trading_limits)

        quantity = rm.calculate_position_size(0)

        assert quantity == 0


class TestRiskManagerRiskSummary:
    """RiskManager 리스크 요약 테스트"""

    def test_risk_summary(self, trading_limits, sample_holdings):
        """리스크 요약 정보"""
        rm = RiskManager(trading_limits)

        total_assets = 10_000_000
        summary = rm.get_risk_summary(sample_holdings, total_assets)

        assert "holdings_count" in summary
        assert "max_holdings" in summary
        assert "total_invested" in summary
        assert "total_profit" in summary
        assert "profit_rate" in summary
        assert "cash_ratio" in summary
        assert summary["holdings_count"] == 3
        assert summary["max_holdings"] == trading_limits.max_holdings
