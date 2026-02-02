"""
스코어링 설정 YAML 로더

사용법:
    from scoring.config import load_scoring_config, get_config

    # YAML 파일에서 설정 로드
    config = load_scoring_config('v2')

    # 규칙 평가
    for group_name, group in config.scoring_groups.items():
        for rule in group.rules:
            if rule.evaluate(indicators):
                score += rule.score
                signals.append(rule.signal)
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
import yaml

# 설정 파일 디렉토리
CONFIG_DIR = Path(__file__).parent


@dataclass
class ScoringRule:
    """개별 스코어링 규칙"""
    name: str
    condition: str
    score: int
    signal: str
    exclusive_group: Optional[str] = None  # 배타적 그룹 (하나만 적용)

    def evaluate(self, indicators: Dict[str, Any]) -> bool:
        """조건 평가

        Args:
            indicators: 지표 딕셔너리

        Returns:
            조건 충족 여부
        """
        try:
            return _evaluate_condition(self.condition, indicators)
        except Exception:
            return False


@dataclass
class DisqualifierRule:
    """과락 규칙"""
    name: str
    condition: str
    signal: str

    def evaluate(self, indicators: Dict[str, Any]) -> bool:
        """과락 조건 평가"""
        try:
            return _evaluate_condition(self.condition, indicators)
        except Exception:
            return False


@dataclass
class ScoringGroup:
    """스코어링 그룹"""
    name: str
    max_score: int = 100
    min_score: int = 0
    rules: List[ScoringRule] = field(default_factory=list)

    def calculate_score(self, indicators: Dict[str, Any]) -> tuple:
        """그룹 점수 계산

        Args:
            indicators: 지표 딕셔너리

        Returns:
            (점수, 발생 신호 리스트)
        """
        total_score = 0
        signals = []
        applied_groups = set()  # 적용된 배타적 그룹

        for rule in self.rules:
            # 배타적 그룹 체크
            if rule.exclusive_group and rule.exclusive_group in applied_groups:
                continue

            if rule.evaluate(indicators):
                total_score += rule.score
                signals.append(rule.signal)

                if rule.exclusive_group:
                    applied_groups.add(rule.exclusive_group)

        # 점수 클리핑
        total_score = max(self.min_score, min(self.max_score, total_score))

        return total_score, signals


@dataclass
class ScoringConfig:
    """스코어링 설정"""
    version: str
    name: str
    description: str = ""
    min_data_days: int = 60
    max_score: int = 100
    disqualifiers: List[DisqualifierRule] = field(default_factory=list)
    scoring_groups: Dict[str, ScoringGroup] = field(default_factory=dict)
    signal_names_kr: Dict[str, str] = field(default_factory=dict)

    def check_disqualifiers(self, indicators: Dict[str, Any]) -> Optional[str]:
        """과락 조건 검사

        Returns:
            과락 사유 (None이면 통과)
        """
        for rule in self.disqualifiers:
            if rule.evaluate(indicators):
                return rule.name
        return None

    def calculate_all_scores(self, indicators: Dict[str, Any]) -> Dict:
        """전체 스코어 계산

        Returns:
            {'score': 총점, 'groups': {그룹명: 점수}, 'signals': [신호들]}
        """
        # 과락 체크
        disqualify_reason = self.check_disqualifiers(indicators)
        if disqualify_reason:
            disq_signal = None
            for rule in self.disqualifiers:
                if rule.name == disqualify_reason:
                    disq_signal = rule.signal
                    break
            return {
                'score': 0,
                'groups': {},
                'signals': [disq_signal] if disq_signal else [],
                'disqualified': True,
                'disqualify_reason': disqualify_reason,
            }

        # 그룹별 점수 계산
        groups = {}
        all_signals = []
        total_score = 0

        for group_name, group in self.scoring_groups.items():
            group_score, group_signals = group.calculate_score(indicators)
            groups[f"{group_name}_score"] = group_score
            all_signals.extend(group_signals)
            total_score += group_score

        # 총점 클리핑
        total_score = max(0, min(self.max_score, total_score))

        return {
            'score': total_score,
            'groups': groups,
            'signals': all_signals,
            'disqualified': False,
        }

    def get_signal_kr(self, signal: str) -> str:
        """신호 한글명 반환"""
        return self.signal_names_kr.get(signal, signal)


def _evaluate_condition(condition: str, indicators: Dict[str, Any]) -> bool:
    """조건 문자열 평가

    지원 형식:
    - "SMA_5 > SMA_20"
    - "RSI >= 60 AND RSI <= 75"
    - "60 <= RSI <= 75"
    - "TRADING_VALUE >= 50000000000"
    """
    # 특수 패턴: "A < B < C" 형식
    triple_match = re.match(r'^(\w+)\s*(<|<=)\s*(\w+)\s*(<|<=)\s*(\w+)$', condition)
    if triple_match:
        left, op1, mid, op2, right = triple_match.groups()
        left_val = _get_value(left, indicators)
        mid_val = _get_value(mid, indicators)
        right_val = _get_value(right, indicators)
        return _compare(left_val, op1, mid_val) and _compare(mid_val, op2, right_val)

    # 특수 패턴: "60 <= RSI <= 75" 형식
    range_match = re.match(r'^(\d+(?:\.\d+)?)\s*(<=?)\s*(\w+)\s*(<=?)\s*(\d+(?:\.\d+)?)$', condition)
    if range_match:
        low, op1, var, op2, high = range_match.groups()
        val = _get_value(var, indicators)
        low_val = float(low)
        high_val = float(high)
        return _compare(low_val, op1, val) and _compare(val, op2, high_val)

    # AND/OR 분리
    if ' AND ' in condition:
        parts = condition.split(' AND ')
        return all(_evaluate_condition(p.strip(), indicators) for p in parts)

    if ' OR ' in condition:
        parts = condition.split(' OR ')
        return any(_evaluate_condition(p.strip(), indicators) for p in parts)

    # 단일 비교: "A >= B" 또는 "A >= 123"
    compare_match = re.match(r'^(\w+)\s*(>=|<=|>|<|==|!=)\s*(.+)$', condition)
    if compare_match:
        left, op, right = compare_match.groups()
        left_val = _get_value(left, indicators)
        right_val = _get_value(right.strip(), indicators)
        return _compare(left_val, op, right_val)

    return False


def _get_value(expr: str, indicators: Dict[str, Any]) -> Any:
    """표현식에서 값 추출"""
    expr = expr.strip()

    # 숫자
    if re.match(r'^-?\d+(?:\.\d+)?$', expr):
        return float(expr)

    # _prev 접미사 (이전 값)
    if expr.endswith('_prev'):
        base = expr[:-5]
        # 이전 값이 있으면 사용, 없으면 현재값 사용
        if f"{base}_prev" in indicators:
            return indicators.get(f"{base}_prev", 0)
        return indicators.get(base, 0)

    # 일반 변수
    return indicators.get(expr, 0)


def _compare(left: Any, op: str, right: Any) -> bool:
    """비교 연산"""
    if left is None or right is None:
        return False

    try:
        left = float(left) if not isinstance(left, (int, float)) else left
        right = float(right) if not isinstance(right, (int, float)) else right
    except (ValueError, TypeError):
        return False

    if op in ('>', '>'):
        return left > right
    elif op in ('<', '<'):
        return left < right
    elif op == '>=':
        return left >= right
    elif op == '<=':
        return left <= right
    elif op == '==':
        return left == right
    elif op == '!=':
        return left != right
    return False


def load_scoring_config(version: str) -> Optional[ScoringConfig]:
    """YAML 설정 파일 로드

    Args:
        version: 버전 (예: 'v2', 'v4')

    Returns:
        ScoringConfig 객체
    """
    config_path = CONFIG_DIR / f"{version}_config.yaml"

    if not config_path.exists():
        print(f"설정 파일 없음: {config_path}")
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # 과락 규칙 파싱
        disqualifiers = []
        for d in data.get('disqualifiers', []):
            disqualifiers.append(DisqualifierRule(
                name=d['name'],
                condition=d['condition'],
                signal=d.get('signal', '')
            ))

        # 스코어링 그룹 파싱
        scoring_groups = {}
        for group_name, group_data in data.get('scoring_groups', {}).items():
            rules = []
            for r in group_data.get('rules', []):
                rules.append(ScoringRule(
                    name=r['name'],
                    condition=r['condition'],
                    score=r['score'],
                    signal=r.get('signal', ''),
                    exclusive_group=r.get('exclusive_group')
                ))

            scoring_groups[group_name] = ScoringGroup(
                name=group_name,
                max_score=group_data.get('max_score', 100),
                min_score=group_data.get('min_score', 0),
                rules=rules
            )

        return ScoringConfig(
            version=data.get('version', version),
            name=data.get('name', ''),
            description=data.get('description', ''),
            min_data_days=data.get('min_data_days', 60),
            max_score=data.get('max_score', 100),
            disqualifiers=disqualifiers,
            scoring_groups=scoring_groups,
            signal_names_kr=data.get('signal_names_kr', {})
        )

    except Exception as e:
        print(f"설정 로드 오류: {e}")
        return None


# 캐시된 설정
_config_cache: Dict[str, ScoringConfig] = {}


def get_config(version: str) -> Optional[ScoringConfig]:
    """설정 가져오기 (캐시 사용)"""
    if version not in _config_cache:
        config = load_scoring_config(version)
        if config:
            _config_cache[version] = config
    return _config_cache.get(version)


def clear_config_cache() -> None:
    """설정 캐시 초기화"""
    _config_cache.clear()


def list_available_configs() -> List[str]:
    """사용 가능한 설정 버전 목록"""
    versions = []
    for f in CONFIG_DIR.glob('*_config.yaml'):
        version = f.stem.replace('_config', '')
        versions.append(version)
    return sorted(versions)
