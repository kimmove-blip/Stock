"""
트레이딩 시스템 통합 설정 클래스

TradingConfig dataclass로 모든 설정을 통합 관리
- 기존 config.py의 AutoTraderConfig 대체
- DB/환경변수에서 로드하는 팩토리 메서드 제공
"""

import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

# 기본 경로
BASE_DIR = Path(__file__).parent.parent.parent  # /home/kimhc/Stock
DATABASE_DIR = BASE_DIR / "database"


@dataclass
class TradingConfig:
    """트레이딩 설정 통합 클래스"""

    # === 투자 모드 ===
    is_virtual: bool = True  # True: 모의투자, False: 실전투자
    trade_mode: str = "auto"  # "auto": 자동매매, "semi-auto": 반자동 매수제안

    # === 포지션 관리 ===
    max_per_stock: int = 200_000  # 종목당 최대 투자금액 (원)
    max_holdings: int = 20  # 최대 보유 종목 수
    max_daily_trades: int = 30  # 일일 최대 거래 횟수

    # === 매수 조건 ===
    min_buy_score: int = 65  # 최소 매수 점수
    min_volume_ratio: float = 1.0  # 최소 거래량 비율 (20일 평균 대비)
    min_trading_amount: int = 300_000_000  # 최소 거래대금 (3억)

    # === 손절/익절 ===
    stop_loss_pct: float = -0.10  # 손절 비율 (-10%)
    take_profit_pct: Optional[float] = None  # 익절 비율 (None=비활성화)
    min_hold_score: int = 50  # 최소 보유 점수 (이하 시 매도)
    max_hold_days: int = 10  # 최대 보유 기간 (일)

    # === 수수료/세금 ===
    commission_rate: float = 0.00015  # 매매 수수료 0.015%
    tax_rate_kospi: float = 0.0033  # KOSPI 세금 0.33%
    tax_rate_kosdaq: float = 0.0018  # KOSDAQ 세금 0.18%

    # === 매수 제안 (semi-auto 모드) ===
    suggestion_expire_hours: int = 24  # 매수 제안 만료 시간
    max_pending_suggestions: int = 10  # 최대 대기 제안 수
    target_profit_pct: float = 0.20  # 목표 수익률 (+20%)
    buy_band_pct: float = 0.03  # 매수 밴드 (±3%)

    # === 갭 전략 ===
    gap_strategy_enabled: bool = True  # 갭 전략 활성화
    limit_up_threshold: float = 25.0  # 상한가 판정 기준 (25%)
    limit_up_gap_min: float = 5.0  # 상한가 종목 최소 갭
    limit_up_gap_max: float = 15.0  # 상한가 종목 최대 갭
    normal_gap_min: float = 3.0  # 일반 종목 최소 갭
    normal_gap_ideal_max: float = 8.0  # 일반 종목 이상적 갭 상한
    normal_gap_max: float = 10.0  # 일반 종목 최대 갭

    # === 알림 설정 ===
    telegram_notify: bool = True  # 텔레그램 알림 활성화
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # === 긴급 정지 ===
    max_daily_loss_pct: float = -0.05  # 일일 최대 손실률 (-5%)
    emergency_stop: bool = False  # 긴급 정지 플래그

    # === 스코어링 설정 ===
    scoring_version: str = "v2"  # 기본 스코어링 버전
    scoring_versions_for_buy: List[str] = field(
        default_factory=lambda: ["v2", "v4"]
    )  # 매수 판단에 사용할 버전들

    # === 강력 매수 신호 ===
    strong_buy_signals: List[str] = field(
        default_factory=lambda: [
            "GOLDEN_CROSS_20_60",
            "MACD_GOLDEN_CROSS",
            "SUPERTREND_BUY",
            "STOCH_GOLDEN_OVERSOLD",
            "MORNING_STAR",
            "MA_ALIGNED",
        ]
    )

    # === 매도 신호 ===
    sell_signals: List[str] = field(
        default_factory=lambda: [
            "RSI_OVERBOUGHT",
            "MACD_DEAD_CROSS",
            "DEAD_CROSS_5_20",
            "DEAD_CROSS_20_60",
            "BB_UPPER_BREAK",
            "BEARISH_ENGULFING",
            "EVENING_STAR",
            "SUPERTREND_SELL",
            "PSAR_SELL_SIGNAL",
        ]
    )

    # === 메타 정보 ===
    user_id: Optional[int] = None  # DB에서 로드한 경우 사용자 ID
    account_number: Optional[str] = None

    @classmethod
    def from_db(cls, user_id: int, db_path: Optional[str] = None) -> "TradingConfig":
        """DB에서 설정을 로드하여 TradingConfig 인스턴스 생성

        Args:
            user_id: 사용자 ID
            db_path: DB 경로 (기본값: database/auto_trade.db)

        Returns:
            TradingConfig 인스턴스
        """
        if db_path is None:
            db_path = str(DATABASE_DIR / "auto_trade.db")

        config = cls(user_id=user_id)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # auto_trade_settings 테이블에서 설정 로드
            cursor.execute(
                """
                SELECT
                    investment_per_stock,
                    min_score,
                    stop_loss_pct,
                    take_profit_pct,
                    trade_mode,
                    max_daily_trades,
                    min_hold_score,
                    max_hold_days,
                    initial_investment,
                    is_active
                FROM auto_trade_settings
                WHERE user_id = ?
            """,
                (user_id,),
            )

            row = cursor.fetchone()
            if row:
                (
                    investment_per_stock,
                    min_score,
                    stop_loss_pct,
                    take_profit_pct,
                    trade_mode,
                    max_daily_trades,
                    min_hold_score,
                    max_hold_days,
                    initial_investment,
                    is_active,
                ) = row

                if investment_per_stock:
                    config.max_per_stock = investment_per_stock
                if min_score:
                    config.min_buy_score = min_score
                if stop_loss_pct:
                    config.stop_loss_pct = stop_loss_pct
                if take_profit_pct:
                    config.take_profit_pct = take_profit_pct
                if trade_mode:
                    config.trade_mode = trade_mode
                if max_daily_trades:
                    config.max_daily_trades = max_daily_trades
                if min_hold_score:
                    config.min_hold_score = min_hold_score
                if max_hold_days:
                    config.max_hold_days = max_hold_days
                if not is_active:
                    config.emergency_stop = True

            # api_key_settings 테이블에서 계좌 정보 로드
            cursor.execute(
                """
                SELECT account_number, is_mock
                FROM api_key_settings
                WHERE user_id = ?
            """,
                (user_id,),
            )

            row = cursor.fetchone()
            if row:
                account_number, is_mock = row
                config.account_number = account_number
                config.is_virtual = bool(is_mock)

            conn.close()

        except sqlite3.Error as e:
            print(f"DB 설정 로드 오류: {e}")

        return config

    @classmethod
    def from_env(cls) -> "TradingConfig":
        """환경변수에서 설정을 로드하여 TradingConfig 인스턴스 생성

        환경변수:
            TRADING_MAX_PER_STOCK: 종목당 최대 투자금액
            TRADING_MAX_HOLDINGS: 최대 보유 종목 수
            TRADING_MIN_BUY_SCORE: 최소 매수 점수
            TRADING_STOP_LOSS_PCT: 손절 비율
            TRADING_IS_VIRTUAL: 모의투자 여부 ("true" | "false")
            TRADING_TRADE_MODE: 거래 모드 ("auto" | "semi-auto")
            TELEGRAM_BOT_TOKEN: 텔레그램 봇 토큰
            TELEGRAM_CHAT_ID: 텔레그램 채팅 ID
        """
        config = cls()

        # 정수형 설정
        if val := os.environ.get("TRADING_MAX_PER_STOCK"):
            config.max_per_stock = int(val)
        if val := os.environ.get("TRADING_MAX_HOLDINGS"):
            config.max_holdings = int(val)
        if val := os.environ.get("TRADING_MIN_BUY_SCORE"):
            config.min_buy_score = int(val)
        if val := os.environ.get("TRADING_MAX_DAILY_TRADES"):
            config.max_daily_trades = int(val)

        # 실수형 설정
        if val := os.environ.get("TRADING_STOP_LOSS_PCT"):
            config.stop_loss_pct = float(val)
        if val := os.environ.get("TRADING_TAKE_PROFIT_PCT"):
            config.take_profit_pct = float(val)
        if val := os.environ.get("TRADING_MIN_VOLUME_RATIO"):
            config.min_volume_ratio = float(val)

        # 불리언 설정
        if val := os.environ.get("TRADING_IS_VIRTUAL"):
            config.is_virtual = val.lower() == "true"
        if val := os.environ.get("TRADING_TELEGRAM_NOTIFY"):
            config.telegram_notify = val.lower() == "true"

        # 문자열 설정
        if val := os.environ.get("TRADING_TRADE_MODE"):
            config.trade_mode = val
        if val := os.environ.get("TELEGRAM_BOT_TOKEN"):
            config.telegram_bot_token = val
        if val := os.environ.get("TELEGRAM_CHAT_ID"):
            config.telegram_chat_id = val

        return config

    @classmethod
    def merge(cls, *configs: "TradingConfig") -> "TradingConfig":
        """여러 설정을 병합 (뒤의 설정이 우선)

        Args:
            *configs: 병합할 TradingConfig 인스턴스들

        Returns:
            병합된 TradingConfig 인스턴스
        """
        result = cls()

        for config in configs:
            for field_name in result.__dataclass_fields__:
                value = getattr(config, field_name)
                # None이 아닌 값만 덮어씀
                if value is not None:
                    # 리스트 필드는 기본값이 아닌 경우만 덮어씀
                    if isinstance(value, list):
                        default_value = cls().__dataclass_fields__[
                            field_name
                        ].default_factory()
                        if value != default_value:
                            setattr(result, field_name, value)
                    else:
                        setattr(result, field_name, value)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """설정을 딕셔너리로 변환"""
        return {
            "is_virtual": self.is_virtual,
            "trade_mode": self.trade_mode,
            "max_per_stock": self.max_per_stock,
            "max_holdings": self.max_holdings,
            "max_daily_trades": self.max_daily_trades,
            "min_buy_score": self.min_buy_score,
            "min_volume_ratio": self.min_volume_ratio,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "min_hold_score": self.min_hold_score,
            "max_hold_days": self.max_hold_days,
            "commission_rate": self.commission_rate,
            "telegram_notify": self.telegram_notify,
            "scoring_version": self.scoring_version,
            "emergency_stop": self.emergency_stop,
        }

    def validate(self) -> List[str]:
        """설정 유효성 검사

        Returns:
            에러 메시지 리스트 (빈 리스트 = 유효)
        """
        errors = []

        if self.max_per_stock <= 0:
            errors.append("max_per_stock은 양수여야 합니다")

        if self.max_holdings <= 0:
            errors.append("max_holdings는 양수여야 합니다")

        if not -1.0 <= self.stop_loss_pct <= 0:
            errors.append("stop_loss_pct는 -1.0 ~ 0 사이여야 합니다")

        if self.take_profit_pct is not None and self.take_profit_pct <= 0:
            errors.append("take_profit_pct는 양수여야 합니다")

        if not 0 <= self.min_buy_score <= 100:
            errors.append("min_buy_score는 0 ~ 100 사이여야 합니다")

        if self.min_volume_ratio < 0:
            errors.append("min_volume_ratio는 0 이상이어야 합니다")

        if self.trade_mode not in ("auto", "semi-auto", "greenlight"):
            errors.append("trade_mode는 'auto', 'semi-auto', 'greenlight' 중 하나여야 합니다")

        return errors


# 기본 설정 인스턴스 (싱글톤 패턴)
_default_config: Optional[TradingConfig] = None


def get_default_config() -> TradingConfig:
    """기본 설정 인스턴스 반환 (싱글톤)"""
    global _default_config
    if _default_config is None:
        # 환경변수 설정을 기본값에 병합
        _default_config = TradingConfig.merge(
            TradingConfig(),
            TradingConfig.from_env()
        )
    return _default_config


def set_default_config(config: TradingConfig) -> None:
    """기본 설정 인스턴스 설정"""
    global _default_config
    _default_config = config


def reset_default_config() -> None:
    """기본 설정 인스턴스 리셋"""
    global _default_config
    _default_config = None
