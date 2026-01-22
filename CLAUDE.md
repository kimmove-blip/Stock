# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요
한국 주식 AI 분석 및 자동매매 PWA 앱 (KOSPI/KOSDAQ)

## 기술 스택
- **Frontend**: React 19 + Vite 7 + TailwindCSS + DaisyUI + TanStack Query
- **Backend**: FastAPI + SQLite + APScheduler
- **증권 API**: 한국투자증권 Open API
- **모바일**: Capacitor (iOS)

---

## 개발 명령어

### API 서버 (필수: 반드시 이 스크립트 사용)
```bash
# 서버 재시작 (기존 프로세스 종료 + 새 서버 시작)
/home/kimhc/Stock/restart_server.sh

# 서버 상태 확인
curl -s http://localhost:8000/health

# 서버 로그 확인
tail -50 /tmp/stock_api.log

# 프로세스 확인
ps aux | grep "uvicorn api.main" | grep -v grep
```

### PWA 프론트엔드
```bash
cd /home/kimhc/Stock/pwa

npm run dev       # 개발 서버 (http://localhost:5173)
npm run build     # 프로덕션 빌드 (dist/)
npm run lint      # ESLint 검사
npm run preview   # 빌드 결과 미리보기

# iOS 빌드
npm run ios:build # 빌드 + Capacitor sync
npm run ios:open  # Xcode 열기
```

### Python 스크립트
```bash
source /home/kimhc/Stock/venv/bin/activate

python daily_top100.py              # TOP 100 스크리닝 (빠른 모드)
python daily_top100.py --full       # 전체 분석
python daily_top100.py --email      # 이메일 발송 포함
python auto_trader.py               # 자동매매 실행
```

### 문법 검사 (테스트 없음)
```bash
python -m py_compile <filename>.py
```

---

## 아키텍처

### 계층 구조
```
[React PWA]  →  [FastAPI 18개 라우터]  →  [SQLite 2개 DB]
     ↓                  ↓                       ↓
 TanStack Query    APScheduler            stock_data.db
 AuthContext       kis_client.py          auto_trade.db
```

### 주요 디렉토리
| 디렉토리 | 설명 |
|----------|------|
| `pwa/src/pages/` | 30+ React 페이지 컴포넌트 |
| `pwa/src/contexts/` | AuthContext, StockCacheContext |
| `api/routers/` | FastAPI 18개 엔드포인트 |
| `api/services/` | kis_client.py (한투 API), scheduler |
| `trading/` | 자동매매 모듈 (trade_logger.py 85KB) |
| `database/` | SQLite DB, db_manager.py |
| `scoring/` | 종목 스코어링 알고리즘 |

### API 엔드포인트 구조
```
/api/auth          - 인증
/api/stocks        - 종목 데이터
/api/portfolio     - 포트폴리오
/api/watchlist     - 관심종목
/api/top100        - AI TOP 100
/api/realtime      - 실시간 시세
/api/auto-trade    - 자동매매 (시크릿)
/api/alerts        - 알림
/api/market        - 시장 지수
```

### 데이터베이스
- `database/stock_data.db`: users, watchlists, portfolios, alert_history
- `database/auto_trade.db`: 자동매매 설정, 거래 내역, API 키 (암호화)

---

## 시크릿 기능 - 자동매매

> **중요**: 앱스토어 설명에 이 기능 언급 금지. 법적 문제로 추후 제거 가능.

### 자동매매 페이지 (9개, 3x3 그리드)
| API 키 설정 | 보유종목 진단 | 미체결 내역 |
|-------------|---------------|-------------|
| 계좌 현황 | 매매 제안 | 거래 내역 |
| 자동매매 설정 | 수동 매매 | 성과 분석 |

### 관련 파일
- `pwa/src/pages/AutoTrade*.jsx` (10개 파일)
- `api/routers/auto_trade.py`
- `trading/trade_logger.py`

### 자동매매 제거 시
1. `pwa/src/pages/AutoTrade*.jsx` 삭제
2. `pwa/src/App.jsx`에서 AutoTrade import/Route 제거
3. `pwa/src/components/Layout.jsx`에서 메뉴 제거
4. `pwa/src/api/client.js`에서 autoTradeAPI 제거
5. `api/routers/auto_trade.py` 삭제
6. `api/main.py`에서 라우터 제거

### API 키 보안
- Fernet 암호화 (AES 128-bit CBC + HMAC SHA256)
- 암호화 키: `database/.encryption_key` 또는 환경변수 `AUTO_TRADE_ENCRYPTION_KEY`

---

## 한국투자증권 Open API

### URL
| 구분 | URL |
|------|-----|
| 실전투자 | `https://openapi.koreainvestment.com:9443` |
| 모의투자 | `https://openapivts.koreainvestment.com:29443` |

### 토큰 관리
| 항목 | 값 |
|------|-----|
| 유효기간 | 24시간 |
| 발급 제한 | 1분에 1회 (EGW00133) |
| 속도 제한 | 실전 20건/초, 모의 2건/초 |

