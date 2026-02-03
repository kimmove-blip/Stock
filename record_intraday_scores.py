#!/usr/bin/env python3
"""
10분 단위 전 종목 스코어 기록기

- 10분마다 거래대금 30억+ 종목에 대해 V1~V5 스코어 계산
- 주가, 거래량, 거래대금 등 지표 기록
- output/intraday_scores/ 폴더에 CSV 저장
- V4: Hybrid Sniper 전략
- V5: 장대양봉 전략
- 한투 API 연동 시 체결강도, 외국인/기관 수급, 시장지수 추가
- **V2/V4/V5 Delta 자동 계산** (이전 CSV 대비 스코어 변화량)

사용법:
    python record_intraday_scores.py              # 기본 실행 (FDR만 사용)
    python record_intraday_scores.py --kis        # 한투 API 연동 (체결강도/수급 추가)
    python record_intraday_scores.py --dry-run    # 테스트 (저장 안함)
"""

import os
import sys
import argparse
import warnings
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

# 설정
OUTPUT_DIR = PROJECT_ROOT / "output" / "intraday_scores"
MIN_MARKET_CAP = 30_000_000_000      # 300억
MIN_TRADING_AMOUNT = 3_000_000_000   # 30억 (어제 기준)
MAX_WORKERS = 40
VERSIONS = ['v1', 'v2', 'v4', 'v5']  # V1, V2, V4, V5만 사용

# 한투 API 클라이언트 (전역)
KIS_CLIENT = None
USE_KIS_API = False
MARKET_INDEX = {'kospi': 0.0, 'kosdaq': 0.0}  # 시장 지수 변화율

# Delta 계산용 이전 스코어 (전역)
PREV_SCORES = {}  # {code: {'v2': score, 'v4': score, 'v5': score}}

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


def load_previous_scores() -> dict:
    """이전 CSV 파일에서 스코어 로드 (Delta 계산용)"""
    global PREV_SCORES

    try:
        # 오늘 날짜의 CSV 파일 목록
        today_str = datetime.now().strftime('%Y%m%d')
        csv_files = sorted(OUTPUT_DIR.glob(f"{today_str}_*.csv"))

        if not csv_files:
            # 오늘 파일 없으면 어제 마지막 파일
            from datetime import timedelta
            yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            csv_files = sorted(OUTPUT_DIR.glob(f"{yesterday_str}_*.csv"))

        if not csv_files:
            print("    이전 스코어 파일 없음 (Delta 계산 불가)")
            return {}

        # 가장 최근 파일 로드
        latest_file = csv_files[-1]
        df = pd.read_csv(latest_file)
        df['code'] = df['code'].astype(str).str.zfill(6)

        # 스코어 딕셔너리 구성
        prev_scores = {}
        for _, row in df.iterrows():
            code = row['code']
            prev_scores[code] = {
                'v2': row.get('v2', 0),
                'v4': row.get('v4', 0),
                'v5': row.get('v5', 0),
            }

        PREV_SCORES = prev_scores
        print(f"    이전 스코어 로드: {latest_file.name} ({len(prev_scores)}개)")
        return prev_scores

    except Exception as e:
        print(f"    이전 스코어 로드 실패: {e}")
        return {}


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
    """V1~V5 스코어 및 지표 계산"""
    scores = {}
    signals = {}
    indicators = {}

    for version in VERSIONS:
        try:
            func = SCORING_FUNCTIONS.get(version)
            if func:
                result = func(df)
                if result:
                    scores[version] = result.get('score', 0)
                    if version == 'v2':
                        signals['v2'] = result.get('signals', [])[:5]
                        # V2 지표
                        ind = result.get('indicators', {})
                        indicators['rsi'] = round(ind.get('rsi', 0), 1)
                        indicators['sma20_slope'] = round(ind.get('sma20_slope', 0), 2)
                        indicators['volume_ratio'] = round(ind.get('volume_ratio', 0), 2)
                        indicators['trading_value_억'] = round(ind.get('trading_value_억', 0), 1)
                        indicators['high_60d_pct'] = round(ind.get('high_60d_pct', 0), 2)
                    elif version == 'v4':
                        # V4 지표
                        ind = result.get('indicators', {})
                        patterns = result.get('patterns', [])
                        indicators['v4_vcp'] = 1 if 'VCP' in patterns else 0
                        indicators['v4_obv_div'] = 1 if 'OBV_DIV' in patterns else 0
                        indicators['v4_stochrsi'] = round(ind.get('stoch_rsi_k', 0), 1)
                    elif version == 'v5':
                        # V5 지표
                        indicators['v5_pullback'] = result.get('pullback_score', 0)
                        indicators['v5_bb'] = result.get('bollinger_score', 0)
                        indicators['v5_ma'] = result.get('ma_score', 0)
                        indicators['v5_obv'] = result.get('obv_score', 0)
                else:
                    scores[version] = 0
            else:
                scores[version] = 0
        except:
            scores[version] = 0

    return scores, signals, indicators


