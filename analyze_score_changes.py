#!/usr/bin/env python3
"""
스코어 변화 분석기 (장중 급등/급락 감지)

연속된 intraday_scores CSV 파일을 비교하여:
- V2, V4 등 스코어의 변화량(delta) 계산
- 급등 후보 종목 감지 (Tier 1/2/3)
- 급락 위험 종목 감지

사용법:
    python analyze_score_changes.py                     # 오늘 최신 2개 파일 비교
    python analyze_score_changes.py --date 20260128     # 특정 날짜
    python analyze_score_changes.py --all               # 하루 전체 분석
    python analyze_score_changes.py --watch 005930,035420  # 특정 종목 추적
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent
SCORES_DIR = PROJECT_ROOT / "output" / "intraday_scores"


# ============================================================================
# Tier 정의 (급등 후보 조건)
# ============================================================================
TIER_CONFIG = {
    'tier1': {
        'name': 'Tier 1 (최고 신뢰도)',
        'desc': '10~30분 내 급등 예상',
        'conditions': {
            'v2_min': 70,
            'v2_delta_min': 8,
            'volume_surge': True,  # VOLUME_EXPLOSION 또는 VOLUME_SURGE_3X
            'v4_min': 50,
            'amount_min': 10_000_000_000,  # 100억
            'buy_strength_min': 110,  # 체결강도 110 이상 (옵션)
        }
    },
    'tier2': {
        'name': 'Tier 2 (양호 신뢰도)',
        'desc': '30~60분 내 급등 예상',
        'conditions': {
            'v2_min': 65,
            'v2_delta_min': 5,
            'volume_ratio_min': 2.0,  # 2배 이상
            'v35_min': 40,  # V3.5 또는
            'v5_min': 50,   # V5
            'buy_strength_min': 100,  # 체결강도 100 이상 (옵션)
        }
    },
    'tier3': {
        'name': 'Tier 3 (관찰)',
        'desc': '에너지 축적 중',
        'conditions': {
            'v2_min': 60,
            'pattern_signal': True,  # BB_SQUEEZE 또는 VCP_PATTERN
            'v9_min': 55,
        }
    }
}

# 새 컬럼 존재 여부 (한투 API 데이터)
HAS_KIS_DATA = False

# 급락 경고 조건
DROP_WARNING_CONFIG = {
    'critical': {
        'name': 'CRITICAL',
        'conditions': [
            {'type': 'v2_zero', 'desc': 'V2=0 (역배열)'},
            {'type': 'v2_delta_drop', 'threshold': -15, 'desc': 'V2 급락 (-15 이상)'},
        ]
    },
    'high': {
        'name': 'HIGH',
        'conditions': [
            {'type': 'distribution', 'desc': '고거래량 + 음봉 (분배패턴)'},
            {'type': 'rsi_falling_knife', 'desc': 'RSI_FALLING_KNIFE 시그널'},
        ]
    },
    'medium': {
        'name': 'MEDIUM',
        'conditions': [
            {'type': 'v2_consecutive_drop', 'count': 3, 'desc': 'V2 3연속 하락'},
        ]
    }
}


# ============================================================================
# CSV 로드 및 비교 함수
# ============================================================================
def get_csv_files(date_str: str = None) -> list:
    """특정 날짜의 CSV 파일 목록 조회 (시간순 정렬)"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    pattern = f"{date_str}_*.csv"
    files = sorted(SCORES_DIR.glob(pattern))
    return files


def load_csv(filepath: Path) -> pd.DataFrame:
    """CSV 파일 로드"""
    df = pd.read_csv(filepath)
    df['code'] = df['code'].astype(str).str.zfill(6)
    return df


def get_timestamp_from_filename(filepath: Path) -> str:
    """파일명에서 시간 추출 (HHMM)"""
    return filepath.stem.split('_')[1]


