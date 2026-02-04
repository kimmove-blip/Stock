#!/usr/bin/env python3
"""
LightGBM 모델 학습

분봉 피처 데이터로 장중 매수 타이밍 예측 모델을 학습합니다.

사용법:
    python ml_intraday/train_model.py                    # 기본 학습
    python ml_intraday/train_model.py --horizon 5min    # 5분 예측 모델
    python ml_intraday/train_model.py --cv              # 교차검증
"""

import os
import sys
import argparse
import functools
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml_intraday.config import (
    OUTPUT_DIR, MODEL_DIR, MODEL_CONFIG,
    FEATURE_COLUMNS, LABEL_ENCODING, LABEL_DECODING
)

# 출력 즉시 플러시
print = functools.partial(print, flush=True)


def load_labeled_data(horizon: str = '10min') -> pd.DataFrame:
    """라벨링된 데이터 로드"""
    data_path = OUTPUT_DIR / f"labeled_{horizon}.parquet"

    if not data_path.exists():
        print(f"[에러] 라벨 데이터 없음: {data_path}")
        print("       먼저 label_data.py 실행 필요")
        return pd.DataFrame()

    df = pd.read_parquet(data_path)
    print(f"데이터 로드: {len(df):,}행")

    return df


def prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    학습용 피처 준비

    Args:
        df: 라벨링된 데이터

    Returns:
        (피처 DataFrame, 사용된 피처 목록)
    """
    # 사용 가능한 피처만 선택
    available_features = [col for col in FEATURE_COLUMNS if col in df.columns]

    # 누락된 피처 확인
    missing_features = [col for col in FEATURE_COLUMNS if col not in df.columns]
    if missing_features:
        print(f"[경고] 누락된 피처: {missing_features}")

    # 피처 데이터
    X = df[available_features].copy()

    # NaN 처리
    X = X.fillna(0)

    # 무한대 처리
    X = X.replace([np.inf, -np.inf], 0)

    print(f"피처: {len(available_features)}개")

    return X, available_features


def time_series_split(
    df: pd.DataFrame,
    train_ratio: float = 0.7,
    valid_ratio: float = 0.15
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    시계열 기반 데이터 분할

    Args:
        df: 전체 데이터 (date 컬럼 필요)
        train_ratio: 학습 데이터 비율
        valid_ratio: 검증 데이터 비율

    Returns:
        (train_df, valid_df, test_df)
    """
    # 날짜순 정렬
    dates = sorted(df['date'].unique())
    n_dates = len(dates)

    train_end = int(n_dates * train_ratio)
    valid_end = int(n_dates * (train_ratio + valid_ratio))

    train_dates = dates[:train_end]
    valid_dates = dates[train_end:valid_end]
    test_dates = dates[valid_end:]

    train_df = df[df['date'].isin(train_dates)]
    valid_df = df[df['date'].isin(valid_dates)]
    test_df = df[df['date'].isin(test_dates)]

    print(f"데이터 분할:")
    print(f"  Train: {len(train_dates)}일, {len(train_df):,}샘플 ({train_dates[0]}~{train_dates[-1]})")
    print(f"  Valid: {len(valid_dates)}일, {len(valid_df):,}샘플 ({valid_dates[0]}~{valid_dates[-1]})")
    print(f"  Test:  {len(test_dates)}일, {len(test_df):,}샘플 ({test_dates[0]}~{test_dates[-1]})")

    return train_df, valid_df, test_df


