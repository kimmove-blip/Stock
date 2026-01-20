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

---

## 한국투자증권 Open API

### API 기본 정보
- **공식 문서**: https://apiportal.koreainvestment.com
- **GitHub 예제**: https://github.com/koreainvestment/open-trading-api

### API URL
| 구분 | URL |
|------|-----|
| 실전투자 | `https://openapi.koreainvestment.com:9443` |
| 모의투자 | `https://openapivts.koreainvestment.com:29443` |

### 토큰 관리 (중요)
| 항목 | 값 |
|------|-----|
| 토큰 유효기간 | **24시간 (86400초)** |
| 토큰 발급 제한 | **1분에 1회** (EGW00133 에러 발생) |
| REST API 속도 제한 | 실전 20건/초, 모의 2건/초 |

### 토큰 캐싱 구현
- **캐시 파일**: `.kis_multi_token_cache.json`
- **캐시 키**: `{app_key}_{bool(is_virtual)}` (계정별 + 모의/실전 분리, **반드시 bool 타입 사용**)
- **이중 캐싱**: 메모리 캐시 + 파일 캐시 (서버 재시작 시에도 유지)
- **관련 코드**: `api/services/kis_client.py`의 `_load_user_cached_token()`, `_save_user_token_cache()`

### 토큰 만료 자동 갱신 (2026-01-21 추가)
> **중요**: 한투 서버에서 토큰이 만료되어도 캐시 파일의 만료시간은 유효해 보일 수 있음

- **문제**: 캐시된 토큰이 한투 서버에서 만료(EGW00123)되었는데, 캐시 파일의 expires_at은 아직 유효
- **증상**: API 호출 시 500 Server Error + `"msg_cd":"EGW00123"` (기간이 만료된 token)
- **해결**: `_invalidate_token()` 메서드로 만료된 토큰 캐시 삭제 후 자동 재발급
- **적용 함수**: `get_account_balance()` - 토큰 만료 에러 시 자동 재시도

**캐시 키 주의사항**:
- DB에서 `is_mock`이 정수(0, 1)로 저장될 수 있음
- 캐시 키 생성 시 `bool(is_virtual)` 사용하여 `_0` vs `_False` 불일치 방지
- 잘못된 예: `app_key_0` (정수) vs `app_key_False` (bool) → 다른 캐시 엔트리 참조

### TR_ID 목록
| 기능 | 모의투자 | 실전투자 |
|------|----------|----------|
| 매수 | VTTC0802U | TTTC0802U |
| 매도 | VTTC0801U | TTTC0801U |
| 취소 | VTTC0803U | TTTC0803U |
| 잔고조회 | VTTC8434R | TTTC8434R |
| 미체결조회 | VTTC8036R | TTTC8036R |
| 체결내역 | VTTC8001R | TTTC8001R |
| 현재가 | FHKST01010100 | FHKST01010100 |
| 일별시세 | FHKST01010400 | FHKST01010400 |

### 주의사항
1. **API 키 복사 시 줄바꿈 주의**: APP Secret 복사 시 `\r`, `\n` 문자가 포함될 수 있음 → `.strip()` 처리 필수
2. **계좌번호**: 8자리 숫자만 사용 (하이픈 제외)
3. **상품코드**: 일반적으로 "01" (종합계좌)
4. **토큰 혼용 금지**: 모의투자 토큰과 실전투자 토큰을 혼용하면 에러 발생

---

## Claude Code 작업 명령어

### API 서버 재시작 (필수)
> **중요**: API 서버 재시작 시 반드시 아래 스크립트를 사용할 것. 다른 방법 사용 금지.

```bash
/home/kimhc/Stock/restart_server.sh
```

### 서버 상태 확인
```bash
curl -s http://localhost:8000/api/announcements | head -c 50
```

### 서버 로그 확인
```bash
tail -50 /tmp/stock_api.log
```

### 서버 프로세스 확인
```bash
ps aux | grep "uvicorn api.main" | grep -v grep
```

### PWA 빌드
```bash
cd /home/kimhc/Stock/pwa && npm run build
```

---

## 사용자 계좌 정보

| User ID | 계좌번호 | 유형 | 사용자명 |
|---------|----------|------|----------|
| 2 | XXXXXXXX | 실제투자 | 김형철 |
| 7 | XXXXXXXX | 모의투자 | 김브로 |
| 17 | XXXXXXXX | 실제투자 | - |

### 계좌 데이터 조회 (Python)
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
logger = TradeLogger()
api_key_data = logger.get_api_key_settings(2)  # user_id 변경
account_data = logger.get_real_account_balance(
    app_key=api_key_data.get('app_key'),
    app_secret=api_key_data.get('app_secret'),
    account_number=api_key_data.get('account_number'),
    account_product_code=api_key_data.get('account_product_code', '01'),
    is_mock=bool(api_key_data.get('is_mock', True))
)
holdings = [h for h in account_data.get('holdings', []) if h.get('quantity', 0) > 0]
for h in holdings:
    print(f"{h.get('stock_name')}: {h.get('quantity')}주, {h.get('eval_amount'):,}원")
EOF
```

### DB 직접 조회
```bash
sqlite3 /home/kimhc/Stock/database/auto_trade.db "SELECT user_id, initial_investment FROM auto_trade_settings;"
```

---

## 주의사항 (Claude Code 작업 시)

1. **항상 `/home/kimhc/Stock` 디렉토리 기준으로 작업**
2. **venv 활성화 필수**: `source venv/bin/activate`
3. **서버 재시작 전 기존 프로세스 종료**: `pkill -9 -f "uvicorn api.main:app"`
4. **PWA 빌드 후 브라우저 캐시 문제 발생 가능** → 사용자에게 캐시 삭제 안내
5. **명령어 실행 실패 시 디렉토리 확인** → `pwd`로 현재 위치 확인
