"""
KIS WebSocket 클라이언트

실시간 체결가(H0STCNT0)와 호가(H0STASP0) 데이터 스트리밍

사용법:
    from trading.realtime import KISWebSocket

    async def on_execution(data):
        print(f"체결: {data.stock_code} @ {data.price}")

    async def on_orderbook(data):
        print(f"호가: {data.stock_code} 매수잔량={data.total_bid_qty}")

    ws = KISWebSocket(app_key, app_secret, is_virtual=False)
    ws.on_execution = on_execution
    ws.on_orderbook = on_orderbook

    await ws.connect()
    await ws.subscribe(['005930', '035420'])
    await ws.run_forever()
"""

import asyncio
import json
import websockets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict, Set, Any
from collections import deque
import aiohttp


@dataclass
class ExecutionData:
    """실시간 체결 데이터 (H0STCNT0)"""
    stock_code: str
    stock_name: str
    exec_time: str           # 체결시간 HHMMSS
    price: int               # 체결가
    change: int              # 전일대비
    change_rate: float       # 등락률
    change_sign: str         # 부호 (1:상한, 2:상승, 3:보합, 4:하한, 5:하락)
    exec_volume: int         # 체결수량
    cumulative_volume: int   # 누적거래량
    cumulative_amount: int   # 누적거래대금
    weighted_avg_price: int  # 가중평균가
    open_price: int          # 시가
    high_price: int          # 고가
    low_price: int           # 저가
    ask_price1: int          # 매도호가1
    bid_price1: int          # 매수호가1
    exec_strength: float     # 체결강도
    total_ask_qty: int       # 총매도잔량
    total_bid_qty: int       # 총매수잔량
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrderbookData:
    """실시간 호가 데이터 (H0STASP0)"""
    stock_code: str
    exec_time: str           # 호가시간 HHMMSS

    # 매도호가 (1~10)
    ask_prices: List[int] = field(default_factory=list)   # 매도호가
    ask_volumes: List[int] = field(default_factory=list)  # 매도잔량

    # 매수호가 (1~10)
    bid_prices: List[int] = field(default_factory=list)   # 매수호가
    bid_volumes: List[int] = field(default_factory=list)  # 매수잔량

    total_ask_qty: int = 0   # 총매도잔량
    total_bid_qty: int = 0   # 총매수잔량
    total_ask_cnt: int = 0   # 총매도건수
    total_bid_cnt: int = 0   # 총매수건수

    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def imbalance_ratio(self) -> float:
        """호가 불균형 비율 (매도/매수)"""
        if self.total_bid_qty == 0:
            return float('inf')
        return self.total_ask_qty / self.total_bid_qty

    @property
    def is_ask_dominant(self) -> bool:
        """매도 우위 여부 (매도잔량 > 매수잔량 * 2)"""
        return self.total_ask_qty > self.total_bid_qty * 2


@dataclass
class RealtimeData:
    """통합 실시간 데이터"""
    stock_code: str
    execution: Optional[ExecutionData] = None
    orderbook: Optional[OrderbookData] = None
    timestamp: datetime = field(default_factory=datetime.now)


