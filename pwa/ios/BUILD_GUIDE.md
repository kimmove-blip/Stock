# iOS App Store 빌드 가이드

## 사전 준비 완료 항목

- [x] Capacitor iOS 설정
- [x] 앱 ID: `com.kimsai.stock`
- [x] 앱 이름: `Kim's AI 주식분석`
- [x] 앱 아이콘: 1024x1024 PNG
- [x] 한국어 지원 설정
- [x] 웹 assets 동기화

---

## Mac에서 실행할 단계

### 1. 프로젝트 열기

```bash
cd /path/to/Stock/pwa
npx cap open ios
```

또는 Xcode에서 직접 열기:
```
pwa/ios/App/App.xcworkspace
```

### 2. Xcode 설정

1. **Signing & Capabilities**
   - Team: Apple Developer 계정 선택
   - Bundle Identifier: `com.kimsai.stock` (자동 설정됨)
   - Provisioning Profile: Automatically manage signing 체크

2. **General**
   - Version: `1.0.0`
   - Build: `1`
   - Deployment Target: `iOS 14.0` 이상 권장

3. **Build Settings**
   - iOS Deployment Target: 14.0

### 3. Archive 생성

1. Xcode 메뉴: **Product → Archive**
2. Archive 완료 후 Organizer 창 열림
3. **Distribute App** 클릭
4. **App Store Connect** 선택
5. **Upload** 선택
6. 업로드 완료 대기

### 4. App Store Connect 설정

[App Store Connect](https://appstoreconnect.apple.com) 접속

#### 앱 정보 입력

| 항목 | 값 |
|------|-----|
| 앱 이름 | Kim's AI 주식분석 |
| 부제목 | AI 기반 한국 주식 분석 |
| 번들 ID | com.kimsai.stock |
| SKU | kimsai-stock-001 |
| 기본 언어 | 한국어 |
| 카테고리 | 금융 |
| 연령 등급 | 4+ |

#### 앱 설명

**프로모션 텍스트 (170자):**
```
매일 업데이트되는 TOP 100 추천 종목과 25개 기술적 지표 분석
```

**설명:**
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

**키워드 (100자, 쉼표로 구분):**
```
주식,주식분석,AI,기술적분석,포트폴리오,코스피,코스닥,한국주식,종목추천,투자
```

#### 스크린샷 요구사항

| 디바이스 | 해상도 | 필수 |
|----------|--------|------|
| iPhone 6.7" (14 Pro Max) | 1290 x 2796 | Yes |
| iPhone 6.5" (11 Pro Max) | 1284 x 2778 | Yes |
| iPhone 5.5" (8 Plus) | 1242 x 2208 | No |
| iPad 12.9" (3rd gen) | 2048 x 2732 | No |

**스크린샷 위치:** `screenshot/스토어등록용/`

#### 필수 URL

| 항목 | URL |
|------|-----|
| 개인정보처리방침 | https://stock.kims-ai.com/privacy |
| 지원 URL | https://stock.kims-ai.com |
| 마케팅 URL | https://stock.kims-ai.com |

### 5. 심사 제출

1. 모든 정보 입력 확인
2. 빌드 선택 (업로드한 Archive)
3. **심사를 위해 제출** 클릭

---

## 심사 주의사항

### 금융 앱 특별 요구사항

1. **면책 문구 필수**
   - "투자 권유가 아님" 명시 (앱 내 포함됨)
   - "투자 책임은 본인에게 있음" 명시 (앱 내 포함됨)

2. **실제 거래 기능 없음 명시**
   - 정보 제공 앱임을 강조
   - 실제 주식 매매 기능 없음

3. **개인정보처리방침**
   - 수집 정보 명확히 기재
   - 데이터 삭제 방법 안내

### 심사 거절 대비

흔한 거절 사유와 대응:

1. **Guideline 4.2 - 최소 기능**
   - 충분한 기능 제공 확인 (완료)

2. **Guideline 5.1.1 - 데이터 수집**
   - 개인정보처리방침 URL 제공 (완료)
   - 데이터 삭제 기능 제공 (완료)

3. **Guideline 3.1.1 - 금융 앱**
   - 투자 권유가 아님 면책 문구 (완료)

---

## 문제 해결

### 빌드 실패 시

```bash
# 캐시 정리
cd pwa
rm -rf ios/App/Pods
rm -rf ios/App/Podfile.lock

# 다시 동기화
npx cap sync ios
```

### CocoaPods 오류 시

```bash
cd ios/App
pod install --repo-update
```

---

## 타임라인

| 단계 | 예상 소요 |
|------|----------|
| Mac에서 Xcode 빌드 | 30분 |
| App Store Connect 설정 | 1시간 |
| 스크린샷 준비/업로드 | 1시간 |
| 심사 대기 | 1-7일 |

---

## 연락처

- 지원 이메일: help@kims-ai.com
- 서비스 URL: https://stock.kims-ai.com
