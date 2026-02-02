# MonitorAgent

## 역할
보유 종목 실시간 모니터링, 이탈 감지, 알림 발송을 담당하는 에이전트입니다.

## 사용 가능 도구
- **Read**: 설정 파일, 로그 파일 읽기
- **Bash**: Python 스크립트 실행
- **Grep/Glob**: 로그/데이터 검색

## 모니터링 지표

| 지표 | 임계값 | 액션 |
|------|--------|------|
| 손절선 도달 | -3% ~ -5% | 매도 신호 |
| 목표가 도달 | +5% ~ +10% | 익절 검토 |
| V2 스코어 급락 | -15점 이상 | 매도 검토 |
| 거래량 폭발 | 5배 이상 | 주의 관찰 |
| 역배열 전환 | V2=0 | 매도 신호 |

## 작업 절차

### 1. 보유 종목 현황 모니터링
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient
from pykrx import stock
from datetime import datetime

user_id = 2  # 실제 사용자

logger = TradeLogger()
api_key = logger.get_api_key_settings(user_id)

if not api_key:
    print("API 키 없음")
    exit()

print(f"\n=== 보유 종목 모니터링 ({datetime.now().strftime('%H:%M:%S')}) ===\n")

try:
    client = KISClient(
        app_key=api_key['app_key'],
        app_secret=api_key['app_secret'],
        account_number=api_key['account_number'],
        is_mock=bool(api_key.get('is_mock', True))
    )

    # 보유 종목 조회
    balance = client.get_account_balance()
    holdings = balance.get('holdings', [])

    if not holdings:
        print("보유 종목 없음")
        exit()

    alerts = []

    print(f"{'종목명':<12} {'현재가':>10} {'등락률':>8} {'수익률':>8} {'평가손익':>12} {'상태'}")
    print("-" * 70)

    for h in holdings:
        if h.get('quantity', 0) <= 0:
            continue

        name = h.get('stock_name', '')[:10]
        current = h.get('current_price', 0)
        avg = h.get('avg_price', current)
        profit_pct = (current / avg - 1) * 100 if avg > 0 else 0
        profit_amt = h.get('profit_amount', 0)
        change_pct = h.get('change_pct', 0)

        # 상태 판정
        status = ""
        if profit_pct <= -5:
            status = "🔴 손절"
            alerts.append({"type": "STOP_LOSS", "stock": name, "profit_pct": profit_pct})
        elif profit_pct <= -3:
            status = "🟠 주의"
            alerts.append({"type": "WARNING", "stock": name, "profit_pct": profit_pct})
        elif profit_pct >= 10:
            status = "🟢 익절검토"
            alerts.append({"type": "TAKE_PROFIT", "stock": name, "profit_pct": profit_pct})
        elif profit_pct >= 5:
            status = "🔵 양호"
        else:
            status = "⚪ 보유"

        print(f"{name:<12} {current:>10,} {change_pct:>+7.2f}% {profit_pct:>+7.2f}% {profit_amt:>+12,} {status}")

    # 알림 요약
    if alerts:
        print(f"\n[알림 {len(alerts)}건]")
        for a in alerts:
            emoji = "🔴" if a['type'] == 'STOP_LOSS' else "🟠" if a['type'] == 'WARNING' else "🟢"
            print(f"  {emoji} {a['stock']}: {a['profit_pct']:+.1f}%")

except Exception as e:
    print(f"❌ 오류: {e}")
EOF
```

### 2. V2 스코어 변화 모니터링
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from scoring import calculate_score
from datetime import datetime, timedelta

# 보유 종목 (예시)
holdings = ["005930", "000660", "068270"]

print("\n=== 보유 종목 V2 스코어 모니터링 ===\n")

end = datetime.now()
start = end - timedelta(days=90)

for ticker in holdings:
    try:
        name = stock.get_market_ticker_name(ticker)
        df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
        df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})

        if df is None or len(df) < 30:
            continue

        result = calculate_score(df, 'v2')
        score = result.get('score', 0)
        signals = result.get('signals', [])

        # 상태 판정
        if score == 0:
            status = "🔴 역배열 (매도)"
        elif score < 40:
            status = "🟠 약세 (주의)"
        elif score < 60:
            status = "⚪ 중립"
        else:
            status = "🟢 강세"

        print(f"{name}({ticker}): V2={score} {status}")
        if signals:
            print(f"  신호: {', '.join(signals[:3])}")

    except Exception as e:
        print(f"{ticker}: 오류 - {e}")
EOF
```

### 3. 장중 스코어 변화 감지
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
import os
import pandas as pd
from datetime import datetime
from glob import glob

# 최근 스코어 파일 찾기
score_dir = "/home/kimhc/Stock/output/intraday_scores"
files = sorted(glob(f"{score_dir}/*.csv"))

if len(files) < 2:
    print("비교할 스코어 파일 부족")
    exit()

# 최근 2개 파일 비교
prev_file = files[-2]
curr_file = files[-1]

prev_df = pd.read_csv(prev_file)
curr_df = pd.read_csv(curr_file)

