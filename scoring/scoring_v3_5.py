"""
V3.5 점수 계산 로직 - 사일런트 바이어 발전형 (Silent Buyer Enhanced)

V3 대비 개선사항:
1. 공시 확증: 5% 대량보유 공시, CB/BW 오버행 체크
2. 와이코프 Phase: A~C 국면 자동 감지
3. 위치 필터: 바닥권 vs 고점권 구분, 분산 패턴 감지
4. 숏커버링 필터: 대차잔고 감소 + 상승 = 숏커버링 경고
5. 매물대 분석: 가격대별 누적 거래량으로 저항/지지 측정

점수 체계 (100점 만점):
┌────────────────────────────────┬───────┬───────────┐
│ 그룹                            │ 배점  │ 신규/개선  │
├────────────────────────────────┼───────┼───────────┤
│ 1. 공시 확증                    │ 15점  │ 신규      │
│ 2. 와이코프 Phase               │ 20점  │ 신규      │
│ 3. 매집 패턴 (위치 필터 적용)    │ 25점  │ 개선      │
│ 4. 수급 분석 (숏커버링 필터)     │ 20점  │ 신규      │
│ 5. 거래량/매물대                │ 15점  │ 개선      │
│ 6. 추세/모멘텀                  │ 5점   │ 축소      │
└────────────────────────────────┴───────┴───────────┘

과락 조건:
- 역배열: 전체 0점
- 고점권 (60일 고가 95%+): 매집 패턴 점수 0점
- 숏커버링 의심: 수급 점수 0점
- CB/BW 오버행: 최대 50점 제한
- 외국인+기관 10일 연속 순매도: 수급 0점

조합 보너스:
- 5% 공시 + Phase C + 기관 순매수: +15점 (확증된 매집)
- Phase C + OBV 다이버전스 + 매물대 클리어: +10점
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta


# ============================================================
# Phase 1: 위치 필터 + 분산 패턴 감지
# ============================================================

def classify_price_location(df: pd.DataFrame) -> Dict:
    """
    현재 가격 위치 분류 (바닥권 vs 고점권)

    바닥권 조건 (매집 신호 유효):
    - 60일 저가 대비 10% 이내
    - 볼린저밴드 하단 근처
    - 와이코프 Phase A~C

    고점권 조건 (매집 신호 무효화):
    - 60일 고가 대비 5% 이내
    - 볼린저밴드 상단 돌파
    - 상승률 50%+ (최근 20일)

    Returns:
        {
            'location': 'bottom' | 'middle' | 'top',
            'is_bottom_zone': bool,  # 바닥권 여부 (매집 신호 유효)
            'is_top_zone': bool,     # 고점권 여부 (매집 신호 무효)
            'pct_from_high_60d': float,  # 60일 고점 대비 %
            'pct_from_low_60d': float,   # 60일 저점 대비 %
            'recent_gain_20d': float,    # 최근 20일 상승률
            'bb_position': str,  # 'above_upper' | 'upper_band' | 'middle' | 'lower_band' | 'below_lower'
        }
    """
    result = {
        'location': 'middle',
        'is_bottom_zone': False,
        'is_top_zone': False,
        'pct_from_high_60d': 0,
        'pct_from_low_60d': 0,
        'recent_gain_20d': 0,
        'bb_position': 'middle',
    }

    try:
        if len(df) < 60:
            return result

        curr_close = df.iloc[-1]['Close']

        # 60일 고가/저가
        high_60d = df['High'].tail(60).max()
        low_60d = df['Low'].tail(60).min()

        result['pct_from_high_60d'] = (curr_close / high_60d - 1) * 100
        result['pct_from_low_60d'] = (curr_close / low_60d - 1) * 100

        # 최근 20일 상승률
        if len(df) >= 20:
            close_20d_ago = df.iloc[-20]['Close']
            if close_20d_ago > 0:
                result['recent_gain_20d'] = (curr_close / close_20d_ago - 1) * 100

        # 볼린저밴드 위치
        bbands = ta.bbands(df['Close'], length=20, std=2)
        if bbands is not None and not bbands.empty:
            bb_upper = bbands.iloc[-1].get('BBU_20_2.0')
            bb_lower = bbands.iloc[-1].get('BBL_20_2.0')
            bb_mid = bbands.iloc[-1].get('BBM_20_2.0')

            if pd.notna(bb_upper) and pd.notna(bb_lower):
                if curr_close > bb_upper:
                    result['bb_position'] = 'above_upper'
                elif curr_close > bb_mid + (bb_upper - bb_mid) * 0.5:
                    result['bb_position'] = 'upper_band'
                elif curr_close < bb_lower:
                    result['bb_position'] = 'below_lower'
                elif curr_close < bb_mid - (bb_mid - bb_lower) * 0.5:
                    result['bb_position'] = 'lower_band'
                else:
                    result['bb_position'] = 'middle'

        # 위치 판정
        # 고점권: 60일 고가의 95% 이상 OR 20일간 50% 이상 상승 OR 볼린저밴드 상단 돌파
        is_near_high = result['pct_from_high_60d'] >= -5
        is_rapid_gain = result['recent_gain_20d'] >= 50
        is_bb_overbought = result['bb_position'] in ['above_upper', 'upper_band']

        if is_near_high or is_rapid_gain or (is_near_high and is_bb_overbought):
            result['location'] = 'top'
            result['is_top_zone'] = True

        # 바닥권: 60일 저가의 110% 이내 AND 볼린저밴드 하단 근처
        is_near_low = result['pct_from_low_60d'] <= 10
        is_bb_oversold = result['bb_position'] in ['below_lower', 'lower_band']

        if is_near_low or (is_near_low and is_bb_oversold):
            result['location'] = 'bottom'
            result['is_bottom_zone'] = True

            # 동시에 고점권이면 고점권 우선 (급등 후 급락 시)
            if result['is_top_zone']:
                result['is_bottom_zone'] = False

    except Exception as e:
        pass

    return result


def detect_distribution_pattern(df: pd.DataFrame) -> Dict:
    """
    분산(Distribution) 패턴 감지 - 고점권 피뢰침 음봉

    분산 경고:
    - 고점권 + 윗꼬리 + 거래량 급증 = 분산 패턴 (피뢰침 음봉)
    - 고점권 + VCP = 분산 (매집 아님)

    Returns:
        {
            'detected': bool,
            'pattern_type': 'lightning_rod' | 'high_volume_rejection' | 'vcp_at_top' | None,
            'severity': 'high' | 'medium' | 'low' | None,
        }
    """
    result = {
        'detected': False,
        'pattern_type': None,
        'severity': None,
    }

    try:
        if len(df) < 20:
            return result

        curr = df.iloc[-1]
        vol_ma = df['Volume'].tail(20).mean()

        # 캔들 구조 분석
        body = curr['Close'] - curr['Open']
        upper_shadow = curr['High'] - max(curr['Close'], curr['Open'])
        lower_shadow = min(curr['Close'], curr['Open']) - curr['Low']
        total_range = curr['High'] - curr['Low']

        if total_range == 0:
            return result

        upper_wick_ratio = upper_shadow / total_range
        vol_ratio = curr['Volume'] / vol_ma if vol_ma > 0 else 0

        # 위치 확인
        location = classify_price_location(df)

        # 피뢰침 음봉 (Lightning Rod): 고점권 + 긴 윗꼬리 + 음봉 + 거래량 급증
        is_bearish = body < 0
        is_long_upper_wick = upper_wick_ratio >= 0.5
        is_high_volume = vol_ratio >= 2.0

        if location['is_top_zone']:
            if is_bearish and is_long_upper_wick and is_high_volume:
                result['detected'] = True
                result['pattern_type'] = 'lightning_rod'
                result['severity'] = 'high'

            elif is_long_upper_wick and is_high_volume:
                # 고거래량 rejection (양봉이라도)
                result['detected'] = True
                result['pattern_type'] = 'high_volume_rejection'
                result['severity'] = 'medium'

    except Exception as e:
        pass

    return result


# ============================================================
# Phase 2: 와이코프 Phase 판단
# ============================================================

def detect_wyckoff_phase(df: pd.DataFrame) -> Dict:
    """
    와이코프 매집 국면(Accumulation Phase) 판단

    Phase A (하락 정지) 확인:
    - PS (Preliminary Support): 대량 거래 + 하락 둔화
    - SC (Selling Climax): 급락 + 거래량 폭발
    - AR (Automatic Rally): 반등
    - ST (Secondary Test): SC 저점 재테스트

    Phase B (매집) 확인:
    - 박스권 형성 (TR: Trading Range)
    - 거래량 점진적 감소

    Phase C (테스트) 확인:
    - Spring: 지지선 이탈 후 급반등 ← 기존 V3
    - LPS (Last Point of Support)

    점수:
    - Phase C 진입 (Spring 발생): +20점 (매집 완료 임박)
    - Phase B 진행 중: +10점 (매집 진행)
    - Phase A 확인됨: +5점 (하락 정지)
    - Phase 미확인: 0점

    Returns:
        {
            'phase': 'A' | 'B' | 'C' | 'D' | 'E' | None,
            'phase_score': 0-20,
            'events': ['SC', 'AR', 'ST', 'SPRING', ...],
            'trading_range': {
                'support': float,
                'resistance': float,
                'range_pct': float
            },
            'confidence': 0-100,
        }
    """
    result = {
        'phase': None,
        'phase_score': 0,
        'events': [],
        'trading_range': {
            'support': 0,
            'resistance': 0,
            'range_pct': 0
        },
        'confidence': 0,
    }

    try:
        if len(df) < 60:
            return result

        # 최근 60일 분석
        recent = df.tail(60)
        vol_ma = recent['Volume'].mean()
        curr_close = df.iloc[-1]['Close']

        # Trading Range 식별 (박스권)
        high_60d = recent['High'].max()
        low_60d = recent['Low'].min()
        range_pct = (high_60d - low_60d) / low_60d * 100

        result['trading_range'] = {
            'support': low_60d,
            'resistance': high_60d,
            'range_pct': range_pct
        }

        # Phase A 이벤트 감지

        # SC (Selling Climax): 급락 + 거래량 폭발
        sc_detected = False
        sc_idx = None
        for i in range(10, len(recent) - 5):
            # 5일간 10% 이상 하락
            if (recent.iloc[i]['Close'] / recent.iloc[i-5]['Close'] - 1) * 100 < -10:
                # 거래량이 평균의 2배 이상
                if recent.iloc[i]['Volume'] > vol_ma * 2:
                    sc_detected = True
                    sc_idx = i
                    result['events'].append('SC')
                    break

        # AR (Automatic Rally): SC 후 반등
        ar_detected = False
        if sc_detected and sc_idx is not None:
            for i in range(sc_idx + 1, min(sc_idx + 10, len(recent))):
                # SC 저점 대비 5% 이상 반등
                if (recent.iloc[i]['Close'] / recent.iloc[sc_idx]['Low'] - 1) * 100 > 5:
                    ar_detected = True
                    result['events'].append('AR')
                    break

        # ST (Secondary Test): SC 저점 재테스트
        st_detected = False
        if sc_detected and ar_detected and sc_idx is not None:
            sc_low = recent.iloc[sc_idx]['Low']
            for i in range(sc_idx + 5, len(recent)):
                # SC 저점 근처 (±3%)까지 다시 내려옴
                if abs(recent.iloc[i]['Low'] / sc_low - 1) * 100 < 3:
                    # 거래량은 SC 때보다 적음
                    if recent.iloc[i]['Volume'] < recent.iloc[sc_idx]['Volume'] * 0.7:
                        st_detected = True
                        result['events'].append('ST')
                        break

        # Phase B 이벤트 감지

        # 박스권 거래 (변동성 축소)
        first_half_range = recent.iloc[:30]['High'].max() - recent.iloc[:30]['Low'].min()
        second_half_range = recent.iloc[30:]['High'].max() - recent.iloc[30:]['Low'].min()
        range_contraction = second_half_range < first_half_range * 0.7

        # 거래량 감소
        first_half_vol = recent.iloc[:30]['Volume'].mean()
        second_half_vol = recent.iloc[30:]['Volume'].mean()
        vol_contraction = second_half_vol < first_half_vol * 0.8

        if range_contraction:
            result['events'].append('TR_CONTRACTION')
        if vol_contraction:
            result['events'].append('VOL_DRYUP')

        # Phase C 이벤트 감지

        # Spring: 지지선 이탈 후 회복 (기존 V3 로직 활용)
        spring_detected = False
        support = recent['Low'].quantile(0.1)  # 하위 10%

        for i in range(len(recent) - 10, len(recent)):
            # 지지선 이탈
            if recent.iloc[i]['Low'] < support:
                # 이후 회복
                if curr_close > support:
                    spring_detected = True
                    result['events'].append('SPRING')
                    break

        # LPS (Last Point of Support): Spring 후 재테스트 시 지지 확인
        lps_detected = False
        if spring_detected:
            for i in range(len(recent) - 5, len(recent)):
                if abs(recent.iloc[i]['Low'] / support - 1) * 100 < 2:
                    if recent.iloc[i]['Close'] > support:
                        lps_detected = True
                        result['events'].append('LPS')
                        break

        # Phase 판정
        if spring_detected or lps_detected:
            result['phase'] = 'C'
            result['phase_score'] = 20
            result['confidence'] = 80 if lps_detected else 60

        elif st_detected and (range_contraction or vol_contraction):
            result['phase'] = 'B'
            result['phase_score'] = 10
            result['confidence'] = 50

        elif sc_detected and ar_detected:
            result['phase'] = 'A'
            result['phase_score'] = 5
            result['confidence'] = 30

        # SOS (Sign of Strength) 감지 - Phase D 진입 신호
        if result['phase'] == 'C':
            # 저항선 돌파 + 거래량 급증
            if curr_close > high_60d * 0.95 and df.iloc[-1]['Volume'] > vol_ma * 1.5:
                result['events'].append('SOS')
                result['phase'] = 'D'
                result['confidence'] = min(100, result['confidence'] + 20)

    except Exception as e:
        pass

    return result


# ============================================================
# Phase 3: 수급 분석 (숏커버링 필터)
# ============================================================

def detect_short_covering_risk(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None,
    short_data: Optional[Dict] = None
) -> Dict:
    """
    숏커버링 vs 진성 매집 구분

    위험 신호:
    - 대차잔고 급감 (10일 내 20%+) + 주가 상승 = 숏커버링 경고
    - 공매도 비중 5%+ 에서 급감 = 숏스퀴즈 가능성

    구분 방법:
    - 대차잔고 감소 + OBV 상승 + 기관 순매수 = 진성 매집
    - 대차잔고 감소 + OBV 하락 + 기관 순매도 = 숏커버링 (제외)

    Args:
        df: OHLCV 데이터프레임
        investor_data: 투자자 동향 데이터 (naver_investor.py에서 조회)
        short_data: 공매도/대차잔고 데이터 (krx_short_data.py에서 조회)

    Returns:
        {
            'is_short_covering': bool,
            'risk_level': 'high' | 'medium' | 'low' | 'none',
            'reason': str,
            'genuine_accumulation': bool,  # 진성 매집 여부
        }
    """
    result = {
        'is_short_covering': False,
        'risk_level': 'none',
        'reason': '',
        'genuine_accumulation': False,
    }

    try:
        if len(df) < 20:
            return result

        # OBV 추세 분석
        obv = ta.obv(df['Close'], df['Volume'])
        if obv is not None:
            obv_recent = obv.tail(10)
            obv_trend_up = obv_recent.iloc[-1] > obv_recent.iloc[0]
        else:
            obv_trend_up = None

        # 가격 추세 분석
        price_change_10d = (df.iloc[-1]['Close'] / df.iloc[-10]['Close'] - 1) * 100 if len(df) >= 10 else 0
        price_up = price_change_10d > 5

        # 투자자 동향 분석
        institution_buying = False
        institution_selling = False
        if investor_data:
            inst_net = investor_data.get('institution_net', 0)
            institution_buying = inst_net > 0
            institution_selling = inst_net < -100000  # 10만주 이상 순매도

        # 숏커버링 판정 로직

        # 1. 공매도 데이터가 있는 경우
        if short_data:
            short_balance_change = short_data.get('balance_change_pct', 0)
            short_ratio = short_data.get('short_ratio', 0)

            # 대차잔고 20% 이상 급감 + 주가 상승 = 숏커버링 의심
            if short_balance_change < -20 and price_up:
                if institution_selling or obv_trend_up is False:
                    result['is_short_covering'] = True
                    result['risk_level'] = 'high'
                    result['reason'] = '대차잔고 급감 + 주가상승 + 기관순매도/OBV하락 → 숏커버링'
                elif institution_buying and obv_trend_up:
                    result['genuine_accumulation'] = True
                    result['reason'] = '대차잔고 감소 + 기관순매수 + OBV상승 → 진성 매집'
                else:
                    result['risk_level'] = 'medium'
                    result['reason'] = '대차잔고 급감 + 주가상승 → 숏커버링 가능성'

            # 공매도 비중 5% 이상에서 급감 = 숏스퀴즈
            if short_ratio > 5 and short_balance_change < -30:
                result['risk_level'] = 'high'
                result['reason'] = f'공매도 비중 {short_ratio}%에서 숏스퀴즈 가능성'

        # 2. 공매도 데이터 없이 패턴으로 추정
        else:
            # 급등 + 기관 순매도 + OBV 하락 = 의심
            if price_up and institution_selling and obv_trend_up is False:
                result['is_short_covering'] = True
                result['risk_level'] = 'medium'
                result['reason'] = '급등 + 기관순매도 + OBV하락 → 숏커버링 의심'

            # 급등 + 기관 순매수 + OBV 상승 = 진성 매집
            elif price_up and institution_buying and obv_trend_up:
                result['genuine_accumulation'] = True
                result['reason'] = '기관순매수 + OBV상승 → 진성 매집'

    except Exception as e:
        pass

    return result


def analyze_supply_demand(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None,
    short_data: Optional[Dict] = None
) -> Dict:
    """
    수급 종합 분석 (20점 만점)

    점수 체계:
    - 외국인 5일 연속 순매수: +6점
    - 기관 5일 연속 순매수: +6점
    - 외국인+기관 동시 순매수: +4점
    - OBV 상승 추세: +4점

    과락:
    - 숏커버링 의심: 수급 점수 0점
    - 외국인+기관 10일 연속 순매도: 수급 0점

    Returns:
        {
            'score': 0-20,
            'signals': [],
            'disqualified': bool,
            'disqualify_reason': str,
        }
    """
    result = {
        'score': 0,
        'signals': [],
        'disqualified': False,
        'disqualify_reason': '',
    }

    try:
        # 숏커버링 체크
        short_covering = detect_short_covering_risk(df, investor_data, short_data)
        if short_covering['is_short_covering'] and short_covering['risk_level'] == 'high':
            result['disqualified'] = True
            result['disqualify_reason'] = short_covering['reason']
            result['signals'].append('SHORT_COVERING_RISK')
            return result

        score = 0

        # 투자자 동향 분석
        if investor_data:
            foreign_cons = investor_data.get('consecutive_foreign_buy', 0)
            inst_cons = investor_data.get('consecutive_institution_buy', 0)
            foreign_net = investor_data.get('foreign_net', 0)
            inst_net = investor_data.get('institution_net', 0)

            # 외국인 연속 순매수
            if foreign_cons >= 5:
                score += 6
                result['signals'].append('FOREIGN_5DAY_BUY')
            elif foreign_cons >= 3:
                score += 3
                result['signals'].append('FOREIGN_3DAY_BUY')

            # 기관 연속 순매수
            if inst_cons >= 5:
                score += 6
                result['signals'].append('INST_5DAY_BUY')
            elif inst_cons >= 3:
                score += 3
                result['signals'].append('INST_3DAY_BUY')

            # 외국인+기관 동시 순매수
            if foreign_net > 0 and inst_net > 0:
                score += 4
                result['signals'].append('FOREIGN_INST_ALIGNED')

            # 10일 연속 순매도 과락
            daily_data = investor_data.get('daily', [])
            if len(daily_data) >= 10:
                consecutive_sell = 0
                for d in daily_data[:10]:
                    if d.get('foreign_net', 0) < 0 and d.get('institution_net', 0) < 0:
                        consecutive_sell += 1
                    else:
                        break

                if consecutive_sell >= 10:
                    result['disqualified'] = True
                    result['disqualify_reason'] = '외국인+기관 10일 연속 순매도'
                    result['signals'].append('10DAY_SELL_STREAK')
                    return result

        # OBV 추세
        if len(df) >= 20:
            obv = ta.obv(df['Close'], df['Volume'])
            if obv is not None:
                obv_ma = ta.sma(obv, length=20)
                if obv_ma is not None and pd.notna(obv_ma.iloc[-1]):
                    if obv.iloc[-1] > obv_ma.iloc[-1]:
                        score += 4
                        result['signals'].append('OBV_ABOVE_MA')

        result['score'] = min(20, score)

    except Exception as e:
        pass

    return result


# ============================================================
# Phase 4: 공시 데이터 연동
# ============================================================

def analyze_disclosure_signals(disclosure_data: Optional[Dict] = None) -> Dict:
    """
    공시 확증 분석 (15점 만점)

    신호:
    - 5% 신규 보유 공시 (경영참가 목적): +15점 (강한 확증)
    - 5% 신규 보유 공시 (단순투자 목적): +8점
    - 1%p 이상 지분 변동 공시: +5점
    - CB/BW 전환가액 대비 현재가 20% 이상: 주의 (오버행)

    과락:
    - CB 물량 출회 예정 (전환가액 < 현재가): 최대 50점 제한

    Args:
        disclosure_data: {
            'major_shareholders': [{
                'name': str,
                'ownership_pct': float,
                'change_pct': float,
                'purpose': 'management' | 'investment' | 'other',
                'report_date': str,
            }],
            'cb_bw': [{
                'type': 'CB' | 'BW',
                'conversion_price': float,
                'amount': float,
                'maturity_date': str,
            }],
            'current_price': float,
        }

    Returns:
        {
            'score': 0-15,
            'signals': [],
            'overhang_warning': bool,
            'overhang_ratio': float,  # 오버행 비율
            'max_score_limit': 100 | 50,  # CB 오버행 시 50점 제한
        }
    """
    result = {
        'score': 0,
        'signals': [],
        'overhang_warning': False,
        'overhang_ratio': 0,
        'max_score_limit': 100,
    }

    if not disclosure_data:
        return result

    try:
        score = 0
        current_price = disclosure_data.get('current_price', 0)

        # 5% 대량보유 공시 분석
        major_shareholders = disclosure_data.get('major_shareholders', [])
        for sh in major_shareholders:
            ownership = sh.get('ownership_pct', 0)
            change = sh.get('change_pct', 0)
            purpose = sh.get('purpose', '')

            # 5% 신규 보유
            if ownership >= 5 and change >= 5:
                if purpose == 'management':
                    score += 15
                    result['signals'].append('5PCT_NEW_MANAGEMENT')
                else:
                    score += 8
                    result['signals'].append('5PCT_NEW_INVESTMENT')

            # 1%p 이상 지분 증가
            elif change >= 1:
                score += 5
                result['signals'].append('1PCT_INCREASE')

        # CB/BW 오버행 분석
        cb_bw_list = disclosure_data.get('cb_bw', [])
        total_overhang = 0

        for cb in cb_bw_list:
            conversion_price = cb.get('conversion_price', 0)
            amount = cb.get('amount', 0)

            if conversion_price > 0 and current_price > 0:
                # 현재가가 전환가액보다 20% 이상 높으면 출회 가능성
                if current_price > conversion_price * 1.2:
                    total_overhang += amount
                    result['overhang_warning'] = True

        if result['overhang_warning']:
            result['signals'].append('CB_BW_OVERHANG')
            result['max_score_limit'] = 50
            result['overhang_ratio'] = total_overhang  # 오버행 물량

        result['score'] = min(15, score)

    except Exception as e:
        pass

    return result


# ============================================================
# Phase 5: 매물대 분석
# ============================================================

def analyze_volume_profile(df: pd.DataFrame, bins: int = 20) -> Dict:
    """
    가격대별 누적 거래량 분석 (Volume Profile)

    신호:
    - 현재가 위 두터운 매물대 없음: +10점 (저항 약함)
    - 현재가 아래 두터운 매물대 있음: +5점 (지지 강함)
    - 매물대 소화 중 (고거래량 돌파 시도): +8점

    경고:
    - 현재가 바로 위 매물대 존재 (5% 이내): 목표가 보수적 설정

    Args:
        df: OHLCV 데이터프레임 (최소 60일)
        bins: 가격 구간 수 (기본 20개)

    Returns:
        {
            'score': 0-15,
            'signals': [],
            'resistance_strength': 0-100,  # 상방 저항 강도
            'support_strength': 0-100,     # 하방 지지 강도
            'price_levels': [{
                'price_low': float,
                'price_high': float,
                'volume': int,
                'volume_pct': float,
            }],
            'nearest_resistance': float,  # 가장 가까운 저항선
            'nearest_support': float,     # 가장 가까운 지지선
        }
    """
    result = {
        'score': 0,
        'signals': [],
        'resistance_strength': 0,
        'support_strength': 0,
        'price_levels': [],
        'nearest_resistance': None,
        'nearest_support': None,
    }

    try:
        if len(df) < 60:
            return result

        recent = df.tail(60)
        curr_close = df.iloc[-1]['Close']

        # 가격 범위 분할
        price_min = recent['Low'].min()
        price_max = recent['High'].max()
        price_range = price_max - price_min

        if price_range == 0:
            return result

        bin_size = price_range / bins

        # 각 가격대별 거래량 누적
        volume_by_price = []
        total_volume = 0

        for i in range(bins):
            price_low = price_min + (i * bin_size)
            price_high = price_min + ((i + 1) * bin_size)

            # 해당 가격대에서 거래된 거래량
            mask = (recent['Low'] <= price_high) & (recent['High'] >= price_low)
            bin_volume = recent.loc[mask, 'Volume'].sum()

            volume_by_price.append({
                'price_low': price_low,
                'price_high': price_high,
                'volume': bin_volume,
                'mid_price': (price_low + price_high) / 2,
            })
            total_volume += bin_volume

        # 비율 계산
        for vp in volume_by_price:
            vp['volume_pct'] = (vp['volume'] / total_volume * 100) if total_volume > 0 else 0

        result['price_levels'] = volume_by_price

        # 현재가 기준 상방/하방 분석
        above_volume = 0
        below_volume = 0
        nearest_resistance = None
        nearest_support = None

        avg_volume_pct = 100 / bins  # 균등 분포 시 평균

        for vp in volume_by_price:
            if vp['mid_price'] > curr_close:
                above_volume += vp['volume']
                # 두터운 매물대 (평균의 2배 이상) = 저항선
                if vp['volume_pct'] > avg_volume_pct * 2:
                    if nearest_resistance is None or vp['mid_price'] < nearest_resistance:
                        nearest_resistance = vp['mid_price']
            else:
                below_volume += vp['volume']
                # 두터운 매물대 = 지지선
                if vp['volume_pct'] > avg_volume_pct * 2:
                    if nearest_support is None or vp['mid_price'] > nearest_support:
                        nearest_support = vp['mid_price']

        result['nearest_resistance'] = nearest_resistance
        result['nearest_support'] = nearest_support

        # 저항/지지 강도 계산
        total = above_volume + below_volume
        if total > 0:
            result['resistance_strength'] = int(above_volume / total * 100)
            result['support_strength'] = int(below_volume / total * 100)

        # 점수 계산
        score = 0

        # 상방 저항 약함 (30% 미만): +10점
        if result['resistance_strength'] < 30:
            score += 10
            result['signals'].append('LOW_RESISTANCE')
        elif result['resistance_strength'] < 50:
            score += 5
            result['signals'].append('MODERATE_RESISTANCE')

        # 하방 지지 강함 (50% 이상): +5점
        if result['support_strength'] >= 50:
            score += 5
            result['signals'].append('STRONG_SUPPORT')

        # 가까운 저항선 경고 (현재가의 5% 이내)
        if nearest_resistance:
            resistance_distance = (nearest_resistance / curr_close - 1) * 100
            if resistance_distance < 5:
                result['signals'].append('NEAR_RESISTANCE_WARNING')

        result['score'] = min(15, score)

    except Exception as e:
        pass

    return result


# ============================================================
# 기존 V3 패턴 (위치 필터 적용)
# ============================================================

def detect_obv_divergence(df: pd.DataFrame, lookback: int = 30) -> Dict:
    """OBV 불리시 다이버전스 감지 (기존 V3 동일)"""
    result = {'detected': False, 'strength': 0, 'days': 0}

    try:
        if len(df) < lookback:
            return result

        obv = ta.obv(df['Close'], df['Volume'])
        if obv is None:
            return result

        df_temp = df.tail(lookback).copy()
        df_temp['OBV'] = obv.tail(lookback).values

        price_lows = []
        obv_at_lows = []

        for i in range(2, len(df_temp) - 2):
            if (df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i-1] and
                df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i-2] and
                df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i+1] and
                df_temp['Low'].iloc[i] <= df_temp['Low'].iloc[i+2]):
                price_lows.append((i, df_temp['Low'].iloc[i]))
                obv_at_lows.append((i, df_temp['OBV'].iloc[i]))

        if len(price_lows) >= 2:
            prev_price_low = price_lows[-2][1]
            curr_price_low = price_lows[-1][1]
            prev_obv = obv_at_lows[-2][1]
            curr_obv = obv_at_lows[-1][1]

            if curr_price_low < prev_price_low and curr_obv > prev_obv:
                result['detected'] = True
                result['days'] = price_lows[-1][0] - price_lows[-2][0]
                price_decline = (prev_price_low - curr_price_low) / prev_price_low * 100
                obv_rise = (curr_obv - prev_obv) / abs(prev_obv) * 100 if prev_obv != 0 else 0
                result['strength'] = min(100, price_decline + obv_rise)

    except Exception:
        pass

    return result


def detect_accumulation_candle(df: pd.DataFrame, location: Dict) -> Dict:
    """
    매집봉 감지 (위치 필터 적용)

    고점권에서는 매집봉이 아닌 분산봉으로 해석
    """
    result = {
        'detected': False,
        'volume_ratio': 0,
        'upper_wick_ratio': 0,
        'is_distribution': False,
    }

    try:
        if len(df) < 20:
            return result

        curr = df.iloc[-1]
        vol_ma = df['Volume'].tail(20).mean()

        body = curr['Close'] - curr['Open']
        upper_shadow = curr['High'] - max(curr['Close'], curr['Open'])
        total_range = curr['High'] - curr['Low']

        if total_range == 0:
            return result

        # 바닥권 확인: 20일 저가의 105% 이내
        low_20d = df['Low'].tail(20).min()
        is_near_bottom = curr['Low'] <= low_20d * 1.05

        upper_wick_ratio = upper_shadow / total_range
        vol_ratio = curr['Volume'] / vol_ma if vol_ma > 0 else 0
        is_bullish_or_doji = body >= 0

        # 고점권에서 윗꼬리 + 거래량 = 분산
        if location.get('is_top_zone', False):
            if upper_wick_ratio >= 0.4 and vol_ratio >= 1.5:
                result['is_distribution'] = True
                result['volume_ratio'] = vol_ratio
                result['upper_wick_ratio'] = upper_wick_ratio * 100
                return result

        # 바닥권 매집봉
        if (is_near_bottom and
            upper_wick_ratio >= 0.4 and
            vol_ratio >= 1.5 and
            is_bullish_or_doji):
            result['detected'] = True
            result['volume_ratio'] = vol_ratio
            result['upper_wick_ratio'] = upper_wick_ratio * 100

    except Exception:
        pass

    return result


def detect_spring_pattern(df: pd.DataFrame) -> Dict:
    """Spring 패턴 감지 (기존 V3 동일)"""
    result = {'detected': False, 'recovery_strength': 0, 'volume_spike': False}

    try:
        if len(df) < 20:
            return result

        recent = df.tail(10)
        curr = df.iloc[-1]
        support = df['Low'].tail(20).quantile(0.1)

        breakdown_day = None
        for i in range(len(recent) - 1):
            if recent['Low'].iloc[i] < support:
                breakdown_day = i
                break

        if breakdown_day is not None:
            breakdown_low = recent['Low'].iloc[breakdown_day]

            if curr['Close'] > support:
                recovery = (curr['Close'] - breakdown_low) / breakdown_low * 100
                result['recovery_strength'] = recovery

                vol_ma = df['Volume'].tail(20).mean()
                if curr['Volume'] > vol_ma * 1.5:
                    result['volume_spike'] = True

                if recovery >= 3:
                    result['detected'] = True

    except Exception:
        pass

    return result


def detect_vcp_pattern(df: pd.DataFrame, location: Dict) -> Dict:
    """
    VCP 패턴 감지 (위치 필터 적용)

    고점권 VCP = 분산 패턴
    """
    result = {
        'detected': False,
        'contraction_pct': 0,
        'vol_dryup': False,
        'is_distribution': False,
    }

    try:
        if len(df) < 40:
            return result

        recent = df.tail(40)

        ranges = []
        volumes = []

        for i in range(4):
            period = recent.iloc[i*10:(i+1)*10]
            high = period['High'].max()
            low = period['Low'].min()
            vol = period['Volume'].mean()
            ranges.append(high - low)
            volumes.append(vol)

        first_range = ranges[0]
        last_range = ranges[3]
        first_vol = volumes[0]
        last_vol = volumes[3]

        first_low = recent.iloc[:10]['Low'].min()
        last_low = recent.iloc[30:]['Low'].min()

        range_contraction = last_range < first_range * 0.7
        lows_rising = last_low > first_low
        vol_contraction = last_vol < first_vol * 0.7

        if range_contraction and lows_rising:
            # 고점권 VCP = 분산
            if location.get('is_top_zone', False):
                result['is_distribution'] = True
                result['contraction_pct'] = (1 - last_range / first_range) * 100
            else:
                result['detected'] = True
                result['contraction_pct'] = (1 - last_range / first_range) * 100

            if vol_contraction:
                result['vol_dryup'] = True

    except Exception:
        pass

    return result


def detect_pullback_volume_dryup(df: pd.DataFrame) -> Dict:
    """눌림목 거래량 급감 감지 (기존 V3 동일)"""
    result = {'detected': False, 'pullback_pct': 0, 'vol_ratio': 0}

    try:
        if len(df) < 20:
            return result

        recent_5d = df.tail(5)
        prev_15d = df.iloc[-20:-5]

        down_days = recent_5d[recent_5d['Close'] < recent_5d['Open']]

        if len(down_days) == 0:
            return result

        down_vol = down_days['Volume'].mean()
        prev_vol = prev_15d['Volume'].mean()

        if prev_vol > 0:
            vol_ratio = down_vol / prev_vol
            result['vol_ratio'] = vol_ratio

            high_5d = recent_5d['High'].max()
            low_5d = recent_5d['Low'].min()
            pullback = (high_5d - low_5d) / high_5d * 100
            result['pullback_pct'] = pullback

            if vol_ratio < 0.6 and pullback >= 2:
                result['detected'] = True

    except Exception:
        pass

    return result


# ============================================================
# 메인 점수 계산 함수
# ============================================================

def calculate_score_v3_5(
    df: pd.DataFrame,
    investor_data: Optional[Dict] = None,
    short_data: Optional[Dict] = None,
    disclosure_data: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    V3.5 점수 계산 (사일런트 바이어 발전형)

    Args:
        df: OHLCV 데이터프레임 (최소 60일)
        investor_data: 투자자 동향 데이터 (naver_investor.py)
        short_data: 공매도/대차잔고 데이터 (krx_short_data.py)
        disclosure_data: 공시 데이터 (5% 공시, CB/BW)

    Returns:
        {
            'score': 최종 점수 (0-100),
            'disclosure_score': 공시 확증 점수 (0-15),
            'wyckoff_score': 와이코프 Phase 점수 (0-20),
            'pattern_score': 매집 패턴 점수 (0-25),
            'supply_demand_score': 수급 분석 점수 (0-20),
            'volume_score': 거래량/매물대 점수 (0-15),
            'trend_score': 추세/모멘텀 점수 (0-5),
            'bonus_score': 조합 보너스 점수,
            'signals': 발생한 신호 리스트,
            'patterns': 감지된 패턴,
            'disqualified': 과락 여부,
            'disqualify_reason': 과락 사유,
            'location': 가격 위치 정보,
            'wyckoff': 와이코프 Phase 정보,
            'indicators': 지표 상세값,
            'version': 'v3.5'
        }
    """
    if df is None or len(df) < 60:
        return None

    result = {
        'score': 0,
        'disclosure_score': 0,
        'wyckoff_score': 0,
        'pattern_score': 0,
        'supply_demand_score': 0,
        'volume_score': 0,
        'trend_score': 0,
        'bonus_score': 0,
        'signals': [],
        'patterns': [],
        'disqualified': False,
        'disqualify_reason': '',
        'location': {},
        'wyckoff': {},
        'indicators': {},
        'version': 'v3.5'
    }

    try:
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 기본 정보
        result['indicators']['close'] = curr['Close']
        result['indicators']['change_pct'] = ((curr['Close'] - prev['Close']) / prev['Close']) * 100
        result['indicators']['volume'] = curr['Volume']
        trading_value = curr['Close'] * curr['Volume']
        result['indicators']['trading_value_억'] = trading_value / 100_000_000

        # ========== 이동평균선 ==========
        df = df.copy()
        df['SMA_5'] = ta.sma(df['Close'], length=5)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_60'] = ta.sma(df['Close'], length=60)

        curr = df.iloc[-1]
        curr_sma5 = curr['SMA_5']
        curr_sma20 = curr['SMA_20']
        curr_sma60 = curr['SMA_60']

        result['indicators']['sma5'] = curr_sma5
        result['indicators']['sma20'] = curr_sma20
        result['indicators']['sma60'] = curr_sma60

        # === 과락 1: 역배열 → 0점 ===
        if curr_sma5 < curr_sma20 < curr_sma60:
            result['signals'].append('MA_REVERSE_ALIGNED')
            result['indicators']['ma_status'] = 'reverse_aligned'
            result['disqualified'] = True
            result['disqualify_reason'] = '역배열 (SMA5 < SMA20 < SMA60)'
            result['score'] = 0
            return result

        # ========== Phase 1: 위치 분석 ==========
        location = classify_price_location(df)
        result['location'] = location

        if location['is_top_zone']:
            result['signals'].append('TOP_ZONE')
        elif location['is_bottom_zone']:
            result['signals'].append('BOTTOM_ZONE')

        # 분산 패턴 감지
        distribution = detect_distribution_pattern(df)
        if distribution['detected']:
            result['signals'].append(f'DISTRIBUTION_{distribution["pattern_type"].upper()}')
            result['indicators']['distribution_severity'] = distribution['severity']

        # ========== Phase 2: 와이코프 Phase ==========
        wyckoff = detect_wyckoff_phase(df)
        result['wyckoff'] = wyckoff
        result['wyckoff_score'] = wyckoff['phase_score']

        if wyckoff['phase']:
            result['signals'].append(f'WYCKOFF_PHASE_{wyckoff["phase"]}')
            for event in wyckoff['events']:
                result['signals'].append(f'WYK_{event}')

        # ========== Phase 3: 수급 분석 ==========
        supply_demand = analyze_supply_demand(df, investor_data, short_data)

        if supply_demand['disqualified']:
            result['supply_demand_score'] = 0
            result['signals'].append('SUPPLY_DEMAND_DISQUALIFIED')
            result['indicators']['sd_disqualify_reason'] = supply_demand['disqualify_reason']
        else:
            result['supply_demand_score'] = supply_demand['score']
            result['signals'].extend(supply_demand['signals'])

        # ========== Phase 4: 공시 분석 ==========
        disclosure = analyze_disclosure_signals(disclosure_data)
        result['disclosure_score'] = disclosure['score']
        result['signals'].extend(disclosure['signals'])

        if disclosure['overhang_warning']:
            result['indicators']['cb_bw_overhang'] = True
            result['indicators']['max_score_limit'] = disclosure['max_score_limit']

        # ========== Phase 5: 매물대 분석 ==========
        volume_profile = analyze_volume_profile(df)
        result['volume_score'] = volume_profile['score']
        result['signals'].extend(volume_profile['signals'])
        result['indicators']['resistance_strength'] = volume_profile['resistance_strength']
        result['indicators']['support_strength'] = volume_profile['support_strength']

        # ========== 매집 패턴 (위치 필터 적용) ==========
        pattern_score = 0
        detected_patterns = []

        # 고점권이면 매집 패턴 점수 0점 (과락)
        if location['is_top_zone']:
            result['signals'].append('PATTERN_SCORE_ZEROED_TOP_ZONE')
            pattern_score = 0
        else:
            # OBV 다이버전스: +8점
            obv_div = detect_obv_divergence(df)
            if obv_div['detected']:
                pattern_score += 8
                result['signals'].append('OBV_BULLISH_DIV')
                detected_patterns.append('OBV_DIV')
                result['indicators']['obv_div_strength'] = obv_div['strength']
                result['indicators']['obv_div_days'] = obv_div['days']

            # 매집봉: +6점
            accum_candle = detect_accumulation_candle(df, location)
            if accum_candle['detected']:
                pattern_score += 6
                result['signals'].append('ACCUMULATION_CANDLE')
                detected_patterns.append('ACCUM_CANDLE')
                result['indicators']['accum_vol_ratio'] = accum_candle['volume_ratio']
            elif accum_candle['is_distribution']:
                result['signals'].append('DISTRIBUTION_CANDLE')
                detected_patterns.append('DIST_CANDLE')

            # Spring 패턴: +6점
            spring = detect_spring_pattern(df)
            if spring['detected']:
                pattern_score += 6
                result['signals'].append('SPRING_PATTERN')
                detected_patterns.append('SPRING')
                result['indicators']['spring_recovery'] = spring['recovery_strength']
                if spring['volume_spike']:
                    result['signals'].append('SPRING_VOLUME_SPIKE')

            # VCP 패턴: +5점
            vcp = detect_vcp_pattern(df, location)
            if vcp['detected']:
                pattern_score += 5
                result['signals'].append('VCP_PATTERN')
                detected_patterns.append('VCP')
                result['indicators']['vcp_contraction'] = vcp['contraction_pct']
                if vcp['vol_dryup']:
                    result['signals'].append('VCP_VOL_DRYUP')
            elif vcp['is_distribution']:
                result['signals'].append('VCP_DISTRIBUTION')
                detected_patterns.append('VCP_DIST')

        result['pattern_score'] = min(25, pattern_score)
        result['patterns'] = detected_patterns

        # ========== 추세/모멘텀 (5점) ==========
        trend_score = 0

        # 정배열: +3점
        if curr_sma5 > curr_sma20 > curr_sma60:
            trend_score += 3
            result['signals'].append('MA_ALIGNED')
            result['indicators']['ma_status'] = 'aligned'
        else:
            result['indicators']['ma_status'] = 'partial'

        # RSI 50-70: +2점
        df['RSI'] = ta.rsi(df['Close'], length=14)
        rsi = df.iloc[-1]['RSI']
        if pd.notna(rsi):
            result['indicators']['rsi'] = rsi
            if 50 <= rsi <= 70:
                trend_score += 2
                result['signals'].append('RSI_HEALTHY')

        result['trend_score'] = min(5, trend_score)

        # ========== 조합 보너스 ==========
        bonus_score = 0

        # 5% 공시 + Phase C + 기관 순매수 = +15점
        has_5pct_disclosure = any('5PCT_' in s for s in result['signals'])
        is_phase_c = wyckoff['phase'] == 'C'
        has_inst_buy = any('INST_' in s for s in result['signals'])

        if has_5pct_disclosure and is_phase_c and has_inst_buy:
            bonus_score += 15
            result['signals'].append('CONFIRMED_ACCUMULATION_COMBO')

        # Phase C + OBV 다이버전스 + 매물대 클리어 = +10점
        has_obv_div = 'OBV_DIV' in detected_patterns
        has_low_resistance = 'LOW_RESISTANCE' in result['signals']

        if is_phase_c and has_obv_div and has_low_resistance:
            bonus_score += 10
            result['signals'].append('PHASE_C_BREAKOUT_COMBO')

        result['bonus_score'] = bonus_score

        # ========== 최종 점수 계산 ==========
        total_score = (
            result['disclosure_score'] +
            result['wyckoff_score'] +
            result['pattern_score'] +
            result['supply_demand_score'] +
            result['volume_score'] +
            result['trend_score'] +
            result['bonus_score']
        )

        # CB/BW 오버행 시 최대 50점 제한
        max_limit = result['indicators'].get('max_score_limit', 100)
        total_score = min(total_score, max_limit)

        result['score'] = max(0, min(100, total_score))

        return result

    except Exception as e:
        print(f"V3.5 점수 계산 오류: {e}")
        return None