def compare_two_csvs(prev_df: pd.DataFrame, curr_df: pd.DataFrame) -> pd.DataFrame:
    """두 CSV 비교하여 delta 계산"""
    global HAS_KIS_DATA

    # 기본 컬럼
    prev_cols = ['code', 'v2', 'v4', 'v5', 'v3.5', 'v9_prob', 'close', 'volume']

    # 한투 API 컬럼 존재 시 추가
    kis_cols = ['buy_strength', 'foreign_net', 'inst_net', 'rel_strength']
    available_kis_cols = [c for c in kis_cols if c in prev_df.columns and c in curr_df.columns]

    if available_kis_cols:
        HAS_KIS_DATA = True
        prev_cols.extend(available_kis_cols)

    # 공통 종목만
    merged = curr_df.merge(
        prev_df[prev_cols],
        on='code',
        how='inner',
        suffixes=('', '_prev')
    )

    # Delta 계산
    merged['v2_delta'] = merged['v2'] - merged['v2_prev']
    merged['v4_delta'] = merged['v4'] - merged['v4_prev']
    merged['v5_delta'] = merged['v5'] - merged['v5_prev']
    merged['v35_delta'] = merged['v3.5'] - merged['v3.5_prev']
    merged['v9_delta'] = merged['v9_prob'] - merged['v9_prob_prev']

    # 가격/거래량 변화
    merged['price_change'] = ((merged['close'] - merged['close_prev']) / merged['close_prev'] * 100).round(2)
    merged['volume_ratio'] = (merged['volume'] / merged['volume_prev']).round(2)
    merged['volume_ratio'] = merged['volume_ratio'].replace([np.inf, -np.inf], 0).fillna(0)

    # 한투 API 데이터 delta (존재 시)
    if 'buy_strength' in merged.columns and 'buy_strength_prev' in merged.columns:
        merged['buy_strength_delta'] = merged['buy_strength'] - merged['buy_strength_prev']
    if 'foreign_net' in merged.columns and 'foreign_net_prev' in merged.columns:
        merged['foreign_net_delta'] = merged['foreign_net'] - merged['foreign_net_prev']

    return merged


def analyze_all_pairs(date_str: str) -> list:
    """하루 전체 CSV 쌍 분석"""
    files = get_csv_files(date_str)
    if len(files) < 2:
        print(f"파일이 2개 미만입니다: {len(files)}개")
        return []

    results = []
    for i in range(1, len(files)):
        prev_file = files[i-1]
        curr_file = files[i]

        prev_df = load_csv(prev_file)
        curr_df = load_csv(curr_file)

        merged = compare_two_csvs(prev_df, curr_df)

        prev_time = get_timestamp_from_filename(prev_file)
        curr_time = get_timestamp_from_filename(curr_file)

        results.append({
            'prev_time': prev_time,
            'curr_time': curr_time,
            'data': merged
        })

    return results


# ============================================================================
# Tier 판정 함수
# ============================================================================
def has_volume_surge_signal(signals_str: str) -> bool:
    """VOLUME_EXPLOSION 또는 VOLUME_SURGE_3X 시그널 확인"""
    if pd.isna(signals_str):
        return False
    return 'VOLUME_EXPLOSION' in signals_str or 'VOLUME_SURGE_3X' in signals_str


def has_pattern_signal(signals_str: str) -> bool:
    """BB_SQUEEZE 또는 VCP_PATTERN 시그널 확인"""
    if pd.isna(signals_str):
        return False
    return 'BB_SQUEEZE' in signals_str or 'VCP_PATTERN' in signals_str


def check_tier1(row: pd.Series) -> bool:
    """Tier 1 조건 확인"""
    cfg = TIER_CONFIG['tier1']['conditions']

    if row['v2'] < cfg['v2_min']:
        return False
    if row['v2_delta'] < cfg['v2_delta_min']:
        return False
    if not has_volume_surge_signal(row.get('signals', '')):
        return False
    if row['v4'] < cfg['v4_min']:
        return False
    # 거래대금은 prev_amount 컬럼 사용 (전일 거래대금)
    # 장중에는 당일 거래대금을 알기 어려우므로 volume * close로 추정
    est_amount = row['close'] * row['volume']
    if est_amount < cfg['amount_min']:
        return False

    # 체결강도 조건 (한투 API 데이터 존재 시)
    if HAS_KIS_DATA and 'buy_strength' in row:
        buy_strength = row.get('buy_strength', 0)
        if buy_strength > 0 and buy_strength < cfg.get('buy_strength_min', 0):
            return False  # 체결강도 미달

    return True


def check_tier2(row: pd.Series) -> bool:
    """Tier 2 조건 확인"""
    cfg = TIER_CONFIG['tier2']['conditions']

    if row['v2'] < cfg['v2_min']:
        return False
    if row['v2_delta'] < cfg['v2_delta_min']:
        return False
    if row['volume_ratio'] < cfg['volume_ratio_min']:
        return False
    # V3.5 >= 40 또는 V5 >= 50
    if row['v3.5'] < cfg['v35_min'] and row['v5'] < cfg['v5_min']:
        return False

    # 체결강도 조건 (한투 API 데이터 존재 시)
    if HAS_KIS_DATA and 'buy_strength' in row:
        buy_strength = row.get('buy_strength', 0)
        if buy_strength > 0 and buy_strength < cfg.get('buy_strength_min', 0):
            return False

    return True


