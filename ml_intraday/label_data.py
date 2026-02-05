#!/usr/bin/env python3
"""
라벨링 모듈

분봉 피처 데이터에 N분 후 수익률 기반 라벨(BUY/HOLD/SELL)을 추가합니다.

사용법:
    python ml_intraday/label_data.py                    # 기본 (10분 후 예측)
    python ml_intraday/label_data.py --horizon 5min    # 5분 후 예측
    python ml_intraday/label_data.py --horizon 30min   # 30분 후 예측
"""

import os
import sys
import argparse
import functools
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml_intraday.config import (
    DATA_DIR, OUTPUT_DIR, LABEL_CONFIG,
    LABEL_ENCODING, LABEL_DECODING
)

# 출력 즉시 플러시
print = functools.partial(print, flush=True)


def calculate_forward_return(df: pd.DataFrame, horizon_bars: int) -> pd.Series:
    """
    N봉 후 수익률 계산

    Args:
        df: 분봉 데이터 (close 컬럼 필요)
        horizon_bars: 예측 범위 (봉 수)

    Returns:
        N봉 후 수익률 시리즈 (%)
    """
    future_close = df['close'].shift(-horizon_bars)
    current_close = df['close']

    return_pct = (future_close - current_close) / current_close * 100
    return return_pct


def assign_labels(
    returns: pd.Series,
    buy_threshold: float,
    sell_threshold: float
) -> pd.Series:
    """
    수익률에 따라 라벨 부여

    Args:
        returns: 수익률 시리즈 (%)
        buy_threshold: 매수 임계값 (예: 1.0 = 1% 이상 상승)
        sell_threshold: 매도 임계값 (예: -1.0 = 1% 이상 하락)

    Returns:
        라벨 시리즈 (0=BUY, 1=HOLD, 2=SELL)
    """
    labels = pd.Series(index=returns.index, dtype=int)

    # BUY: 임계값 이상 상승
    labels[returns >= buy_threshold] = LABEL_ENCODING['BUY']

    # SELL: 임계값 이하 하락
    labels[returns <= sell_threshold] = LABEL_ENCODING['SELL']

    # HOLD: 나머지
    labels[(returns > sell_threshold) & (returns < buy_threshold)] = LABEL_ENCODING['HOLD']

    # NaN은 HOLD로 처리 (미래 데이터 없는 마지막 구간)
    labels = labels.fillna(LABEL_ENCODING['HOLD']).astype(int)

    return labels


def label_stock_data(df: pd.DataFrame, horizon: str = '10min') -> pd.DataFrame:
    """
    종목별 분봉 데이터에 라벨 추가

    Args:
        df: 종목 분봉 데이터 (시간순 정렬, 하루 데이터)
        horizon: 예측 범위 ('5min', '10min', '30min')

    Returns:
        라벨이 추가된 DataFrame
    """
    if df.empty:
        return df

    horizon_bars = LABEL_CONFIG['horizons'].get(horizon, 2)
    thresholds = LABEL_CONFIG['thresholds'].get(horizon, {'buy': 1.0, 'sell': -1.0})

    df = df.copy()

    # 수익률 계산
    df['forward_return'] = calculate_forward_return(df, horizon_bars)

    # 라벨 부여
    df['label'] = assign_labels(
        df['forward_return'],
        thresholds['buy'],
        thresholds['sell']
    )

    # 라벨 문자열 (참고용)
    df['label_str'] = df['label'].map(LABEL_DECODING)

    return df


def label_features_data(
    features_df: pd.DataFrame,
    horizon: str = '10min'
) -> pd.DataFrame:
    """
    피처 데이터에 라벨 추가

    Args:
        features_df: engineer_features.py에서 생성한 피처 DataFrame
        horizon: 예측 범위

    Returns:
        라벨이 추가된 DataFrame
    """
    if features_df.empty:
        return features_df

    print(f"라벨링 시작 (horizon={horizon})...")

    horizon_bars = LABEL_CONFIG['horizons'].get(horizon, 2)
    thresholds = LABEL_CONFIG['thresholds'].get(horizon, {'buy': 1.0, 'sell': -1.0})

    all_labeled = []

    # 날짜+종목별로 그룹화하여 처리
    for (date, code), group in features_df.groupby(['date', 'code']):
        group = group.sort_values('time').copy()

        # 수익률 계산
        group['forward_return'] = calculate_forward_return(group, horizon_bars)

        # 라벨 부여
        group['label'] = assign_labels(
            group['forward_return'],
            thresholds['buy'],
            thresholds['sell']
        )

        all_labeled.append(group)

    if all_labeled:
        result = pd.concat(all_labeled, ignore_index=True)

        # 라벨 문자열 (참고용)
        result['label_str'] = result['label'].map(LABEL_DECODING)

        return result

    return pd.DataFrame()


