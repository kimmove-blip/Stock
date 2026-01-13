# Google OAuth 설정 가이드

## 1. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. **API 및 서비스** > **OAuth 동의 화면** 설정
   - 앱 이름: AI 주식분석
   - 사용자 지원 이메일: 본인 이메일
   - 승인된 도메인: `kimhc.dedyn.io` 추가

4. **API 및 서비스** > **사용자 인증 정보** > **OAuth 2.0 클라이언트 ID 만들기**
   - 애플리케이션 유형: 웹 애플리케이션
   - 승인된 JavaScript 원본:
     - `https://stock.kimhc.dedyn.io`
     - `http://localhost:3000` (개발용)
   - 승인된 리디렉션 URI:
     - `https://stock.kimhc.dedyn.io`

5. 클라이언트 ID 복사

## 2. 환경 변수 설정

### FastAPI 백엔드 (.env)
```bash
# /home/kimhc/Stock/.env
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
```

### PWA 프론트엔드 (.env)
```bash
# /home/kimhc/Stock/pwa/.env
VITE_API_URL=/api
VITE_GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
```

## 3. 서비스 재시작

```bash
# FastAPI 재시작
pkill -f "uvicorn api.main"
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 &

# PWA 재빌드 및 재시작
cd pwa
npm run build
cp -r public/* dist/
pkill -f "node serve.js"
npm run serve &
```

## 4. 테스트

1. https://stock.kimhc.dedyn.io 접속
2. 로그인 페이지에서 "Google로 로그인" 버튼 클릭
3. Google 계정 선택
4. 자동 로그인 및 메인 페이지 이동 확인

## 주의사항

- Google OAuth는 HTTPS에서만 작동합니다 (localhost 제외)
- 승인된 도메인에 정확한 도메인을 추가해야 합니다
- 클라이언트 ID는 프론트엔드와 백엔드 모두에 동일하게 설정해야 합니다
