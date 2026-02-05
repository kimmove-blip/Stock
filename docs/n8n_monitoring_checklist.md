# n8n 감시 체크리스트

> 최종 업데이트: 2026-02-04
> 텔레그램 chat_id: 5411684999

---

## 1. 종목 필터링 (07:00, 08:00)

### 체크 명령어

```bash
# 오늘 필터 파일 존재 확인
ls /home/kimhc/Stock/output/filtered_stocks_$(date +%Y%m%d).csv 2>/dev/null && echo "OK" || echo "FAIL"
```

```bash
# 필터된 종목 수 확인 (최소 500개 이상)
wc -l /home/kimhc/Stock/output/filtered_stocks_$(date +%Y%m%d).csv 2>/dev/null | awk '{print $1}'
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 파일 없음 (08:30 기준) | 즉시 알림 |
| 종목 수 < 500 | 경고 알림 |

---

## 2. 시황브리핑 (08:00)

### 체크 명령어

```bash
# 오늘 실행 여부 확인
grep "$(date +%Y-%m-%d)" /tmp/morning_briefing.log | tail -1
```

```bash
# 에러 확인
grep -E "ERROR|Exception" /tmp/morning_briefing.log | tail -3
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 08:30까지 실행 기록 없음 | 알림 |
| 에러 발생 | 즉시 알림 |

---

## 3. 스코어 기록 (09:00~15:45)

### 체크 명령어

```bash
# 최근 10분 내 CSV 파일 존재 (장중 필수)
find /home/kimhc/Stock/output/intraday_scores -name "*.csv" -mmin -10 | wc -l
# 결과 0이면 → 알림
```

```bash
# 최신 파일 확인
ls -t /home/kimhc/Stock/output/intraday_scores/*.csv | head -1
```

```bash
# CSV 로드 실패 확인 (치명적!)
grep "CSV 로드 실패" /tmp/auto_trader_all.log | tail -1
# 결과 있으면 → 즉시 알림
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 10분 이상 CSV 없음 (장중) | 즉시 알림 |
| "CSV 로드 실패" 로그 | 즉시 알림 |

---

## 4. 자동매매 (09:10~15:20)

### 체크 명령어

```bash
# 마지막 실행 시간
grep "실행 시각" /tmp/auto_trader_all.log | tail -1
```

```bash
# 에러 확인
grep -E "ERROR|Exception|Traceback" /tmp/auto_trader_all.log | tail -3
```

```bash
# 오늘 매매 건수
echo "매수: $(grep "$(date +%Y-%m-%d)" /tmp/auto_trader_all.log | grep -c '매수:')"
echo "매도: $(grep "$(date +%Y-%m-%d)" /tmp/auto_trader_all.log | grep -c '매도:')"
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 15분 이상 실행 기록 없음 (장중) | 알림 |
| 에러 발생 | 즉시 알림 |

---

## 5. 스캘핑 시뮬레이터 (09:10~15:20)

### 체크 명령어

```bash
# 스캘핑 프로세스 실행 중인지 확인 (장중)
pgrep -f "scalping_simulator" > /dev/null && echo "RUNNING" || echo "NOT RUNNING"
```

```bash
# 오늘 스캘핑 시작 확인
grep "$(date +%Y-%m-%d)" /home/kimhc/Stock/logs/scalping_simulator.log | head -1
```

```bash
# 최근 거래 내역
grep "$(date +%Y-%m-%d)" /home/kimhc/Stock/logs/scalping_mock_execute.log | tail -5
```

```bash
# 오늘 스캘핑 매매 건수
echo "매수: $(grep "$(date +%Y-%m-%d)" /home/kimhc/Stock/logs/scalping_mock_execute.log | grep -c 'BUY')"
echo "매도: $(grep "$(date +%Y-%m-%d)" /home/kimhc/Stock/logs/scalping_mock_execute.log | grep -c 'SELL')"
```

