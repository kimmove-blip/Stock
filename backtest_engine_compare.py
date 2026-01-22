"""
V1/V2/V4 스크리닝 엔진 5일 백테스트
- 최근 5거래일 동안 각 엔진으로 TOP 100 선정 (해당 날짜 기준 과거 데이터 사용)
- 다음날 OHLCV 데이터와 비교하여 수익률 분석
"""
import argparse
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import time

from scoring import SCORING_FUNCTIONS
from config import calculate_signal_weight

warnings.filterwarnings("ignore")


def get_trading_days(n_days=6):
    """
    최근 n개의 거래일 조회 (KOSPI 지수 기준)

    Args:
        n_days: 조회할 거래일 수 (기본 6일: 5일 스크리닝 + 1일 수익률 확인)

    Returns:
        list: 거래일 리스트 (오래된 순)
    """
    print(f"최근 {n_days}거래일 조회 중...")

    # 오늘 기준 최근 45일 데이터 조회 (충분한 마진)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)

    try:
        # KOSPI 지수로 거래일 조회
        kospi = fdr.DataReader('KS11', start_date, end_date)

        if kospi.empty:
            print("  → KOSPI 데이터 조회 실패")
            return []

        # 인덱스에서 날짜 추출
        trading_days = kospi.index.tolist()

        # 최근 n_days개 선택 (오래된 순)
        recent_days = trading_days[-n_days:]

        print(f"  → {len(recent_days)}개 거래일 조회 완료")
        for i, day in enumerate(recent_days):
            day_str = day.strftime('%Y-%m-%d')
            if i < len(recent_days) - 1:
                print(f"      {i+1}. {day_str} (스크리닝)")
            else:
                print(f"      {i+1}. {day_str} (수익률 확인)")

        return recent_days

    except Exception as e:
        print(f"  → 거래일 조회 실패: {e}")
        return []


def load_stock_list(min_marcap=30_000_000_000, max_marcap=1_000_000_000_000, min_amount=300_000_000):
    """
    KRX 전체 종목 중 유동성 기준 통과 종목 로딩

    Returns:
        DataFrame: 필터링된 종목 목록
    """
    print("\nKRX 종목 로딩 중...")

    try:
        krx = fdr.StockListing("KRX")
        columns_needed = ["Code", "Name", "Market", "Marcap", "Volume", "Amount", "Close"]
        available_cols = [c for c in columns_needed if c in krx.columns]
        df = krx[available_cols].copy()

        # 종목코드 6자리 맞추기
        df["Code"] = df["Code"].astype(str).str.zfill(6)
        print(f"  → 총 {len(df):,}개 종목 로딩")

        # 시가총액 필터
        if "Marcap" in df.columns:
            df = df[df["Marcap"] >= min_marcap]
            if max_marcap:
                df = df[df["Marcap"] <= max_marcap]

        # 거래대금 필터
        if "Amount" in df.columns:
            df = df[df["Amount"] >= min_amount]

        # 특수종목 제외
        exclude_keywords = ["스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지",
                           "합병", "정리매매", "관리종목", "투자주의", "투자경고", "투자위험"]
        for keyword in exclude_keywords:
            df = df[~df["Name"].str.contains(keyword, case=False, na=False)]

        # 우선주 제외
        df = df[df["Code"].str[-1] == "0"]

        print(f"  → {len(df):,}개 종목 필터링 완료")

        return df

    except Exception as e:
        print(f"  → 종목 로딩 실패: {e}")
        return pd.DataFrame()


def get_stock_ohlcv_all(code: str, start_date: datetime, end_date: datetime):
    """
    특정 기간의 OHLCV 데이터 조회

    Args:
        code: 종목코드
        start_date: 시작일
        end_date: 종료일

    Returns:
        DataFrame: OHLCV 데이터
    """
    try:
        df = fdr.DataReader(code, start_date, end_date)
        if df.empty:
            return None
        return df
    except Exception as e:
        return None