def check_tier3(row: pd.Series) -> bool:
    """Tier 3 조건 확인"""
    cfg = TIER_CONFIG['tier3']['conditions']

    if row['v2'] < cfg['v2_min']:
        return False
    # 패턴 시그널 또는 V9 >= 55%
    if not has_pattern_signal(row.get('signals', '')) and row['v9_prob'] < cfg['v9_min']:
        return False

    return True


def detect_surge_candidates(merged_df: pd.DataFrame) -> dict:
    """급등 후보 감지"""
    candidates = {
        'tier1': [],
        'tier2': [],
        'tier3': []
    }

    for _, row in merged_df.iterrows():
        if check_tier1(row):
            candidates['tier1'].append(row)
        elif check_tier2(row):
            candidates['tier2'].append(row)
        elif check_tier3(row):
            candidates['tier3'].append(row)

    return candidates


# ============================================================================
# 급락 경고 감지
# ============================================================================
def detect_drop_warnings(merged_df: pd.DataFrame, watch_codes: list = None) -> dict:
    """급락 경고 감지"""
    warnings = {
        'critical': [],
        'high': [],
        'medium': []
    }

    # 감시 대상 필터
    if watch_codes:
        df = merged_df[merged_df['code'].isin(watch_codes)]
    else:
        df = merged_df

    for _, row in df.iterrows():
        # CRITICAL: V2 = 0 (역배열)
        if row['v2'] == 0:
            warnings['critical'].append({
                'code': row['code'],
                'name': row['name'],
                'reason': 'V2=0 (역배열)',
                'v2': row['v2'],
                'v2_prev': row['v2_prev'],
                'change_pct': row['change_pct']
            })

        # CRITICAL: V2 급락 (-15 이상)
        elif row['v2_delta'] <= -15:
            warnings['critical'].append({
                'code': row['code'],
                'name': row['name'],
                'reason': f"V2 급락 ({row['v2_delta']:+.0f})",
                'v2': row['v2'],
                'v2_prev': row['v2_prev'],
                'change_pct': row['change_pct']
            })

        # HIGH: 고거래량 + 음봉
        if row['volume_ratio'] >= 3.0 and row['price_change'] < -2.0:
            warnings['high'].append({
                'code': row['code'],
                'name': row['name'],
                'reason': f"분배패턴 (거래량 {row['volume_ratio']:.1f}배, {row['price_change']:+.1f}%)",
                'v2': row['v2'],
                'change_pct': row['change_pct']
            })

        # HIGH: RSI_FALLING_KNIFE
        signals = row.get('signals', '')
        if isinstance(signals, str) and 'RSI_FALLING_KNIFE' in signals:
            warnings['high'].append({
                'code': row['code'],
                'name': row['name'],
                'reason': 'RSI_FALLING_KNIFE',
                'v2': row['v2'],
                'change_pct': row['change_pct']
            })

    return warnings


def detect_consecutive_v2_drop(results: list, watch_codes: list = None) -> list:
    """V2 3연속 하락 감지 (하루 전체 데이터 필요)"""
    if len(results) < 3:
        return []

    # 종목별 V2 추적
    code_v2_history = {}

    for r in results:
        for _, row in r['data'].iterrows():
            code = row['code']
            if code not in code_v2_history:
                code_v2_history[code] = []
            code_v2_history[code].append({
                'time': r['curr_time'],
                'v2': row['v2'],
                'name': row['name']
            })

    # 3연속 하락 확인
    warnings = []
    for code, history in code_v2_history.items():
        if watch_codes and code not in watch_codes:
            continue

        if len(history) >= 3:
            # 마지막 3개
            last3 = history[-3:]
            if all(last3[i]['v2'] > last3[i+1]['v2'] for i in range(2)):
                drop = last3[0]['v2'] - last3[-1]['v2']
                warnings.append({
                    'code': code,
                    'name': last3[-1]['name'],
                    'reason': f"V2 3연속 하락 ({last3[0]['v2']}→{last3[-1]['v2']}, -{drop}점)",
                    'v2_history': [h['v2'] for h in last3],
                    'times': [h['time'] for h in last3]
                })

    return warnings


# ============================================================================
# 복합 스코어 계산
# ============================================================================
def calculate_composite_score(row: pd.Series) -> float:
    """복합 스코어 계산 (surge_score)"""
    score = row['v2'] * 0.35

    # 패턴 보너스 (V4)
    if row['v4'] >= 60:
        score += 20
    elif row['v4'] >= 50:
        score += 10

    # 에너지 보너스 (V5)
    if row['v5'] >= 70:
        score += 12
    elif row['v5'] >= 60:
        score += 8

    # 와이코프 보너스 (V3.5)
    if row['v3.5'] >= 50:
        score += 7

    # 반등 보너스 (V2 < 30 & V8 >= 50)
    if row['v2'] < 30 and row['v8'] >= 50:
        score += 10

    # 갭상승 확률 보너스 (V9)
    if row['v9_prob'] >= 60:
        score += 10
    elif row['v9_prob'] >= 55:
        score += 8

    return round(score, 1)


