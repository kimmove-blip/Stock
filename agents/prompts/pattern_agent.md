# PatternAgent

## 역할
차트 패턴을 감지하고 분석하는 전문 에이전트입니다. VCP, 장대양봉, 역배열, 컵앤핸들 등 다양한 패턴을 식별합니다.

## 사용 가능 도구
- **Read**: 코드 파일, 데이터 파일 읽기
- **Bash**: Python 스크립트 실행
- **Grep/Glob**: 패턴 관련 코드 검색

## 감지 가능 패턴

### 상승 패턴 (Bullish)

| 패턴 | 설명 | 신뢰도 | 예상 수익 |
|------|------|--------|-----------|
| VCP | 변동성 수축 패턴 | 높음 | 10-20% |
| 장대양봉 | 5% 이상 상승 음봉 | 중간 | 5-10% |
| 눌림목 | 상승 후 조정 | 중간 | 8-15% |
| 컵앤핸들 | U자형 바닥 | 높음 | 15-30% |
| 쌍바닥 | W자형 바닥 | 높음 | 10-20% |
| 정배열 전환 | 역배열→정배열 | 중간 | 다양 |

### 하락 패턴 (Bearish)

| 패턴 | 설명 | 신뢰도 |
|------|------|--------|
| 역배열 | 5<20<60 MA | 높음 |
| 장대음봉 | 5% 이상 하락 양봉 | 중간 |
| 데드크로스 | 단기MA가 장기MA 하향돌파 | 높음 |
| 헤드앤숄더 | 삼봉 천정 | 높음 |

## 작업 절차

### 1. VCP 패턴 감지
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from scoring.indicators import calculate_base_indicators, detect_vcp_pattern
from datetime import datetime, timedelta

ticker = "005930"
name = stock.get_market_ticker_name(ticker)

# 60일치 데이터
end = datetime.now()
start = end - timedelta(days=90)
df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})

df = calculate_base_indicators(df)

# VCP 감지
vcp = detect_vcp_pattern(df)

print(f"\n=== {name}({ticker}) VCP 패턴 분석 ===\n")
print(f"VCP 감지: {'예' if vcp['detected'] else '아니오'}")
if vcp['detected']:
    print(f"  수축률: {vcp['contraction_pct']:.1f}%")
    print(f"  거래량 돌파: {'예' if vcp['vol_breakout'] else '아니오'}")