def train_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_valid: pd.DataFrame = None,
    y_valid: pd.Series = None,
    params: Dict = None
):
    """
    LightGBM 모델 학습

    Args:
        X_train: 학습 피처
        y_train: 학습 라벨
        X_valid: 검증 피처 (early stopping용)
        y_valid: 검증 라벨
        params: 하이퍼파라미터

    Returns:
        학습된 모델
    """
    try:
        import lightgbm as lgb
    except ImportError:
        print("[에러] LightGBM 설치 필요: pip install lightgbm")
        return None

    if params is None:
        params = MODEL_CONFIG['lgbm_params'].copy()

    # LightGBM 데이터셋
    train_data = lgb.Dataset(X_train, label=y_train)

    valid_sets = [train_data]
    valid_names = ['train']

    if X_valid is not None and y_valid is not None:
        valid_data = lgb.Dataset(X_valid, label=y_valid, reference=train_data)
        valid_sets.append(valid_data)
        valid_names.append('valid')

    # 학습 파라미터
    num_round = params.pop('n_estimators', 500)

    # 콜백 설정
    callbacks = [
        lgb.early_stopping(stopping_rounds=50, verbose=True),
        lgb.log_evaluation(period=100)
    ]

    # 학습
    print("\nLightGBM 학습 시작...")
    model = lgb.train(
        params,
        train_data,
        num_boost_round=num_round,
        valid_sets=valid_sets,
        valid_names=valid_names,
        callbacks=callbacks
    )

    return model


def train_sklearn_lgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_valid: pd.DataFrame = None,
    y_valid: pd.Series = None,
    params: Dict = None
):
    """
    sklearn API로 LightGBM 학습 (호환성용)
    """
    try:
        from lightgbm import LGBMClassifier
    except ImportError:
        print("[에러] LightGBM 설치 필요: pip install lightgbm")
        return None

    if params is None:
        params = MODEL_CONFIG['lgbm_params'].copy()

    # sklearn API 파라미터 조정
    sklearn_params = {
        'n_estimators': params.get('n_estimators', 500),
        'learning_rate': params.get('learning_rate', 0.05),
        'num_leaves': params.get('num_leaves', 31),
        'max_depth': params.get('max_depth', 8),
        'min_child_samples': params.get('min_child_samples', 50),
        'subsample': params.get('subsample', 0.8),
        'colsample_bytree': params.get('colsample_bytree', 0.8),
        'reg_alpha': params.get('reg_alpha', 0.1),
        'reg_lambda': params.get('reg_lambda', 0.1),
        'class_weight': params.get('class_weight', 'balanced'),
        'random_state': params.get('random_state', 42),
        'verbose': -1,
        'n_jobs': -1,
    }

    model = LGBMClassifier(**sklearn_params)

    # Early stopping
    eval_set = [(X_train, y_train)]
    if X_valid is not None:
        eval_set.append((X_valid, y_valid))

    print("\nLightGBM (sklearn API) 학습 시작...")
    model.fit(
        X_train, y_train,
        eval_set=eval_set,
        callbacks=[
            lambda env: print(f"  [{env.iteration}] train: {env.evaluation_result_list[0][2]:.4f}") if env.iteration % 100 == 0 else None
        ]
    )

    return model


