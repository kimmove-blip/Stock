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
import httpx

router = APIRouter()

async def get_stock_ai_score(stock_code: str) -> dict:
    """종목의 AI 기술분석 점수 조회"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:8000/api/stocks/{stock_code}/analysis",
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'score': data.get('score', 50),
                    'opinion': data.get('opinion', '관망'),
                    'comment': data.get('comment', '')
                }
    except Exception as e:
        print(f"AI 점수 조회 실패 [{stock_code}]: {e}")
    return {'score': 50, 'opinion': '관망', 'comment': ''}


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
    user_id = current_user.get('id')

    # API 키가 없으면 빈 데이터 반환 (다른 사용자 데이터 노출 방지)
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return AutoTradeStatusResponse(
            holdings=[],
            recent_trades=[],
            pending_suggestions=[],
            virtual_balance=None,
            performance=PerformanceSummary(
                total_trades=0, win_count=0, loss_count=0,
                win_rate=0, total_profit=0, avg_profit_rate=0
            )
        )

    # 보유 종목 (user_id로 필터링)
    holdings_raw = logger.get_holdings(user_id=user_id)
    holdings = [HoldingResponse(
        stock_code=h['stock_code'],
        stock_name=h.get('stock_name'),
        quantity=h['quantity'],
        avg_price=h['avg_price'],
        buy_date=h['buy_date'],
        buy_reason=h.get('buy_reason')
    ) for h in holdings_raw]

    # 최근 거래 내역 (7일, user_id로 필터링)
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    trades_raw = logger.get_trade_history(user_id=user_id, start_date=start_date)
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

    # 대기 중인 매수 제안 (user_id로 필터링)
    suggestions_raw = logger.get_pending_suggestions(user_id=user_id)
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

    # 가상 잔고 (user_id로 필터링)
    virtual_raw = logger.get_virtual_balance(user_id=user_id)
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
    user_id = current_user.get('id')

    # API 키가 없으면 빈 데이터 반환 (다른 사용자 데이터 노출 방지)
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return []

    # user_id로 필터링하여 해당 사용자의 보유 종목만 조회
    holdings_raw = logger.get_holdings(user_id=user_id)

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
    days: int = 7,
    current_user: dict = Depends(get_current_user_required)
):
    """거래 내역 조회 (실시간 증권사 API)"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    user_id = current_user.get('id')

    # API 키 확인
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return []

    # 실시간 증권사 API에서 체결내역 조회
    try:
        from api.services.kis_client import KISClient

        client = KISClient(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=bool(api_key_data.get('is_mock', True))
        )

        # 조회 기간 설정
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        history = client.get_order_history(start_date=start_date, end_date=end_date)

        if not history:
            return []

        # 체결된 주문만 필터링 (체결수량 > 0)
        history = [h for h in history if h.get('executed_qty', 0) > 0]

        if not history:
            return []

        # 주문번호 목록 추출
        order_nos = [h.get('order_no') for h in history if h.get('order_no')]

        # DB에서 매매사유 조회 (order_no로 매칭)
        trade_reasons = {}
        if order_nos:
            trade_reasons = logger.get_trade_reasons_by_order_nos(order_nos, user_id)

        # 종목별 매수 평균가 계산 (매도 손익 계산용)
        from collections import defaultdict
        stock_buys = defaultdict(lambda: {'total_amount': 0, 'total_qty': 0})
        for h in history:
            if h.get('side') == 'buy':
                code = h.get('stock_code')
                qty = h.get('executed_qty', 0)
                price = h.get('executed_price', 0)
                stock_buys[code]['total_amount'] += qty * price
                stock_buys[code]['total_qty'] += qty

        # 종목별 매수 평균가
        stock_avg_buy_price = {}
        for code, data in stock_buys.items():
            if data['total_qty'] > 0:
                stock_avg_buy_price[code] = data['total_amount'] / data['total_qty']

        # 응답 형식 변환 (매매사유 병합 + 매도 손익 계산)
        result = []
        for idx, h in enumerate(history):
            # 날짜 형식 변환 (YYYYMMDD -> YYYY-MM-DD)
            order_date = h.get('order_date', '')
            if len(order_date) == 8:
                order_date = f"{order_date[:4]}-{order_date[4:6]}-{order_date[6:8]}"

            # 주문번호로 매매사유 조회
            order_no = h.get('order_no', '')
            reason_data = trade_reasons.get(order_no, {})

            # 매도인 경우 손익 계산
            profit_loss = reason_data.get('profit_loss')
            profit_rate = reason_data.get('profit_rate')

            if h.get('side') == 'sell' and profit_loss is None:
                code = h.get('stock_code')
                sell_price = h.get('executed_price', 0)
                sell_qty = h.get('executed_qty', 0)
                avg_buy_price = stock_avg_buy_price.get(code, 0)

                if avg_buy_price > 0 and sell_price > 0:
                    profit_loss = int((sell_price - avg_buy_price) * sell_qty)
                    profit_rate = round(((sell_price / avg_buy_price) - 1) * 100, 2)

            result.append(TradeLogResponse(
                id=idx + 1,
                trade_date=order_date,
                trade_time="",
                stock_code=h.get('stock_code', ''),
                stock_name=h.get('stock_name'),
                side=h.get('side', 'buy'),
                quantity=h.get('executed_qty', 0),
                price=h.get('executed_price'),
                amount=h.get('executed_amount'),
                status='completed' if h.get('executed_qty', 0) > 0 else 'pending',
                trade_reason=reason_data.get('trade_reason'),
                profit_loss=profit_loss,
                profit_rate=profit_rate
            ))

        return result

    except Exception as e:
        import traceback
        print(f"[거래내역 조회 에러] {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"거래내역 조회 실패: {str(e)}"
        )


