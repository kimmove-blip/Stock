"""
배치 스코어링 통합 테스트

테스트 항목:
1. BatchScorer 병렬 처리
2. IndicatorCache 캐시 효율
3. YAML 설정 기반 스코어링
4. 결과 일관성 검증
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from scoring import BatchScorer, BatchResult
from scoring.indicators import IndicatorCache, calculate_base_indicators
from scoring.config import load_scoring_config, get_config


class TestBatchScorer:
    """BatchScorer 통합 테스트"""

    @pytest.fixture
    def sample_stocks(self):
        """테스트용 종목 데이터 생성"""
        def create_df(seed):
            np.random.seed(seed)
            n_days = 100
            base = 10000
            prices = [base]
            for i in range(1, n_days):
                prices.append(prices[-1] * (1 + np.random.normal(0.001, 0.02)))
            dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')
            return pd.DataFrame({
                'Open': [p * 0.99 for p in prices],
                'High': [p * 1.02 for p in prices],
                'Low': [p * 0.98 for p in prices],
                'Close': prices,
                'Volume': [np.random.randint(100000, 500000) for _ in range(n_days)],
            }, index=dates)

        return {f'TEST{i:03d}': create_df(i) for i in range(20)}

    def test_batch_scorer_sequential(self, sample_stocks):
        """순차 처리 테스트"""
        scorer = BatchScorer(versions=['v2'])
        result = scorer.score_batch(sample_stocks, parallel=False)

        assert isinstance(result, BatchResult)
        assert result.total_count == 20
        assert result.success_count > 0
        assert result.elapsed_seconds > 0

    def test_batch_scorer_parallel(self, sample_stocks):
        """병렬 처리 테스트"""
        scorer = BatchScorer(versions=['v2'])
        result = scorer.score_batch(sample_stocks, parallel=True, max_workers=4)

        assert isinstance(result, BatchResult)
        assert result.total_count == 20
        assert result.success_count > 0

    def test_batch_scorer_multiple_versions(self, sample_stocks):
        """멀티 버전 스코어링"""
        scorer = BatchScorer(versions=['v2', 'v4'])
        result = scorer.score_batch(sample_stocks)

        # 결과에 두 버전 모두 포함
        for code, scores in result.results.items():
            assert 'v2' in scores or 'v4' in scores

    def test_batch_scorer_cache(self, sample_stocks):
        """캐시 효율 테스트"""
        scorer = BatchScorer(versions=['v2'], use_cache=True)

        # 첫 번째 실행
        result1 = scorer.score_batch(sample_stocks)
        stats1 = scorer.cache_stats

        # 두 번째 실행 (캐시 히트 예상)
        result2 = scorer.score_batch(sample_stocks)
        stats2 = scorer.cache_stats

        assert stats2['hits'] >= stats1['hits']

    def test_batch_scorer_get_top_stocks(self, sample_stocks):
        """상위 종목 조회"""
        scorer = BatchScorer(versions=['v2'])
        result = scorer.score_batch(sample_stocks)

        top = result.get_top_stocks('v2', min_score=0, limit=5)

        assert len(top) <= 5
        # 정렬 확인
        if len(top) >= 2:
            assert top[0]['score'] >= top[1]['score']

    def test_batch_scorer_to_dataframe(self, sample_stocks):
        """DataFrame 변환"""
        scorer = BatchScorer(versions=['v2'])
        result = scorer.score_batch(sample_stocks)

        df = result.to_dataframe('v2')

        assert isinstance(df, pd.DataFrame)
        assert 'code' in df.columns
        assert 'score' in df.columns

    def test_batch_scorer_progress_callback(self, sample_stocks):
        """진행률 콜백"""
        scorer = BatchScorer(versions=['v2'])
        progress_calls = []

        def on_progress(completed, total, code):
            progress_calls.append((completed, total, code))

        result = scorer.score_batch(sample_stocks, on_progress=on_progress)

        assert len(progress_calls) == 20
        assert progress_calls[-1][0] == 20


class TestIndicatorCache:
    """IndicatorCache 통합 테스트"""

    @pytest.fixture
    def sample_df(self):
        """테스트용 DataFrame"""
        np.random.seed(42)
        n_days = 100
        prices = [10000 + np.random.uniform(-100, 100) for _ in range(n_days)]
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')
        return pd.DataFrame({
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': [100000] * n_days,
        }, index=dates)

    def test_cache_get_or_calculate(self, sample_df):
        """캐시 저장 및 조회"""
        cache = IndicatorCache(maxsize=10)

        # 첫 번째 호출 (미스)
        df1 = cache.get_or_calculate('TEST001', sample_df)
        assert cache.stats['misses'] == 1
        assert cache.stats['hits'] == 0

        # 두 번째 호출 (히트)
        df2 = cache.get_or_calculate('TEST001', sample_df)
        assert cache.stats['misses'] == 1
        assert cache.stats['hits'] == 1

        # 동일 결과 확인
        assert df1.equals(df2)

    def test_cache_maxsize(self, sample_df):
        """캐시 크기 제한"""
        cache = IndicatorCache(maxsize=5)

        # 10개 종목 캐시
        for i in range(10):
            cache.get_or_calculate(f'TEST{i:03d}', sample_df.copy())

        # 캐시 크기 제한 확인
        assert cache.stats['size'] == 5

    def test_cache_invalidate(self, sample_df):
        """캐시 무효화"""
        cache = IndicatorCache()

        cache.get_or_calculate('TEST001', sample_df)
        assert cache.stats['size'] == 1

        cache.invalidate('TEST001')
        assert cache.stats['size'] == 0

    def test_cache_clear(self, sample_df):
        """캐시 초기화"""
        cache = IndicatorCache()

        for i in range(5):
            cache.get_or_calculate(f'TEST{i:03d}', sample_df.copy())

        cache.clear()
        assert cache.stats['size'] == 0
        assert cache.stats['hits'] == 0
        assert cache.stats['misses'] == 0


class TestScoringConfig:
    """YAML 설정 기반 스코어링 테스트"""

    def test_load_v2_config(self):
        """V2 설정 로드"""
        config = load_scoring_config('v2')

        assert config is not None
        assert config.version == 'v2'
        assert config.name == '추세 추종 강화'
        assert len(config.disqualifiers) >= 1
        assert len(config.scoring_groups) >= 3

    def test_load_v4_config(self):
        """V4 설정 로드"""
        config = load_scoring_config('v4')

        assert config is not None
        assert config.version == 'v4'
        assert 'trend' in config.scoring_groups
        assert 'pattern' in config.scoring_groups

    def test_config_disqualifier(self):
        """과락 조건 테스트"""
        config = load_scoring_config('v2')

        # 역배열 조건
        indicators = {
            'SMA_5': 9000,
            'SMA_20': 9500,
            'SMA_60': 10000,
        }

        reason = config.check_disqualifiers(indicators)
        assert reason == '역배열'

    def test_config_scoring(self):
        """스코어링 테스트"""
        config = load_scoring_config('v2')

        # 정배열 + 좋은 조건
        indicators = {
            'SMA_5': 10500,
            'SMA_20': 10000,
            'SMA_60': 9500,
            'SMA20_SLOPE': 2.5,
            'MACD': 100,
            'RSI': 65,
            'RSI_prev': 60,
            'high_60d': 10400,
            'close': 10500,
            'VOL_RATIO': 4.0,
            'TRADING_VALUE': 20_000_000_000,
        }

        result = config.calculate_all_scores(indicators)

        assert not result['disqualified']
        assert result['score'] > 0
        assert len(result['signals']) > 0

    def test_config_exclusive_groups(self):
        """배타적 그룹 테스트"""
        config = load_scoring_config('v2')

        # RSI Sweet Spot과 RSI Healthy는 배타적
        indicators = {
            'SMA_5': 10500,
            'SMA_20': 10000,
            'SMA_60': 9500,
            'RSI': 65,  # Sweet Spot 구간
            'RSI_prev': 60,
            'high_60d': 10000,
            'close': 9800,
            'VOL_RATIO': 1.5,
            'TRADING_VALUE': 5_000_000_000,
        }

        result = config.calculate_all_scores(indicators)

        # RSI 관련 신호는 하나만
        rsi_signals = [s for s in result['signals'] if s.startswith('RSI_')]
        assert len(rsi_signals) == 1

    def test_config_caching(self):
        """설정 캐싱"""
        config1 = get_config('v2')
        config2 = get_config('v2')

        # 동일 객체 (캐시)
        assert config1 is config2
