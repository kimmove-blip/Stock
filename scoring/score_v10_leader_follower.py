"""
V10 스코어링 엔진 - Leader-Follower (대장주-종속주 전략)

핵심 컨셉:
- 같은 테마/섹터 내에서 대장주와 종속주는 높은 상관관계를 보임
- 대장주가 먼저 움직이면 종속주가 시차를 두고 따라가는 경향
- 이 시간차(Time Lag)를 이용해 대장주 상승 시 종속주 매수

레퍼런스 기반:
- 머신러닝으로 학습된 상관관계 레퍼런스 사용
- models/v10_leader_follower_reference.pkl 파일 로드
- 실제 측정된 상관계수 기반 점수 계산

점수 체계 (100점 만점):
- 대장주 움직임 (35점): 대장주 상승률, 거래량 동반
- 상관관계 (25점): 실측 피어슨 상관계수 0.5~0.9+
- 캐치업 갭 (25점): 대장주 대비 언더퍼폼 정도
- 기술적 지지 (15점): MA, RSI, 볼린저밴드 지지

청산 전략:
- 목표가: 대장주 상승률의 70~80% 수준 캐치업
- 손절가: -3% (빠른 손절)
- 시간 손절: 최대 3일 (모멘텀 소멸)
"""

import os
import json
import pickle
import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta


# ============================================================
# 레퍼런스 로드
# ============================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE_PKL = os.path.join(PROJECT_ROOT, "models", "v10_leader_follower_reference.pkl")
REFERENCE_JSON = os.path.join(PROJECT_ROOT, "models", "v10_leader_follower_reference.json")

# 글로벌 레퍼런스 캐시
_REFERENCE_CACHE = None


def load_reference() -> Optional[dict]:
    """레퍼런스 로드 (캐시 사용)"""
    global _REFERENCE_CACHE

    if _REFERENCE_CACHE is not None:
        return _REFERENCE_CACHE

    # Pickle 우선 로드
    if os.path.exists(REFERENCE_PKL):
        try:
            with open(REFERENCE_PKL, 'rb') as f:
                _REFERENCE_CACHE = pickle.load(f)
            return _REFERENCE_CACHE
        except Exception as e:
            print(f"[V10] Pickle 로드 실패: {e}")

    # JSON 대안
    if os.path.exists(REFERENCE_JSON):
        try:
            with open(REFERENCE_JSON, 'r', encoding='utf-8') as f:
                _REFERENCE_CACHE = json.load(f)
            return _REFERENCE_CACHE
        except Exception as e:
            print(f"[V10] JSON 로드 실패: {e}")

    print("[V10] 레퍼런스 파일이 없습니다. train_leader_follower.py를 먼저 실행하세요.")
    return None


def get_leaders_for_follower(follower_code: str) -> List[dict]:
    """종속주의 대장주 목록 조회"""
    ref = load_reference()
    if ref is None:
        return []

    return ref.get('follower_to_leaders', {}).get(follower_code, [])


def get_followers_for_leader(leader_code: str) -> List[dict]:
    """대장주의 종속주 목록 조회"""
    ref = load_reference()
    if ref is None:
        return []

    return ref.get('leader_to_followers', {}).get(leader_code, [])


def get_correlation(leader_code: str, follower_code: str) -> float:
    """대장주-종속주 상관계수 조회"""
    ref = load_reference()
    if ref is None:
        return 0.0

    # follower_to_leaders에서 검색
    leaders = ref.get('follower_to_leaders', {}).get(follower_code, [])
    for leader in leaders:
        if leader['leader_code'] == leader_code:
            return leader['correlation']

    return 0.0


def get_all_leaders() -> List[str]:
    """모든 대장주 코드 목록"""
    ref = load_reference()
    if ref is None:
        return []

    return list(ref.get('leader_to_followers', {}).keys())


def get_all_followers() -> List[str]:
    """모든 종속주 코드 목록"""
    ref = load_reference()
    if ref is None:
        return []

    return list(ref.get('follower_to_leaders', {}).keys())


