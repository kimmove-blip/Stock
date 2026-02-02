"""
트레이딩 시스템 공통 예외 클래스

예외 계층 구조:
TradingError (기본)
├── MarketClosedError     - 장 마감 상태
├── InsufficientFundsError - 잔고 부족
├── OrderExecutionError   - 주문 실행 실패
├── DataLoadError         - 데이터 로딩 실패
├── ConfigurationError    - 설정 오류
└── APIError              - 외부 API 오류
    ├── TokenExpiredError - 토큰 만료
    └── RateLimitError    - 속도 제한 초과
"""

from typing import Optional, Dict, Any


class TradingError(Exception):
    """트레이딩 시스템 기본 예외 클래스"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지
            code: 에러 코드 (예: "E001", "MARKET_CLOSED")
            details: 추가 상세 정보
        """
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """예외 정보를 딕셔너리로 반환"""
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details
        }


class MarketClosedError(TradingError):
    """장 마감 상태 예외 (거래 시간 외)"""

    def __init__(
        self,
        message: str = "현재 장이 마감된 상태입니다",
        market_open: Optional[str] = None,
        market_close: Optional[str] = None
    ):
        details = {}
        if market_open:
            details["market_open"] = market_open
        if market_close:
            details["market_close"] = market_close

        super().__init__(message, code="MARKET_CLOSED", details=details)


class InsufficientFundsError(TradingError):
    """잔고 부족 예외"""

    def __init__(
        self,
        message: str = "주문을 실행하기에 잔고가 부족합니다",
        required: Optional[int] = None,
        available: Optional[int] = None,
        stock_code: Optional[str] = None
    ):
        details = {}
        if required is not None:
            details["required"] = required
        if available is not None:
            details["available"] = available
        if stock_code:
            details["stock_code"] = stock_code

        super().__init__(message, code="INSUFFICIENT_FUNDS", details=details)


class OrderExecutionError(TradingError):
    """주문 실행 실패 예외"""

    def __init__(
        self,
        message: str = "주문 실행에 실패했습니다",
        order_type: Optional[str] = None,  # "BUY" | "SELL"
        stock_code: Optional[str] = None,
        quantity: Optional[int] = None,
        price: Optional[int] = None,
        reason: Optional[str] = None
    ):
        details = {}
        if order_type:
            details["order_type"] = order_type
        if stock_code:
            details["stock_code"] = stock_code
        if quantity is not None:
            details["quantity"] = quantity
        if price is not None:
            details["price"] = price
        if reason:
            details["reason"] = reason

        super().__init__(message, code="ORDER_EXECUTION_FAILED", details=details)


class DataLoadError(TradingError):
    """데이터 로딩 실패 예외"""

    def __init__(
        self,
        message: str = "데이터 로딩에 실패했습니다",
        source: Optional[str] = None,  # "pykrx", "fdr", "csv", "api"
        data_type: Optional[str] = None,  # "ohlcv", "investor", "score"
        path: Optional[str] = None
    ):
        details = {}
        if source:
            details["source"] = source
        if data_type:
            details["data_type"] = data_type
        if path:
            details["path"] = path

        super().__init__(message, code="DATA_LOAD_FAILED", details=details)


class ConfigurationError(TradingError):
    """설정 오류 예외"""

    def __init__(
        self,
        message: str = "설정 오류가 발생했습니다",
        config_key: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None
    ):
        details = {}
        if config_key:
            details["config_key"] = config_key
        if expected_type:
            details["expected_type"] = expected_type
        if actual_value is not None:
            details["actual_value"] = str(actual_value)

        super().__init__(message, code="CONFIGURATION_ERROR", details=details)


class APIError(TradingError):
    """외부 API 오류 예외 (한투 API 등)"""

    def __init__(
        self,
        message: str = "API 호출에 실패했습니다",
        api_name: Optional[str] = None,  # "KIS", "pykrx"
        status_code: Optional[int] = None,
        response_code: Optional[str] = None,  # 한투 응답 코드 (예: "EGW00123")
        endpoint: Optional[str] = None
    ):
        details = {}
        if api_name:
            details["api_name"] = api_name
        if status_code is not None:
            details["status_code"] = status_code
        if response_code:
            details["response_code"] = response_code
        if endpoint:
            details["endpoint"] = endpoint

        super().__init__(message, code="API_ERROR", details=details)


class TokenExpiredError(APIError):
    """토큰 만료 예외 (한투 API 토큰)"""

    def __init__(
        self,
        message: str = "API 토큰이 만료되었습니다",
        api_name: str = "KIS",
        response_code: Optional[str] = None
    ):
        super().__init__(
            message=message,
            api_name=api_name,
            response_code=response_code
        )
        self.code = "TOKEN_EXPIRED"


class RateLimitError(APIError):
    """속도 제한 초과 예외"""

    def __init__(
        self,
        message: str = "API 요청 속도 제한을 초과했습니다",
        api_name: str = "KIS",
        retry_after: Optional[int] = None,  # 재시도까지 대기 시간 (초)
        response_code: Optional[str] = None
    ):
        super().__init__(
            message=message,
            api_name=api_name,
            response_code=response_code
        )
        self.code = "RATE_LIMIT_EXCEEDED"
        if retry_after is not None:
            self.details["retry_after"] = retry_after


# 예외 코드 상수
class ErrorCodes:
    """에러 코드 상수"""
    # 시장 관련
    MARKET_CLOSED = "MARKET_CLOSED"
    MARKET_HOLIDAY = "MARKET_HOLIDAY"

    # 주문 관련
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    ORDER_EXECUTION_FAILED = "ORDER_EXECUTION_FAILED"
    ORDER_CANCELED = "ORDER_CANCELED"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_PRICE = "INVALID_PRICE"

    # 데이터 관련
    DATA_LOAD_FAILED = "DATA_LOAD_FAILED"
    DATA_NOT_FOUND = "DATA_NOT_FOUND"
    DATA_STALE = "DATA_STALE"

    # API 관련
    API_ERROR = "API_ERROR"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # 설정 관련
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    MISSING_API_KEY = "MISSING_API_KEY"


# 한투 API 에러 코드 매핑
KIS_ERROR_CODES = {
    "EGW00123": ("토큰 만료", TokenExpiredError),
    "EGW00133": ("토큰 발급 제한 (1분 1회)", RateLimitError),
    "APBK0919": ("잔고 부족", InsufficientFundsError),
    "APBK0013": ("주문 수량 오류", OrderExecutionError),
    "APBK0014": ("주문 가격 오류", OrderExecutionError),
}


def raise_for_kis_error(response_code: str, message: str = "") -> None:
    """한투 API 응답 코드에 따른 예외 발생

    Args:
        response_code: 한투 API 응답 코드
        message: 추가 에러 메시지

    Raises:
        적절한 예외 클래스
    """
    if response_code in KIS_ERROR_CODES:
        error_msg, error_cls = KIS_ERROR_CODES[response_code]
        full_msg = f"{error_msg}: {message}" if message else error_msg
        raise error_cls(message=full_msg, response_code=response_code)

    # 알려지지 않은 에러 코드
    raise APIError(
        message=message or f"한투 API 오류: {response_code}",
        api_name="KIS",
        response_code=response_code
    )
