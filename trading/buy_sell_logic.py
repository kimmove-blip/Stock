"""
매매 전략 함수 모듈

auto_trader.py에서 분리된 매수/매도 전략 함수들
"""

import re
from typing import Dict, List, Tuple


def parse_condition(condition_str: str) -> list:
    """
    조건 문자열을 파싱하여 조건 리스트로 변환
    예: "V1>=60 AND V5>=50 AND V4>40" -> [{'score': 'v1', 'op': '>=', 'value': 60, 'connector': 'AND'}, ...]

    확장 지원:
    - 델타 조건: V4_DELTA<=0, CHANGE_DELTA<0
    - 음수 값: V4_DELTA>=-5
    """
    if not condition_str:
        return []

    parts = re.split(r'\s+(AND|OR)\s+', condition_str, flags=re.IGNORECASE)
    conditions = []
    current_connector = 'AND'

    for part in parts:
        part = part.strip()
        if part.upper() in ('AND', 'OR'):
            current_connector = part.upper()
        else:
            # 델타 조건 (V4_DELTA<=0, CHANGE_DELTA<0 등)
            delta_match = re.match(r'^(V\d+_DELTA|CHANGE_DELTA)\s*(>=|<=|>|<|=)\s*(-?\d+\.?\d*)$', part, re.IGNORECASE)
            if delta_match:
                conditions.append({
                    'score': delta_match.group(1).lower(),
                    'op': delta_match.group(2),
                    'value': float(delta_match.group(3)),
                    'connector': current_connector
                })
            else:
                # 기존 스코어 조건 (V1>=60 등)
                match = re.match(r'^(V\d+)\s*(>=|<=|>|<|=)\s*(\d+)$', part, re.IGNORECASE)
                if match:
                    conditions.append({
                        'score': match.group(1).lower(),
                        'op': match.group(2),
                        'value': int(match.group(3)),
                        'connector': current_connector
                    })
    return conditions


def evaluate_conditions(conditions: list, scores: dict) -> bool:
    """
    조건 리스트를 스코어 딕셔너리로 평가
    scores: {'v1': 70, 'v2': 60, 'v4': 45, 'v5': 55, 'v4_delta': -2, 'change_delta': -0.5}

    델타 키 지원: v4_delta, v1_delta, v2_delta, v5_delta, change_delta
    """
    if not conditions:
        return False

    results = []
    connectors = []

    for cond in conditions:
        score_key = cond['score']
        score_value = scores.get(score_key, 0)
        op = cond['op']
        target = cond['value']

        if op == '>=':
            result = score_value >= target
        elif op == '<=':
            result = score_value <= target
        elif op == '>':
            result = score_value > target
        elif op == '<':
            result = score_value < target
        elif op == '=':
            result = score_value == target
        else:
            result = False

        results.append(result)
        if len(results) > 1:
            connectors.append(cond['connector'])

    # 조건 평가 (AND/OR 처리)
    if len(results) == 1:
        return results[0]

    # 순차적으로 평가
    final = results[0]
    for i, connector in enumerate(connectors):
        if connector == 'AND':
            final = final and results[i + 1]
        else:  # OR
            final = final or results[i + 1]

    return final


def check_hold_condition(scores: dict, profit_rate: float, stop_loss_rate: float = 3.0) -> Tuple[bool, str]:
    """
    개선된 매도/홀딩 판단 함수

    Args:
        scores: {'v1': x, 'v2': y, 'v4': z, 'v5': w, 'v4_delta': d, ...}
        profit_rate: 현재 수익률 (%)
        stop_loss_rate: 손절 기준 (%)

    Returns:
        (should_sell: bool, reason: str)
    """
    v5 = scores.get('v5', 50)
    v4 = scores.get('v4', 50)
    v2 = scores.get('v2', 50)

    # 1. 강제 손절 (스코어 무관)
    if profit_rate <= -stop_loss_rate:
        return True, f"손절 ({profit_rate:.1f}% <= -{stop_loss_rate}%)"

    # 2. V5 >= 70이면 홀딩 (추가 상승 가능, 60→70 상향)
    if v5 >= 70:
        return False, f"V5={v5}>=70 홀딩 (추가상승여력)"

    # 3. V4 >= 55이면 홀딩
    if v4 >= 55:
        return False, f"V4={v4}>=55 홀딩"

    # 4. V2 >= 60이면 홀딩
    if v2 >= 60:
        return False, f"V2={v2}>=60 홀딩"

    # 5. 매도 조건: V4 < 40
    if v4 < 40:
        return True, f"V4={v4}<40 매도"

    # 6. 매도 조건: V2 < 50 AND V4 < 45
    if v2 < 50 and v4 < 45:
        return True, f"V2={v2}<50 & V4={v4}<45 매도"

    # 7. 기본 홀딩
    return False, "조건미충족 홀딩"


def get_change_limit_by_marcap(marcap: float) -> float:
    """시총별 상승률 제한 반환

    - 대형주 (1조+): 5%
    - 중형주 (3000억~1조): 10%
    - 소형주 (3000억 미만): 15%
    """
    if marcap >= 1_000_000_000_000:  # 1조 이상
        return 5.0
    elif marcap >= 300_000_000_000:  # 3000억 이상
        return 10.0
    else:
        return 15.0


def should_buy_advanced(scores: dict, current_hour: int, use_time_filter: bool = True) -> Tuple[bool, str]:
    """
    개선된 매수 조건 판단 함수 (6일 백테스트 최적화 결과 적용)

    최적화 조건 (2026-02-03 백테스트 기반):
    - V2 >= 55 (기존 70에서 완화)
    - V4 >= 40 (기존 50에서 완화)
    - V1 조건 제거 (역발상 전략 비효율 확인)

    백테스트 결과:
    - 기존 조건: 7거래, +2,110원/6일
    - 최적화 조건: 524거래, +334,941원/6일 (+55,824원/일)

    Args:
        scores: {'v1': x, 'v2': y, 'v4': z, 'v5': w, 'v4_delta': d, ...}
        current_hour: 현재 시간 (9~15)
        use_time_filter: 시간 필터 사용 여부

    Returns:
        (should_buy: bool, reason: str)
    """
    v2 = scores.get('v2', 0)
    v4 = scores.get('v4', 0)
    v4_delta = scores.get('v4_delta', 0)

    # 오전 전략 (09:30~10:55): V2 >= 55, V4 >= 40
    if current_hour < 11:
        if v2 >= 55 and v4 >= 40:
            return True, f"[오전] V2={v2}>=55, V4={v4}>=40"
        else:
            if v2 < 55:
                return False, f"V2={v2}<55 (오전)"
            return False, f"V4={v4}<40 (오전)"

    # 11시 이후 기본 전략
    # 1. V2 기본 조건 (55 이상)
    if v2 < 55:
        return False, f"V2={v2}<55"

    # 2. V4 기본 조건 (40 이상)
    if v4 < 40:
        return False, f"V4={v4}<40"

    # 3. V4 안정/하락 확인 (V4_DELTA <= 0) - 급등중 종목 제외
    if v4_delta > 0:
        return False, f"V4델타={v4_delta}>0 (급등중 제외)"

    # 모든 조건 충족
    return True, f"V2={v2}>=55, V4={v4}>=40, V4델타={v4_delta}<=0"
