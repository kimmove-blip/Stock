#!/usr/bin/env python3
"""
10분 단위 전 종목 스코어 기록기

- 10분마다 거래대금 30억+ 종목에 대해 V1~V9 스코어 계산
- 주가, 거래량, 거래대금 등 지표 기록
- output/intraday_scores/ 폴더에 CSV 저장
- V9: 갭상승 확률 예측 (ML 모델)
- 한투 API 연동 시 체결강도, 외국인/기관 수급, 시장지수 추가

사용법:
    python record_intraday_scores.py              # 기본 실행 (FDR만 사용)
    python record_intraday_scores.py --kis        # 한투 API 연동 (체결강도/수급 추가)
    python record_intraday_scores.py --dry-run    # 테스트 (저장 안함)
"""

import os
import sys
import argparse
import warnings
import pickle
import time
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
from scoring.score_v10_leader_follower import calculate_score_v10, load_reference as load_v10_reference

# 설정
OUTPUT_DIR = PROJECT_ROOT / "output" / "intraday_scores"
V9_MODEL_PATH = PROJECT_ROOT / "models" / "gap_model_v9.pkl"
MIN_MARKET_CAP = 30_000_000_000      # 300억
MIN_TRADING_AMOUNT = 3_000_000_000   # 30억 (어제 기준)
MAX_WORKERS = 40
VERSIONS = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']

# V10 모델 (전역 로드)
V10_REFERENCE = None

# V9 모델 (전역 로드)
V9_MODEL = None
V9_FEATURES = None

# 한투 API 클라이언트 (전역)
KIS_CLIENT = None
USE_KIS_API = False
MARKET_INDEX = {'kospi': 0.0, 'kosdaq': 0.0}  # 시장 지수 변화율

# 출력 즉시 플러시
import functools
print = functools.partial(print, flush=True)


def init_kis_client():
    """한투 API 클라이언트 초기화"""
    global KIS_CLIENT, USE_KIS_API, MARKET_INDEX

    try:
        from api.services.kis_client import KISClient

        # 환경변수에서 API 키 확인
        app_key = os.getenv("KIS_APP_KEY")
        app_secret = os.getenv("KIS_APP_SECRET")

        if not app_key or not app_secret:
            print("    [경고] 한투 API 키 미설정 (KIS_APP_KEY, KIS_APP_SECRET)")
            return False

        KIS_CLIENT = KISClient(is_virtual=False)  # 실전 API로 시세 조회
        USE_KIS_API = True

        # 시장 지수 조회
        try:
            kospi = KIS_CLIENT.get_index_price("0001")
            kosdaq = KIS_CLIENT.get_index_price("1001")
            if kospi:
                MARKET_INDEX['kospi'] = kospi.get('change_rate', 0.0)
            if kosdaq:
                MARKET_INDEX['kosdaq'] = kosdaq.get('change_rate', 0.0)
            print(f"    시장지수: KOSPI {MARKET_INDEX['kospi']:+.2f}%, KOSDAQ {MARKET_INDEX['kosdaq']:+.2f}%")
        except Exception as e:
            print(f"    [경고] 시장지수 조회 실패: {e}")

        return True

    except Exception as e:
        print(f"    [경고] 한투 API 초기화 실패: {e}")
        return False


def get_kis_extra_data(code: str) -> dict:
    """한투 API로 체결강도, 외국인/기관 수급 조회"""
    global KIS_CLIENT

    result = {
        'buy_strength': 0.0,    # 체결강도
        'foreign_net': 0,       # 외국인 당일 순매수
        'inst_net': 0,          # 기관 당일 순매수
    }

    if not KIS_CLIENT:
        return result

    try:
        # 체결강도 조회
        ccnl = KIS_CLIENT.get_conclusion_trend(code)
        if ccnl:
            result['buy_strength'] = ccnl.get('buy_strength', 0.0)

        # 외국인/기관 수급 조회 (당일)
        investor = KIS_CLIENT.get_investor_trend(code, days=1)
        if investor and investor.get('daily'):
            today = investor['daily'][0]
            result['foreign_net'] = today.get('foreign_net', 0)
            result['inst_net'] = today.get('institution_net', 0)

    except Exception:
        pass

    return result