### 토큰 캐싱
- 캐시 파일: `.kis_multi_token_cache.json`
- 캐시 키: `{app_key}_{bool(is_virtual)}` (**반드시 bool 타입**)
- 관련 코드: `api/services/kis_client.py`

### 토큰 만료 자동 갱신
- 문제: 캐시된 토큰이 한투 서버에서 만료(EGW00123)되었으나 캐시 파일의 expires_at은 유효
- 해결: `_invalidate_token()` 메서드로 만료된 토큰 삭제 후 자동 재발급

### TR_ID 목록
| 기능 | 모의투자 | 실전투자 |
|------|----------|----------|
| 매수 | VTTC0802U | TTTC0802U |
| 매도 | VTTC0801U | TTTC0801U |
| 취소 | VTTC0803U | TTTC0803U |
| 잔고조회 | VTTC8434R | TTTC8434R |
| 미체결조회 | VTTC8036R | TTTC8036R |
| 현재가 | FHKST01010100 | FHKST01010100 |

### 실전 vs 모의투자 API 차이 (중요!)
| 구분 | 실전투자 | 모의투자 |
|------|----------|----------|
| output1 | 계좌 요약 | **보유종목 리스트** |
| output2 | 보유종목 리스트 | **계좌 요약** |

`kis_client.py`에서 모의투자인 경우 output1/output2 바꿔서 처리

### 주의사항
1. API 키 복사 시 `\r`, `\n` 문자 포함 가능 → `.strip()` 필수
2. 계좌번호: 8자리 숫자 (하이픈 제외)
3. 상품코드: "01" (종합계좌)
4. 토큰 혼용 금지 (모의/실전)

---

## 사용자 계좌 정보

| User ID | 계좌번호 | 유형 |
|---------|----------|------|
| 2 | XXXXXXXX | 실제투자 |
| 7 | XXXXXXXX | 모의투자 |
| 17 | XXXXXXXX | 실제투자 |

### 계좌 데이터 조회
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
logger = TradeLogger()
api_key_data = logger.get_api_key_settings(2)  # user_id
account_data = logger.get_real_account_balance(
    app_key=api_key_data.get('app_key'),
    app_secret=api_key_data.get('app_secret'),
    account_number=api_key_data.get('account_number'),
    account_product_code=api_key_data.get('account_product_code', '01'),
    is_mock=bool(api_key_data.get('is_mock', True))
)
for h in account_data.get('holdings', []):
    if h.get('quantity', 0) > 0:
        print(f"{h.get('stock_name')}: {h.get('quantity')}주")
EOF
```

### DB 직접 조회
```bash
sqlite3 /home/kimhc/Stock/database/auto_trade.db "SELECT user_id, initial_investment FROM auto_trade_settings;"
```

---

## 코드 스타일

### Import 순서
1. 표준 라이브러리 (`os`, `sys`, `datetime`)
2. 서드파티 (`pandas`, `fastapi`, `pykrx`)
3. 로컬 모듈 (`from config import ...`)

### 네이밍
- 함수/변수: `snake_case`
- 클래스: `PascalCase`
- 상수: `UPPER_SNAKE_CASE`

### 에러 처리
```python
try:
    result = api_call()
except Exception as e:
    print(f"에러: {e}")
    return None
```

### 주석 언어
한국어 (한글) 사용

---

## PDF 생성 시 폰트 주의사항

### TTC 폰트 문제
- **TTC (TrueType Collection)** 파일은 여러 폰트를 하나의 파일에 묶은 형식
- WeasyPrint에서 TTC 파일 사용 시 `TTLibFileIsCollectionError` 발생
- 예: `NotoSansCJK.ttc` 파일 → "specify a font number between 0 and 4" 에러

### 해결 방법
- **TTC 대신 TTF 또는 OTF 사용**
- 사용 가능한 폰트 (fonts/ 디렉토리):
  - `NanumBarunpenR.ttf` (일반)
  - `NanumBarunpenB.ttf` (볼드)
  - `NotoSansCJKkr-Regular.otf`

### PDF 라이브러리별 권장사항
| 라이브러리 | 권장 폰트 | 비고 |
|-----------|----------|------|
| ReportLab | NanumBarunpen.ttf | TTFont 등록 필요 |
| WeasyPrint | NotoSansCJKkr.otf | TTC 사용 불가 |
| fpdf2 | NanumBarunpen.ttf | add_font() 사용 |

### 예시 코드 (ReportLab)
```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont('NanumBarunpen', '/home/kimhc/Stock/fonts/NanumBarunpenR.ttf'))
pdfmetrics.registerFont(TTFont('NanumBarunpenB', '/home/kimhc/Stock/fonts/NanumBarunpenB.ttf'))
```

---

## 주의사항

1. **항상 `/home/kimhc/Stock` 디렉토리 기준**
2. **venv 활성화 필수**: `source venv/bin/activate`
3. **서버 재시작**: 반드시 `restart_server.sh` 사용
4. **PWA 빌드 후**: 브라우저 캐시 삭제 안내 필요