@router.get("/suggestions", response_model=List[SuggestionResponse])
async def get_suggestions(
    status: Optional[str] = None,  # pending, approved, rejected, expired, executed
    current_user: dict = Depends(get_current_user_required)
):
    """매수 제안 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    user_id = current_user.get('id')

    # API 키가 없으면 빈 데이터 반환 (다른 사용자 데이터 노출 방지)
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return []

    # user_id로 필터링하여 해당 사용자의 제안만 조회
    if status == 'pending':
        suggestions_raw = logger.get_pending_suggestions(user_id=user_id)
    elif status == 'approved':
        suggestions_raw = logger.get_approved_suggestions(user_id=user_id)
    else:
        # 전체 조회 (pending + approved)
        suggestions_raw = logger.get_pending_suggestions(user_id=user_id) + logger.get_approved_suggestions(user_id=user_id)

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
    """성과 분석 (실시간 증권사 API 기반)"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    user_id = current_user.get('id')

    empty_response = {
        "period_days": days,
        "total_trades": 0,
        "buy_count": 0,
        "sell_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "total_profit": 0,
        "avg_profit_rate": 0.0,
        "max_profit": 0,
        "max_loss": 0,
        "realized_trades": [],
        "initial_investment": 0,
        "current_total_asset": 0,
        "total_profit_from_initial": 0,
        "total_profit_rate_from_initial": 0.0
    }

    # API 키가 없으면 빈 데이터 반환
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return empty_response

    # 초기투자금 조회
    settings = logger.get_auto_trade_settings(user_id)
    initial_investment = settings.get('initial_investment', 0) if settings else 0

    try:
        from api.services.kis_client import KISClient
        from collections import defaultdict

        client = KISClient(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=bool(api_key_data.get('is_mock', True))
        )

        # 조회 기간 설정
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # 체결 내역 조회
        history = client.get_order_history(start_date=start_date, end_date=end_date)
        history = [h for h in history if h.get('executed_qty', 0) > 0]

        if not history:
            return empty_response

        # 매수/매도 분류
        buys = [h for h in history if h.get('side') == 'buy']
        sells = [h for h in history if h.get('side') == 'sell']

        # 종목별 매수/매도 분석
        stock_trades = defaultdict(lambda: {'buys': [], 'sells': [], 'name': ''})
        for h in history:
            code = h.get('stock_code')
            name = h.get('stock_name', '')
            if h.get('side') == 'buy':
                stock_trades[code]['buys'].append(h)
            else:
                stock_trades[code]['sells'].append(h)
            stock_trades[code]['name'] = name

        # 실현 손익 계산 (매도된 종목)
        realized_trades = []
        total_profit = 0
        win_count = 0
        loss_count = 0
        max_profit = 0
        max_loss = 0
        profit_rates = []

        for code, trades in stock_trades.items():
            if trades['sells']:
                name = trades['name']

                # 매수 평균가
                total_buy_amount = sum(h.get('executed_qty', 0) * h.get('executed_price', 0) for h in trades['buys'])
                total_buy_qty = sum(h.get('executed_qty', 0) for h in trades['buys'])
                avg_buy_price = total_buy_amount / total_buy_qty if total_buy_qty > 0 else 0

                # 매도 평균가
                total_sell_amount = sum(h.get('executed_qty', 0) * h.get('executed_price', 0) for h in trades['sells'])
                total_sell_qty = sum(h.get('executed_qty', 0) for h in trades['sells'])
                avg_sell_price = total_sell_amount / total_sell_qty if total_sell_qty > 0 else 0

                # 실현 손익
                profit = int((avg_sell_price - avg_buy_price) * total_sell_qty)
                profit_rate = ((avg_sell_price / avg_buy_price) - 1) * 100 if avg_buy_price > 0 else 0

                total_profit += profit
                profit_rates.append(profit_rate)

                if profit > 0:
                    win_count += 1
                    max_profit = max(max_profit, profit)
                elif profit < 0:
                    loss_count += 1
                    max_loss = min(max_loss, profit)

                realized_trades.append({
                    "stock_code": code,
                    "stock_name": name,
                    "buy_price": int(avg_buy_price),
                    "sell_price": int(avg_sell_price),
                    "quantity": total_sell_qty,
                    "profit": profit,
                    "profit_rate": round(profit_rate, 2)
                })

        # 승률 계산
        total_realized = win_count + loss_count
        win_rate = (win_count / total_realized * 100) if total_realized > 0 else 0.0
        avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0.0

        # 현재 총자산 계산 (계좌 잔고 + 평가금액)
        current_total_asset = 0
        total_profit_from_initial = 0
        total_profit_rate_from_initial = 0.0

        try:
            # 계좌 잔고 조회
            is_mock = bool(api_key_data.get('is_mock', True))
            account_data = logger.get_real_account_balance(
                app_key=api_key_data.get('app_key'),
                app_secret=api_key_data.get('app_secret'),
                account_number=api_key_data.get('account_number'),
                account_product_code=api_key_data.get('account_product_code', '01'),
                is_mock=is_mock
            )

            if account_data:
                holdings = account_data.get('holdings', [])
                holdings = [h for h in holdings if h.get('quantity', 0) > 0]
                summary = account_data.get('summary', {})

                # 총 평가금액
                if summary and summary.get('total_eval_amount', 0) > 0:
                    total_evaluation = summary.get('total_eval_amount', 0)
                    cash_balance = summary.get('cash_balance', 0)
                else:
                    total_evaluation = sum(h.get('eval_amount', 0) for h in holdings)
                    cash_balance = summary.get('cash_balance', 0)

                current_total_asset = total_evaluation + cash_balance

                # 초기투자금 기준 총수익 계산
                if initial_investment > 0:
                    total_profit_from_initial = current_total_asset - initial_investment
                    total_profit_rate_from_initial = round(
                        ((current_total_asset / initial_investment) - 1) * 100, 2
                    )

        except Exception as e:
            print(f"[성과분석] 계좌잔고 조회 실패: {e}")

        return {
            "period_days": days,
            "total_trades": len(history),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 1),
            "total_profit": total_profit,
            "avg_profit_rate": round(avg_profit_rate, 2),
            "max_profit": max_profit,
            "max_loss": max_loss,
            "realized_trades": realized_trades,
            "initial_investment": initial_investment,
            "current_total_asset": current_total_asset,
            "total_profit_from_initial": total_profit_from_initial,
            "total_profit_rate_from_initial": total_profit_rate_from_initial
        }

    except Exception as e:
        import traceback
        print(f"[성과분석 에러] {e}")
        traceback.print_exc()
        return empty_response


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
    """API 키 저장 (연동 테스트 후 저장)"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    mode_text = "모의투자" if request.is_mock else "실제투자"

    # 1. 먼저 API 연동 테스트
    try:
        print(f"[API키저장] 연동 테스트 시작 - {mode_text}, 계좌: {request.account_number}")

        # 입력값 공백 제거
        app_key = request.app_key.strip()
        app_secret = request.app_secret.strip()
        account_number = request.account_number.strip()

        # KIS API 토큰 발급 및 계좌 조회 테스트
        test_result = logger.get_real_account_balance(
            app_key=app_key,
            app_secret=app_secret,
            account_number=account_number,
            account_product_code=request.account_product_code,
            is_mock=request.is_mock
        )

        # 테스트 결과 확인 - holdings가 비어있어도 조회 자체가 성공하면 OK
        # (빈 계좌일 수 있음)
        if test_result is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API 연동 테스트 실패: KIS API 응답 없음. API 키와 계좌번호를 확인해주세요."
            )

        print(f"[API키저장] 연동 테스트 성공 - 보유종목: {len(test_result.get('holdings', []))}개")

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"[API키저장] 연동 테스트 실패: {error_msg}")

        # 에러 메시지 가공
        if "INVALID_CHECK_ACNO" in error_msg or "계좌" in error_msg.lower():
            detail = f"계좌번호가 올바르지 않습니다. {mode_text} 계좌번호를 확인해주세요."
        elif "token" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
            detail = f"API 키가 올바르지 않습니다. {mode_text}용 APP Key와 Secret을 확인해주세요."
        elif "rate" in error_msg.lower() or "1분" in error_msg:
            detail = "토큰 발급 제한 (1분당 1회). 잠시 후 다시 시도해주세요."
        else:
            detail = f"API 연동 테스트 실패: {error_msg}"

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

    # 2. 테스트 성공 시 API 키 저장
    success = logger.save_api_key_settings(
        user_id=current_user.get('id'),
        app_key=app_key,
        app_secret=app_secret,
        account_number=account_number,
        account_product_code=request.account_product_code,
        is_mock=request.is_mock
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API 키 저장에 실패했습니다"
        )

    return {
        "message": f"API 키가 저장되었습니다 ({mode_text} 모드)",
        "is_connected": True,
        "is_mock": request.is_mock,
        "test_result": {
            "holdings_count": len(test_result.get('holdings', [])),
            "cash_balance": test_result.get('summary', {}).get('cash_balance', 0)
        }
    }


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
        print(f"[계좌조회] API 키 조회 - is_mock: {is_mock}, account: {api_key_data.get('account_number')}")

        account_data = logger.get_real_account_balance(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=is_mock
        )

        print(f"[계좌조회] KIS 응답 - holdings: {len(account_data.get('holdings', [])) if account_data else 0}개, summary: {account_data.get('summary') if account_data else None}")

        # account_data가 None이면 빈 응답
        if not account_data:
            return {
                'holdings': [],
                'balance': {'cash': 0},
                'summary': {
                    'total_asset': 0,
                    'total_purchase': 0,
                    'total_evaluation': 0,
                    'total_profit': 0,
                    'profit_rate': 0,
                },
                'total_purchase': 0,
                'total_evaluation': 0,
                'total_profit_loss': 0,
                'profit_rate': 0,
                'cash_balance': 0,
                'is_mock': is_mock,
                'timestamp': None
            }

        # 프론트엔드가 기대하는 형식으로 변환
        holdings = account_data.get('holdings', [])
        # 0주인 종목 필터링
        holdings = [h for h in holdings if h.get('quantity', 0) > 0]
        summary = account_data.get('summary', {})

        # 총 매입금액 계산 (평균단가 * 수량의 합)
        total_purchase = sum(h.get('avg_price', 0) * h.get('quantity', 0) for h in holdings)

        # output2(summary)가 비어있으면 holdings에서 직접 계산
        if summary and summary.get('total_eval_amount', 0) > 0:
            # summary 데이터 사용
            total_evaluation = summary.get('total_eval_amount', 0)
            total_profit_loss = summary.get('total_profit_loss', 0)
            cash_balance = summary.get('cash_balance', 0)
        else:
            # holdings 데이터에서 직접 계산
            total_evaluation = sum(h.get('eval_amount', 0) for h in holdings)
            total_profit_loss = sum(h.get('profit_loss', 0) for h in holdings)
            cash_balance = summary.get('cash_balance', 0)  # 예수금은 summary에서만

        # 수익률은 항상 직접 계산 (KIS API가 0을 반환하는 경우가 있음)
        profit_rate = ((total_evaluation - total_purchase) / total_purchase * 100) if total_purchase > 0 else 0

        # 총 자산 = 평가금액 + 예수금
        total_asset = total_evaluation + cash_balance

        return {
            'holdings': holdings,
            'balance': {
                'cash': cash_balance,
            },
            'summary': {
                'total_asset': total_asset,
                'total_purchase': total_purchase,
                'total_evaluation': total_evaluation,
                'total_profit': total_profit_loss,
                'profit_rate': profit_rate,
            },
            # 하위 호환성을 위해 flat 필드도 유지
            'total_purchase': total_purchase,
            'total_evaluation': total_evaluation,
            'total_profit_loss': total_profit_loss,
            'profit_rate': profit_rate,
            'cash_balance': cash_balance,
            'is_mock': is_mock,
            'timestamp': account_data.get('timestamp')
        }
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
    stock_ratio: int = 5  # 종목당 투자비율 (1~20%)
    stop_loss_rate: float = -7.0  # 손절률 (-20 ~ 0%)
    min_buy_score: int = 70  # 최소 매수 점수 (50~100)
    sell_score: int = 40  # 매도 점수 (이 점수 이하면 매도)
    max_holdings: int = 10  # 최대 보유 종목 (1~20)
    max_daily_trades: int = 10  # 일일 최대 거래 (1~50)
    max_holding_days: int = 14  # 최대 보유 기간 (1~30일)
    trading_enabled: bool = True
    trading_start_time: str = "09:00"
    trading_end_time: str = "15:20"
    initial_investment: int = 0  # 초기 투자금


@router.get("/settings")
async def get_settings(
    current_user: dict = Depends(get_current_user_required)
):
    """자동매매 설정 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    settings = logger.get_auto_trade_settings(current_user.get('id'))

    # 기본값 설정
    default_settings = {
        "trade_mode": "manual",
        "max_investment": 1000000,
        "stock_ratio": 5,
        "stop_loss_rate": -7.0,
        "min_buy_score": 70,
        "sell_score": 40,
        "max_holdings": 10,
        "max_daily_trades": 10,
        "max_holding_days": 14,
        "trading_enabled": True,
        "trading_start_time": "09:00",
        "trading_end_time": "15:20",
        "initial_investment": 0
    }

    if not settings:
        return default_settings

    # 기존 설정에 initial_investment가 없으면 기본값 추가
    if 'initial_investment' not in settings:
        settings['initial_investment'] = 0

    print(f"[설정조회] user_id={current_user.get('id')}, initial_investment={settings.get('initial_investment')}")
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

    # API 키가 없으면 거부 (다른 사용자 데이터 수정 방지)
    api_key_data = logger.get_api_key_settings(current_user.get('id'))
    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

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

    # API 키가 없으면 거부 (다른 사용자 데이터 수정 방지)
    api_key_data = logger.get_api_key_settings(current_user.get('id'))
    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

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

    # API 키가 없으면 빈 데이터 반환 (다른 사용자 데이터 노출 방지)
    api_key_data = logger.get_api_key_settings(current_user.get('id'))
    if not api_key_data:
        return []

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

    # API 키가 없으면 거부 (다른 사용자 데이터 수정 방지)
    api_key_data = logger.get_api_key_settings(current_user.get('id'))
    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

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

    # API 키가 없으면 거부 (다른 사용자 데이터 수정 방지)
    api_key_data = logger.get_api_key_settings(current_user.get('id'))
    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

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
    holding_value: Optional[int]  # 보유금액
    profit_amount: Optional[int]  # 수익액
    buy_date: Optional[str]  # 매입일


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
    sort_by: str = "holding_value",  # holding_value, buy_date, profit_amount, profit_rate
    current_user: dict = Depends(get_current_user_required)
):
    """보유종목 AI 진단

    정렬 옵션:
    - holding_value: 보유금액순 (내림차순)
    - buy_date: 매입일순 (최신순)
    - profit_amount: 수익액순 (내림차순)
    - profit_rate: 수익률순 (내림차순)
    """
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
    # 0주인 종목 필터링
    holdings = [h for h in holdings if h.get('quantity', 0) > 0]

    diagnosed_holdings = []
    total_health = 0
    warning_count = 0
    total_profit_rate = 0

    import asyncio

    # 모든 종목의 AI 점수를 병렬로 조회
    stock_codes = [h.get('stock_code', '') for h in holdings]
    ai_scores = await asyncio.gather(*[get_stock_ai_score(code) for code in stock_codes])

    for i, h in enumerate(holdings):
        profit_rate = h.get('profit_rate', 0)
        current_price = h.get('current_price', 0)
        avg_price = h.get('avg_price', 0)

        # AI 기술분석 점수 사용
        ai_data = ai_scores[i]
        health_score = int(ai_data.get('score', 50))
        ai_opinion = ai_data.get('opinion', '관망')
        ai_comment = ai_data.get('comment', '')

        # 시그널 결정: AI 점수 + 수익률 고려
        signal = 'hold'
        if profit_rate >= 20:
            signal = 'take_profit'  # 익절 고려
            if not ai_comment:
                ai_comment = "목표 수익률 달성. 일부 익절을 고려해보세요."
        elif profit_rate <= -10:
            signal = 'strong_sell'
            warning_count += 1
            if not ai_comment:
                ai_comment = "손절을 고려해야 할 시점입니다."
        elif profit_rate <= -5:
            signal = 'sell'
            warning_count += 1
            if not ai_comment:
                ai_comment = "주의가 필요합니다. 손절 라인을 확인하세요."
        elif health_score >= 70:
            signal = 'buy'
        elif health_score <= 40:
            signal = 'sell'
            if profit_rate < 0:
                warning_count += 1

        # 보유금액, 수익액 계산
        quantity = h.get('quantity', 0)
        holding_value = int(current_price * quantity) if current_price else 0
        profit_amount = int((current_price - avg_price) * quantity) if current_price and avg_price else 0

        diagnosed_holdings.append(DiagnosisHolding(
            stock_code=h.get('stock_code', ''),
            stock_name=h.get('stock_name', ''),
            quantity=quantity,
            avg_price=avg_price,
            current_price=current_price,
            profit_rate=profit_rate,
            health_score=health_score,
            signal=signal,
            holding_value=holding_value,
            profit_amount=profit_amount,
            buy_date=h.get('buy_date')
        ))

        total_health += health_score
        total_profit_rate += profit_rate

    avg_health = int(total_health / len(holdings)) if holdings else 0
    avg_profit_rate = total_profit_rate / len(holdings) if holdings else 0

    # 정렬
    if sort_by == "holding_value":
        diagnosed_holdings.sort(key=lambda x: x.holding_value or 0, reverse=True)
    elif sort_by == "buy_date":
        diagnosed_holdings.sort(key=lambda x: x.buy_date or '', reverse=True)
    elif sort_by == "profit_amount":
        diagnosed_holdings.sort(key=lambda x: x.profit_amount or 0, reverse=True)
    elif sort_by == "profit_rate":
        diagnosed_holdings.sort(key=lambda x: x.profit_rate or 0, reverse=True)

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
