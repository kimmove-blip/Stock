# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

한국 주식시장(KOSPI/KOSDAQ) AI 분석 및 자동매매 시스템. 기술적 분석 25개 지표 기반으로 매수/매도 신호를 생성하고, 한국투자증권 API를 통해 자동매매를 수행합니다.

## Common Commands

```bash
# 가상환경 활성화 (모든 Python 명령 실행 전 필수)
source venv/bin/activate

# TOP 100 스크리닝 실행 (full 분석 + 이메일)
python daily_top100.py --full --email

# API 서버 실행 (포트 8000)
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 자동매매 대시보드 (포트 5001)
python trading_dashboard.py --host 0.0.0.0 --port 5001

# 포트폴리오 모니터링 (장중 알림)
python portfolio_monitor.py --force

# 백테스트 실행
python backtest_1year.py
```

## Architecture

### Core Analysis Flow
```
daily_top100.py (Entry Point)
    ├── market_screener.py     # KRX 종목 필터링 (시총, 거래대금)
    ├── technical_analyst.py   # 25개 기술적 지표 분석 → 점수 산출
    ├── streak_tracker.py      # 신호 연속성 추적
    └── Output: JSON/Excel/PDF (output/ 디렉토리)
```

### Auto Trading System
```
auto_trader.py (Main Trader)
    ├── trading/order_executor.py  # 한투 API 주문 실행
    ├── trading/risk_manager.py    # 손절/익절/포지션 관리
    ├── trading/trade_logger.py    # 거래 기록 (SQLite) + 매수 제안 관리
    └── api/services/kis_client.py # 한국투자증권 API 클라이언트

trading_dashboard.py → Flask 웹 대시보드 (실시간 계좌, 설정 변경, 매수 대기열)
```

### API Server (FastAPI)
```
api/main.py
    ├── routers/stocks.py      # 종목 분석 API
    ├── routers/top100.py      # TOP 100 조회
    ├── routers/portfolio.py   # 포트폴리오 관리
    ├── routers/realtime.py    # 실시간 추천
    └── services/kis_client.py # 증권사 API
```

### Key Configuration (config.py)
- `AutoTraderConfig`: 자동매매 설정 (MIN_BUY_SCORE, STOP_LOSS_PCT, MAX_HOLDINGS 등)
- `AutoTraderConfig.TRADE_MODE`: 매매 모드 ("auto" / "semi-auto")
- `ScreeningConfig`: 스크리닝 필터 (시총, 거래대금 기준)
- `IndicatorWeights`: 기술적 지표별 가중치 (점수 계산용)
- `TelegramConfig`: 텔레그램 알림 설정

### Database
- `database/stock_data.db`: 종목 데이터, 사용자, 포트폴리오
- `database/auto_trade.db`: 자동매매 거래 기록, 매수 제안 (pending_buy_suggestions)

## Key Technical Signals

점수 계산 시 사용되는 주요 신호:
- **GOLDEN_CROSS_20_60**: 중장기 골든크로스 (+25점)
- **MA_ALIGNED**: 이평선 정배열 (+15점)
- **RSI_OVERBOUGHT**: 과매수 (-10점, 매도 신호)
- **VOLUME_SURGE**: 거래량 급증 (+15점)

---

## 매매 모드

### Auto Mode (자동매매)
- 조건 충족 → 즉시 자동 매수
- `TRADE_MODE = "auto"`

### Semi-Auto Mode (반자동 매수제안)
- 조건 충족 → 매수 제안 알림 → 사용자 승인 → 추천 매수가 이하일 때 매수
- `TRADE_MODE = "semi-auto"`
- 텔레그램으로 추천 매수가, 목표가, 상승확률 알림
- 대시보드에서 승인/거부 가능

---

## 자동화 스케줄

### Cron 스케줄 (crontab -l)

| 시간 | 요일 | 스크립트 | 설명 |
|------|------|----------|------|
| 07:30 | 월~금 | `daily_top100.py --full` | TOP 100 스크리닝 (자동매매용) |
| 18:00 | 월~금 | `daily_top100.py --full --email` | TOP 100 스크리닝 + 이메일 발송 |
| 08:30 | 월~금 | `portfolio_monitor.py --force` | 포트폴리오 모니터링 (장 시작 전) |
| */10분 09:00~15:30 | 월~금 | `portfolio_monitor.py` | 포트폴리오 모니터링 (장중 10분마다) |
| 08:00 | 월~토 | `daily_value_stocks.py` | 가치주 발굴 |

### Cron 원본
```cron
# TOP 100 스크리닝 (자동매매용) - 오전 7:30 (월~금)
30 7 * * 1-5 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python daily_top100.py --full >> /home/kimhc/Stock/logs/cron.log 2>&1

# TOP 100 스크리닝 + 이메일 - 오후 6시 (월~금)
0 18 * * 1-5 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python daily_top100.py --full --email >> /home/kimhc/Stock/logs/cron.log 2>&1

# 포트폴리오 모니터링 - 오전 8:30 (월~금)
30 8 * * 1-5 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python portfolio_monitor.py --force >> /home/kimhc/Stock/logs/monitor.log 2>&1

# 포트폴리오 모니터링 - 장중 10분마다 09:00~15:30 (월~금)
*/10 9-14 * * 1-5 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python portfolio_monitor.py >> /home/kimhc/Stock/logs/monitor.log 2>&1
0,10,20,30 15 * * 1-5 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python portfolio_monitor.py >> /home/kimhc/Stock/logs/monitor.log 2>&1

# 가치주 발굴 - 오전 8시 (월~토)
0 8 * * 1-6 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python daily_value_stocks.py >> /home/kimhc/Stock/logs/value_stocks.log 2>&1
```