def analyze_stock_for_date(code: str, name: str, market: str, screening_date: datetime,
                           scoring_func, ohlcv_cache: dict = None) -> dict:
    """
    특정 날짜 기준으로 종목 분석

    Args:
        code: 종목코드
        name: 종목명
        market: 시장구분
        screening_date: 스크리닝 기준 날짜
        scoring_func: 스코어링 함수
        ohlcv_cache: OHLCV 데이터 캐시 (선택)

    Returns:
        dict: 분석 결과
    """
    try:
        # 데이터 로드 (캐시 또는 FDR)
        if ohlcv_cache and code in ohlcv_cache:
            df_full = ohlcv_cache[code]
        else:
            # 스크리닝 날짜 기준 1년 전부터 데이터 조회
            start = screening_date - timedelta(days=400)
            df_full = get_stock_ohlcv_all(code, start, screening_date + timedelta(days=10))

            if df_full is None or len(df_full) < 60:
                return None

            if ohlcv_cache is not None:
                ohlcv_cache[code] = df_full

        # 스크리닝 날짜까지의 데이터만 사용
        screening_ts = pd.Timestamp(screening_date).normalize()
        df_full.index = pd.to_datetime(df_full.index).normalize()
        df = df_full[df_full.index <= screening_ts].copy()

        if len(df) < 60:
            return None

        # 스코어링 수행
        result = scoring_func(df)

        if result is None:
            return None

        indicators = result.get("indicators", {})

        return {
            "code": code,
            "name": name,
            "market": market,
            "score": result["score"],
            "signals": result["signals"],
            "indicators": indicators,
            "close": indicators.get("close", df.iloc[-1]["Close"]),
            "volume": indicators.get("volume", df.iloc[-1]["Volume"]),
            "change_pct": indicators.get("change_pct", 0),
            "version": result.get("version", ""),
        }

    except Exception as e:
        return None


def run_screening_for_date(stock_list: pd.DataFrame, screening_date: datetime,
                           scoring_version: str, top_n: int = 100,
                           ohlcv_cache: dict = None, max_workers: int = 10) -> list:
    """
    특정 날짜 기준 스크리닝 실행

    Args:
        stock_list: 종목 목록 DataFrame
        screening_date: 스크리닝 날짜
        scoring_version: 스코어링 버전 (v1, v2, v4)
        top_n: 상위 종목 수
        ohlcv_cache: OHLCV 캐시 딕셔너리
        max_workers: 병렬 처리 워커 수

    Returns:
        list: 스크리닝 결과 (상위 top_n개)
    """
    date_str = screening_date.strftime('%Y-%m-%d')
    print(f"\n  [{scoring_version.upper()}] {date_str} 스크리닝 중...")

    scoring_func = SCORING_FUNCTIONS.get(scoring_version)

    if scoring_func is None:
        print(f"    → 알 수 없는 스코어링 버전: {scoring_version}")
        return []

    stocks_to_analyze = stock_list.to_dict("records")
    total = len(stocks_to_analyze)
    results = []
    completed = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_stock = {
            executor.submit(
                analyze_stock_for_date,
                stock["Code"], stock["Name"], stock.get("Market", ""),
                screening_date, scoring_func, ohlcv_cache
            ): stock
            for stock in stocks_to_analyze
        }

        for future in as_completed(future_to_stock):
            completed += 1
            result = future.result()
            if result is not None:
                results.append(result)

            if completed % 100 == 0 or completed == total:
                elapsed = time.time() - start_time
                print(f"    → 진행: {completed:,}/{total:,} | 유효: {len(results):,} | {elapsed:.0f}초")

    # 점수 기준 정렬 및 상위 추출
    def sort_key(stock):
        signals = stock.get("signals", [])
        return (-stock["score"], -calculate_signal_weight(signals), -len(signals))

    sorted_results = sorted(results, key=sort_key)
    top_stocks = sorted_results[:top_n]

    print(f"    → {len(top_stocks)}개 선정 완료")

    return top_stocks


