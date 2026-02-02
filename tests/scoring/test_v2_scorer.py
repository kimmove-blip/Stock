"""
V2 스코어러 테스트

테스트 항목:
1. 역배열 0점 반환 검증
2. 60일 미만 데이터 None 반환
3. 정배열 가점 검증
4. RSI 구간별 점수 검증
5. 거래량 배수별 점수 검증
6. 60일 신고가 돌파 검증
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

# 프로젝트 임포트
from scoring import calculate_score_v2


class TestV2ScorerBasic:
    """V2 스코어러 기본 테스트"""

    def test_none_for_short_data(self, short_df):
        """60일 미만 데이터는 None 반환"""
        result = calculate_score_v2(short_df)
        assert result is None

    def test_none_for_none_input(self):
        """None 입력은 None 반환"""
        result = calculate_score_v2(None)
        assert result is None

    def test_none_for_empty_df(self):
        """빈 DataFrame은 None 반환"""
        result = calculate_score_v2(pd.DataFrame())
        assert result is None

    def test_returns_dict_structure(self, sample_ohlcv_df):
        """결과 딕셔너리 구조 검증"""
        result = calculate_score_v2(sample_ohlcv_df)

        assert result is not None
        assert 'score' in result
        assert 'trend_score' in result
        assert 'momentum_score' in result
        assert 'volume_score' in result
        assert 'signals' in result
        assert 'indicators' in result
        assert 'version' in result
        assert result['version'] == 'v2'


class TestV2ScorerReverseAlign:
    """V2 역배열 과락 테스트"""

    def test_reverse_align_returns_zero(self, reverse_aligned_df):
        """역배열 시 0점 반환"""
        result = calculate_score_v2(reverse_aligned_df)

        assert result is not None
        assert result['score'] == 0
        assert 'MA_REVERSE_ALIGNED' in result['signals']
        assert result['indicators'].get('ma_status') == 'reverse_aligned'

    def test_reverse_align_early_return(self, reverse_aligned_df):
        """역배열 시 추가 계산 없이 조기 반환"""
        result = calculate_score_v2(reverse_aligned_df)

        # 역배열 조기 반환 시 trend_score 등은 0
        assert result['trend_score'] == 0
        assert result['momentum_score'] == 0
        assert result['volume_score'] == 0


class TestV2ScorerTrend:
    """V2 추세 점수 테스트"""

    def test_aligned_ma_bonus(self, sample_ohlcv_df):
        """정배열 시 MA_ALIGNED 신호 및 가점"""
        result = calculate_score_v2(sample_ohlcv_df)

        # 상승 추세 데이터이므로 정배열 가능성 높음
        if 'MA_ALIGNED' in result['signals']:
            # 정배열이면 최소 5점
            assert result['trend_score'] >= 5

    def test_trend_score_max_30(self, sample_ohlcv_df):
        """추세 점수 최대 30점"""
        result = calculate_score_v2(sample_ohlcv_df)
        assert result['trend_score'] <= 30

    def test_sma20_slope_signals(self, sample_ohlcv_df):
        """20일선 기울기 신호"""
        result = calculate_score_v2(sample_ohlcv_df)

        slope_signals = ['MA_20_VERY_STEEP', 'MA_20_STEEP', 'MA_20_RISING']
        has_slope_signal = any(s in result['signals'] for s in slope_signals)

        # 상승 추세 데이터이므로 기울기 신호 있을 수 있음
        if 'sma20_slope' in result['indicators']:
            slope = result['indicators']['sma20_slope']
            if slope >= 0.5:
                assert has_slope_signal


class TestV2ScorerMomentum:
    """V2 모멘텀 점수 테스트"""

    def test_momentum_score_range(self, sample_ohlcv_df):
        """모멘텀 점수 범위 (-10 ~ 35)"""
        result = calculate_score_v2(sample_ohlcv_df)
        assert -10 <= result['momentum_score'] <= 35

    def test_rsi_falling_knife_penalty(self):
        """RSI 30 미만 (떨어지는 칼날) 감점"""
        # RSI가 낮은 하락 데이터 생성
        np.random.seed(42)
        n_days = 100

        # 급락 데이터
        base_price = 10000
        prices = [base_price]
        for i in range(1, n_days):
            change = np.random.uniform(-0.03, 0.01)  # 하락 편향
            prices.append(prices[-1] * (1 + change))

        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        df = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.98 for p in prices],
            'Close': prices,
            'Volume': [100000] * n_days,
        }, index=dates)

        result = calculate_score_v2(df)

        if result and 'rsi' in result['indicators']:
            rsi = result['indicators']['rsi']
            if rsi < 30:
                assert 'RSI_FALLING_KNIFE' in result['signals']

    def test_60d_high_breakout(self, breakout_df):
        """60일 신고가 돌파 검증"""
        result = calculate_score_v2(breakout_df)

        assert result is not None
        # 돌파 데이터이므로 관련 신호 있어야 함
        breakout_signals = ['BREAKOUT_60D_HIGH', 'NEAR_60D_HIGH', 'CLOSE_TO_60D_HIGH']
        has_breakout = any(s in result['signals'] for s in breakout_signals)
        assert has_breakout


class TestV2ScorerVolume:
    """V2 수급 점수 테스트"""

    def test_volume_score_range(self, sample_ohlcv_df):
        """수급 점수 범위 (-10 ~ 35)"""
        result = calculate_score_v2(sample_ohlcv_df)
        assert -10 <= result['volume_score'] <= 35

    def test_volume_explosion_signal(self, high_volume_df):
        """거래량 5배 급증 신호"""
        result = calculate_score_v2(high_volume_df)

        assert result is not None
        # 거래량 급증 신호
        volume_signals = ['VOLUME_EXPLOSION', 'VOLUME_SURGE_3X', 'VOLUME_HIGH']
        has_volume_signal = any(s in result['signals'] for s in volume_signals)
        assert has_volume_signal

    def test_low_liquidity_penalty(self):
        """거래대금 10억 미만 감점"""
        np.random.seed(42)
        n_days = 100

        # 저유동성 데이터 (거래대금 10억 미만)
        prices = [1000] * n_days  # 저가
        volumes = [10000] * n_days  # 저거래량

        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        df = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': volumes,
        }, index=dates)

        result = calculate_score_v2(df)

        if result and result['indicators'].get('trading_value', 0) < 1_000_000_000:
            assert 'LOW_LIQUIDITY' in result['signals']


class TestV2ScorerTotal:
    """V2 종합 점수 테스트"""

    def test_total_score_range(self, sample_ohlcv_df):
        """최종 점수 범위 (0 ~ 100)"""
        result = calculate_score_v2(sample_ohlcv_df)
        assert 0 <= result['score'] <= 100

    def test_score_equals_sum(self, sample_ohlcv_df):
        """최종 점수 = 추세 + 모멘텀 + 수급 (클리핑 후)"""
        result = calculate_score_v2(sample_ohlcv_df)

        raw_sum = (
            result['trend_score'] +
            result['momentum_score'] +
            result['volume_score']
        )

        # 0~100 클리핑 적용
        expected = max(0, min(100, raw_sum))
        assert result['score'] == expected

    def test_indicators_present(self, sample_ohlcv_df):
        """필수 지표 존재 확인"""
        result = calculate_score_v2(sample_ohlcv_df)

        required_indicators = ['close', 'change_pct', 'volume', 'trading_value']
        for ind in required_indicators:
            assert ind in result['indicators'], f"Missing indicator: {ind}"


class TestV2ScorerEdgeCases:
    """V2 엣지 케이스 테스트"""

    def test_all_same_prices(self):
        """모든 가격이 동일한 경우"""
        n_days = 100
        prices = [10000] * n_days
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        df = pd.DataFrame({
            'Open': prices,
            'High': prices,
            'Low': prices,
            'Close': prices,
            'Volume': [100000] * n_days,
        }, index=dates)

        result = calculate_score_v2(df)

        # 에러 없이 결과 반환
        assert result is not None
        assert 0 <= result['score'] <= 100

    def test_zero_volume(self):
        """거래량이 0인 경우"""
        np.random.seed(42)
        n_days = 100
        prices = [10000 + i * 10 for i in range(n_days)]
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        df = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': [0] * n_days,
        }, index=dates)

        result = calculate_score_v2(df)

        # 에러 없이 결과 반환
        assert result is not None

    def test_exactly_60_days(self):
        """정확히 60일 데이터"""
        np.random.seed(42)
        n_days = 60
        prices = [10000 + np.random.uniform(-100, 100) for _ in range(n_days)]
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        df = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': [100000] * n_days,
        }, index=dates)

        result = calculate_score_v2(df)

        # 60일은 유효
        assert result is not None
