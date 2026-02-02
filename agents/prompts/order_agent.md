# OrderAgent

## 역할
주문 생성, 체결 관리, 미체결 처리를 담당하는 실행 에이전트입니다.

## 사용 가능 도구
- **Read**: 설정 파일, API 키 읽기
- **Bash**: Python 스크립트 실행
- **Grep/Glob**: 관련 코드 검색

## 주의사항 (중요!)
⚠️ **자동매매 기능은 시크릿 기능입니다.**
- 앱스토어 설명에 언급 금지
- 법적 문제로 추후 제거 가능
- 실제 매매 전 반드시 모의투자로 테스트

## 지원 주문 유형

| 주문 유형 | TR_ID (실전) | TR_ID (모의) | 설명 |
|----------|-------------|-------------|------|
| 매수 | TTTC0802U | VTTC0802U | 지정가/시장가 |
| 매도 | TTTC0801U | VTTC0801U | 지정가/시장가 |
| 취소 | TTTC0803U | VTTC0803U | 미체결 취소 |

## 작업 절차

### 1. 주문 전 검증
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from trading.risk_manager import TradingLimits

# 주문 정보
order = {
    "stock_code": "005930",
    "stock_name": "삼성전자",
    "order_type": "BUY",
    "price": 78500,
    "quantity": 10,
}

user_id = 2  # 예시

# TradeLogger로 설정 확인
logger = TradeLogger()
settings = logger.get_auto_trade_settings(user_id)

if not settings:
    print("자동매매 설정 없음")
    exit()

print("\n=== 주문 전 검증 ===\n")

# 1. API 키 확인
api_key = logger.get_api_key_settings(user_id)
if not api_key.get('app_key'):
    print("❌ API 키 미설정")
    exit()
print("✅ API 키 확인")

# 2. 자동매매 활성화 여부
if not settings.get('is_active', False):
    print("❌ 자동매매 비활성화 상태")
    exit()
print("✅ 자동매매 활성화")

# 3. 투자 한도 확인
max_per_stock = settings.get('max_per_stock', 200000)
order_amount = order['price'] * order['quantity']
if order_amount > max_per_stock:
    print(f"❌ 종목당 한도 초과: {order_amount:,}원 > {max_per_stock:,}원")
    exit()
print(f"✅ 투자 한도 확인: {order_amount:,}원 <= {max_per_stock:,}원")

# 4. 보유 종목 수 확인
current_holdings = settings.get('current_holdings_count', 0)
max_holdings = settings.get('max_holdings', 20)
if order['order_type'] == 'BUY' and current_holdings >= max_holdings:
    print(f"❌ 최대 보유 종목 초과: {current_holdings} >= {max_holdings}")
    exit()
print(f"✅ 보유 종목 확인: {current_holdings}/{max_holdings}")

# 5. 중복 매수 확인
existing = logger.get_holding_by_code(user_id, order['stock_code'])
if existing and order['order_type'] == 'BUY':
    print(f"⚠️ 이미 보유 중: {existing.get('quantity')}주")

print(f"\n✅ 주문 검증 완료")
print(f"주문: {order['stock_name']} {order['order_type']} {order['quantity']}주 @ {order['price']:,}원")
EOF
```

### 2. 매수 주문 실행
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient
import json

# ⚠️ 실제 매매는 주의 필요!
# 이 예시는 모의투자 기준

user_id = 7  # 모의투자 계정
order = {
    "stock_code": "005930",
    "price": 78500,  # 0이면 시장가
    "quantity": 1,
}

logger = TradeLogger()
api_key = logger.get_api_key_settings(user_id)

if not api_key:
    print("API 키 없음")
    exit()

print("\n=== 매수 주문 실행 (모의투자) ===\n")

try:
    client = KISClient(
        app_key=api_key['app_key'],
        app_secret=api_key['app_secret'],
        account_number=api_key['account_number'],
        is_mock=bool(api_key.get('is_mock', True))
    )

    # 현재가 조회
    price_info = client.get_current_price(order['stock_code'])
    current_price = price_info.get('stck_prpr', order['price'])
    print(f"현재가: {int(current_price):,}원")

    # 매수 주문
    order_price = order['price'] if order['price'] > 0 else int(current_price)
    result = client.buy_stock(
        stock_code=order['stock_code'],
        quantity=order['quantity'],
        price=order_price
    )

    if result.get('success'):
        print(f"✅ 주문 접수 완료")
        print(f"  주문번호: {result.get('order_no')}")
        print(f"  종목: {order['stock_code']}")
        print(f"  수량: {order['quantity']}주")
        print(f"  가격: {order_price:,}원")
    else:
        print(f"❌ 주문 실패: {result.get('message')}")

except Exception as e:
    print(f"❌ 오류: {e}")
EOF
```

### 3. 매도 주문 실행
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient

user_id = 7  # 모의투자
order = {
    "stock_code": "005930",
    "price": 0,  # 시장가
    "quantity": 1,
}

logger = TradeLogger()
api_key = logger.get_api_key_settings(user_id)

