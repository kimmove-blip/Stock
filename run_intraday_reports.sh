#!/bin/bash
# 장중 스크리닝 리포트 - 모든 활성 사용자에게 전송
# 10분마다 cron으로 실행

cd /home/kimhc/Stock
source venv/bin/activate

# 김브로 (user_id=7) - 모의투자
python3 intraday_debug_report.py --user-id 7 &

# 김형철 (user_id=2) - 실전투자
python3 intraday_debug_report.py --user-id 2 &

wait
echo "$(date '+%Y-%m-%d %H:%M:%S') - 리포트 전송 완료"
