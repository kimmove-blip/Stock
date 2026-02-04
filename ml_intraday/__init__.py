"""
ML 장중매매 파이프라인

분봉 데이터 기반 장중 매수 타이밍 예측 모델

모듈:
    - config: 설정 값
    - collect_minute_bars: 분봉 데이터 수집
    - engineer_features: 피처 엔지니어링
    - label_data: 라벨링
    - train_model: 모델 학습
    - backtest: 백테스트
    - predictor: 실시간 예측

사용법:
    # 1. 분봉 데이터 수집 (60일)
    python -m ml_intraday.collect_minute_bars --days 60

    # 2. 피처 생성
    python -m ml_intraday.engineer_features

    # 3. 라벨링
    python -m ml_intraday.label_data

    # 4. 모델 학습
    python -m ml_intraday.train_model

    # 5. 백테스트
    python -m ml_intraday.backtest --report

    # 6. 실시간 예측 (auto_trader.py에서)
    from ml_intraday import IntradayPredictor, predict_stock
"""

from ml_intraday.config import (
    DATA_DIR,
    MODEL_DIR,
    OUTPUT_DIR,
    COLLECT_CONFIG,
    FEATURE_CONFIG,
    LABEL_CONFIG,
    MODEL_CONFIG,
    BACKTEST_CONFIG,
    INTEGRATION_CONFIG,
    FEATURE_COLUMNS,
    LABEL_ENCODING,
    LABEL_DECODING,
    get_time_bucket,
)

from ml_intraday.predictor import (
    IntradayPredictor,
    get_predictor,
    predict_stock,
)

__all__ = [
    # 설정
    'DATA_DIR',
    'MODEL_DIR',
    'OUTPUT_DIR',
    'COLLECT_CONFIG',
    'FEATURE_CONFIG',
    'LABEL_CONFIG',
    'MODEL_CONFIG',
    'BACKTEST_CONFIG',
    'INTEGRATION_CONFIG',
    'FEATURE_COLUMNS',
    'LABEL_ENCODING',
    'LABEL_DECODING',
    'get_time_bucket',
    # 예측기
    'IntradayPredictor',
    'get_predictor',
    'predict_stock',
]

__version__ = '1.0.0'
