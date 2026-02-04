#!/usr/bin/env python3
"""
피처 엔지니어링 모듈

분봉 데이터로부터 ML 학습용 피처를 계산합니다.

사용법:
    python ml_intraday/engineer_features.py              # 전체 피처 생성
    python ml_intraday/engineer_features.py --date 20260128  # 특정 날짜만
"""

import os
import sys
import argparse
import functools
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml_intraday.config import (
    DATA_DIR, OUTPUT_DIR, FEATURE_CONFIG,
    TIME_BUCKETS, get_time_bucket, FEATURE_COLUMNS
)

# 출력 즉시 플러시
print = functools.partial(print, flush=True)


def calculate_rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """RSI 계산"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()

    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD 계산"""
    exp_fast = prices.ewm(span=fast, adjust=False).mean()
    exp_slow = prices.ewm(span=slow, adjust=False).mean()

    macd_line = exp_fast - exp_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_bollinger_bands(prices: pd.Series, window: int = 20, std_mult: float = 2):
    """볼린저밴드 계산"""
    middle = prices.rolling(window=window).mean()
    std = prices.rolling(window=window).std()

    upper = middle + (std * std_mult)
    lower = middle - (std * std_mult)

    return upper, middle, lower


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP (거래량 가중 평균 가격) 계산"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    cum_tp_vol = (typical_price * df['volume']).cumsum()
    cum_vol = df['volume'].cumsum()

    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    return vwap.fillna(df['close'])