def load_v10_model():
    """V10 레퍼런스 로드"""
    global V10_REFERENCE
    try:
        V10_REFERENCE = load_v10_reference()
        return V10_REFERENCE is not None
    except Exception as e:
        print(f"[경고] V10 레퍼런스 로드 실패: {e}")
        return False


def calculate_v10_scores(records: list) -> list:
    """모든 종목에 대해 V10 스코어 계산"""
    global V10_REFERENCE

    if not V10_REFERENCE:
        for r in records:
            r['v10'] = 0
        return records

    # today_changes 딕셔너리 생성 (종목코드 -> 등락률)
    today_changes = {r['code']: r['change_pct'] for r in records}

    # 종속주 목록 (V10 레퍼런스에서)
    follower_to_leaders = V10_REFERENCE.get('follower_to_leaders', {})

    for r in records:
        code = r['code']

        # 이 종목이 종속주인지 확인
        leaders = follower_to_leaders.get(code, [])

        if not leaders:
            r['v10'] = 0
            continue

        # 최적의 대장주 찾기
        best_score = 0

        for leader_info in leaders:
            leader_code = leader_info.get('leader_code')
            correlation = leader_info.get('correlation', 0)

            leader_change = today_changes.get(leader_code, 0)
            follower_change = r['change_pct']
            gap = leader_change - follower_change

            # 대장주 상승 + 종속주 미추종 조건
            if leader_change >= 2.0 and gap > 1.0:
                # 점수 계산 (간소화 버전)
                score = 50

                # 대장주 움직임 점수 (35점)
                if leader_change >= 5:
                    score += 35
                elif leader_change >= 3:
                    score += 25
                else:
                    score += 15

                # 상관관계 점수 (25점)
                if correlation >= 0.85:
                    score += 25
                elif correlation >= 0.75:
                    score += 20
                elif correlation >= 0.65:
                    score += 15
                else:
                    score += 10

                # 캐치업 갭 점수 (25점)
                if gap >= 4:
                    score += 25
                elif gap >= 3:
                    score += 20
                elif gap >= 2:
                    score += 15
                else:
                    score += 10

                if score > best_score:
                    best_score = score

        r['v10'] = min(best_score, 100)  # 최대 100점

    return records


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