# 편의 함수: 투자자 데이터 포함 계산
def calculate_score_v3_5_with_investor(
    df: pd.DataFrame,
    stock_code: str,
    investor_fetcher=None,
    short_fetcher=None,
    disclosure_fetcher=None,
) -> Optional[Dict]:
    """
    V3.5 점수 계산 + 외부 데이터 자동 조회

    Args:
        df: OHLCV 데이터프레임
        stock_code: 종목코드
        investor_fetcher: 투자자 동향 조회 함수 (기본: naver_investor.get_investor_trend)
        short_fetcher: 공매도 데이터 조회 함수
        disclosure_fetcher: 공시 데이터 조회 함수

    Returns:
        V3.5 점수 계산 결과
    """
    investor_data = None
    short_data = None
    disclosure_data = None

    # 투자자 동향 조회
    if investor_fetcher:
        try:
            investor_data = investor_fetcher(stock_code, days=10)
        except Exception:
            pass

    # 공매도 데이터 조회
    if short_fetcher:
        try:
            short_data = short_fetcher(stock_code)
        except Exception:
            pass

    # 공시 데이터 조회
    if disclosure_fetcher:
        try:
            disclosure_data = disclosure_fetcher(stock_code)
            if disclosure_data and df is not None:
                disclosure_data['current_price'] = df.iloc[-1]['Close']
        except Exception:
            pass

    return calculate_score_v3_5(df, investor_data, short_data, disclosure_data)


# ============================================================
# 테스트
# ============================================================
if __name__ == "__main__":
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    # 테스트 종목
    test_stocks = ['005930', '035720', '000660']

    for code in test_stocks:
        df = fdr.DataReader(code, start_date)

        result = calculate_score_v3_5(df)
        if result:
            print(f"\n=== {code} V3.5 사일런트 바이어 발전형 ===")
            print(f"최종점수: {result['score']}")
            print(f"  공시 확증: {result['disclosure_score']}/15")
            print(f"  와이코프: {result['wyckoff_score']}/20 (Phase {result['wyckoff'].get('phase', '-')})")
            print(f"  매집 패턴: {result['pattern_score']}/25")
            print(f"  수급 분석: {result['supply_demand_score']}/20")
            print(f"  거래량/매물대: {result['volume_score']}/15")
            print(f"  추세/모멘텀: {result['trend_score']}/5")
            print(f"  조합 보너스: {result['bonus_score']}")
            print(f"위치: {result['location'].get('location', '-')}")
            print(f"패턴: {result['patterns']}")
            print(f"신호: {result['signals'][:10]}")  # 상위 10개만
            if result['disqualified']:
                print(f"과락: {result['disqualify_reason']}")