def process_stock(stock_info: dict) -> dict:
    """단일 종목 처리 - 데이터 1회 로드 후 V1~V5 모두 계산"""
    global USE_KIS_API, MARKET_INDEX, PREV_SCORES

    code = stock_info['Code']
    name = stock_info.get('Name', '')
    market = stock_info.get('Market', '')
    stocks = stock_info.get('Stocks', 0)  # 발행주식수

    try:
        # 데이터 1회만 로드 (V1~V5 공유)
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

        # V1~V5 스코어 계산 (같은 df 사용)
        scores, signals, indicators = calculate_scores(df)

        # Delta 계산 (이전 스코어 대비 변화량)
        prev = PREV_SCORES.get(code, {})
        v2_delta = scores.get('v2', 0) - prev.get('v2', scores.get('v2', 0))
        v4_delta = scores.get('v4', 0) - prev.get('v4', scores.get('v4', 0))
        v5_delta = scores.get('v5', 0) - prev.get('v5', scores.get('v5', 0))

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
            # 스코어
            'v1': scores.get('v1', 0),
            'v2': scores.get('v2', 0),
            'v4': scores.get('v4', 0),
            'v5': scores.get('v5', 0),
            # Delta (스코어 변화량)
            'v2_delta': v2_delta,
            'v4_delta': v4_delta,
            'v5_delta': v5_delta,
            # V2 지표
            'rsi': indicators.get('rsi', 0),
            'sma20_slope': indicators.get('sma20_slope', 0),
            'trading_value_억': indicators.get('trading_value_억', 0),
            'high_60d_pct': indicators.get('high_60d_pct', 0),
            # V4 지표
            'v4_vcp': indicators.get('v4_vcp', 0),
            'v4_obv_div': indicators.get('v4_obv_div', 0),
            'v4_stochrsi': indicators.get('v4_stochrsi', 0),
            # V5 지표
            'v5_pullback': indicators.get('v5_pullback', 0),
            'v5_bb': indicators.get('v5_bb', 0),
            'v5_ma': indicators.get('v5_ma', 0),
            'v5_obv': indicators.get('v5_obv', 0),
            # 시그널
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

    # 컬럼 순서 정리 (체결강도, 수급, 상대강도, volume_ratio, 지표, Delta 추가)
    columns = ['code', 'name', 'market', 'open', 'high', 'low', 'close', 'prev_close',
               'change_pct', 'volume', 'volume_ratio', 'prev_amount', 'prev_marcap',
               'buy_strength', 'foreign_net', 'inst_net', 'rel_strength',
               'v1', 'v2', 'v4', 'v5',
               # Delta (스코어 변화량) - 연구결과 핵심 지표
               'v2_delta', 'v4_delta', 'v5_delta',
               # V2 지표
               'rsi', 'sma20_slope', 'trading_value_억', 'high_60d_pct',
               # V4 지표
               'v4_vcp', 'v4_obv_div', 'v4_stochrsi',
               # V5 지표
               'v5_pullback', 'v5_bb', 'v5_ma', 'v5_obv',
               'signals']

    # 존재하는 컬럼만 선택 (이전 버전 호환)
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    # V2 스코어 기준 정렬
    df = df.sort_values('v2', ascending=False)

    df.to_csv(filepath, index=False, encoding='utf-8-sig')

    return str(filepath)


def run_auto_trader_all():
    """CSV 저장 후 auto_trader.py --all 호출 (전체 사용자)"""
    import subprocess

    script_path = PROJECT_ROOT / "auto_trader.py"
    if not script_path.exists():
        print(f"    [경고] auto_trader.py 없음: {script_path}")
        return False

    print(f"\n[4] auto_trader.py 호출 (--all --intraday)...")
    try:
        cmd = [sys.executable, str(script_path), '--all', '--intraday']
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
    """장 시간(09:00~15:45) 여부 확인"""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=45, second=0, microsecond=0)
    return market_open <= now <= market_close


def main():
    global USE_KIS_API

    parser = argparse.ArgumentParser(description='10분 단위 전 종목 스코어 기록')
    parser.add_argument('--filter', action='store_true', help='장 전 실행: 전일 기준 종목 필터링')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드 (저장 안함)')
    parser.add_argument('--kis', action='store_true', help='한투 API 연동 (체결강도/수급 추가)')
    parser.add_argument('--call-auto-trader', action='store_true',
                        help='CSV 저장 후 auto_trader.py --all 호출')
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
    print(f"  전 종목 스코어 기록 (V1, V2, V4, V5) - {recorded_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.kis:
        print("  [한투 API 모드: 체결강도/수급 데이터 포함]")
    print("=" * 60)

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

    # 이전 스코어 로드 (Delta 계산용)
    print("\n[1.5] 이전 스코어 로드 (Delta 계산용)...")
    load_previous_scores()

    # 병렬 처리
    print(f"\n[2] 스코어 계산 (V1, V2, V4, V5 + Delta)...")
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
            delta_str = f"Δ{r.get('v2_delta', 0):+d}" if r.get('v2_delta', 0) != 0 else ""
            print(f"      {r['code']} {r['name']}: V2={r['v2']}{delta_str}, V4={r['v4']}, V5={r['v5']}")

        # V2 Delta 상위 10개 출력 (급등 후보)
        top10_delta = sorted(records, key=lambda x: x.get('v2_delta', 0), reverse=True)[:10]
        print("\n    V2 Delta 상위 10 (급등 후보):")
        for r in top10_delta:
            if r.get('v2_delta', 0) > 0:
                print(f"      {r['code']} {r['name']}: V2Δ={r['v2_delta']:+d}, V2={r['v2']}, V4={r['v4']}, chg={r['change_pct']:+.1f}%")
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
