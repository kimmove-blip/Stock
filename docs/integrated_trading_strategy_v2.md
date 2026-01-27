# V-Engine 통합 트레이딩 전략서 (Source-Based Edition)

> **이 문서는 V1~V10 엔진의 실제 파이썬 코드 로직과 기술적 분석 이론을 기반으로 작성되었습니다.**
> 모든 전략에는 소스 코드 참조(파일:라인)가 명시되어 있습니다.

---

## 목차
1. [시장 국면 판단 (Market Regime)](#1-시장-국면-판단-market-regime)
2. [1단계: 종목 발굴 (What to Buy)](#2-1단계-종목-발굴-what-to-buy)
3. [2단계: 매수 시기 결정 (When to Buy)](#3-2단계-매수-시기-결정-when-to-buy)
4. [3단계: 매도 시기 결정 (When to Sell)](#4-3단계-매도-시기-결정-when-to-sell)
5. [엔진별 상세 로직 참조](#5-엔진별-상세-로직-참조)
6. [실전 매매 체크리스트](#6-실전-매매-체크리스트)

---

## 1. 시장 국면 판단 (Market Regime)

### 1.1 다우 이론 (Dow Theory) 기반 추세 판단

전략 실행 전, 시장의 **1차 추세(Primary Trend)**를 파악해야 합니다.

| 국면 | 정의 | 매매 전략 |
|------|------|----------|
| **강세장** | 고점-저점이 연속 상승, 지수 20일선 > 60일선 | V2, V4, V7 (추세 추종) |
| **약세장** | 고점-저점이 연속 하락, 지수 20일선 < 60일선 | V8, V1 (역발상 반등) |
| **횡보장** | 고점-저점이 수평, 지수 박스권 | V3, V5, V6 (매집 탐지, 스윙) |
| **테마장** | 특정 섹터 거래대금 급증 | V10 (대장주-종속주) |

### 1.2 일목균형표 필터

**소스**: `scoring/scoring_v4.py:289-301`

```python
# 일목균형표 구름대 위: +5점
ichimoku = ta.ichimoku(df['High'], df['Low'], df['Close'])
span_a = ich_df['ISA_9'].iloc[-1]  # 선행스팬A
span_b = ich_df['ISB_26'].iloc[-1]  # 선행스팬B
cloud_top = max(span_a, span_b)
if curr['Close'] > cloud_top:
    score += 5  # 구름대 위 = 상승 추세 확인
```

**해석**:
- 주가가 **양운(구름대) 위**에 위치 → 상승 추세 건전성 확인
- 주가가 **음운(구름대) 아래** → 하락 추세, 추세 추종 진입 금지

---

## 2. 1단계: 종목 발굴 (What to Buy)

### 2.1 전략 A: 추세 추종 및 주도주 발굴

**사용 엔진**: V2, V4, V7
**적용 시장**: 강세장

#### 2.1.1 이동평균선 정배열 + 기울기 필터

**소스**: `scoring/scoring_v2.py:150-165`

```python
# 20일선 기울기 계산 (핵심 지표)
sma20_slope = (curr_sma20 - sma20_5d_ago) / sma20_5d_ago * 100

if sma20_slope >= 3.0:
    score += 15  # 가파른 상승
    signals.append('MA20_SLOPE_STEEP')
elif sma20_slope >= 1.5:
    score += 10  # 상승 추세
    signals.append('MA20_SLOPE_RISING')
elif sma20_slope >= 0.5:
    score += 3   # 완만한 상승
    signals.append('MA20_SLOPE_GENTLE')
```

| 조건 | 점수 | 의미 |
|------|------|------|
| MA5 > MA20 > MA60 (정배열) | +5 | 기본 추세 확인 |
| MA20 기울기 ≥ 3% | +15 | 강력한 상승 추세 |
| MA20 기울기 ≥ 1.5% | +10 | 건전한 상승 추세 |
| MA20 기울기 ≥ 0.5% | +3 | 완만한 상승 |
| **역배열 (5 < 20 < 60)** | **0점 (과락)** | **진입 금지** |

> ⚠️ **핵심 원칙**: 역배열 시 점수 = 0으로 강제 과락 처리 (`scoring_v2.py:130-135`)

#### 2.1.2 RSI Sweet Spot 필터

**소스**: `scoring/scoring_v2.py:195-220`

```python
rsi = df.iloc[-1]['RSI']
prev_rsi = df.iloc[-2]['RSI']

if 60 <= rsi <= 75:
    score += 15  # Sweet Spot
    signals.append('RSI_SWEET_SPOT')
elif 50 <= rsi < 60:
    score += 5
elif rsi > 80:
    if rsi > prev_rsi:
        score += 10  # 상승 중
    else:
        score -= 5   # 꺾임
elif rsi < 30:
    score -= 10  # 떨어지는 칼날
    signals.append('RSI_FALLING_KNIFE')
```

| RSI 구간 | 점수 | 해석 |
|----------|------|------|
| **60-75** | **+15** | **모멘텀 최강 구간 (Sweet Spot)** |
| 50-60 | +5 | 건전한 상승 |
| >80 (상승중) | +10 | 강력한 모멘텀 |
| >80 (꺾임) | -5 | 과열 경고 |
| **<30** | **-10** | **떨어지는 칼날 ❌** |

> ⚠️ **핵심 철학**: V1은 RSI<30을 매수 기회로 보지만, **V2는 "떨어지는 칼날"로 간주하여 감점 처리**

#### 2.1.3 거래대금 필터

**소스**: `scoring/scoring_v2.py:240-260`

| 거래대금 | 점수 | 의미 |
|----------|------|------|
| ≥ 500억원 | +15 | 대형주급 유동성 |
| ≥ 100억원 | +10 | 충분한 유동성 |
| ≥ 30억원 | +3 | 최소 유동성 |
| < 10억원 | -5 | 유동성 리스크 |

---

### 2.2 전략 B: 세력 매집 및 수급 포착

**사용 엔진**: V3, V3.5, V4
**적용 시장**: 횡보장, 바닥권

#### 2.2.1 OBV 다이버전스 (OBV Divergence)

**소스**: `scoring/scoring_v3.py:54-105`

```python
def detect_obv_divergence(df: pd.DataFrame, lookback: int = 30) -> Dict:
    """
    OBV 불리시 다이버전스 감지
    세력 매집 신호: 주가는 저점을 낮추는데 OBV는 저점을 높임
    """
    obv = ta.obv(df['Close'], df['Volume'])

    # 주가 저점 찾기
    price_at_lows = []
    obv_at_lows = []

    # 불리시 다이버전스: 가격↓ OBV↑
    if curr_price < prev_price and curr_obv > prev_obv:
        return {'detected': True, 'type': 'bullish', 'days': days}
```

**해석**:
- **주가 하락 + OBV 상승** = 스마트머니 유입 (매집)
- "가격은 속일 수 있어도 거래량은 속일 수 없다" (Granville 원칙)

| 조건 | 점수 | 신호 |
|------|------|------|
| OBV 불리시 다이버전스 | +12 | `OBV_BULLISH_DIVERGENCE` |

#### 2.2.2 VCP 패턴 (Volatility Contraction Pattern)

**소스**: `scoring/scoring_v4.py:71-110`

```python
def detect_vcp_pattern(df: pd.DataFrame) -> Dict:
    """
    VCP (Volatility Contraction Pattern) 패턴 감지

    VCP 특징:
    1. 변동성 축소 (변동폭 감소)
    2. 거래량 감소 (건조해짐)
    3. 지지선 근처에서 수렴
    """
    # 변동성 축소율 계산
    recent_range = (recent_high - recent_low) / recent_low * 100
    earlier_range = (earlier_high - earlier_low) / earlier_low * 100
    contraction_pct = (earlier_range - recent_range) / earlier_range * 100

    # VCP 조건: 변동성 50% 이상 축소 + 거래량 감소
    if contraction_pct >= 50 and volume_declining:
        return {'detected': True, 'contraction_pct': contraction_pct}
```

| 조건 | 점수 | 의미 |
|------|------|------|
| 변동성 50%+ 축소 + 거래량 감소 | +12 | 매집 완료 임박 |

#### 2.2.3 와이코프 국면 분석 (Wyckoff Phase)

**소스**: `scoring/scoring_v3_5.py:400-570`

| Phase | 특징 | 매매 전략 |
|-------|------|----------|
| **A** | Selling Climax (SC) 후 첫 반등 | 관망 |
| **B** | 박스권 횡보, 세력 매집 | 관심종목 등록 |
| **C** | **Spring** (지지선 이탈 후 회복) | **최적 매수 타이밍** |
| **D** | Sign of Strength (SOS) | 추격 매수 가능 |
| **E** | 본격 상승 (SOS 후 5%+ 추가 상승) | 보유 |

```python
# Spring 감지 (Phase C)
# SC 저점 대비 5% 이상 반등
if curr_close > sc_low * 1.05:
    return 'Phase_C'

# SOS 이후 5% 이상 추가 상승 시 Phase E
if curr_close > sos_price * 1.05:
    return 'Phase_E'
```

#### 2.2.4 공시 확증 + 숏커버링 필터 (V3.5)

**소스**: `scoring/scoring_v3_5.py:15-31, 576-610`

```python
# 공시 확증 점수 체계
│ 1. 공시 확증                    │ 15점  │
#   - 5% 신규 보유 공시 (경영참가 목적)
#   - 보유 목적 변경 (단순투자→경영참가)

# 숏커버링 vs 진성 매집 구분
def detect_short_covering_risk():
    """
    - 대차잔고 급감 (10일 내 20%+) + 주가 상승 = 숏커버링 경고
    - 공매도 비중 5%+ 에서 급감 = 숏스퀴즈 가능성
    """
```

| 조건 | 점수 | 의미 |
|------|------|------|
| 5% 대량보유 공시 (경영참가) | +15 | 강력한 매집 신호 |
| 대차잔고 -20% + 주가 상승 | 수급 점수 0 | **숏커버링 경고** |
| 고점권 (60일 고가 95%+) | 매집 패턴 0점 | 배분 위험 |

---

### 2.3 전략 C: 대장주-종속주 캐치업

**사용 엔진**: V10
**적용 시장**: 테마장

**소스**: `scoring/score_v10_leader_follower.py:93-105, 246-260`

```python
def get_correlation(leader_code: str, follower_code: str) -> float:
    """대장주-종속주 상관계수 조회 (피어슨 상관계수)"""
    return leader['correlation']

# 상관계수 점수 (25점) - 실측값 사용
if corr >= 0.8:
    score += 25
    signals.append(f"상관계수 {corr:.2f} (매우 높음)")
elif corr >= 0.7:
    score += 20
elif corr >= 0.6:
    score += 14
elif corr >= 0.5:
    score += 8
```

**캐치업 조건** (`score_v10_leader_follower.py:324-420`):

```python
# 캐치업 기회 조건
if leader_change >= min_leader_change:  # 대장주 +3% 이상
    if follower_change <= max_follower_change:  # 종속주 +2% 이하
        gap = leader_change - follower_change  # 캐치업 갭
```

| 조건 | 점수 | 설명 |
|------|------|------|
| 상관계수 ≥ 0.8 | +25 | 강한 동행성 |
| 상관계수 0.7-0.8 | +20 | 양호한 동행성 |
| 대장주 +7% 이상 | +16 | 강력한 리더 움직임 |
| 캐치업 갭 ≥ 6% | +12 | 따라잡기 여력 |

---

## 3. 2단계: 매수 시기 결정 (When to Buy)

### 3.1 타점 1: 정밀 기술적 진입 (Sniper Entry)

#### 3.1.1 캔들 패턴 확증

**소스**: `scoring/scoring_v1.py:421-445`

```python
# 망치형 (Hammer) - 하락 추세 전환 신호
hammer = ta.cdl_pattern(df['Open'], df['High'], df['Low'], df['Close'], name='hammer')
if hammer.iloc[-1].values[0] != 0:
    score += 15
    patterns.append('HAMMER')

# 상승 장악형 (Bullish Engulfing)
engulfing = ta.cdl_pattern(..., name='engulfing')
if engulfing.iloc[-1].values[0] > 0:
    score += 15
    patterns.append('BULLISH_ENGULFING')

# 모닝스타 (Morning Star) - 강력한 반전 신호
morning_star = ta.cdl_pattern(..., name='morningstar')
if morning_star.iloc[-1].values[0] != 0:
    score += 20
    patterns.append('MORNING_STAR')
```

| 패턴 | 점수 | 신뢰도 | 의미 |
|------|------|--------|------|
| **모닝스타** | +20 | ★★★★★ | 강력한 반전 |
| 망치형 | +15 | ★★★★☆ | 하락세 소진 |
| 상승 장악형 | +15 | ★★★★☆ | 매수세 우위 |

> **기술적 분석 이론**: 캔들 패턴은 **지지선 근처**에서 발생할 때 신뢰도가 높음

#### 3.1.2 StochRSI 골든크로스

**소스**: `scoring/scoring_v4.py:163-185`

```python
def calculate_stoch_rsi(df: pd.DataFrame) -> Optional[Dict]:
    stoch_rsi = ta.stochrsi(df['Close'], length=14, rsi_length=14, k=3, d=3)

    curr_k = stoch_rsi.iloc[-1]['STOCHRSIk']
    curr_d = stoch_rsi.iloc[-1]['STOCHRSId']
    prev_k = stoch_rsi.iloc[-2]['STOCHRSIk']
    prev_d = stoch_rsi.iloc[-2]['STOCHRSId']

    # 골든크로스 (K가 D를 상향 돌파)
    if prev_k <= prev_d and curr_k > curr_d:
        if curr_k < 30:  # 과매도권에서 골든크로스
            return {'golden_cross': True, 'oversold': True}
```

| 조건 | 점수 | 신호 |
|------|------|------|
| StochRSI K<30 골든크로스 | +7 | `STOCHRSI_GOLDEN_CROSS_OVERSOLD` |
| StochRSI 상승 추세 | +4 | `STOCHRSI_BULLISH` |

> **RSI vs StochRSI**: StochRSI는 RSI보다 **민감**하여 더 빠른 진입 신호를 제공

#### 3.1.3 눌림목 거래량 급감

**소스**: `scoring/scoring_v3.py:180-220`

```python
def detect_pullback_volume_dryup(df: pd.DataFrame) -> Dict:
    """
    눌림목 거래량 급감 감지
    - 상승 후 조정 시 거래량이 평균의 80% 미만으로 감소
    - 세력이 이탈하지 않았음을 의미
    """
    avg_volume = df['Volume'].rolling(20).mean().iloc[-1]
    recent_volume = df['Volume'].iloc[-5:].mean()

    if recent_volume < avg_volume * 0.8:
        return {'detected': True, 'volume_ratio': recent_volume / avg_volume}
```

| 조건 | 점수 | 의미 |
|------|------|------|
| 조정 시 거래량 < 평균 80% | +8 | 매도세 고갈, 매수 적기 |

---

### 3.2 타점 2: 역발상 과매도 진입 (Contrarian Entry)

**사용 엔진**: V8, V1
**적용 시장**: 약세장

#### 3.2.1 V8 필수 조건

**소스**: `scoring/score_v8_contrarian_bounce.py:5-6, 96-110`

```python
# V8 핵심 발견 (백테스트 결과)
# - 추세<=15 & 모멘텀>=12: 42.9% 승률, +2.77% 평균수익률

# 과락 조건 확인
def _check_disqualification_v8(df, momentum_score, trend_score):
    # 모멘텀 점수 >= 12 (필수)
    if momentum_score < 12:
        return {'disqualified': True, 'reason': 'MOMENTUM_TOO_LOW'}

    # 추세 점수 <= 20 (필수)
    if trend_score > 20:
        return {'disqualified': True, 'reason': 'TREND_TOO_STRONG'}
```

| 필수 조건 | 값 | 이유 |
|----------|-----|------|
| 모멘텀 점수 | ≥ 12 | 반등 에너지 확보 |
| 추세 점수 | ≤ 20 | 약한 추세에서만 작동 |

> **핵심 인사이트**: "약한 추세 + 강한 모멘텀 = 최고의 엣지"

#### 3.2.2 RSI 과매도 탈출

**소스**: `scoring/score_v8_contrarian_bounce.py:110-140`

```python
# 반등 신호 (최대 40점)
rsi = df['RSI'].iloc[-1]
prev_rsi = df['RSI'].iloc[-2]

# RSI 30 상향 돌파 (과매도 탈출)
if prev_rsi < 30 and rsi >= 30:
    bounce_score += 15
    signals.append('RSI_OVERSOLD_ESCAPE')
```

#### 3.2.3 볼린저밴드 하단 지지

**소스**: `scoring/scoring_v5.py:295-320`

```python
def _check_bollinger_squeeze(df: pd.DataFrame) -> Dict:
    """볼린저 밴드 수축 패턴 - 최대 25점"""

    # 극단적 수축 (폭발 임박)
    if bb_width < bb_width_ma * 0.7:
        score += 15
        signals.append('BB_EXTREME_SQUEEZE')
    elif today['bb_squeeze']:
        score += 10

    # 돌파 준비 (수축 + 상단 접근)
    if today['bb_squeeze'] and today['bb_position'] > 0.7:
        score += 5
        signals.append('BB_BREAKOUT_READY')
```

| 조건 | 점수 | 의미 |
|------|------|------|
| BB 극단적 수축 (폭 < 평균 70%) | +15 | 폭발 임박 |
| BB 수축 + 상단 접근 | +5 | 돌파 준비 |
| BB 하단 터치 후 양봉 | +15 | 지지 확인 |

---

### 3.3 타점 3: 갭 트레이딩 (V9 자동매매)

**소스**: `predict_gap_prob70.py`, `models/gap_model_v9.pkl`

```python
# 매수 조건 (15:20 자동 실행)
if gap_probability >= 0.70:  # 70% 이상
    execute_buy_at_close()

# 필터 조건
거래대금 >= 50억원
등락률: -15% ~ +25%
```

| 확률 임계값 | 일평균 거래 | 승률 | 순수익률 |
|------------|------------|------|----------|
| ≥70% | 3-4건 | 61.2% | +0.185% |
| ≥75% | 1-2건 | 63.8% | +0.428% |

---

## 4. 3단계: 매도 시기 결정 (When to Sell)

### 4.1 원칙 1: 이익 실현 (Profit Taking)

#### 4.1.1 ATR 기반 목표가

**소스**: `scoring/score_v7_trend_momentum.py:182-190, 24-27`

```python
# ATR 계산
tr = pd.concat([
    df['High'] - df['Low'],
    abs(df['High'] - df['Close'].shift(1)),
    abs(df['Low'] - df['Close'].shift(1))
], axis=1).max(axis=1)

df['atr'] = tr.rolling(14, min_periods=1).mean()

# V7 청산 전략
# - 목표가: 진입가 + ATR × 1.5
# - 손절가: 진입가 - ATR × 0.8
# - 트레일링 스탑: ATR×0.5 수익 시 본전 스탑
```

| 전략 | 목표가 | 손절가 | R:R |
|------|--------|--------|-----|
| **V7 추세모멘텀** | Entry + ATR × 1.5 | Entry - ATR × 0.8 | 1.875:1 |
| V6 스윙 | Entry + ATR × 2.0 | Entry - ATR × 1.0 | 2:1 |
| V8 역발상 | Entry + ATR × 1.5 | Entry - ATR × 0.8 | 1.875:1 |

**계산 예시**:
```
삼성전자: 현재가 80,000원, ATR(14) = 1,500원

목표가 = 80,000 + (1,500 × 1.5) = 82,250원 (+2.8%)
손절가 = 80,000 - (1,500 × 0.8) = 78,800원 (-1.5%)
트레일링 활성화 = 80,000 + (1,500 × 0.5) = 80,750원 (+0.9%)
```

#### 4.1.2 RSI 과열 이탈 분할 매도

**소스**: `scoring/scoring_v2.py:203-220`

```python
if rsi > 80:
    if rsi > prev_rsi:
        score += 10  # 아직 상승 중
    else:
        score -= 5   # 꺾임 → 매도 신호
        signals.append('RSI_OVERBOUGHT_DECLINING')
```

| RSI | 조치 | 비중 |
|-----|------|------|
| 70 도달 | 1차 분할 매도 | 30% |
| 80 도달 | 2차 분할 매도 | 40% |
| 80 이탈 (꺾임) | 잔량 청산 | 30% |

#### 4.1.3 하락 반전 캔들 패턴

**소스**: `scoring/scoring_v1.py:430-445`

```python
# 하락 장악형 (Bearish Engulfing)
if engulfing.iloc[-1].values[0] < 0:
    score -= 15
    patterns.append('BEARISH_ENGULFING')

# 유성형 (Shooting Star) - V4에서 감점 처리
# scoring_v4.py:270-280
if is_shooting_star:
    score -= 5
    signals.append('SHOOTING_STAR')
```

| 패턴 | 조치 | 신뢰도 |
|------|------|--------|
| **흑삼병** | 전량 매도 | ★★★★★ |
| 하락 장악형 | 즉시 매도 | ★★★★☆ |
| 유성형 | 분할 매도 | ★★★☆☆ |

---

### 4.2 원칙 2: 손절매 (Risk Management)

#### 4.2.1 트레일링 스탑 (Trailing Stop)

**소스**: `scoring/score_v7_trend_momentum.py:27`

```python
# 트레일링 스탑: ATR×0.5 수익 시 본전 스탑
if unrealized_profit >= atr * 0.5:
    stop_loss = entry_price  # 본전으로 상향
```

**작동 방식**:
```
매수가: 10,000원 | ATR: 200원

1단계: 10,100원 도달 (+1%) → 손절가 유지 (9,840원)
2단계: 10,100원 도달 (ATR×0.5 = +100원) → 손절가 본전(10,000원)으로 상향
3단계: 10,200원 도달 → 손절가 10,100원으로 상향 (트레일링)
```

#### 4.2.2 V10 테마주 -3% 룰

**소스**: `scoring/score_v10_leader_follower.py:20-23`

```python
# 청산 전략:
# - 목표가: 대장주 상승률의 70~80% 수준 캐치업
# - 손절가: -3% (빠른 손절)
# - 시간 손절: 최대 3일 (모멘텀 소멸)
```

| 조건 | 손절가 | 이유 |
|------|--------|------|
| V10 테마주 | -3% | 변동성 큼, 빠른 손절 |
| 추세 전략 | -ATR × 0.8 | 변동성 조정 |
| 20일선 이탈 | 종가 기준 | 추세 훼손 |

---

### 4.3 원칙 3: 시간 손절 (Time Cut)

**소스**: `scoring/score_v7_trend_momentum.py:14, 26`

```python
# V7 개선사항
# 5. 시간 손절 단축 (5일 → 3일)

# - 시간 손절: 최대 3일 홀딩
```

| 전략 | 최대 보유 | 미반응 시 |
|------|----------|----------|
| V7 추세모멘텀 | 3일 | 전량 매도 |
| V8 역발상 | 3일 | 전량 매도 |
| V6 스윙 | 5일 | 전량 매도 |
| V10 캐치업 | 3일 | 전량 매도 |
| V9 갭 | 당일 | 익일 시가 매도 |

> **철학**: 예상한 모멘텀이 3-5일 내 발생하지 않으면 추세가 없다고 판단

---

## 5. 엔진별 상세 로직 참조

### 5.1 소스 파일 매핑

| 엔진 | 파일 | 핵심 함수 |
|------|------|----------|
| V1 | `scoring/scoring_v1.py` | `calculate_score_v1()` |
| V2 | `scoring/scoring_v2.py` | `calculate_score_v2()` |
| V3 | `scoring/scoring_v3.py` | `calculate_score_v3()`, `detect_obv_divergence()` |
| V3.5 | `scoring/scoring_v3_5.py` | `calculate_score_v3_5()`, `detect_wyckoff_phase()` |
| V4 | `scoring/scoring_v4.py` | `calculate_score_v4()`, `detect_vcp_pattern()` |
| V5 | `scoring/scoring_v5.py` | `calculate_score_v5()`, `_check_bollinger_squeeze()` |
| V6 | `scoring/scoring_v6.py` | `calculate_score_v6()` |
| V7 | `scoring/score_v7_trend_momentum.py` | `calculate_score_v7()` |
| V8 | `scoring/score_v8_contrarian_bounce.py` | `calculate_score_v8()` |
| V9 | `models/gap_model_v9.pkl` | RandomForest 모델 |
| V10 | `scoring/score_v10_leader_follower.py` | `calculate_score_v10()`, `get_follower_opportunities()` |

### 5.2 핵심 코드 라인 참조

| 로직 | 파일:라인 |
|------|----------|
| 역배열 과락 | `scoring_v2.py:130-135` |
| MA20 기울기 계산 | `scoring_v2.py:150-165` |
| RSI Sweet Spot | `scoring_v2.py:195-220` |
| OBV 다이버전스 | `scoring_v3.py:54-105` |
| VCP 패턴 | `scoring_v4.py:71-110` |
| StochRSI | `scoring_v4.py:163-185` |
| 일목균형표 | `scoring_v4.py:289-301` |
| 볼린저 스퀴즈 | `scoring_v5.py:295-320` |
| ATR 계산/청산 | `score_v7.py:182-190, 24-27` |
| V8 필수조건 | `score_v8.py:96-110` |
| 상관계수 점수 | `score_v10.py:246-260` |
| 캔들 패턴 | `scoring_v1.py:421-445` |

---

## 6. 실전 매매 체크리스트

### 6.1 종합 매매 기준표

| 구분 | 추세 매매 (Bull) | 역발상 매매 (Bear/Range) | 소스 참조 |
|------|-----------------|------------------------|----------|
| **대상** | 정배열, 거래대금>500억, RSI 60-75 | RSI<30 탈출, 이격도 과다 | V2:130-220 |
| **진입** | RSI Sweet Spot, StochRSI 골든크로스 | RSI 30 상향돌파, 망치형 캔들 | V4:163-185, V1:421 |
| **보조** | 눌림목 거래량 50% 급감 | BB 하단 터치 양봉 | V3:180-220 |
| **목표** | ATR × 1.5 익절, RSI 80 | 단기 반등 ATR × 1.0 | V7:24-27 |
| **손절** | 20일선 이탈, ATR × 0.8 | 전저점 이탈 | V7:25 |
| **시간** | 최대 3일 | 최대 3일 | V7:14, V8 |

### 6.2 일일 체크리스트

#### 장 시작 전 (08:30-09:00)
```
□ 코스피/코스닥 지수 20일선 vs 60일선 확인 (시장 국면)
□ V2 TOP100 리스트 확인
□ V10 대장주 전일 급등 여부 체크
□ 보유 종목 손절가/목표가 사전 설정
```

#### 장중 (09:00-15:20)
```
□ V2 70점+ 종목 모니터링
□ V10 대장주 +3% 이상 시 종속주 체크
□ 손절가 도달 → 즉시 청산 (감정 배제)
□ 목표가 도달 → 분할 매도 (30%/40%/30%)
```

#### 장 마감 (15:20-15:30)
```
□ V9 갭상승 확률 70%+ 종목 자동매수
□ 보유 종목 일봉 캔들 패턴 확인 (유성형, 장악형)
□ 당일 매매 결과 기록
```

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.0 | 2026-01-27 | 최초 작성 |
| 2.0 | 2026-01-27 | 소스 코드 참조 추가, 기술적 분석 이론 통합 |

---

*이 문서는 `/home/kimhc/Stock/scoring/` 디렉토리의 실제 파이썬 코드를 분석하여 작성되었습니다.*
*모든 점수, 조건, 로직은 코드에서 직접 추출되었으며, 각 항목에 소스 참조가 명시되어 있습니다.*
