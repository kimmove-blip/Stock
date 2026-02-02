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

from api.dependencies import get_current_user_required, get_db
from trading.trade_logger import TradeLogger
from database.db_manager import DatabaseManager
import httpx
import FinanceDataReader as fdr
import pandas as pd

router = APIRouter()


def get_stock_sma20(stock_code: str) -> dict:
    """종목의 20일선 조회 (래치 전략용)"""
    try:
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        df = fdr.DataReader(stock_code, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if df is None or len(df) < 20:
            return {'sma20': None, 'below_sma20': False}

        df['SMA_20'] = df['Close'].rolling(window=20).mean()

        current_price = df.iloc[-1]['Close']
        sma20 = df.iloc[-1]['SMA_20']

        if pd.isna(sma20):
            return {'sma20': None, 'below_sma20': False}

        below_sma20 = current_price < sma20

        return {
            'sma20': int(sma20),
            'current_price': int(current_price),
            'below_sma20': below_sma20,
            'distance_pct': round((current_price / sma20 - 1) * 100, 2) if sma20 > 0 else 0
        }
    except Exception as e:
        print(f"20일선 조회 실패 [{stock_code}]: {e}")
        return {'sma20': None, 'below_sma20': False}


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


async def get_stock_current_price(stock_code: str) -> int:
    """종목의 현재가 조회"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:8000/api/stocks/{stock_code}",
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('price', 0) or data.get('current_price', 0)
    except Exception as e:
        print(f"현재가 조회 실패 [{stock_code}]: {e}")
    return 0


async def get_stock_price_info(stock_code: str) -> dict:
    """종목의 현재가 및 전일비 조회 (실시간 API 사용)"""
    try:
        async with httpx.AsyncClient() as client:
            # 실시간 시세 API 사용 (30초 캐시)
            response = await client.get(
                f"http://localhost:8000/api/realtime/price/{stock_code}",
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'current_price': data.get('current_price', 0),
                    'change_rate': data.get('change_rate', 0) or 0
                }
    except Exception as e:
        print(f"가격 정보 조회 실패 [{stock_code}]: {e}")
    return {'current_price': 0, 'change_rate': 0}


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
    current_price: Optional[int] = None  # 현재가 (실시간)
    original_price: Optional[int] = None  # 제안 시점 가격
    change_rate: Optional[float] = None  # 전일대비 등락률
    quantity: int
    custom_quantity: Optional[int] = None  # 사용자 지정 수량
    reason: Optional[str]
    score: Optional[float]
    status: str
    created_at: str
    profit_rate: Optional[float] = None  # 매도 제안용 수익률


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

    # 대기 중인 매수 제안 (user_id로 필터링) - 수량 동적 계산
    suggestions_raw = logger.get_pending_suggestions(user_id=user_id)

    # 사용자 설정에서 max_per_stock 가져오기 (종목당 최대 투자금액)
    user_settings = logger.get_auto_trade_settings(user_id)
    max_per_stock = user_settings.get('max_per_stock', 200000) if user_settings else 200000

    # 각 제안에 대해 수량 계산 (max_per_stock 기준)
    pending_suggestions = []
    for s in suggestions_raw:
        suggested_price = s.get('suggested_price', 0)
        custom_quantity = s.get('custom_quantity')

        # custom_quantity가 있으면 사용, 없으면 max_per_stock 기준으로 계산
        if custom_quantity and custom_quantity > 0:
            quantity = custom_quantity
        else:
            quantity = max_per_stock // suggested_price if suggested_price > 0 else 1
            quantity = max(1, quantity)  # 최소 1주

        pending_suggestions.append(SuggestionResponse(
            id=s['id'],
            stock_code=s['stock_code'],
            stock_name=s.get('stock_name'),
            suggested_price=suggested_price,
            quantity=quantity,
            reason=s.get('reason'),
            score=s.get('score'),
            status=s['status'],
            created_at=s['created_at'],
            custom_quantity=custom_quantity
        ))

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

        # 조회 기간 설정 (days=1은 "당일"로 처리)
        end_date = datetime.now().strftime("%Y%m%d")
        if days <= 1:
            start_date = end_date  # 당일만 조회
        else:
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

        # 매도 종목의 평균 매수가 조회 (DB에서 전체 기간 조회)
        sell_codes = list(set([h.get('stock_code') for h in history if h.get('side') == 'sell' and h.get('stock_code')]))
        stock_avg_buy_price = {}

        if sell_codes:
            # 1. DB에서 매수 평균가 조회 (전체 기간)
            stock_avg_buy_price = logger.get_avg_buy_prices(user_id, sell_codes)

            # 2. DB에 없으면 현재 조회 기간 내 매수에서 계산
            missing_codes = [c for c in sell_codes if c not in stock_avg_buy_price]
            if missing_codes:
                from collections import defaultdict
                stock_buys = defaultdict(lambda: {'total_amount': 0, 'total_qty': 0})
                for h in history:
                    if h.get('side') == 'buy':
                        code = h.get('stock_code')
                        if code in missing_codes:
                            qty = h.get('executed_qty', 0)
                            price = h.get('executed_price', 0)
                            stock_buys[code]['total_amount'] += qty * price
                            stock_buys[code]['total_qty'] += qty

                for code, data in stock_buys.items():
                    if data['total_qty'] > 0:
                        stock_avg_buy_price[code] = data['total_amount'] / data['total_qty']

            # 3. 여전히 없으면 KIS 30일 체결내역에서 매수 조회
            still_missing = [c for c in sell_codes if c not in stock_avg_buy_price]
            if still_missing:
                try:
                    from collections import defaultdict
                    buy_start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
                    buy_end = datetime.now().strftime("%Y%m%d")
                    buy_history = client.get_order_history(start_date=buy_start, end_date=buy_end)
                    buy_history = [h for h in buy_history if h.get('executed_qty', 0) > 0 and h.get('side') == 'buy']

                    stock_buys = defaultdict(lambda: {'total_amount': 0, 'total_qty': 0})
                    for h in buy_history:
                        code = h.get('stock_code')
                        if code in still_missing:
                            qty = h.get('executed_qty', 0)
                            price = h.get('executed_price', 0)
                            stock_buys[code]['total_amount'] += qty * price
                            stock_buys[code]['total_qty'] += qty

                    for code, data in stock_buys.items():
                        if data['total_qty'] > 0:
                            stock_avg_buy_price[code] = data['total_amount'] / data['total_qty']
                except Exception as e:
                    print(f"[거래내역] KIS 매수내역 조회 실패: {e}")

            # 4. 여전히 없으면 KIS 잔고에서 조회
            still_missing = [c for c in sell_codes if c not in stock_avg_buy_price]
            if still_missing:
                try:
                    balance = client.get_balance()
                    for holding in balance.get('holdings', []):
                        code = holding.get('stock_code')
                        if code in still_missing:
                            avg_price = holding.get('avg_price', 0)
                            if avg_price > 0:
                                stock_avg_buy_price[code] = avg_price
                except Exception as e:
                    print(f"[거래내역] 잔고에서 평균가 조회 실패: {e}")

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

    # 사용자 설정에서 max_per_stock 가져오기
    user_settings = logger.get_auto_trade_settings(user_id)
    max_per_stock = user_settings.get('max_per_stock', 200000) if user_settings else 200000

    # user_id로 필터링하여 해당 사용자의 제안만 조회
    if status == 'pending':
        suggestions_raw = logger.get_pending_suggestions(user_id=user_id)
    elif status == 'approved':
        suggestions_raw = logger.get_approved_suggestions(user_id=user_id)
    elif status == 'executed':
        suggestions_raw = logger.get_executed_suggestions(user_id=user_id)
    else:
        # 전체 조회 (pending + approved + executed)
        suggestions_raw = (
            logger.get_pending_suggestions(user_id=user_id) +
            logger.get_approved_suggestions(user_id=user_id) +
            logger.get_executed_suggestions(user_id=user_id)
        )

    # 각 제안에 대해 동적으로 수량 계산 + 현재가/등락률 조회
    import asyncio
    stock_codes = [s.get('stock_code', '') for s in suggestions_raw]
    price_infos = await asyncio.gather(*[get_stock_price_info(code) for code in stock_codes])

    result = []
    for i, s in enumerate(suggestions_raw):
        suggested_price = s.get('suggested_price', 0)
        custom_quantity = s.get('custom_quantity')
        price_info = price_infos[i] if i < len(price_infos) else {}
        current_price = price_info.get('current_price', 0)
        change_rate = price_info.get('change_rate', 0)

        # custom_quantity가 있으면 사용, 없으면 max_per_stock 기준으로 계산
        if custom_quantity and custom_quantity > 0:
            quantity = custom_quantity
        else:
            quantity = max_per_stock // suggested_price if suggested_price > 0 else 1
            quantity = max(1, quantity)  # 최소 1주

        result.append(SuggestionResponse(
            id=s['id'],
            stock_code=s['stock_code'],
            stock_name=s.get('stock_name'),
            suggested_price=suggested_price,
            current_price=current_price,
            original_price=s.get('current_price'),  # 제안 시점 가격 (DB 저장값)
            change_rate=change_rate,
            quantity=quantity,
            custom_quantity=custom_quantity,
            reason=s.get('reason'),
            score=s.get('score'),
            status=s['status'],
            created_at=s['created_at']
        ))

    return result


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

        # 조회 기간 설정 (days=1은 "당일"로 처리)
        end_date = datetime.now().strftime("%Y%m%d")
        if days <= 1:
            start_date = end_date  # 당일만 조회
        else:
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
                else:
                    total_evaluation = sum(h.get('eval_amount', 0) for h in holdings)

                # D+2 예수금 (계좌현황과 동일하게 사용)
                d2_cash_balance = summary.get('d2_cash_balance', 0) or summary.get('cash_balance', 0)

                current_total_asset = total_evaluation + d2_cash_balance

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


@router.get("/performance/daily-asset")
async def get_daily_asset_history(
    days: int = 365,
    current_user: dict = Depends(get_current_user_required)
):
    """
    일별 총자산 히스토리 조회 (그래프용)
    - 일별 총자산 (D+2예수금 + 평가금액)
    - 초기투자금
    - 코스피/코스닥 지수 (같은 스케일로 환산)
    - 오늘 데이터는 실시간 조회
    - 첫 투자일부터 데이터 조회 (days 파라미터 무시)
    """
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    user_id = current_user.get('id')

    # 자본 투입 이력 조회 (TWR 계산용)
    capital_events = logger.get_capital_events(user_id)
    capital_summary = logger.get_capital_summary(user_id)

    # 초기투자금: 첫 번째 자본 투입금 (전체 net_capital 아님)
    settings = logger.get_auto_trade_settings(user_id)
    first_deposit = capital_events[0]['amount'] if capital_events else 0
    initial_investment = first_deposit or (settings.get('initial_investment', 0) if settings else 0)

    # daily_performance 테이블에서 전체 일별 자산 조회 (첫 투자일부터)
    today = datetime.now().strftime('%Y-%m-%d')

    with logger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT trade_date, total_assets, d2_cash, holdings_value
            FROM daily_performance
            WHERE user_id = ? AND trade_date < ?
            ORDER BY trade_date ASC
        """, (user_id, today))
        rows = cursor.fetchall()

    daily_data = []
    for row in rows:
        daily_data.append({
            'date': row['trade_date'],
            'total_asset': row['total_assets'] or 0,
            'd2_cash': row['d2_cash'] or 0,
            'holdings_value': row['holdings_value'] or 0
        })

    # 오늘 데이터는 실시간 조회
    api_key_data = logger.get_api_key_settings(user_id)
    if api_key_data:
        try:
            from api.services.kis_client import KISClient
            import requests

            is_mock = bool(api_key_data.get('is_mock', True))
            client = KISClient(
                app_key=api_key_data.get('app_key'),
                app_secret=api_key_data.get('app_secret'),
                account_number=api_key_data.get('account_number'),
                account_product_code=api_key_data.get('account_product_code', '01'),
                is_mock=is_mock
            )

            # 잔고 조회 API 직접 호출
            token = client._get_access_token()
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": client.app_key,
                "appsecret": client.app_secret,
                "tr_id": "VTTC8434R" if is_mock else "TTTC8434R",
            }
            params = {
                "CANO": api_key_data.get('account_number'),
                "ACNT_PRDT_CD": "01",
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            }
            resp = requests.get(
                f"{client.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params,
                timeout=10
            )
            data = resp.json()

            if data.get('output2'):
                s = data['output2'][0] if isinstance(data['output2'], list) else data['output2']
                d2_cash = int(s.get('nxdy_excc_amt', 0))
                holdings_value = int(s.get('scts_evlu_amt', 0))
                total_asset = int(s.get('tot_evlu_amt', 0))

                daily_data.append({
                    'date': today,
                    'total_asset': total_asset,
                    'd2_cash': d2_cash,
                    'holdings_value': holdings_value
                })
        except Exception as e:
            print(f"[일별자산] 실시간 조회 실패: {e}")

    # 코스피/코스닥 지수 조회 (첫 투자일부터)
    kospi_data = []
    kosdaq_data = []

    try:
        end_date = datetime.now()
        # 첫 투자일부터 조회 (daily_data가 있으면 그 날짜, 없으면 30일 전)
        if daily_data:
            start_date = datetime.strptime(daily_data[0]['date'], '%Y-%m-%d') - timedelta(days=3)
        else:
            start_date = end_date - timedelta(days=30)

        # 코스피 지수
        kospi_df = fdr.DataReader('KS11', start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if kospi_df is not None and len(kospi_df) > 0:
            for idx, row in kospi_df.iterrows():
                kospi_data.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'close': float(row['Close'])
                })

        # 코스닥 지수
        kosdaq_df = fdr.DataReader('KQ11', start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if kosdaq_df is not None and len(kosdaq_df) > 0:
            for idx, row in kosdaq_df.iterrows():
                kosdaq_data.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'close': float(row['Close'])
                })
    except Exception as e:
        print(f"[일별자산] 지수 조회 실패: {e}")

    # 같은 스케일로 환산 (초기투자금 기준 100%로 환산)
    # 지수도 첫 날 기준 100%로 환산
    scaled_kospi = []
    scaled_kosdaq = []

    if kospi_data and len(kospi_data) > 0:
        base_kospi = kospi_data[0]['close']
        for item in kospi_data:
            scaled_kospi.append({
                'date': item['date'],
                'value': round(item['close'] / base_kospi * 100, 2) if base_kospi > 0 else 100
            })

    if kosdaq_data and len(kosdaq_data) > 0:
        base_kosdaq = kosdaq_data[0]['close']
        for item in kosdaq_data:
            scaled_kosdaq.append({
                'date': item['date'],
                'value': round(item['close'] / base_kosdaq * 100, 2) if base_kosdaq > 0 else 100
            })

    # TWR 기반 스케일 계산 (자본 투입 시점마다 리베이싱)
    scaled_asset = []
    base_asset = initial_investment if initial_investment > 0 else (daily_data[0]['total_asset'] if daily_data else 0)

    # 자본 이벤트를 날짜별로 정리 (첫 투입 제외)
    capital_by_date = {}
    for i, event in enumerate(capital_events):
        if i == 0:  # 첫 투입은 시작점이므로 제외
            continue
        event_date = event['event_date']
        if event_date not in capital_by_date:
            capital_by_date[event_date] = 0
        if event['event_type'] == 'deposit':
            capital_by_date[event_date] += event['amount']
        else:
            capital_by_date[event_date] -= event['amount']

    # TWR 기반 누적 수익률 계산
    cumulative_return = 1.0
    prev_asset = base_asset

    for item in daily_data:
        date = item['date']
        total_asset = item['total_asset']

        # 자본 투입이 있는 날인지 확인
        if date in capital_by_date and prev_asset > 0:
            # 투입 전 자산으로 수익률 계산 (투입금 제외)
            asset_before_deposit = total_asset - capital_by_date[date]
            period_return = asset_before_deposit / prev_asset
            cumulative_return *= period_return
            twr_value = cumulative_return * 100
            prev_asset = total_asset  # 새 베이스: 투입 후 총자산
        else:
            # 일반 날: 전일 대비 수익률 반영
            if prev_asset > 0:
                period_return = total_asset / prev_asset
                cumulative_return *= period_return
                twr_value = cumulative_return * 100
            else:
                twr_value = 100
            prev_asset = total_asset

        scaled_asset.append({
            'date': date,
            'total_asset': total_asset,
            'value': round(twr_value, 2)
        })

    return {
        'initial_investment': initial_investment,
        'daily_asset': daily_data,
        'scaled_asset': scaled_asset,
        'scaled_kospi': scaled_kospi,
        'scaled_kosdaq': scaled_kosdaq,
        'base_asset': base_asset
    }


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
        else:
            # holdings 데이터에서 직접 계산
            total_evaluation = sum(h.get('eval_amount', 0) for h in holdings)
            total_profit_loss = sum(h.get('profit_loss', 0) for h in holdings)

        # 예수금: d2_cash_balance (실제 자산)
        d2_cash_balance = summary.get('d2_cash_balance', 0) or summary.get('cash_balance', 0)
        # 주문가능금액: max_buy_amt (미체결 제외)
        max_buy_amt = summary.get('max_buy_amt', 0) or d2_cash_balance

        # 수익률은 항상 직접 계산 (KIS API가 0을 반환하는 경우가 있음)
        profit_rate = ((total_evaluation - total_purchase) / total_purchase * 100) if total_purchase > 0 else 0

        # 총 자산 = 평가금액 + d2 예수금 (실제 자산 기준)
        total_asset = total_evaluation + d2_cash_balance

        # holdings에 AI 점수 추가 (사용자 설정 버전 점수 사용)
        user_settings = logger.get_auto_trade_settings(current_user.get('id')) or {}
        score_version = user_settings.get('score_version', 'v2')

        scores_map = {}
        try:
            import glob
            import pandas as pd
            from config import OUTPUT_DIR
            score_files = sorted(glob.glob(str(OUTPUT_DIR / "intraday_scores" / "*.csv")))
            if score_files:
                latest_csv = score_files[-1]
                df = pd.read_csv(latest_csv)
                df['code'] = df['code'].astype(str).str.zfill(6)
                if score_version in df.columns:
                    for _, row in df.iterrows():
                        scores_map[row['code']] = int(row.get(score_version, 0))
                elif 'v5' in df.columns:  # fallback to v5
                    for _, row in df.iterrows():
                        scores_map[row['code']] = int(row.get('v5', 0))
        except Exception as e:
            print(f"{score_version} 점수 조회 실패: {e}")

        # holdings에 점수 추가
        for h in holdings:
            stock_code = h.get('stock_code', '')
            h['score'] = scores_map.get(stock_code, None)

        return {
            'holdings': holdings,
            'balance': {
                'cash': d2_cash_balance,  # 예수금 (D+2)
                'available': max_buy_amt,  # 주문가능금액
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
            'cash_balance': d2_cash_balance,  # 예수금 (D+2)
            'max_buy_amt': max_buy_amt,  # 주문가능금액
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
    max_per_stock: int = 200000  # 종목당 최대 금액
    stop_loss_rate: float = -7.0  # 손절률 (-20 ~ 0%)
    min_buy_score: int = 70  # 최소 매수 점수 (50~100)
    sell_score: int = 40  # 매도 점수 (이 점수 이하면 매도)
    trading_enabled: bool = True
    initial_investment: int = 0  # 초기 투자금
    score_version: str = "v2"  # 스코어 버전 (v1, v2, v5)
    strategy: str = "simple"  # 전략: simple(단순 스코어), v1_composite(V1 복합)
    buy_conditions: str = ""  # 매수 조건 (예: "V1>=60 AND V5>=50")
    sell_conditions: str = ""  # 매도 조건 (예: "V4<=30 OR V1<=40")


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
        "max_per_stock": 200000,
        "stop_loss_rate": -7.0,
        "min_buy_score": 70,
        "sell_score": 40,
        "trading_enabled": True,
        "initial_investment": 0,
        "score_version": "v2",
        "strategy": "simple"
    }

    if not settings:
        return default_settings

    # 기존 설정에 없는 필드 기본값 추가
    if 'initial_investment' not in settings:
        settings['initial_investment'] = 0
    if 'strategy' not in settings or settings['strategy'] is None:
        settings['strategy'] = 'simple'
    if 'max_per_stock' not in settings:
        settings['max_per_stock'] = 200000
    if 'score_version' not in settings:
        settings['score_version'] = 'v5'

    print(f"[설정조회] user_id={current_user.get('id')}, initial_investment={settings.get('initial_investment')}")
    return settings


@router.post("/settings")
async def save_settings(
    request: AutoTradeSettingsRequest,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
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

    # score_version이 있으면 users 테이블에도 동기화
    if request.score_version:
        valid_versions = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']
        if request.score_version in valid_versions:
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE users SET score_version = ? WHERE id = ?",
                    (request.score_version, current_user.get('id'))
                )
                conn.commit()

    return {"message": "설정이 저장되었습니다"}


class PreviewConditionsRequest(BaseModel):
    """조건 미리보기 요청"""
    buy_conditions: str = ""
    sell_conditions: str = ""


def parse_condition(condition_str: str) -> list:
    """조건 문자열 파싱"""
    import re
    if not condition_str:
        return []

    parts = re.split(r'\s+(AND|OR)\s+', condition_str, flags=re.IGNORECASE)
    conditions = []
    current_connector = 'AND'

    for part in parts:
        part = part.strip()
        if part.upper() in ('AND', 'OR'):
            current_connector = part.upper()
        else:
            match = re.match(r'^(V\d+)\s*(>=|<=|>|<|=)\s*(\d+)$', part, re.IGNORECASE)
            if match:
                conditions.append({
                    'score': match.group(1).lower(),
                    'op': match.group(2),
                    'value': int(match.group(3)),
                    'connector': current_connector
                })
    return conditions


def evaluate_conditions(conditions: list, scores: dict) -> bool:
    """조건 평가"""
    if not conditions:
        return False

    results = []
    connectors = []

    for cond in conditions:
        score_key = cond['score']
        score_value = scores.get(score_key, 0)
        op = cond['op']
        target = cond['value']

        if op == '>=':
            result = score_value >= target
        elif op == '<=':
            result = score_value <= target
        elif op == '>':
            result = score_value > target
        elif op == '<':
            result = score_value < target
        elif op == '=':
            result = score_value == target
        else:
            result = False

        results.append(result)
        if len(results) > 1:
            connectors.append(cond['connector'])

    if len(results) == 1:
        return results[0]

    final = results[0]
    for i, connector in enumerate(connectors):
        if connector == 'AND':
            final = final and results[i + 1]
        else:
            final = final or results[i + 1]

    return final


@router.post("/preview-conditions")
async def preview_conditions(
    request: PreviewConditionsRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """매수/매도 조건 미리보기 - 최신 인트라데이 스코어 기준"""
    check_auto_trade_permission(current_user)

    import glob
    from pathlib import Path

    # 최신 인트라데이 스코어 CSV 로드
    scores_dir = Path("/home/kimhc/Stock/output/intraday_scores")
    csv_files = sorted(glob.glob(str(scores_dir / "*.csv")))

    if not csv_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="인트라데이 스코어 데이터가 없습니다"
        )

    latest_csv = csv_files[-1]
    csv_time = Path(latest_csv).stem  # 20260202_1130

    try:
        df = pd.read_csv(latest_csv)
        df['code'] = df['code'].astype(str).str.zfill(6)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSV 로드 실패: {e}"
        )

    # 매수 조건 평가
    buy_conditions = parse_condition(request.buy_conditions)
    buy_candidates = []

    if buy_conditions:
        for _, row in df.iterrows():
            scores = {
                'v1': int(row.get('v1', 0)),
                'v2': int(row.get('v2', 0)),
                'v4': int(row.get('v4', 0)),
                'v5': int(row.get('v5', 0)),
            }

            if evaluate_conditions(buy_conditions, scores):
                buy_candidates.append({
                    'code': row['code'],
                    'name': row.get('name', ''),
                    'close': int(row.get('close', 0)),
                    'change_pct': round(row.get('change_pct', 0), 2),
                    'v1': scores['v1'],
                    'v2': scores['v2'],
                    'v4': scores['v4'],
                    'v5': scores['v5'],
                })

        # V1 점수 순 정렬
        buy_candidates.sort(key=lambda x: x['v1'], reverse=True)

    # 매도 조건 평가 (보유 종목 대상)
    sell_conditions = parse_condition(request.sell_conditions)
    sell_candidates = []

    if sell_conditions:
        # 사용자 보유 종목 조회
        logger = get_trade_logger()
        api_key_data = logger.get_api_key_settings(current_user.get('id'))

        if api_key_data:
            try:
                holdings = logger.get_real_account_balance(
                    app_key=api_key_data.get('app_key'),
                    app_secret=api_key_data.get('app_secret'),
                    account_number=api_key_data.get('account_number'),
                    account_product_code=api_key_data.get('account_product_code', '01'),
                    is_mock=bool(api_key_data.get('is_mock', True))
                ).get('holdings', [])

                # 보유 종목 중 매도 조건 충족 확인
                for h in holdings:
                    if h.get('quantity', 0) <= 0:
                        continue

                    code = h.get('stock_code', '')
                    row = df[df['code'] == code]

                    if row.empty:
                        continue

                    row = row.iloc[0]
                    scores = {
                        'v1': int(row.get('v1', 0)),
                        'v2': int(row.get('v2', 0)),
                        'v4': int(row.get('v4', 0)),
                        'v5': int(row.get('v5', 0)),
                    }

                    if evaluate_conditions(sell_conditions, scores):
                        sell_candidates.append({
                            'code': code,
                            'name': h.get('stock_name', ''),
                            'quantity': h.get('quantity', 0),
                            'avg_price': h.get('avg_price', 0),
                            'current_price': h.get('current_price', 0),
                            'profit_rate': h.get('profit_rate', 0),
                            'v1': scores['v1'],
                            'v2': scores['v2'],
                            'v4': scores['v4'],
                            'v5': scores['v5'],
                        })
            except Exception as e:
                print(f"보유종목 조회 실패: {e}")

    return {
        "csv_time": csv_time,
        "buy_conditions": request.buy_conditions,
        "sell_conditions": request.sell_conditions,
        "buy_candidates": buy_candidates[:20],  # 상위 20개
        "buy_total": len(buy_candidates),
        "sell_candidates": sell_candidates,
        "sell_total": len(sell_candidates),
    }


