"""
FastAPI Backend for AI Stock Analysis System
앱스토어/플레이스토어 출시를 위한 REST API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.routers import auth, stocks, portfolio, watchlist, top100, realtime, value_stocks, contact, themes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 이벤트"""
    # 시작 시
    print("🚀 AI 주식 분석 API 서버 시작")

    # 백그라운드 스케줄러 시작 (30분마다 TOP100 스크리닝)
    try:
        from api.services.scheduler import start_scheduler, run_initial_screening
        start_scheduler(interval_minutes=30)
        # 장 시간이면 시작 시 한 번 실행
        run_initial_screening()
    except Exception as e:
        print(f"⚠️ 스케줄러 시작 실패: {e}")

    yield

    # 종료 시
    try:
        from api.services.scheduler import stop_scheduler
        stop_scheduler()
    except:
        pass
    print("👋 API 서버 종료")


app = FastAPI(
    title="AI 주식 분석 API",
    description="한국 주식시장(KOSPI/KOSDAQ) AI 기반 분석 시스템",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 설정 (PWA에서 접근 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",           # React 개발 서버
        "http://localhost:5173",           # Vite 개발 서버
        "https://stock.kimhc.dedyn.io",    # 프로덕션 도메인
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 라우터 등록
app.include_router(auth.router, prefix="/api/auth", tags=["인증"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["종목"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["포트폴리오"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["관심종목"])
app.include_router(top100.router, prefix="/api/top100", tags=["AI 추천"])
app.include_router(realtime.router, prefix="/api/realtime", tags=["실시간 시세"])
app.include_router(value_stocks.router, prefix="/api/value-stocks", tags=["가치주"])
app.include_router(contact.router, prefix="/api/contact", tags=["문의"])
app.include_router(themes.router, prefix="/api/themes", tags=["테마"])


@app.get("/", tags=["헬스체크"])
async def root():
    """API 서버 상태 확인"""
    return {
        "status": "running",
        "message": "AI 주식 분석 API 서버",
        "version": "1.0.0"
    }


@app.get("/health", tags=["헬스체크"])
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy"}


@app.get("/api/scheduler/status", tags=["스케줄러"])
async def scheduler_status():
    """스케줄러 상태 확인"""
    try:
        from api.services.scheduler import get_scheduler_status
        return get_scheduler_status()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