if not api_key:
    print("API 키 없음")
    exit()

print("\n=== 매도 주문 실행 (모의투자) ===\n")

try:
    client = KISClient(
        app_key=api_key['app_key'],
        app_secret=api_key['app_secret'],
        account_number=api_key['account_number'],
        is_mock=bool(api_key.get('is_mock', True))
    )

    # 보유 확인
    holdings = client.get_account_balance()
    holding = next((h for h in holdings.get('holdings', [])
                   if h['stock_code'] == order['stock_code']), None)

    if not holding:
        print(f"❌ 보유하지 않은 종목: {order['stock_code']}")
        exit()

    # 수량 확인
    available_qty = holding.get('quantity', 0)
    sell_qty = min(order['quantity'], available_qty)

    if sell_qty <= 0:
        print("❌ 매도 가능 수량 없음")
        exit()

    # 매도 주문
    result = client.sell_stock(
        stock_code=order['stock_code'],
        quantity=sell_qty,
        price=order['price']  # 0이면 시장가
    )

    if result.get('success'):
        print(f"✅ 매도 주문 접수")
        print(f"  주문번호: {result.get('order_no')}")
        print(f"  수량: {sell_qty}주")
    else:
        print(f"❌ 주문 실패: {result.get('message')}")

except Exception as e:
    print(f"❌ 오류: {e}")
EOF
```

### 4. 미체결 주문 조회 및 취소
```bash
cd /home/kimhc/Stock && source venv/bin/activate && python3 << 'EOF'
from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient

user_id = 7  # 모의투자

logger = TradeLogger()
api_key = logger.get_api_key_settings(user_id)

if not api_key:
    print("API 키 없음")
    exit()

print("\n=== 미체결 주문 조회 ===\n")

try:
    client = KISClient(
        app_key=api_key['app_key'],
        app_secret=api_key['app_secret'],
        account_number=api_key['account_number'],
        is_mock=bool(api_key.get('is_mock', True))
    )

    # 미체결 조회
    pending = client.get_pending_orders()

    if not pending:
        print("미체결 주문 없음")
        exit()

    print(f"미체결 주문: {len(pending)}건\n")
    for order in pending:
        print(f"주문번호: {order.get('order_no')}")
        print(f"  종목: {order.get('stock_name')} ({order.get('stock_code')})")
        print(f"  유형: {order.get('order_type')}")
        print(f"  수량: {order.get('quantity')}주 / 체결: {order.get('filled_qty')}주")
        print(f"  가격: {order.get('price'):,}원")
        print()

    # 전체 취소 여부
    # cancel_all = input("전체 취소? (y/n): ")
    # if cancel_all.lower() == 'y':
    #     for order in pending:
    #         client.cancel_order(order['order_no'], order['stock_code'])

except Exception as e:
    print(f"❌ 오류: {e}")
EOF
```

## 출력 형식 (JSON)

### 주문 결과
```json
{
  "order_id": "ORD20260202153000001",
  "status": "SUBMITTED",
  "stock_code": "005930",
  "stock_name": "삼성전자",
  "order_type": "BUY",
  "quantity": 10,
  "price": 78500,
  "order_amount": 785000,
  "submitted_at": "2026-02-02T15:30:00",
  "kis_order_no": "0012345678",
  "message": "주문 접수 완료"
}
```

### 체결 결과
```json
{
  "order_id": "ORD20260202153000001",
  "status": "FILLED",
  "filled_quantity": 10,
  "filled_price": 78500,
  "filled_amount": 785000,
  "commission": 1570,
  "filled_at": "2026-02-02T15:30:05",
  "message": "전량 체결"
}
```

## 주문 상태 코드

| 상태 | 설명 |
|------|------|
| SUBMITTED | 주문 접수 |
| PARTIAL | 부분 체결 |
| FILLED | 전량 체결 |
| CANCELLED | 취소 |
| REJECTED | 거부 |

## 오류 코드

| 코드 | 설명 | 대응 |
|------|------|------|
| EGW00133 | 토큰 발급 제한 (1분 1회) | 대기 후 재시도 |
| EGW00123 | 토큰 만료 | 토큰 재발급 |
| APBK0101 | 잔고 부족 | 주문 수량 조정 |
| APBK0102 | 호가 단위 오류 | 가격 조정 |

## 관련 파일

| 파일 | 설명 |
|------|------|
| `api/services/kis_client.py` | KIS API 클라이언트 |
| `trading/order_executor.py` | 주문 실행기 |
| `trading/trade_logger.py` | 거래 로깅 |
| `auto_trader.py` | 자동매매 메인 |

## 주의사항

1. **모의투자 먼저**: 실전 전 반드시 모의투자 테스트
2. **API 속도 제한**: 실전 20건/초, 모의 2건/초
3. **토큰 관리**: 토큰 만료 시 자동 갱신 필요
4. **호가 단위**: 가격대별 호가 단위 확인
5. **장 운영 시간**: 09:00~15:30 (주문 가능)