# ============================================================================
# 출력 함수
# ============================================================================
def print_surge_candidates(candidates: dict, prev_time: str, curr_time: str):
    """급등 후보 출력"""
    print(f"\n{'='*70}")
    print(f"  급등 후보 분석 ({prev_time} → {curr_time})")
    print(f"{'='*70}")

    for tier_key in ['tier1', 'tier2', 'tier3']:
        tier_info = TIER_CONFIG[tier_key]
        tier_list = candidates[tier_key]

        print(f"\n[{tier_info['name']}] {tier_info['desc']} - {len(tier_list)}개")
        print("-" * 70)

        if not tier_list:
            print("  (해당 없음)")
            continue

        # DataFrame으로 변환하여 정렬
        df = pd.DataFrame(tier_list)
        df['composite'] = df.apply(calculate_composite_score, axis=1)
        df = df.sort_values('composite', ascending=False)

        for _, row in df.head(10).iterrows():
            signals = row.get('signals', '')
            signal_short = signals[:40] + '...' if len(str(signals)) > 40 else signals
            print(f"  {row['code']} {row['name']:<12} | "
                  f"V2={row['v2']:2.0f}(Δ{row['v2_delta']:+3.0f}) "
                  f"V4={row['v4']:2.0f} V5={row['v5']:2.0f} V9={row['v9_prob']:4.1f}% | "
                  f"종합={row['composite']:4.1f} | {row['change_pct']:+5.2f}%")


def print_drop_warnings(warnings: dict, prev_time: str, curr_time: str):
    """급락 경고 출력"""
    total = sum(len(v) for v in warnings.values())
    if total == 0:
        return

    print(f"\n{'='*70}")
    print(f"  급락 경고 ({prev_time} → {curr_time})")
    print(f"{'='*70}")

    for level in ['critical', 'high', 'medium']:
        level_list = warnings[level]
        if not level_list:
            continue

        level_name = DROP_WARNING_CONFIG[level]['name']
        print(f"\n[{level_name}] - {len(level_list)}개")
        print("-" * 70)

        for w in level_list[:10]:
            print(f"  {w['code']} {w['name']:<12} | {w['reason']} | {w.get('change_pct', 0):+.2f}%")


def print_watch_stocks(merged_df: pd.DataFrame, watch_codes: list, prev_time: str, curr_time: str):
    """특정 종목 추적 결과 출력"""
    df = merged_df[merged_df['code'].isin(watch_codes)]

    if df.empty:
        print(f"\n감시 종목이 데이터에 없습니다: {watch_codes}")
        return

    print(f"\n{'='*70}")
    print(f"  종목 추적 ({prev_time} → {curr_time})")
    print(f"{'='*70}")

    for _, row in df.iterrows():
        print(f"\n{row['code']} {row['name']}")
        print(f"  가격: {row['close_prev']:,} → {row['close']:,} ({row['price_change']:+.2f}%)")
        print(f"  V2:   {row['v2_prev']:.0f} → {row['v2']:.0f} (Δ{row['v2_delta']:+.0f})")
        print(f"  V4:   {row['v4_prev']:.0f} → {row['v4']:.0f} (Δ{row['v4_delta']:+.0f})")
        print(f"  V5:   {row['v5_prev']:.0f} → {row['v5']:.0f} (Δ{row['v5_delta']:+.0f})")
        print(f"  V9:   {row['v9_prob_prev']:.1f}% → {row['v9_prob']:.1f}% (Δ{row['v9_delta']:+.1f})")
        print(f"  거래량 배율: {row['volume_ratio']:.2f}x")
        print(f"  시그널: {row.get('signals', '')}")