```bash
# 에러 확인
grep -E "ERROR|Exception|Traceback" /home/kimhc/Stock/logs/scalping_simulator.log | tail -3
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 09:30 이후 프로세스 없음 | 즉시 알림 |
| 에러 발생 | 즉시 알림 |
| 30분 이상 거래 없음 (장중) | 경고 알림 |

---

## 6. 크론 존재 확인 (수시)

> **중요: root 크론탭 사용** (2026-02-05 변경)
> - `crontab -l` → `sudo crontab -l`

### 체크 명령어

```bash
# 핵심 크론 존재 여부 (모두 1 이상이어야 함) - root 크론탭
echo "filter: $(sudo crontab -l | grep -c filter_stocks)"
echo "record: $(sudo crontab -l | grep -c record_intraday)"
echo "auto_trader: $(sudo crontab -l | grep -c 'auto_trader\|call-auto-trader')"
echo "scalping: $(sudo crontab -l | grep -c scalping_simulator)"
echo "morning_briefing: $(sudo crontab -l | grep -c morning_briefing)"
echo "daily_top100: $(sudo crontab -l | grep -c daily_top100)"
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 핵심 크론 누락 (0개) | 즉시 알림 |

---

## 6. API 서버 (수시)

### 체크 명령어

```bash
# 서버 상태 확인
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
# 200 아니면 → 알림
```

```bash
# 응답 시간 확인 (5초 초과 시 경고)
curl -s -o /dev/null -w "%{time_total}" http://localhost:8000/health
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| HTTP 200 아님 | 즉시 알림 |
| 응답 5초 초과 | 경고 알림 |

---

## 7. 일일 보고서 (16:00)

### 체크 명령어

```bash
# 실행 확인
grep "$(date +%Y-%m-%d)" /tmp/daily_trade_report.log | tail -1
```

### 알림 조건

| 조건 | 알림 |
|------|------|
| 16:30까지 실행 기록 없음 | 알림 |

---

## 시간대별 체크 스케줄

| 시간 | 체크 항목 | 알림 조건 |
|------|----------|----------|
| 07:30 | 종목 필터 파일 | 파일 없음 |
| 08:30 | 시황브리핑 + 필터 완료 | 실행 안됨 또는 종목 < 500 |
| 09:10 | 스코어 기록 시작 | CSV 없음 |
| 09:15 | 스캘핑 시뮬레이터 시작 | 프로세스 없음 |
| 09:15~14:55 (10분) | 스코어 + 자동매매 + 스캘핑 | CSV 없음, 프로세스 없음 |
| 15:00 | 정리매도 시작 | 로그 에러 |
| 15:30 | 정리매도 + 스캘핑 종료 | - |
| 16:30 | 일일 보고서 | 실행 안됨 |
| 수시 | 크론 존재 + API 서버 | 누락 또는 다운 |

---

## 텔레그램 알림 템플릿

```
🚨 [Stock 감시] 이상 감지

항목: {항목명}
상태: {상태 설명}
시간: {발생 시간}
조치: {필요한 조치}
```

### 예시

```
🚨 [Stock 감시] 이상 감지

항목: 스코어 기록
상태: 10분 이상 CSV 파일 없음
시간: 2026-02-04 14:25
조치: record_intraday_scores.py 크론 확인 필요
```

---

## 크론 복구 명령어

문제 발생 시 크론 복구:

```bash
# 크론 백업 파일 확인
cat /home/kimhc/cron_new.txt

# 크론 적용
crontab /home/kimhc/cron_new.txt

# 확인
crontab -l | grep -c record_intraday
```

---

## 수동 실행 명령어

```bash
# 스코어 기록
/home/kimhc/Stock/venv/bin/python record_intraday_scores.py

# 자동매매 (정리매도 포함)
/home/kimhc/Stock/venv/bin/python auto_trader.py --intraday --all

# 시황브리핑
/home/kimhc/Stock/venv/bin/python morning_briefing.py --email

# 종목 필터
/home/kimhc/Stock/venv/bin/python filter_stocks.py
```

---

## n8n 통합 모니터링 스크립트 (2026-02-05)

> **중요**: root 크론탭 사용으로 변경됨

```bash
TODAY=$(date +%Y%m%d)
DATE_DASH=$(date +%Y-%m-%d)

# 1. 기본 시스템 체크
FILTER_FILE="/home/kimhc/Stock/output/filtered_stocks_$TODAY.csv"
[ -f "$FILTER_FILE" ] && FILTER_CNT=$(wc -l < "$FILTER_FILE" | tr -d ' \n') || FILTER_CNT=0

