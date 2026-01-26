#!/usr/bin/env python3
"""
10분 단위 전 종목 스코어 기록기

- 10분마다 거래대금 30억+ 종목에 대해 V1~V9 스코어 계산
- 주가, 거래량, 거래대금 등 지표 기록
- output/intraday_scores/ 폴더에 CSV 저장
- V9: 갭상승 확률 예측 (ML 모델)

사용법:
    python record_intraday_scores.py              # 기본 실행
    python record_intraday_scores.py --dry-run    # 테스트 (저장 안함)
"""

import os
import sys
import argparse
import warnings
import pickle
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

warnings.filterwarnings("ignore")

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from scoring import SCORING_FUNCTIONS

# 설정
OUTPUT_DIR = PROJECT_ROOT / "output" / "intraday_scores"
V9_MODEL_PATH = PROJECT_ROOT / "models" / "gap_model_v9.pkl"
MIN_MARKET_CAP = 30_000_000_000      # 300억
MIN_TRADING_AMOUNT = 3_000_000_000   # 30억 (어제 기준)
MAX_WORKERS = 20
VERSIONS = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']

# V9 모델 (전역 로드)
V9_MODEL = None
V9_FEATURES = None

# 출력 즉시 플러시
import functools
print = functools.partial(print, flush=True)


def load_v9_model():
    """V9 모델 로드"""
    global V9_MODEL, V9_FEATURES
    try:
        with open(V9_MODEL_PATH, 'rb') as f:
            data = pickle.load(f)
        V9_MODEL = data['model']
        V9_FEATURES = data['features']
        return True
    except Exception as e:
        print(f"[경고] V9 모델 로드 실패: {e}")
        return False


