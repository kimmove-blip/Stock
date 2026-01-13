#!/bin/bash
# FastAPI 서버 시작 스크립트

cd /home/kimhc/Stock
source venv/bin/activate

# 기존 프로세스 종료
pkill -f "uvicorn api.main:app" 2>/dev/null

# 백그라운드 실행
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &

echo "FastAPI 서버 시작됨 (포트: 8000)"
echo "Swagger 문서: http://localhost:8000/docs"
