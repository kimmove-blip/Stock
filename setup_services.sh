#!/bin/bash
# 서비스 설정 스크립트

echo "=== AI 주식분석 서비스 설정 ==="

# 1. systemd 서비스 설치
echo "[1/4] systemd 서비스 설치..."
sudo cp /home/kimhc/Stock/stock-api.service /etc/systemd/system/
sudo cp /home/kimhc/Stock/stock-pwa.service /etc/systemd/system/
sudo systemctl daemon-reload

# 2. 서비스 활성화
echo "[2/4] 서비스 활성화..."
sudo systemctl enable stock-api
sudo systemctl enable stock-pwa

# 3. 서비스 시작
echo "[3/4] 서비스 시작..."
sudo systemctl start stock-api
sudo systemctl start stock-pwa

# 4. 상태 확인
echo "[4/4] 서비스 상태 확인..."
sleep 2
echo ""
echo "=== FastAPI 상태 ==="
sudo systemctl status stock-api --no-pager | head -5
echo ""
echo "=== PWA 상태 ==="
sudo systemctl status stock-pwa --no-pager | head -5
echo ""

# 서비스 확인
echo "=== 서비스 테스트 ==="
curl -s http://localhost:8000/health && echo " - FastAPI OK" || echo " - FastAPI FAIL"
curl -s http://localhost:3000 > /dev/null && echo " - PWA OK" || echo " - PWA FAIL"
curl -s http://localhost:8501 > /dev/null && echo " - Streamlit OK" || echo " - Streamlit FAIL"

echo ""
echo "=== 설정 완료 ==="
echo ""
echo "접속 URL:"
echo "  - 기존 웹 대시보드: https://stock.kimhc.dedyn.io"
echo "  - PWA 앱:          https://app.kimhc.dedyn.io (Caddy 설정 후)"
echo "  - API 문서:        https://stock.kimhc.dedyn.io/api/docs"
