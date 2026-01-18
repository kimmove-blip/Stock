"""
연속 출현 및 순위 변동 추적 모듈
- 과거 TOP100 데이터를 분석하여 연속 출현 일수 계산
- 전일 대비 순위 변동 계산
- 신호별 연속 출현 추적 (방안 A)
- 2단계 분류 지원 (방안 C)
"""

import json
import glob
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

OUTPUT_DIR = Path(__file__).parent / "output"


def get_historical_files(days: int = 30) -> List[Path]:
    """최근 N일간의 TOP100 JSON 파일 목록 (날짜 역순)"""
    json_files = sorted(
        glob.glob(str(OUTPUT_DIR / "top100_*.json")),
        reverse=True
    )
    return [Path(f) for f in json_files[:days]]


def load_top100_data(filepath: Path) -> Dict[str, dict]:
    """JSON 파일에서 종목코드 -> {rank, score, name} 매핑 로드"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        stocks = data.get('stocks', [])
        result = {}
        for i, stock in enumerate(stocks, 1):
            code = stock.get('code')
            if code:
                result[code] = {
                    'rank': i,
                    'score': stock.get('score', 0),
                    'name': stock.get('name', '')
                }
        return result
    except Exception as e:
        print(f"[연속추적] 파일 로드 실패 ({filepath}): {e}")
        return {}


def get_date_from_filename(filepath: Path) -> Optional[str]:
    """파일명에서 날짜 추출 (top100_20260116.json -> 20260116)"""
    name = filepath.stem  # top100_20260116
    parts = name.split('_')
    if len(parts) >= 2:
        return parts[1]
    return None


def calculate_streak_and_rank_change(
    current_results: List[dict],
    max_history_days: int = 30
) -> List[dict]:
    """
    현재 결과에 연속 출현 일수와 순위 변동 추가

    Args:
        current_results: 오늘의 스크리닝 결과 리스트
        max_history_days: 과거 데이터 조회 일수

    Returns:
        streak, rank_change 필드가 추가된 결과 리스트
    """
    # 과거 파일 로드
    history_files = get_historical_files(max_history_days)

    if not history_files:
        # 과거 데이터 없으면 모두 신규
        for i, r in enumerate(current_results, 1):
            r['streak'] = 1
            r['rank_change'] = None  # NEW
            r['prev_rank'] = None
        return current_results

    # 가장 최근 파일 (전일)
    yesterday_file = history_files[0]
    yesterday_data = load_top100_data(yesterday_file)

    # 과거 모든 데이터 로드 (연속 계산용)
    history_data = []
    for f in history_files:
        data = load_top100_data(f)
        if data:
            history_data.append(data)

    # 현재 결과에 추가 정보 계산
    for i, r in enumerate(current_results, 1):
        code = r['code']

        # 1. 순위 변동 계산
        if code in yesterday_data:
            prev_rank = yesterday_data[code]['rank']
            r['prev_rank'] = prev_rank
            r['rank_change'] = prev_rank - i  # 양수면 상승, 음수면 하락
        else:
            r['prev_rank'] = None
            r['rank_change'] = None  # NEW

        # 2. 연속 출현 일수 계산
        streak = 0
        for hist in history_data:
            if code in hist:
                streak += 1
            else:
                break  # 연속이 끊기면 중단

        # 오늘 포함
        r['streak'] = streak + 1

    return current_results


def format_rank_change(rank_change: Optional[int]) -> str:
    """순위 변동을 문자열로 포맷"""
    if rank_change is None:
        return "NEW"
    elif rank_change > 0:
        return f"↑{rank_change}"
    elif rank_change < 0:
        return f"↓{abs(rank_change)}"
    else:
        return "-"


def format_streak(streak: int) -> str:
    """연속 일수를 문자열로 포맷"""
    if streak >= 5:
        return f"{streak}일 🔥"
    elif streak >= 3:
        return f"{streak}일 ⭐"
    else:
        return f"{streak}일"


def get_streak_stats(results: List[dict]) -> dict:
    """연속 출현 통계 계산"""
    if not results:
        return {}

    streaks = [r.get('streak', 1) for r in results]
    new_entries = sum(1 for r in results if r.get('rank_change') is None)
    rank_up = sum(1 for r in results if r.get('rank_change') is not None and r.get('rank_change', 0) > 0)
    rank_down = sum(1 for r in results if r.get('rank_change') is not None and r.get('rank_change', 0) < 0)
    rank_same = sum(1 for r in results if r.get('rank_change') == 0)

    return {
        'total': len(results),
        'new_entries': new_entries,
        'continued': len(results) - new_entries,
        'rank_up': rank_up,
        'rank_down': rank_down,
        'rank_same': rank_same,
        'max_streak': max(streaks) if streaks else 0,
        'avg_streak': sum(streaks) / len(streaks) if streaks else 0,
        'streak_5plus': sum(1 for s in streaks if s >= 5),
        'streak_3plus': sum(1 for s in streaks if s >= 3),
    }


def get_signal_streak(
    code: str,
    current_signals: List[str],
    max_history_days: int = 10
) -> Dict[str, int]:
    """
    종목의 신호별 연속 출현 일수 계산 (방안 A)

    Args:
        code: 종목코드
        current_signals: 현재 신호 리스트
        max_history_days: 과거 데이터 조회 일수

    Returns:
        signal -> streak_days 매핑
    """
    history_files = get_historical_files(max_history_days)
    signal_streaks = {}

    for signal in current_signals:
        streak = 0

        # 과거 파일에서 해당 종목의 해당 신호 연속 출현 확인
        for filepath in history_files:
            data = load_top100_data(filepath)
            if code not in data:
                break  # 종목이 리스트에 없으면 중단

            # 파일에서 전체 데이터 다시 로드 (signals 포함)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    full_data = json.load(f)

                stock_found = False
                for stock in full_data.get('stocks', []):
                    if stock.get('code') == code:
                        if signal in stock.get('signals', []):
                            streak += 1
                            stock_found = True
                        break

                if not stock_found or (stock_found and signal not in stock.get('signals', [])):
                    break

            except Exception:
                break

        # 오늘 포함
        signal_streaks[signal] = streak + 1

    return signal_streaks


def apply_streak_weighted_score(
    current_results: List[dict],
    max_history_days: int = 10
) -> List[dict]:
    """
    신호 지속성 기반 가중치 적용 (방안 A)

    신호가 연속 출현한 일수에 따라 점수 조정:
    - 1일: 0.5배 (신규 신호는 약하게)
    - 2일: 0.8배
    - 3일+: 1.0배 (확인된 신호)
    - 5일+: 1.2배 (강력한 신호)

    Args:
        current_results: 오늘의 스크리닝 결과
        max_history_days: 과거 데이터 조회 일수

    Returns:
        adjusted_score 필드가 추가된 결과 리스트
    """
    from config import StreakConfig

    history_files = get_historical_files(max_history_days)

    # 과거 데이터 캐시 (종목별 신호)
    history_cache = []
    for filepath in history_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                full_data = json.load(f)
            stock_signals = {}
            for stock in full_data.get('stocks', []):
                code = stock.get('code')
                if code:
                    stock_signals[code] = set(stock.get('signals', []))
            history_cache.append(stock_signals)
        except Exception:
            continue

    for result in current_results:
        code = result['code']
        signals = result.get('signals', [])
        original_score = result.get('score', 0)

        # 각 신호의 연속 출현 일수 계산
        signal_streak_weights = []

        for signal in signals:
            streak = 0
            for hist in history_cache:
                if code in hist and signal in hist[code]:
                    streak += 1
                else:
                    break

            # 오늘 포함
            streak += 1

            # 연속 일수에 따른 가중치
            weight = StreakConfig.get_streak_weight(streak)
            signal_streak_weights.append({
                'signal': signal,
                'streak': streak,
                'weight': weight
            })

        # 평균 가중치 계산
        if signal_streak_weights:
            avg_weight = sum(s['weight'] for s in signal_streak_weights) / len(signal_streak_weights)
        else:
            avg_weight = 1.0

        # 신규 진입 종목 페널티
        if result.get('rank_change') is None:  # NEW
            avg_weight *= StreakConfig.NEW_ENTRY_PENALTY

        # 조정된 점수 계산
        adjusted_score = int(original_score * avg_weight)
        adjusted_score = max(0, min(100, adjusted_score))

        result['original_score'] = original_score
        result['adjusted_score'] = adjusted_score
        result['streak_weight'] = round(avg_weight, 2)
        result['signal_streaks'] = signal_streak_weights

    return current_results


def classify_stocks(
    results: List[dict],
    max_stable: int = 50,
    max_new: int = 50
) -> Tuple[List[dict], List[dict]]:
    """
    2단계 분류 (방안 C)

    종목을 안정 추천과 신규 관심으로 분류:
    - 안정 추천: 3일+ 연속 출현 + 점수 50+
    - 신규 관심: 나머지 (NEW 또는 단기 출현)

    Args:
        results: streak 정보가 포함된 결과 리스트
        max_stable: 안정 추천 최대 종목 수
        max_new: 신규 관심 최대 종목 수

    Returns:
        (stable_list, new_list) 튜플
    """
    from config import ClassificationConfig

    stable = []
    new_interest = []

    for r in results:
        streak = r.get('streak', 1)
        score = r.get('adjusted_score', r.get('score', 0))

        # 안정 추천 기준
        if streak >= ClassificationConfig.STABLE_MIN_STREAK and \
           score >= ClassificationConfig.STABLE_MIN_SCORE:
            stable.append(r)
        # 신규 관심 기준
        elif score >= ClassificationConfig.NEW_MIN_SCORE:
            new_interest.append(r)

    # 안정 추천: adjusted_score 기준 정렬
    stable.sort(key=lambda x: x.get('adjusted_score', x.get('score', 0)), reverse=True)
    stable = stable[:max_stable]

    # 신규 관심: score 기준 정렬
    new_interest.sort(key=lambda x: x.get('score', 0), reverse=True)
    new_interest = new_interest[:max_new]

    return stable, new_interest


def get_classification_stats(stable: List[dict], new_interest: List[dict]) -> dict:
    """분류 통계"""
    def calc_stats(items):
        if not items:
            return {'count': 0, 'avg_score': 0, 'avg_streak': 0}
        scores = [r.get('adjusted_score', r.get('score', 0)) for r in items]
        streaks = [r.get('streak', 1) for r in items]
        return {
            'count': len(items),
            'avg_score': round(sum(scores) / len(scores), 1),
            'avg_streak': round(sum(streaks) / len(streaks), 1)
        }

    return {
        'stable': calc_stats(stable),
        'new_interest': calc_stats(new_interest),
        'total': len(stable) + len(new_interest)
    }


if __name__ == "__main__":
    # 테스트: 오늘 데이터로 테스트
    today_file = get_historical_files(1)
    if today_file:
        with open(today_file[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        results = data.get('stocks', [])[:10]
        results = calculate_streak_and_rank_change(results)

        print("=== 연속 출현 및 순위 변동 테스트 ===")
        for r in results:
            rank_str = format_rank_change(r.get('rank_change'))
            streak_str = format_streak(r.get('streak', 1))
            print(f"{r['name']:<12} | 순위변동: {rank_str:>5} | 연속: {streak_str}")

        stats = get_streak_stats(results)
        print(f"\n통계: 신규 {stats['new_entries']}개, 연속 {stats['continued']}개")

        # 신호 지속성 가중치 테스트
        print("\n=== 신호 지속성 가중치 테스트 ===")
        results = apply_streak_weighted_score(results)
        for r in results[:5]:
            print(f"{r['name']:<12} | 원점수: {r.get('original_score', 0):>3} | "
                  f"조정점수: {r.get('adjusted_score', 0):>3} | 가중치: {r.get('streak_weight', 1):.2f}")

        # 2단계 분류 테스트
        print("\n=== 2단계 분류 테스트 ===")
        stable, new_list = classify_stocks(results)
        print(f"안정 추천: {len(stable)}개")
        print(f"신규 관심: {len(new_list)}개")
