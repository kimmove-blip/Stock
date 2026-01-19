"""
자동매매 API 라우터
- 자동매매 현황, 설정, 거래 내역 조회
- 자동매매 권한이 있는 사용자만 접근 가능
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.dependencies import get_current_user_required
from trading.trade_logger import TradeLogger

router = APIRouter()


def get_trade_logger():
    """TradeLogger 인스턴스 생성"""
    return TradeLogger()


def check_auto_trade_permission(current_user: dict):
    """자동매매 권한 확인"""
    if not current_user.get('auto_trade_enabled'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="자동매매 권한이 없습니다"
        )


# ==================== 응답 모델 ====================

class HoldingResponse(BaseModel):
    """보유 종목"""
    stock_code: str
    stock_name: Optional[str]
    quantity: int
    avg_price: int
    buy_date: str
    buy_reason: Optional[str]
    current_price: Optional[int] = None
    profit_loss: Optional[int] = None
    profit_rate: Optional[float] = None


class TradeLogResponse(BaseModel):
    """거래 내역"""
    id: int
    trade_date: str
    trade_time: str
    stock_code: str
    stock_name: Optional[str]
    side: str  # buy/sell
    quantity: int
    price: Optional[int]
    amount: Optional[int]
    status: str
    trade_reason: Optional[str]
    profit_loss: Optional[int] = None
    profit_rate: Optional[float] = None


class SuggestionResponse(BaseModel):
    """매수 제안"""
    id: int
    stock_code: str
    stock_name: Optional[str]
    suggested_price: int
    quantity: int
    reason: Optional[str]
    score: Optional[float]
    status: str
    created_at: str


class PerformanceSummary(BaseModel):
    """성과 요약"""
    total_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    total_profit: int
    avg_profit_rate: float


class VirtualBalanceResponse(BaseModel):
    """가상 잔고"""
    total_balance: int
    available_balance: int
    invested_amount: int
    total_profit: int
    profit_rate: float


class AutoTradeStatusResponse(BaseModel):
    """자동매매 현황"""
    holdings: List[HoldingResponse]
    recent_trades: List[TradeLogResponse]
    pending_suggestions: List[SuggestionResponse]
    virtual_balance: Optional[VirtualBalanceResponse]
    performance: PerformanceSummary


# ==================== API 엔드포인트 ====================

@router.get("/status", response_model=AutoTradeStatusResponse)
async def get_auto_trade_status(
    current_user: dict = Depends(get_current_user_required)
):
    """자동매매 현황 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()

    # 보유 종목
    holdings_raw = logger.get_holdings()
    holdings = [HoldingResponse(
        stock_code=h['stock_code'],
        stock_name=h.get('stock_name'),
        quantity=h['quantity'],
        avg_price=h['avg_price'],
        buy_date=h['buy_date'],
        buy_reason=h.get('buy_reason')
    ) for h in holdings_raw]

    # 최근 거래 내역 (7일)
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    trades_raw = logger.get_trade_history(start_date=start_date)
    recent_trades = [TradeLogResponse(
        id=t['id'],
        trade_date=t['trade_date'],
        trade_time=t['trade_time'],
        stock_code=t['stock_code'],
        stock_name=t.get('stock_name'),
        side=t['side'],
        quantity=t['quantity'],
        price=t.get('price'),
        amount=t.get('amount'),
        status=t.get('status', 'completed'),
        trade_reason=t.get('trade_reason'),
        profit_loss=t.get('profit_loss'),
        profit_rate=t.get('profit_rate')
    ) for t in trades_raw]

    # 대기 중인 매수 제안
    suggestions_raw = logger.get_pending_suggestions()
    pending_suggestions = [SuggestionResponse(
        id=s['id'],
        stock_code=s['stock_code'],
        stock_name=s.get('stock_name'),
        suggested_price=s['suggested_price'],
        quantity=s['quantity'],
        reason=s.get('reason'),
        score=s.get('score'),
        status=s['status'],
        created_at=s['created_at']
    ) for s in suggestions_raw]

    # 가상 잔고
    virtual_raw = logger.get_virtual_balance()
    virtual_balance = None
    if virtual_raw:
        virtual_balance = VirtualBalanceResponse(
            total_balance=virtual_raw.get('total_balance', 0),
            available_balance=virtual_raw.get('available_balance', 0),
            invested_amount=virtual_raw.get('invested_amount', 0),
            total_profit=virtual_raw.get('total_profit', 0),
            profit_rate=virtual_raw.get('profit_rate', 0)
        )

    # 성과 요약
    stats = logger.get_statistics()
    performance = PerformanceSummary(
        total_trades=stats.get('total_trades', 0),
        win_count=stats.get('win_count', 0),
        loss_count=stats.get('loss_count', 0),
        win_rate=stats.get('win_rate', 0),
        total_profit=stats.get('total_profit', 0),
        avg_profit_rate=stats.get('avg_profit_rate', 0)
    )

    return AutoTradeStatusResponse(
        holdings=holdings,
        recent_trades=recent_trades,
        pending_suggestions=pending_suggestions,
        virtual_balance=virtual_balance,
        performance=performance
    )


