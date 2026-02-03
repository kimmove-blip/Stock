# 스캘핑 전략 v1.0 - 실시간 테스트 사양서

작성일: 2026-02-03
테스트 예정일: 2026-02-04

---

## 1. 전략 개요

| 항목 | 설정값 |
|------|--------|
| 전략명 | 회전율 기반 스캘핑 |
| 목표 | 단기 변동성 수익 포착 |
| 보유시간 | 최대 5분 |
| 일일 목표 | +3~5만원 (100만원 자본 기준) |

---

## 2. 거래 조건

### 2.1 종목 선정 (매일 장 시작 전)

```
시총 대비 거래대금 비율 (회전율) TOP 20
```

**조건:**
- 시총 ≥ 300억원 (유동성 확보)
- 전일 거래대금 ≥ 50억원
- 회전율 = 거래대금 / 시총 × 100

**선정 스크립트:**
```bash
python -c "
import pandas as pd
import glob
files = sorted(glob.glob('output/intraday_scores/*.csv'))
df = pd.read_csv(files[-1])
df['turnover'] = (df['prev_amount'] / df['prev_marcap']) * 100
df = df[(df['prev_marcap'] >= 3e10) & (df['prev_amount'] >= 5e9)]
top20 = df.nlargest(20, 'turnover')
codes = [str(c).zfill(6) for c in top20['code']]
print(','.join(codes))
"
```

### 2.2 진입 조건

| 조건 | 값 | 설명 |
|------|-----|------|
| V2 스코어 | ≥ 60 | 추세 강도 |
| 당일 등락률 | +0.5% ~ +5% | 상승 중이지만 과열 아님 |
| 거래량 비율 | ≥ 1.0 | 평균 이상 거래량 |
| 시간대 | 09:10 ~ 15:15 | 장 초반 노이즈 제외 |

**진입 신호:**
```python
if v2 >= 60 and 0.5 <= change_pct <= 5.0 and volume_ratio >= 1.0:
    BUY(시장가)
```

### 2.3 청산 조건 (실시간 테스트용)

| 우선순위 | 조건 | 액션 |
|---------|------|------|
| 1 | 수익률 ≥ +3% | **익절** |
| 2 | 수익률 ≤ -2% | **손절** |
| 3 | 보유시간 ≥ 15분 | **시간청산** |
| 4 | 시간 ≥ 15:19 | **장마감청산** |

**청산 우선순위:** 익절 > 손절 > 시간청산 > 장마감청산

### 2.4 재진입 규칙

| 항목 | 설정 |
|------|------|
| 블랙리스트 | **없음** (재매수 허용) |
| 재진입 대기 | 1분 (같은 종목) |
| 동시 보유 | 최대 3종목 |

---

## 3. 리스크 관리

### 3.1 포지션 크기

| 항목 | 값 |
|------|-----|
| 총 자본금 | 1,000,000원 |
| 종목당 투자금 | 100,000원 (10%) |
| 최대 동시 보유 | 3종목 (30만원) |
| 일일 최대 손실 | -50,000원 (-5%) |

### 3.2 일일 한도

```python
# 일일 손실 한도 도달 시 매매 중단
if daily_loss <= -50000:
    STOP_TRADING()

# 일일 목표 수익 도달 시 (선택)
if daily_profit >= 100000:
    CONSIDER_STOP()  # 선택적
```

### 3.3 시간대별 전략

| 시간대 | 전략 | 이유 |
|--------|------|------|
| 09:00~09:10 | **매매 금지** | 장 초반 노이즈 |
| 09:10~10:00 | 보수적 진입 | 변동성 높음 |
| 10:00~14:00 | 정상 매매 | 안정적 구간 |
| 14:00~15:15 | 적극적 청산 | 마감 대비 |
| 15:15~15:19 | **신규 진입 금지** | 청산만 |
| 15:19~ | **전량 청산** | 장마감 |

---

## 4. 기술적 구현

### 4.1 데이터 수집 (2초 폴링)

```python
# KIS REST API 현재가 조회
kis_client.get_current_price(stock_code)

# 폴링 간격
POLL_INTERVAL = 2  # 초
```

### 4.2 포지션 관리

```python
class Position:
    stock_code: str
    entry_price: int
    entry_time: datetime
    quantity: int

    def check_exit(self, current_price, current_time):
        pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        hold_seconds = (current_time - self.entry_time).total_seconds()

        # 익절
        if pnl_pct >= 2.0:
            return 'TAKE_PROFIT', pnl_pct

        # 손절
        if pnl_pct <= -2.0:
            return 'STOP_LOSS', pnl_pct

        # 시간초과
        if hold_seconds >= 300:  # 5분
            return 'TIMEOUT', pnl_pct

        return None, pnl_pct
```