def evaluate_model(model, X_test: pd.DataFrame, y_test: pd.Series) -> Dict:
    """
    모델 평가

    Args:
        model: 학습된 모델
        X_test: 테스트 피처
        y_test: 테스트 라벨

    Returns:
        평가 지표 딕셔너리
    """
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        classification_report, confusion_matrix
    )

    # 예측
    y_pred = model.predict(X_test)

    # 확률 예측 (있으면)
    try:
        y_prob = model.predict_proba(X_test)
    except:
        y_prob = None

    # 기본 지표
    metrics = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision_macro': precision_score(y_test, y_pred, average='macro', zero_division=0),
        'recall_macro': recall_score(y_test, y_pred, average='macro', zero_division=0),
        'f1_macro': f1_score(y_test, y_pred, average='macro', zero_division=0),
    }

    # 클래스별 지표
    for label_name, label_id in LABEL_ENCODING.items():
        y_binary = (y_test == label_id).astype(int)
        y_pred_binary = (y_pred == label_id).astype(int)

        metrics[f'precision_{label_name}'] = precision_score(y_binary, y_pred_binary, zero_division=0)
        metrics[f'recall_{label_name}'] = recall_score(y_binary, y_pred_binary, zero_division=0)
        metrics[f'f1_{label_name}'] = f1_score(y_binary, y_pred_binary, zero_division=0)

    # BUY 예측의 승률 (가장 중요)
    buy_predictions = y_pred == LABEL_ENCODING['BUY']
    if buy_predictions.sum() > 0:
        buy_correct = (y_pred[buy_predictions] == y_test.values[buy_predictions]).sum()
        metrics['buy_win_rate'] = buy_correct / buy_predictions.sum()
        metrics['buy_predictions'] = int(buy_predictions.sum())
    else:
        metrics['buy_win_rate'] = 0
        metrics['buy_predictions'] = 0

    # Precision@K (상위 K개 예측의 정확도)
    if y_prob is not None:
        buy_prob = y_prob[:, LABEL_ENCODING['BUY']]
        top_k = min(100, len(buy_prob) // 10)  # 상위 10% 또는 100개

        top_indices = np.argsort(buy_prob)[-top_k:]
        top_correct = (y_test.values[top_indices] == LABEL_ENCODING['BUY']).sum()
        metrics['precision_at_k'] = top_correct / top_k
        metrics['k'] = top_k

    return metrics


def get_feature_importance(model, feature_names: List[str]) -> pd.DataFrame:
    """피처 중요도 추출"""
    try:
        importance = model.feature_importance(importance_type='gain')
    except:
        importance = model.feature_importances_

    fi_df = pd.DataFrame({
        'feature': feature_names,
        'importance': importance
    })
    fi_df = fi_df.sort_values('importance', ascending=False)
    fi_df['importance_pct'] = fi_df['importance'] / fi_df['importance'].sum() * 100

    return fi_df


def train_and_evaluate(horizon: str = '10min', use_cv: bool = False):
    """
    전체 학습 및 평가 파이프라인

    Args:
        horizon: 예측 범위
        use_cv: 교차검증 사용 여부
    """
    print("=" * 60)
    print("  LightGBM 모델 학습")
    print("=" * 60)

    # 데이터 로드
    print(f"\n[1] 데이터 로드 (horizon={horizon})...")
    df = load_labeled_data(horizon)
    if df.empty:
        return

    # 피처 준비
    print(f"\n[2] 피처 준비...")
    X, feature_names = prepare_features(df)
    y = df['label']

    print(f"  피처 수: {len(feature_names)}")
    print(f"  샘플 수: {len(X):,}")

    # 라벨 분포
    print("\n라벨 분포:")
    for label_name, label_id in LABEL_ENCODING.items():
        count = (y == label_id).sum()
        pct = count / len(y) * 100
        print(f"  {label_name}: {count:,} ({pct:.1f}%)")

    # 데이터 분할
    print(f"\n[3] 데이터 분할...")
    train_df, valid_df, test_df = time_series_split(
        df,
        MODEL_CONFIG['train_ratio'],
        MODEL_CONFIG['valid_ratio']
    )

    X_train = X.loc[train_df.index]
    y_train = y.loc[train_df.index]
    X_valid = X.loc[valid_df.index]
    y_valid = y.loc[valid_df.index]
    X_test = X.loc[test_df.index]
    y_test = y.loc[test_df.index]

    # 모델 학습
    print(f"\n[4] 모델 학습...")
    model = train_sklearn_lgbm(X_train, y_train, X_valid, y_valid)

    if model is None:
        return

    # 평가
    print(f"\n[5] 모델 평가...")
    metrics = evaluate_model(model, X_test, y_test)

    print("\n테스트 결과:")
    print(f"  정확도: {metrics['accuracy']:.4f}")
    print(f"  F1 (Macro): {metrics['f1_macro']:.4f}")
    print(f"\n  BUY 성능:")
    print(f"    Precision: {metrics['precision_BUY']:.4f}")
    print(f"    Recall: {metrics['recall_BUY']:.4f}")
    print(f"    Win Rate: {metrics['buy_win_rate']:.4f} ({metrics['buy_predictions']}건)")
    if 'precision_at_k' in metrics:
        print(f"    Precision@{metrics['k']}: {metrics['precision_at_k']:.4f}")

    # 피처 중요도
    print(f"\n[6] 피처 중요도...")
    fi_df = get_feature_importance(model, feature_names)

    print("\n상위 15개 피처:")
    for _, row in fi_df.head(15).iterrows():
        print(f"  {row['feature']}: {row['importance_pct']:.1f}%")

    # 저장
    print(f"\n[7] 모델 저장...")

    # 모델 저장
    model_path = MODEL_DIR / f"intraday_lgbm_{horizon}.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump({
            'model': model,
            'feature_names': feature_names,
            'horizon': horizon,
            'metrics': metrics,
            'trained_at': datetime.now().isoformat(),
        }, f)
    print(f"  모델: {model_path}")

    # 피처 중요도 저장
    fi_path = OUTPUT_DIR / f"feature_importance_{horizon}.csv"
    fi_df.to_csv(fi_path, index=False)
    print(f"  피처 중요도: {fi_path}")

    # 메트릭 저장
    metrics_path = OUTPUT_DIR / f"metrics_{horizon}.csv"
    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)
    print(f"  메트릭: {metrics_path}")

    print("\n[완료]")

    return model, metrics


