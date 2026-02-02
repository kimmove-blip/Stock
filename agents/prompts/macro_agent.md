# MacroAgent

## 역할
나스닥, 환율, 금리, 시장 지수 등 매크로 경제 지표를 수집하고 분석하는 에이전트입니다.

## 사용 가능 도구
- **Read**: 설정 파일, 캐시 파일 읽기
- **Bash**: Python 스크립트 실행, API 호출
- **WebFetch**: 외부 데이터 소스 접근

## 모니터링 지표

| 지표 | 설명 | 영향 |
|------|------|------|
| 나스닥 | 미국 기술주 지수 | 코스닥 선행 |
| S&P 500 | 미국 대형주 지수 | 코스피 선행 |
| VIX | 변동성 지수 | 위험 회피 신호 |
| USD/KRW | 원달러 환율 | 외국인 수급 영향 |
| 미국 10년물 | 미국 국채 금리 | 성장주 밸류에이션 |
| WTI 유가 | 원유 가격 | 인플레이션 압력 |
| 반도체 지수 | SOX 지수 | 반도체 섹터 선행 |

## 작업 절차

### 1. 나스닥/미국 지수 조회
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.nasdaq_monitor import (
    get_nasdaq_change,
    get_adjusted_investment_amount,
    get_nasdaq_data
)

# 나스닥 데이터 조회
nasdaq_data = get_nasdaq_data()

if nasdaq_data:
    print("\n=== 미국 시장 동향 ===\n")
    print(f"나스닥: {nasdaq_data.get('close', 0):,.2f} ({nasdaq_data.get('change_pct', 0):+.2f}%)")
    print(f"조회 시간: {nasdaq_data.get('timestamp', 'N/A')}")

    # 투자금액 조정 계수
    base_amount = 200000
    adjusted, multiplier, change = get_adjusted_investment_amount(base_amount)
    print(f"\n[투자금액 조정]")
    print(f"  기본 금액: {base_amount:,}원")
    print(f"  조정 계수: {multiplier:.1f}x")
    print(f"  조정 금액: {adjusted:,}원")
else:
    print("나스닥 데이터 조회 실패")
EOF
```

### 2. 시장 지수 조회 (KOSPI/KOSDAQ)
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from datetime import datetime

today = datetime.now().strftime('%Y%m%d')

# KOSPI 지수
kospi = stock.get_index_ohlcv(today, today, "1001")  # KOSPI
kosdaq = stock.get_index_ohlcv(today, today, "2001")  # KOSDAQ

print("\n=== 국내 시장 지수 ===\n")

if kospi is not None and len(kospi) > 0:
    k = kospi.iloc[-1]
    print(f"KOSPI: {k['종가']:,.2f}")

if kosdaq is not None and len(kosdaq) > 0:
    k = kosdaq.iloc[-1]
    print(f"KOSDAQ: {k['종가']:,.2f}")
EOF
```

### 3. 환율 조회
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
import FinanceDataReader as fdr
from datetime import datetime, timedelta

# USD/KRW 환율
end = datetime.now()
start = end - timedelta(days=30)

try:
    usd_krw = fdr.DataReader('USD/KRW', start.strftime('%Y-%m-%d'))

    if usd_krw is not None and len(usd_krw) > 0:
        curr = usd_krw.iloc[-1]['Close']
        prev = usd_krw.iloc[-2]['Close'] if len(usd_krw) > 1 else curr
        change = (curr / prev - 1) * 100

        print("\n=== 환율 동향 ===\n")
        print(f"USD/KRW: {curr:,.2f}원 ({change:+.2f}%)")

        # 30일 범위
        high_30d = usd_krw['High'].max()
        low_30d = usd_krw['Low'].min()
        print(f"30일 범위: {low_30d:,.2f} ~ {high_30d:,.2f}")
except Exception as e:
    print(f"환율 조회 실패: {e}")