def calculate_features_for_bar(df: pd.DataFrame, idx: int) -> Optional[Dict]:
    """
    특정 분봉에 대한 피처 계산

    Args:
        df: 분봉 데이터 (시간순 정렬)
        idx: 현재 분봉 인덱스

    Returns:
        피처 딕셔너리
    """
    # 최소 20봉 이상 필요
    if idx < 20:
        return None

    row = df.iloc[idx]
    prev_rows = df.iloc[:idx+1]  # 현재까지의 모든 데이터

    o, h, l, c, v = row['open'], row['high'], row['low'], row['close'], row['volume']

    # 유효성 검사
    if o == 0 or c == 0:
        return None

    features = {}

    # ==================== 가격 피처 ====================

    # 시가 대비 종가 변화율
    features['close_vs_open'] = (c - o) / o * 100 if o > 0 else 0

    # 고저 범위 (변동성)
    features['high_low_range'] = (h - l) / o * 100 if o > 0 else 0

    # 캔들 몸통 비율
    body = abs(c - o)
    total_range = h - l if h > l else 1
    features['body_ratio'] = body / total_range if total_range > 0 else 0

    # 윗꼬리/아랫꼬리 비율
    features['upper_wick'] = (h - max(o, c)) / total_range if total_range > 0 else 0
    features['lower_wick'] = (min(o, c) - l) / total_range if total_range > 0 else 0

    # 캔들 내 종가 위치 (0=저가, 1=고가)
    features['close_position'] = (c - l) / total_range if total_range > 0 else 0.5

    # ==================== 이동평균 피처 ====================

    close_series = prev_rows['close']

    # VWAP
    vwap = calculate_vwap(prev_rows).iloc[-1]
    features['dist_vwap'] = (c - vwap) / vwap * 100 if vwap > 0 else 0

    # 단기 이동평균 (5봉)
    if len(close_series) >= 5:
        ma5 = close_series.tail(5).mean()
        features['dist_ma5m'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0

        # MA5 기울기 (최근 5봉 선형 회귀 기울기)
        ma5_values = close_series.rolling(5).mean().tail(5).dropna()
        if len(ma5_values) >= 2:
            features['ma_slope_5'] = (ma5_values.iloc[-1] - ma5_values.iloc[0]) / ma5_values.iloc[0] * 100
        else:
            features['ma_slope_5'] = 0
    else:
        features['dist_ma5m'] = 0
        features['ma_slope_5'] = 0

    # 중기 이동평균 (20봉)
    if len(close_series) >= 20:
        ma20 = close_series.tail(20).mean()
        features['dist_ma20m'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

        # MA20 기울기
        ma20_values = close_series.rolling(20).mean().tail(5).dropna()
        if len(ma20_values) >= 2:
            features['ma_slope_20'] = (ma20_values.iloc[-1] - ma20_values.iloc[0]) / ma20_values.iloc[0] * 100
        else:
            features['ma_slope_20'] = 0
    else:
        features['dist_ma20m'] = 0
        features['ma_slope_20'] = 0

    # 이평선 정배열 여부
    if len(close_series) >= 20:
        ma5 = close_series.tail(5).mean()
        ma10 = close_series.tail(10).mean()
        ma20 = close_series.tail(20).mean()
        features['ma_aligned'] = 1 if c > ma5 > ma10 > ma20 else 0
    else:
        features['ma_aligned'] = 0

    # ==================== 거래량 피처 ====================

    vol_series = prev_rows['volume']

    # 5봉 평균 대비 거래량 비율
    if len(vol_series) >= 5:
        avg_vol_5 = vol_series.tail(6).head(5).mean()  # 이전 5봉 평균
        features['vol_ratio_5m'] = v / avg_vol_5 if avg_vol_5 > 0 else 1
    else:
        features['vol_ratio_5m'] = 1

    # 거래량 가속도 (변화율의 변화율)
    if len(vol_series) >= 3:
        vol_change = vol_series.pct_change().tail(3)
        features['vol_acceleration'] = vol_change.diff().iloc[-1] if not pd.isna(vol_change.diff().iloc[-1]) else 0
    else:
        features['vol_acceleration'] = 0

    # 누적 거래량 비율 (하루 대비)
    if 'cum_volume' in row and row['cum_volume'] > 0:
        # 현재 시간까지의 예상 일 거래량 대비
        time_str = row.get('time', '120000')
        minutes_from_open = int(time_str[:2]) * 60 + int(time_str[2:4]) - 540  # 09:00 기준
        total_minutes = 390  # 장 시간 6.5시간
        expected_ratio = minutes_from_open / total_minutes if total_minutes > 0 else 0.5
        features['cum_vol_pct'] = expected_ratio  # 간소화
    else:
        features['cum_vol_pct'] = 0.5

    # 거래량-가격 상관계수 (최근 10봉)
    if len(prev_rows) >= 10:
        recent = prev_rows.tail(10)
        corr = recent['close'].corr(recent['volume'])
        features['vol_price_corr'] = corr if not pd.isna(corr) else 0
    else:
        features['vol_price_corr'] = 0

    # ==================== 모멘텀 피처 ====================

    # RSI (14봉)
    if len(close_series) >= 14:
        rsi_series = calculate_rsi(close_series, 14)
        features['rsi_5m'] = rsi_series.iloc[-1]
    else:
        features['rsi_5m'] = 50

    # MACD 히스토그램
    if len(close_series) >= 26:
        _, _, macd_hist = calculate_macd(close_series)
        features['macd_hist'] = macd_hist.iloc[-1] / c * 100 if c > 0 else 0
    else:
        features['macd_hist'] = 0

    # 가격 모멘텀 (N봉 전 대비 변화율)
    if len(close_series) >= 5:
        features['price_momentum_5'] = (c - close_series.iloc[-5]) / close_series.iloc[-5] * 100
    else:
        features['price_momentum_5'] = 0

    if len(close_series) >= 10:
        features['price_momentum_10'] = (c - close_series.iloc[-10]) / close_series.iloc[-10] * 100
    else:
        features['price_momentum_10'] = 0

    # ==================== 볼린저밴드 피처 ====================

    if len(close_series) >= 20:
        upper, middle, lower = calculate_bollinger_bands(close_series)

        # BB 내 위치 (0=하단, 1=상단)
        bb_range = upper.iloc[-1] - lower.iloc[-1]
        if bb_range > 0:
            features['bb_position'] = (c - lower.iloc[-1]) / bb_range
        else:
            features['bb_position'] = 0.5

        # BB 폭 (변동성 지표)
        features['bb_width'] = bb_range / middle.iloc[-1] * 100 if middle.iloc[-1] > 0 else 0
    else:
        features['bb_position'] = 0.5
        features['bb_width'] = 0

    # ==================== 시간 피처 ====================

    time_str = row.get('time', '120000')

    # 시간대 버킷 (원핫 인코딩 대신 숫자)
    bucket = get_time_bucket(time_str)
    bucket_map = {'early': 0, 'morning': 1, 'golden': 2, 'afternoon': 3, 'closing': 4}
    features['time_bucket'] = bucket_map.get(bucket, 2)

    # 장 시작 후 경과 시간 (분)
    h, m = int(time_str[:2]), int(time_str[2:4])
    features['minutes_from_open'] = (h - 9) * 60 + m

    # ==================== 메타 정보 ====================
    features['date'] = row.get('date', '')
    features['time'] = time_str
    features['code'] = row.get('code', '')
    features['close'] = c

    return features


def process_stock_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    종목 데이터에서 피처 계산

    Args:
        df: 종목 분봉 데이터 (시간순 정렬)

    Returns:
        피처 DataFrame
    """
    features_list = []

    for idx in range(len(df)):
        features = calculate_features_for_bar(df, idx)
        if features:
            features_list.append(features)

    if features_list:
        return pd.DataFrame(features_list)
    return pd.DataFrame()


def process_date(date: str) -> pd.DataFrame:
    """
    특정 날짜의 모든 종목 피처 계산

    Args:
        date: 날짜 (YYYYMMDD)

    Returns:
        전체 피처 DataFrame
    """
    date_dir = DATA_DIR / date

    if not date_dir.exists():
        print(f"  [경고] {date} 데이터 없음")
        return pd.DataFrame()

    parquet_files = list(date_dir.glob("*.parquet"))
    if not parquet_files:
        return pd.DataFrame()

    all_features = []

    for pf in parquet_files:
        try:
            df = pd.read_parquet(pf)
            df = df.sort_values('time').reset_index(drop=True)

            features_df = process_stock_data(df)
            if not features_df.empty:
                all_features.append(features_df)
        except Exception as e:
            continue

    if all_features:
        return pd.concat(all_features, ignore_index=True)
    return pd.DataFrame()


def load_intraday_scores(date: str) -> Dict[str, Dict]:
    """
    record_intraday_scores.py가 기록한 스코어 로드

    Args:
        date: 날짜 (YYYYMMDD)

    Returns:
        {code_time: {'v2': score, 'v4': score, ...}}
    """
    scores_dir = PROJECT_ROOT / "output" / "intraday_scores"

    # 해당 날짜 CSV 파일들
    csv_files = sorted(scores_dir.glob(f"{date}_*.csv"))

    scores = {}
    prev_scores = {}  # 이전 스코어 (delta 계산용)

    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            time_str = csv_file.stem.split('_')[1]  # YYYYMMDD_HHMM.csv

            for _, row in df.iterrows():
                code = str(row.get('code', '')).zfill(6)
                key = f"{code}_{time_str}"

                # 스코어 저장
                scores[key] = {
                    'v1': row.get('v1', 0),
                    'v2': row.get('v2', 0),
                    'v4': row.get('v4', 0),
                    'v5': row.get('v5', 0),
                }

                # Delta 계산
                prev_key = f"{code}_prev"
                if prev_key in prev_scores:
                    scores[key]['v2_delta'] = row.get('v2', 0) - prev_scores[prev_key].get('v2', 0)
                    scores[key]['v4_delta'] = row.get('v4', 0) - prev_scores[prev_key].get('v4', 0)
                else:
                    scores[key]['v2_delta'] = 0
                    scores[key]['v4_delta'] = 0

                # 현재 스코어를 다음 delta 계산용으로 저장
                prev_scores[prev_key] = {
                    'v2': row.get('v2', 0),
                    'v4': row.get('v4', 0),
                }

        except Exception:
            continue

    return scores


def merge_with_scores(features_df: pd.DataFrame, scores: Dict) -> pd.DataFrame:
    """피처에 V2/V4/V5 스코어 병합"""
    if features_df.empty or not scores:
        # 스코어 없으면 기본값
        features_df['v2_score'] = 0
        features_df['v4_score'] = 0
        features_df['v5_score'] = 0
        features_df['v2_delta'] = 0
        features_df['v4_delta'] = 0
        return features_df

    def get_score(row):
        code = str(row['code']).zfill(6)
        time_str = str(row['time'])[:4]  # HHMM

        # 5분 단위로 반올림 (record_intraday_scores.py와 맞춤)
        h, m = int(time_str[:2]), int(time_str[2:])
        m_5 = (m // 5) * 5
        time_key = f"{h:02d}{m_5:02d}"

        key = f"{code}_{time_key}"
        return scores.get(key, {})

    score_data = features_df.apply(get_score, axis=1)

    features_df['v2_score'] = score_data.apply(lambda x: x.get('v2', 0))
    features_df['v4_score'] = score_data.apply(lambda x: x.get('v4', 0))
    features_df['v5_score'] = score_data.apply(lambda x: x.get('v5', 0))
    features_df['v2_delta'] = score_data.apply(lambda x: x.get('v2_delta', 0))
    features_df['v4_delta'] = score_data.apply(lambda x: x.get('v4_delta', 0))

    return features_df


def engineer_features(dates: List[str] = None, merge_scores: bool = True):
    """
    전체 피처 엔지니어링 실행

    Args:
        dates: 처리할 날짜 목록 (None이면 전체)
        merge_scores: V2/V4/V5 스코어 병합 여부
    """
    print("=" * 60)
    print("  피처 엔지니어링")
    print("=" * 60)

    # 처리할 날짜 목록
    if dates is None:
        date_dirs = sorted([d.name for d in DATA_DIR.iterdir() if d.is_dir()])
    else:
        date_dirs = dates

    if not date_dirs:
        print("[에러] 처리할 데이터가 없습니다.")
        return

    print(f"\n{len(date_dirs)}일 데이터 처리...")

    all_features = []

    for i, date in enumerate(date_dirs):
        print(f"\n[{i+1}/{len(date_dirs)}] {date} 처리 중...")

        # 피처 계산
        features_df = process_date(date)

        if features_df.empty:
            print("  스킵 (데이터 없음)")
            continue

        # 스코어 병합
        if merge_scores:
            scores = load_intraday_scores(date)
            if scores:
                features_df = merge_with_scores(features_df, scores)
                print(f"  스코어 병합: {len(scores)}개")
            else:
                # 스코어 없으면 기본값
                features_df['v2_score'] = 0
                features_df['v4_score'] = 0
                features_df['v5_score'] = 0
                features_df['v2_delta'] = 0
                features_df['v4_delta'] = 0

        all_features.append(features_df)
        print(f"  {len(features_df)}행 완료")

    if all_features:
        result = pd.concat(all_features, ignore_index=True)

        # 저장
        output_path = OUTPUT_DIR / "features.parquet"
        result.to_parquet(output_path, index=False)
        print(f"\n[완료] {output_path}")
        print(f"       총 {len(result)}행, {len(result.columns)}열")

        return result

    return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="피처 엔지니어링")
    parser.add_argument("--date", type=str, help="특정 날짜만 처리 (YYYYMMDD)")
    parser.add_argument("--no-scores", action="store_true", help="스코어 병합 안함")

    args = parser.parse_args()

    dates = [args.date] if args.date else None
    engineer_features(dates, merge_scores=not args.no_scores)


if __name__ == "__main__":
    main()