def get_next_day_ohlcv(code: str, next_date: datetime, ohlcv_cache: dict = None) -> dict:
    """
    다음 거래일 OHLCV 조회

    Args:
        code: 종목코드
        next_date: 조회할 날짜
        ohlcv_cache: OHLCV 캐시

    Returns:
        dict: OHLCV 데이터
    """
    try:
        if ohlcv_cache and code in ohlcv_cache:
            df = ohlcv_cache[code]
        else:
            start = next_date - timedelta(days=5)
            end = next_date + timedelta(days=5)
            df = fdr.DataReader(code, start, end)

            if df is None or df.empty:
                return None

        next_ts = pd.Timestamp(next_date).normalize()
        df.index = pd.to_datetime(df.index).normalize()

        if next_ts in df.index:
            row = df.loc[next_ts]
            return {
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row['Volume']),
            }

        return None

    except Exception as e:
        return None


def run_backtest(days: int = 5, top_n: int = 100, engines: list = None, max_workers: int = 10):
    """
    백테스트 메인 함수

    Args:
        days: 백테스트 기간 (거래일 수)
        top_n: 각 엔진별 상위 종목 수
        engines: 테스트할 엔진 리스트 (기본: v1, v2, v3, v4)
        max_workers: 병렬 처리 워커 수

    Returns:
        DataFrame: 백테스트 결과
    """
    if engines is None:
        engines = ['v1', 'v2', 'v3', 'v4']

    print("\n" + "="*70)
    print("  V1/V2/V4 스크리닝 엔진 백테스트")
    print("="*70)
    print(f"  - 테스트 기간: {days}거래일")
    print(f"  - 테스트 엔진: {', '.join([e.upper() for e in engines])}")
    print(f"  - 종목 수: 각 엔진별 TOP {top_n}")
    print(f"  - 총 스크리닝 횟수: {days} × {len(engines)} = {days * len(engines)}회")
    print("="*70)

    start_time = time.time()

    # 1. 거래일 조회
    trading_days = get_trading_days(n_days=days + 1)

    if len(trading_days) < 2:
        print("거래일 데이터 부족")
        return None

    screening_days = trading_days[:-1]  # 스크리닝 날짜
    return_days = trading_days[1:]       # 수익률 확인 날짜

    # 2. 종목 목록 로딩
    stock_list = load_stock_list()

    if stock_list.empty:
        print("종목 목록 로딩 실패")
        return None

    # 3. OHLCV 캐시 (메모리 효율을 위해 날짜별로 분리)
    all_results = []

    # 4. 각 스크리닝 날짜별로 처리
    for i, screening_date in enumerate(screening_days):
        next_date = return_days[i]

        screening_str = screening_date.strftime('%Y-%m-%d')
        next_str = next_date.strftime('%Y-%m-%d')

        print(f"\n{'#'*70}")
        print(f"  [{i+1}/{len(screening_days)}] 스크리닝: {screening_str} → 수익률: {next_str}")
        print(f"{'#'*70}")

        # OHLCV 캐시 (날짜별로 리셋)
        ohlcv_cache = {}

        # 각 엔진별 스크리닝
        for engine in engines:
            top_stocks = run_screening_for_date(
                stock_list=stock_list,
                screening_date=screening_date,
                scoring_version=engine,
                top_n=top_n,
                ohlcv_cache=ohlcv_cache,
                max_workers=max_workers
            )

            # 다음날 수익률 계산
            print(f"    → {engine.upper()} 다음날 수익률 계산 중...")
            processed = 0

            for rank, stock in enumerate(top_stocks, 1):
                code = stock['code']
                next_ohlcv = get_next_day_ohlcv(code, next_date, ohlcv_cache)

                if next_ohlcv:
                    base_price = stock['close']
                    next_change_pct = ((next_ohlcv['close'] - base_price) / base_price) * 100 if base_price > 0 else 0

                    all_results.append({
                        'date': screening_str,
                        'code': code,
                        'name': stock['name'],
                        'engine': engine,
                        'score': stock['score'],
                        'rank': rank,
                        'base_close': base_price,
                        'next_open': next_ohlcv['open'],
                        'next_high': next_ohlcv['high'],
                        'next_low': next_ohlcv['low'],
                        'next_close': next_ohlcv['close'],
                        'next_volume': next_ohlcv['volume'],
                        'next_change_pct': round(next_change_pct, 2),
                    })
                    processed += 1

            print(f"      완료: {processed}/{len(top_stocks)}개")

        # 메모리 해제
        del ohlcv_cache

    # 5. DataFrame 생성
    if not all_results:
        print("\n결과 없음")
        return None

    df = pd.DataFrame(all_results)

    elapsed = time.time() - start_time
    print(f"\n총 소요시간: {elapsed/60:.1f}분")

    return df


