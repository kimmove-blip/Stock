"""
pytest 공통 fixtures

사용법:
    pytest tests/ -v
    pytest tests/scoring/ -v
    pytest tests/trading/ -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============ OHLCV 데이터 Fixtures ============

@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """기본 OHLCV 데이터프레임 (60일)

    정배열 추세 상승 중인 종목 시뮬레이션
    """
    np.random.seed(42)
    n_days = 100

    # 기본 상승 추세 (일일 0.3% 상승)
    base_price = 10000
    prices = [base_price]
    for i in range(1, n_days):
        change = np.random.normal(0.003, 0.02)  # 평균 0.3%, 표준편차 2%
        prices.append(prices[-1] * (1 + change))

    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

    df = pd.DataFrame({
        'Open': [p * np.random.uniform(0.99, 1.01) for p in prices],
        'High': [p * np.random.uniform(1.0, 1.03) for p in prices],
        'Low': [p * np.random.uniform(0.97, 1.0) for p in prices],
        'Close': prices,
        'Volume': [np.random.randint(100000, 1000000) for _ in range(n_days)],
    }, index=dates)

    return df


@pytest.fixture
def reverse_aligned_df() -> pd.DataFrame:
    """역배열 OHLCV 데이터프레임

    하락 추세 (5일 < 20일 < 60일 이동평균)
    """
    np.random.seed(42)
    n_days = 100

    # 하락 추세 (일일 -0.3% 하락)
    base_price = 10000
    prices = [base_price]
    for i in range(1, n_days):
        change = np.random.normal(-0.003, 0.02)  # 평균 -0.3%
        prices.append(prices[-1] * (1 + change))

    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

    df = pd.DataFrame({
        'Open': [p * np.random.uniform(0.99, 1.01) for p in prices],
        'High': [p * np.random.uniform(1.0, 1.03) for p in prices],
        'Low': [p * np.random.uniform(0.97, 1.0) for p in prices],
        'Close': prices,
        'Volume': [np.random.randint(100000, 500000) for _ in range(n_days)],
    }, index=dates)

    return df


@pytest.fixture
def short_df() -> pd.DataFrame:
    """짧은 OHLCV 데이터프레임 (30일 - 60일 미만)

    스코어 계산이 None을 반환해야 함
    """
    np.random.seed(42)
    n_days = 30

    prices = [10000 + np.random.uniform(-100, 100) for _ in range(n_days)]
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

    df = pd.DataFrame({
        'Open': prices,
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Close': prices,
        'Volume': [np.random.randint(100000, 500000) for _ in range(n_days)],
    }, index=dates)

    return df


@pytest.fixture
def high_volume_df(sample_ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """거래량 급증 데이터프레임

    마지막 거래량이 평균의 5배
    """
    df = sample_ohlcv_df.copy()
    avg_volume = df['Volume'].mean()
    df.loc[df.index[-1], 'Volume'] = int(avg_volume * 5)
    return df


@pytest.fixture
def breakout_df() -> pd.DataFrame:
    """60일 신고가 돌파 데이터프레임"""
    np.random.seed(42)
    n_days = 100

    # 박스권 후 돌파
    prices = [10000 + np.random.uniform(-200, 200) for _ in range(90)]
    # 마지막 10일: 급등
    for i in range(10):
        prices.append(prices[-1] * 1.02)

    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

    df = pd.DataFrame({
        'Open': [p * 0.995 for p in prices],
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Close': prices,
        'Volume': [np.random.randint(100000, 500000) for _ in range(n_days)],
    }, index=dates)

    return df


# ============ 보유 종목 Fixtures ============

@pytest.fixture
def sample_holdings() -> list:
    """샘플 보유 종목 리스트"""
    return [
        {
            "stock_code": "005930",
            "stock_name": "삼성전자",
            "quantity": 10,
            "avg_price": 70000,
            "current_price": 72000,
            "market": "KOSPI",
        },
        {
            "stock_code": "035420",
            "stock_name": "NAVER",
            "quantity": 5,
            "avg_price": 200000,
            "current_price": 195000,
            "market": "KOSPI",
        },
        {
            "stock_code": "247540",
            "stock_name": "에코프로비엠",
            "quantity": 3,
            "avg_price": 150000,
            "current_price": 140000,  # -6.67%
            "market": "KOSDAQ",
        },
    ]


@pytest.fixture
def stop_loss_holding() -> dict:
    """손절 대상 보유 종목"""
    return {
        "stock_code": "000000",
        "stock_name": "손절종목",
        "quantity": 10,
        "avg_price": 10000,
        "current_price": 8900,  # -11%
        "market": "KOSDAQ",
    }


@pytest.fixture
def take_profit_holding() -> dict:
    """익절 대상 보유 종목"""
    return {
        "stock_code": "000001",
        "stock_name": "익절종목",
        "quantity": 10,
        "avg_price": 10000,
        "current_price": 12500,  # +25%
        "market": "KOSDAQ",
    }


# ============ 설정 Fixtures ============

@pytest.fixture
def trading_config():
    """테스트용 TradingConfig"""
    from trading.core.config import TradingConfig

    return TradingConfig(
        is_virtual=True,
        max_per_stock=200000,
        max_holdings=20,
        stop_loss_pct=-0.10,
        take_profit_pct=0.20,
        min_buy_score=65,
        min_volume_ratio=1.0,
        min_hold_score=40,
    )


@pytest.fixture
def trading_limits():
    """테스트용 TradingLimits"""
    from trading.risk_manager import TradingLimits

    return TradingLimits(
        max_per_stock=200000,
        stop_loss_pct=-0.07,
        take_profit_pct=0.15,
        max_daily_trades=10,
        max_holdings=20,
        min_buy_score=80,
        min_hold_score=40,
    )


# ============ 매수 후보 Fixtures ============

@pytest.fixture
def buy_candidates() -> list:
    """매수 후보 종목 리스트"""
    return [
        {
            "stock_code": "373220",
            "stock_name": "LG에너지솔루션",
            "score": 85,
            "volume_ratio": 2.5,
            "signals": ["MA_ALIGNED", "RSI_SWEET_SPOT", "VOLUME_SURGE_3X"],
        },
        {
            "stock_code": "000270",
            "stock_name": "기아",
            "score": 78,
            "volume_ratio": 1.8,
            "signals": ["MA_ALIGNED", "MACD_BULL"],
        },
        {
            "stock_code": "352820",
            "stock_name": "하이브",
            "score": 72,
            "volume_ratio": 1.5,
            "signals": ["MA_20_STEEP"],
        },
        {
            "stock_code": "LOW001",
            "stock_name": "저점수종목",
            "score": 55,  # min_buy_score 미달
            "volume_ratio": 1.2,
            "signals": [],
        },
    ]


# ============ 유틸리티 Fixtures ============

@pytest.fixture
def temp_csv_dir(tmp_path):
    """임시 CSV 디렉토리"""
    csv_dir = tmp_path / "intraday_scores"
    csv_dir.mkdir()
    return csv_dir


@pytest.fixture
def mock_datetime(monkeypatch):
    """datetime.now() 모킹 헬퍼"""
    class MockDatetime:
        def __init__(self, year=2026, month=1, day=28, hour=10, minute=0):
            self._now = datetime(year, month, day, hour, minute)

        def now(self):
            return self._now

        def set_time(self, hour, minute=0):
            self._now = self._now.replace(hour=hour, minute=minute)

    mock_dt = MockDatetime()

    def mock_now():
        return mock_dt.now()

    return mock_dt
