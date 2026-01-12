#!/bin/bash
# Streamlit 대시보드 실행 스크립트
# URL: https://stock.kimhc.dedyn.io/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 활성화
source venv/bin/activate

echo "====================================="
echo "  AI 주식 분석 대시보드 시작"
echo "====================================="
echo ""
echo "URL: https://stock.kimhc.dedyn.io/"
echo "Local: http://0.0.0.0:8501"
echo ""
echo "종료: Ctrl+C"
echo ""

# Streamlit 실행
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
