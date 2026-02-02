"""
트레이딩 플로우 통합 테스트

테스트 항목:
1. BaseTrader 장 시간 체크
2. AutoModeTrader 매매 플로우
3. SemiAutoTrader 제안 플로우
4. 예외 처리 검증
"""

import pytest
from datetime import datetime, time
from unittest.mock import Mock, patch

from trading.execution import BaseTrader, AutoModeTrader, SemiAutoTrader, TradeResult
from trading.core.config import TradingConfig
from trading.core.exceptions import MarketClosedError


class MockTrader(BaseTrader):
    """테스트용 Mock 트레이더"""

    def run(self) -> TradeResult:
        return TradeResult(success=True, mode='mock')


class TestBaseTrader:
    """BaseTrader 테스트"""

    @pytest.fixture
    def trader(self):
        """테스트용 트레이더"""
        config = TradingConfig(
            max_per_stock=200000,
            max_holdings=20,
            stop_loss_pct=-0.10,
        )
        return MockTrader(config=config, dry_run=True)

    def test_market_hours_weekday(self, trader):
        """평일 장 시간 체크"""
        # 실제 datetime 사용하므로 현재 시간에 따라 결과가 달라짐
        can_trade, reason = trader.check_market_hours()
        # reason은 항상 문자열
        assert isinstance(reason, str)
        assert isinstance(can_trade, bool)

    def test_market_hours_weekend(self, trader):
        """주말 체크"""
        with patch('trading.execution.base_trader.datetime') as mock_dt:
            # 토요일
            mock_now = Mock()
            mock_now.weekday.return_value = 5
            mock_now.time.return_value = time(10, 0)
            mock_dt.now.return_value = mock_now

            can_trade, reason = trader.check_market_hours()
            assert can_trade is False
            assert "주말" in reason

    def test_reset_daily_state(self, trader):
        """일일 상태 리셋"""
        trader._today_traded.add('005930')
        trader._today_traded.add('035420')

        # 날짜가 바뀌면 리셋
        trader._last_reset_date = None
        trader.reset_daily_state()

        assert len(trader._today_traded) == 0

    def test_add_traded_stock(self, trader):
        """거래 종목 추가"""
        trader.add_traded_stock('005930')

        assert '005930' in trader._today_traded
        assert trader.is_traded_today('005930') is True
        assert trader.is_traded_today('035420') is False

    def test_calculate_position_size(self, trader):
        """포지션 크기 계산"""
        # 200,000원 / 10,000원 = 20주
        quantity = trader.calculate_position_size(10000)
        assert quantity == 20

        # 200,000원 / 50,000원 = 4주
        quantity = trader.calculate_position_size(50000)
        assert quantity == 4

        # 0원 가격
        quantity = trader.calculate_position_size(0)
        assert quantity == 0

    def test_get_tick_size(self, trader):
        """호가 단위"""
        assert trader.get_tick_size(500) == 1
        assert trader.get_tick_size(2000) == 5
        assert trader.get_tick_size(8000) == 10
        assert trader.get_tick_size(30000) == 50
        assert trader.get_tick_size(80000) == 100
        assert trader.get_tick_size(300000) == 500
        assert trader.get_tick_size(600000) == 1000

    def test_round_to_tick(self, trader):
        """호가 단위 반올림"""
        # 내림
        assert trader.round_to_tick(10025, round_down=True) == 10000
        # 올림
        assert trader.round_to_tick(10025, round_down=False) == 10050