# morning_briefing 로그 (없으면 SKIP)
BRIEF_LOG="/tmp/morning_briefing.log"
if [ -f "$BRIEF_LOG" ]; then
  grep -q "$DATE_DASH" "$BRIEF_LOG" && BRIEF_OK="OK" || BRIEF_OK="FAIL"
else
  BRIEF_OK="SKIP"
fi

LAST_SCORE=$(ls -t /home/kimhc/Stock/output/intraday_scores/*.csv 2>/dev/null | head -1)
[ -n "$LAST_SCORE" ] && SCORE_TIME=$(date -r "$LAST_SCORE" +%H:%M) || SCORE_TIME="N/A"
SCORE_10M=$(find /home/kimhc/Stock/output/intraday_scores -name "*.csv" -mmin -10 | wc -l | tr -d ' \n')

TRADE_TIME=$(grep "실행 시각" /tmp/auto_trader_all.log | tail -1 | grep -oP "\d{2}:\d{2}:\d{2}" | tail -1 | tr -d '\n')
[ -z "$TRADE_TIME" ] && TRADE_TIME="N/A"
TRADE_B=$(grep "$DATE_DASH" /tmp/auto_trader_all.log | grep -c '매수:' | tr -d ' \n')
TRADE_S=$(grep "$DATE_DASH" /tmp/auto_trader_all.log | grep -c '매도:' | tr -d ' \n')

pgrep -f "scalping_simulator" > /dev/null && SCAL_PROC="RUNNING" || SCAL_PROC="DEAD"
SCAL_B=$(grep "$DATE_DASH" /home/kimhc/Stock/logs/scalping_mock_execute.log 2>/dev/null | grep -c 'BUY' | tr -d ' \n' || echo 0)
SCAL_S=$(grep "$DATE_DASH" /home/kimhc/Stock/logs/scalping_mock_execute.log 2>/dev/null | grep -c 'SELL' | tr -d ' \n' || echo 0)

HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | tr -d ' \n')

# root 크론탭 확인 (2026-02-05 변경)
CRON_CNT=$(sudo crontab -l 2>/dev/null | grep -E "filter_stocks|record_intraday|auto_trader|scalping_simulator" | wc -l | tr -d ' \n')

# 2. 스캘핑 상세 데이터
S_FILE="/home/kimhc/Stock/output/scalping_simulation/summary_$TODAY.json"
T_FILE="/home/kimhc/Stock/output/scalping_simulation/trades_$TODAY.json"

if [ -f "$S_FILE" ]; then S_JSON=$(cat "$S_FILE" | tr -d '\n'); else S_JSON="{}"; fi

if [ -f "$T_FILE" ]; then
  H_JSON=$(jq -c '[.[] | select(.exit_time == null)]' "$T_FILE")
  R_JSON=$(jq -c '.[-5:]' "$T_FILE")
else
  H_JSON="[]"
  R_JSON="[]"
fi

# 3. 최종 JSON
echo "{\"filter\":$FILTER_CNT, \"briefing\":\"$BRIEF_OK\", \"score\":{\"time\":\"$SCORE_TIME\",\"c10\":$SCORE_10M}, \"trade\":{\"time\":\"$TRADE_TIME\",\"b\":$TRADE_B,\"s\":$TRADE_S}, \"scalping\":{\"proc\":\"$SCAL_PROC\",\"b\":$SCAL_B,\"s\":$SCAL_S}, \"http\":\"$HTTP\", \"cron\":$CRON_CNT, \"scalping_detail\": {\"summary\": $S_JSON, \"holdings\": $H_JSON, \"recent\": $R_JSON}}"
```

### 이상감지 조건

| 필드 | 정상 | 이상 |
|------|------|------|
| `filter` | >= 500 | < 500 |
| `briefing` | "OK" 또는 "SKIP" | "FAIL" |
| `score.c10` | >= 1 | 0 (10분간 CSV 없음) |
| `http` | "200" | 그 외 |
| `cron` | >= 3 | 0 |
| `scalping.proc` | "RUNNING" (장중) | "DEAD" (장중) |
