"""
종목 관련 Pydantic 스키마
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class StockBase(BaseModel):
    """종목 기본 정보"""
    code: str = Field(..., description="종목코드")
    name: str = Field(..., description="종목명")


class StockSearch(StockBase):
    """종목 검색 결과"""
    market: Optional[str] = Field(None, description="시장 (KOSPI/KOSDAQ)")


class StockDetail(StockBase):
    """종목 상세 정보"""
    market: Optional[str] = None
    current_price: Optional[int] = Field(None, description="현재가")
    change: Optional[int] = Field(None, description="전일대비")
    change_rate: Optional[float] = Field(None, description="등락률 (%)")
    volume: Optional[int] = Field(None, description="거래량")
    market_cap: Optional[int] = Field(None, description="시가총액")

    # 기술적 지표
    ma5: Optional[float] = Field(None, description="5일 이동평균")
    ma20: Optional[float] = Field(None, description="20일 이동평균")
    ma60: Optional[float] = Field(None, description="60일 이동평균")
    rsi: Optional[float] = Field(None, description="RSI")
    macd: Optional[float] = Field(None, description="MACD")
    macd_signal: Optional[float] = Field(None, description="MACD 시그널")

    updated_at: Optional[datetime] = None


class SupportResistance(BaseModel):
    """지지/저항선"""
    pivot: Optional[float] = Field(None, description="피봇 포인트")
    resistance_1: Optional[float] = Field(None, description="1차 저항선")
    resistance_2: Optional[float] = Field(None, description="2차 저항선")
    support_1: Optional[float] = Field(None, description="1차 지지선")
    support_2: Optional[float] = Field(None, description="2차 지지선")
    recent_high: Optional[float] = Field(None, description="최근 20일 고점")
    recent_low: Optional[float] = Field(None, description="최근 20일 저점")


class StockAnalysis(BaseModel):
    """종목 AI 분석 결과"""
    code: str
    name: str
    score: float = Field(..., ge=0, le=100, description="종합 점수 (0-100)")
    opinion: str = Field(..., description="기술적 신호 (매수/관망/주의/하락 신호)")

    # 상승확률 및 신뢰도
    probability: Optional[float] = Field(None, ge=0, le=100, description="상승 확률 (%)")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="신뢰도 (%)")

    # 세부 분석
    technical_score: Optional[float] = Field(None, description="기술적 분석 점수")
    fundamental_score: Optional[float] = Field(None, description="펀더멘털 분석 점수")
    sentiment_score: Optional[float] = Field(None, description="뉴스 감성 점수")

    # 기술적 지표 상세
    signals: Optional[Dict[str, Any]] = Field(None, description="기술적 신호")
    signal_descriptions: Optional[List[str]] = Field(None, description="신호 설명 리스트 (한글)")

    # 지지/저항선
    support_resistance: Optional[SupportResistance] = Field(None, description="지지/저항선")

    # 분석 코멘트
    comment: Optional[str] = Field(None, description="AI 분석 코멘트")

    analyzed_at: Optional[datetime] = None


class Top100Item(BaseModel):
    """TOP 100 종목"""
    rank: int = Field(..., ge=1, le=100, description="순위")
    code: str
    name: str
    score: float
    opinion: str
    current_price: Optional[int] = None
    change_rate: Optional[float] = None

    # 주요 지표
    rsi: Optional[float] = None
    macd_signal: Optional[float] = None
    volume_surge: Optional[bool] = Field(None, description="거래량 급증 여부")


class Top100Response(BaseModel):
    """TOP 100 응답"""
    date: str = Field(..., description="분석 날짜 (YYYY-MM-DD)")
    total_count: int
    items: List[Top100Item]
