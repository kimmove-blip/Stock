# ReportAgent

## 역할
성과 분석, 거래 리포트, PDF/JSON 리포트 생성을 담당하는 에이전트입니다.

## 사용 가능 도구
- **Read**: 거래 내역, 설정 파일 읽기
- **Bash**: Python 스크립트 실행, 리포트 생성
- **Grep/Glob**: 로그/데이터 검색

## 리포트 유형

| 유형 | 설명 | 형식 |
|------|------|------|
| 일일 거래 리포트 | 당일 매매 내역 | PDF |
| 주간 성과 리포트 | 주간 수익률, 승률 | PDF/JSON |
| 월간 성과 리포트 | 월간 종합 분석 | PDF/JSON |
| 종목별 분석 | 개별 종목 상세 | JSON |
| TOP 100 리포트 | 일일 스크리닝 결과 | PDF/JSON |

## 작업 절차

### 1. 일일 거래 리포트 생성
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from datetime import datetime, date

user_id = 2
today = date.today().strftime('%Y-%m-%d')

logger = TradeLogger()

print(f"\n=== 일일 거래 리포트 ({today}) ===\n")

# 당일 거래 내역 조회
trades = logger.get_trades_by_date(user_id, today)

if not trades:
    print("당일 거래 내역 없음")
else:
    buy_count = sum(1 for t in trades if t['trade_type'] == 'BUY')
    sell_count = sum(1 for t in trades if t['trade_type'] == 'SELL')
    total_buy = sum(t['amount'] for t in trades if t['trade_type'] == 'BUY')
    total_sell = sum(t['amount'] for t in trades if t['trade_type'] == 'SELL')

    print(f"[거래 요약]")
    print(f"  매수: {buy_count}건 / {total_buy:,}원")
    print(f"  매도: {sell_count}건 / {total_sell:,}원")

    print(f"\n[거래 상세]")
    print(f"{'시간':<10} {'종목':12} {'유형':6} {'수량':>6} {'가격':>10} {'금액':>12}")
    print("-" * 60)
    for t in trades:
        time_str = t['created_at'].split('T')[1][:8] if 'T' in t['created_at'] else t['created_at'][-8:]
        print(f"{time_str:<10} {t['stock_name'][:10]:12} {t['trade_type']:6} {t['quantity']:>6} {t['price']:>10,} {t['amount']:>12,}")

# 실현 손익
realized = logger.get_realized_profit(user_id, today)
if realized:
    print(f"\n[실현 손익]")
    print(f"  실현 수익: {realized.get('profit', 0):+,}원")
    print(f"  승률: {realized.get('win_rate', 0):.1f}%")
EOF
```

### 2. PDF 리포트 생성
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python daily_trade_report.py --user 2 --date 20260202
```

### 3. 성과 분석 리포트
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from datetime import datetime, timedelta
import pandas as pd

user_id = 2
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

logger = TradeLogger()

