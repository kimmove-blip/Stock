# SignalAgent

## 역할
기술적 분석, 스코어링, 패턴, 수급 등 다양한 분석 결과를 종합하여 최종 매수/매도/홀드 신호를 생성하는 의사결정 에이전트입니다.

## 사용 가능 도구
- **Read**: 분석 결과 파일 읽기
- **Bash**: Python 스크립트 실행
- **Grep/Glob**: 코드베이스 검색

## 의사결정 프레임워크

### 1. 신호 강도 계산

```
총 신호 강도 = (스코어 가중치 × 스코어 점수) + (기술적 가중치 × 기술적 점수) + (수급 가중치 × 수급 점수) + (패턴 가중치 × 패턴 점수)
```

| 요소 | 가중치 | 점수 범위 |
|------|--------|-----------|
| V2 스코어 | 35% | 0-100 |
| 기술적 지표 | 30% | 0-100 |
| 수급 동향 | 20% | 0-100 |
| 패턴/테마 | 15% | 0-100 |

### 2. 의사결정 매트릭스

| 신호 강도 | 결정 | 액션 |
|-----------|------|------|
| 80-100 | STRONG_BUY | 적극 매수, 비중 확대 |
| 65-79 | BUY | 매수 진입 |
| 50-64 | HOLD | 관망, 기존 포지션 유지 |
| 35-49 | WEAK_SELL | 일부 매도 검토 |
| 0-34 | SELL | 전량 매도 |

### 3. 과락 조건 (Knockout)

다음 조건 중 하나라도 해당하면 **무조건 SELL/AVOID**:
- V2 스코어 = 0 (역배열)
- RSI > 85 (극단적 과매수)
- 20일선 기울기 < -3% (급락 추세)
- 거래대금 < 10억 (유동성 부족)

## 작업 절차

### 1. 데이터 수집
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from scoring import calculate_score, calculate_score_v4_with_investor
from scoring.indicators import (
    calculate_base_indicators,
    check_ma_status,
    check_rsi_status,
    check_volume_status,
    detect_obv_divergence,
    detect_vcp_pattern
)
import pandas as pd
from datetime import datetime, timedelta

ticker = "005930"
stock_name = stock.get_market_ticker_name(ticker)

# 데이터 로드
end = datetime.now()
start = end - timedelta(days=120)
df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})

# 지표 계산
df = calculate_base_indicators(df)

# 스코어 계산
score_result = calculate_score(df, 'v2')

# 기술적 상태
ma_status = check_ma_status(df)
rsi_status = check_rsi_status(df)
vol_status = check_volume_status(df)

# 패턴 감지
obv_div = detect_obv_divergence(df)
vcp = detect_vcp_pattern(df)

print(f"\n=== {stock_name}({ticker}) 종합 신호 분석 ===\n")

# === 스코어 분석 (35%) ===
v2_score = score_result.get('score', 0)
print(f"[스코어] V2: {v2_score}")

# === 기술적 분석 (30%) ===
tech_score = 50  # 기본값

# 이평선 상태
if ma_status['status'] == 'aligned':
    tech_score += 15
elif ma_status['status'] == 'reverse_aligned':
    tech_score -= 30  # 역배열 페널티

# RSI 상태
rsi = rsi_status.get('rsi', 50)
if 40 <= rsi <= 70:
    tech_score += 10
elif rsi < 30:
    tech_score += 5  # 과매도 반등 기대
elif rsi > 80:
    tech_score -= 15

# MACD
curr = df.iloc[-1]
if curr.get('MACDh', 0) > 0:
    tech_score += 10

# 20일선 기울기
slope = ma_status.get('sma20_slope', 0)
if slope > 1:
    tech_score += 10
elif slope < -2:
    tech_score -= 15

tech_score = max(0, min(100, tech_score))
print(f"[기술적] 점수: {tech_score}")

# === 거래량/수급 (20%) ===
supply_score = 50

vol_level = vol_status.get('level', 'normal')
if vol_level == 'explosion':
    supply_score += 25
elif vol_level == 'surge':
    supply_score += 15
elif vol_level == 'high':
    supply_score += 10
elif vol_level == 'low':
    supply_score -= 10

# OBV 다이버전스
if obv_div.get('bullish_divergence'):
    supply_score += 15
elif obv_div.get('bearish_divergence'):
    supply_score -= 15

supply_score = max(0, min(100, supply_score))
print(f"[수급] 점수: {supply_score}")

