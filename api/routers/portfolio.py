"""
포트폴리오 API 라우터
- 포트폴리오 CRUD, 분석
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.schemas.portfolio import (
    PortfolioItemCreate,
    PortfolioItemUpdate,
    PortfolioItemResponse,
    PortfolioResponse,
    PortfolioSummary,
    PortfolioAnalysis
)
from api.dependencies import get_db, get_current_user_required
from database.db_manager import DatabaseManager

# 주식 라이브러리 지연 임포트
from api.routers.stocks import get_stock_libs


router = APIRouter()


def get_current_price(code: str) -> Optional[int]:
    """현재가 조회"""
    try:
        libs = get_stock_libs()
        if not libs:
            return None
        get_ohlcv = libs['get_ohlcv']
        ohlcv = get_ohlcv(code, 5)
        if ohlcv.empty:
            return None
        return int(ohlcv.iloc[-1]['종가'])
    except:
        return None


@router.get("", response_model=PortfolioResponse)
async def get_portfolio(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """포트폴리오 조회"""
    items = db.get_portfolio(current_user['id'])

    portfolio_items = []
    total_investment = 0
    total_value = 0

    for item in items:
        buy_price = int(item['buy_price'] or 0)
        quantity = int(item['quantity'] or 1)
        investment = buy_price * quantity

        current_price = get_current_price(item['stock_code'])
        current_value = (current_price or buy_price) * quantity

        profit_loss = current_value - investment
        profit_loss_rate = round((profit_loss / investment * 100), 2) if investment > 0 else 0

        total_investment += investment
        total_value += current_value

        portfolio_items.append(PortfolioItemResponse(
            id=item['id'],
            user_id=current_user['id'],
            stock_code=item['stock_code'],
            stock_name=item['stock_name'] or '',
            buy_price=buy_price,
            quantity=quantity,
            buy_date=item.get('buy_date'),
            current_price=current_price,
            profit_loss=profit_loss,
            profit_loss_rate=profit_loss_rate
        ))

    total_profit_loss = total_value - total_investment
    total_profit_loss_rate = round((total_profit_loss / total_investment * 100), 2) if total_investment > 0 else 0

    return PortfolioResponse(
        summary=PortfolioSummary(
            total_investment=total_investment,
            total_value=total_value,
            total_profit_loss=total_profit_loss,
            total_profit_loss_rate=total_profit_loss_rate,
            stock_count=len(portfolio_items)
        ),
        items=portfolio_items
    )


@router.post("", response_model=PortfolioItemResponse, status_code=status.HTTP_201_CREATED)
async def add_portfolio_item(
    item: PortfolioItemCreate,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """포트폴리오 종목 추가"""
    item_id = db.add_portfolio_item(
        user_id=current_user['id'],
        stock_code=item.stock_code,
        stock_name=item.stock_name,
        buy_price=item.buy_price,
        quantity=item.quantity,
        buy_date=item.buy_date
    )

    current_price = get_current_price(item.stock_code)
    investment = item.buy_price * item.quantity
    current_value = (current_price or item.buy_price) * item.quantity
    profit_loss = current_value - investment
    profit_loss_rate = round((profit_loss / investment * 100), 2) if investment > 0 else 0

    return PortfolioItemResponse(
        id=item_id,
        user_id=current_user['id'],
        stock_code=item.stock_code,
        stock_name=item.stock_name,
        buy_price=item.buy_price,
        quantity=item.quantity,
        buy_date=item.buy_date,
        current_price=current_price,
        profit_loss=profit_loss,
        profit_loss_rate=profit_loss_rate
    )


@router.put("/{item_id}", response_model=PortfolioItemResponse)
async def update_portfolio_item(
    item_id: int,
    item: PortfolioItemUpdate,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """포트폴리오 종목 수정"""
    # 본인 소유 확인
    portfolio = db.get_portfolio(current_user['id'])
    existing = next((p for p in portfolio if p['id'] == item_id), None)

    if not existing:
        raise HTTPException(status_code=404, detail="포트폴리오 항목을 찾을 수 없습니다")

    # 업데이트
    update_data = {}
    if item.buy_price is not None:
        update_data['buy_price'] = item.buy_price
    if item.quantity is not None:
        update_data['quantity'] = item.quantity
    if item.buy_date is not None:
        update_data['buy_date'] = item.buy_date

    if update_data:
        db.update_portfolio_item(item_id, **update_data)

    # 업데이트된 정보 반환
    portfolio = db.get_portfolio(current_user['id'])
    updated = next((p for p in portfolio if p['id'] == item_id), None)

    buy_price = updated['buy_price'] or 0
    quantity = updated['quantity'] or 1
    current_price = get_current_price(updated['stock_code'])
    investment = buy_price * quantity
    current_value = (current_price or buy_price) * quantity
    profit_loss = current_value - investment
    profit_loss_rate = round((profit_loss / investment * 100), 2) if investment > 0 else 0

    return PortfolioItemResponse(
        id=updated['id'],
        user_id=current_user['id'],
        stock_code=updated['stock_code'],
        stock_name=updated['stock_name'] or '',
        buy_price=buy_price,
        quantity=quantity,
        buy_date=updated.get('buy_date'),
        current_price=current_price,
        profit_loss=profit_loss,
        profit_loss_rate=profit_loss_rate
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio_item(
    item_id: int,
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """포트폴리오 종목 삭제"""
    # 본인 소유 확인
    portfolio = db.get_portfolio(current_user['id'])
    existing = next((p for p in portfolio if p['id'] == item_id), None)

    if not existing:
        raise HTTPException(status_code=404, detail="포트폴리오 항목을 찾을 수 없습니다")

    db.delete_portfolio_item(item_id)


@router.get("/analysis", response_model=PortfolioAnalysis)
async def analyze_portfolio(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """포트폴리오 분석"""
    try:
        from portfolio_advisor import PortfolioAdvisor
        advisor = PortfolioAdvisor()
    except ImportError:
        raise HTTPException(status_code=503, detail="분석 서비스 이용 불가")

    items = db.get_portfolio(current_user['id'])
    if not items:
        return PortfolioAnalysis(
            summary=PortfolioSummary(
                total_investment=0,
                total_value=0,
                total_profit_loss=0,
                total_profit_loss_rate=0,
                stock_count=0
            ),
            items=[],
            risk_stocks=[],
            recommendations=["포트폴리오에 종목을 추가해주세요."]
        )

    # 분석 실행
    analysis_results = []
    risk_stocks = []
    recommendations = []

    total_investment = 0
    total_value = 0

    for item in items:
        try:
            result = advisor.analyze_stock(item['stock_code'])
            opinion = result.get('opinion', '보유')
            score = result.get('score', 50)

            buy_price = item['buy_price'] or 0
            quantity = item['quantity'] or 1
            current_price = result.get('current_price') or get_current_price(item['stock_code']) or buy_price

            investment = buy_price * quantity
            current_value = current_price * quantity
            profit_loss = current_value - investment
            profit_loss_rate = round((profit_loss / investment * 100), 2) if investment > 0 else 0

            total_investment += investment
            total_value += current_value

            analysis_results.append(PortfolioItemResponse(
                id=item['id'],
                user_id=current_user['id'],
                stock_code=item['stock_code'],
                stock_name=item['stock_name'] or '',
                buy_price=buy_price,
                quantity=quantity,
                buy_date=item.get('buy_date'),
                current_price=current_price,
                profit_loss=profit_loss,
                profit_loss_rate=profit_loss_rate,
                ai_opinion=opinion,
                ai_score=score
            ))

            # 위험 종목 판별
            if opinion in ['매도', '손절'] or profit_loss_rate < -10:
                risk_stocks.append({
                    'code': item['stock_code'],
                    'name': item['stock_name'],
                    'opinion': opinion,
                    'profit_loss_rate': profit_loss_rate
                })

        except Exception as e:
            # 분석 실패 시 기본값
            analysis_results.append(PortfolioItemResponse(
                id=item['id'],
                user_id=current_user['id'],
                stock_code=item['stock_code'],
                stock_name=item['stock_name'] or '',
                buy_price=item['buy_price'] or 0,
                quantity=item['quantity'] or 1,
                buy_date=item.get('buy_date'),
                ai_opinion='분석불가'
            ))

    # 추천 액션 생성
    if risk_stocks:
        recommendations.append(f"위험 종목 {len(risk_stocks)}개 확인 필요")
    if total_value > total_investment:
        recommendations.append("전체 수익 상태 - 익절 시점 검토")
    elif total_value < total_investment * 0.9:
        recommendations.append("전체 손실 상태 - 손절 또는 추가 매수 검토")

    total_profit_loss = total_value - total_investment
    total_profit_loss_rate = round((total_profit_loss / total_investment * 100), 2) if total_investment > 0 else 0

    return PortfolioAnalysis(
        summary=PortfolioSummary(
            total_investment=total_investment,
            total_value=total_value,
            total_profit_loss=total_profit_loss,
            total_profit_loss_rate=total_profit_loss_rate,
            stock_count=len(analysis_results)
        ),
        items=analysis_results,
        risk_stocks=risk_stocks,
        recommendations=recommendations
    )