# ============================================================================
# 메인 함수
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='스코어 변화 분석기')
    parser.add_argument('--date', type=str, help='분석할 날짜 (YYYYMMDD)', default=None)
    parser.add_argument('--all', action='store_true', help='하루 전체 분석')
    parser.add_argument('--watch', type=str, help='감시할 종목 코드 (쉼표 구분)', default=None)
    parser.add_argument('--top', type=int, default=10, help='상위 N개 출력')
    args = parser.parse_args()

    # 날짜 설정
    date_str = args.date or datetime.now().strftime('%Y%m%d')

    # 감시 종목 파싱
    watch_codes = None
    if args.watch:
        watch_codes = [c.strip().zfill(6) for c in args.watch.split(',')]

    print(f"\n{'#'*70}")
    print(f"#  스코어 변화 분석기 - {date_str}")
    print(f"{'#'*70}")

    files = get_csv_files(date_str)
    print(f"\n대상 파일: {len(files)}개")

    if len(files) < 2:
        print("분석에 필요한 파일이 부족합니다 (최소 2개 필요)")
        return

    if args.all:
        # 하루 전체 분석
        results = analyze_all_pairs(date_str)

        # 전체 급등 후보 집계
        all_tier1, all_tier2, all_tier3 = [], [], []

        for r in results:
            candidates = detect_surge_candidates(r['data'])
            all_tier1.extend([dict(row) | {'time': r['curr_time']} for row in candidates['tier1']])
            all_tier2.extend([dict(row) | {'time': r['curr_time']} for row in candidates['tier2']])
            all_tier3.extend([dict(row) | {'time': r['curr_time']} for row in candidates['tier3']])

            warnings = detect_drop_warnings(r['data'], watch_codes)
            print_drop_warnings(warnings, r['prev_time'], r['curr_time'])

        # 3연속 하락 감지
        consec_warnings = detect_consecutive_v2_drop(results, watch_codes)
        if consec_warnings:
            print(f"\n{'='*70}")
            print(f"  V2 3연속 하락 경고")
            print(f"{'='*70}")
            for w in consec_warnings:
                print(f"  {w['code']} {w['name']:<12} | {w['reason']}")

        # 요약
        print(f"\n{'='*70}")
        print(f"  하루 전체 요약 ({date_str})")
        print(f"{'='*70}")
        print(f"  Tier 1 감지: {len(all_tier1)}건")
        print(f"  Tier 2 감지: {len(all_tier2)}건")
        print(f"  Tier 3 감지: {len(all_tier3)}건")

        # 가장 자주 감지된 종목 Top 10
        if all_tier1 or all_tier2:
            from collections import Counter
            all_codes = [r['code'] for r in all_tier1 + all_tier2]
            top_codes = Counter(all_codes).most_common(args.top)
            print(f"\n  자주 감지된 종목 (Tier 1+2):")
            for code, cnt in top_codes:
                # 최신 데이터에서 종목명 조회
                name = next((r['name'] for r in all_tier1 + all_tier2 if r['code'] == code), code)
                print(f"    {code} {name}: {cnt}회")

    else:
        # 최신 2개 파일만 비교
        prev_file = files[-2]
        curr_file = files[-1]

        prev_time = get_timestamp_from_filename(prev_file)
        curr_time = get_timestamp_from_filename(curr_file)

        print(f"비교: {prev_file.name} → {curr_file.name}")

        prev_df = load_csv(prev_file)
        curr_df = load_csv(curr_file)

        merged = compare_two_csvs(prev_df, curr_df)
        print(f"공통 종목: {len(merged)}개")

        # 특정 종목 추적
        if watch_codes:
            print_watch_stocks(merged, watch_codes, prev_time, curr_time)

        # 급등 후보 감지
        candidates = detect_surge_candidates(merged)
        print_surge_candidates(candidates, prev_time, curr_time)

        # 급락 경고 감지
        warnings = detect_drop_warnings(merged, watch_codes)
        print_drop_warnings(warnings, prev_time, curr_time)

        # V2 상승폭 Top 10
        print(f"\n{'='*70}")
        print(f"  V2 상승폭 Top {args.top}")
        print(f"{'='*70}")
        top_v2_delta = merged.nlargest(args.top, 'v2_delta')
        for _, row in top_v2_delta.iterrows():
            print(f"  {row['code']} {row['name']:<12} | "
                  f"V2: {row['v2_prev']:.0f}→{row['v2']:.0f} (Δ{row['v2_delta']:+.0f}) | "
                  f"{row['change_pct']:+.2f}%")

        # V2 하락폭 Top 10
        print(f"\n{'='*70}")
        print(f"  V2 하락폭 Top {args.top}")
        print(f"{'='*70}")
        bottom_v2_delta = merged.nsmallest(args.top, 'v2_delta')
        for _, row in bottom_v2_delta.iterrows():
            print(f"  {row['code']} {row['name']:<12} | "
                  f"V2: {row['v2_prev']:.0f}→{row['v2']:.0f} (Δ{row['v2_delta']:+.0f}) | "
                  f"{row['change_pct']:+.2f}%")

    print()


if __name__ == "__main__":
    main()