def create_summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    엔진별/점수대별 통계 요약 생성
    """
    if df is None or df.empty:
        return None

    summaries = []

    # 전체 엔진별 통계
    for engine in df['engine'].unique():
        engine_df = df[df['engine'] == engine]

        summaries.append({
            'engine': engine.upper(),
            'score_range': '전체',
            'count': len(engine_df),
            'avg_change_pct': round(engine_df['next_change_pct'].mean(), 2),
            'median_change_pct': round(engine_df['next_change_pct'].median(), 2),
            'std_change_pct': round(engine_df['next_change_pct'].std(), 2),
            'positive_rate': round((engine_df['next_change_pct'] > 0).sum() / len(engine_df) * 100, 1),
            'avg_score': round(engine_df['score'].mean(), 1),
        })

        # 점수대별 통계
        score_ranges = [
            ('80점 이상', 80, 101),
            ('70-79점', 70, 80),
            ('60-69점', 60, 70),
            ('60점 미만', 0, 60),
        ]

        for label, min_score, max_score in score_ranges:
            range_df = engine_df[(engine_df['score'] >= min_score) & (engine_df['score'] < max_score)]

            if len(range_df) > 0:
                summaries.append({
                    'engine': engine.upper(),
                    'score_range': label,
                    'count': len(range_df),
                    'avg_change_pct': round(range_df['next_change_pct'].mean(), 2),
                    'median_change_pct': round(range_df['next_change_pct'].median(), 2),
                    'std_change_pct': round(range_df['next_change_pct'].std(), 2),
                    'positive_rate': round((range_df['next_change_pct'] > 0).sum() / len(range_df) * 100, 1),
                    'avg_score': round(range_df['score'].mean(), 1),
                })

    return pd.DataFrame(summaries)


def create_rank_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    순위별 수익률 분석
    """
    if df is None or df.empty:
        return None

    analysis = []

    rank_ranges = [
        ('TOP 10', 1, 11),
        ('TOP 20', 1, 21),
        ('TOP 50', 1, 51),
        ('TOP 100', 1, 101),
        ('11-30위', 11, 31),
        ('31-50위', 31, 51),
        ('51-100위', 51, 101),
    ]

    for engine in df['engine'].unique():
        engine_df = df[df['engine'] == engine]

        for label, min_rank, max_rank in rank_ranges:
            range_df = engine_df[(engine_df['rank'] >= min_rank) & (engine_df['rank'] < max_rank)]

            if len(range_df) > 0:
                analysis.append({
                    'engine': engine.upper(),
                    'rank_range': label,
                    'count': len(range_df),
                    'avg_change_pct': round(range_df['next_change_pct'].mean(), 2),
                    'median_change_pct': round(range_df['next_change_pct'].median(), 2),
                    'positive_rate': round((range_df['next_change_pct'] > 0).sum() / len(range_df) * 100, 1),
                })

    return pd.DataFrame(analysis)


def save_to_excel(df: pd.DataFrame, summary_df: pd.DataFrame, rank_df: pd.DataFrame, output_path: str):
    """
    Excel 파일로 저장
    """
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sheet 1: 전체 데이터
        df.to_excel(writer, sheet_name='전체데이터', index=False)

        # Sheet 2: 통계 요약
        if summary_df is not None:
            summary_df.to_excel(writer, sheet_name='엔진별통계', index=False)

        # Sheet 3: 순위별 분석
        if rank_df is not None:
            rank_df.to_excel(writer, sheet_name='순위별분석', index=False)

        # Sheet 4: 날짜별 엔진 비교
        if not df.empty:
            date_engine_stats = df.groupby(['date', 'engine']).agg({
                'next_change_pct': ['mean', 'median', 'count', 'std'],
                'score': 'mean',
            }).round(2)
            date_engine_stats.columns = ['평균등락률', '중앙값등락률', '종목수', '표준편차', '평균점수']
            date_engine_stats.reset_index().to_excel(writer, sheet_name='날짜별비교', index=False)

    print(f"\n결과 저장 완료: {output_path}")


