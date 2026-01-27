#!/bin/bash
# API 서버 안정적 재시작 스크립트

echo "=== API 서버 재시작 ==="

# 1. 기존 프로세스 종료
echo "[1/5] 기존 프로세스 종료 중..."
pkill -9 -f "uvicorn api.main:app" 2>/dev/null
sleep 2

# 2. 포트 확인 및 강제 해제
echo "[2/5] 포트 8000 확인 중..."
fuser -k 8000/tcp 2>/dev/null
sleep 1

# 3. 포트 비어있는지 확인
if lsof -i :8000 | grep -q LISTEN; then
    echo "포트 8000이 아직 사용 중입니다. 강제 종료..."
    lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs -r kill -9
    sleep 2
fi

# 4. 서버 시작
echo "[3/5] 서버 시작 중..."
cd /home/kimhc/Stock
source venv/bin/activate
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/stock_api.log 2>&1 &

# 5. API가 완전히 준비될 때까지 대기 (최대 15초)
echo "[4/5] API 준비 대기 중..."
MAX_WAIT=15
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    sleep 1
    WAITED=$((WAITED + 1))

    # API 응답 체크
    if curl -s "http://localhost:8000/api/announcements" | head -c 20 | grep -q "id"; then
        echo "  -> API 준비 완료 (${WAITED}초)"
        break
    fi
    echo "  -> 대기 중... (${WAITED}/${MAX_WAIT}초)"
done

# 6. 최종 확인
echo "[5/5] 서버 상태 확인..."
if curl -s "http://localhost:8000/api/announcements" | head -c 20 | grep -q "id"; then
    echo ""
    echo "✅ 서버 시작 성공!"
    ps aux | grep "uvicorn api.main:app" | grep -v grep | awk '{print "   PID:", $2}'
    echo ""
else
    echo ""
    echo "❌ 서버 시작 실패. 로그 확인:"
    tail -20 /tmp/stock_api.log
fi