@router.get("/holdings", response_model=List[HoldingResponse])
async def get_holdings(
    current_user: dict = Depends(get_current_user_required)
):
    """자동매매 보유 종목 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    holdings_raw = logger.get_holdings()

    return [HoldingResponse(
        stock_code=h['stock_code'],
        stock_name=h.get('stock_name'),
        quantity=h['quantity'],
        avg_price=h['avg_price'],
        buy_date=h['buy_date'],
        buy_reason=h.get('buy_reason')
    ) for h in holdings_raw]


@router.get("/trades", response_model=List[TradeLogResponse])
async def get_trade_history(
    days: int = 30,
    current_user: dict = Depends(get_current_user_required)
):
    """거래 내역 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    trades_raw = logger.get_trade_history(start_date=start_date)

    return [TradeLogResponse(
        id=t['id'],
        trade_date=t['trade_date'],
        trade_time=t['trade_time'],
        stock_code=t['stock_code'],
        stock_name=t.get('stock_name'),
        side=t['side'],
        quantity=t['quantity'],
        price=t.get('price'),
        amount=t.get('amount'),
        status=t.get('status', 'completed'),
        trade_reason=t.get('trade_reason'),
        profit_loss=t.get('profit_loss'),
        profit_rate=t.get('profit_rate')
    ) for t in trades_raw]


@router.get("/suggestions", response_model=List[SuggestionResponse])
async def get_suggestions(
    status: Optional[str] = None,  # pending, approved, rejected, expired, executed
    current_user: dict = Depends(get_current_user_required)
):
    """매수 제안 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()

    if status == 'pending':
        suggestions_raw = logger.get_pending_suggestions()
    elif status == 'approved':
        suggestions_raw = logger.get_approved_suggestions()
    else:
        # 전체 조회 (pending + approved)
        suggestions_raw = logger.get_pending_suggestions() + logger.get_approved_suggestions()

    return [SuggestionResponse(
        id=s['id'],
        stock_code=s['stock_code'],
        stock_name=s.get('stock_name'),
        suggested_price=s['suggested_price'],
        quantity=s['quantity'],
        reason=s.get('reason'),
        score=s.get('score'),
        status=s['status'],
        created_at=s['created_at']
    ) for s in suggestions_raw]


@router.get("/performance")
async def get_performance(
    days: int = 30,
    current_user: dict = Depends(get_current_user_required)
):
    """성과 분석"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    return logger.get_performance_summary(days=days)


# ==================== API 키 관리 ====================

class ApiKeyRequest(BaseModel):
    """API 키 설정 요청"""
    app_key: str
    app_secret: str
    account_number: str
    account_product_code: str = "01"
    is_mock: bool = True  # True: 모의투자, False: 실제투자


class ApiKeyResponse(BaseModel):
    """API 키 설정 응답"""
    app_key: Optional[str]
    account_number: Optional[str]
    account_product_code: Optional[str]
    is_connected: bool
    is_mock: bool = True  # 모의투자 여부