# ==================== 매수 제안 승인/거부 ====================

class ApproveRequest(BaseModel):
    """승인 요청 (선택적 매개변수)"""
    custom_price: Optional[int] = None  # 사용자 지정 가격 (지정가 주문 시)
    custom_quantity: Optional[int] = None  # 사용자 지정 수량
    is_market_order: bool = False  # True: 시장가, False: 지정가
    force_adjusted: bool = False  # True: 조정된 수량으로 강제 주문


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: int,
    request: Optional[ApproveRequest] = None,
    current_user: dict = Depends(get_current_user_required)
):
    """매수 제안 승인 및 즉시 주문 실행"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    user_id = current_user.get('id')

    # API 키가 없으면 거부
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API 키가 설정되지 않았습니다."
        )

    # 제안 정보 조회
    suggestion = logger.get_suggestion(suggestion_id)
    if not suggestion or suggestion.get('status') != 'pending':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 제안을 찾을 수 없거나 이미 처리되었습니다"
        )

    # 추가 매개변수 추출
    custom_price = request.custom_price if request else None
    custom_quantity = request.custom_quantity if request else None
    is_market_order = request.is_market_order if request else False

    # 주문 가격 결정
    if is_market_order:
        order_price = 0
        order_type = "01"  # 시장가
    else:
        order_price = custom_price or suggestion.get('buy_band_high') or suggestion.get('recommended_price') or suggestion.get('current_price')
        order_type = "00"  # 지정가

    # 사용자 설정에서 max_per_stock 가져오기
    user_settings = logger.get_auto_trade_settings(user_id)
    max_per_stock = user_settings.get('max_per_stock', 200000) if user_settings else 200000

    try:
        from api.services.kis_client import KISClient
        client = KISClient(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=bool(api_key_data.get('is_mock', True))
        )

        # 계좌 잔고 조회
        balance = client.get_account_balance()
        if balance:
            summary = balance.get('summary', {})
            max_buy_amt = summary.get('max_buy_amt', 0) or summary.get('d2_cash_balance', 0) or summary.get('cash_balance', 0)
        else:
            max_buy_amt = max_per_stock

        # 수량 계산: custom_quantity > suggestion.custom_quantity > max_per_stock 기준
        price_for_calc = order_price if order_price > 0 else suggestion.get('current_price', 0)

        if custom_quantity and custom_quantity > 0:
            quantity = custom_quantity
        elif suggestion.get('custom_quantity') and suggestion.get('custom_quantity') > 0:
            quantity = suggestion.get('custom_quantity')
        else:
            quantity = max_per_stock // price_for_calc if price_for_calc > 0 else 1
            quantity = max(1, quantity)

        # 주문 금액이 주문가능금액 초과 시 조정된 수량 제안
        order_amount = quantity * price_for_calc
        if order_amount > max_buy_amt and max_buy_amt > 0:
            adjusted_quantity = max_buy_amt // price_for_calc
            if adjusted_quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"주문가능금액({max_buy_amt:,}원)이 1주 가격({price_for_calc:,}원)보다 적습니다."
                )
            # 조정된 수량으로 주문할지 확인 요청
            if not (request and request.force_adjusted):
                return {
                    "status": "need_adjustment",
                    "message": f"주문가능금액 초과",
                    "original_quantity": quantity,
                    "adjusted_quantity": adjusted_quantity,
                    "price": price_for_calc,
                    "original_amount": order_amount,
                    "adjusted_amount": adjusted_quantity * price_for_calc,
                    "max_buy_amt": max_buy_amt
                }
            # force_adjusted=True면 조정된 수량으로 진행
            quantity = adjusted_quantity

        # 주문 실행 전 상한가 체크
        stock_code = suggestion.get('stock_code')
        current_quote = client.get_current_price(stock_code)
        if current_quote:
            change_rate = current_quote.get('change_rate', 0)
            # 상한가(+29% 이상) 종목은 매수 불가 - 매도 물량이 없어 체결 안됨
            if change_rate >= 29.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"상한가 종목({change_rate:+.1f}%)은 매수할 수 없습니다. 매도 물량이 없어 체결되지 않습니다."
                )
            # 상한가 근접(+25% 이상) 시장가 주문 경고
            if change_rate >= 25.0 and is_market_order:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"상한가 근접 종목({change_rate:+.1f}%)은 시장가 주문이 위험합니다. 지정가 주문을 사용하세요."
                )

        # 주문 실행
        result = client.place_order(
            stock_code=stock_code,
            side='buy',
            order_type=order_type,
            quantity=quantity,
            price=order_price
        )

        if result and result.get('order_no'):
            # 승인 및 실행 완료 처리
            logger.approve_suggestion(suggestion_id, custom_price=custom_price, is_market_order=is_market_order)
            logger.mark_executed(suggestion_id)

            # 거래 로그 기록
            logger.log_trade(
                user_id=user_id,
                stock_code=stock_code,
                stock_name=suggestion.get('stock_name'),
                side='buy',
                quantity=quantity,
                price=order_price if order_price > 0 else price_for_calc,
                order_no=result.get('order_no'),
                trade_reason=f"매수제안 승인 (AI점수: {suggestion.get('score', '-')}점)",
                status='ordered'
            )

            order_type_str = "시장가" if is_market_order else f"지정가 {order_price:,}원"
            return {
                "message": f"주문이 실행되었습니다 ({order_type_str}, {quantity}주)",
                "status": "executed",
                "order_no": result.get('order_no'),
                "quantity": quantity,
                "price": order_price
            }
        else:
            error_msg = result.get('message', '알 수 없는 오류') if result else '주문 응답 없음'
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"주문 실패: {error_msg}"
            )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_str = str(e)
        # KIS API 에러 메시지 추출
        if '주문가능금액' in error_str or '잔액' in error_str or '부족' in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"잔액 부족: {error_str}"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"주문 실행 중 오류: {str(e)}"
        )


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

    user_id = current_user.get('id')
    if status == 'pending':
        suggestions_raw = logger.get_pending_sell_suggestions(user_id)
    elif status == 'approved':
        suggestions_raw = logger.get_approved_sell_suggestions(user_id)
    else:
        suggestions_raw = logger.get_pending_sell_suggestions(user_id) + logger.get_approved_sell_suggestions(user_id)

    # 현재가/등락률 조회
    import asyncio
    stock_codes = [s.get('stock_code', '') for s in suggestions_raw]
    price_infos = await asyncio.gather(*[get_stock_price_info(code) for code in stock_codes])

    result = []
    for i, s in enumerate(suggestions_raw):
        price_info = price_infos[i] if i < len(price_infos) else {}
        current_price = price_info.get('current_price', 0)
        change_rate = price_info.get('change_rate', 0)
        result.append(SuggestionResponse(
            id=s['id'],
            stock_code=s['stock_code'],
            stock_name=s.get('stock_name'),
            suggested_price=s['suggested_price'],
            current_price=current_price,
            original_price=s.get('current_price'),  # 제안 시점 가격 (DB 저장값)
            change_rate=change_rate,
            quantity=s['quantity'],
            reason=s.get('reason'),
            score=s.get('score'),
            status=s['status'],
            created_at=s['created_at'],
            profit_rate=s.get('profit_rate')
        ))

    return result


@router.post("/sell-suggestions/{suggestion_id}/approve")
async def approve_sell_suggestion(
    suggestion_id: int,
    request: Optional[ApproveRequest] = None,
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

    # 추가 매개변수 추출
    custom_price = request.custom_price if request else None
    is_market_order = request.is_market_order if request else False

    success = logger.approve_sell_suggestion(
        suggestion_id,
        custom_price=custom_price,
        is_market_order=is_market_order
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 제안을 찾을 수 없거나 이미 처리되었습니다"
        )

    order_type = "시장가" if is_market_order else f"지정가 {custom_price:,}원" if custom_price else "현재가"
    return {"message": f"매도 제안이 승인되었습니다 ({order_type})", "status": "approved"}


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
    change_rate: Optional[float] = None  # 전일비 등락률
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
    from concurrent.futures import ThreadPoolExecutor

    # 종목 코드 목록
    stock_codes = [h.get('stock_code', '') for h in holdings]

    # 사용자 설정에서 score_version 조회 (없으면 v5 기본값)
    user_settings = logger.get_auto_trade_settings(current_user.get('id')) or {}
    score_version = user_settings.get('score_version', 'v2')

    # 장중 스코어 CSV에서 사용자 설정 버전 점수 가져오기
    scores_map = {}
    try:
        import glob
        import pandas as pd
        from config import OUTPUT_DIR
        score_files = sorted(glob.glob(str(OUTPUT_DIR / "intraday_scores" / "*.csv")))
        if score_files:
            latest_csv = score_files[-1]
            df = pd.read_csv(latest_csv)
            df['code'] = df['code'].astype(str).str.zfill(6)
            if score_version in df.columns:
                for _, row in df.iterrows():
                    scores_map[row['code']] = int(row.get(score_version, 0))
            elif 'v5' in df.columns:  # fallback to v5
                for _, row in df.iterrows():
                    scores_map[row['code']] = int(row.get('v5', 0))
    except Exception as e:
        print(f"{score_version} 점수 조회 실패: {e}")

    # 가격 정보를 병렬로 조회
    price_infos = await asyncio.gather(*[get_stock_price_info(code) for code in stock_codes])

    # 20일선 정보 조회 (래치 전략용) - 동기 함수이므로 executor 사용
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=5) as executor:
        sma20_infos = await asyncio.gather(*[
            loop.run_in_executor(executor, get_stock_sma20, code)
            for code in stock_codes
        ])

    for i, h in enumerate(holdings):
        profit_rate = h.get('profit_rate', 0)
        current_price = h.get('current_price', 0)
        avg_price = h.get('avg_price', 0)
        # 전일비 등락률
        change_rate = price_infos[i].get('change_rate', 0) if price_infos[i] else 0

        # JSON에서 가져온 스크리닝 점수 사용 (계좌현황과 동일)
        stock_code = h.get('stock_code', '')
        health_score = scores_map.get(stock_code, 50)
        if health_score is None:
            health_score = 50
        health_score = int(health_score)
        ai_comment = ''

        # 20일선 정보
        sma20_data = sma20_infos[i]
        below_sma20 = sma20_data.get('below_sma20', False)
        sma20_distance = sma20_data.get('distance_pct', 0)

        # 시그널 결정: V5 전략 (20일선 이탈 + 50점 미만)
        signal = 'hold'

        # [래치 전략] 20일선 이탈 = 추세 종료 → 강력 매도
        if below_sma20:
            signal = 'strong_sell'
            warning_count += 1
            ai_comment = f"⚠️ 20일선 이탈 ({sma20_distance:+.1f}%) - 추세 종료, 매도 권장"
        # [V5 전략] 50점 미만 = 모멘텀 약화 → 강력 매도
        elif health_score < 50:
            signal = 'strong_sell'
            warning_count += 1
            if not ai_comment:
                ai_comment = f"⚠️ AI 점수 {health_score}점 - 모멘텀 붕괴, 매도 권장"
        elif profit_rate >= 20:
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
        elif health_score < 50:
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
            change_rate=change_rate,
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
    current_price: Optional[int] = None  # 현재가
    change_rate: Optional[float] = None  # 전일비
    score: Optional[int] = None  # AI 점수


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

        orders_raw = result.get('orders', [])

        # 현재가 및 전일비 조회
        import asyncio
        stock_codes = [o.get('stock_code', '') for o in orders_raw]
        price_infos = await asyncio.gather(*[get_stock_price_info(code) for code in stock_codes])

        # AI 점수 조회 (최신 분석 결과에서)
        scores_map = {}
        try:
            from config import OUTPUT_DIR
            from datetime import datetime, timedelta
            import json
            today = datetime.now()
            for days_back in range(7):
                check_date = today - timedelta(days=days_back)
                json_path = OUTPUT_DIR / f"top100_{check_date.strftime('%Y%m%d')}.json"
                if json_path.exists():
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for stock in data.get('stocks', []):
                            scores_map[stock.get('code')] = stock.get('score', 0)
                    break
        except Exception as e:
            print(f"점수 조회 실패: {e}")

        orders = []
        buy_count = 0
        sell_count = 0
        buy_amount = 0
        sell_amount = 0

        for i, o in enumerate(orders_raw):
            side = o.get('side', 'buy')
            price = o.get('order_price', 0)
            quantity = o.get('order_qty', 0)
            remaining_qty = o.get('remaining_qty', quantity)
            stock_code = o.get('stock_code', '')

            if side == 'buy':
                buy_count += 1
                buy_amount += price * remaining_qty
            else:
                sell_count += 1
                sell_amount += price * remaining_qty

            price_info = price_infos[i] if i < len(price_infos) else {}
            orders.append(PendingOrder(
                order_id=o.get('order_no', ''),
                stock_code=stock_code,
                stock_name=o.get('stock_name', ''),
                side=side,
                order_type='limit' if price > 0 else 'market',
                price=price,
                quantity=quantity,
                remaining_quantity=remaining_qty,
                order_time=o.get('order_time', ''),
                current_price=price_info.get('current_price'),
                change_rate=price_info.get('change_rate'),
                score=scores_map.get(stock_code)
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


class ModifyOrderRequest(BaseModel):
    """주문 정정 요청"""
    order_id: str
    stock_code: str
    quantity: int
    price: int
    order_type: Optional[str] = "limit"  # limit: 지정가, market: 시장가


@router.put("/pending-orders/{order_id}")
async def modify_pending_order(
    order_id: str,
    request: ModifyOrderRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """주문 정정"""
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
        is_market_order = request.order_type == "market"
        result = logger.modify_order(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            order_no=order_id,
            stock_code=request.stock_code,
            quantity=request.quantity,
            price=0 if is_market_order else request.price,
            order_type="01" if is_market_order else "00",  # 01: 시장가, 00: 지정가
            is_mock=is_mock
        )

        order_type_str = "시장가" if is_market_order else "지정가"
        if result.get('success'):
            return {
                "success": True,
                "message": f"주문이 {order_type_str}로 정정되었습니다.",
                "new_order_id": result.get('new_order_no', '')
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('message', '주문 정정 실패')
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"주문 정정 실패: {str(e)}"
        )


@router.post("/sync-portfolio")
async def sync_portfolio_from_auto_trade(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """
    자동매매 계좌의 보유종목을 홈탭 포트폴리오와 동기화
    - 증권사 계좌의 실제 보유종목을 포트폴리오에 반영
    - 기존 포트폴리오 종목은 수량/단가 업데이트
    - 새 종목은 추가
    """
    user_id = current_user['id']

    # 자동매매 권한 체크
    if not current_user.get('auto_trade_enabled'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="자동매매 권한이 없습니다."
        )

    logger = TradeLogger()

    # API 키 설정 조회
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data or not api_key_data.get('app_key'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API 키가 설정되지 않았습니다."
        )

    # 증권사 계좌에서 보유종목 조회
    try:
        account_data = logger.get_real_account_balance(
            app_key=api_key_data.get('app_key'),
            app_secret=api_key_data.get('app_secret'),
            account_number=api_key_data.get('account_number'),
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_mock=bool(api_key_data.get('is_mock', False))
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"계좌 조회 실패: {str(e)}"
        )

    holdings = account_data.get('holdings', [])

    # 현재 포트폴리오 조회
    current_portfolio = db.get_portfolio(user_id)
    portfolio_map = {item['stock_code']: item for item in current_portfolio}

    synced = 0
    added = 0
    updated = 0
    deleted = 0

    # 자동매매 계좌의 보유종목 코드 세트 (수량 > 0인 것만)
    account_stock_codes = {
        h.get('stock_code') for h in holdings
        if h.get('quantity', 0) > 0
    }

    for holding in holdings:
        stock_code = holding.get('stock_code')
        quantity = holding.get('quantity', 0)

        # 수량이 0이면 스킵
        if quantity <= 0:
            continue

        stock_name = holding.get('stock_name', '')
        avg_price = holding.get('avg_price', 0)

        if stock_code in portfolio_map:
            # 기존 종목 업데이트
            existing = portfolio_map[stock_code]
            if existing['quantity'] != quantity or existing['buy_price'] != avg_price:
                db.update_portfolio_item(
                    existing['id'],
                    quantity=quantity,
                    buy_price=avg_price
                )
                updated += 1
        else:
            # 새 종목 추가
            db.add_portfolio_item(
                user_id=user_id,
                stock_code=stock_code,
                stock_name=stock_name,
                buy_price=avg_price,
                quantity=quantity
            )
            added += 1

        synced += 1

    # 자동매매 계좌에 없는 종목 삭제
    for stock_code, item in portfolio_map.items():
        if stock_code not in account_stock_codes:
            db.delete_portfolio_item(item['id'])
            deleted += 1

    return {
        "success": True,
        "message": f"동기화 완료: {synced}종목 (추가 {added}, 업데이트 {updated}, 삭제 {deleted})",
        "synced_count": synced,
        "added_count": added,
        "updated_count": updated,
        "deleted_count": deleted
    }


# ==================== Green Light (LLM) 설정 ====================

class LLMSettingsRequest(BaseModel):
    """LLM 설정 요청"""
    llm_provider: str  # claude, openai, gemini
    llm_api_key: str
    llm_model: Optional[str] = None  # None이면 기본 모델 사용


class LLMSettingsResponse(BaseModel):
    """LLM 설정 응답"""
    llm_provider: Optional[str]
    llm_model: Optional[str]
    is_configured: bool


@router.get("/llm-settings", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current_user: dict = Depends(get_current_user_required)
):
    """LLM 설정 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    settings = logger.get_llm_settings(current_user.get('id'))

    if settings and settings.get('llm_api_key'):
        return LLMSettingsResponse(
            llm_provider=settings.get('llm_provider'),
            llm_model=settings.get('llm_model'),
            is_configured=True
        )

    return LLMSettingsResponse(
        llm_provider=None,
        llm_model=None,
        is_configured=False
    )