# ============================================================
# 기술적 지표 계산
# ============================================================
def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()

    # 이동평균
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))

    # 볼린저밴드
    df['BB_mid'] = df['Close'].rolling(20).mean()
    df['BB_std'] = df['Close'].rolling(20).std()
    df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
    df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']
    df['BB_pct'] = (df['Close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'] + 1e-10)

    return df


# ============================================================
# V10 점수 계산
# ============================================================
def calculate_score_v10(
    df: pd.DataFrame,
    ticker: str = None,
    today_changes: Optional[Dict[str, float]] = None,
) -> Optional[Dict]:
    """
    V10 점수 계산 - Leader-Follower (대장주-종속주)

    Args:
        df: 해당 종목의 OHLCV 데이터프레임 (최소 60일 권장)
        ticker: 종목코드
        today_changes: 금일 종목별 등락률 {ticker: change_pct}

    Returns:
        점수 및 분석 결과 딕셔너리
    """
    if df is None or len(df) < 60:
        return None

    ref = load_reference()
    if ref is None:
        return None

    try:
        df = df.copy()
        df = _calculate_indicators(df)

        score = 50  # 기본 점수
        signals = []
        details = {}

        # 이 종목이 종속주인지 확인
        leaders = get_leaders_for_follower(ticker) if ticker else []

        if not leaders:
            # 대장주이거나 매핑이 없는 종목
            details['role'] = 'leader_or_unknown'
            details['message'] = '대장주이거나 매핑된 종속주가 아님'
            return {
                'score': score,
                'signals': signals,
                'details': details
            }

        details['role'] = 'follower'
        details['leaders'] = leaders

        # 대장주 움직임 확인
        if today_changes:
            best_leader = None
            best_gap = 0

            for leader_info in leaders:
                leader_code = leader_info['leader_code']
                leader_change = today_changes.get(leader_code, 0)
                follower_change = today_changes.get(ticker, 0)
                correlation = leader_info['correlation']

                gap = leader_change - follower_change

                if leader_change >= 2.0 and gap > best_gap:
                    best_leader = {
                        'code': leader_code,
                        'name': leader_info['leader_name'],
                        'change': leader_change,
                        'correlation': correlation,
                        'gap': gap
                    }
                    best_gap = gap

            if best_leader:
                details['active_leader'] = best_leader

                # 1. 대장주 움직임 점수 (35점)
                leader_change = best_leader['change']
                if leader_change >= 5:
                    score += 35
                    signals.append(f"대장주 +{leader_change:.1f}% 급등")
                elif leader_change >= 4:
                    score += 28
                    signals.append(f"대장주 +{leader_change:.1f}% 강세")
                elif leader_change >= 3:
                    score += 20
                    signals.append(f"대장주 +{leader_change:.1f}% 상승")
                elif leader_change >= 2:
                    score += 12
                    signals.append(f"대장주 +{leader_change:.1f}% 상승")

                # 2. 상관계수 점수 (25점) - 실측값 사용
                corr = best_leader['correlation']
                if corr >= 0.8:
                    score += 25
                    signals.append(f"상관계수 {corr:.2f} (매우 높음)")
                elif corr >= 0.7:
                    score += 20
                    signals.append(f"상관계수 {corr:.2f} (높음)")
                elif corr >= 0.6:
                    score += 15
                    signals.append(f"상관계수 {corr:.2f} (양호)")
                elif corr >= 0.5:
                    score += 10
                    signals.append(f"상관계수 {corr:.2f} (보통)")

                # 3. 캐치업 갭 점수 (25점)
                gap = best_leader['gap']
                if gap >= 5:
                    score += 25
                    signals.append(f"캐치업 갭 +{gap:.1f}%")
                elif gap >= 4:
                    score += 20
                    signals.append(f"캐치업 갭 +{gap:.1f}%")
                elif gap >= 3:
                    score += 15
                    signals.append(f"캐치업 갭 +{gap:.1f}%")
                elif gap >= 2:
                    score += 10
                    signals.append(f"캐치업 갭 +{gap:.1f}%")

        # 4. 기술적 지지 점수 (15점)
        latest = df.iloc[-1]

        # RSI 지지
        rsi = latest.get('RSI', 50)
        if 30 <= rsi <= 50:
            score += 5
            signals.append("RSI 지지대")

        # 볼린저밴드 하단 근처
        bb_pct = latest.get('BB_pct', 0.5)
        if bb_pct <= 0.3:
            score += 5
            signals.append("BB 하단 지지")

        # 이평선 지지
        close = latest['Close']
        ma20 = latest.get('MA20', close)
        if close >= ma20 * 0.97 and close <= ma20 * 1.03:
            score += 5
            signals.append("MA20 지지")

        # 점수 범위 제한
        score = max(0, min(100, score))

        return {
            'score': score,
            'signals': signals,
            'details': details
        }

    except Exception as e:
        return None


