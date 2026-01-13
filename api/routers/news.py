"""
시장 뉴스 API 라우터
- 네이버 뉴스 검색 API 연동
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# 네이버 API 설정
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"


class NewsItem(BaseModel):
    """뉴스 항목"""
    title: str
    link: str
    description: str
    pub_date: str
    source: Optional[str] = None


class NewsResponse(BaseModel):
    """뉴스 응답"""
    items: List[NewsItem]
    total: int
    query: str
    fetched_at: str


def clean_html(text: str) -> str:
    """HTML 태그 제거"""
    import re
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&quot;', '"').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&apos;', "'")
    return text.strip()


def extract_source(link: str) -> str:
    """링크에서 출처 추출"""
    source_map = {
        'yna.co.kr': '연합뉴스',
        'hankyung.com': '한국경제',
        'mk.co.kr': '매일경제',
        'mt.co.kr': '머니투데이',
        'sedaily.com': '서울경제',
        'edaily.co.kr': '이데일리',
        'fnnews.com': '파이낸셜뉴스',
        'asiae.co.kr': '아시아경제',
        'news1.kr': '뉴스1',
        'newsis.com': '뉴시스',
        'chosun.com': '조선일보',
        'donga.com': '동아일보',
        'joins.com': '중앙일보',
        'hani.co.kr': '한겨레',
        'khan.co.kr': '경향신문',
    }
    for domain, name in source_map.items():
        if domain in link:
            return name
    return '뉴스'


def parse_date(date_str: str) -> str:
    """날짜 파싱 및 상대 시간 변환"""
    try:
        # "Mon, 13 Jan 2026 10:30:00 +0900" 형식
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        now = datetime.now(dt.tzinfo)
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days}일 전"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}시간 전"
        minutes = diff.seconds // 60
        if minutes > 0:
            return f"{minutes}분 전"
        return "방금 전"
    except:
        return date_str


@router.get("", response_model=NewsResponse)
async def get_news(
    query: str = Query("주식 증시", description="검색어"),
    display: int = Query(20, ge=1, le=100, description="결과 개수")
):
    """
    증권/경제 뉴스 검색

    - query: 검색어 (기본: 주식 증시)
    - display: 결과 개수 (기본: 20, 최대: 100)
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="뉴스 API가 설정되지 않았습니다. 관리자에게 문의하세요."
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                NAVER_NEWS_API_URL,
                params={
                    "query": query,
                    "display": display,
                    "sort": "date"  # 최신순
                },
                headers={
                    "X-Naver-Client-Id": NAVER_CLIENT_ID,
                    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
                },
                timeout=10.0
            )

            if response.status_code != 200:
                print(f"[News API Error] Status: {response.status_code}, Body: {response.text}")
                raise HTTPException(status_code=502, detail="뉴스 API 호출 실패")

            data = response.json()

            items = []
            for item in data.get("items", []):
                items.append(NewsItem(
                    title=clean_html(item.get("title", "")),
                    link=item.get("originallink") or item.get("link", ""),
                    description=clean_html(item.get("description", "")),
                    pub_date=parse_date(item.get("pubDate", "")),
                    source=extract_source(item.get("originallink") or item.get("link", ""))
                ))

            return NewsResponse(
                items=items,
                total=data.get("total", len(items)),
                query=query,
                fetched_at=datetime.now().isoformat()
            )

    except httpx.RequestError as e:
        print(f"[News API Error] {e}")
        raise HTTPException(status_code=502, detail="뉴스 서버 연결 실패")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[News API Error] {e}")
        raise HTTPException(status_code=500, detail="뉴스 처리 중 오류 발생")


@router.get("/categories")
async def get_news_by_category(
    category: str = Query("시장", description="카테고리"),
    display: int = Query(10, ge=1, le=50)
):
    """
    카테고리별 뉴스 조회

    - 시장: 코스피 코스닥 증시
    - 기업: 삼성 현대 SK LG
    - 해외: 미국 나스닥 다우존스
    - 테마: 2차전지 AI반도체 바이오
    """
    category_queries = {
        "시장": "코스피 코스닥 증시",
        "기업": "삼성전자 현대차 SK하이닉스",
        "해외": "미국증시 나스닥 다우존스",
        "테마": "2차전지 AI반도체 바이오",
    }

    query = category_queries.get(category, "주식 증시")
    return await get_news(query=query, display=display)