@router.post("/llm-settings")
async def save_llm_settings(
    request: LLMSettingsRequest,
    current_user: dict = Depends(get_current_user_required)
):
    """LLM 설정 저장 (API 키 검증 후 저장)"""
    check_auto_trade_permission(current_user)

    # API 키 유효성 검증
    provider = request.llm_provider.lower()
    api_key = request.llm_api_key.strip()
    model = request.llm_model

    if provider not in ['claude', 'openai', 'gemini']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"지원하지 않는 provider: {provider}"
        )

    # 간단한 API 키 검증 (호출 테스트)
    try:
        from trading.llm_trader import LLMTrader
        trader = LLMTrader(provider=provider, api_key=api_key, model=model)
        # 간단한 테스트 호출은 비용이 발생하므로 생략
        # 대신 클라이언트 초기화 성공 여부만 확인
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LLM 라이브러리 설치 필요: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LLM 초기화 실패: {str(e)}"
        )

    # 저장
    logger = get_trade_logger()
    success = logger.save_llm_settings(
        user_id=current_user.get('id'),
        provider=provider,
        api_key=api_key,
        model=model
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM 설정 저장 실패"
        )

    provider_names = {'claude': 'Claude (Anthropic)', 'openai': 'OpenAI', 'gemini': 'Gemini (Google)'}
    return {
        "message": f"LLM 설정이 저장되었습니다 ({provider_names.get(provider, provider)})",
        "is_configured": True
    }


