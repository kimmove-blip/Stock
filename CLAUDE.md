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

## 스코어링/전략 엔진

### 기술적 분석 스코어링 (V1~V5)

| 버전 | 전략명 | 설명 | 상태 |
|------|--------|------|------|
| V1 | 종합 기술적 분석 | 과매도 가점, 역발상 | 활성 |
| **V2** | **추세 추종 강화** | **역배열 과락, 20일선 기울기** | **기본값** |
| V4 | Hybrid Sniper | VCP, OBV 다이버전스, 수급 | 활성 |
| V5 | 장대양봉 | 눌림목, BB수축, 이평선 밀집 | 활성 |
| ~~V3.5~~ | ~~사일런트 바이어~~ | ~~와이코프 Phase~~ | 비활성 |
| ~~V6~~ | ~~Swing Predictor~~ | ~~2~5일 홀딩~~ | 비활성 |
| ~~V7~~ | ~~Trend Momentum~~ | ~~추세필터, 3일홀딩~~ | 비활성 |
| ~~V8~~ | ~~Contrarian Bounce~~ | ~~약세종목 모멘텀반전~~ | 비활성 |

> **참고**: V3.5, V6~V8, V9, V10은 장중 스코어 계산에서 제외됨 (시간 단축)

### V9: 갭상승 확률 예측 (ML 기반)

> **V9는 기술적 스코어링이 아닌 머신러닝 기반 오버나잇 갭상승 예측 전략**

| 항목 | 내용 |
|------|------|
| 모델 | RandomForest 분류기 |
| 목표 | 익일 시가 갭상승 확률 예측 |
| 진입 | 장 마감 전 매수 (15:20 크론) |
| 청산 | 익일 시가 매도 |
| 임계값 | **확률 70% 이상** |

#### V9 백테스트 결과 (1년, 비용 0.203% 차감 후)

| 확률 임계값 | 거래수 | 승률 | 실제수익률 | 연간 총수익 |
|-------------|--------|------|------------|-------------|
| ≥50% | 18,245 | 55.9% | -0.075% | -1,368% |
| ≥60% | 5,927 | 59.2% | +0.066% | +391% |
| **≥70%** | **909** | **61.2%** | **+0.185%** | **+168%** |
| ≥75% | 312 | 63.8% | +0.428% | +134% |
| ≥80% | 98 | 61.2% | +0.446% | +44% |

#### V9 피처 (20+개)
- 캔들: `close_pos`, `body_ratio`, `upper_wick`, `lower_wick`, `is_bull`
- 이평선: `dist_ma5`, `dist_ma20`, `aligned`
- 거래량: `vol_ratio`, `vol_declining`, `trade_value`
- 모멘텀: `day_change`, `rsi`, `consec_bull`, `is_surge`, `two_day_surge`
- 위치: `near_high_20d`, `from_low_20d`, `volatility`

#### V9 모델 학습

```bash
# 모델 재학습 (1회성, 약 30분 소요)
python train_gap_model_v2.py
```

| 항목 | 내용 |
|------|------|
| 학습 데이터 | 5년치 (2021-01-23 ~ 2026-01-23) |
| 데이터 소스 | pykrx (KOSPI/KOSDAQ 전 종목) |
| 필터 조건 | 거래대금 50억+, 등락률 -15%~+25% |
| 샘플 수 | 약 60,000+ 건 |
| 저장 경로 | `models/gap_model_v9.pkl` |

#### V9 관련 파일

| 파일 | 설명 |
|------|------|
| `train_gap_model_v2.py` | 모델 학습 스크립트 (백테스트 동일 피처) |
| `auto_trade_v9.py` | 자동매매 실행 (크론 15:20) |
| `predict_gap_prob70.py` | 갭상승 확률 70%+ 종목 예측 |
| `predict_gap_prob70_fast.py` | 빠른 버전 (캐시 모델 사용) |
| `backtest_v9_historical.py` | 6개월 백테스트 |
| `models/gap_model_v9.pkl` | 학습된 모델 파일 |
| `docs/overnight_gap_strategy_v9_v10.md` | 전략 상세 문서 |

### V10: Leader-Follower (대장주-종속주)

> **V10은 테마/섹터 내 상관관계를 이용한 캐치업 전략**

| 항목 | 내용 |
|------|------|
| 전략 | 대장주 상승 → 종속주 매수 (시차 이용) |
| 진입 | 대장주 +3% 이상 상승 시 |
| 조건 | 종속주가 아직 따라가지 못한 경우 (갭 2%+) |
| 상관계수 | 0.7 이상 (강한 커플링) |

#### V10 점수 체계 (100점 만점)

| 항목 | 배점 | 설명 |
|------|------|------|
| 대장주 움직임 | 35점 | 대장주 상승률 (3~7%+) |
| 상관관계 | 25점 | 피어슨 상관계수 (0.65~0.85+) |
| 캐치업 갭 | 25점 | 대장주 대비 언더퍼폼 (1~4%+) |
| 기술적 지지 | 15점 | MA20 위, BB 하단, RSI 적정 |