def get_filtered_stocks_path(date_str: str = None) -> Path:
    """필터링된 종목 CSV 경로"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    return PROJECT_ROOT / "output" / f"filtered_stocks_{date_str}.csv"


def create_filtered_stocks() -> pd.DataFrame:
    """06:00 실행: FDR 전일 마감 데이터로 종목 필터링 후 CSV 저장

    06:00에는 FDR.StockListing이 전일 마감 데이터를 반환함
    - Marcap: 전일 시가총액
    - Amount: 전일 거래대금
    """
    print("전일 데이터 기준 종목 필터링 시작...")

    krx = fdr.StockListing("KRX")
    df = krx[["Code", "Name", "Market", "Marcap", "Amount", "Stocks"]].copy()
    df["Code"] = df["Code"].astype(str).str.zfill(6)

    print(f"  전체 종목: {len(df)}개")

    # 시총 300억+ 필터
    if df["Marcap"].notna().sum() > 100:
        df = df[df["Marcap"] >= MIN_MARKET_CAP]
        print(f"  시총 300억+ 필터: {len(df)}개")
    else:
        print(f"  [경고] Marcap 데이터 없음")

    # 거래대금 30억+ 필터
    if df["Amount"].notna().sum() > 100:
        df = df[df["Amount"] >= MIN_TRADING_AMOUNT]
        print(f"  거래대금 30억+ 필터: {len(df)}개")
    else:
        print(f"  [경고] Amount 데이터 없음")

    # 특수종목/우선주 제외
    exclude_keywords = ["스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지"]
    for kw in exclude_keywords:
        df = df[~df["Name"].str.contains(kw, case=False, na=False)]
    df = df[df["Code"].str[-1] == "0"]

    print(f"  최종 필터 후: {len(df)}개")

    # CSV 저장
    csv_path = get_filtered_stocks_path()
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"  저장 완료: {csv_path}")

    return df


def get_stock_list() -> pd.DataFrame:
    """장중 실행: 오늘 필터링된 종목 CSV 로드"""
    try:
        csv_path = get_filtered_stocks_path()

        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df["Code"] = df["Code"].astype(str).str.zfill(6)
            print(f"    필터 종목 로드: {csv_path.name} ({len(df)}개)")
            return df
        else:
            print(f"    [경고] 필터 파일 없음: {csv_path.name}")
            print(f"    → 장 전에 --filter 옵션으로 먼저 실행 필요")
            return pd.DataFrame()

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
    global USE_KIS_API, MARKET_INDEX

    code = stock_info['Code']
    name = stock_info.get('Name', '')
    market = stock_info.get('Market', '')
    stocks = stock_info.get('Stocks', 0)  # 발행주식수

    try:
        # 데이터 1회만 로드 (V1~V9 공유)
        df = get_stock_data(code)
        if df is None or len(df) < 60:
            return None

        # 현재가 정보
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # 전일 거래대금 필터 (30억+)
        prev_amount = int(prev['Close'] * prev['Volume'])
        if prev_amount < MIN_TRADING_AMOUNT:
            return None

        # 전일 시총 계산 (전일종가 × 발행주식수)
        prev_marcap = int(prev['Close'] * stocks) if stocks > 0 else 0

        current_price = int(latest['Close'])
        prev_close = int(prev['Close'])
        change_rate = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0

        # 거래량 비율 계산 (5일 평균 대비)
        avg_volume_5d = df['Volume'].tail(6).head(5).mean()  # 오늘 제외 최근 5일
        current_volume = int(latest.get('Volume', 0))
        volume_ratio = round(current_volume / avg_volume_5d, 2) if avg_volume_5d > 0 else 1.0

        # V1~V8 스코어 계산 (같은 df 사용)
        scores, signals = calculate_scores(df)

        # V9 갭상승 확률 계산 (같은 df 사용)
        v9_prob = predict_v9_prob(df)

        result = {
            'code': code,
            'name': name,
            'market': market,
            'open': int(latest.get('Open', 0)),
            'high': int(latest.get('High', 0)),
            'low': int(latest.get('Low', 0)),
            'close': current_price,
            'prev_close': prev_close,
            'change_pct': round(change_rate, 2),
            'volume': current_volume,
            'volume_ratio': volume_ratio,  # 5일 평균 대비 거래량 비율
            'prev_amount': prev_amount,  # 전일 거래대금
            'prev_marcap': prev_marcap,  # 전일 시총
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

        # 한투 API 데이터 추가 (체결강도, 외국인/기관 수급)
        if USE_KIS_API:
            kis_data = get_kis_extra_data(code)
            result['buy_strength'] = kis_data['buy_strength']
            result['foreign_net'] = kis_data['foreign_net']
            result['inst_net'] = kis_data['inst_net']
            # 시장 대비 상대강도
            market_chg = MARKET_INDEX.get('kosdaq' if 'KOSDAQ' in market else 'kospi', 0.0)
            result['rel_strength'] = round(change_rate - market_chg, 2)
        else:
            result['buy_strength'] = 0.0
            result['foreign_net'] = 0
            result['inst_net'] = 0
            result['rel_strength'] = 0.0

        return result
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

    # 컬럼 순서 정리 (체결강도, 수급, 상대강도, V10, volume_ratio 추가)
    columns = ['code', 'name', 'market', 'open', 'high', 'low', 'close', 'prev_close',
               'change_pct', 'volume', 'volume_ratio', 'prev_amount', 'prev_marcap',
               'buy_strength', 'foreign_net', 'inst_net', 'rel_strength',
               'v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9_prob', 'v10', 'signals']

    # 존재하는 컬럼만 선택 (이전 버전 호환)
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    # V2 스코어 기준 정렬
    df = df.sort_values('v2', ascending=False)

    df.to_csv(filepath, index=False, encoding='utf-8-sig')

    return str(filepath)


def run_auto_trader_all():
    """CSV 저장 후 auto_trader.py --use-csv --all 호출 (전체 사용자)"""
    import subprocess

    script_path = PROJECT_ROOT / "auto_trader.py"
    if not script_path.exists():
        print(f"    [경고] auto_trader.py 없음: {script_path}")
        return False

    print(f"\n[4] auto_trader.py 호출 (--use-csv --all --intraday)...")
    try:
        cmd = [sys.executable, str(script_path), '--use-csv', '--all', '--intraday']
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300  # 5분 타임아웃
        )

        if result.returncode == 0:
            print(f"    auto_trader 완료")
            # 주요 결과만 출력
            for line in result.stdout.split('\n'):
                if any(kw in line for kw in ['매수', '매도', '청산', 'USER', '완료', '결과']):
                    print(f"    {line}")
            return True
        else:
            print(f"    auto_trader 실패 (code={result.returncode})")
            if result.stderr:
                print(f"    에러: {result.stderr[:300]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"    auto_trader 타임아웃 (5분)")
        return False
    except Exception as e:
        print(f"    auto_trader 호출 오류: {e}")
        return False


def is_market_hours() -> bool:
    """장 시간(09:00~15:20) 여부 확인"""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=20, second=0, microsecond=0)
    return market_open <= now <= market_close


def main():
    global USE_KIS_API

    parser = argparse.ArgumentParser(description='10분 단위 전 종목 스코어 기록')
    parser.add_argument('--filter', action='store_true', help='장 전 실행: 전일 기준 종목 필터링')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드 (저장 안함)')
    parser.add_argument('--kis', action='store_true', help='한투 API 연동 (체결강도/수급 추가)')
    parser.add_argument('--call-auto-trader', action='store_true',
                        help='CSV 저장 후 auto_trader.py --use-csv --all 호출')
    args = parser.parse_args()

    # 장 전 필터링 모드
    if args.filter:
        print("=" * 60)
        print(f"  종목 필터링 (장 전 실행) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        create_filtered_stocks()
        return

    recorded_at = datetime.now()
    print("=" * 60)
    print(f"  전 종목 스코어 기록 (V1~V10) - {recorded_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.kis:
        print("  [한투 API 모드: 체결강도/수급 데이터 포함]")
    print("=" * 60)

    # V9 모델 로드
    print("\n[0] V9 모델 로드...")
    if load_v9_model():
        print(f"    완료: {len(V9_FEATURES)}개 피처")
    else:
        print("    실패 - V9 확률 0으로 처리")

    # V10 레퍼런스 로드
    print("\n[0.1] V10 레퍼런스 로드...")
    if load_v10_model():
        follower_count = len(V10_REFERENCE.get('follower_to_leaders', {}))
        print(f"    완료: {follower_count}개 종속주 매핑")
    else:
        print("    실패 - V10 점수 0으로 처리")

    # 한투 API 초기화 (--kis 옵션)
    if args.kis:
        print("\n[0.5] 한투 API 초기화...")
        if init_kis_client():
            print("    완료")
        else:
            print("    실패 - 체결강도/수급 데이터 없이 진행")
            USE_KIS_API = False

    # 종목 목록
    print("\n[1] 종목 목록 조회...")
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

    # V10 스코어 계산 (모든 종목 등락률 필요)
    print(f"\n[2.5] V10 스코어 계산 (Leader-Follower)...")
    records = calculate_v10_scores(records)
    v10_active = len([r for r in records if r.get('v10', 0) > 50])
    print(f"    완료: {v10_active}개 종목 활성 시그널")

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

        # V10 상위 10개 출력
        top10_v10 = sorted(records, key=lambda x: x.get('v10', 0), reverse=True)[:10]
        print("\n    V10 Leader-Follower 상위 10:")
        for r in top10_v10:
            print(f"      {r['code']} {r['name']}: V10={r.get('v10', 0)}, 등락률={r['change_pct']:+.2f}%")
    else:
        print("\n[3] CSV 저장...")
        filepath = save_to_csv(records, recorded_at)
        if filepath:
            print(f"    저장 완료: {filepath}")
        else:
            print("    저장 실패")

    # auto_trader 호출 (--call-auto-trader 옵션)
    if args.call_auto_trader and not args.dry_run and filepath:
        if is_market_hours():
            run_auto_trader_all()
        else:
            print(f"\n[4] 장 운영 시간 아님 - auto_trader 호출 건너뜀")

    elapsed = (datetime.now() - recorded_at).total_seconds()
    print(f"\n" + "=" * 60)
    print(f"  완료: {elapsed:.1f}초 소요")
    print("=" * 60)


if __name__ == "__main__":
    main()