@router.delete("/llm-settings")
async def delete_llm_settings(
    current_user: dict = Depends(get_current_user_required)
):
    """LLM 설정 삭제"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    # NULL로 설정하여 삭제
    success = logger.save_llm_settings(
        user_id=current_user.get('id'),
        provider=None,
        api_key=None,
        model=None
    )

    return {"message": "LLM 설정이 삭제되었습니다", "is_configured": False}


# ==================== Green Light 결정 이력 ====================

class GreenlightDecision(BaseModel):
    """Green Light 결정"""
    id: int
    decision_time: str
    llm_provider: str
    market_analysis: Optional[str]
    decisions_count: int
    buy_count: int
    sell_count: int
    risk_assessment: Optional[str]


@router.get("/greenlight-decisions")
async def get_greenlight_decisions(
    limit: int = 20,
    current_user: dict = Depends(get_current_user_required)
):
    """Green Light AI 결정 이력 조회"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    decisions = logger.get_greenlight_decisions(current_user.get('id'), limit=limit)

    result = []
    for d in decisions:
        decisions_json = d.get('decisions_json', [])
        if isinstance(decisions_json, str):
            import json
            try:
                decisions_json = json.loads(decisions_json)
            except:
                decisions_json = []

        buy_count = sum(1 for dec in decisions_json if dec.get('action') == 'BUY')
        sell_count = sum(1 for dec in decisions_json if dec.get('action') == 'SELL')

        # raw_response에서 market_analysis, risk_assessment 추출
        raw_response = d.get('raw_response', '')
        market_analysis = ''
        risk_assessment = ''

        if raw_response:
            import json
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw_response)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                    market_analysis = parsed.get('market_analysis', '')
                    risk_assessment = parsed.get('risk_assessment', '')
                except:
                    pass

        result.append({
            "id": d.get('id'),
            "decision_time": d.get('decision_time'),
            "llm_provider": d.get('llm_provider'),
            "market_analysis": market_analysis,
            "decisions_count": len(decisions_json),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "risk_assessment": risk_assessment,
            "decisions": decisions_json,
            "executed_orders": d.get('executed_orders_json', [])
        })

    return {"decisions": result, "total": len(result)}