@router.get("/api-key", response_model=ApiKeyResponse)
async def get_api_key(
    current_user: dict = Depends(get_current_user_required)
):
    """API 키 설정 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    api_key_data = logger.get_api_key_settings(current_user.get('id'))

    if api_key_data:
        return ApiKeyResponse(
            app_key=api_key_data.get('app_key', '')[:8] + '****' if api_key_data.get('app_key') else None,
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_connected=True,
            is_mock=bool(api_key_data.get('is_mock', True))
        )

    return ApiKeyResponse(
        app_key=None,
        account_number=None,
        account_product_code=None,
        is_connected=False,
        is_mock=True
    )


@router.post("/api-key")
async def save_api_key(
    request: ApiKeyRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """API 키 저장"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.save_api_key_settings(
        user_id=current_user.get('id'),
        app_key=request.app_key,
        app_secret=request.app_secret,
        account_number=request.account_number,
        account_product_code=request.account_product_code,
        is_mock=request.is_mock
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API 키 저장에 실패했습니다"
        )

    mode_text = "모의투자" if request.is_mock else "실제투자"
    return {"message": f"API 키가 저장되었습니다 ({mode_text} 모드)", "is_connected": True, "is_mock": request.is_mock}


@router.delete("/api-key")
async def delete_api_key(
    current_user: dict = Depends(get_current_user_required)
):
    """API 키 삭제"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.delete_api_key_settings(current_user.get('id'))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API 키 삭제에 실패했습니다"
        )

    return {"message": "API 키가 삭제되었습니다", "is_connected": False}


# ==================== 계좌 현황 ====================

@router.get("/account")
async def get_account(
    current_user: dict = Depends(get_current_user_required)
):
    """실제/모의 증권 계좌 현황 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    api_key_data = logger.get_api_key_settings(current_user.get('id'))

    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다. 먼저 API 키를 등록해주세요."
        )

    # 계좌 조회 (KIS API 호출) - 모의/실전 구분
    try:
        is_mock = bool(api_key_data.get('is_mock', True))
        account_data = logger.get_real_account_balance(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=is_mock
        )
        account_data['is_mock'] = is_mock
        return account_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"계좌 조회 실패: {str(e)}"
        )


# ==================== 자동매매 설정 ====================

class AutoTradeSettingsRequest(BaseModel):
    """자동매매 설정 요청"""
    trade_mode: str = "manual"  # auto, semi, manual
    max_investment: int = 1000000
    max_per_stock: int = 200000
    stop_loss_rate: float = 5.0
    take_profit_rate: float = 10.0
    trading_enabled: bool = True
    trading_start_time: str = "09:00"
    trading_end_time: str = "15:20"


@router.get("/settings")
async def get_settings(
    current_user: dict = Depends(get_current_user_required)
):
    """자동매매 설정 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    settings = logger.get_auto_trade_settings(current_user.get('id'))

    # 기본값 반환
    if not settings:
        return {
            "trade_mode": "manual",
            "max_investment": 1000000,
            "max_per_stock": 200000,
            "stop_loss_rate": 5.0,
            "take_profit_rate": 10.0,
            "trading_enabled": True,
            "trading_start_time": "09:00",
            "trading_end_time": "15:20"
        }

    return settings


@router.post("/settings")
async def save_settings(
    request: AutoTradeSettingsRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """자동매매 설정 저장"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.save_auto_trade_settings(
        user_id=current_user.get('id'),
        settings=request.dict()
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="설정 저장에 실패했습니다"
        )

    return {"message": "설정이 저장되었습니다"}


# ==================== 매수 제안 승인/거부 ====================

@router.post("/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """매수 제안 승인"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.approve_suggestion(suggestion_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 제안을 찾을 수 없거나 이미 처리되었습니다"
        )

    return {"message": "매수 제안이 승인되었습니다", "status": "approved"}


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    suggestion_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """매수 제안 거부"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.reject_suggestion(suggestion_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 제안을 찾을 수 없거나 이미 처리되었습니다"
        )

    return {"message": "매수 제안이 거부되었습니다", "status": "rejected"}


# ==================== 매도 제안 ====================

@router.get("/sell-suggestions", response_model=List[SuggestionResponse])
async def get_sell_suggestions(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user_required)
):
    """매도 제안 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()

    if status == 'pending':
        suggestions_raw = logger.get_pending_sell_suggestions()
    elif status == 'approved':
        suggestions_raw = logger.get_approved_sell_suggestions()
    else:
        suggestions_raw = logger.get_pending_sell_suggestions() + logger.get_approved_sell_suggestions()

    return [SuggestionResponse(
        id=s['id'],
        stock_code=s['stock_code'],
        stock_name=s.get('stock_name'),
        suggested_price=s['suggested_price'],
        quantity=s['quantity'],
        reason=s.get('reason'),
        score=s.get('score'),
        status=s['status'],
        created_at=s['created_at']
    ) for s in suggestions_raw]