def calc_v9_features(df):
    """V9 피처 계산 (FDR 컬럼명 사용: Open, High, Low, Close, Volume)"""
    if len(df) < 21:
        return None

    idx = len(df) - 1
    row = df.iloc[idx]
    prev_rows = df.iloc[idx-20:idx]

    o, h, l, c, v = row['Open'], row['High'], row['Low'], row['Close'], row['Volume']
    if o == 0 or c == 0 or v == 0:
        return None

    f = {}
    body = abs(c - o)
    total_range = h - l if h > l else 1

    f['close_pos'] = (c - l) / total_range if total_range > 0 else 0.5
    f['close_high'] = (c - l) / (h - l) if h > l else 0.5
    f['is_bull'] = 1 if c > o else 0
    f['body_ratio'] = body / total_range if total_range > 0 else 0
    f['upper_wick'] = (h - max(o, c)) / total_range if total_range > 0 else 0
    f['lower_wick'] = (min(o, c) - l) / total_range if total_range > 0 else 0

    prev_close = df.iloc[idx-1]['Close']
    f['day_change'] = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0

    ma5 = prev_rows['Close'].tail(5).mean()
    ma20 = prev_rows['Close'].mean()
    f['dist_ma5'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0
    f['dist_ma20'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

    avg_vol = prev_rows['Volume'].mean()
    f['vol_ratio'] = v / avg_vol if avg_vol > 0 else 1

    recent_vol = prev_rows['Volume'].tail(5).mean()
    older_vol = prev_rows['Volume'].head(15).mean()
    f['vol_declining'] = 1 if recent_vol < older_vol * 0.7 else 0

    changes = prev_rows['Close'].diff()
    gains = changes.where(changes > 0, 0).mean()
    losses = (-changes.where(changes < 0, 0)).mean()
    f['rsi'] = gains / (gains + losses) * 100 if gains + losses > 0 else 50
    f['rsi_overbought'] = 1 if f['rsi'] > 70 else 0

    recent_5 = df.iloc[idx-4:idx+1]
    f['consec_bull'] = sum(1 for i in range(len(recent_5))
                           if recent_5.iloc[i]['Close'] > recent_5.iloc[i]['Open'])

    ma5_val = df.iloc[idx-4:idx+1]['Close'].mean()
    ma10_val = df.iloc[idx-9:idx+1]['Close'].mean()
    ma20_val = df.iloc[idx-19:idx+1]['Close'].mean()
    f['aligned'] = 1 if c > ma5_val > ma10_val > ma20_val else 0

    high_20d = prev_rows['High'].max()
    low_20d = prev_rows['Low'].min()
    f['near_high_20d'] = c / high_20d if high_20d > 0 else 0
    f['from_low_20d'] = (c - low_20d) / low_20d * 100 if low_20d > 0 else 0

    f['volatility'] = prev_rows['Close'].pct_change().std() * 100
    f['trade_value'] = row['Volume'] * c / 100000000
    f['is_surge'] = 1 if f['day_change'] >= 15 else 0

    if idx >= 2:
        prev_prev_close = df.iloc[idx-2]['Close']
        two_day_change = (c - prev_prev_close) / prev_prev_close * 100
        f['two_day_surge'] = 1 if two_day_change >= 20 else 0
    else:
        f['two_day_surge'] = 0

    return f


def predict_v9_prob(df) -> float:
    """V9 갭상승 확률 예측"""
    global V9_MODEL, V9_FEATURES

    if V9_MODEL is None:
        return 0.0

    try:
        features = calc_v9_features(df)
        if features is None:
            return 0.0

        # 피처 필터링 (등락률, 거래대금)
        if not (-15 <= features['day_change'] <= 25):
            return 0.0
        if features['trade_value'] < 50:  # 50억
            return 0.0

        # 예측
        X = pd.DataFrame([features])[V9_FEATURES]
        prob = V9_MODEL.predict_proba(X)[0][1]
        return round(prob * 100, 1)
    except:
        return 0.0


def get_stock_list() -> pd.DataFrame:
    """스크리닝 대상 종목 목록 (거래대금 30억+)"""
    try:
        krx = fdr.StockListing("KRX")
        columns_needed = ["Code", "Name", "Market", "Marcap", "Amount"]
        available_cols = [c for c in columns_needed if c in krx.columns]
        df = krx[available_cols].copy()
        df["Code"] = df["Code"].astype(str).str.zfill(6)

        if "Marcap" in df.columns:
            df = df[df["Marcap"] >= MIN_MARKET_CAP]
        if "Amount" in df.columns:
            df = df[df["Amount"] >= MIN_TRADING_AMOUNT]

        # 특수종목/우선주 제외
        exclude_keywords = ["스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지"]
        for kw in exclude_keywords:
            df = df[~df["Name"].str.contains(kw, case=False, na=False)]
        df = df[df["Code"].str[-1] == "0"]

        return df.reset_index(drop=True)
    except Exception as e:
        print(f"[오류] 종목 목록 조회 실패: {e}")
        return pd.DataFrame()


def get_stock_data(code: str, days: int = 120) -> pd.DataFrame:
    """종목 OHLCV 데이터 조회"""
    try:
        from datetime import timedelta
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = fdr.DataReader(code, start_date, end_date)
        return df if df is not None and not df.empty else None
    except:
        return None


def calculate_scores(df: pd.DataFrame) -> dict:
    """V1~V8 스코어 계산"""
    scores = {}
    signals = {}

    for version in VERSIONS:
        try:
            func = SCORING_FUNCTIONS.get(version)
            if func:
                result = func(df)
                if result:
                    scores[version] = result.get('score', 0)
                    if version == 'v2':
                        signals['v2'] = result.get('signals', [])[:5]
                else:
                    scores[version] = 0
            else:
                scores[version] = 0
        except:
            scores[version] = 0

    return scores, signals


def process_stock(stock_info: dict) -> dict:
    """단일 종목 처리 - 데이터 1회 로드 후 V1~V9 모두 계산"""
    code = stock_info['Code']
    name = stock_info.get('Name', '')
    market = stock_info.get('Market', '')

    try:
        # 데이터 1회만 로드 (V1~V9 공유)
        df = get_stock_data(code)
        if df is None or len(df) < 60:
            return None

        # 현재가 정보
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        current_price = int(latest['Close'])
        prev_close = int(prev['Close'])
        change_rate = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0

        # V1~V8 스코어 계산 (같은 df 사용)
        scores, signals = calculate_scores(df)

        # V9 갭상승 확률 계산 (같은 df 사용)
        v9_prob = predict_v9_prob(df)

        return {
            'code': code,
            'name': name,
            'market': market,
            'open': int(latest.get('Open', 0)),
            'high': int(latest.get('High', 0)),
            'low': int(latest.get('Low', 0)),
            'close': current_price,
            'prev_close': prev_close,
            'change_pct': round(change_rate, 2),
            'volume': int(latest.get('Volume', 0)),
            'amount': int(stock_info.get('Amount', 0)),
            'marcap': int(stock_info.get('Marcap', 0)),
            'v1': scores.get('v1', 0),
            'v2': scores.get('v2', 0),
            'v3.5': scores.get('v3.5', 0),
            'v4': scores.get('v4', 0),
            'v5': scores.get('v5', 0),
            'v6': scores.get('v6', 0),
            'v7': scores.get('v7', 0),
            'v8': scores.get('v8', 0),
            'v9_prob': v9_prob,
            'signals': ','.join(signals.get('v2', [])),
        }
    except:
        return None


def save_to_csv(records: list, recorded_at: datetime) -> str:
    """CSV 파일로 저장"""
    if not records:
        return None

    # 출력 디렉토리 생성
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 파일명: YYYYMMDD_HHMM.csv
    filename = recorded_at.strftime('%Y%m%d_%H%M') + '.csv'
    filepath = OUTPUT_DIR / filename

    df = pd.DataFrame(records)

    # 컬럼 순서 정리
    columns = ['code', 'name', 'market', 'open', 'high', 'low', 'close', 'prev_close',
               'change_pct', 'volume', 'amount', 'marcap',
               'v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9_prob', 'signals']
    df = df[columns]

    # V2 스코어 기준 정렬
    df = df.sort_values('v2', ascending=False)

    df.to_csv(filepath, index=False, encoding='utf-8-sig')

    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description='10분 단위 전 종목 스코어 기록')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드 (저장 안함)')
    args = parser.parse_args()

    recorded_at = datetime.now()
    print("=" * 60)
    print(f"  전 종목 스코어 기록 (V1~V9) - {recorded_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # V9 모델 로드
    print("\n[0] V9 모델 로드...")
    if load_v9_model():
        print(f"    완료: {len(V9_FEATURES)}개 피처")
    else:
        print("    실패 - V9 확률 0으로 처리")

    # 종목 목록
    print("\n[1] 종목 목록 조회 (거래대금 30억+)...")
    stocks_df = get_stock_list()
    if stocks_df.empty:
        print("    종목 없음. 종료.")
        return
    print(f"    {len(stocks_df)}개 종목")

    # 병렬 처리
    print(f"\n[2] 스코어 계산 (V1~V8)...")
    stocks = stocks_df.to_dict('records')
    records = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_stock, s): s for s in stocks}

        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"    {done}/{len(stocks)}...")

            result = future.result()
            if result:
                records.append(result)

    print(f"    완료: {len(records)}개 종목 처리")

    # 저장
    if args.dry_run:
        print("\n[3] 드라이런 모드 - 저장 스킵")
        # V2 상위 10개 출력
        top10_v2 = sorted(records, key=lambda x: x['v2'], reverse=True)[:10]
        print("\n    V2 스코어 상위 10:")
        for r in top10_v2:
            print(f"      {r['code']} {r['name']}: V2={r['v2']}, V4={r['v4']}, V9={r['v9_prob']}%")

        # V9 상위 10개 출력
        top10_v9 = sorted(records, key=lambda x: x['v9_prob'], reverse=True)[:10]
        print("\n    V9 갭상승확률 상위 10:")
        for r in top10_v9:
            print(f"      {r['code']} {r['name']}: V9={r['v9_prob']}%, V2={r['v2']}")
    else:
        print("\n[3] CSV 저장...")
        filepath = save_to_csv(records, recorded_at)
        if filepath:
            print(f"    저장 완료: {filepath}")
        else:
            print("    저장 실패")

    elapsed = (datetime.now() - recorded_at).total_seconds()
    print(f"\n" + "=" * 60)
    print(f"  완료: {elapsed:.1f}초 소요")
    print("=" * 60)


if __name__ == "__main__":
    main()