### 4.3 주문 실행

```python
# 시장가 매수
kis_client.place_order(
    stock_code=code,
    side='buy',
    quantity=quantity,
    price=0,
    order_type='01'  # 시장가
)

# 시장가 매도
kis_client.place_order(
    stock_code=code,
    side='sell',
    quantity=quantity,
    price=0,
    order_type='01'  # 시장가
)
```

---

## 5. 실시간 테스트 계획

### 5.1 테스트 환경

| 항목 | 설정 |
|------|------|
| 계정 | User 2 (실전투자) |
| 자본금 | 100만원 |
| 모드 | **시뮬레이션** (주문 미실행) |
| 로그 | /tmp/scalping_realtime.log |

### 5.2 테스트 일정

**2026-02-04 (화)**

| 시간 | 활동 |
|------|------|
| 08:50 | 시스템 시작, 종목 선정 |
| 09:00 | 데이터 수집 시작 |
| 09:10 | 매매 시작 |
| 12:00 | 중간 점검 |
| 15:19 | 전량 청산 |
| 15:30 | 결과 분석 |

### 5.3 실행 명령어

```bash
# 1. 종목 선정
python -c "..." > /tmp/scalp_stocks.txt

# 2. 시뮬레이터 실행
source venv/bin/activate
stdbuf -oL python -u scalping_realtime.py \
    --stocks $(cat /tmp/scalp_stocks.txt) \
    --user-id 2 \
    --mode simulation \
    --tp 3.0 \
    --sl 2.0 \
    --max-hold 900 \
    > /tmp/scalping_realtime.log 2>&1 &

# 3. 실시간 모니터링
tail -f /tmp/scalping_realtime.log
```

---

## 6. 백테스트 결과 요약

### 6.1 최적화 결과 (6일간, 세금/수수료 0.203% 반영)

| 설정 | 거래수 | 승률 | 손익 (세후) | 비고 |
|------|--------|------|------------|------|
| 기존 (익절2%, 5분) | 108건 | 48.1% | +3,211원 | 수수료 부담 큼 |
| **최적 (익절1.5%, 15분)** | **53건** | **54.7%** | **+10,625원** | **3배 개선** |

**최적 파라미터:**
- 익절: +1.5%
- 손절: -2.0%
- 최대 보유: 15분
- V2 진입조건: ≥ 60

### 6.2 청산 유형별 (세금/수수료 반영)

| 유형 | 건수 | 비율 | 손익 (세후) |
|------|------|------|------|
| 시간초과 | 95건 | 88% | -19,095원 |
| 익절 | 8건 | 7% | +34,790원 |
| 손절 | 5건 | 5% | -12,484원 |

> **참고**: 매도 시 0.203% 세금+수수료 차감됨 (10만원 거래당 약 200원)

### 6.3 개선 포인트

1. **진입 조건 강화** - 시간초과 88% 감소 필요
2. **변동성 필터** - 변동폭 큰 종목 우선
3. **익절 확률 개선** - V5 돌파 신호 추가 검토

---

## 7. 체크리스트

### 7.1 사전 준비 (전날)

- [ ] API 토큰 유효성 확인
- [ ] 종목 리스트 사전 선정
- [ ] 시뮬레이터 코드 테스트
- [ ] 로그 디렉토리 확인

### 7.2 당일 아침 (08:50)

- [ ] 서버 상태 확인
- [ ] 토큰 갱신
- [ ] 종목 리스트 최종 확인
- [ ] 시뮬레이터 시작

### 7.3 장중 모니터링

- [ ] 10:00 - 첫 1시간 성과 확인
- [ ] 12:00 - 오전 종합 확인
- [ ] 14:00 - 마감 대비 점검

### 7.4 장 마감 후

- [ ] 거래 내역 저장
- [ ] 성과 분석
- [ ] 개선점 도출

---

## 8. 비상 대응

### 8.1 시스템 오류

```bash
# 프로세스 강제 종료
pkill -f scalping_realtime

# 포지션 확인 (수동)
python -c "from trading.trade_logger import TradeLogger; ..."
```

### 8.2 급락장 대응

- 일일 손실 -5만원 도달 시 자동 중단
- 코스피 -2% 이상 하락 시 신규 진입 중단

---

*Document Version: 1.0*
*Last Updated: 2026-02-03*