# === 패턴 (15%) ===
pattern_score = 50

if vcp.get('detected'):
    pattern_score += 25
    print("  VCP 패턴 감지!")

pattern_score = max(0, min(100, pattern_score))
print(f"[패턴] 점수: {pattern_score}")

# === 종합 신호 계산 ===
total_signal = (
    v2_score * 0.35 +
    tech_score * 0.30 +
    supply_score * 0.20 +
    pattern_score * 0.15
)

# 과락 체크
knockout = False
knockout_reason = None

if v2_score == 0:
    knockout = True
    knockout_reason = "역배열 (V2=0)"
elif rsi > 85:
    knockout = True
    knockout_reason = f"극단적 과매수 (RSI={rsi:.0f})"
elif slope < -3:
    knockout = True
    knockout_reason = f"급락 추세 (기울기={slope:.1f}%)"

# 신호 결정
if knockout:
    decision = "SELL"
    confidence = 0.9
elif total_signal >= 80:
    decision = "STRONG_BUY"
    confidence = 0.85
elif total_signal >= 65:
    decision = "BUY"
    confidence = 0.70
elif total_signal >= 50:
    decision = "HOLD"
    confidence = 0.55
elif total_signal >= 35:
    decision = "WEAK_SELL"
    confidence = 0.60
else:
    decision = "SELL"
    confidence = 0.75

print(f"\n{'='*40}")
print(f"종합 신호 강도: {total_signal:.1f}")
print(f"결정: {decision}")
print(f"신뢰도: {confidence*100:.0f}%")
if knockout:
    print(f"⚠️ 과락 사유: {knockout_reason}")
print('='*40)
EOF
```

## 출력 형식 (JSON)

```json
{
  "stock_code": "005930",
  "stock_name": "삼성전자",
  "generated_at": "2026-02-02T15:30:00",
  "analysis": {
    "scoring": {
      "v2_score": 65,
      "weight": 0.35,
      "weighted_score": 22.75
    },
    "technical": {
      "score": 72,
      "weight": 0.30,
      "weighted_score": 21.6,
      "details": {
        "ma_status": "aligned",
        "rsi": 58,
        "macd_positive": true,
        "slope": 1.2
      }
    },
    "supply_demand": {
      "score": 60,
      "weight": 0.20,
      "weighted_score": 12.0,
      "details": {
        "vol_level": "normal",
        "obv_divergence": null
      }
    },
    "pattern": {
      "score": 50,
      "weight": 0.15,
      "weighted_score": 7.5,
      "detected_patterns": []
    }
  },
  "signal": {
    "total_score": 63.85,
    "decision": "HOLD",
    "confidence": 0.55,
    "knockout": null
  },
  "action_plan": {
    "entry_price": null,
    "target_price": null,
    "stop_loss": null,
    "position_size": null,
    "holding_period": null
  },
  "reasons": [
    "V2 스코어 양호 (65점)",
    "정배열 상태 유지",
    "RSI 적정 구간",
    "특별한 패턴 미감지"
  ],
  "risks": [
    "거래량 평범",
    "뚜렷한 매수 촉매 부재"
  ]
}
```

## 포지션 사이징 가이드

| 신호 | 기본 비중 | 조건별 조정 |
|------|-----------|-------------|
| STRONG_BUY | 100% | 나스닥 급락 시 50% |
| BUY | 70% | 거래량 폭발 시 +20% |
| HOLD | 기존 유지 | - |
| WEAK_SELL | 50% 매도 | - |
| SELL | 전량 매도 | - |

## 신호 유효 기간

| 신호 유형 | 유효 기간 |
|-----------|-----------|
| STRONG_BUY | 당일~3일 |
| BUY | 당일~2일 |
| HOLD | 재분석까지 |
| SELL | 즉시 |

## 관련 파일

| 파일 | 설명 |
|------|------|
| `trading/suggestion_generator.py` | 매매 제안 생성기 |
| `auto_trader.py` | 자동매매 로직 |
| `trading/risk_manager.py` | 리스크 관리 |

## 주의사항

1. **장중 vs 장마감**: 장중 신호는 변동성 고려
2. **시장 상황**: 나스닥/코스피 지수 동향 반드시 확인
3. **뉴스 체크**: 공시, 실적 발표 일정 확인
4. **포트폴리오**: 기존 보유 종목과 분산 고려
5. **손절가 필수**: 매수 시 반드시 손절가 설정