def label_from_parquet(horizon: str = '10min'):
    """
    저장된 피처 파일에서 라벨링

    Args:
        horizon: 예측 범위
    """
    print("=" * 60)
    print("  데이터 라벨링")
    print("=" * 60)

    # 피처 파일 로드
    features_path = OUTPUT_DIR / "features.parquet"
    if not features_path.exists():
        print(f"[에러] 피처 파일 없음: {features_path}")
        print("       먼저 engineer_features.py 실행 필요")
        return

    print(f"\n피처 파일 로드: {features_path}")
    features_df = pd.read_parquet(features_path)
    print(f"  {len(features_df)}행 로드")

    # 라벨링
    labeled_df = label_features_data(features_df, horizon)

    if labeled_df.empty:
        print("[에러] 라벨링 실패")
        return

    # 라벨 분포 출력
    print("\n라벨 분포:")
    label_counts = labeled_df['label_str'].value_counts()
    for label, count in label_counts.items():
        pct = count / len(labeled_df) * 100
        print(f"  {label}: {count:,}개 ({pct:.1f}%)")

    # 유효 샘플만 필터 (미래 데이터 있는 것만)
    valid_df = labeled_df[labeled_df['forward_return'].notna()]
    print(f"\n유효 샘플: {len(valid_df):,}개 (NaN 제거)")

    # 저장
    output_path = OUTPUT_DIR / f"labeled_{horizon}.parquet"
    valid_df.to_parquet(output_path, index=False)
    print(f"\n[완료] {output_path}")

    return valid_df


def label_from_minute_bars(horizon: str = '10min'):
    """
    분봉 데이터에서 직접 라벨링 (피처 없이)

    간단한 라벨만 필요할 때 사용
    """
    print("=" * 60)
    print("  분봉 데이터 직접 라벨링")
    print("=" * 60)

    horizon_bars = LABEL_CONFIG['horizons'].get(horizon, 2)
    thresholds = LABEL_CONFIG['thresholds'].get(horizon, {'buy': 1.0, 'sell': -1.0})

    print(f"\n설정:")
    print(f"  예측 범위: {horizon} ({horizon_bars}봉)")
    print(f"  BUY 임계값: +{thresholds['buy']}%")
    print(f"  SELL 임계값: {thresholds['sell']}%")

    # 날짜별 처리
    date_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])

    if not date_dirs:
        print("[에러] 분봉 데이터 없음")
        return

    all_labeled = []

    for date_dir in date_dirs:
        date = date_dir.name
        parquet_files = list(date_dir.glob("*.parquet"))

        for pf in parquet_files:
            try:
                df = pd.read_parquet(pf)
                df = df.sort_values('time').reset_index(drop=True)

                # 라벨링
                df = label_stock_data(df, horizon)

                # 필요한 컬럼만
                df = df[['date', 'time', 'code', 'close', 'forward_return', 'label', 'label_str']]
                all_labeled.append(df)

            except Exception:
                continue

    if all_labeled:
        result = pd.concat(all_labeled, ignore_index=True)

        # 유효 샘플만
        valid = result[result['forward_return'].notna()]

        # 라벨 분포
        print(f"\n총 샘플: {len(result):,}개")
        print(f"유효 샘플: {len(valid):,}개")

        print("\n라벨 분포:")
        for label, count in valid['label_str'].value_counts().items():
            pct = count / len(valid) * 100
            print(f"  {label}: {count:,}개 ({pct:.1f}%)")

        return valid

    return pd.DataFrame()


def analyze_label_quality(labeled_df: pd.DataFrame):
    """라벨 품질 분석"""
    print("\n" + "=" * 40)
    print("  라벨 품질 분석")
    print("=" * 40)

    # 시간대별 라벨 분포
    print("\n시간대별 라벨 분포:")
    if 'time_bucket' in labeled_df.columns:
        bucket_labels = labeled_df.groupby('time_bucket')['label_str'].value_counts(normalize=True)
        print(bucket_labels.unstack().fillna(0).round(3))

    # BUY 샘플의 실제 수익률 분포
    buy_samples = labeled_df[labeled_df['label'] == LABEL_ENCODING['BUY']]
    if not buy_samples.empty:
        print(f"\nBUY 샘플 수익률 통계:")
        print(f"  평균: {buy_samples['forward_return'].mean():.2f}%")
        print(f"  중앙값: {buy_samples['forward_return'].median():.2f}%")
        print(f"  표준편차: {buy_samples['forward_return'].std():.2f}%")

    # SELL 샘플의 실제 수익률 분포
    sell_samples = labeled_df[labeled_df['label'] == LABEL_ENCODING['SELL']]
    if not sell_samples.empty:
        print(f"\nSELL 샘플 수익률 통계:")
        print(f"  평균: {sell_samples['forward_return'].mean():.2f}%")
        print(f"  중앙값: {sell_samples['forward_return'].median():.2f}%")
        print(f"  표준편차: {sell_samples['forward_return'].std():.2f}%")


def main():
    parser = argparse.ArgumentParser(description="데이터 라벨링")
    parser.add_argument(
        "--horizon",
        type=str,
        default="2min",  # 스캘핑 기본값
        choices=["1min", "2min", "3min", "5min"],  # 스캘핑용
        help="예측 범위"
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="분봉에서 직접 라벨링 (피처 없이)"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="라벨 품질 분석"
    )

    args = parser.parse_args()

    if args.direct:
        result = label_from_minute_bars(args.horizon)
    else:
        result = label_from_parquet(args.horizon)

    if args.analyze and result is not None and not result.empty:
        analyze_label_quality(result)


if __name__ == "__main__":
    main()
