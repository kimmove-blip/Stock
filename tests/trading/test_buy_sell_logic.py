"""
trading/buy_sell_logic.py 테스트

매수/매도 전략 함수 단위 테스트
"""

import pytest
from trading.buy_sell_logic import (
    parse_condition,
    evaluate_conditions,
    check_hold_condition,
    should_buy_advanced,
    get_change_limit_by_marcap,
)


class TestParseCondition:
    """조건 문자열 파싱 테스트"""

    def test_simple_condition(self):
        """단일 조건 파싱"""
        result = parse_condition("V2>=60")
        assert len(result) == 1
        assert result[0]['score'] == 'v2'
        assert result[0]['op'] == '>='
        assert result[0]['value'] == 60

    def test_multiple_conditions_and(self):
        """AND 조건 파싱"""
        result = parse_condition("V2>=60 AND V4>=50")
        assert len(result) == 2
        assert result[0]['score'] == 'v2'
        assert result[1]['score'] == 'v4'
        assert result[1]['connector'] == 'AND'

    def test_delta_condition(self):
        """델타 조건 파싱"""
        result = parse_condition("V4_DELTA<=0")
        assert len(result) == 1
        assert result[0]['score'] == 'v4_delta'
        assert result[0]['op'] == '<='
        assert result[0]['value'] == 0

    def test_negative_value(self):
        """음수 값 파싱"""
        result = parse_condition("V4_DELTA>=-5")
        assert len(result) == 1
        assert result[0]['value'] == -5

    def test_empty_condition(self):
        """빈 조건 파싱"""
        result = parse_condition("")
        assert result == []

    def test_or_condition(self):
        """OR 조건 파싱"""
        result = parse_condition("V2>=70 OR V4>=60")
        assert len(result) == 2
        assert result[1]['connector'] == 'OR'


class TestEvaluateConditions:
    """조건 평가 테스트"""

    def test_single_condition_true(self):
        """단일 조건 충족"""
        conditions = [{'score': 'v2', 'op': '>=', 'value': 60, 'connector': 'AND'}]
        scores = {'v2': 70}
        assert evaluate_conditions(conditions, scores) is True

    def test_single_condition_false(self):
        """단일 조건 미충족"""
        conditions = [{'score': 'v2', 'op': '>=', 'value': 60, 'connector': 'AND'}]
        scores = {'v2': 50}
        assert evaluate_conditions(conditions, scores) is False

    def test_and_conditions(self):
        """AND 조건 평가"""
        conditions = [
            {'score': 'v2', 'op': '>=', 'value': 60, 'connector': 'AND'},
            {'score': 'v4', 'op': '>=', 'value': 50, 'connector': 'AND'},
        ]
        # 둘 다 충족
        assert evaluate_conditions(conditions, {'v2': 70, 'v4': 55}) is True
        # 하나만 충족
        assert evaluate_conditions(conditions, {'v2': 70, 'v4': 40}) is False

    def test_or_conditions(self):
        """OR 조건 평가"""
        conditions = [
            {'score': 'v2', 'op': '>=', 'value': 70, 'connector': 'AND'},
            {'score': 'v4', 'op': '>=', 'value': 60, 'connector': 'OR'},
        ]
        # 첫 번째만 충족
        assert evaluate_conditions(conditions, {'v2': 75, 'v4': 40}) is True
        # 두 번째만 충족
        assert evaluate_conditions(conditions, {'v2': 50, 'v4': 65}) is True
        # 둘 다 미충족
        assert evaluate_conditions(conditions, {'v2': 50, 'v4': 40}) is False

    def test_empty_conditions(self):
        """빈 조건"""
        assert evaluate_conditions([], {}) is False


class TestCheckHoldCondition:
    """매도/홀딩 판단 테스트"""

    def test_stop_loss(self):
        """손절 조건"""
        should_sell, reason = check_hold_condition({'v5': 80, 'v4': 60, 'v2': 70}, -5.0, stop_loss_rate=3.0)
        assert should_sell is True
        assert "손절" in reason

    def test_hold_v5_high(self):
        """V5 높으면 홀딩"""
        should_sell, reason = check_hold_condition({'v5': 75, 'v4': 30, 'v2': 40}, 2.0)
        assert should_sell is False
        assert "V5" in reason

    def test_hold_v4_high(self):
        """V4 높으면 홀딩"""
        should_sell, reason = check_hold_condition({'v5': 50, 'v4': 60, 'v2': 40}, 2.0)
        assert should_sell is False
        assert "V4" in reason

    def test_hold_v2_high(self):
        """V2 높으면 홀딩"""
        should_sell, reason = check_hold_condition({'v5': 50, 'v4': 40, 'v2': 65}, 2.0)
        assert should_sell is False
        assert "V2" in reason

    def test_sell_v4_low(self):
        """V4 낮으면 매도"""
        should_sell, reason = check_hold_condition({'v5': 50, 'v4': 35, 'v2': 55}, 2.0)
        assert should_sell is True
        assert "V4" in reason

    def test_sell_v2_v4_both_low(self):
        """V2, V4 둘 다 낮으면 매도"""
        should_sell, reason = check_hold_condition({'v5': 50, 'v4': 42, 'v2': 45}, 2.0)
        assert should_sell is True
        assert "V2" in reason and "V4" in reason


class TestShouldBuyAdvanced:
    """매수 조건 판단 테스트"""

    def test_morning_buy_success(self):
        """오전 매수 조건 충족"""
        scores = {'v2': 60, 'v4': 45}
        should_buy, reason = should_buy_advanced(scores, 10)
        assert should_buy is True
        assert "오전" in reason

    def test_morning_v2_too_low(self):
        """오전 V2 부족"""
        scores = {'v2': 50, 'v4': 45}
        should_buy, reason = should_buy_advanced(scores, 10)
        assert should_buy is False
        assert "V2" in reason

    def test_morning_v4_too_low(self):
        """오전 V4 부족"""
        scores = {'v2': 60, 'v4': 35}
        should_buy, reason = should_buy_advanced(scores, 10)
        assert should_buy is False
        assert "V4" in reason

    def test_afternoon_buy_success(self):
        """오후 매수 조건 충족"""
        scores = {'v2': 60, 'v4': 45, 'v4_delta': -2}
        should_buy, reason = should_buy_advanced(scores, 14)
        assert should_buy is True

    def test_afternoon_v4_delta_positive_reject(self):
        """오후 V4 델타 양수면 거부"""
        scores = {'v2': 70, 'v4': 50, 'v4_delta': 5}
        should_buy, reason = should_buy_advanced(scores, 14)
        assert should_buy is False
        assert "급등중" in reason


class TestGetChangeLimitByMarcap:
    """시총별 상승률 제한 테스트"""

    def test_large_cap(self):
        """대형주 (1조 이상)"""
        assert get_change_limit_by_marcap(2_000_000_000_000) == 5.0

    def test_mid_cap(self):
        """중형주 (3000억~1조)"""
        assert get_change_limit_by_marcap(500_000_000_000) == 10.0

    def test_small_cap(self):
        """소형주 (3000억 미만)"""
        assert get_change_limit_by_marcap(100_000_000_000) == 15.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
