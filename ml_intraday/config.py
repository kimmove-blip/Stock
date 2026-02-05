"""
ML 장중매매 파이프라인 설정 (스캘핑 전략)
"""
from pathlib import Path

# ==================== 경로 설정 ====================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "database" / "minute_bars"
MODEL_DIR = PROJECT_ROOT / "models"
OUTPUT_DIR = PROJECT_ROOT / "output" / "ml_intraday"

# 디렉토리 생성
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 데이터 수집 설정 ====================
COLLECT_CONFIG = {
    "top_stocks": 500,           # 거래대금 상위 종목 수
    "history_days": 60,          # 수집할 과거 거래일 수
    "minute_unit": 1,            # 분봉 단위 (1분봉 - 스캘핑용)
    "min_trading_amount": 5_000_000_000,  # 최소 거래대금 (50억)
    "api_rate_limit": 20,        # API 호출 제한 (실전: 20건/초)
    "api_sleep": 0.06,           # API 호출 간격 (초)
}

# ==================== 피처 엔지니어링 설정 ====================
FEATURE_CONFIG = {
    # 이동평균 윈도우 (1분봉 수 기준)
    "ma_windows": [5, 10, 20, 60],  # 1분봉 기준: 5분, 10분, 20분, 60분

    # RSI 윈도우 (스캘핑용 단기)
    "rsi_window": 9,

    # MACD 파라미터 (스캘핑용 단기)
    "macd_fast": 8,
    "macd_slow": 17,
    "macd_signal": 9,

    # 볼린저밴드
    "bb_window": 20,
    "bb_std": 2,

    # 거래량 이동평균
    "vol_ma_window": 5,
}

# ==================== 시간대 버킷 설정 ====================
TIME_BUCKETS = {
    "early": ("090000", "091500"),      # 장 초반 (09:00~09:15) - 노이즈 많음
    "morning1": ("091500", "100000"),   # 오전1 (09:15~10:00) - 스캘핑 적합
    "morning2": ("100000", "110000"),   # 오전2 (10:00~11:00)
    "golden": ("110000", "130000"),     # 골든타임 (11:00~13:00)
    "afternoon": ("130000", "143000"),  # 오후장 (13:00~14:30)
    "closing": ("143000", "153000"),    # 마감 (14:30~15:30) - 스캘핑 주의
}

def get_time_bucket(time_str: str) -> str:
    """시간 문자열(HHMMSS)을 시간대 버킷으로 변환"""
    for bucket, (start, end) in TIME_BUCKETS.items():
        if start <= time_str < end:
            return bucket
    return "closing"

# ==================== 라벨링 설정 (스캘핑) ====================
LABEL_CONFIG = {
    # 예측 범위 (1분봉 수 기준)
    "horizons": {
        "1min": 1,      # 1봉 후 = 1분 후
        "2min": 2,      # 2봉 후 = 2분 후
        "3min": 3,      # 3봉 후 = 3분 후
        "5min": 5,      # 5봉 후 = 5분 후
    },

    # 라벨 임계값 (수익률 %) - 스캘핑용 낮은 임계값
    # 거래비용 ~0.2% 고려하여 설정
    "thresholds": {
        "1min": {"buy": 0.25, "sell": -0.25},   # 0.25% 움직임
        "2min": {"buy": 0.35, "sell": -0.35},   # 0.35% 움직임
        "3min": {"buy": 0.45, "sell": -0.45},   # 0.45% 움직임
        "5min": {"buy": 0.60, "sell": -0.60},   # 0.60% 움직임
    },

    # 기본 예측 범위 (2분 후 예측 권장)
    "default_horizon": "2min",
}

# ==================== 모델 학습 설정 ====================
MODEL_CONFIG = {
    # LightGBM 하이퍼파라미터 (스캘핑용 튜닝)
    "lgbm_params": {
        "objective": "multiclass",
        "num_class": 3,           # BUY=0, HOLD=1, SELL=2
        "learning_rate": 0.03,    # 낮춤 (과적합 방지)
        "num_leaves": 31,
        "max_depth": 6,           # 낮춤 (과적합 방지)
        "min_child_samples": 100, # 높임 (노이즈 대응)
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "reg_alpha": 0.2,         # 높임 (정규화 강화)
        "reg_lambda": 0.2,
        "n_estimators": 800,      # 높임 (early stopping 활용)
        "class_weight": "balanced",
        "random_state": 42,
        "verbose": -1,
    },

    # 학습/검증 분할
    "train_ratio": 0.7,          # 학습 데이터 비율
    "valid_ratio": 0.15,         # 검증 데이터 비율
    "test_ratio": 0.15,          # 테스트 데이터 비율

    # TimeSeriesSplit 설정
    "n_splits": 5,               # 교차검증 폴드 수

    # 모델 저장 경로
    "model_path": MODEL_DIR / "scalping_lgbm.pkl",
    "feature_importance_path": OUTPUT_DIR / "feature_importance.csv",
}

