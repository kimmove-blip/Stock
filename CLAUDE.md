# Kim's AI Stock - 프로젝트 가이드

## 프로젝트 개요
한국 주식 AI 분석 및 자동매매 PWA 앱

## 기술 스택
- **Frontend**: React + Vite + TailwindCSS + TanStack Query
- **Backend**: FastAPI + SQLite
- **증권 API**: 한국투자증권 Open API

## 주요 디렉토리
- `/pwa` - React PWA 프론트엔드
- `/api` - FastAPI 백엔드
- `/trading` - 자동매매 관련 모듈
- `/database` - SQLite DB 및 데이터 관리

## 개발 환경
- Python 가상환경: `/home/kimhc/Stock/venv`
- API 서버 실행: `/home/kimhc/Stock/venv/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000`
- PWA 빌드: `cd pwa && npm run build`

---

## 시크릿 기능 - 자동매매

> **중요**: 자동매매 기능은 시크릿 기능입니다.
> - 앱스토어 설명, 앱 소개 페이지 등에 이 기능에 대한 내용이 포함되면 안 됩니다.
> - 법적 문제가 될 수 있어 추후 기능을 제거할 수 있습니다.
> - 자동매매 권한이 있는 사용자에게만 하단 메뉴에 표시됩니다.

### 자동매매 페이지 구조 (9개 메뉴, 3x3 그리드)

| 1행 | 2행 | 3행 |
|-----|-----|-----|
| API 키 설정 | 보유종목 진단 | 미체결 내역 |
| 계좌 현황 | 매매 제안 | 거래 내역 |
| 자동매매 설정 | 수동 매매 | 성과 분석 |

### 자동매매 관련 파일

**프론트엔드 (pwa/src/pages/)**
- `AutoTrade.jsx` - 메인 메뉴 페이지
- `AutoTradeApiKey.jsx` - API 키 설정 (모의/실제 계좌 선택)
- `AutoTradeAccount.jsx` - 계좌 현황
- `AutoTradeSettings.jsx` - 자동매매 설정
- `AutoTradeDiagnosis.jsx` - 보유종목 AI 진단
- `AutoTradeSuggestions.jsx` - 매수/매도 제안 관리
- `AutoTradeManual.jsx` - 수동 매매
- `AutoTradePendingOrders.jsx` - 미체결 내역
- `AutoTradeHistory.jsx` - 거래 내역
- `AutoTradePerformance.jsx` - 성과 분석

**백엔드**
- `api/routers/auto_trade.py` - 자동매매 API 엔드포인트
- `trading/trade_logger.py` - 거래 로깅 및 API 키 암호화 관리

### 자동매매 기능 제거 시
1. `pwa/src/pages/AutoTrade*.jsx` 파일들 삭제
2. `pwa/src/App.jsx`에서 AutoTrade 관련 import 및 Route 제거
3. `pwa/src/components/Layout.jsx`에서 자동매매 메뉴 및 타이틀 제거
4. `pwa/src/api/client.js`에서 autoTradeAPI 제거
5. `api/routers/auto_trade.py` 삭제
6. `api/main.py`에서 auto_trade 라우터 제거

### API 키 보안
- API 키는 Fernet 암호화(AES 128-bit CBC + HMAC SHA256)로 저장
- 암호화 키: 환경변수 `AUTO_TRADE_ENCRYPTION_KEY` 또는 `database/.encryption_key` 파일
- `.encryption_key` 파일은 `.gitignore`에 포함되어 있음
