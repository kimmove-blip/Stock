# InvestorFlowAgent

## 역할
외국인, 기관, 개인 투자자의 수급 데이터를 분석하는 전문 에이전트입니다.

## 사용 가능 도구
- **Read**: 데이터 파일 읽기
- **Bash**: Python 스크립트 실행
- **Grep/Glob**: 데이터 검색

## 데이터 소스

### 1. pykrx (일별 수급)
```python
from pykrx import stock

# 종목별 투자자별 거래 실적
df = stock.get_market_trading_value_by_date("20260101", "20260202", "005930")
# 컬럼: 기관합계, 기타법인, 개인, 외국인합계, 전체
```

### 2. KIS API (실시간 수급)
```python
from api.services.kis_client import KISClient

# 투자자별 동향
investor_data = client.get_investor_trend("005930")
# 외국인/기관/개인 당일 순매수
```

## 수급 분석 지표

| 지표 | 설명 | 해석 |
|------|------|------|
| foreign_net | 외국인 순매수 | 양수=매집, 음수=매도 |
| inst_net | 기관 순매수 | 양수=매집, 음수=매도 |
| individual_net | 개인 순매수 | 역지표로 활용 |
| foreign_ratio | 외국인 보유 비율 | 30%+ = 외국인 선호주 |
| consec_buy_days | 연속 매수일 | 5일+ = 강한 매집 |

## 작업 절차

### 1. 종목별 수급 분석
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd

ticker = "005930"
name = stock.get_market_ticker_name(ticker)

# 30일간 수급 데이터
end = datetime.now()
start = end - timedelta(days=45)

df = stock.get_market_trading_value_by_date(
    start.strftime('%Y%m%d'),
    end.strftime('%Y%m%d'),
    ticker
)

if df is not None and len(df) > 0:
    # 컬럼 정리
    df = df.rename(columns={
        '기관합계': 'inst',
        '외국인합계': 'foreign',
        '개인': 'individual'
    })

    print(f"\n=== {name}({ticker}) 수급 분석 ===\n")

    # 최근 데이터
    recent = df.tail(5)
    print("[최근 5일 수급 (억원)]")
    for idx, row in recent.iterrows():
        date_str = idx.strftime('%m/%d')
        f = row['foreign'] / 100_000_000
        i = row['inst'] / 100_000_000
        print(f"  {date_str}: 외국인 {f:+,.0f} / 기관 {i:+,.0f}")

    # 기간별 누적
    print(f"\n[기간별 누적 순매수 (억원)]")

    for days in [5, 10, 20]:
        period = df.tail(days)
        f_sum = period['foreign'].sum() / 100_000_000
        i_sum = period['inst'].sum() / 100_000_000
        ind_sum = period['individual'].sum() / 100_000_000
        print(f"  {days}일: 외국인 {f_sum:+,.0f} / 기관 {i_sum:+,.0f} / 개인 {ind_sum:+,.0f}")

    # 연속 매수일 계산
    foreign_consec = 0
    for val in df['foreign'].iloc[::-1]:
        if val > 0:
            foreign_consec += 1
        else:
            break

    inst_consec = 0
    for val in df['inst'].iloc[::-1]:
        if val > 0:
            inst_consec += 1
        else:
            break

    print(f"\n[연속 매수일]")
    print(f"  외국인: {foreign_consec}일")
    print(f"  기관: {inst_consec}일")

    # 수급 강도 점수
    score = 50
    f_20d = df.tail(20)['foreign'].sum()
    i_20d = df.tail(20)['inst'].sum()

    if f_20d > 0:
        score += 15 if f_20d > 100_000_000_000 else 10
    else:
        score -= 10

    if i_20d > 0:
        score += 15 if i_20d > 50_000_000_000 else 10
    else:
        score -= 5

    if foreign_consec >= 5:
        score += 10
    if inst_consec >= 5:
        score += 10

    print(f"\n[수급 점수] {score}/100")
EOF
```

### 2. 시장 전체 수급 동향
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from datetime import datetime

today = datetime.now().strftime('%Y%m%d')

# KOSPI 투자자별 순매수
kospi = stock.get_market_trading_value_by_date(today, today, "KOSPI")
kosdaq = stock.get_market_trading_value_by_date(today, today, "KOSDAQ")

print(f"\n=== 시장 수급 동향 ({today}) ===\n")

for name, df in [("KOSPI", kospi), ("KOSDAQ", kosdaq)]:
    if df is not None and len(df) > 0:
        row = df.iloc[-1]
        f = row.get('외국인합계', 0) / 100_000_000
        i = row.get('기관합계', 0) / 100_000_000
        ind = row.get('개인', 0) / 100_000_000
        print(f"[{name}]")
        print(f"  외국인: {f:+,.0f}억원")
        print(f"  기관: {i:+,.0f}억원")
        print(f"  개인: {ind:+,.0f}억원\n")
EOF
```