def calculate_score_v10_with_market_data(
    df: pd.DataFrame,
    ticker: str = None,
    market_data: Optional[Dict[str, pd.DataFrame]] = None,
    today_changes: Optional[Dict[str, float]] = None,
) -> Optional[Dict]:
    """시장 데이터 포함 V10 점수 계산 (호환성)"""
    return calculate_score_v10(df, ticker, today_changes)


# ============================================================
# 캐치업 기회 탐색
# ============================================================
def get_follower_opportunities(
    today_changes: Dict[str, float],
    min_leader_change: float = 3.0,
    max_follower_change: float = 2.0,
) -> List[Dict]:
    """
    캐치업 기회 있는 종속주 탐색

    Args:
        today_changes: 금일 종목별 등락률 {ticker: change_pct}
        min_leader_change: 대장주 최소 상승률 (기본 3%)
        max_follower_change: 종속주 최대 상승률 (기본 2%)

    Returns:
        캐치업 기회 목록 (점수 높은 순)
    """
    ref = load_reference()
    if ref is None:
        return []

    opportunities = []

    # 모든 대장주 확인
    for leader_code, followers in ref.get('leader_to_followers', {}).items():
        leader_change = today_changes.get(leader_code, 0)

        if leader_change < min_leader_change:
            continue

        # 대장주 이름 찾기
        leader_name = leader_code
        for pair in ref.get('all_pairs', []):
            if pair['leader_code'] == leader_code:
                leader_name = pair['leader_name']
                break

        # 종속주 확인
        for follower in followers:
            follower_code = follower['code']
            follower_change = today_changes.get(follower_code, 0)

            if follower_change > max_follower_change:
                continue

            gap = leader_change - follower_change
            correlation = follower['correlation']

            # V10 점수 계산 (상관계수 기반 차등)
            score = 40  # 기본 점수

            # 1. 대장주 움직임 (최대 20점)
            if leader_change >= 10:
                score += 20
            elif leader_change >= 7:
                score += 16
            elif leader_change >= 5:
                score += 12
            elif leader_change >= 3:
                score += 8

            # 2. 실측 상관계수 (최대 25점) - 핵심 요소
            if correlation >= 0.8:
                score += 25
            elif correlation >= 0.7:
                score += 20
            elif correlation >= 0.6:
                score += 14
            elif correlation >= 0.5:
                score += 8

            # 3. 캐치업 갭 (최대 15점)
            if gap >= 8:
                score += 15
            elif gap >= 6:
                score += 12
            elif gap >= 4:
                score += 8
            elif gap >= 2:
                score += 4

            score = min(100, score)

            opportunities.append({
                'follower_code': follower_code,
                'follower_name': follower['name'],
                'follower_change': follower_change,
                'leader_code': leader_code,
                'leader_name': leader_name,
                'leader_change': leader_change,
                'correlation': correlation,
                'catchup_gap': gap,
                'score': int(score)
            })

    # 점수 높은 순 정렬
    opportunities.sort(key=lambda x: (-x['score'], -x['catchup_gap']))

    return opportunities


def get_reference_info() -> dict:
    """레퍼런스 정보 조회"""
    ref = load_reference()
    if ref is None:
        return {'loaded': False, 'error': '레퍼런스 파일 없음'}

    return {
        'loaded': True,
        'version': ref.get('version', 'unknown'),
        'created_at': ref.get('created_at', 'unknown'),
        'min_correlation': ref.get('min_correlation', 0),
        'total_leaders': ref.get('total_leaders', 0),
        'total_followers': ref.get('total_followers', 0),
        'total_pairs': ref.get('total_pairs', 0)
    }
