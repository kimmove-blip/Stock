#!/usr/bin/env python3
"""
장중 스코어 기반 급등 감지 백테스트

과거 intraday_scores 데이터를 사용하여:
- Tier 1/2/3 급등 후보 감지 시점 기록
- 10분/30분/60분 후 실제 수익률 측정
- 임계값 최적화

사용법:
    python backtest_intraday_signals.py                     # 전체 데이터 백테스트
    python backtest_intraday_signals.py --date 20260128     # 특정 날짜만
    python backtest_intraday_signals.py --optimize          # 임계값 최적화
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
from collections import defaultdict

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent
SCORES_DIR = PROJECT_ROOT / "output" / "intraday_scores"


# ============================================================================
# Tier 조건 (analyze_score_changes.py와 동일)
# ============================================================================
def has_volume_surge_signal(signals_str: str) -> bool:
    if pd.isna(signals_str):
        return False
    return 'VOLUME_EXPLOSION' in signals_str or 'VOLUME_SURGE_3X' in signals_str


def has_pattern_signal(signals_str: str) -> bool:
    if pd.isna(signals_str):
        return False
    return 'BB_SQUEEZE' in signals_str or 'VCP_PATTERN' in signals_str


def check_tier1(row: pd.Series, v2_delta: float, cfg: dict) -> bool:
    """Tier 1 조건 확인 (동적 임계값)"""
    if row['v2'] < cfg.get('v2_min', 70):
        return False
    if v2_delta < cfg.get('v2_delta_min', 8):
        return False
    if not has_volume_surge_signal(row.get('signals', '')):
        return False
    if row['v4'] < cfg.get('v4_min', 50):
        return False
    # 거래대금 추정
    est_amount = row['close'] * row['volume']
    if est_amount < cfg.get('amount_min', 10_000_000_000):
        return False
    return True


def check_tier2(row: pd.Series, v2_delta: float, volume_ratio: float, cfg: dict) -> bool:
    """Tier 2 조건 확인"""
    if row['v2'] < cfg.get('v2_min', 65):
        return False
    if v2_delta < cfg.get('v2_delta_min', 5):
        return False
    if volume_ratio < cfg.get('volume_ratio_min', 2.0):
        return False
    if row['v3.5'] < cfg.get('v35_min', 40) and row['v5'] < cfg.get('v5_min', 50):
        return False
    return True


def check_tier3(row: pd.Series, cfg: dict) -> bool:
    """Tier 3 조건 확인"""
    if row['v2'] < cfg.get('v2_min', 60):
        return False
    if not has_pattern_signal(row.get('signals', '')) and row['v9_prob'] < cfg.get('v9_min', 55):
        return False
    return True


# ============================================================================
# CSV 로드
# ============================================================================
def get_all_csv_files() -> dict:
    """모든 CSV 파일을 날짜별로 그룹화"""
    all_files = sorted(SCORES_DIR.glob("*.csv"))
    by_date = defaultdict(list)

    for f in all_files:
        date_str = f.stem.split('_')[0]
        by_date[date_str].append(f)

    return dict(by_date)


def load_csv(filepath: Path) -> pd.DataFrame:
    """CSV 파일 로드 (컬럼명 정규화)"""
    df = pd.read_csv(filepath)
    df['code'] = df['code'].astype(str).str.zfill(6)

    # 컬럼명 정규화 (v3 → v3.5, amount → prev_amount)
    if 'v3' in df.columns and 'v3.5' not in df.columns:
        df = df.rename(columns={'v3': 'v3.5'})
    if 'amount' in df.columns and 'prev_amount' not in df.columns:
        df = df.rename(columns={'amount': 'prev_amount'})
    if 'marcap' in df.columns and 'prev_marcap' not in df.columns:
        df = df.rename(columns={'marcap': 'prev_marcap'})

    # 필수 컬럼 없으면 0으로 채움
    for col in ['v3.5', 'v8', 'v9_prob']:
        if col not in df.columns:
            df[col] = 0

    return df


def get_time_from_filename(filepath: Path) -> int:
    """파일명에서 분 단위 시간 추출 (0900 → 540)"""
    time_str = filepath.stem.split('_')[1]
    hours = int(time_str[:2])
    minutes = int(time_str[2:])
    return hours * 60 + minutes


# ============================================================================
# 백테스트 로직
# ============================================================================
def run_backtest_for_date(date_str: str, files: list, tier_config: dict) -> list:
    """하루치 데이터 백테스트"""
    if len(files) < 3:
        return []

    # 파일을 시간순 정렬
    files = sorted(files, key=get_time_from_filename)

    # 모든 파일 로드
    data_by_time = {}
    times = []
    for f in files:
        time_min = get_time_from_filename(f)
        data_by_time[time_min] = load_csv(f)
        times.append(time_min)

    results = []

    # 각 시점에서 시그널 감지 후 미래 수익률 측정
    for i in range(1, len(times) - 1):  # 마지막은 미래 데이터 필요
        prev_time = times[i-1]
        curr_time = times[i]

        prev_df = data_by_time[prev_time]
        curr_df = data_by_time[curr_time]

        # 공통 종목
        merged = curr_df.merge(
            prev_df[['code', 'v2', 'v4', 'v5', 'v3.5', 'v9_prob', 'close', 'volume']],
            on='code',
            how='inner',
            suffixes=('', '_prev')
        )

        # Delta 계산
        merged['v2_delta'] = merged['v2'] - merged['v2_prev']
        merged['volume_ratio'] = (merged['volume'] / merged['volume_prev']).replace([np.inf, -np.inf], 0).fillna(0)

        # 각 종목 Tier 판정
        for _, row in merged.iterrows():
            tier = None

            if check_tier1(row, row['v2_delta'], tier_config.get('tier1', {})):
                tier = 'tier1'
            elif check_tier2(row, row['v2_delta'], row['volume_ratio'], tier_config.get('tier2', {})):
                tier = 'tier2'
            elif check_tier3(row, tier_config.get('tier3', {})):
                tier = 'tier3'

            if tier is None:
                continue

            entry_price = row['close']
            code = row['code']

            # 10분/30분/60분 후 가격 조회
            returns = {}
            for offset, label in [(1, '10min'), (3, '30min'), (6, '60min')]:
                future_idx = i + offset
                if future_idx < len(times):
                    future_time = times[future_idx]
                    future_df = data_by_time[future_time]
                    future_row = future_df[future_df['code'] == code]
                    if not future_row.empty:
                        future_price = future_row.iloc[0]['close']
                        returns[label] = ((future_price - entry_price) / entry_price * 100)
                    else:
                        returns[label] = np.nan
                else:
                    returns[label] = np.nan

            # 장 마감 가격 (마지막 파일)
            last_time = times[-1]
            last_df = data_by_time[last_time]
            last_row = last_df[last_df['code'] == code]
            if not last_row.empty:
                eod_price = last_row.iloc[0]['close']
                returns['eod'] = ((eod_price - entry_price) / entry_price * 100)
            else:
                returns['eod'] = np.nan

            results.append({
                'date': date_str,
                'time': f"{curr_time // 60:02d}{curr_time % 60:02d}",
                'code': code,
                'name': row['name'],
                'tier': tier,
                'entry_price': entry_price,
                'v2': row['v2'],
                'v2_delta': row['v2_delta'],
                'v4': row['v4'],
                'v5': row['v5'],
                'v9_prob': row['v9_prob'],
                'return_10min': returns.get('10min', np.nan),
                'return_30min': returns.get('30min', np.nan),
                'return_60min': returns.get('60min', np.nan),
                'return_eod': returns.get('eod', np.nan),
            })

    return results


def analyze_results(results: list) -> dict:
    """백테스트 결과 분석"""
    df = pd.DataFrame(results)
    if df.empty:
        return {}

    analysis = {}

    for tier in ['tier1', 'tier2', 'tier3']:
        tier_df = df[df['tier'] == tier]
        if tier_df.empty:
            continue

        tier_analysis = {
            'count': len(tier_df),
            'unique_stocks': tier_df['code'].nunique(),
        }

        for col in ['return_10min', 'return_30min', 'return_60min', 'return_eod']:
            valid = tier_df[col].dropna()
            if len(valid) > 0:
                tier_analysis[col] = {
                    'mean': valid.mean(),
                    'median': valid.median(),
                    'std': valid.std(),
                    'win_rate': (valid > 0).mean() * 100,
                    'win_rate_1pct': (valid > 1.0).mean() * 100,  # 1% 이상 수익
                    'loss_rate_2pct': (valid < -2.0).mean() * 100,  # 2% 이상 손실
                    'max': valid.max(),
                    'min': valid.min(),
                }
            else:
                tier_analysis[col] = None

        analysis[tier] = tier_analysis

    # 전체 통계
    analysis['total'] = {
        'count': len(df),
        'unique_stocks': df['code'].nunique(),
        'by_date': df.groupby('date').size().to_dict(),
    }

    return analysis


def print_analysis(analysis: dict):
    """분석 결과 출력"""
    print(f"\n{'='*80}")
    print(f"  백테스트 결과 분석")
    print(f"{'='*80}")

    total = analysis.get('total', {})
    print(f"\n전체: {total.get('count', 0)}건, 고유 종목: {total.get('unique_stocks', 0)}개")
    print(f"날짜별: {total.get('by_date', {})}")

    for tier in ['tier1', 'tier2', 'tier3']:
        tier_data = analysis.get(tier)
        if not tier_data:
            continue

        print(f"\n{'-'*80}")
        print(f"[{tier.upper()}] 감지 {tier_data['count']}건, 고유 종목 {tier_data['unique_stocks']}개")
        print(f"{'-'*80}")

        for period in ['return_10min', 'return_30min', 'return_60min', 'return_eod']:
            stats = tier_data.get(period)
            if not stats:
                continue

            period_name = period.replace('return_', '').upper()
            print(f"\n  {period_name}:")
            print(f"    평균 수익률: {stats['mean']:+.2f}% (중앙값: {stats['median']:+.2f}%)")
            print(f"    승률: {stats['win_rate']:.1f}%, 1% 이상 수익: {stats['win_rate_1pct']:.1f}%")
            print(f"    2% 이상 손실: {stats['loss_rate_2pct']:.1f}%")
            print(f"    범위: {stats['min']:+.2f}% ~ {stats['max']:+.2f}%")


# ============================================================================
# 임계값 최적화
# ============================================================================
def optimize_thresholds(all_files: dict) -> dict:
    """임계값 최적화"""
    print(f"\n{'='*80}")
    print(f"  임계값 최적화")
    print(f"{'='*80}")

    # 테스트할 파라미터 범위
    v2_min_range = [60, 65, 70, 75]
    v2_delta_range = [5, 8, 10, 12]
    v4_min_range = [40, 50, 60]

    best_result = None
    best_params = None
    best_score = -np.inf

    total_tests = len(v2_min_range) * len(v2_delta_range) * len(v4_min_range)
    test_num = 0

    for v2_min in v2_min_range:
        for v2_delta_min in v2_delta_range:
            for v4_min in v4_min_range:
                test_num += 1
                if test_num % 10 == 0:
                    print(f"  테스트 {test_num}/{total_tests}...")

                config = {
                    'tier1': {
                        'v2_min': v2_min,
                        'v2_delta_min': v2_delta_min,
                        'v4_min': v4_min,
                        'amount_min': 10_000_000_000,
                    },
                    'tier2': {
                        'v2_min': v2_min - 5,
                        'v2_delta_min': v2_delta_min - 3,
                        'volume_ratio_min': 2.0,
                        'v35_min': 40,
                        'v5_min': 50,
                    },
                    'tier3': {
                        'v2_min': v2_min - 10,
                        'v9_min': 55,
                    }
                }

                # 백테스트 실행
                all_results = []
                for date_str, files in all_files.items():
                    results = run_backtest_for_date(date_str, files, config)
                    all_results.extend(results)

                if not all_results:
                    continue

                analysis = analyze_results(all_results)

                # Tier 1 기준 스코어 계산
                tier1 = analysis.get('tier1', {})
                if not tier1:
                    continue

                ret_30 = tier1.get('return_30min', {})
                if not ret_30:
                    continue

                # 스코어 = 평균수익률 × 승률 / 감지건수 (과적합 방지)
                count = tier1.get('count', 1)
                if count < 5:  # 최소 5건 이상
                    continue

                score = ret_30['mean'] * ret_30['win_rate'] / 100

                if score > best_score:
                    best_score = score
                    best_params = config
                    best_result = analysis

    print(f"\n{'='*80}")
    print(f"  최적 파라미터")
    print(f"{'='*80}")

    if best_params:
        print(f"\nTier 1:")
        for k, v in best_params['tier1'].items():
            print(f"  {k}: {v}")
        print(f"\n최적 스코어: {best_score:.2f}")
        print_analysis(best_result)
    else:
        print("최적화 실패 (데이터 부족)")

    return best_params


# ============================================================================
# 상세 결과 출력
# ============================================================================
def print_detailed_results(results: list, limit: int = 30):
    """상세 결과 출력"""
    df = pd.DataFrame(results)
    if df.empty:
        print("결과 없음")
        return

    # Tier 1 결과
    tier1_df = df[df['tier'] == 'tier1'].copy()
    if not tier1_df.empty:
        print(f"\n{'='*100}")
        print(f"  Tier 1 상세 결과 ({len(tier1_df)}건)")
        print(f"{'='*100}")

        tier1_df = tier1_df.sort_values('return_30min', ascending=False)
        print(f"{'날짜':<10} {'시간':<6} {'종목코드':<8} {'종목명':<14} "
              f"{'V2':>4} {'Δ':>4} {'V4':>4} {'10분':>7} {'30분':>7} {'60분':>7} {'EOD':>7}")
        print("-" * 100)

        for _, row in tier1_df.head(limit).iterrows():
            print(f"{row['date']:<10} {row['time']:<6} {row['code']:<8} {row['name']:<14} "
                  f"{row['v2']:4.0f} {row['v2_delta']:+4.0f} {row['v4']:4.0f} "
                  f"{row['return_10min']:+6.2f}% {row['return_30min']:+6.2f}% "
                  f"{row['return_60min']:+6.2f}% {row['return_eod']:+6.2f}%")

    # 수익/손실 극단 사례
    if not df.empty:
        print(f"\n{'='*100}")
        print(f"  수익 Top 10 (30분 기준)")
        print(f"{'='*100}")

        top_profits = df.nlargest(10, 'return_30min')
        for _, row in top_profits.iterrows():
            print(f"  {row['date']} {row['time']} {row['code']} {row['name']:<12} "
                  f"[{row['tier']}] V2={row['v2']:.0f}(Δ{row['v2_delta']:+.0f}) → "
                  f"{row['return_30min']:+.2f}%")

        print(f"\n{'='*100}")
        print(f"  손실 Top 10 (30분 기준)")
        print(f"{'='*100}")

        top_losses = df.nsmallest(10, 'return_30min')
        for _, row in top_losses.iterrows():
            print(f"  {row['date']} {row['time']} {row['code']} {row['name']:<12} "
                  f"[{row['tier']}] V2={row['v2']:.0f}(Δ{row['v2_delta']:+.0f}) → "
                  f"{row['return_30min']:+.2f}%")


# ============================================================================
# 메인 함수
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='장중 스코어 백테스트')
    parser.add_argument('--date', type=str, help='특정 날짜만 분석 (YYYYMMDD)', default=None)
    parser.add_argument('--optimize', action='store_true', help='임계값 최적화')
    parser.add_argument('--detail', action='store_true', help='상세 결과 출력')
    parser.add_argument('--save', type=str, help='결과 CSV 저장 경로', default=None)
    args = parser.parse_args()

    print(f"\n{'#'*80}")
    print(f"#  장중 스코어 기반 급등 감지 백테스트")
    print(f"{'#'*80}")

    all_files = get_all_csv_files()
    print(f"\n데이터: {len(all_files)}일")
    for date_str, files in sorted(all_files.items()):
        print(f"  {date_str}: {len(files)}개 파일")

    # 특정 날짜만
    if args.date:
        if args.date not in all_files:
            print(f"해당 날짜 데이터 없음: {args.date}")
            return
        all_files = {args.date: all_files[args.date]}

    # 임계값 최적화
    if args.optimize:
        optimize_thresholds(all_files)
        return

    # 기본 백테스트
    default_config = {
        'tier1': {
            'v2_min': 70,
            'v2_delta_min': 8,
            'v4_min': 50,
            'amount_min': 10_000_000_000,
        },
        'tier2': {
            'v2_min': 65,
            'v2_delta_min': 5,
            'volume_ratio_min': 2.0,
            'v35_min': 40,
            'v5_min': 50,
        },
        'tier3': {
            'v2_min': 60,
            'v9_min': 55,
        }
    }

    print(f"\n현재 설정:")
    print(f"  Tier 1: V2>={default_config['tier1']['v2_min']}, ΔV2>={default_config['tier1']['v2_delta_min']}, "
          f"V4>={default_config['tier1']['v4_min']}, 거래대금>={default_config['tier1']['amount_min']/1e8:.0f}억")
    print(f"  Tier 2: V2>={default_config['tier2']['v2_min']}, ΔV2>={default_config['tier2']['v2_delta_min']}, "
          f"거래량>={default_config['tier2']['volume_ratio_min']}배")
    print(f"  Tier 3: V2>={default_config['tier3']['v2_min']}, V9>={default_config['tier3']['v9_min']}%")

    # 백테스트 실행
    print(f"\n백테스트 실행 중...")
    all_results = []

    for date_str, files in sorted(all_files.items()):
        print(f"  {date_str} 처리 중...")
        results = run_backtest_for_date(date_str, files, default_config)
        all_results.extend(results)
        print(f"    → {len(results)}건 감지")

    if not all_results:
        print("\n감지된 시그널 없음")
        return

    # 결과 분석
    analysis = analyze_results(all_results)
    print_analysis(analysis)

    # 상세 결과
    if args.detail:
        print_detailed_results(all_results)

    # CSV 저장
    if args.save:
        df = pd.DataFrame(all_results)
        df.to_csv(args.save, index=False, encoding='utf-8-sig')
        print(f"\n결과 저장: {args.save}")

    print()


if __name__ == "__main__":
    main()