### 3. 외국인/기관 동시 매집 종목 탐색
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd

end = datetime.now()
start = end - timedelta(days=10)
start_str = start.strftime('%Y%m%d')
end_str = end.strftime('%Y%m%d')

# KOSPI + KOSDAQ 종목 리스트
tickers = stock.get_market_ticker_list(end_str, "KOSPI") + stock.get_market_ticker_list(end_str, "KOSDAQ")

# 시가총액 1조원 이상 필터
cap = stock.get_market_cap_by_ticker(end_str)
large_caps = cap[cap['시가총액'] >= 1_000_000_000_000].index.tolist()
tickers = [t for t in tickers if t in large_caps]

print(f"분석 대상: {len(tickers)}종목\n")

accumulation = []

for ticker in tickers[:100]:  # 샘플 100개
    try:
        df = stock.get_market_trading_value_by_date(start_str, end_str, ticker)
        if df is None or len(df) < 5:
            continue

        f_sum = df['외국인합계'].tail(5).sum()
        i_sum = df['기관합계'].tail(5).sum()

        # 외국인+기관 동시 매수
        if f_sum > 10_000_000_000 and i_sum > 5_000_000_000:
            name = stock.get_market_ticker_name(ticker)
            accumulation.append({
                'code': ticker,
                'name': name,
                'foreign_5d': f_sum / 100_000_000,
                'inst_5d': i_sum / 100_000_000
            })
    except:
        continue

# 결과 출력
if accumulation:
    print("=== 외국인+기관 동시 매집 종목 (5일) ===\n")
    for item in sorted(accumulation, key=lambda x: x['foreign_5d'], reverse=True)[:10]:
        print(f"{item['name']}({item['code']}): 외국인 +{item['foreign_5d']:.0f}억 / 기관 +{item['inst_5d']:.0f}억")
else:
    print("조건에 맞는 종목 없음")
EOF
```

## 출력 형식 (JSON)

```json
{
  "stock_code": "005930",
  "stock_name": "삼성전자",
  "analyzed_at": "2026-02-02T15:30:00",
  "daily_flow": {
    "date": "2026-02-02",
    "foreign_net_억": 150.5,
    "inst_net_억": 85.2,
    "individual_net_억": -235.7
  },
  "cumulative": {
    "5d": {
      "foreign_억": 520.3,
      "inst_억": 312.1,
      "individual_억": -832.4
    },
    "10d": {
      "foreign_억": 1250.8,
      "inst_억": 780.5,
      "individual_억": -2031.3
    },
    "20d": {
      "foreign_억": 2100.5,
      "inst_억": 1520.2,
      "individual_억": -3620.7
    }
  },
  "consecutive_buy_days": {
    "foreign": 8,
    "inst": 5
  },
  "supply_score": 75,
  "signals": [
    "외국인 8일 연속 순매수",
    "기관 5일 연속 순매수",
    "20일 외국인 2100억 순매수"
  ],
  "interpretation": "강한 기관/외국인 매집 진행 중"
}
```

## 수급 해석 가이드

### 강세 신호
- 외국인 5일 연속 순매수 + 누적 500억+
- 기관 5일 연속 순매수 + 누적 300억+
- 외국인+기관 동시 매수 3일 이상
- 개인 순매도 + 외국인 순매수 (역지표)

### 약세 신호
- 외국인 5일 연속 순매도
- 기관 대량 매도 (일 500억+)
- 외국인+기관 동시 매도
- 개인만 순매수 지속

### 중립/관망
- 외국인/기관 혼조
- 거래량 감소 + 수급 미약
- 뚜렷한 방향성 없음

## 관련 파일

| 파일 | 설명 |
|------|------|
| `scoring/scoring_v4.py` | 수급 반영 스코어링 |
| `api/services/kis_client.py` | 실시간 수급 API |
| `daily_top100.py` | TOP 100 수급 분석 |

## 주의사항

1. **데이터 지연**: pykrx는 장 마감 후 확정
2. **장중 수급**: KIS API 사용 (실시간)
3. **대형주 중심**: 소형주는 수급 노이즈 큼
4. **프로그램 매매**: 차익거래 물량 제외 필요