def cross_validate(horizon: str = '10min', n_splits: int = 5):
    """
    시계열 교차검증

    Args:
        horizon: 예측 범위
        n_splits: 폴드 수
    """
    from sklearn.model_selection import TimeSeriesSplit

    print("=" * 60)
    print("  시계열 교차검증")
    print("=" * 60)

    # 데이터 로드
    df = load_labeled_data(horizon)
    if df.empty:
        return

    # 피처 준비
    X, feature_names = prepare_features(df)
    y = df['label']

    # 날짜순 정렬
    df_sorted = df.sort_values('date')
    X = X.loc[df_sorted.index]
    y = y.loc[df_sorted.index]

    # TimeSeriesSplit
    tscv = TimeSeriesSplit(n_splits=n_splits)

    all_metrics = []

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        print(f"\n[Fold {fold+1}/{n_splits}]")

        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        # 학습
        model = train_sklearn_lgbm(X_train, y_train)

        # 평가
        metrics = evaluate_model(model, X_test, y_test)
        metrics['fold'] = fold + 1
        all_metrics.append(metrics)

        print(f"  Accuracy: {metrics['accuracy']:.4f}")
        print(f"  BUY Win Rate: {metrics['buy_win_rate']:.4f}")

    # 평균 결과
    metrics_df = pd.DataFrame(all_metrics)

    print("\n" + "=" * 40)
    print("  교차검증 평균 결과")
    print("=" * 40)
    print(f"  Accuracy: {metrics_df['accuracy'].mean():.4f} ± {metrics_df['accuracy'].std():.4f}")
    print(f"  BUY Win Rate: {metrics_df['buy_win_rate'].mean():.4f} ± {metrics_df['buy_win_rate'].std():.4f}")
    print(f"  BUY Precision: {metrics_df['precision_BUY'].mean():.4f} ± {metrics_df['precision_BUY'].std():.4f}")

    return metrics_df


def main():
    parser = argparse.ArgumentParser(description="LightGBM 모델 학습")
    parser.add_argument(
        "--horizon",
        type=str,
        default="10min",
        choices=["5min", "10min", "30min"],
        help="예측 범위"
    )
    parser.add_argument(
        "--cv",
        action="store_true",
        help="교차검증 실행"
    )

    args = parser.parse_args()

    if args.cv:
        cross_validate(args.horizon)
    else:
        train_and_evaluate(args.horizon)


if __name__ == "__main__":
    main()