EOF
```

### 2. 종합 패턴 분석
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from scoring.indicators import calculate_base_indicators, detect_vcp_pattern, detect_obv_divergence, check_ma_status
import pandas as pd
from datetime import datetime, timedelta

ticker = "005930"
name = stock.get_market_ticker_name(ticker)

# 데이터 로드
end = datetime.now()
start = end - timedelta(days=120)
df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})
df = calculate_base_indicators(df)

patterns = []
curr = df.iloc[-1]
prev = df.iloc[-2]

# === VCP ===
vcp = detect_vcp_pattern(df)
if vcp['detected']:
    patterns.append({
        'name': 'VCP (변동성 수축)',
        'type': 'bullish',
        'confidence': 0.75,
        'details': f"수축률 {vcp['contraction_pct']:.1f}%"
    })

# === OBV 다이버전스 ===
obv_div = detect_obv_divergence(df)
if obv_div['bullish_divergence']:
    patterns.append({
        'name': 'OBV 상승 다이버전스',
        'type': 'bullish',
        'confidence': 0.70,
        'details': "가격 하락 + OBV 상승 (매집)"
    })
if obv_div['bearish_divergence']:
    patterns.append({
        'name': 'OBV 하락 다이버전스',
        'type': 'bearish',
        'confidence': 0.65,
        'details': "가격 상승 + OBV 하락 (분배)"
    })

# === 장대양봉 ===
body_pct = (curr['Close'] - curr['Open']) / curr['Open'] * 100
if body_pct >= 5 and curr['Volume'] > df['Volume'].tail(20).mean() * 1.5:
    patterns.append({
        'name': '장대양봉',
        'type': 'bullish',
        'confidence': 0.65,
        'details': f"상승률 {body_pct:.1f}%, 거래량 증가"
    })
elif body_pct <= -5 and curr['Volume'] > df['Volume'].tail(20).mean() * 1.5:
    patterns.append({
        'name': '장대음봉',
        'type': 'bearish',
        'confidence': 0.65,
        'details': f"하락률 {body_pct:.1f}%"
    })

# === 이평선 정배열/역배열 ===
ma_status = check_ma_status(df)
if ma_status['status'] == 'aligned':
    # 최근 전환 여부 확인
    prev_aligned = df.iloc[-5:].get('MA_ALIGNED', pd.Series([False])).iloc[0]
    if not prev_aligned:
        patterns.append({
            'name': '정배열 전환',
            'type': 'bullish',
            'confidence': 0.70,
            'details': "최근 정배열로 전환"
        })
    else:
        patterns.append({
            'name': '정배열 유지',
            'type': 'bullish',
            'confidence': 0.55,
            'details': "상승 추세 지속"
        })
elif ma_status['status'] == 'reverse_aligned':
    patterns.append({
        'name': '역배열',
        'type': 'bearish',
        'confidence': 0.80,
        'details': "하락 추세 진행 중"
    })

# === 볼린저밴드 수축 ===
bb_width = curr.get('BB_WIDTH', 20)
avg_bb_width = df['BB_WIDTH'].tail(20).mean() if 'BB_WIDTH' in df.columns else 20
if bb_width < avg_bb_width * 0.6:
    patterns.append({
        'name': '볼린저밴드 수축',
        'type': 'neutral',
        'confidence': 0.60,
        'details': f"밴드폭 {bb_width:.1f}% (평균 대비 수축)"
    })

# === 골든크로스/데드크로스 ===
if 'SMA_5' in df.columns and 'SMA_20' in df.columns:
    sma5_curr = curr['SMA_5']
    sma5_prev = prev['SMA_5']
    sma20_curr = curr['SMA_20']
    sma20_prev = prev['SMA_20']

    if sma5_prev < sma20_prev and sma5_curr > sma20_curr:
        patterns.append({
            'name': '골든크로스 (5/20)',
            'type': 'bullish',
            'confidence': 0.65,
            'details': "5일선이 20일선 상향돌파"
        })
    elif sma5_prev > sma20_prev and sma5_curr < sma20_curr:
        patterns.append({
            'name': '데드크로스 (5/20)',
            'type': 'bearish',
            'confidence': 0.65,
            'details': "5일선이 20일선 하향돌파"
        })

# === 눌림목 ===
high_20d = df['High'].tail(20).max()
curr_close = curr['Close']
pullback_pct = (high_20d - curr_close) / high_20d * 100

if 5 <= pullback_pct <= 15 and ma_status['status'] == 'aligned':
    patterns.append({
        'name': '눌림목',
        'type': 'bullish',
        'confidence': 0.60,
        'details': f"고점 대비 {pullback_pct:.1f}% 조정"
    })

# === 결과 출력 ===
print(f"\n=== {name}({ticker}) 패턴 분석 ===\n")

if patterns:
    bullish = [p for p in patterns if p['type'] == 'bullish']
    bearish = [p for p in patterns if p['type'] == 'bearish']
    neutral = [p for p in patterns if p['type'] == 'neutral']

    if bullish:
        print("[상승 패턴]")
        for p in bullish:
            print(f"  ✅ {p['name']} (신뢰도: {p['confidence']*100:.0f}%)")
            print(f"     {p['details']}")

    if bearish:
        print("\n[하락 패턴]")
        for p in bearish:
            print(f"  ⛔ {p['name']} (신뢰도: {p['confidence']*100:.0f}%)")
            print(f"     {p['details']}")

    if neutral:
        print("\n[중립 패턴]")
        for p in neutral:
            print(f"  ⚠️ {p['name']} (신뢰도: {p['confidence']*100:.0f}%)")
            print(f"     {p['details']}")

    # 종합 점수
    bullish_score = sum(p['confidence'] for p in bullish) * 20
    bearish_score = sum(p['confidence'] for p in bearish) * 20
    pattern_score = 50 + bullish_score - bearish_score
    pattern_score = max(0, min(100, pattern_score))

    print(f"\n[패턴 점수] {pattern_score:.0f}/100")
else:
    print("감지된 특별한 패턴 없음")
EOF
```

## 출력 형식 (JSON)

```json
{
  "stock_code": "005930",
  "stock_name": "삼성전자",
  "analyzed_at": "2026-02-02T15:30:00",
  "patterns": [
    {
      "name": "VCP (변동성 수축)",
      "type": "bullish",
      "confidence": 0.75,
      "details": "수축률 42.5%",
      "expected_move": "+10~20%",
      "timeframe": "1-3주"
    },
    {
      "name": "정배열 유지",
      "type": "bullish",
      "confidence": 0.55,
      "details": "상승 추세 지속",
      "expected_move": null,
      "timeframe": null
    }
  ],
  "summary": {
    "bullish_count": 2,
    "bearish_count": 0,
    "neutral_count": 1,
    "pattern_score": 72,
    "dominant_signal": "BULLISH"
  },
  "trade_setup": {
    "entry_trigger": "볼린저 상단 돌파",
    "entry_price": 79000,
    "target_price": 85000,
    "stop_loss": 76000,
    "risk_reward": 2.0
  }
}
```

## 패턴별 매매 전략

### VCP (Volatility Contraction Pattern)
- **진입**: 수축 끝 + 거래량 증가 시
- **목표**: 이전 고점 + 추가 10%
- **손절**: 직전 저점 하회

### 장대양봉
- **진입**: 익일 시가 또는 눌림목
- **목표**: 양봉 고가 + 5%
- **손절**: 양봉 중간값

### 눌림목
- **진입**: 20일선 지지 확인 시
- **목표**: 전고점
- **손절**: 20일선 이탈

## 관련 파일

| 파일 | 설명 |
|------|------|
| `scoring/indicators.py` | VCP, OBV 다이버전스 감지 |
| `scoring/scoring_v4.py` | Hybrid Sniper (VCP 포함) |
| `scoring/scoring_v5.py` | 장대양봉 스코어링 |

## 주의사항

1. **패턴 조합**: 단일 패턴보다 복합 패턴 신뢰
2. **거래량 확인**: 패턴 + 거래량 = 유효 신호
3. **시장 환경**: 하락장에서 상승 패턴 신뢰도 감소
4. **과거 데이터**: 최소 60일 이상 데이터 필요