---

## 상시 실행 프로세스

| 포트 | 프로세스 | 설명 |
|------|----------|------|
| 8000 | `uvicorn api.main:app` | Stock API 서버 |
| 5001 | `trading_dashboard.py` | 자동매매 대시보드 |

### 프로세스 시작 명령어
```bash
# Stock API 서버
nohup /home/kimhc/Stock/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 > /home/kimhc/Stock/logs/api.log 2>&1 &

# 자동매매 대시보드
nohup /home/kimhc/Stock/venv/bin/python /home/kimhc/Stock/trading_dashboard.py --host 0.0.0.0 --port 5001 > /home/kimhc/Stock/logs/dashboard.log 2>&1 &
```

---

## 자동매매 스케줄러

대시보드에서 "실행" 버튼 클릭 시 시작됨

| 항목 | 내용 |
|------|------|
| 스크립트 | `auto_trader_scheduler.py` |
| 실행 시간 | 평일 08:50 ~ 15:20 (하루 1회) |
| 로그 | `logs/scheduler.log` |
| PID 파일 | `.auto_trader.pid` |

### 매수 조건
- 점수 >= 85점
- 매수 신호 존재
- 거래량 충족 (20일 평균 대비)
- 최대 보유 종목 수 미만

### 매도 조건

| 조건 | 점수 >= 70 | 점수 < 70 | 설명 |
|------|:----------:|:---------:|------|
| 손절 -7% | ✅ 매도 | ✅ 매도 | 손실 제한 (항상 적용) |
| 점수 < 40 | ✅ 매도 | ✅ 매도 | 신호 악화 (항상 적용) |
| 보유 > 10일 | ✅ 매도 | ✅ 매도 | 장기 보유 방지 (항상 적용) |
| 매도신호 3개+ | ❌ 무시 | ✅ 매도 | **점수 기반 필터링** |

**점수 기반 매도 신호 필터링:**
- 점수 >= 70점: 매수 신호가 강하므로 매도 신호 무시 (손절/점수하락은 적용)
- 점수 < 70점: 매도 신호 3개 이상 발생 시 매도

**강력 매도 신호 목록:**
- RSI 과매수 (>80), MACD 데드크로스, 볼린저밴드 상단 이탈
- 단기/중기 데드크로스, 이평선 역배열
- 슈퍼트렌드 매도전환, PSAR 매도신호
- 하락장악형, 저녁별형 (캔들 패턴)

### Semi-Auto 모드 추가 조건
- 승인된 제안의 현재가가 추천 매수가(또는 매수밴드 상단) 이하일 때 매수

---

## 외부 접속 URL

| 서비스 | URL |
|--------|-----|
| Stock PWA | https://stock.kims-ai.com |
| Stock API | https://api-stock.kims-ai.com |
| 자동매매 대시보드 | https://trading.kims-ai.com |

---

## 로그 파일 위치

```
/home/kimhc/Stock/logs/
├── cron.log           # daily_top100.py 실행 로그
├── monitor.log        # portfolio_monitor.py 실행 로그
├── value_stocks.log   # daily_value_stocks.py 실행 로그
├── scheduler.log      # 자동매매 스케줄러 로그
├── api.log            # API 서버 로그
└── dashboard.log      # 대시보드 로그
```

---

## 주요 출력 파일

```
/home/kimhc/Stock/output/
├── top100_YYYYMMDD.json   # 일일 TOP 100 분석 결과
├── top100_YYYYMMDD.xlsx   # 엑셀 리포트
├── top100_YYYYMMDD.pdf    # PDF 리포트
└── value_stocks_YYYYMMDD.json  # 가치주 분석 결과
```

---

---

## PWA/TWA 트러블슈팅

### 앱 흰 화면(White Screen) 문제

**증상:** TWA 앱에서 흰 화면만 표시되고, 웹 브라우저(stock.kims-ai.com)로는 정상 작동

**원인:** Service Worker가 오래된 `index.html`을 캐시하여 이미 삭제된 JS 파일 참조

**해결 방법:**
1. `sw.js` 캐시 버전 업데이트 (예: `ai-stock-v4` → `ai-stock-v5`)
2. `index.html`은 항상 네트워크 우선으로 변경

**수정 파일:** `pwa/public/sw.js`, `pwa/dist/sw.js`

```javascript
// 캐시 버전 업데이트
const CACHE_NAME = 'ai-stock-v5';

// index.html은 캐시 목록에서 제외
const STATIC_ASSETS = [
  '/manifest.json',
];

// fetch 이벤트에서 HTML 요청은 네트워크 우선
if (event.request.mode === 'navigate' || url.pathname.endsWith('.html')) {
  event.respondWith(
    fetch(event.request)
      .catch(() => caches.match(event.request))
  );
  return;
}
```

**사용자 조치:** 앱 삭제 후 재설치

---

### Vite 빌드 호환성

**증상:** 일부 Android 기기에서 앱 로드 실패

**원인:** Vite 기본 빌드 타겟이 최신 브라우저 기준이라 구형 WebView 미지원

**해결:** `vite.config.js`에 빌드 타겟 설정

```javascript
export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2017',  // 구형 Android WebView 호환
  },
})
```

---

### PWA 서버 재시작

```bash
cd /home/kimhc/Stock/pwa
pkill -f "node serve.js"
nohup node serve.js > /tmp/pwa-serve.log 2>&1 &
```

---

*최종 업데이트: 2026-01-19 (PWA/TWA 트러블슈팅 추가)*