# ==================== 백테스트 설정 (스캘핑) ====================
BACKTEST_CONFIG = {
    # 거래 비용 (정확히 반영)
    "commission": 0.00015,       # 수수료 0.015%
    "slippage": 0.0015,          # 슬리피지 0.15% (스캘핑은 높게)
    "tax": 0.0018,               # 세금 0.18% (매도 시)

    # 총 왕복 비용: 약 0.21% (수수료x2 + 슬리피지x2 + 세금)
    # 실질 수익 = 예측수익 - 0.21%

    # 리스크 관리 (스캘핑용 빠른 손절/익절)
    "max_position_pct": 0.15,    # 최대 포지션 (총 자산의 15%)
    "stop_loss": -0.007,         # 손절 -0.7% (빠른 손절)
    "take_profit": 0.01,         # 익절 +1.0% (빠른 익절)
    "time_stop_bars": 10,        # 시간손절 10분 (10봉)

    # 진입 조건 (스캘핑용 높은 확률 요구)
    "min_confidence": 0.65,      # 최소 예측 확률
    "min_score_v2": 65,          # 최소 V2 스코어 (완화)
    "min_score_v4": 45,          # 최소 V4 스코어 (완화)
}

# ==================== auto_trader 통합 설정 (스캘핑) ====================
INTEGRATION_CONFIG = {
    # 하이브리드 전략 조건 (스캘핑용)
    "strong_buy": {
        "ml_prob": 0.65,         # ML 확률 65%+
        "v2_min": 70,
        "v4_min": 45,
    },
    "ml_priority_buy": {
        "ml_prob": 0.75,         # ML 확률 높으면 스코어 완화
        "v2_min": 60,
    },
    "ml_warning_skip": {
        "ml_prob_max": 0.35,     # ML 경고
        "v2_min": 75,
    },

    # 캐시 설정 (스캘핑용 짧은 TTL)
    "prediction_cache_ttl": 30,  # 예측 캐시 TTL (30초)

    # 스캘핑 전용 설정
    "scalping": {
        "enabled": True,
        "max_trades_per_day": 30,        # 일일 최대 거래 수
        "min_volume_ratio": 2.0,         # 최소 거래량 비율 (평균 대비)
        "avoid_early_minutes": 15,       # 장 초반 15분 회피
        "avoid_closing_minutes": 30,     # 장 마감 30분 전 회피
    },
}

# ==================== 피처 목록 ====================
FEATURE_COLUMNS = [
    # 가격 피처
    "close_vs_open",        # (종가-시가)/시가
    "high_low_range",       # (고가-저가)/시가
    "body_ratio",           # 캔들 몸통 비율
    "upper_wick",           # 윗꼬리 비율
    "lower_wick",           # 아랫꼬리 비율
    "close_position",       # 캔들 내 종가 위치

    # 이동평균 피처 (1분봉 기준)
    "dist_vwap",            # VWAP 대비 이격도
    "dist_ma5m",            # 5봉(5분) MA 대비 이격도
    "dist_ma20m",           # 20봉(20분) MA 대비 이격도
    "ma_slope_5",           # 5봉 MA 기울기
    "ma_slope_20",          # 20봉 MA 기울기
    "ma_aligned",           # 이평선 정배열 여부

    # 거래량 피처
    "vol_ratio_5m",         # 5봉 평균 대비 거래량 비율
    "vol_acceleration",     # 거래량 가속도
    "cum_vol_pct",          # 누적 거래량 비율 (하루 대비)
    "vol_price_corr",       # 거래량-가격 상관계수

    # 모멘텀 피처
    "rsi_5m",               # RSI (9봉)
    "macd_hist",            # MACD 히스토그램
    "price_momentum_5",     # 5봉 가격 모멘텀
    "price_momentum_10",    # 10봉 가격 모멘텀

    # 볼린저밴드 피처
    "bb_position",          # BB 내 위치 (0~1)
    "bb_width",             # BB 폭 (변동성)

    # 시간 피처
    "time_bucket",          # 시간대 (인코딩)
    "minutes_from_open",    # 장 시작 후 경과 시간

    # 기존 스코어 피처 (record_intraday_scores.py에서)
    "v2_score",             # V2 스코어
    "v4_score",             # V4 스코어
    "v5_score",             # V5 스코어
    "v2_delta",             # V2 변화량
    "v4_delta",             # V4 변화량
]

# 라벨 인코딩
LABEL_ENCODING = {
    "BUY": 0,
    "HOLD": 1,
    "SELL": 2,
}

LABEL_DECODING = {v: k for k, v in LABEL_ENCODING.items()}