@router.post("/sell-suggestions/{suggestion_id}/approve")
async def approve_sell_suggestion(
    suggestion_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """매도 제안 승인"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.approve_sell_suggestion(suggestion_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 제안을 찾을 수 없거나 이미 처리되었습니다"
        )

    return {"message": "매도 제안이 승인되었습니다", "status": "approved"}


@router.post("/sell-suggestions/{suggestion_id}/reject")
async def reject_sell_suggestion(
    suggestion_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """매도 제안 거부"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    success = logger.reject_sell_suggestion(suggestion_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 제안을 찾을 수 없거나 이미 처리되었습니다"
        )

    return {"message": "매도 제안이 거부되었습니다", "status": "rejected"}


# ==================== 보유종목 진단 ====================

class DiagnosisHolding(BaseModel):
    """보유종목 진단 정보"""
    stock_code: str
    stock_name: Optional[str]
    quantity: int
    avg_price: int
    current_price: Optional[int]
    profit_rate: Optional[float]
    health_score: Optional[int]  # 건강 점수 (0-100)
    signal: Optional[str]  # strong_buy, buy, hold, sell, strong_sell
    target_price: Optional[int]  # 목표가
    stop_loss_price: Optional[int]  # 손절가
    ai_comment: Optional[str]  # AI 코멘트


class DiagnosisSummary(BaseModel):
    """진단 요약"""
    health_score: int  # 포트폴리오 전체 건강 점수
    total_profit_rate: float
    warning_count: int  # 주의 필요 종목 수


class DiagnosisResponse(BaseModel):
    """보유종목 진단 응답"""
    holdings: List[DiagnosisHolding]
    summary: DiagnosisSummary


