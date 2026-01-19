# Kim's AI 주식분석 앱스토어 출시 체크리스트

## 준비 완료 항목

| 항목 | 상태 | 위치 |
|------|------|------|
| PWA 앱 빌드 | OK | `pwa/dist/` |
| Android APK | OK | `output/KimsAI_Stock_v1.0.0.apk` (1.1MB) |
| 스크린샷 (14개) | OK | `screenshot/스토어등록용/` |
| 개인정보처리방침 | OK | `pwa/src/pages/Privacy.jsx` |
| 계정삭제 기능 | OK | `pwa/src/pages/DeleteAccount.jsx` |
| 데이터삭제 기능 | OK | `pwa/src/pages/DeleteData.jsx` |
| 스토어 메타데이터 | OK | `store-listing.json` |
| 서비스 URL | OK | https://stock.kims-ai.com |

---

## Google Play Store 출시 절차

### 1단계: 개발자 계정 등록
- [ ] [Google Play Console](https://play.google.com/console) 접속
- [ ] $25 일회성 등록비 결제
- [ ] 신원 확인 완료 (여권/신분증)

### 2단계: 앱 만들기
- [ ] "앱 만들기" 클릭
- [ ] 앱 이름: `Kim's AI 주식분석`
- [ ] 기본 언어: 한국어
- [ ] 앱 유형: 앱 (게임 아님)
- [ ] 무료/유료: 무료

### 3단계: 스토어 등록 정보 입력

**앱 이름:** Kim's AI 주식분석

**짧은 설명 (80자):**
```
AI 기반 한국 주식 분석 - 매일 TOP 100 종목 추천, 기술적 분석, 포트폴리오 관리
```

**전체 설명:**
```
Kim's AI 주식분석은 AI와 25개 기술적 지표를 활용한 한국 주식시장 분석 앱입니다.

주요 기능:
• 실시간 AI 추천: 매일 업데이트되는 TOP 100 추천 종목
• 가치주 발굴: 저평가 우량주 자동 스크리닝
• 기술적 분석: RSI, MACD, 볼린저밴드 등 25개 지표 분석
• 포트폴리오 관리: 보유 종목 수익률 추적 및 매도/보유 의견
• 관심종목: 관심 종목 모니터링 및 알림
• 시장 동향: 국내외 주요 지수 및 뉴스

분석 지표:
- 이동평균선 (5/20/60/120일)
- RSI, MACD, 스토캐스틱
- 볼린저밴드, ATR
- 거래량 분석, 캔들 패턴
- 슈퍼트렌드, PSAR 등

투자에 참고가 되는 객관적인 기술적 분석 정보를 제공합니다.
본 앱의 정보는 투자 권유가 아니며, 투자 판단은 본인의 책임입니다.
```

- [ ] 앱 아이콘 업로드 (512x512 PNG)
- [ ] 그래픽 이미지 업로드 (1024x500 PNG)
- [ ] 스크린샷 업로드 (screenshot/스토어등록용/)

### 4단계: 앱 콘텐츠 설정
- [ ] **개인정보처리방침 URL:** `https://stock.kims-ai.com/privacy`
- [ ] **광고 포함:** 아니오
- [ ] **콘텐츠 등급:** 설문지 작성 → 전체이용가
- [ ] **타겟층:** 13세 이상 (금융 앱)
- [ ] **데이터 보안:** 데이터 수집/공유 양식 작성

### 5단계: APK 업로드
- [ ] "프로덕션" 또는 "내부 테스트" 트랙 선택
- [ ] `output/KimsAI_Stock_v1.0.0.apk` 업로드
- [ ] 출시 국가 선택: 대한민국

### 6단계: 심사 제출
- [ ] 모든 필수 항목 입력 확인
- [ ] "검토를 위해 제출" 클릭
- [ ] 심사 대기 (보통 1-3일)

---

## Apple App Store 출시 절차 (선택)

### 1단계: 개발자 계정 등록
- [ ] [Apple Developer Program](https://developer.apple.com) 가입
- [ ] $99/년 등록비 결제
- [ ] D-U-N-S 번호 또는 개인 등록

### 2단계: iOS 빌드 (Mac 필요)

**옵션 A: PWABuilder**
```bash
# https://pwabuilder.com 접속
# URL 입력: https://stock.kims-ai.com
# iOS 패키지 다운로드 후 Xcode에서 빌드
```

**옵션 B: Capacitor**
```bash
cd pwa
npm install @capacitor/core @capacitor/ios
npx cap add ios
npx cap sync
npx cap open ios  # Xcode 실행
```

### 3단계: App Store Connect 설정
- [ ] 앱 이름: Kim's AI 주식분석
- [ ] 번들 ID: com.kimsai.stock
- [ ] SKU: kimsai-stock-001
- [ ] 카테고리: 금융
- [ ] 연령 등급: 4+

### 4단계: 스크린샷 업로드
- iPhone 6.7": 1290 x 2796
- iPhone 6.5": 1284 x 2778
- iPhone 5.5": 1242 x 2208

### 5단계: 심사 제출
- [ ] 모든 정보 입력 완료
- [ ] "심사를 위해 제출" 클릭
- [ ] 심사 대기 (보통 1-7일)

---

## 비용 요약

| 항목 | 비용 |
|------|------|
| Google Play 개발자 | $25 (일회성) |
| Apple Developer | $99/년 (선택) |
| **총 비용** | **$25 ~ $124** |

---

## 중요 링크

- Google Play Console: https://play.google.com/console
- Apple Developer: https://developer.apple.com
- PWABuilder: https://pwabuilder.com
- 서비스 URL: https://stock.kims-ai.com
- 개인정보처리방침: https://stock.kims-ai.com/privacy

---

## 파일 위치 요약

```
/home/kimhc/Stock/
├── output/
│   └── KimsAI_Stock_v1.0.0.apk          # Android APK
├── pwa/
│   └── dist/                             # PWA 빌드
├── screenshot/스토어등록용/              # 스토어 스크린샷
├── store-listing.json                    # 스토어 메타데이터
└── STORE_RELEASE_CHECKLIST.md           # 이 문서
```