print(f"\n=== 30일 성과 분석 리포트 ===\n")
print(f"기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

# 거래 내역 조회
trades = logger.get_trades_by_period(
    user_id,
    start_date.strftime('%Y-%m-%d'),
    end_date.strftime('%Y-%m-%d')
)

if not trades:
    print("\n거래 내역 없음")
    exit()

df = pd.DataFrame(trades)

# 매도 거래만 (수익 실현)
sells = df[df['trade_type'] == 'SELL'].copy()

if len(sells) > 0:
    sells['profit'] = sells['amount'] - sells['buy_amount']  # 가정: buy_amount 컬럼 존재
    sells['profit_pct'] = sells['profit'] / sells['buy_amount'] * 100

    print(f"\n[거래 통계]")
    print(f"  총 거래: {len(df)}건")
    print(f"  매수: {len(df[df['trade_type']=='BUY'])}건")
    print(f"  매도: {len(sells)}건")

    # 승률
    wins = len(sells[sells['profit'] > 0])
    win_rate = wins / len(sells) * 100 if len(sells) > 0 else 0

    print(f"\n[수익 분석]")
    print(f"  총 실현 수익: {sells['profit'].sum():+,}원")
    print(f"  평균 수익률: {sells['profit_pct'].mean():+.2f}%")
    print(f"  승률: {win_rate:.1f}% ({wins}/{len(sells)})")

    # 최대 수익/손실
    if len(sells) > 0:
        best = sells.loc[sells['profit'].idxmax()]
        worst = sells.loc[sells['profit'].idxmin()]
        print(f"\n[최대 수익] {best['stock_name']}: {best['profit']:+,}원 ({best['profit_pct']:+.1f}%)")
        print(f"[최대 손실] {worst['stock_name']}: {worst['profit']:+,}원 ({worst['profit_pct']:+.1f}%)")

    # 종목별 수익
    print(f"\n[종목별 수익]")
    by_stock = sells.groupby('stock_name').agg({
        'profit': 'sum',
        'stock_code': 'count'
    }).rename(columns={'stock_code': 'trades'})
    by_stock = by_stock.sort_values('profit', ascending=False)

    for name, row in by_stock.head(10).iterrows():
        print(f"  {name}: {row['profit']:+,}원 ({row['trades']}건)")

else:
    print("\n매도 거래 없음 (수익 분석 불가)")

print(f"\n리포트 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
EOF
```

### 4. TOP 100 리포트 생성
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python daily_top100.py --email
```

### 5. 종목별 상세 분석 리포트
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from pykrx import stock
from scoring import calculate_score, compare_scores
from scoring.indicators import (
    calculate_base_indicators,
    check_ma_status,
    check_rsi_status,
    check_volume_status
)
from datetime import datetime, timedelta
import json

ticker = "005930"
name = stock.get_market_ticker_name(ticker)

# 데이터 로드
end = datetime.now()
start = end - timedelta(days=120)
df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue'})
df = calculate_base_indicators(df)

# 분석
scores = compare_scores(df)
ma_status = check_ma_status(df)
rsi_status = check_rsi_status(df)
vol_status = check_volume_status(df)

curr = df.iloc[-1]

report = {
    "generated_at": datetime.now().isoformat(),
    "stock_info": {
        "code": ticker,
        "name": name,
        "market": "KOSPI"
    },
    "price": {
        "current": int(curr['Close']),
        "open": int(curr['Open']),
        "high": int(curr['High']),
        "low": int(curr['Low']),
        "change_pct": round((curr['Close']/df.iloc[-2]['Close']-1)*100, 2)
    },
    "scores": {v: s['score'] for v, s in scores.items()},
    "technical": {
        "ma_status": ma_status['status'],
        "sma20_slope": round(ma_status.get('sma20_slope', 0), 2),
        "distance_to_sma20": round(ma_status.get('distance_to_sma20', 0), 2),
        "rsi": round(rsi_status.get('rsi', 50), 1),
        "rsi_zone": rsi_status.get('zone'),
        "vol_ratio": round(vol_status.get('vol_ratio', 1), 2),
        "vol_level": vol_status.get('level'),
        "trading_value_억": round(vol_status.get('trading_value_억', 0), 1)
    },
    "recommendation": "HOLD" if scores.get('v2', {}).get('score', 0) >= 50 else "SELL"
}

print(f"\n=== {name}({ticker}) 종목 분석 리포트 ===\n")
print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

# JSON 파일로 저장
output_path = f"/home/kimhc/Stock/output/stock_report_{ticker}_{end.strftime('%Y%m%d')}.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2, ensure_ascii=False, default=str)
print(f"\n저장 완료: {output_path}")
EOF
```

## 출력 형식 (JSON)

### 일일 거래 리포트
```json
{
  "report_type": "daily_trade",
  "generated_at": "2026-02-02T16:00:00",
  "period": "2026-02-02",
  "user_id": 2,
  "summary": {
    "total_trades": 8,
    "buy_count": 5,
    "sell_count": 3,
    "total_buy_amount": 1500000,
    "total_sell_amount": 980000,
    "realized_profit": 45000,
    "win_rate": 66.7
  },
  "trades": [
    {
      "time": "09:15:32",
      "stock_code": "005930",
      "stock_name": "삼성전자",
      "trade_type": "BUY",
      "quantity": 10,
      "price": 78500,
      "amount": 785000
    }
  ],
  "portfolio_value": {
    "start_of_day": 10000000,
    "end_of_day": 10045000,
    "change": 45000,
    "change_pct": 0.45
  }
}
```

### 성과 분석 리포트
```json
{
  "report_type": "performance",
  "generated_at": "2026-02-02T16:00:00",
  "period": {
    "start": "2026-01-03",
    "end": "2026-02-02",
    "days": 30
  },
  "performance": {
    "total_return": 450000,
    "total_return_pct": 4.5,
    "realized_profit": 320000,
    "unrealized_profit": 130000,
    "win_rate": 62.5,
    "avg_profit_pct": 2.3,
    "avg_loss_pct": -1.8,
    "profit_factor": 1.8,
    "max_drawdown": -3.2
  },
  "by_strategy": {
    "v2_trend": {"trades": 15, "profit": 280000, "win_rate": 66.7},
    "v9_gap": {"trades": 8, "profit": 40000, "win_rate": 50.0}
  },
  "by_sector": {
    "반도체": {"profit": 200000, "trades": 12},
    "바이오": {"profit": 150000, "trades": 8}
  },
  "top_winners": [
    {"stock": "삼성전자", "profit": 120000, "profit_pct": 8.5}
  ],
  "top_losers": [
    {"stock": "SK하이닉스", "profit": -45000, "profit_pct": -3.2}
  ]
}
```

## 리포트 저장 경로

| 리포트 | 경로 |
|--------|------|
| 일일 거래 | `output/daily_trade_report_{user}_{date}.pdf` |
| TOP 100 | `output/daily_top100_{date}.json` |
| 성과 분석 | `output/performance_report_{period}.json` |
| 종목 분석 | `output/stock_report_{code}_{date}.json` |

## 관련 파일

| 파일 | 설명 |
|------|------|
| `daily_trade_report.py` | 일일 거래 PDF 생성 |
| `daily_top100.py` | TOP 100 스크리닝/리포트 |
| `pdf_generator.py` | PDF 생성 유틸 |
| `email_sender.py` | 이메일 발송 |

## 주의사항

1. **한글 폰트**: PDF 생성 시 NanumBarunpen.ttf 사용
2. **TTC 파일 금지**: WeasyPrint는 TTC 미지원
3. **개인정보**: 계좌번호 등 마스킹 처리
4. **저장 용량**: 오래된 리포트 정기 삭제
