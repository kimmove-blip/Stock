"""
테마주 검색 API 라우터
- 테마별 관련 종목 제공
- 인기 테마 목록
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter()


class ThemeStock(BaseModel):
    """테마 관련 종목"""
    code: str
    name: str


class Theme(BaseModel):
    """테마 모델"""
    id: str
    name: str
    description: str
    stocks: List[ThemeStock]


# 테마 데이터 (한국 주식시장 대표 테마)
THEMES_DATA = {
    "ai": Theme(
        id="ai",
        name="AI/인공지능",
        description="인공지능, 머신러닝, 빅데이터 관련 기업",
        stocks=[
            ThemeStock(code="005930", name="삼성전자"),
            ThemeStock(code="000660", name="SK하이닉스"),
            ThemeStock(code="035420", name="NAVER"),
            ThemeStock(code="035720", name="카카오"),
            ThemeStock(code="036570", name="엔씨소프트"),
            ThemeStock(code="263750", name="펄어비스"),
            ThemeStock(code="041510", name="에스엠"),
            ThemeStock(code="377300", name="카카오페이"),
            ThemeStock(code="052690", name="한전기술"),
            ThemeStock(code="078340", name="컴투스"),
        ]
    ),
    "ev": Theme(
        id="ev",
        name="전기차/2차전지",
        description="전기차, 배터리, 충전 인프라 관련 기업",
        stocks=[
            ThemeStock(code="373220", name="LG에너지솔루션"),
            ThemeStock(code="006400", name="삼성SDI"),
            ThemeStock(code="051910", name="LG화학"),
            ThemeStock(code="005380", name="현대차"),
            ThemeStock(code="000270", name="기아"),
            ThemeStock(code="096770", name="SK이노베이션"),
            ThemeStock(code="247540", name="에코프로비엠"),
            ThemeStock(code="086520", name="에코프로"),
            ThemeStock(code="012330", name="현대모비스"),
            ThemeStock(code="003670", name="포스코퓨처엠"),
        ]
    ),
    "semiconductor": Theme(
        id="semiconductor",
        name="반도체",
        description="반도체 제조, 장비, 소재 관련 기업",
        stocks=[
            ThemeStock(code="005930", name="삼성전자"),
            ThemeStock(code="000660", name="SK하이닉스"),
            ThemeStock(code="009150", name="삼성전기"),
            ThemeStock(code="042700", name="한미반도체"),
            ThemeStock(code="403870", name="HPSP"),
            ThemeStock(code="058470", name="리노공업"),
            ThemeStock(code="336370", name="솔브레인홀딩스"),
            ThemeStock(code="357780", name="솔브레인"),
            ThemeStock(code="166090", name="하나머티리얼즈"),
            ThemeStock(code="240810", name="원익IPS"),
        ]
    ),
    "bio": Theme(
        id="bio",
        name="바이오/제약",
        description="바이오테크, 제약, 헬스케어 관련 기업",
        stocks=[
            ThemeStock(code="207940", name="삼성바이오로직스"),
            ThemeStock(code="068270", name="셀트리온"),
            ThemeStock(code="326030", name="SK바이오팜"),
            ThemeStock(code="128940", name="한미약품"),
            ThemeStock(code="006280", name="녹십자"),
            ThemeStock(code="000100", name="유한양행"),
            ThemeStock(code="145020", name="휴젤"),
            ThemeStock(code="141080", name="레고켐바이오"),
            ThemeStock(code="196170", name="알테오젠"),
            ThemeStock(code="091990", name="셀트리온헬스케어"),
        ]
    ),
    "defense": Theme(
        id="defense",
        name="방산/우주항공",
        description="국방, 우주항공, 방위산업 관련 기업",
        stocks=[
            ThemeStock(code="012450", name="한화에어로스페이스"),
            ThemeStock(code="047810", name="한국항공우주"),
            ThemeStock(code="000880", name="한화"),
            ThemeStock(code="009830", name="한화솔루션"),
            ThemeStock(code="071970", name="STX중공업"),
            ThemeStock(code="014970", name="삼기오토모티브"),
            ThemeStock(code="003490", name="대한항공"),
            ThemeStock(code="032350", name="롯데관광개발"),
            ThemeStock(code="298050", name="효성첨단소재"),
            ThemeStock(code="064350", name="현대로템"),
        ]
    ),
    "renewable": Theme(
        id="renewable",
        name="신재생에너지",
        description="태양광, 풍력, 수소 등 친환경 에너지 관련 기업",
        stocks=[
            ThemeStock(code="009830", name="한화솔루션"),
            ThemeStock(code="336260", name="두산퓨얼셀"),
            ThemeStock(code="117580", name="대성에너지"),
            ThemeStock(code="095660", name="네오위즈"),
            ThemeStock(code="267250", name="HD현대중공업"),
            ThemeStock(code="009540", name="HD한국조선해양"),
            ThemeStock(code="010140", name="삼성중공업"),
            ThemeStock(code="042660", name="한화오션"),
            ThemeStock(code="015760", name="한국전력"),
            ThemeStock(code="036460", name="한국가스공사"),
        ]
    ),
    "fintech": Theme(
        id="fintech",
        name="핀테크/금융",
        description="디지털 금융, 결제, 블록체인 관련 기업",
        stocks=[
            ThemeStock(code="377300", name="카카오페이"),
            ThemeStock(code="035720", name="카카오"),
            ThemeStock(code="035420", name="NAVER"),
            ThemeStock(code="105560", name="KB금융"),
            ThemeStock(code="055550", name="신한지주"),
            ThemeStock(code="086790", name="하나금융지주"),
            ThemeStock(code="316140", name="우리금융지주"),
            ThemeStock(code="024110", name="기업은행"),
            ThemeStock(code="175330", name="JB금융지주"),
            ThemeStock(code="138930", name="BNK금융지주"),
        ]
    ),
    "entertainment": Theme(
        id="entertainment",
        name="엔터테인먼트/K-콘텐츠",
        description="K-POP, 드라마, 게임 등 콘텐츠 관련 기업",
        stocks=[
            ThemeStock(code="352820", name="하이브"),
            ThemeStock(code="041510", name="에스엠"),
            ThemeStock(code="122870", name="와이지엔터테인먼트"),
            ThemeStock(code="035900", name="JYP엔터테인먼트"),
            ThemeStock(code="036570", name="엔씨소프트"),
            ThemeStock(code="263750", name="펄어비스"),
            ThemeStock(code="078340", name="컴투스"),
            ThemeStock(code="112040", name="위메이드"),
            ThemeStock(code="259960", name="크래프톤"),
            ThemeStock(code="293490", name="카카오게임즈"),
        ]
    ),
    "shipbuilding": Theme(
        id="shipbuilding",
        name="조선/해운",
        description="조선, 해운, 해양플랜트 관련 기업",
        stocks=[
            ThemeStock(code="009540", name="HD한국조선해양"),
            ThemeStock(code="010140", name="삼성중공업"),
            ThemeStock(code="042660", name="한화오션"),
            ThemeStock(code="267250", name="HD현대중공업"),
            ThemeStock(code="329180", name="HD현대마린솔루션"),
            ThemeStock(code="011200", name="HMM"),
            ThemeStock(code="028670", name="팬오션"),
            ThemeStock(code="117580", name="대성에너지"),
            ThemeStock(code="071970", name="STX중공업"),
            ThemeStock(code="010620", name="HD현대미포"),
        ]
    ),
    "robot": Theme(
        id="robot",
        name="로봇/자동화",
        description="산업용 로봇, 자동화 설비, 스마트팩토리 관련 기업",
        stocks=[
            ThemeStock(code="005380", name="현대차"),
            ThemeStock(code="012330", name="현대모비스"),
            ThemeStock(code="009150", name="삼성전기"),
            ThemeStock(code="272210", name="한화시스템"),
            ThemeStock(code="042660", name="한화오션"),
            ThemeStock(code="012450", name="한화에어로스페이스"),
            ThemeStock(code="064350", name="현대로템"),
            ThemeStock(code="090430", name="아모레퍼시픽"),
            ThemeStock(code="006400", name="삼성SDI"),
            ThemeStock(code="241560", name="두산밥캣"),
        ]
    ),
}


@router.get("", response_model=List[Theme])
async def get_all_themes():
    """모든 테마 목록 조회"""
    return list(THEMES_DATA.values())


@router.get("/popular", response_model=List[Theme])
async def get_popular_themes(limit: int = 5):
    """인기 테마 목록 조회"""
    popular_ids = ["ai", "ev", "semiconductor", "bio", "defense"]
    return [THEMES_DATA[tid] for tid in popular_ids[:limit] if tid in THEMES_DATA]


@router.get("/search")
async def search_themes(q: str):
    """테마 검색 - 테마명으로 검색하면 관련 종목 반환"""
    q_lower = q.lower()

    # 테마명 매칭 (부분 일치)
    matched_themes = []
    for theme in THEMES_DATA.values():
        if q_lower in theme.name.lower() or q_lower in theme.id.lower():
            matched_themes.append(theme)

    # 키워드 매핑
    keyword_mapping = {
        "인공지능": "ai", "ai": "ai", "머신러닝": "ai", "빅데이터": "ai",
        "전기차": "ev", "배터리": "ev", "2차전지": "ev", "이차전지": "ev",
        "반도체": "semiconductor", "메모리": "semiconductor", "파운드리": "semiconductor",
        "바이오": "bio", "제약": "bio", "헬스케어": "bio", "신약": "bio",
        "방산": "defense", "국방": "defense", "우주": "defense", "항공": "defense",
        "신재생": "renewable", "태양광": "renewable", "풍력": "renewable", "수소": "renewable",
        "핀테크": "fintech", "금융": "fintech", "결제": "fintech", "은행": "fintech",
        "엔터": "entertainment", "kpop": "entertainment", "게임": "entertainment", "콘텐츠": "entertainment",
        "조선": "shipbuilding", "해운": "shipbuilding", "선박": "shipbuilding",
        "로봇": "robot", "자동화": "robot", "스마트팩토리": "robot",
    }

    # 키워드로 테마 찾기
    for keyword, theme_id in keyword_mapping.items():
        if keyword in q_lower and theme_id in THEMES_DATA:
            theme = THEMES_DATA[theme_id]
            if theme not in matched_themes:
                matched_themes.append(theme)

    if not matched_themes:
        return {"themes": [], "stocks": []}

    # 모든 매칭된 테마의 종목 합치기 (중복 제거)
    all_stocks = {}
    for theme in matched_themes:
        for stock in theme.stocks:
            if stock.code not in all_stocks:
                all_stocks[stock.code] = {
                    "code": stock.code,
                    "name": stock.name,
                    "themes": [theme.name]
                }
            else:
                all_stocks[stock.code]["themes"].append(theme.name)

    return {
        "themes": [{"id": t.id, "name": t.name, "description": t.description} for t in matched_themes],
        "stocks": list(all_stocks.values())
    }


@router.get("/{theme_id}", response_model=Theme)
async def get_theme_detail(theme_id: str):
    """특정 테마 상세 조회"""
    if theme_id not in THEMES_DATA:
        raise HTTPException(status_code=404, detail="테마를 찾을 수 없습니다")
    return THEMES_DATA[theme_id]