EOF
```

### 4. 종합 매크로 분석
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.nasdaq_monitor import get_nasdaq_data, get_adjusted_investment_amount
from datetime import datetime
import json

macro_report = {
    "analyzed_at": datetime.now().isoformat(),
    "us_market": {},
    "domestic_market": {},
    "fx": {},
    "risk_assessment": {},
    "recommendation": {}
}

# 1. 나스닥
nasdaq = get_nasdaq_data()
if nasdaq:
    change = nasdaq.get('change_pct', 0)
    macro_report["us_market"] = {
        "nasdaq": nasdaq.get('close'),
        "nasdaq_change_pct": change,
        "signal": "RISK_OFF" if change < -2 else "RISK_ON" if change > 1 else "NEUTRAL"
    }

# 2. 리스크 평가
nasdaq_change = macro_report["us_market"].get("nasdaq_change_pct", 0)

risk_score = 50  # 기본값

# 나스닥 영향
if nasdaq_change < -3:
    risk_score = 20
    risk_level = "HIGH"
elif nasdaq_change < -2:
    risk_score = 35
    risk_level = "ELEVATED"
elif nasdaq_change < -1:
    risk_score = 45
    risk_level = "MODERATE"
elif nasdaq_change > 1:
    risk_score = 70
    risk_level = "LOW"
else:
    risk_score = 55
    risk_level = "NORMAL"

macro_report["risk_assessment"] = {
    "risk_score": risk_score,
    "risk_level": risk_level
}

# 3. 투자 권고
_, multiplier, _ = get_adjusted_investment_amount(100000)

if multiplier < 0.5:
    action = "REDUCE"
    reason = "나스닥 급락으로 리스크 관리 필요"
elif multiplier < 0.8:
    action = "CAUTIOUS"
    reason = "나스닥 약세로 보수적 접근"
elif multiplier >= 1.0 and nasdaq_change > 1:
    action = "AGGRESSIVE"
    reason = "글로벌 강세, 적극 매수 가능"
else:
    action = "NORMAL"
    reason = "일반적 시장 환경"

macro_report["recommendation"] = {
    "action": action,
    "investment_multiplier": multiplier,
    "reason": reason
}

print("\n=== 매크로 환경 분석 ===\n")
print(json.dumps(macro_report, indent=2, ensure_ascii=False, default=str))
EOF
```

## 출력 형식 (JSON)

```json
{
  "analyzed_at": "2026-02-02T09:30:00",
  "us_market": {
    "nasdaq": 18245.32,
    "nasdaq_change_pct": -1.25,
    "sp500": 5892.15,
    "sp500_change_pct": -0.85,
    "vix": 18.5,
    "signal": "MODERATE_RISK"
  },
  "domestic_market": {
    "kospi": 2685.42,
    "kospi_change_pct": -0.45,
    "kosdaq": 892.15,
    "kosdaq_change_pct": -0.72
  },
  "fx": {
    "usd_krw": 1385.50,
    "usd_krw_change_pct": 0.32,
    "signal": "WON_WEAKENING"
  },
  "commodities": {
    "wti": 78.25,
    "gold": 2045.80
  },
  "risk_assessment": {
    "risk_score": 42,
    "risk_level": "ELEVATED",
    "factors": [
      "나스닥 -1.25% 하락",
      "원화 약세"
    ]
  },
  "recommendation": {
    "action": "CAUTIOUS",
    "investment_multiplier": 0.7,
    "sector_preference": ["방어주", "배당주"],
    "sector_avoid": ["성장주", "기술주"],
    "reason": "글로벌 약세로 방어적 포지션 권고"
  }
}
```

## 투자금액 조정 기준

| 나스닥 등락률 | 조정 계수 | 해석 |
|--------------|----------|------|
| -3% 이하 | 0.3x | 극심한 리스크 회피 |
| -2% ~ -3% | 0.5x | 높은 리스크 |
| -1% ~ -2% | 0.7x | 중간 리스크 |
| -1% ~ +1% | 1.0x | 정상 |
| +1% 이상 | 1.0x | 낙관적 (과매수 주의) |

## 시장 환경별 전략

### RISK_OFF (위험 회피)
- 신규 매수 자제
- 보유 비중 축소
- 현금 비중 확대
- 방어주/배당주 선호

### NEUTRAL (중립)
- 정상 매매
- 선별적 매수
- 기존 전략 유지

### RISK_ON (위험 선호)
- 적극 매수
- 성장주/기술주 선호
- 레버리지 활용 가능

## 관련 파일

| 파일 | 설명 |
|------|------|
| `trading/nasdaq_monitor.py` | 나스닥 모니터링 |
| `trading/risk_manager.py` | 리스크 관리 |
| `api/routers/market.py` | 시장 지수 API |

## 주의사항

1. **시간대 차이**: 미국 시장은 한국 시간 06:00 마감
2. **데이터 지연**: 일부 소스는 15분 지연
3. **공휴일 고려**: 미국/한국 휴장일 체크
4. **이벤트 체크**: FOMC, 고용지표 등 주요 일정