class KISWebSocket:
    """KIS WebSocket 클라이언트"""

    # WebSocket URL
    VIRTUAL_WS_URL = "ws://ops.koreainvestment.com:21000"    # 모의투자
    REAL_WS_URL = "ws://ops.koreainvestment.com:31000"        # 실전투자

    # TR_ID
    TR_EXECUTION = "H0STCNT0"  # 실시간 체결가
    TR_ORDERBOOK = "H0STASP0"  # 실시간 호가

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        is_virtual: bool = True,
        max_reconnect: int = 5,
        reconnect_delay: float = 3.0,
    ):
        """
        Args:
            app_key: KIS API 앱키
            app_secret: KIS API 시크릿
            is_virtual: 모의투자 여부
            max_reconnect: 최대 재연결 시도 횟수
            reconnect_delay: 재연결 대기 시간(초)
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.is_virtual = is_virtual
        self.max_reconnect = max_reconnect
        self.reconnect_delay = reconnect_delay

        self.ws_url = self.VIRTUAL_WS_URL if is_virtual else self.REAL_WS_URL
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._approval_key: Optional[str] = None
        self._subscribed: Set[str] = set()
        self._running = False
        self._reconnect_count = 0

        # 콜백 함수
        self.on_execution: Optional[Callable[[ExecutionData], Any]] = None
        self.on_orderbook: Optional[Callable[[OrderbookData], Any]] = None
        self.on_error: Optional[Callable[[Exception], Any]] = None
        self.on_connect: Optional[Callable[[], Any]] = None
        self.on_disconnect: Optional[Callable[[], Any]] = None

        # 데이터 버퍼 (최근 데이터 저장)
        self._execution_buffer: Dict[str, deque] = {}
        self._orderbook_buffer: Dict[str, OrderbookData] = {}

    async def _get_approval_key(self) -> str:
        """WebSocket 접속키 발급"""
        if self._approval_key:
            return self._approval_key

        url = "https://openapi.koreainvestment.com:9443/oauth2/Approval"
        if self.is_virtual:
            url = "https://openapivts.koreainvestment.com:29443/oauth2/Approval"

        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                data = await resp.json()
                self._approval_key = data.get("approval_key")
                if not self._approval_key:
                    raise ValueError(f"WebSocket 접속키 발급 실패: {data}")
                print(f"[WS] 접속키 발급 완료")
                return self._approval_key

    async def connect(self) -> bool:
        """WebSocket 연결"""
        try:
            approval_key = await self._get_approval_key()

            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10,
            )

            self._running = True
            self._reconnect_count = 0
            print(f"[WS] 연결 성공: {self.ws_url}")

            if self.on_connect:
                await self._call_handler(self.on_connect)

            # 기존 구독 복구
            if self._subscribed:
                await self._resubscribe()

            return True

        except Exception as e:
            print(f"[WS] 연결 실패: {e}")
            if self.on_error:
                await self._call_handler(self.on_error, e)
            return False

    async def disconnect(self):
        """연결 종료"""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            print("[WS] 연결 종료")

        if self.on_disconnect:
            await self._call_handler(self.on_disconnect)

    async def subscribe(self, stock_codes: List[str], include_orderbook: bool = True):
        """
        종목 구독

        Args:
            stock_codes: 종목코드 리스트
            include_orderbook: 호가 데이터도 구독할지 여부
        """
        if not self._ws:
            raise RuntimeError("WebSocket 미연결")

        for code in stock_codes:
            # 체결가 구독
            await self._send_subscribe(self.TR_EXECUTION, code)
            self._subscribed.add(f"{self.TR_EXECUTION}:{code}")

            # 호가 구독
            if include_orderbook:
                await self._send_subscribe(self.TR_ORDERBOOK, code)
                self._subscribed.add(f"{self.TR_ORDERBOOK}:{code}")

            # 버퍼 초기화
            if code not in self._execution_buffer:
                self._execution_buffer[code] = deque(maxlen=1000)

            print(f"[WS] 구독: {code}")

    async def unsubscribe(self, stock_codes: List[str]):
        """종목 구독 해제"""
        if not self._ws:
            return

        for code in stock_codes:
            await self._send_unsubscribe(self.TR_EXECUTION, code)
            await self._send_unsubscribe(self.TR_ORDERBOOK, code)
            self._subscribed.discard(f"{self.TR_EXECUTION}:{code}")
            self._subscribed.discard(f"{self.TR_ORDERBOOK}:{code}")
            print(f"[WS] 구독 해제: {code}")

    async def _send_subscribe(self, tr_id: str, stock_code: str):
        """구독 요청 전송"""
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",  # 개인
                "tr_type": "1",   # 1: 등록
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": stock_code
                }
            }
        }
        await self._ws.send(json.dumps(msg))

    async def _send_unsubscribe(self, tr_id: str, stock_code: str):
        """구독 해제 요청 전송"""
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "2",   # 2: 해제
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": stock_code
                }
            }
        }
        await self._ws.send(json.dumps(msg))

    async def _resubscribe(self):
        """재연결 후 구독 복구"""
        for key in list(self._subscribed):
            tr_id, stock_code = key.split(":")
            await self._send_subscribe(tr_id, stock_code)
        print(f"[WS] 구독 복구: {len(self._subscribed)}건")

    async def run_forever(self):
        """메시지 수신 루프"""
        while self._running:
            try:
                if not self._ws:
                    if self._reconnect_count < self.max_reconnect:
                        self._reconnect_count += 1
                        print(f"[WS] 재연결 시도 ({self._reconnect_count}/{self.max_reconnect})")
                        await asyncio.sleep(self.reconnect_delay)
                        await self.connect()
                    else:
                        print("[WS] 최대 재연결 횟수 초과")
                        break
                    continue

                message = await self._ws.recv()
                await self._handle_message(message)

            except websockets.ConnectionClosed as e:
                print(f"[WS] 연결 끊김: {e}")
                self._ws = None
                if self.on_disconnect:
                    await self._call_handler(self.on_disconnect)

            except Exception as e:
                print(f"[WS] 오류: {e}")
                if self.on_error:
                    await self._call_handler(self.on_error, e)

    async def _handle_message(self, message: str):
        """메시지 처리"""
        # JSON 형식 응답 (구독 응답 등)
        if message.startswith('{'):
            data = json.loads(message)
            header = data.get("header", {})
            if header.get("tr_id") == "PINGPONG":
                # PONG 응답
                await self._ws.send(message)
                return
            # 구독 응답 로그
            body = data.get("body", {})
            if "rt_cd" in body:
                rt_cd = body.get("rt_cd")
                msg1 = body.get("msg1", "")
                if rt_cd != "0":
                    print(f"[WS] 응답 오류: {msg1}")
            return

        # 파이프(|) 구분 실시간 데이터
        parts = message.split("|")
        if len(parts) < 4:
            return

        # 헤더 파싱: 암호화여부|TR_ID|데이터건수|데이터
        encrypted = parts[0]
        tr_id = parts[1]
        count = int(parts[2])
        raw_data = parts[3]

        if tr_id == self.TR_EXECUTION:
            await self._parse_execution(raw_data)
        elif tr_id == self.TR_ORDERBOOK:
            await self._parse_orderbook(raw_data)

    async def _parse_execution(self, raw_data: str):
        """체결 데이터 파싱 (H0STCNT0)"""
        fields = raw_data.split("^")
        if len(fields) < 40:
            return

        try:
            data = ExecutionData(
                stock_code=fields[0],
                stock_name=fields[1] if len(fields) > 1 else "",
                exec_time=fields[2],
                price=int(fields[3] or 0),
                change=int(fields[5] or 0),
                change_rate=float(fields[6] or 0),
                change_sign=fields[4],
                exec_volume=int(fields[8] or 0),
                cumulative_volume=int(fields[9] or 0),
                cumulative_amount=int(fields[10] or 0),
                weighted_avg_price=int(fields[11] or 0),
                open_price=int(fields[12] or 0),
                high_price=int(fields[13] or 0),
                low_price=int(fields[14] or 0),
                ask_price1=int(fields[16] or 0),
                bid_price1=int(fields[17] or 0),
                exec_strength=float(fields[19] or 0),
                total_ask_qty=int(fields[28] or 0),
                total_bid_qty=int(fields[29] or 0),
            )

            # 버퍼에 저장
            if data.stock_code in self._execution_buffer:
                self._execution_buffer[data.stock_code].append(data)

            # 콜백 호출
            if self.on_execution:
                await self._call_handler(self.on_execution, data)

        except (ValueError, IndexError) as e:
            print(f"[WS] 체결 파싱 오류: {e}")

    async def _parse_orderbook(self, raw_data: str):
        """호가 데이터 파싱 (H0STASP0)"""
        fields = raw_data.split("^")
        if len(fields) < 50:
            return

        try:
            stock_code = fields[0]
            exec_time = fields[1]

            # 매도호가 1~10
            ask_prices = [int(fields[i] or 0) for i in range(3, 23, 2)]
            ask_volumes = [int(fields[i] or 0) for i in range(4, 24, 2)]

            # 매수호가 1~10
            bid_prices = [int(fields[i] or 0) for i in range(23, 43, 2)]
            bid_volumes = [int(fields[i] or 0) for i in range(24, 44, 2)]

            data = OrderbookData(
                stock_code=stock_code,
                exec_time=exec_time,
                ask_prices=ask_prices,
                ask_volumes=ask_volumes,
                bid_prices=bid_prices,
                bid_volumes=bid_volumes,
                total_ask_qty=int(fields[43] or 0),
                total_bid_qty=int(fields[44] or 0),
                total_ask_cnt=int(fields[47] or 0) if len(fields) > 47 else 0,
                total_bid_cnt=int(fields[48] or 0) if len(fields) > 48 else 0,
            )

            # 버퍼에 저장
            self._orderbook_buffer[stock_code] = data

            # 콜백 호출
            if self.on_orderbook:
                await self._call_handler(self.on_orderbook, data)

        except (ValueError, IndexError) as e:
            print(f"[WS] 호가 파싱 오류: {e}")

    async def _call_handler(self, handler: Callable, *args):
        """콜백 함수 호출 (동기/비동기 모두 지원)"""
        try:
            result = handler(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"[WS] 핸들러 오류: {e}")

    def get_recent_executions(self, stock_code: str, count: int = 100) -> List[ExecutionData]:
        """최근 체결 데이터 조회"""
        if stock_code not in self._execution_buffer:
            return []
        buffer = self._execution_buffer[stock_code]
        return list(buffer)[-count:]

    def get_orderbook(self, stock_code: str) -> Optional[OrderbookData]:
        """현재 호가 데이터 조회"""
        return self._orderbook_buffer.get(stock_code)

    def get_execution_strength_history(
        self,
        stock_code: str,
        seconds: int = 10
    ) -> List[float]:
        """최근 N초간 체결강도 히스토리"""
        executions = self.get_recent_executions(stock_code, 1000)
        if not executions:
            return []

        cutoff = datetime.now().timestamp() - seconds
        return [
            e.exec_strength
            for e in executions
            if e.timestamp.timestamp() > cutoff
        ]
