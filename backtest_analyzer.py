#!/usr/bin/env python3
"""
TOP100 적중률 백테스트 분석 모듈

주요 기능:
1. 과거 top100 JSON 파일 로드
2. 10일간 주가 데이터 조회 (fdr)
3. 일차별 수익률 계산
4. 적중률 분석 (점수대별, 신호별)
5. 결과 리포트 생성

사용법:
    python backtest_analyzer.py              # 기본 실행 (전체 과거 데이터)
    python backtest_analyzer.py --days 3     # 최근 3일 데이터만
    python backtest_analyzer.py --export     # Excel 리포트 생성
"""

import argparse
import json
import glob
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import pandas as pd
import FinanceDataReader as fdr
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import OUTPUT_DIR, SIGNAL_NAMES_KR, get_signal_kr


def load_historical_selections(days: int = 30) -> List[dict]:
    """
    과거 top100 JSON 파일 로드

    Args:
        days: 로드할 과거 일수 (기본 30일)

    Returns:
        List of {date, stocks: []} 형태의 데이터
    """
    json_files = sorted(
        glob.glob(str(OUTPUT_DIR / "top100_*.json")),
        reverse=True  # 최신순
    )[:days]

    historical_data = []

    for filepath in json_files:
        try:
            # 파일명에서 날짜 추출 (top100_20260116.json -> 2026-01-16)
            filename = Path(filepath).stem
            date_str = filename.split('_')[1]
            date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            stocks = data.get('stocks', [])

            historical_data.append({
                'date': date,
                'filepath': filepath,
                'stocks': stocks
            })

        except Exception as e:
            print(f"[경고] 파일 로드 실패 ({filepath}): {e}")

    return historical_data


