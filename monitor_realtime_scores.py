#!/usr/bin/env python3
"""
실시간 스코어 모니터링

record_intraday_scores.py 실행 후 자동으로 분석하여:
- 급등 후보 종목 감지 (Tier 1/2/3)
- 급락 경고 종목 감지
- 터미널/로그로 결과 출력
- (향후) 푸시 알림 연동 가능

사용법:
    python monitor_realtime_scores.py                  # 최신 2개 파일 비교 (1회)
    python monitor_realtime_scores.py --daemon         # 데몬 모드 (10분마다 실행)
    python monitor_realtime_scores.py --watch 005930   # 특정 종목 추적
"""

import os
import sys
import argparse
import time
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent
SCORES_DIR = PROJECT_ROOT / "output" / "intraday_scores"
LOG_FILE = Path("/tmp/monitor_scores.log")

# 종료 플래그
running = True


def signal_handler(sig, frame):
    global running
    print("\n종료 신호 수신. 모니터링 중단...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ============================================================================
# 로깅
# ============================================================================
def log(message: str, to_file: bool = True):
    """터미널 + 파일 로그"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {message}"
    print(line)

    if to_file:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')


# ============================================================================
# CSV 로드 및 비교 (analyze_score_changes.py와 동일한 로직)
# ============================================================================
def get_latest_csv_files(n: int = 2) -> list:
    """최신 N개 CSV 파일 조회"""
    today = datetime.now().strftime('%Y%m%d')
    pattern = f"{today}_*.csv"
    files = sorted(SCORES_DIR.glob(pattern), key=lambda f: f.stem)

    if len(files) < n:
        # 오늘 파일이 부족하면 어제 파일도 포함
        yesterday = (datetime.now() - pd.Timedelta(days=1)).strftime('%Y%m%d')
        pattern_yesterday = f"{yesterday}_*.csv"
        files_yesterday = sorted(SCORES_DIR.glob(pattern_yesterday), key=lambda f: f.stem)
        files = files_yesterday + files

    return files[-n:] if len(files) >= n else files


def load_csv(filepath: Path) -> pd.DataFrame:
    """CSV 파일 로드"""
    df = pd.read_csv(filepath)
    df['code'] = df['code'].astype(str).str.zfill(6)
    return df


def compare_two_csvs(prev_df: pd.DataFrame, curr_df: pd.DataFrame) -> pd.DataFrame:
    """두 CSV 비교하여 delta 계산"""
    merged = curr_df.merge(
        prev_df[['code', 'v2', 'v4', 'v5', 'v3.5', 'v9_prob', 'close', 'volume']],
        on='code',
        how='inner',
        suffixes=('', '_prev')
    )

    merged['v2_delta'] = merged['v2'] - merged['v2_prev']
    merged['v4_delta'] = merged['v4'] - merged['v4_prev']
    merged['v5_delta'] = merged['v5'] - merged['v5_prev']
    merged['v9_delta'] = merged['v9_prob'] - merged['v9_prob_prev']
    merged['price_change'] = ((merged['close'] - merged['close_prev']) / merged['close_prev'] * 100).round(2)
    merged['volume_ratio'] = (merged['volume'] / merged['volume_prev']).replace([np.inf, -np.inf], 0).fillna(0)

    return merged


# ============================================================================
# Tier 판정
# ============================================================================
def has_volume_surge_signal(signals_str: str) -> bool:
    if pd.isna(signals_str):
        return False
    return 'VOLUME_EXPLOSION' in signals_str or 'VOLUME_SURGE_3X' in signals_str


def has_pattern_signal(signals_str: str) -> bool:
    if pd.isna(signals_str):
        return False
    return 'BB_SQUEEZE' in signals_str or 'VCP_PATTERN' in signals_str


def check_tier1(row: pd.Series) -> bool:
    if row['v2'] < 70:
        return False
    if row['v2_delta'] < 8:
        return False
    if not has_volume_surge_signal(row.get('signals', '')):
        return False
    if row['v4'] < 50:
        return False
    est_amount = row['close'] * row['volume']
    if est_amount < 10_000_000_000:
        return False
    return True


def check_tier2(row: pd.Series) -> bool:
    if row['v2'] < 65:
        return False
    if row['v2_delta'] < 5:
        return False
    if row['volume_ratio'] < 2.0:
        return False
    if row['v3.5'] < 40 and row['v5'] < 50:
        return False
    return True


def check_tier3(row: pd.Series) -> bool:
    if row['v2'] < 60:
        return False
    if not has_pattern_signal(row.get('signals', '')) and row['v9_prob'] < 55:
        return False
    return True


def calculate_composite_score(row: pd.Series) -> float:
    """복합 스코어"""
    score = row['v2'] * 0.35
    if row['v4'] >= 60:
        score += 20
    elif row['v4'] >= 50:
        score += 10
    if row['v5'] >= 70:
        score += 12
    elif row['v5'] >= 60:
        score += 8
    if row['v3.5'] >= 50:
        score += 7
    if row['v2'] < 30 and row['v8'] >= 50:
        score += 10
    if row['v9_prob'] >= 60:
        score += 10
    elif row['v9_prob'] >= 55:
        score += 8
    return round(score, 1)


# ============================================================================
# 감지 로직
# ============================================================================
def detect_surge_candidates(merged_df: pd.DataFrame) -> dict:
    """급등 후보 감지"""
    candidates = {'tier1': [], 'tier2': [], 'tier3': []}

    for _, row in merged_df.iterrows():
        if check_tier1(row):
            candidates['tier1'].append(row.to_dict())
        elif check_tier2(row):
            candidates['tier2'].append(row.to_dict())
        elif check_tier3(row):
            candidates['tier3'].append(row.to_dict())

    return candidates


def detect_drop_warnings(merged_df: pd.DataFrame, watch_codes: list = None) -> list:
    """급락 경고 감지"""
    warnings = []

    df = merged_df if watch_codes is None else merged_df[merged_df['code'].isin(watch_codes)]

    for _, row in df.iterrows():
        if row['v2'] == 0:
            warnings.append({
                'level': 'CRITICAL',
                'code': row['code'],
                'name': row['name'],
                'reason': 'V2=0 (역배열)',
                'change_pct': row['change_pct']
            })
        elif row['v2_delta'] <= -15:
            warnings.append({
                'level': 'CRITICAL',
                'code': row['code'],
                'name': row['name'],
                'reason': f"V2 급락 ({row['v2_delta']:+.0f})",
                'change_pct': row['change_pct']
            })
        elif row['volume_ratio'] >= 3.0 and row['price_change'] < -2.0:
            warnings.append({
                'level': 'HIGH',
                'code': row['code'],
                'name': row['name'],
                'reason': f"분배패턴 (거래량 {row['volume_ratio']:.1f}배)",
                'change_pct': row['change_pct']
            })

    return warnings


# ============================================================================
# 모니터링 실행
# ============================================================================
def run_monitoring(watch_codes: list = None) -> dict:
    """1회 모니터링 실행"""
    files = get_latest_csv_files(2)

    if len(files) < 2:
        log("파일 부족 (최소 2개 필요)")
        return {}

    prev_file = files[0]
    curr_file = files[1]

    prev_time = prev_file.stem.split('_')[1]
    curr_time = curr_file.stem.split('_')[1]

    log(f"비교: {prev_file.name} → {curr_file.name}")

    prev_df = load_csv(prev_file)
    curr_df = load_csv(curr_file)

    merged = compare_two_csvs(prev_df, curr_df)

    # 급등 후보 감지
    candidates = detect_surge_candidates(merged)

    # 급락 경고 감지
    warnings = detect_drop_warnings(merged, watch_codes)

    # 결과 출력
    result = {
        'prev_time': prev_time,
        'curr_time': curr_time,
        'candidates': candidates,
        'warnings': warnings
    }

    print_results(result)

    return result


def print_results(result: dict):
    """결과 출력"""
    candidates = result['candidates']
    warnings = result['warnings']
    prev_time = result['prev_time']
    curr_time = result['curr_time']

    # Tier 1 (최우선)
    tier1 = candidates.get('tier1', [])
    if tier1:
        log(f"\n{'='*60}")
        log(f"  [Tier 1] 급등 후보 {len(tier1)}개 ({prev_time} → {curr_time})")
        log(f"{'='*60}")

        for r in sorted(tier1, key=lambda x: x['v2'], reverse=True)[:5]:
            log(f"  {r['code']} {r['name']:<12} | "
                f"V2={r['v2']:.0f}(Δ{r['v2_delta']:+.0f}) V4={r['v4']:.0f} | "
                f"{r['change_pct']:+.2f}%")

    # Tier 2
    tier2 = candidates.get('tier2', [])
    if tier2:
        log(f"\n  [Tier 2] 급등 후보 {len(tier2)}개")
        for r in sorted(tier2, key=lambda x: x['v2'], reverse=True)[:3]:
            log(f"  {r['code']} {r['name']:<12} | "
                f"V2={r['v2']:.0f}(Δ{r['v2_delta']:+.0f}) | {r['change_pct']:+.2f}%")

    # 경고
    if warnings:
        log(f"\n{'='*60}")
        log(f"  급락 경고 {len(warnings)}개")
        log(f"{'='*60}")

        for w in warnings[:5]:
            log(f"  [{w['level']}] {w['code']} {w['name']:<12} | {w['reason']} | {w['change_pct']:+.2f}%")

    # 요약
    total = len(tier1) + len(tier2) + len(candidates.get('tier3', []))
    if total == 0 and not warnings:
        log("  (급등 후보/경고 없음)")


def run_daemon(interval_minutes: int = 10, watch_codes: list = None):
    """데몬 모드 실행"""
    global running

    log(f"데몬 모드 시작 (간격: {interval_minutes}분)")
    log(f"Ctrl+C로 종료")

    if watch_codes:
        log(f"감시 종목: {watch_codes}")

    while running:
        now = datetime.now()

        # 장 시간 체크 (09:00 ~ 15:40)
        if now.hour < 9 or (now.hour >= 15 and now.minute >= 40):
            log("장 마감. 대기 중...")
            time.sleep(60)
            continue

        # 모니터링 실행
        try:
            run_monitoring(watch_codes)
        except Exception as e:
            log(f"오류: {e}")

        # 다음 실행까지 대기
        if running:
            log(f"\n다음 실행까지 {interval_minutes}분 대기...")
            for _ in range(interval_minutes * 60):
                if not running:
                    break
                time.sleep(1)

    log("데몬 종료")


# ============================================================================
# V2 Delta 상위 종목 (빠른 조회)
# ============================================================================
def show_top_delta(top_n: int = 20):
    """V2 Delta 상위 종목 빠른 조회"""
    files = get_latest_csv_files(2)

    if len(files) < 2:
        print("파일 부족")
        return

    prev_df = load_csv(files[0])
    curr_df = load_csv(files[1])
    merged = compare_two_csvs(prev_df, curr_df)

    # V2 상승 Top
    print(f"\n{'='*60}")
    print(f"  V2 상승폭 Top {top_n} ({files[0].stem} → {files[1].stem})")
    print(f"{'='*60}")

    top_up = merged.nlargest(top_n, 'v2_delta')
    for _, r in top_up.iterrows():
        print(f"  {r['code']} {r['name']:<12} | "
              f"V2: {r['v2_prev']:.0f}→{r['v2']:.0f} (Δ{r['v2_delta']:+.0f}) | "
              f"{r['change_pct']:+.2f}%")

    # V2 하락 Top
    print(f"\n{'='*60}")
    print(f"  V2 하락폭 Top {top_n}")
    print(f"{'='*60}")

    top_down = merged.nsmallest(top_n, 'v2_delta')
    for _, r in top_down.iterrows():
        print(f"  {r['code']} {r['name']:<12} | "
              f"V2: {r['v2_prev']:.0f}→{r['v2']:.0f} (Δ{r['v2_delta']:+.0f}) | "
              f"{r['change_pct']:+.2f}%")


# ============================================================================
# 메인 함수
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='실시간 스코어 모니터링')
    parser.add_argument('--daemon', action='store_true', help='데몬 모드 (10분마다 실행)')
    parser.add_argument('--interval', type=int, default=10, help='데몬 실행 간격 (분)')
    parser.add_argument('--watch', type=str, help='감시할 종목 코드 (쉼표 구분)', default=None)
    parser.add_argument('--top', action='store_true', help='V2 Delta Top 20 빠른 조회')
    parser.add_argument('--top-n', type=int, default=20, help='Top N 개수')
    args = parser.parse_args()

    # 감시 종목 파싱
    watch_codes = None
    if args.watch:
        watch_codes = [c.strip().zfill(6) for c in args.watch.split(',')]

    # Top Delta 빠른 조회
    if args.top:
        show_top_delta(args.top_n)
        return

    print(f"\n{'#'*60}")
    print(f"#  실시간 스코어 모니터링")
    print(f"#  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    if args.daemon:
        run_daemon(args.interval, watch_codes)
    else:
        run_monitoring(watch_codes)

    print()


if __name__ == "__main__":
    main()
