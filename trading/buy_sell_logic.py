"""
매매 전략 함수 모듈

auto_trader.py에서 분리된 매수/매도 전략 함수들
임계값은 config.StrategyConfig에서 중앙 관리
"""

import re
from typing import Dict, List, Tuple

from config import StrategyConfig as SC


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


def get_time_based_stop_loss(current_hour: int = None) -> float:
    """
    시간대별 손절 기준 반환

    - 오전 (09~10시): 5% (빠른 손절)
    - 골든타임 (11~12시): 7% (현행 유지)
    - 오후 (13시 이후): 4% (더 빠른 손절)
    """
    from datetime import datetime
    if current_hour is None:
        current_hour = datetime.now().hour

    if current_hour < 11:
        return SC.STOP_LOSS_MORNING
    elif current_hour < 13:
        return SC.STOP_LOSS_GOLDEN
    else:
        return SC.STOP_LOSS_AFTERNOON


def check_hold_condition(scores: dict, profit_rate: float, stop_loss_rate: float = None,
                         current_hour: int = None) -> Tuple[bool, str]:
    """
    개선된 매도/홀딩 판단 함수 (2026-02-04 수익 극대화 전략)

    V5 기반 강력 홀딩 + 시간대별 손절선 차등 적용

    Args:
        scores: {'v1': x, 'v2': y, 'v4': z, 'v5': w, 'v4_delta': d, ...}
        profit_rate: 현재 수익률 (%)
        stop_loss_rate: 손절 기준 (%), None이면 시간대별 자동 적용
        current_hour: 현재 시간 (테스트용), None이면 자동

    Returns:
        (should_sell: bool, reason: str)
    """
    from datetime import datetime
    if current_hour is None:
        current_hour = datetime.now().hour

    # 시간대별 손절 기준 적용
    if stop_loss_rate is None:
        stop_loss_rate = get_time_based_stop_loss(current_hour)

    v5 = scores.get('v5', 50)
    v4 = scores.get('v4', 50)
    v2 = scores.get('v2', 50)

    # 1. 강제 손절 (스코어 무관, 시간대별 차등)
    if profit_rate <= -stop_loss_rate:
        return True, f"손절 ({profit_rate:.1f}% <= -{stop_loss_rate}%)"

    # 2. V5 >= HOLD_V5_STRONG (70) 이면 강력 홀딩 (익일까지 보유)
    if v5 >= SC.HOLD_V5_STRONG:
        return False, f"V5={v5}>={SC.HOLD_V5_STRONG} 강력홀딩 (익일보유)"

    # 3. V5 >= HOLD_V5_MIN (60) AND V4 >= 50 이면 홀딩
    if v5 >= SC.HOLD_V5_MIN and v4 >= 50:
        return False, f"V5={v5}>={SC.HOLD_V5_MIN} & V4={v4}>=50 홀딩"

    # 4. V4 >= HOLD_V4_MIN 이면 홀딩
    if v4 >= SC.HOLD_V4_MIN:
        return False, f"V4={v4}>={SC.HOLD_V4_MIN} 홀딩"

    # 5. V2 >= HOLD_V2_MIN 이면 홀딩
    if v2 >= SC.HOLD_V2_MIN:
        return False, f"V2={v2}>={SC.HOLD_V2_MIN} 홀딩"

    # 6. 매도 조건: V4 < SELL_V4_MAX
    if v4 < SC.SELL_V4_MAX:
        return True, f"V4={v4}<{SC.SELL_V4_MAX} 매도"

    # 7. 매도 조건: V2 < SELL_V2_MAX AND V4 < SELL_V4_COMBINED
    if v2 < SC.SELL_V2_MAX and v4 < SC.SELL_V4_COMBINED:
        return True, f"V2={v2}<{SC.SELL_V2_MAX} & V4={v4}<{SC.SELL_V4_COMBINED} 매도"

    # 8. 기본 홀딩
    return False, "조건미충족 홀딩"


def get_change_limit_by_marcap(marcap: float) -> float:
    """시총별 상승률 제한 반환

    - 대형주 (1조+): CHANGE_LIMIT_LARGE
    - 중형주 (3000억~1조): CHANGE_LIMIT_MID
    - 소형주 (3000억 미만): CHANGE_LIMIT_SMALL
    """
    if marcap >= 1_000_000_000_000:  # 1조 이상
        return SC.CHANGE_LIMIT_LARGE
    elif marcap >= 300_000_000_000:  # 3000억 이상
        return SC.CHANGE_LIMIT_MID
    else:
        return SC.CHANGE_LIMIT_SMALL