# ========== 자본 투입/회수 이력 API ==========

class CapitalEventCreate(BaseModel):
    """자본 이벤트 생성 요청"""
    event_date: str  # YYYY-MM-DD
    event_type: str  # 'deposit' or 'withdraw'
    amount: int
    memo: Optional[str] = None


class CapitalEventResponse(BaseModel):
    """자본 이벤트 응답"""
    id: int
    user_id: int
    event_date: str
    event_type: str
    amount: int
    memo: Optional[str]
    created_at: str


class CapitalSummaryResponse(BaseModel):
    """자본 요약 응답"""
    total_deposit: int
    total_withdraw: int
    net_capital: int
    events: List[CapitalEventResponse]
    twr: Optional[float] = None  # 시간가중수익률
    simple_return: Optional[float] = None  # 단순수익률
    current_asset: Optional[int] = None  # 현재 총자산


@router.get("/capital-events")
async def get_capital_events(
    current_user: dict = Depends(get_current_user_required)
):
    """자본 투입/회수 이력 조회 + TWR 계산"""
    check_auto_trade_permission(current_user)

    logger = get_trade_logger()
    user_id = current_user.get('id')

    events = logger.get_capital_events(user_id)
    summary = logger.get_capital_summary(user_id)

    # 현재 총자산 조회 (TWR 계산용)
    current_asset = 0
    twr_data = {'twr': 0, 'simple_return': 0}

    try:
        api_key_data = logger.get_api_key_settings(user_id)
        if api_key_data:
            account_data = logger.get_real_account_balance(
                app_key=api_key_data.get('app_key'),
                app_secret=api_key_data.get('app_secret'),
                account_number=api_key_data.get('account_number'),
                account_product_code=api_key_data.get('account_product_code', '01'),
                is_mock=bool(api_key_data.get('is_mock', True))
            )

            acct_summary = account_data.get('summary', {})
            is_mock = bool(api_key_data.get('is_mock', True))

            if is_mock:
                # 모의투자: 평가금액 + 예수금
                total_eval = acct_summary.get('total_eval_amount', 0) or acct_summary.get('total_evaluation', 0)
                cash = acct_summary.get('d2_cash_balance', 0) or acct_summary.get('cash_balance', 0)
                current_asset = total_eval + cash
            else:
                # 실전투자: 평가금액 + 예수금
                total_eval = acct_summary.get('total_eval_amount', 0) or acct_summary.get('total_evaluation', 0)
                cash = acct_summary.get('d2_cash_balance', 0) or acct_summary.get('cash_balance', 0)
                current_asset = total_eval + cash

            # TWR 계산
            if current_asset > 0 and events:
                twr_data = logger.calculate_twr(user_id, current_asset)
    except Exception as e:
        print(f"TWR 계산 오류: {e}")

    return {
        "total_deposit": summary['total_deposit'],
        "total_withdraw": summary['total_withdraw'],
        "net_capital": summary['net_capital'],
        "events": events,
        "twr": twr_data.get('twr', 0),
        "simple_return": twr_data.get('simple_return', 0),
        "current_asset": current_asset
    }


