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


def analyze_stock_technical(code: str) -> dict:
    """기술적 분석 기반 종목 분석 - 종목 상세와 동일한 로직"""
    try:
        libs = get_stock_libs()
        if not libs:
            return None

        fdr = libs['fdr']
        get_ohlcv = libs['get_ohlcv']

        # OHLCV 데이터
        ohlcv = get_ohlcv(code, 365)
        if ohlcv is None or ohlcv.empty:
            return None

        current_price = int(ohlcv.iloc[-1]['종가'])

        # 컬럼명 영문으로 변환
        ohlcv = ohlcv.rename(columns={
            '시가': 'Open',
            '고가': 'High',
            '저가': 'Low',
            '종가': 'Close',
            '거래량': 'Volume'
        })

        # 기술적 분석
        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()
        result = analyst.analyze_full(ohlcv)

        if result is None:
            score_tuple = analyst.analyze(ohlcv)
            score = score_tuple[0] if isinstance(score_tuple, tuple) else 50
        else:
            score = result.get('score', 50)

        # 점수 기반 의견 결정 (종목 상세와 동일)
        if score >= 70:
            opinion = '매수'
        elif score >= 50:
            opinion = '관망'
        elif score >= 30:
            opinion = '주의'
        else:
            opinion = '하락 신호'

        return {
            'current_price': current_price,
            'opinion': opinion,
            'score': score
        }

    except Exception as e:
        print(f"기술적 분석 실패 [{code}]: {e}")
        return None


@router.get("/analysis", response_model=PortfolioAnalysis)
async def analyze_portfolio(
    current_user: dict = Depends(get_current_user_required),
    db: DatabaseManager = Depends(get_db)
):
    """포트폴리오 분석"""
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
            recommendations=["보유종목을 추가해주세요."]
        )

    # 분석 실행
    analysis_results = []
    risk_stocks = []
    recommendations = []

    total_investment = 0
    total_value = 0

    for item in items:
        buy_price = int(item['buy_price'] or 0)
        quantity = int(item['quantity'] or 1)

        # 기술적 분석 실행 (종목 상세와 동일)
        result = analyze_stock_technical(item['stock_code'])

        if result:
            opinion = result['opinion']
            score = result['score']
            current_price = int(result['current_price'])
        else:
            opinion = '분석불가'
            score = 0
            current_price = buy_price

        investment = buy_price * quantity
        current_value = current_price * quantity
        profit_loss = int(current_value - investment)
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

        # 주의 종목 판별
        if opinion in ['하락 신호', '주의'] or profit_loss_rate < -10:
            risk_stocks.append({
                'code': item['stock_code'],
                'name': item['stock_name'],
                'opinion': opinion,
                'profit_loss_rate': profit_loss_rate
            })

    # 포트폴리오 상태 분석 (객관적 데이터 기반)
    if risk_stocks:
        recommendations.append(f"주의 종목 {len(risk_stocks)}개")
    if total_value > total_investment * 1.1:
        recommendations.append("수익률 +10% 이상")
    elif total_value < total_investment * 0.9:
        recommendations.append("수익률 -10% 이하")
    else:
        recommendations.append("수익률 ±10% 이내")

    total_profit_loss = int(total_value - total_investment)
    total_profit_loss_rate = round((total_profit_loss / total_investment * 100), 2) if total_investment > 0 else 0

    return PortfolioAnalysis(
        summary=PortfolioSummary(
            total_investment=int(total_investment),
            total_value=int(total_value),
            total_profit_loss=total_profit_loss,
            total_profit_loss_rate=total_profit_loss_rate,
            stock_count=len(analysis_results)
        ),
        items=analysis_results,
        risk_stocks=risk_stocks,
        recommendations=recommendations
    )