def should_buy_advanced(scores: dict, current_hour: int, use_time_filter: bool = True,
                        signals: list = None, change_pct: float = 0, current_minute: int = 30) -> Tuple[bool, str]:
    """
    개선된 매수 조건 판단 함수 (2026-02-04 수익 극대화 전략 적용)

    시간대별 전략 분리:
    - Early Surge (09:10~09:25): MACD+MA 시그널 필수, V2>=85, V4>=60
    - 오전 (09:30~10:55): V2>=80, V4>=55 (보수적)
    - 골든타임 (11:00~12:55): V2>=70, V4>=45 (완화, 59.3% 승률)
    - 오후 (13:00~14:50): V2>=85, V4>=60 (강화)
    - 14:55 이후: 매수 금지 (정리매도 시간)

    Args:
        scores: {'v1': x, 'v2': y, 'v4': z, 'v5': w, 'v4_delta': d, ...}
        current_hour: 현재 시간 (9~15)
        use_time_filter: 시간 필터 사용 여부
        signals: 시그널 리스트 (예: ['MACD_BULL', 'MA_ALIGNED'])
        change_pct: 등락률
        current_minute: 현재 분 (0~59)

    Returns:
        (should_buy: bool, reason: str)
    """
    v2 = scores.get('v2', 0)
    v4 = scores.get('v4', 0)
    v5 = scores.get('v5', 0)
    v1 = scores.get('v1', 50)
    v4_delta = scores.get('v4_delta', 0)
    signals = signals or []

    # === V5 최소 조건 (2026-02-05 추가) ===
    if v5 < SC.BUY_V5_MIN:
        return False, f"V5={v5}<{SC.BUY_V5_MIN} (추가상승 여력 부족)"

    # === 정리매도 시간 (14:55 이후) - 매수 금지 ===
    if current_hour == 14 and current_minute >= 55:
        return False, f"[정리매도] 14:55 이후 매수 금지"
    if current_hour >= 15:
        return False, f"[정리매도] 15시 이후 매수 금지"

    # === Early Surge Detection (09:10~09:25) ===
    if current_hour == 9 and SC.EARLY_SURGE_START[1] <= current_minute <= SC.EARLY_SURGE_END[1]:
        has_macd_bull = 'MACD_BULL' in signals
        has_ma_signal = any(s in signals for s in ['MA_ALIGNED', 'MA_STEEP', 'MA_20_STEEP', 'MA_20_VERY_STEEP'])
        has_volume_signal = any(s in signals for s in ['VOLUME_EXPLOSION', 'VOLUME_SURGE', 'VOLUME_SURGE_3X', 'VOLUME_HIGH'])
        change_ok = SC.MIN_CHANGE_PCT <= change_pct <= SC.MAX_CHANGE_PCT

        if has_macd_bull and has_ma_signal and change_ok:
            # Early Surge는 시그널 기반이므로 V2/V4 조건 완화
            if v2 >= SC.EARLY_V2_MIN and v4 >= SC.EARLY_V4_MIN:
                vol_note = "+VOL" if has_volume_signal else ""
                return True, f"[EarlySurge] MACD+MA{vol_note}, V2={v2}, V4={v4}, Chg={change_pct:.1f}%"
            else:
                return False, f"[EarlySurge] V2={v2}<{SC.EARLY_V2_MIN} 또는 V4={v4}<{SC.EARLY_V4_MIN}"
        # Early Surge 시그널 없으면 오전 조건으로 폴백
        if v2 >= SC.MORNING_V2_MIN and v4 >= SC.MORNING_V4_MIN:
            return True, f"[오전초반] V2={v2}>={SC.MORNING_V2_MIN}, V4={v4}>={SC.MORNING_V4_MIN}"
        return False, f"[오전초반] V2={v2}<{SC.MORNING_V2_MIN} 또는 V4={v4}<{SC.MORNING_V4_MIN}"

    # === 오전 전략 (09:30~10:55) - 보수적 ===
    if current_hour == 9 or current_hour == 10:
        v2_min = SC.MORNING_V2_MIN
        v4_min = SC.MORNING_V4_MIN
        if v2 >= v2_min and v4 >= v4_min:
            return True, f"[오전] V2={v2}>={v2_min}, V4={v4}>={v4_min}"
        if v2 < v2_min:
            return False, f"V2={v2}<{v2_min} (오전)"
        return False, f"V4={v4}<{v4_min} (오전)"

    # === 골든타임 (11:00~12:55) - 완화 (핵심 개선!) ===
    if SC.GOLDEN_HOUR_START <= current_hour < SC.GOLDEN_HOUR_END:
        v2_min = SC.GOLDEN_V2_MIN
        v4_min = SC.GOLDEN_V4_MIN

        # V1 역발상: V1이 낮을수록 성과 좋음 (분석 결과)
        v1_bonus = v1 <= 40

        if v2 >= v2_min and v4 >= v4_min:
            # V4 델타 체크 (급등중 제외)
            if v4_delta > SC.BUY_V4_DELTA_MAX:
                return False, f"V4델타={v4_delta}>{SC.BUY_V4_DELTA_MAX} (골든타임 급등중)"
            bonus_note = " V1역발상" if v1_bonus else ""
            return True, f"[골든타임] V2={v2}>={v2_min}, V4={v4}>={v4_min}{bonus_note}"
        if v2 < v2_min:
            return False, f"V2={v2}<{v2_min} (골든타임)"
        return False, f"V4={v4}<{v4_min} (골든타임)"

    # === 오후 전략 (13:00~14:50) - 강화 ===
    if current_hour >= SC.GOLDEN_HOUR_END:
        v2_min = SC.AFTERNOON_V2_MIN
        v4_min = SC.AFTERNOON_V4_MIN

        if v2 >= v2_min and v4 >= v4_min:
            # V4 델타 체크 (급등중 제외)
            if v4_delta > SC.BUY_V4_DELTA_MAX:
                return False, f"V4델타={v4_delta}>{SC.BUY_V4_DELTA_MAX} (오후 급등중)"
            return True, f"[오후] V2={v2}>={v2_min}, V4={v4}>={v4_min}"
        if v2 < v2_min:
            return False, f"V2={v2}<{v2_min} (오후)"
        return False, f"V4={v4}<{v4_min} (오후)"

    # 기본 전략 (폴백)
    if v2 >= SC.BUY_V2_MIN and v4 >= SC.BUY_V4_MIN:
        return True, f"V2={v2}>={SC.BUY_V2_MIN}, V4={v4}>={SC.BUY_V4_MIN}"
    return False, f"V2={v2}<{SC.BUY_V2_MIN} 또는 V4={v4}<{SC.BUY_V4_MIN}"
