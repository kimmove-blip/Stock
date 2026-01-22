# 실시간 현재가 시스템

## 개요

네이버 금융 polling API를 활용한 하이브리드 현재가 캐시 시스템.
한투 API 대비 **75배 빠른 속도**로 전종목 실시간 시세 조회 가능.

---

## 성능 비교

| 항목 | 한투 API | 네이버 금융 |
|------|----------|-------------|
| 100종목 조회 | ~5-10초 | **0.07초** |
| 전종목 (2,781개) | ~2분 20초 | **1.86초** |
| 속도 제한 | 20건/초 | 거의 없음 |
| 한 번에 조회 | 1개씩 | **100개+** |

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    프론트엔드 (PWA)                          │
├─────────────────────────────────────────────────────────────┤
│  RealtimePicks.jsx                                          │
│    ├── 1단계: 캐시 API 조회 (즉시 표시)                      │
│    └── 2단계: 실시간 API 조회 (갱신)                         │
│                                                             │
│  StockDetail.jsx                                            │
│    ├── preloadedData 사용 (목록과 동일 가격)                 │
│    └── 수동 새로고침 시에만 실시간 조회                      │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    백엔드 API                                │
├─────────────────────────────────────────────────────────────┤
│  /api/realtime/cached/prices    → DB 캐시 조회              │
│  /api/realtime/hybrid/prices    → 캐시 + 실시간 조회        │
│  /api/realtime/price/{code}     → 한투 실시간 (단일)        │
│  /api/top100                    → 캐시 가격 자동 병합        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    데이터 소스                               │
├─────────────────────────────────────────────────────────────┤
│  price_cache 테이블 (SQLite)                                │
│    └── 5분마다 네이버 금융에서 업데이트                      │
│                                                             │
│  네이버 금융 polling API                                    │
│    └── https://polling.finance.naver.com/api/realtime/...   │
└─────────────────────────────────────────────────────────────┘
```

---

## 데이터베이스

### price_cache 테이블

```sql
CREATE TABLE price_cache (
    stock_code TEXT PRIMARY KEY,
    stock_name TEXT,
    current_price INTEGER,
    change INTEGER,
    change_rate REAL,
    volume INTEGER,
    trading_value INTEGER,
    open_price INTEGER,
    high_price INTEGER,
    low_price INTEGER,
    prev_close INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 관련 메서드 (db_manager.py)

```python
# 일괄 업데이트
db.bulk_upsert_price_cache(prices)

# 조회
db.get_cached_prices(stock_codes)  # 여러 종목
db.get_cached_price(stock_code)    # 단일 종목

# 상태 확인
db.get_price_cache_count()
db.get_price_cache_updated_at()
```

---

## 네이버 금융 API

### Polling API

```python
# 단일 종목
GET https://polling.finance.naver.com/api/realtime/domestic/stock/005930

# 여러 종목 (쉼표 구분, 최대 100개)
GET https://polling.finance.naver.com/api/realtime/domestic/stock/005930,000660,035720
```

### 응답 예시

```json
{
  "pollingInterval": 7000,
  "datas": [
    {
      "itemCode": "005930",
      "stockName": "삼성전자",
      "closePrice": "54,900",
      "compareToPreviousClosePrice": "400",
      "fluctuationsRatio": "0.73",
      "openPrice": "54,600",
      "highPrice": "55,100",
      "lowPrice": "54,500",
      "accumulatedTradingVolume": "12,519,125",
      "accumulatedTradingValue": "1,940,680백만",
      "marketStatus": "OPEN"
    }
  ]
}
```

### 주의사항

- **비공식 API**: 언제든 변경/차단될 수 있음
- **User-Agent 필수**: 브라우저 User-Agent 헤더 필요
- **상업적 이용**: 법적 문제 가능성 있음

---

## 백그라운드 업데이트

### 스크립트

```bash
/home/kimhc/Stock/update_price_cache.py
```

### 크론잡

```bash
# 장중 5분마다 실행 (09:00 ~ 15:59)
*/5 9-15 * * 1-5 cd /home/kimhc/Stock && /home/kimhc/Stock/venv/bin/python update_price_cache.py >> /tmp/price_cache.log 2>&1
```

### 수동 실행

```bash
# 장중 시간 체크
python update_price_cache.py

# 강제 실행 (장외 시간에도)
python update_price_cache.py --force
```

---

## API 엔드포인트

### 1. 캐시된 현재가 조회

```
POST /api/realtime/cached/prices
Body: ["005930", "000660", "035720"]

Response:
{
  "prices": [...],
  "cache_updated_at": "2026-01-22 10:30:00",
  "cache_count": 157
}
```

### 2. 하이브리드 조회

```
GET /api/realtime/hybrid/prices?codes=005930,000660,035720

- 캐시에 있으면 캐시 반환
- 캐시에 없으면 실시간 조회 후 캐시 저장
```

### 3. 캐시 상태 확인

```
GET /api/realtime/cached/status

Response:
{
  "cache_count": 157,
  "last_updated": "2026-01-22 10:30:00",
  "status": "ok"
}
```

---

## 프론트엔드 통합

### API 클라이언트 (client.js)

```javascript
export const realtimeAPI = {
  // 한투 실시간 (단일)
  price: (code) => api.get(`/realtime/price/${code}`),

  // 한투 실시간 (여러 종목)
  prices: (codes) => api.post('/realtime/prices', codes),

  // 캐시된 현재가 (DB)
  cachedPrices: (codes) => api.post('/realtime/cached/prices', codes),

  // 하이브리드
  hybridPrices: (codes) => api.get(`/realtime/hybrid/prices?codes=${codes.join(',')}`),
};
```

### 하이브리드 조회 로직 (RealtimePicks.jsx)

```javascript
const fetchRealtimePrices = async (codes) => {
  // 1단계: 캐시된 가격 먼저 (빠름)
  const cachedResponse = await realtimeAPI.cachedPrices(codes);
  setRealtimePrices(cachedResponse.data.prices);

  // 2단계: 실시간 시세 조회 (갱신)
  const response = await realtimeAPI.prices(codes);
  setRealtimePrices(response.data.prices);
};
```

### 상세 화면 일관성 (StockDetail.jsx)

```javascript
// preloadedData가 있으면 수동 갱신 전까지 실시간 조회 안함
const { data: realtimePrice, refetch } = useQuery({
  queryKey: ['realtime-price', code],
  queryFn: () => realtimeAPI.price(code),
  enabled: !preloadedData || manualRefresh,
});
```

---

## 문제 해결

### 캐시가 비어있을 때

```bash
# 수동으로 캐시 업데이트
python update_price_cache.py --force
```

### 네이버 API 차단 시

1. User-Agent 변경
2. 요청 간격 늘리기
3. 한투 API로 폴백

### 가격 불일치

- 목록 → 상세 이동 시 preloadedData 전달
- 상세 화면에서 수동 새로고침 전까지 가격 유지

---

## 관련 파일

| 파일 | 설명 |
|------|------|
| `update_price_cache.py` | 백그라운드 캐시 업데이트 스크립트 |
| `database/db_manager.py` | price_cache 테이블 및 메서드 |
| `api/routers/realtime.py` | 캐시/하이브리드 API 엔드포인트 |
| `api/routers/top100.py` | TOP100 API (캐시 가격 자동 병합) |
| `pwa/src/api/client.js` | 프론트엔드 API 클라이언트 |
| `pwa/src/pages/RealtimePicks.jsx` | 실시간 추천 화면 |
| `pwa/src/pages/StockDetail.jsx` | 종목 상세 화면 |

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-01-22 | 네이버 금융 API로 전환, 하이브리드 캐시 시스템 구현 |