class TestAutoModeTrader:
    """AutoModeTrader 테스트"""

    @pytest.fixture
    def auto_trader(self):
        """테스트용 AutoModeTrader"""
        config = TradingConfig(
            max_per_stock=200000,
            max_holdings=20,
            stop_loss_pct=-0.10,
            min_buy_score=70,
        )
        return AutoModeTrader(
            config=config,
            dry_run=True
        )

    def test_run_dry_run(self, auto_trader):
        """Dry run 모드 실행"""
        result = auto_trader.run(min_score=75)

        assert isinstance(result, TradeResult)
        assert result.mode == 'auto'
        # dry_run이므로 스코어 데이터 없으면 에러
        assert 'errors' in dir(result)

    def test_evaluate_conditions(self, auto_trader):
        """조건 평가"""
        scores = {'v1': 70, 'v2': 80, 'v4': 60, 'v5': 55}

        # AND 조건
        assert auto_trader._evaluate_conditions("V2>=70 AND V4>=50", scores) is True
        assert auto_trader._evaluate_conditions("V2>=70 AND V4>=70", scores) is False

        # OR 조건
        assert auto_trader._evaluate_conditions("V2>=90 OR V4>=50", scores) is True
        assert auto_trader._evaluate_conditions("V2>=90 OR V4>=70", scores) is False

        # 단일 조건
        assert auto_trader._evaluate_conditions("V2>=80", scores) is True
        assert auto_trader._evaluate_conditions("V2>=90", scores) is False

    def test_evaluate_conditions_operators(self, auto_trader):
        """조건 연산자 테스트"""
        scores = {'v2': 75}

        assert auto_trader._evaluate_conditions("V2>=75", scores) is True
        assert auto_trader._evaluate_conditions("V2>75", scores) is False
        assert auto_trader._evaluate_conditions("V2<=75", scores) is True
        assert auto_trader._evaluate_conditions("V2<75", scores) is False
        assert auto_trader._evaluate_conditions("V2=75", scores) is True


class TestSemiAutoTrader:
    """SemiAutoTrader 테스트"""

    @pytest.fixture
    def semi_trader(self):
        """테스트용 SemiAutoTrader"""
        config = TradingConfig(
            max_per_stock=200000,
            stop_loss_pct=-0.10,
            target_profit_pct=0.20,
            suggestion_expire_hours=24,
        )
        return SemiAutoTrader(
            config=config,
            dry_run=True
        )

    def test_run_dry_run(self, semi_trader):
        """Dry run 모드 실행"""
        result = semi_trader.run()

        assert isinstance(result, TradeResult)
        assert result.mode == 'semi-auto'


class TestTradeResult:
    """TradeResult 테스트"""

    def test_trade_result_creation(self):
        """TradeResult 생성"""
        result = TradeResult(
            success=True,
            mode='auto',
            buy_count=3,
            sell_count=2,
            buy_amount=600000,
            sell_amount=400000,
            realized_profit=15000,
        )

        assert result.success is True
        assert result.mode == 'auto'
        assert result.buy_count == 3
        assert result.sell_count == 2

    def test_trade_result_to_dict(self):
        """딕셔너리 변환"""
        result = TradeResult(
            success=True,
            mode='auto',
            buy_count=1,
        )

        d = result.to_dict()

        assert 'success' in d
        assert 'mode' in d
        assert 'buy_count' in d
        assert 'timestamp' in d


class TestTradingConfig:
    """TradingConfig 테스트"""

    def test_default_config(self):
        """기본 설정"""
        config = TradingConfig()

        assert config.is_virtual is True
        assert config.max_per_stock == 200000
        assert config.max_holdings == 20
        assert config.stop_loss_pct == -0.10

    def test_custom_config(self):
        """커스텀 설정"""
        config = TradingConfig(
            is_virtual=False,
            max_per_stock=500000,
            max_holdings=30,
            stop_loss_pct=-0.05,
        )

        assert config.is_virtual is False
        assert config.max_per_stock == 500000
        assert config.max_holdings == 30
        assert config.stop_loss_pct == -0.05

    def test_config_validate(self):
        """설정 유효성 검사"""
        # 유효한 설정
        config = TradingConfig()
        errors = config.validate()
        assert len(errors) == 0

        # 잘못된 설정
        config = TradingConfig(
            max_per_stock=-100,
            stop_loss_pct=0.5,
        )
        errors = config.validate()
        assert len(errors) > 0

    def test_config_to_dict(self):
        """딕셔너리 변환"""
        config = TradingConfig()
        d = config.to_dict()

        assert 'is_virtual' in d
        assert 'max_per_stock' in d
        assert 'stop_loss_pct' in d