@router.post("/capital-events", response_model=CapitalEventResponse)
async def create_capital_event(
    event: CapitalEventCreate,
    current_user: dict = Depends(get_current_user_required)
):
    """자본 투입/회수 이벤트 기록"""
    check_auto_trade_permission(current_user)
    
    # 유효성 검사
    if event.event_type not in ('deposit', 'withdraw'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_type must be 'deposit' or 'withdraw'"
        )
    if event.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be positive"
        )
    
    logger = get_trade_logger()
    user_id = current_user.get('id')
    
    event_id = logger.add_capital_event(
        user_id=user_id,
        event_date=event.event_date,
        event_type=event.event_type,
        amount=event.amount,
        memo=event.memo
    )
    
    # 생성된 이벤트 조회
    events = logger.get_capital_events(user_id)
    created_event = next((e for e in events if e['id'] == event_id), None)
    
    if not created_event:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create capital event"
        )
    
    return created_event


@router.delete("/capital-events/{event_id}")
async def delete_capital_event(
    event_id: int,
    current_user: dict = Depends(get_current_user_required)
):
    """자본 이벤트 삭제"""
    check_auto_trade_permission(current_user)
    
    logger = get_trade_logger()
    user_id = current_user.get('id')
    
    success = logger.delete_capital_event(event_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capital event not found or not authorized"
        )
    
    return {"success": True, "message": "Capital event deleted"}
