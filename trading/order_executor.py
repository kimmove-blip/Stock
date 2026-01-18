"""
주문 실행 모듈
매수/매도 주문 실행 및 관리
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from api.services.kis_client import KISClient


class OrderExecutor:
    """주문 실행기"""

    def __init__(self, kis_client: KISClient):
        """
        Args:
            kis_client: KIS API 클라이언트
        """
        self.client = kis_client
        self.order_delay = 0.5  # 주문 간 딜레이 (초)

    def place_buy_order(
        self,
        stock_code: str,
        quantity: int,
        price: int = 0,
        order_type: str = "01"
    ) -> Dict:
        """
        매수 주문

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격 (시장가일 때 0)
            order_type: 주문 유형 ("00": 지정가, "01": 시장가)

        Returns:
            주문 결과
        """
        result = self.client.place_order(
            stock_code=stock_code,
            side="buy",
            quantity=quantity,
            price=price,
            order_type=order_type
        )
        time.sleep(self.order_delay)
        return result

    def place_sell_order(
        self,
        stock_code: str,
        quantity: int,
        price: int = 0,
        order_type: str = "01"
    ) -> Dict:
        """
        매도 주문

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격 (시장가일 때 0)
            order_type: 주문 유형 ("00": 지정가, "01": 시장가)

        Returns:
            주문 결과
        """
        result = self.client.place_order(
            stock_code=stock_code,
            side="sell",
            quantity=quantity,
            price=price,
            order_type=order_type
        )
        time.sleep(self.order_delay)
        return result

    def cancel_order(self, order_no: str, stock_code: str, quantity: int) -> Dict:
        """
        주문 취소

        Args:
            order_no: 주문번호
            stock_code: 종목코드
            quantity: 취소 수량

        Returns:
            취소 결과
        """
        result = self.client.cancel_order(
            order_no=order_no,
            stock_code=stock_code,
            quantity=quantity
        )
        return result

    def get_pending_orders(self) -> List[Dict]:
        """미체결 주문 조회"""
        return self.client.get_pending_orders() or []

    def cancel_all_pending_orders(self) -> List[Dict]:
        """모든 미체결 주문 취소"""
        pending = self.get_pending_orders()
        results = []

        for order in pending:
            if order.get("remaining_qty", 0) > 0:
                result = self.cancel_order(
                    order_no=order["order_no"],
                    stock_code=order["stock_code"],
                    quantity=order["remaining_qty"]
                )
                results.append(result)
                time.sleep(self.order_delay)

        return results

    def get_account_balance(self) -> Optional[Dict]:
        """계좌 잔고 조회"""
        return self.client.get_account_balance()

    def get_holdings(self) -> List[Dict]:
        """보유 종목 조회"""
        balance = self.get_account_balance()
        if balance:
            return balance.get("holdings", [])
        return []

    def get_cash_balance(self) -> int:
        """현금 잔고 조회"""
        balance = self.get_account_balance()
        if balance and balance.get("summary"):
            return balance["summary"].get("cash_balance", 0)
        return 0

    def get_current_price(self, stock_code: str) -> Optional[int]:
        """현재가 조회"""
        price_data = self.client.get_current_price(stock_code)
        if price_data:
            return price_data.get("current_price", 0)
        return None

    def calculate_buy_quantity(
        self,
        stock_code: str,
        investment_amount: int
    ) -> Tuple[int, int]:
        """
        투자금액 기준 매수 가능 수량 계산

        Args:
            stock_code: 종목코드
            investment_amount: 투자할 금액

        Returns:
            (매수 가능 수량, 현재가)
        """
        current_price = self.get_current_price(stock_code)
        if not current_price or current_price <= 0:
            return 0, 0

        quantity = investment_amount // current_price
        return quantity, current_price

    def execute_buy_orders(
        self,
        buy_list: List[Dict],
        investment_per_stock: int
    ) -> List[Dict]:
        """
        여러 종목 일괄 매수

        Args:
            buy_list: 매수할 종목 리스트 [{"stock_code": "005930", "stock_name": "삼성전자"}, ...]
            investment_per_stock: 종목당 투자금액

        Returns:
            주문 결과 리스트
        """
        results = []

        for item in buy_list:
            stock_code = item.get("stock_code")
            stock_name = item.get("stock_name", stock_code)

            quantity, current_price = self.calculate_buy_quantity(
                stock_code, investment_per_stock
            )

            if quantity <= 0:
                results.append({
                    "success": False,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "error": "매수 가능 수량 없음"
                })
                continue

            result = self.place_buy_order(
                stock_code=stock_code,
                quantity=quantity
            )
            result["stock_name"] = stock_name
            result["estimated_price"] = current_price
            results.append(result)

        return results

    def execute_sell_orders(self, sell_list: List[Dict]) -> List[Dict]:
        """
        여러 종목 일괄 매도

        Args:
            sell_list: 매도할 종목 리스트 [{"stock_code": "005930", "quantity": 10}, ...]

        Returns:
            주문 결과 리스트
        """
        results = []

        for item in sell_list:
            stock_code = item.get("stock_code")
            stock_name = item.get("stock_name", stock_code)
            quantity = item.get("quantity", 0)

            if quantity <= 0:
                results.append({
                    "success": False,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "error": "매도 수량 없음"
                })
                continue

            result = self.place_sell_order(
                stock_code=stock_code,
                quantity=quantity
            )
            result["stock_name"] = stock_name
            results.append(result)

        return results