def fetch_price_data(code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    종목의 OHLC 데이터 조회

    Args:
        code: 종목코드
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD)

    Returns:
        DataFrame with OHLC data
    """
    try:
        df = fdr.DataReader(code, start_date, end_date)
        if not df.empty:
            return df
    except Exception:
        pass
    return None


def calculate_daily_returns(
    selection_date: str,
    stocks: List[dict],
    holding_days: int = 10,
    max_workers: int = 10
) -> List[dict]:
    """
    선정일 이후 N일간 일차별 수익률 계산

    Args:
        selection_date: 선정일 (YYYY-MM-DD)
        stocks: 선정 종목 리스트
        holding_days: 추적 일수 (기본 10일)
        max_workers: 병렬 처리 워커 수

    Returns:
        각 종목의 일차별 수익률 데이터
    """
    # 날짜 계산 (선정일 다음날부터 추적)
    sel_date = datetime.strptime(selection_date, "%Y-%m-%d")
    start_date = (sel_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (sel_date + timedelta(days=holding_days + 5)).strftime("%Y-%m-%d")  # 여유분

    results = []

    def process_stock(stock):
        code = stock.get('code', '')
        name = stock.get('name', '')
        score = stock.get('score', 0)
        signals = stock.get('signals', [])
        close_price = stock.get('close', 0)  # 선정일 종가

        if not code or close_price == 0:
            return None

        # 주가 데이터 조회
        df = fetch_price_data(code, start_date, end_date)

        if df is None or len(df) < 1:
            return None

        # 일차별 수익률 계산
        daily_returns = {}
        for i, (idx, row) in enumerate(df.iterrows(), 1):
            if i > holding_days:
                break
            day_close = row['Close']
            return_pct = ((day_close - close_price) / close_price) * 100
            daily_returns[f'D+{i}'] = {
                'date': idx.strftime("%Y-%m-%d"),
                'close': day_close,
                'return_pct': round(return_pct, 2)
            }

        return {
            'code': code,
            'name': name,
            'score': score,
            'signals': signals,
            'selection_date': selection_date,
            'selection_price': close_price,
            'daily_returns': daily_returns
        }

    # 병렬 처리
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_stock, stock): stock for stock in stocks}

        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results


def analyze_hit_rate(backtest_results: List[dict], holding_days: int = 10) -> dict:
    """
    적중률 분석

    분석 항목:
    - 일차별 적중률: D+1, D+2, ... D+10
    - 점수대별 적중률: 80점 이상, 60~79점, 40~59점
    - 신호별 적중률: 어떤 신호가 더 잘 맞는지

    Args:
        backtest_results: 백테스트 결과 데이터
        holding_days: 분석 일수

    Returns:
        분석 결과 딕셔너리
    """
    if not backtest_results:
        return {}

    analysis = {
        'summary': {},
        'daily_stats': {},
        'score_band_stats': {},
        'signal_stats': {}
    }

    # 1. 일차별 통계
    for day in range(1, holding_days + 1):
        day_key = f'D+{day}'
        returns = []

        for result in backtest_results:
            daily = result.get('daily_returns', {})
            if day_key in daily:
                returns.append(daily[day_key]['return_pct'])

        if returns:
            positive = sum(1 for r in returns if r > 0)
            negative = sum(1 for r in returns if r < 0)
            flat = sum(1 for r in returns if r == 0)

            analysis['daily_stats'][day_key] = {
                'total': len(returns),
                'positive': positive,
                'negative': negative,
                'flat': flat,
                'hit_rate': round(positive / len(returns) * 100, 1),
                'avg_return': round(sum(returns) / len(returns), 2),
                'max_return': round(max(returns), 2),
                'min_return': round(min(returns), 2)
            }

    # 2. 점수대별 통계
    score_bands = [
        ('80점 이상', lambda s: s >= 80),
        ('60~79점', lambda s: 60 <= s < 80),
        ('40~59점', lambda s: 40 <= s < 60),
        ('40점 미만', lambda s: s < 40)
    ]

    for band_name, condition in score_bands:
        band_results = [r for r in backtest_results if condition(r.get('score', 0))]

        if not band_results:
            continue

        # D+5 기준 수익률
        returns_d5 = []
        for result in band_results:
            daily = result.get('daily_returns', {})
            if 'D+5' in daily:
                returns_d5.append(daily['D+5']['return_pct'])

        # D+10 기준 수익률
        returns_d10 = []
        for result in band_results:
            daily = result.get('daily_returns', {})
            if 'D+10' in daily:
                returns_d10.append(daily['D+10']['return_pct'])

        analysis['score_band_stats'][band_name] = {
            'count': len(band_results),
            'd5_hit_rate': round(sum(1 for r in returns_d5 if r > 0) / len(returns_d5) * 100, 1) if returns_d5 else 0,
            'd5_avg_return': round(sum(returns_d5) / len(returns_d5), 2) if returns_d5 else 0,
            'd10_hit_rate': round(sum(1 for r in returns_d10 if r > 0) / len(returns_d10) * 100, 1) if returns_d10 else 0,
            'd10_avg_return': round(sum(returns_d10) / len(returns_d10), 2) if returns_d10 else 0
        }

    # 3. 신호별 통계
    signal_returns = defaultdict(list)

    for result in backtest_results:
        signals = result.get('signals', [])
        daily = result.get('daily_returns', {})

        # D+5 기준 수익률
        if 'D+5' in daily:
            return_pct = daily['D+5']['return_pct']
            for signal in signals:
                signal_returns[signal].append(return_pct)

    # 각 신호별 통계 계산
    for signal, returns in signal_returns.items():
        if len(returns) >= 5:  # 최소 5개 이상 샘플
            positive = sum(1 for r in returns if r > 0)
            analysis['signal_stats'][signal] = {
                'count': len(returns),
                'hit_rate': round(positive / len(returns) * 100, 1),
                'avg_return': round(sum(returns) / len(returns), 2),
                'signal_kr': get_signal_kr(signal)
            }

    # 신호 통계 정렬 (적중률 기준)
    analysis['signal_stats'] = dict(
        sorted(analysis['signal_stats'].items(),
               key=lambda x: x[1]['hit_rate'],
               reverse=True)
    )

    # 4. 전체 요약
    all_returns_d5 = []
    all_returns_d10 = []

    for result in backtest_results:
        daily = result.get('daily_returns', {})
        if 'D+5' in daily:
            all_returns_d5.append(daily['D+5']['return_pct'])
        if 'D+10' in daily:
            all_returns_d10.append(daily['D+10']['return_pct'])

    analysis['summary'] = {
        'total_stocks': len(backtest_results),
        'selection_dates': len(set(r['selection_date'] for r in backtest_results)),
        'd5_total': len(all_returns_d5),
        'd5_hit_rate': round(sum(1 for r in all_returns_d5 if r > 0) / len(all_returns_d5) * 100, 1) if all_returns_d5 else 0,
        'd5_avg_return': round(sum(all_returns_d5) / len(all_returns_d5), 2) if all_returns_d5 else 0,
        'd10_total': len(all_returns_d10),
        'd10_hit_rate': round(sum(1 for r in all_returns_d10 if r > 0) / len(all_returns_d10) * 100, 1) if all_returns_d10 else 0,
        'd10_avg_return': round(sum(all_returns_d10) / len(all_returns_d10), 2) if all_returns_d10 else 0
    }

    return analysis


def generate_report(analysis: dict, backtest_results: List[dict]) -> str:
    """
    콘솔 리포트 생성

    Args:
        analysis: 분석 결과
        backtest_results: 백테스트 결과

    Returns:
        포맷된 리포트 문자열
    """
    lines = []

    lines.append("\n" + "=" * 70)
    lines.append("  TOP100 적중률 분석 리포트")
    lines.append("=" * 70)

    # 1. 요약
    summary = analysis.get('summary', {})
    lines.append(f"\n분석 기간: {summary.get('selection_dates', 0)}일")
    lines.append(f"분석 종목: {summary.get('total_stocks', 0)}개")

    lines.append(f"\n[전체 적중률]")
    lines.append(f"  D+5: {summary.get('d5_hit_rate', 0)}% (평균 {summary.get('d5_avg_return', 0):+.2f}%)")
    lines.append(f"  D+10: {summary.get('d10_hit_rate', 0)}% (평균 {summary.get('d10_avg_return', 0):+.2f}%)")

    # 2. 일차별 적중률
    lines.append("\n" + "-" * 70)
    lines.append("[일차별 적중률]")
    lines.append("-" * 70)
    lines.append(f"{'일차':<8} {'종목수':<8} {'적중률':<10} {'평균수익률':<12} {'최고':<10} {'최저':<10}")

    for day_key, stats in analysis.get('daily_stats', {}).items():
        lines.append(
            f"{day_key:<8} {stats['total']:<8} {stats['hit_rate']:>6.1f}%   "
            f"{stats['avg_return']:>+8.2f}%   {stats['max_return']:>+7.2f}%   {stats['min_return']:>+7.2f}%"
        )

    # 3. 점수대별 적중률
    lines.append("\n" + "-" * 70)
    lines.append("[점수대별 적중률]")
    lines.append("-" * 70)
    lines.append(f"{'점수대':<12} {'종목수':<8} {'D+5 적중률':<12} {'D+5 평균':<12} {'D+10 적중률':<12} {'D+10 평균':<12}")

    for band_name, stats in analysis.get('score_band_stats', {}).items():
        lines.append(
            f"{band_name:<12} {stats['count']:<8} {stats['d5_hit_rate']:>8.1f}%   "
            f"{stats['d5_avg_return']:>+8.2f}%   {stats['d10_hit_rate']:>8.1f}%   {stats['d10_avg_return']:>+8.2f}%"
        )

    # 4. 신호별 적중률 (상위 15개)
    lines.append("\n" + "-" * 70)
    lines.append("[신호별 적중률 - D+5 기준] (상위 15개)")
    lines.append("-" * 70)
    lines.append(f"{'신호':<25} {'출현횟수':<10} {'적중률':<10} {'평균수익률':<12}")

    signal_stats = list(analysis.get('signal_stats', {}).items())[:15]
    for signal, stats in signal_stats:
        signal_name = stats.get('signal_kr', signal)[:20]
        lines.append(
            f"{signal_name:<25} {stats['count']:<10} {stats['hit_rate']:>6.1f}%   {stats['avg_return']:>+8.2f}%"
        )

    # 5. 신뢰도가 낮은 신호 (하위 5개)
    lines.append("\n" + "-" * 70)
    lines.append("[주의 신호 - D+5 기준] (적중률 하위 5개)")
    lines.append("-" * 70)

    low_signals = list(analysis.get('signal_stats', {}).items())[-5:]
    for signal, stats in reversed(low_signals):
        signal_name = stats.get('signal_kr', signal)[:20]
        lines.append(
            f"{signal_name:<25} {stats['count']:<10} {stats['hit_rate']:>6.1f}%   {stats['avg_return']:>+8.2f}%"
        )

    lines.append("\n" + "=" * 70)

    return "\n".join(lines)


def export_to_excel(
    analysis: dict,
    backtest_results: List[dict],
    output_path: Optional[str] = None
) -> str:
    """
    Excel 리포트 생성

    Args:
        analysis: 분석 결과
        backtest_results: 백테스트 결과
        output_path: 출력 파일 경로

    Returns:
        생성된 파일 경로
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"backtest_report_{datetime.now().strftime('%Y%m%d')}.xlsx"

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # 1. 요약 시트
        summary_df = pd.DataFrame([analysis.get('summary', {})])
        summary_df.to_excel(writer, sheet_name='요약', index=False)

        # 2. 일차별 통계 시트
        daily_rows = []
        for day_key, stats in analysis.get('daily_stats', {}).items():
            row = {'일차': day_key}
            row.update(stats)
            daily_rows.append(row)
        daily_df = pd.DataFrame(daily_rows)
        daily_df.to_excel(writer, sheet_name='일차별통계', index=False)

        # 3. 점수대별 통계 시트
        score_rows = []
        for band_name, stats in analysis.get('score_band_stats', {}).items():
            row = {'점수대': band_name}
            row.update(stats)
            score_rows.append(row)
        score_df = pd.DataFrame(score_rows)
        score_df.to_excel(writer, sheet_name='점수대별통계', index=False)

        # 4. 신호별 통계 시트
        signal_rows = []
        for signal, stats in analysis.get('signal_stats', {}).items():
            row = {'신호': signal, '신호명': stats.get('signal_kr', signal)}
            row.update({k: v for k, v in stats.items() if k != 'signal_kr'})
            signal_rows.append(row)
        signal_df = pd.DataFrame(signal_rows)
        signal_df.to_excel(writer, sheet_name='신호별통계', index=False)

        # 5. 개별 종목 상세 시트
        detail_rows = []
        for result in backtest_results:
            base_row = {
                '선정일': result['selection_date'],
                '종목코드': result['code'],
                '종목명': result['name'],
                '점수': result['score'],
                '선정가': result['selection_price'],
                '주요신호': ', '.join(result['signals'][:3])
            }

            # 일차별 수익률 추가
            for day_key, data in result.get('daily_returns', {}).items():
                base_row[f'{day_key}_수익률'] = data['return_pct']

            detail_rows.append(base_row)

        detail_df = pd.DataFrame(detail_rows)
        detail_df.to_excel(writer, sheet_name='종목별상세', index=False)

    print(f"    → Excel 리포트: {output_path}")
    return str(output_path)


