# AI 주식 분석 시스템

## 개요

한국 주식시장(KOSPI/KOSDAQ)의 종목을 AI 기반으로 분석하여 투자 의사결정을 돕는 종합 분석 시스템입니다. 기술적 분석, 펀더멘털 분석, 뉴스 센티멘트 분석을 통합하여 매수/매도 의견과 점수를 제공합니다.

---

## 주요 기능

### 1. AI 추천 종목 (Daily TOP 100)
- 매일 전 종목을 스크리닝하여 **상위 100개 종목** 자동 선정
- 시가총액 300억~1조, 거래대금 3억 이상, 주가 10만원 이하 필터링
- 20개 이상의 기술적 지표 종합 분석
- PDF/Excel 리포트 자동 생성

### 2. 기술적 분석 (25개 지표)
| 구분 | 지표 |
|------|------|
| 추세 | 이동평균선(5/20/60/120일), 골든크로스, 데드크로스 |
| 모멘텀 | RSI, MACD, 스토캐스틱, ADX, CCI, Williams %R |
| 거래량 | OBV, 거래량 급증, MFI, CMF |
| 변동성 | 볼린저밴드, ATR |
| 캔들패턴 | 망치형, 역망치형, 장악형, 샛별형, 저녁별형 |

### 3. 펀더멘털 분석
- DART 전자공시 연동 (재무제표, 공시정보)
- PER, PBR, ROE 등 주요 지표 분석

### 4. 센티멘트 분석
- 네이버 금융 뉴스 크롤링
- 긍정/부정 키워드 기반 감성 점수 산출

### 5. 포트폴리오 관리
- 보유 종목 등록 (수동 입력 / Excel 업로드)
- 실시간 수익률 계산
- 종목별 **매수/보유/매도/손절** 의견 제공
- 투자 시뮬레이션

### 6. 관심종목 관리
- 카테고리별 관심종목 분류
- AI 추천 종목 → 관심종목 일괄 추가

### 7. 텔레그램 알림 서비스
- 포트폴리오 종목 **하락 징후 감지 시 자동 알림**
- 매도/손절 의견 발생 시 실시간 알림
- 장중 10분 간격 모니터링

### 8. 이메일 구독 서비스
- 회원가입 시 이메일 수신 동의
- 매일 오후 6시 **TOP 100 리포트** 자동 발송 (PDF 첨부)

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.12 |
| Frontend | Streamlit |
| Database | SQLite |
| 주가 데이터 | pykrx, FinanceDataReader |
| 공시 데이터 | OpenDartReader |
| 알림 | Telegram Bot API, SMTP |
| 인증 | streamlit-authenticator |

---

## 실행 방법

```bash
# 가상환경 활성화
source venv/bin/activate

# 대시보드 실행
streamlit run dashboard.py

# 일일 스크리닝 (수동 실행)
python daily_top100.py --full --email

# 포트폴리오 모니터링 (수동 실행)
python portfolio_monitor.py --force
```

---

## 자동 실행 스케줄 (크론)

| 작업 | 시간 | 요일 |
|------|------|------|
| TOP 100 스크리닝 + 이메일 발송 | 오후 6시 | 월~금 |
| 포트폴리오 모니터링 (장 시작 전) | 오전 8:30 | 월~금 |
| 포트폴리오 모니터링 (장중) | 9:00~15:30 (10분마다) | 월~금 |

```bash
# 크론 설정 확인
crontab -l

# 크론 편집
crontab -e
```

---

## 환경 설정 (.env)

```
# DART API
DART_API_KEY=your_dart_api_key

# 이메일 발송
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password

# 텔레그램 봇
TELEGRAM_BOT_TOKEN=your_bot_token
```

---

## 프로젝트 구조

```
Stock/
├── dashboard.py          # 메인 웹 대시보드
├── daily_top100.py       # 일일 TOP 100 스크리닝
├── portfolio_monitor.py  # 포트폴리오 모니터링
├── portfolio_advisor.py  # 포트폴리오 분석 엔진
├── market_screener.py    # 시장 스크리닝
├── technical_analyst.py  # 기술적 분석
├── dart_analyst.py       # 펀더멘털 분석
├── sentiment_analyst.py  # 센티멘트 분석
├── telegram_notifier.py  # 텔레그램 알림
├── email_sender.py       # 이메일 발송
├── pdf_generator.py      # PDF 리포트 생성
├── config.py             # 설정
├── auth/
│   └── authenticator.py  # 인증 시스템
├── database/
│   ├── db_manager.py     # DB 관리
│   └── stock_data.db     # SQLite DB
├── output/               # 생성된 리포트
└── logs/                 # 로그 파일
```

---

## 면책 조항

본 시스템은 기술적 지표 기반의 참고 자료이며, 투자 판단의 최종 책임은 사용자에게 있습니다. 투자 손실에 대한 책임을 지지 않습니다.

---

## 라이선스

Private - All Rights Reserved
