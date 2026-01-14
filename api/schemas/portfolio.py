"""
포트폴리오 관련 Pydantic 스키마
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PortfolioItemBase(BaseModel):
    """포트폴리오 종목 기본 정보"""
    stock_code: str = Field(..., description="종목코드")
    stock_name: str = Field(..., description="종목명")
    buy_price: int = Field(..., ge=0, description="매수가")
    quantity: int = Field(..., ge=1, description="수량")
    buy_date: Optional[str] = Field(None, description="매수일 (YYYY-MM-DD)")


class PortfolioItemCreate(PortfolioItemBase):
    """포트폴리오 종목 추가 요청"""
    pass


class PortfolioItemUpdate(BaseModel):
    """포트폴리오 종목 수정 요청"""
    buy_price: Optional[int] = Field(None, ge=0)
    quantity: Optional[int] = Field(None, ge=1)
    buy_date: Optional[str] = None


class PortfolioItemResponse(PortfolioItemBase):
    """포트폴리오 종목 응답"""
    id: int
    user_id: int

    # 현재 가격 정보
    current_price: Optional[int] = Field(None, description="현재가")
    profit_loss: Optional[int] = Field(None, description="손익 금액")
    profit_loss_rate: Optional[float] = Field(None, description="손익률 (%)")

    # AI 분석 정보
    ai_opinion: Optional[str] = Field(None, description="AI 의견 (매수/관망/주의/하락 신호)")
    ai_score: Optional[float] = Field(None, description="AI 점수")

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PortfolioSummary(BaseModel):
    """포트폴리오 요약"""
    total_investment: int = Field(..., description="총 투자금액")
    total_value: int = Field(..., description="현재 평가금액")
    total_profit_loss: int = Field(..., description="총 손익")
    total_profit_loss_rate: float = Field(..., description="총 수익률 (%)")
    stock_count: int = Field(..., description="보유 종목 수")


class PortfolioResponse(BaseModel):
    """포트폴리오 전체 응답"""
    summary: PortfolioSummary
    items: List[PortfolioItemResponse]


class PortfolioAnalysis(BaseModel):
    """포트폴리오 분석 결과"""
    summary: PortfolioSummary

    # 종목별 분석
    items: List[PortfolioItemResponse]

    # 위험 종목
    risk_stocks: List[dict] = Field(default=[], description="위험 종목 목록")

    # 추천 액션
    recommendations: List[str] = Field(default=[], description="추천 액션")

    analyzed_at: Optional[datetime] = None


class WatchlistItemCreate(BaseModel):
    """관심종목 추가 요청"""
    stock_code: str = Field(..., description="종목코드")
    stock_name: str = Field(..., description="종목명")
    category: Optional[str] = Field("기본", description="카테고리")
    memo: Optional[str] = Field(None, description="메모")


class WatchlistItemResponse(BaseModel):
    """관심종목 응답"""
    id: int
    user_id: int
    stock_code: str
    stock_name: str
    category: Optional[str] = "기본"
    memo: Optional[str] = None

    # 현재 가격 정보
    current_price: Optional[int] = None
    change_rate: Optional[float] = None

    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WatchlistResponse(BaseModel):
    """관심종목 목록 응답"""
    total_count: int
    categories: List[str]
    items: List[WatchlistItemResponse]