#### V10 청산 전략

| 조건 | 값 |
|------|-----|
| 목표가 | 캐치업 갭의 70~80% 회복 |
| 손절가 | -3% (빠른 손절) |
| 시간손절 | 최대 3일 (모멘텀 소멸) |

#### V10 테마 매핑

| 테마 | 대장주 | 종속주 (예시) |
|------|--------|---------------|
| 반도체 | 삼성전자, SK하이닉스 | 한미반도체, HPSP, 테크윙 |
| 2차전지 | LG에너지솔루션, 삼성SDI | 에코프로비엠, 에코프로 |
| 바이오 | 삼성바이오, 셀트리온 | SK바이오팜, 알테오젠 |
| 엔터 | 하이브 | 에스엠, YG, JYP |
| 게임 | 크래프톤, 엔씨소프트 | 펄어비스, 컴투스 |

#### V10 사용법

```python
from scoring import get_follower_opportunities, calculate_score_v10

# 캐치업 기회 종목 조회
opportunities = get_follower_opportunities(
    today_changes={'000660': 5.0, '042700': 1.0},  # 종목별 등락률
    min_leader_change=3.0,  # 대장주 최소 상승률
    max_follower_change=1.5  # 종속주 최대 상승률
)

# 개별 종목 점수 계산
result = calculate_score_v10(df, ticker='042700', market_data=market_data, today_changes=today_changes)
```

#### V10 관련 파일

| 파일 | 설명 |
|------|------|
| `scoring/score_v10_leader_follower.py` | V10 스코어링 엔진 |
| `predict_leader_follower.py` | 실시간 캐치업 기회 분석기 |
| `api/routers/themes.py` | 테마 데이터 API |

#### V10 실행 예시

```bash
python predict_leader_follower.py              # 기본 분석 (대장주 +3% 이상)
python predict_leader_follower.py --min 2      # 대장주 +2% 이상일 때 분석
python predict_leader_follower.py --top 10     # 상위 10개만 출력
python predict_leader_follower.py --corr       # 실제 상관계수 계산 (느림)
```

### 스코어링 사용법

```python
from scoring import calculate_score, calculate_score_v4

# 기본 버전 (v2) 사용
result = calculate_score(df)

# 특정 버전 사용
result = calculate_score(df, version='v4')

# 수급 데이터 포함 (v4, v6, v8)
result = calculate_score_v4_with_investor(df, investor_data)
```

### 장중 스코어 기록 (V1, V2, V4, V5)

> 5분마다 전 종목 스코어를 CSV로 기록

| 항목 | 값 |
|------|-----|
| 대상 종목 | 거래대금 30억+, 시총 300억+ (~800개) |
| 스코어 | V1, V2, V4, V5 (약 2분 30초 소요) |
| 실행 시간 | 09:00 ~ 15:45 (5분 간격) |
| 저장 경로 | `output/intraday_scores/YYYYMMDD_HHMM.csv` |
| 로그 | `/tmp/intraday_scores.log` |

#### 크론 스케줄
| 시간 | 스코어 기록 | auto_trader |
|------|-------------|-------------|
| 09:00, 09:05 | ✓ | ✗ (장 초반 노이즈) |
| 09:10 ~ 15:10 | ✓ | ✓ (5분 간격) |
| 15:45 | ✓ | ✗ (마감 기록) |

```bash
# 기본 실행 (V1, V2, V4, V5)
python record_intraday_scores.py

# 한투 API 연동 (체결강도/수급 데이터 추가)
python record_intraday_scores.py --kis

# 테스트 (저장 안함)
python record_intraday_scores.py --dry-run

# 장 전 종목 필터링
python record_intraday_scores.py --filter
```

#### CSV 컬럼
```
code, name, market, open, high, low, close, prev_close, change_pct,
volume, volume_ratio, prev_amount, prev_marcap,
buy_strength, foreign_net, inst_net, rel_strength,  # --kis 옵션 시 유효
v1, v2, v4, v5, signals
```

| 컬럼 | 설명 | 조건 |
|------|------|------|
| `buy_strength` | 체결강도 (매수/매도 × 100) | `--kis` |
| `foreign_net` | 외국인 당일 순매수 | `--kis` |
| `inst_net` | 기관 당일 순매수 | `--kis` |
| `rel_strength` | 시장 대비 상대강도 | `--kis` |
| `volume_ratio` | 5일 평균 대비 거래량 비율 | 기본 포함 |

### 장중 스코어 기반 급등/급락 감지

> 연속된 CSV 파일을 비교하여 스코어 변화량(delta) 분석

#### Tier 조건 (급등 후보)

| Tier | 조건 | 설명 |
|------|------|------|
| **Tier 1** | V2≥70, ΔV2≥8, V4≥50, 거래대금≥100억, VOLUME_EXPLOSION | 10~30분 내 급등 예상 |
| **Tier 2** | V2≥65, ΔV2≥5, 거래량 2배+, V3.5≥40 또는 V5≥50 | 30~60분 내 급등 예상 |
| **Tier 3** | V2≥60, 패턴시그널 또는 V9≥55% | 에너지 축적 중 |

