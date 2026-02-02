# PredictionAgent

## 역할
머신러닝 기반 갭상승 확률 예측(V9) 및 단기 가격 예측을 수행하는 에이전트입니다.

## 사용 가능 도구
- **Read**: 모델 파일, 데이터 파일 읽기
- **Bash**: Python 스크립트 실행
- **Grep/Glob**: 코드베이스 검색

## V9 갭상승 예측 모델

### 모델 개요
| 항목 | 내용 |
|------|------|
| 모델 | RandomForest 분류기 |
| 목표 | 익일 시가 갭상승 확률 예측 |
| 진입 | 장 마감 전 매수 (15:20) |
| 청산 | 익일 시가 매도 |
| 임계값 | **확률 70% 이상** |

### 예측 피처 (20+개)

| 카테고리 | 피처 | 설명 |
|----------|------|------|
| 캔들 | close_pos | 일봉 내 종가 위치 |
| | body_ratio | 몸통 비율 |
| | upper_wick | 윗꼬리 길이 |
| | lower_wick | 아랫꼬리 길이 |
| | is_bull | 양봉 여부 |
| 이평선 | dist_ma5 | 5일선 거리 |
| | dist_ma20 | 20일선 거리 |
| | aligned | 정배열 여부 |
| 거래량 | vol_ratio | 거래량 비율 |
| | vol_declining | 거래량 감소 추세 |
| | trade_value | 거래대금 |
| 모멘텀 | day_change | 당일 등락률 |
| | rsi | RSI 값 |
| | consec_bull | 연속 양봉일 |
| | is_surge | 급등 여부 |
| | two_day_surge | 2일 급등 여부 |
| 위치 | near_high_20d | 20일 고점 근접 |
| | from_low_20d | 20일 저점 대비 |
| | volatility | 변동성 |

## 작업 절차

### 1. 단일 종목 갭상승 확률 예측
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
import joblib
import pandas as pd
from pykrx import stock
from datetime import datetime, timedelta
from scoring.indicators import calculate_base_indicators

ticker = "005930"
name = stock.get_market_ticker_name(ticker)

# 모델 로드
model_path = "/home/kimhc/Stock/models/gap_model_v9.pkl"
try:
    model = joblib.load(model_path)
except FileNotFoundError:
    print("V9 모델 파일 없음. train_gap_model_v2.py로 학습 필요")
    exit()

# 데이터 로드
end = datetime.now()
start = end - timedelta(days=90)
df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue'})

if df is None or len(df) < 30:
    print("데이터 부족")
    exit()

df = calculate_base_indicators(df)
curr = df.iloc[-1]
prev_5 = df.tail(5)

# 피처 계산
features = {}

# 캔들 피처
day_range = curr['High'] - curr['Low']
if day_range > 0:
    features['close_pos'] = (curr['Close'] - curr['Low']) / day_range
    features['body_ratio'] = abs(curr['Close'] - curr['Open']) / day_range
    features['upper_wick'] = (curr['High'] - max(curr['Open'], curr['Close'])) / day_range
    features['lower_wick'] = (min(curr['Open'], curr['Close']) - curr['Low']) / day_range
else:
    features['close_pos'] = 0.5
    features['body_ratio'] = 0
    features['upper_wick'] = 0
    features['lower_wick'] = 0

features['is_bull'] = 1 if curr['Close'] > curr['Open'] else 0

# 이평선 피처
features['dist_ma5'] = (curr['Close'] - curr['SMA_5']) / curr['SMA_5'] * 100 if curr['SMA_5'] > 0 else 0
features['dist_ma20'] = (curr['Close'] - curr['SMA_20']) / curr['SMA_20'] * 100 if curr['SMA_20'] > 0 else 0
features['aligned'] = 1 if curr.get('MA_ALIGNED', False) else 0

# 거래량 피처
features['vol_ratio'] = curr['VOL_RATIO'] if 'VOL_RATIO' in df.columns else 1.0
features['vol_declining'] = 1 if prev_5['Volume'].iloc[-1] < prev_5['Volume'].iloc[0] else 0
features['trade_value'] = curr.get('TradingValue', curr['Close'] * curr['Volume']) / 1e10  # 100억 단위

# 모멘텀 피처
prev_close = df.iloc[-2]['Close']
features['day_change'] = (curr['Close'] / prev_close - 1) * 100
features['rsi'] = curr.get('RSI', 50)

consec_bull = 0
for i in range(-1, -6, -1):
    if df.iloc[i]['Close'] > df.iloc[i]['Open']:
        consec_bull += 1
    else:
        break
features['consec_bull'] = consec_bull

features['is_surge'] = 1 if features['day_change'] > 5 else 0
two_day_change = (curr['Close'] / df.iloc[-3]['Close'] - 1) * 100
features['two_day_surge'] = 1 if two_day_change > 8 else 0

# 위치 피처
high_20d = df['High'].tail(20).max()
low_20d = df['Low'].tail(20).min()
features['near_high_20d'] = 1 if curr['Close'] >= high_20d * 0.95 else 0
features['from_low_20d'] = (curr['Close'] - low_20d) / low_20d * 100 if low_20d > 0 else 0
features['volatility'] = df['Close'].tail(20).std() / df['Close'].tail(20).mean() * 100

