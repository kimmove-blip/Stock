"""
ML 장중매매 파이프라인 설정
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
    "minute_unit": 5,            # 분봉 단위 (5분봉)
    "min_trading_amount": 5_000_000_000,  # 최소 거래대금 (50억)
    "api_rate_limit": 20,        # API 호출 제한 (실전: 20건/초)
    "api_sleep": 0.06,           # API 호출 간격 (초)
}

# ==================== 피처 엔지니어링 설정 ====================
FEATURE_CONFIG = {
    # 이동평균 윈도우 (분봉 수 기준)
    "ma_windows": [5, 10, 20, 60],  # 5분봉 기준: 25분, 50분, 100분, 5시간

    # RSI 윈도우
    "rsi_window": 14,

    # MACD 파라미터
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # 볼린저밴드
    "bb_window": 20,
    "bb_std": 2,

    # 거래량 이동평균
    "vol_ma_window": 5,
}

# ==================== 시간대 버킷 설정 ====================
TIME_BUCKETS = {
    "early": ("090000", "093000"),      # 장 초반 (09:00~09:30)
    "morning": ("093000", "110000"),    # 오전장 (09:30~11:00)
    "golden": ("110000", "130000"),     # 골든타임 (11:00~13:00)
    "afternoon": ("130000", "150000"),  # 오후장 (13:00~15:00)
    "closing": ("150000", "153000"),    # 마감 (15:00~15:30)
}

def get_time_bucket(time_str: str) -> str:
    """시간 문자열(HHMMSS)을 시간대 버킷으로 변환"""
    for bucket, (start, end) in TIME_BUCKETS.items():
        if start <= time_str < end:
            return bucket
    return "closing"

# ==================== 라벨링 설정 ====================
LABEL_CONFIG = {
    # 예측 범위 (분봉 수 기준, 5분봉이면 x5분)
    "horizons": {
        "5min": 1,      # 1봉 후 = 5분 후
        "10min": 2,     # 2봉 후 = 10분 후
        "30min": 6,     # 6봉 후 = 30분 후
    },

    # 라벨 임계값 (수익률 %)
    "thresholds": {
        "5min": {"buy": 0.5, "sell": -0.5},
        "10min": {"buy": 1.0, "sell": -1.0},
        "30min": {"buy": 1.5, "sell": -1.5},
    },

    # 기본 예측 범위
    "default_horizon": "10min",
}

# ==================== 모델 학습 설정 ====================
MODEL_CONFIG = {
    # LightGBM 하이퍼파라미터
    "lgbm_params": {
        "objective": "multiclass",
        "num_class": 3,           # BUY=0, HOLD=1, SELL=2
        "learning_rate": 0.05,
        "num_leaves": 31,
        "max_depth": 8,
        "min_child_samples": 50,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "n_estimators": 500,
        "class_weight": "balanced",
        "random_state": 42,
        "verbose": -1,
    },

    # 학습/검증 분할
    "train_ratio": 0.7,          # 학습 데이터 비율 (60% train + 10% valid)
    "valid_ratio": 0.15,         # 검증 데이터 비율
    "test_ratio": 0.15,          # 테스트 데이터 비율

    # TimeSeriesSplit 설정
    "n_splits": 5,               # 교차검증 폴드 수

    # 모델 저장 경로
    "model_path": MODEL_DIR / "intraday_lgbm.pkl",
    "feature_importance_path": OUTPUT_DIR / "feature_importance.csv",
}

# ==================== 백테스트 설정 ====================
BACKTEST_CONFIG = {
    # 거래 비용
    "commission": 0.00015,       # 수수료 0.015%
    "slippage": 0.001,           # 슬리피지 0.1%
    "tax": 0.0018,               # 세금 0.18% (매도 시)

    # 리스크 관리
    "max_position_pct": 0.1,     # 최대 포지션 (총 자산의 10%)
    "stop_loss": -0.03,          # 손절 -3%
    "take_profit": 0.05,         # 익절 5%

    # 진입 조건
    "min_confidence": 0.6,       # 최소 예측 확률
    "min_score_v2": 70,          # 최소 V2 스코어
    "min_score_v4": 50,          # 최소 V4 스코어
}

# ==================== auto_trader 통합 설정 ====================
INTEGRATION_CONFIG = {
    # 하이브리드 전략 조건
    "strong_buy": {
        "ml_prob": 0.6,
        "v2_min": 75,
        "v4_min": 50,
    },
    "ml_priority_buy": {
        "ml_prob": 0.7,
        "v2_min": 70,
    },
    "ml_warning_skip": {
        "ml_prob_max": 0.4,
        "v2_min": 80,
    },

    # 캐시 설정
    "prediction_cache_ttl": 60,  # 예측 캐시 TTL (초)
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

    # 이동평균 피처
    "dist_vwap",            # VWAP 대비 이격도
    "dist_ma5m",            # 5분 MA 대비 이격도
    "dist_ma20m",           # 20분 MA 대비 이격도
    "ma_slope_5",           # 5분 MA 기울기
    "ma_slope_20",          # 20분 MA 기울기
    "ma_aligned",           # 이평선 정배열 여부

    # 거래량 피처
    "vol_ratio_5m",         # 5분 평균 대비 거래량 비율
    "vol_acceleration",     # 거래량 가속도
    "cum_vol_pct",          # 누적 거래량 비율 (하루 대비)
    "vol_price_corr",       # 거래량-가격 상관계수

    # 모멘텀 피처
    "rsi_5m",               # 5분봉 RSI
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