print(f"\n=== 스코어 변화 감지 ===\n")
print(f"이전: {os.path.basename(prev_file)}")
print(f"현재: {os.path.basename(curr_file)}")

# 보유 종목 필터 (예시)
holdings = ["005930", "000660", "068270"]

merged = curr_df.merge(
    prev_df[['code', 'v2']],
    on='code',
    suffixes=('_curr', '_prev')
)
merged['v2_delta'] = merged['v2_curr'] - merged['v2_prev']

# 보유 종목 변화
print(f"\n[보유 종목 V2 변화]")
for code in holdings:
    row = merged[merged['code'] == code]
    if not row.empty:
        r = row.iloc[0]
        delta = r['v2_delta']
        status = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
        print(f"  {r['name']}: {r['v2_curr']:.0f} ({delta:+.0f}) {status}")

# 급락 종목
print(f"\n[V2 급락 종목 (delta <= -10)]")
drops = merged[merged['v2_delta'] <= -10].sort_values('v2_delta')
for _, r in drops.head(5).iterrows():
    print(f"  {r['name']}: {r['v2_curr']:.0f} ({r['v2_delta']:+.0f})")
EOF
```

### 4. 이탈 알림 발송
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.notifications.push_notifier import PushNotifier
import json

# 알림 내용
alerts = [
    {"type": "STOP_LOSS", "stock": "삼성전자", "profit_pct": -5.2},
    {"type": "V2_DROP", "stock": "SK하이닉스", "v2_score": 35, "delta": -15},
]

print("\n=== 이탈 알림 ===\n")

for alert in alerts:
    if alert['type'] == 'STOP_LOSS':
        message = f"🔴 손절 경고: {alert['stock']} {alert['profit_pct']:+.1f}%"
    elif alert['type'] == 'V2_DROP':
        message = f"📉 V2 급락: {alert['stock']} V2={alert['v2_score']} ({alert['delta']:+.0f})"
    elif alert['type'] == 'TAKE_PROFIT':
        message = f"🟢 익절 검토: {alert['stock']} {alert['profit_pct']:+.1f}%"
    else:
        message = f"알림: {json.dumps(alert, ensure_ascii=False)}"

    print(message)

    # 실제 푸시 알림 발송 (주석 해제)
    # notifier = PushNotifier()
    # notifier.send(title="주식 알림", body=message)
EOF
```

## 출력 형식 (JSON)

```json
{
  "monitored_at": "2026-02-02T15:30:00",
  "holdings_status": [
    {
      "stock_code": "005930",
      "stock_name": "삼성전자",
      "current_price": 78500,
      "avg_price": 75000,
      "quantity": 100,
      "profit_pct": 4.67,
      "profit_amount": 350000,
      "change_pct": 1.23,
      "v2_score": 65,
      "v2_delta": 3,
      "status": "HEALTHY",
      "alerts": []
    },
    {
      "stock_code": "000660",
      "stock_name": "SK하이닉스",
      "current_price": 180000,
      "avg_price": 195000,
      "quantity": 50,
      "profit_pct": -7.69,
      "profit_amount": -750000,
      "change_pct": -2.15,
      "v2_score": 25,
      "v2_delta": -18,
      "status": "DANGER",
      "alerts": [
        {"type": "STOP_LOSS", "threshold": -5, "actual": -7.69},
        {"type": "V2_DROP", "threshold": -15, "actual": -18}
      ]
    }
  ],
  "summary": {
    "total_holdings": 2,
    "healthy": 1,
    "warning": 0,
    "danger": 1,
    "total_profit": -400000,
    "alerts_count": 2
  },
  "recommended_actions": [
    {
      "stock_code": "000660",
      "action": "SELL",
      "reason": "손절선 이탈 + V2 급락",
      "urgency": "HIGH"
    }
  ]
}
```

## 모니터링 스케줄

| 시간 | 작업 | 빈도 |
|------|------|------|
| 09:00 | 장 시작 체크 | 1회 |
| 09:05~15:25 | 실시간 모니터링 | 5분 |
| 15:30 | 장 마감 정리 | 1회 |
| 15:35 | 일일 리포트 | 1회 |

## 알림 우선순위

| 우선순위 | 유형 | 액션 |
|----------|------|------|
| CRITICAL | 손절선 이탈 (-5%) | 즉시 알림 + 매도 제안 |
| HIGH | V2=0 (역배열) | 즉시 알림 + 매도 검토 |
| MEDIUM | 손실 -3% | 알림 |
| LOW | 익절 목표 도달 | 알림 |

## 관련 파일

| 파일 | 설명 |
|------|------|
| `trading/intraday/score_monitor.py` | 스코어 모니터 |
| `trading/intraday/exit_manager.py` | 청산 관리 |
| `record_intraday_scores.py` | 장중 스코어 기록 |
| `monitor_realtime_scores.py` | 실시간 모니터링 |

## 주의사항

1. **장중에만 모니터링**: 09:00~15:30
2. **API 호출 제한**: 과도한 조회 자제
3. **알림 피로**: 중요 알림만 발송
4. **자동 매도 주의**: 사용자 확인 후 실행