def get_signal_reliability(analysis: dict) -> dict:
    """
    신호별 신뢰도 계산 (2단계 개선용)

    Returns:
        signal -> reliability (0~100) 매핑
    """
    signal_stats = analysis.get('signal_stats', {})
    reliability = {}

    for signal, stats in signal_stats.items():
        hit_rate = stats.get('hit_rate', 50)
        avg_return = stats.get('avg_return', 0)
        count = stats.get('count', 0)

        # 신뢰도 = 적중률 기반 + 평균수익률 보너스/페널티
        # 기본 신뢰도: 적중률 그대로 사용
        base_reliability = hit_rate

        # 평균 수익률에 따른 보정
        if avg_return > 3:
            base_reliability += 10
        elif avg_return > 1:
            base_reliability += 5
        elif avg_return < -1:
            base_reliability -= 5
        elif avg_return < -3:
            base_reliability -= 10

        # 샘플 수가 적으면 신뢰도 낮춤
        if count < 10:
            base_reliability *= 0.8

        reliability[signal] = round(min(100, max(0, base_reliability)), 1)

    return reliability


def run_backtest(
    days: int = 30,
    holding_days: int = 10,
    max_workers: int = 10,
    verbose: bool = True
) -> Tuple[List[dict], dict]:
    """
    전체 백테스트 실행

    Args:
        days: 분석할 과거 일수
        holding_days: 종목당 추적 일수
        max_workers: 병렬 처리 워커 수
        verbose: 상세 로그 출력

    Returns:
        (backtest_results, analysis) 튜플
    """
    print(f"\n[백테스트] 시작 - 최근 {days}일 데이터 분석")
    print("-" * 50)

    # 1. 과거 데이터 로드
    historical_data = load_historical_selections(days)

    if not historical_data:
        print("[오류] 분석할 과거 데이터가 없습니다.")
        return [], {}

    print(f"    → 로드된 파일: {len(historical_data)}개")

    # 2. 각 날짜별 수익률 계산
    all_results = []

    for i, day_data in enumerate(historical_data):
        date = day_data['date']
        stocks = day_data['stocks'][:100]  # 상위 100개만

        if verbose:
            print(f"    → [{i+1}/{len(historical_data)}] {date} ({len(stocks)}개 종목)")

        results = calculate_daily_returns(
            selection_date=date,
            stocks=stocks,
            holding_days=holding_days,
            max_workers=max_workers
        )

        all_results.extend(results)

    print(f"    → 총 분석 종목: {len(all_results)}개")

    # 3. 적중률 분석
    print("\n[분석] 적중률 계산 중...")
    analysis = analyze_hit_rate(all_results, holding_days)

    return all_results, analysis