#### 급락 경고 조건

| 수준 | 조건 |
|------|------|
| CRITICAL | V2=0 (역배열) 또는 ΔV2≤-15 |
| HIGH | 고거래량+음봉 (분배패턴) 또는 RSI_FALLING_KNIFE |
| MEDIUM | V2 3연속 하락 |

#### 관련 스크립트

| 파일 | 설명 |
|------|------|
| `analyze_score_changes.py` | 스코어 변화 분석기 (Tier 판정) |
| `backtest_intraday_signals.py` | 백테스트 및 임계값 최적화 |
| `monitor_realtime_scores.py` | 실시간 모니터링 데몬 |

```bash
# 스코어 변화 분석 (최신 2개 파일 비교)
python analyze_score_changes.py

# 특정 날짜 하루 전체 분석
python analyze_score_changes.py --date 20260128 --all

# 특정 종목 추적
python analyze_score_changes.py --watch 005930,035420

# 백테스트
python backtest_intraday_signals.py --detail

# 임계값 최적화
python backtest_intraday_signals.py --optimize

# 실시간 모니터링 (데몬)
python monitor_realtime_scores.py --daemon

# V2 Delta Top 20 빠른 조회
python monitor_realtime_scores.py --top
```

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

### 나스닥 연동 투자금액 조정

> 나스닥 전일 등락률에 따라 종목당 투자금액을 자동 조정 (리스크 관리)

| 나스닥 등락률 | 조정계수 | 투자금액 (20만원 기준) |
|--------------|---------|----------------------|
| -3% 이하 | 0.3배 | 60,000원 |
| -2% ~ -3% | 0.5배 | 100,000원 |
| -1% ~ -2% | 0.7배 | 140,000원 |
| -1% 이상 | 1.0배 | 200,000원 (기본값) |

```python
from trading.nasdaq_monitor import get_adjusted_investment_amount

# 나스닥 조정 투자금액 조회
adjusted, multiplier, nasdaq_change = get_adjusted_investment_amount(200000)
# → (200000, 1.0, 0.17) : 나스닥 +0.17%면 조정 없음
# → (60000, 0.3, -3.5)  : 나스닥 -3.5%면 0.3배 적용
```

#### 관련 파일
| 파일 | 설명 |
|------|------|
| `trading/nasdaq_monitor.py` | 나스닥 조회 및 조정계수 계산 |
| `trading/risk_manager.py` | TradingLimits (max_holdings=20) |

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
| 체결추이 | FHKST01010300 | FHKST01010300 |
| 투자자동향 | FHKST01010900 | FHKST01010900 |
| 지수시세 | FHPUP02100000 | FHPUP02100000 |

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

| User ID | 유형 | 장중 자동매매 |
|---------|------|--------------|
| 2 | 실제투자 | O |
| 7 | 모의투자 | **X (제외)** |
| 17 | 실제투자 | O |

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

## 장 시작 전 데이터 처리 규칙 (중요!)

### 등락률 0 처리 규칙
> **절대 규칙**: 07:00 ~ 09:00 (장 시작 전)에는 **모든 종목의 등락률(change_rate)을 0으로 표시**

| 시간대 | 등락률 처리 |
|--------|------------|
| 00:00 ~ 06:59 | 전날 종가 기준 등락률 표시 가능 |
| **07:00 ~ 08:59** | **무조건 0으로 표시** |
| 09:00 ~ 15:30 | 실시간 등락률 표시 |
| 15:30 ~ 23:59 | 당일 종가 기준 등락률 표시 |

### 이유
- 장 시작 전 TOP100 조회 시 전날 등락률이 오늘 데이터처럼 보이는 혼란 방지
- 사용자가 07:00에 앱을 열었을 때 "한농화성 +29%" 같은 어제 데이터를 오늘 데이터로 오해하는 문제 해결

### 관련 파일
- `api/routers/top100.py`: `is_before_market` 플래그로 처리
- `api/routers/realtime.py`: TOP100 실시간 시세 조회 시 동일 규칙 적용

### 코드 예시
```python
from datetime import datetime

now = datetime.now()
is_before_market = 7 <= now.hour < 9  # 07:00 ~ 08:59

if is_before_market:
    change_rate = 0.0  # 무조건 0
else:
    change_rate = cached.get('change_rate') or stock.get('change_pct')
```

---

## 주의사항

1. **항상 `/home/kimhc/Stock` 디렉토리 기준**
2. **venv 활성화 필수**: `source venv/bin/activate`
3. **서버 재시작**: 반드시 `restart_server.sh` 사용
4. **PWA 빌드 후**: 브라우저 캐시 삭제 안내 필요
5. **장 시작 전 등락률**: 07:00~09:00 사이에는 무조건 0으로 표시
