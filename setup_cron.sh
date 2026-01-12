#!/bin/bash
# 매일 오후 6시 자동 실행 cron 설정 스크립트

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="$SCRIPT_DIR/venv/bin/python"
SCRIPT_PATH="$SCRIPT_DIR/daily_top100.py"
LOG_PATH="$SCRIPT_DIR/logs/cron.log"

# logs 디렉토리 생성
mkdir -p "$SCRIPT_DIR/logs"

# cron job 내용
CRON_JOB="0 18 * * 1-5 cd $SCRIPT_DIR && $PYTHON_PATH $SCRIPT_PATH --email >> $LOG_PATH 2>&1"

echo "====================================="
echo "  주식 스크리닝 자동 실행 설정"
echo "====================================="
echo ""
echo "다음 cron job이 추가됩니다:"
echo ""
echo "  $CRON_JOB"
echo ""
echo "설명: 매주 월~금 18:00에 스크리닝 실행 후 이메일 발송"
echo ""

read -p "cron job을 추가하시겠습니까? (y/n): " confirm

if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    # 기존 cron에서 daily_top100.py 관련 항목 제거 후 새로 추가
    (crontab -l 2>/dev/null | grep -v "daily_top100.py"; echo "$CRON_JOB") | crontab -

    echo ""
    echo "cron job이 추가되었습니다!"
    echo ""
    echo "현재 cron 설정:"
    crontab -l | grep "daily_top100"
    echo ""
    echo "로그 확인: tail -f $LOG_PATH"
else
    echo ""
    echo "취소되었습니다."
    echo ""
    echo "수동으로 추가하려면:"
    echo "  crontab -e"
    echo "  # 아래 줄 추가:"
    echo "  $CRON_JOB"
fi