@router.get("/diagnosis", response_model=DiagnosisResponse)
async def get_diagnosis(
    current_user: dict = Depends(get_current_user_required)
):
    """보유종목 AI 진단"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    api_key_data = logger.get_api_key_settings(current_user.get('id'))

    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

    # 실제 계좌 잔고 조회
    try:
        is_mock = bool(api_key_data.get('is_mock', True))
        account_data = logger.get_real_account_balance(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=is_mock
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"계좌 조회 실패: {str(e)}"
        )

    holdings = account_data.get('holdings', [])
    diagnosed_holdings = []
    total_health = 0
    warning_count = 0
    total_profit_rate = 0

    for h in holdings:
        profit_rate = h.get('profit_rate', 0)

        # 간단한 건강 점수 계산 (실제로는 더 복잡한 AI 분석 필요)
        health_score = 70  # 기본 점수
        signal = 'hold'

        if profit_rate >= 20:
            health_score = 90
            signal = 'sell'  # 익절 고려
        elif profit_rate >= 10:
            health_score = 85
            signal = 'hold'
        elif profit_rate >= 0:
            health_score = 75
            signal = 'hold'
        elif profit_rate >= -5:
            health_score = 60
            signal = 'hold'
            warning_count += 1
        elif profit_rate >= -10:
            health_score = 45
            signal = 'sell'
            warning_count += 1
        else:
            health_score = 30
            signal = 'strong_sell'
            warning_count += 1

        current_price = h.get('current_price', 0)
        avg_price = h.get('avg_price', 0)

        # 목표가/손절가 계산
        target_price = int(avg_price * 1.15) if avg_price else None  # 15% 수익
        stop_loss_price = int(avg_price * 0.93) if avg_price else None  # 7% 손실

        # AI 코멘트 생성
        ai_comment = None
        if profit_rate >= 20:
            ai_comment = "목표 수익률 달성. 일부 익절을 고려해보세요."
        elif profit_rate >= 10:
            ai_comment = "양호한 수익률입니다. 추세를 지켜보세요."
        elif profit_rate >= 0:
            ai_comment = "손익분기점 근처입니다. 시장 상황을 모니터링하세요."
        elif profit_rate >= -5:
            ai_comment = "소폭 하락 중입니다. 추가 매수 또는 홀딩 검토."
        elif profit_rate >= -10:
            ai_comment = "주의가 필요합니다. 손절 라인을 확인하세요."
        else:
            ai_comment = "손절을 고려해야 할 시점입니다."

        diagnosed_holdings.append(DiagnosisHolding(
            stock_code=h.get('stock_code', ''),
            stock_name=h.get('stock_name', ''),
            quantity=h.get('quantity', 0),
            avg_price=avg_price,
            current_price=current_price,
            profit_rate=profit_rate,
            health_score=health_score,
            signal=signal,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            ai_comment=ai_comment
        ))

        total_health += health_score
        total_profit_rate += profit_rate

    avg_health = int(total_health / len(holdings)) if holdings else 0
    avg_profit_rate = total_profit_rate / len(holdings) if holdings else 0

    return DiagnosisResponse(
        holdings=diagnosed_holdings,
        summary=DiagnosisSummary(
            health_score=avg_health,
            total_profit_rate=avg_profit_rate,
            warning_count=warning_count
        )
    )


# ==================== 수동 매매 ====================

class OrderRequest(BaseModel):
    """주문 요청"""
    stock_code: str
    side: str  # buy, sell
    quantity: int
    price: int = 0  # 0이면 시장가
    order_type: str = "limit"  # limit: 지정가, market: 시장가


class OrderResponse(BaseModel):
    """주문 응답"""
    order_id: Optional[str]
    message: str
    status: str


@router.post("/order", response_model=OrderResponse)
async def place_order(
    request: OrderRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """수동 주문 실행"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    api_key_data = logger.get_api_key_settings(current_user.get('id'))

    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

    try:
        is_mock = bool(api_key_data.get('is_mock', True))
        result = logger.place_order(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            stock_code=request.stock_code,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
            is_mock=is_mock
        )

        if result.get('success'):
            side_text = '매수' if request.side == 'buy' else '매도'
            return OrderResponse(
                order_id=result.get('order_id'),
                message=f"{side_text} 주문이 접수되었습니다.",
                status="submitted"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('message', '주문 실패')
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"주문 실패: {str(e)}"
        )


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    current_user: dict = Depends(get_current_user_required)
):
    """주문 취소"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    api_key_data = logger.get_api_key_settings(current_user.get('id'))

    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

    try:
        is_mock = bool(api_key_data.get('is_mock', True))
        result = logger.cancel_order(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            order_id=order_id,
            is_mock=is_mock
        )

        if result.get('success'):
            return {"message": "주문이 취소되었습니다.", "status": "cancelled"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('message', '주문 취소 실패')
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"주문 취소 실패: {str(e)}"
        )


# ==================== 미체결 내역 ====================

class PendingOrder(BaseModel):
    """미체결 주문"""
    order_id: str
    stock_code: str
    stock_name: Optional[str]
    side: str  # buy, sell
    order_type: str  # limit, market
    price: Optional[int]
    quantity: int
    remaining_quantity: int
    order_time: str


class PendingOrdersSummary(BaseModel):
    """미체결 요약"""
    buy_count: int
    sell_count: int
    buy_amount: int
    sell_amount: int


class PendingOrdersResponse(BaseModel):
    """미체결 내역 응답"""
    orders: List[PendingOrder]
    summary: PendingOrdersSummary


@router.get("/pending-orders", response_model=PendingOrdersResponse)
async def get_pending_orders(
    current_user: dict = Depends(get_current_user_required)
):
    """미체결 주문 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    api_key_data = logger.get_api_key_settings(current_user.get('id'))

    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

    try:
        is_mock = bool(api_key_data.get('is_mock', True))
        result = logger.get_pending_orders(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=is_mock
        )

        orders = []
        buy_count = 0
        sell_count = 0
        buy_amount = 0
        sell_amount = 0

        for o in result.get('orders', []):
            side = o.get('side', 'buy')
            price = o.get('price', 0)
            quantity = o.get('quantity', 0)

            if side == 'buy':
                buy_count += 1
                buy_amount += price * quantity
            else:
                sell_count += 1
                sell_amount += price * quantity

            orders.append(PendingOrder(
                order_id=o.get('order_id', ''),
                stock_code=o.get('stock_code', ''),
                stock_name=o.get('stock_name', ''),
                side=side,
                order_type=o.get('order_type', 'limit'),
                price=price,
                quantity=quantity,
                remaining_quantity=o.get('remaining_quantity', quantity),
                order_time=o.get('order_time', '')
            ))

        return PendingOrdersResponse(
            orders=orders,
            summary=PendingOrdersSummary(
                buy_count=buy_count,
                sell_count=sell_count,
                buy_amount=buy_amount,
                sell_amount=sell_amount
            )
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"미체결 조회 실패: {str(e)}"
        )
