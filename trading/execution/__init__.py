"""
자동매매 실행 모듈

모드별 트레이더 클래스:
- BaseTrader: 공통 기능 추상 클래스
- AutoModeTrader: 완전 자동 매매
- SemiAutoTrader: 제안 기반 매매
- GreenlightTrader: AI 주도 매매
"""

from .base_trader import BaseTrader, TradeResult
from .auto_mode import AutoModeTrader
from .semi_auto_mode import SemiAutoTrader

__all__ = [
    'BaseTrader',
    'TradeResult',
    'AutoModeTrader',
    'SemiAutoTrader',
]