def main():
    parser = argparse.ArgumentParser(
        description="TOP100 적중률 백테스트 분석",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python backtest_analyzer.py              # 전체 과거 데이터 분석
  python backtest_analyzer.py --days 7     # 최근 7일 데이터만
  python backtest_analyzer.py --export     # Excel 리포트 생성
  python backtest_analyzer.py --holding 5  # 5일 보유 기준 분석
        """
    )

    parser.add_argument(
        "--days", type=int, default=30,
        help="분석할 과거 일수 (기본: 30)"
    )
    parser.add_argument(
        "--holding", type=int, default=10,
        help="종목당 추적 일수 (기본: 10)"
    )
    parser.add_argument(
        "--export", action="store_true",
        help="Excel 리포트 생성"
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="병렬 처리 워커 수 (기본: 10)"
    )

    args = parser.parse_args()

    try:
        # 백테스트 실행
        results, analysis = run_backtest(
            days=args.days,
            holding_days=args.holding,
            max_workers=args.workers
        )

        if not results:
            print("[완료] 분석할 데이터가 없습니다.")
            return

        # 리포트 출력
        report = generate_report(analysis, results)
        print(report)

        # Excel 저장
        if args.export:
            export_to_excel(analysis, results)

        # 신호별 신뢰도 출력
        print("\n" + "=" * 70)
        print("[신호별 신뢰도 점수] (2단계 개선 참고용)")
        print("=" * 70)
        reliability = get_signal_reliability(analysis)
        for signal, score in sorted(reliability.items(), key=lambda x: -x[1])[:10]:
            print(f"  {get_signal_kr(signal):<20}: {score:.1f}%")

        print("\n[완료] 백테스트 분석 완료")

    except KeyboardInterrupt:
        print("\n[중단] 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n[오류] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
