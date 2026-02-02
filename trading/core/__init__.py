"""
트레이딩 시스템 핵심 모듈
- exceptions: 공통 예외 클래스
- config: 통합 설정 클래스
"""

from .exceptions import (
    TradingError,
    MarketClosedError,
    InsufficientFundsError,
    OrderExecutionError,
    DataLoadError,
    ConfigurationError,
    APIError,
    TokenExpiredError,
    RateLimitError,
)

from .config import TradingConfig

__all__ = [
    # 예외 클래스
    'TradingError',
    'MarketClosedError',
    'InsufficientFundsError',
    'OrderExecutionError',
    'DataLoadError',
    'ConfigurationError',
    'APIError',
    'TokenExpiredError',
    'RateLimitError',
    # 설정 클래스
    'TradingConfig',
]