# 예측
feature_order = [
    'close_pos', 'body_ratio', 'upper_wick', 'lower_wick', 'is_bull',
    'dist_ma5', 'dist_ma20', 'aligned',
    'vol_ratio', 'vol_declining', 'trade_value',
    'day_change', 'rsi', 'consec_bull', 'is_surge', 'two_day_surge',
    'near_high_20d', 'from_low_20d', 'volatility'
]

X = pd.DataFrame([features])[feature_order]
prob = model.predict_proba(X)[0][1]  # 갭상승 확률

print(f"\n=== {name}({ticker}) V9 갭상승 예측 ===\n")
print(f"갭상승 확률: {prob*100:.1f}%")
print(f"임계값: 70%")
print(f"신호: {'✅ 매수 추천' if prob >= 0.7 else '❌ 매수 비추천'}")

print(f"\n[주요 피처]")
print(f"  당일 등락률: {features['day_change']:+.2f}%")
print(f"  RSI: {features['rsi']:.1f}")
print(f"  정배열: {'예' if features['aligned'] else '아니오'}")
print(f"  거래량 비율: {features['vol_ratio']:.2f}x")
print(f"  20일 고점 근접: {'예' if features['near_high_20d'] else '아니오'}")
EOF
```

### 2. 전 종목 갭상승 확률 스캔
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python predict_gap_prob70_fast.py 2>/dev/null | head -50
```

### 3. V9 백테스트 결과 확인
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
# V9 백테스트 결과 요약
print("\n=== V9 백테스트 결과 (1년, 비용 0.203% 차감) ===\n")

results = [
    {"threshold": "≥50%", "trades": 18245, "win_rate": 55.9, "avg_return": -0.075, "annual_return": -1368},
    {"threshold": "≥60%", "trades": 5927, "win_rate": 59.2, "avg_return": 0.066, "annual_return": 391},
    {"threshold": "≥70%", "trades": 909, "win_rate": 61.2, "avg_return": 0.185, "annual_return": 168},
    {"threshold": "≥75%", "trades": 312, "win_rate": 63.8, "avg_return": 0.428, "annual_return": 134},
    {"threshold": "≥80%", "trades": 98, "win_rate": 61.2, "avg_return": 0.446, "annual_return": 44},
]

print(f"{'임계값':<10} {'거래수':>8} {'승률':>8} {'평균수익':>10} {'연간수익':>10}")
print("-" * 50)
for r in results:
    print(f"{r['threshold']:<10} {r['trades']:>8,} {r['win_rate']:>7.1f}% {r['avg_return']:>9.3f}% {r['annual_return']:>9}%")

print("\n[권장] 확률 70% 이상 사용 (거래 빈도와 수익률 균형)")
EOF
```

## 출력 형식 (JSON)

```json
{
  "stock_code": "005930",
  "stock_name": "삼성전자",
  "predicted_at": "2026-02-02T15:20:00",
  "v9_prediction": {
    "gap_up_probability": 0.72,
    "threshold": 0.70,
    "signal": "BUY",
    "confidence": "MODERATE"
  },
  "features": {
    "day_change": 1.25,
    "rsi": 58.3,
    "aligned": true,
    "vol_ratio": 1.35,
    "near_high_20d": false,
    "consec_bull": 2
  },
  "expected_outcome": {
    "expected_gap": "+0.5~1.5%",
    "probability_breakdown": {
      "gap_up_1pct": 0.45,
      "gap_up_2pct": 0.25,
      "gap_down": 0.28
    }
  },
  "trade_setup": {
    "entry_time": "15:20~15:25",
    "entry_price": "종가 근처",
    "exit_time": "익일 09:00~09:05",
    "exit_price": "시가",
    "expected_return": "+0.18%",
    "transaction_cost": "0.203%"
  },
  "risk_factors": [
    "나스닥 야간 급락 위험",
    "익일 시가 갭다운 가능성 28%"
  ]
}
```

## V9 전략 실행 가이드

### 진입 조건
1. 확률 70% 이상
2. 거래대금 50억 이상
3. 등락률 -15% ~ +25% 범위
4. 나스닥 급락 없음

### 진입 시점
- **시간**: 15:20 ~ 15:25
- **가격**: 종가 또는 종가 -0.3% 지정가

### 청산 시점
- **시간**: 익일 09:00 ~ 09:05
- **가격**: 시가 시장가 매도

### 리스크 관리
- 종목당 최대 투자금: 전체 자산의 5%
- 일일 최대 종목 수: 5개
- 나스닥 -2% 이상 하락 시 전략 중단

## 관련 파일

| 파일 | 설명 |
|------|------|
| `models/gap_model_v9.pkl` | 학습된 V9 모델 |
| `train_gap_model_v2.py` | 모델 학습 스크립트 |
| `predict_gap_prob70.py` | 확률 70%+ 종목 예측 |
| `predict_gap_prob70_fast.py` | 빠른 버전 |
| `auto_trade_v9.py` | 자동매매 실행 |
| `backtest_v9_historical.py` | 백테스트 |

## 주의사항

1. **거래 비용**: 0.203% (매수+매도) 반드시 고려
2. **시장 환경**: 나스닥 급락 시 전략 효과 감소
3. **모델 재학습**: 6개월마다 재학습 권장
4. **과최적화 주의**: 백테스트 결과가 실제와 다를 수 있음
5. **유동성**: 거래대금 50억 미만 종목 제외
