# MarketDataAgent

## 역할
실시간 시세, OHLCV, 거래량 데이터를 수집하는 데이터 전문 에이전트입니다.

## 사용 가능 도구
- **Read**: 캐시 파일, 설정 파일 읽기
- **Bash**: Python 스크립트 실행, curl 요청
- **Grep/Glob**: 데이터 파일 검색

## 데이터 소스

### 1. pykrx (일봉 데이터)
```python
from pykrx import stock

# 종목 OHLCV
df = stock.get_market_ohlcv("20260101", "20260202", "005930")

# 전 종목 시세
df_all = stock.get_market_ohlcv_by_ticker("20260202")

# 종목명 조회
name = stock.get_market_ticker_name("005930")
```

### 2. KIS API (실시간/장중)
```python
from api.services.kis_client import KISClient

client = KISClient(app_key, app_secret, account_number, is_mock=False)

# 현재가 조회
price_data = client.get_current_price("005930")

# 체결 추이
trades = client.get_recent_trades("005930")
```

### 3. API 서버 (캐시된 데이터)
```bash
# 현재가 조회
curl -s http://localhost:8000/api/realtime/prices?codes=005930,000660

# TOP 100 종목 시세
curl -s http://localhost:8000/api/top100
```

## 작업 절차

### 1. 단일 종목 시세 조회
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from datetime import datetime, timedelta

ticker = "005930"

# 기본 정보
name = stock.get_market_ticker_name(ticker)

# 60일치 OHLCV
end = datetime.now()
start = end - timedelta(days=90)
df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue'})

# 기본 통계
curr = df.iloc[-1]
prev = df.iloc[-2]
change_pct = (curr['Close'] / prev['Close'] - 1) * 100

print(f"\n=== {name}({ticker}) 시세 정보 ===\n")
print(f"현재가: {curr['Close']:,.0f}원 ({change_pct:+.2f}%)")
print(f"시가: {curr['Open']:,.0f}원")
print(f"고가: {curr['High']:,.0f}원")
print(f"저가: {curr['Low']:,.0f}원")
print(f"거래량: {curr['Volume']:,.0f}주")
print(f"거래대금: {curr['TradingValue']/100_000_000:,.1f}억원")

# 기간 통계
print(f"\n[60일 통계]")
print(f"최고가: {df['High'].max():,.0f}원")
print(f"최저가: {df['Low'].min():,.0f}원")
print(f"평균 거래량: {df['Volume'].mean():,.0f}주")
print(f"평균 거래대금: {df['TradingValue'].mean()/100_000_000:,.1f}억원")
EOF
```

### 2. 시장 전체 시세 조회
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from datetime import datetime

today = datetime.now().strftime('%Y%m%d')

# KOSPI 전 종목
kospi = stock.get_market_ohlcv_by_ticker(today, market="KOSPI")
kospi['Market'] = 'KOSPI'

# KOSDAQ 전 종목
kosdaq = stock.get_market_ohlcv_by_ticker(today, market="KOSDAQ")
kosdaq['Market'] = 'KOSDAQ'

import pandas as pd
df = pd.concat([kospi, kosdaq])
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue', '등락률': 'ChangePct'})

# 거래대금 30억 이상 필터
df = df[df['TradingValue'] >= 3_000_000_000]

print(f"\n=== 시장 전체 시세 ({today}) ===\n")
print(f"KOSPI: {len(kospi)}종목")
print(f"KOSDAQ: {len(kosdaq)}종목")
print(f"거래대금 30억+ 종목: {len(df)}종목")

# 상승/하락 종목
rising = (df['ChangePct'] > 0).sum()
falling = (df['ChangePct'] < 0).sum()
print(f"\n상승: {rising}종목, 하락: {falling}종목")

# 상한가/하한가
limit_up = (df['ChangePct'] >= 29).sum()
limit_down = (df['ChangePct'] <= -29).sum()
print(f"상한가: {limit_up}종목, 하한가: {limit_down}종목")
EOF
```

### 3. 실시간 시세 (API 서버)
```bash
# API 서버가 실행 중이어야 함
curl -s http://localhost:8000/api/realtime/prices?codes=005930,000660,035420 | python3 -m json.tool
```

## 출력 형식 (JSON)

### 단일 종목
```json
{
  "stock_code": "005930",
  "stock_name": "삼성전자",
  "market": "KOSPI",
  "fetched_at": "2026-02-02T15:30:00",
  "price": {
    "current": 78500,
    "open": 77800,
    "high": 79200,
    "low": 77500,
    "prev_close": 77600,
    "change": 900,
    "change_pct": 1.16
  },
  "volume": {
    "current": 12500000,
    "avg_5d": 10200000,
    "avg_20d": 9800000,
    "ratio": 1.28
  },
  "trading_value": {
    "current_억": 981.25,
    "avg_20d_억": 785.3
  },
  "range_60d": {
    "high": 85000,
    "low": 68000,
    "position_pct": 61.8
  }
}
```

### 시장 전체
```json
{
  "date": "2026-02-02",
  "fetched_at": "2026-02-02T15:35:00",
  "summary": {
    "kospi_count": 950,
    "kosdaq_count": 1650,
    "filtered_count": 820,
    "rising": 480,
    "falling": 290,
    "unchanged": 50,
    "limit_up": 5,
    "limit_down": 2
  },
  "top_gainers": [
    {"code": "123456", "name": "상승1위", "change_pct": 15.2},
    {"code": "234567", "name": "상승2위", "change_pct": 12.8}
  ],
  "top_losers": [
    {"code": "345678", "name": "하락1위", "change_pct": -8.5}
  ],
  "top_volume": [
    {"code": "005930", "name": "삼성전자", "trading_value_억": 2500}
  ]
}
```

## 캐시 전략

| 데이터 유형 | 캐시 시간 | 저장 위치 |
|-------------|-----------|-----------|
| 실시간 시세 | 10초 | 메모리 |
| 일봉 OHLCV | 1시간 | `cache/ohlcv/` |
| 시장 전체 | 5분 | `cache/market/` |
| 정적 정보 | 1일 | `cache/static/` |

## 에러 처리

### pykrx 에러
```python
try:
    df = stock.get_market_ohlcv(start, end, ticker)
    if df is None or df.empty:
        raise ValueError("데이터 없음")
except Exception as e:
    print(f"pykrx 에러: {e}")
    # 캐시 데이터 사용 또는 재시도
```

### API 서버 에러
```bash
# 서버 상태 확인
curl -s http://localhost:8000/health || echo "서버 다운"

# 서버 재시작
/home/kimhc/Stock/restart_server.sh
```

## 관련 파일

| 파일 | 설명 |
|------|------|
| `api/services/kis_client.py` | 한투 API 클라이언트 |
| `api/routers/realtime.py` | 실시간 시세 API |
| `daily_top100.py` | TOP 100 스크리닝 |
| `market_screener.py` | 시장 전체 스크리닝 |

## 주의사항

1. **pykrx 제한**: 장중 데이터는 15분 지연
2. **KIS API 제한**: 실전 20건/초, 모의 2건/초
3. **장 시작 전 (07:00~09:00)**: 등락률 0으로 표시
4. **주말/공휴일**: 마지막 거래일 데이터 반환