def print_summary(df: pd.DataFrame, summary_df: pd.DataFrame, rank_df: pd.DataFrame):
    """
    결과 요약 출력
    """
    print("\n" + "="*70)
    print("  백테스트 결과 요약")
    print("="*70)

    if summary_df is None or summary_df.empty:
        print("데이터 없음")
        return

    # 전체 엔진별 통계
    overall = summary_df[summary_df['score_range'] == '전체']

    print("\n[엔진별 전체 성과]")
    print("-"*70)
    print(f"{'엔진':^6} | {'종목수':>6} | {'평균등락률':>10} | {'중앙값':>8} | {'표준편차':>8} | {'양봉비율':>8}")
    print("-"*70)

    for _, row in overall.iterrows():
        print(f"{row['engine']:^6} | {row['count']:>6} | {row['avg_change_pct']:>+9.2f}% | "
              f"{row['median_change_pct']:>+7.2f}% | {row['std_change_pct']:>7.2f}% | {row['positive_rate']:>7.1f}%")

    print("-"*70)

    # 80점 이상 고득점 종목
    high_score = summary_df[(summary_df['score_range'] == '80점 이상') & (summary_df['count'] > 0)]

    if not high_score.empty:
        print("\n[80점 이상 고득점 종목 성과]")
        print("-"*70)

        for _, row in high_score.iterrows():
            print(f"{row['engine']:^6} | {row['count']:>6} | {row['avg_change_pct']:>+9.2f}% | "
                  f"{row['median_change_pct']:>+7.2f}% | {row['std_change_pct']:>7.2f}% | {row['positive_rate']:>7.1f}%")

        print("-"*70)

    # TOP 10 성과
    if rank_df is not None and not rank_df.empty:
        top10 = rank_df[rank_df['rank_range'] == 'TOP 10']

        if not top10.empty:
            print("\n[TOP 10 성과]")
            print("-"*60)

            for _, row in top10.iterrows():
                print(f"{row['engine']:^6} | {row['count']:>4}개 | {row['avg_change_pct']:>+9.2f}% | "
                      f"{row['median_change_pct']:>+7.2f}% | {row['positive_rate']:>6.1f}%")

            print("-"*60)


def main():
    parser = argparse.ArgumentParser(description='V1/V2/V4 스크리닝 엔진 백테스트')
    parser.add_argument('--days', type=int, default=5, help='백테스트 기간 (거래일 수)')
    parser.add_argument('--top', type=int, default=100, help='각 엔진별 상위 종목 수')
    parser.add_argument('--engines', nargs='+', default=['v1', 'v2', 'v3', 'v4'],
                        help='테스트할 엔진 (v1, v2, v3, v4)')
    parser.add_argument('--workers', type=int, default=10, help='병렬 처리 워커 수')
    parser.add_argument('--output', type=str, default=None,
                        help='출력 파일 경로 (기본: output/backtest_v1_v2_v4_5days_YYYYMMDD.xlsx)')

    args = parser.parse_args()

    # 백테스트 실행
    df = run_backtest(
        days=args.days,
        top_n=args.top,
        engines=args.engines,
        max_workers=args.workers
    )

    if df is None or df.empty:
        print("백테스트 결과 없음")
        return

    # 통계 요약 생성
    summary_df = create_summary_stats(df)
    rank_df = create_rank_analysis(df)

    # 결과 출력
    print_summary(df, summary_df, rank_df)

    # Excel 저장
    if args.output:
        output_path = args.output
    else:
        today_str = datetime.now().strftime('%Y%m%d')
        output_path = f"output/backtest_v1_v2_v4_{args.days}days_{today_str}.xlsx"

    save_to_excel(df, summary_df, rank_df, output_path)


if __name__ == "__main__":
    main()
