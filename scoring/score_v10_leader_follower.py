"""
V10 스코어링 엔진 - Leader-Follower (대장주-종속주 전략)

핵심 컨셉:
- 같은 테마/섹터 내에서 대장주와 종속주는 높은 상관관계를 보임
- 대장주가 먼저 움직이면 종속주가 시차를 두고 따라가는 경향
- 이 시간차(Time Lag)를 이용해 대장주 상승 시 종속주 매수

전략 로직:
1. 대장주가 금일 +3% 이상 상승했는지 확인
2. 종속주가 아직 따라가지 못했는지 확인 (상대적 언더퍼폼)
3. 상관계수 0.7 이상인 종목에 높은 점수 부여
4. 대장주와의 수익률 갭이 클수록 높은 점수

점수 체계 (100점 만점):
- 대장주 움직임 (35점): 대장주 상승률, 거래량 동반
- 상관관계 (25점): 피어슨 상관계수 0.7~0.9+
- 캐치업 갭 (25점): 대장주 대비 언더퍼폼 정도
- 기술적 지지 (15점): MA, RSI, 볼린저밴드 지지

청산 전략:
- 목표가: 대장주 상승률의 70~80% 수준 캐치업
- 손절가: -3% (빠른 손절)
- 시간 손절: 최대 3일 (모멘텀 소멸)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta


# ============================================================
# 테마/섹터별 대장주-종속주 매핑
# 각 테마별로 대장주(leaders)와 종속주(followers) 정의
# 대장주: 시가총액 상위 or 업종 대표 종목
# ============================================================
THEME_STOCK_MAP = {
    # ==================== IT/반도체 ====================
    "반도체": {
        "leaders": [
            {"code": "005930", "name": "삼성전자", "weight": 1.0},
            {"code": "000660", "name": "SK하이닉스", "weight": 0.9},
        ],
        "followers": [
            {"code": "042700", "name": "한미반도체", "corr_target": "000660"},
            {"code": "403870", "name": "HPSP", "corr_target": "000660"},
            {"code": "058470", "name": "리노공업", "corr_target": "000660"},
            {"code": "089030", "name": "테크윙", "corr_target": "000660"},
            {"code": "166090", "name": "하나머티리얼즈", "corr_target": "000660"},
            {"code": "240810", "name": "원익IPS", "corr_target": "000660"},
            {"code": "039030", "name": "이오테크닉스", "corr_target": "000660"},
            {"code": "036830", "name": "솔브레인홀딩스", "corr_target": "000660"},
            {"code": "357780", "name": "솔브레인", "corr_target": "000660"},
            {"code": "007660", "name": "이수페타시스", "corr_target": "005930"},
            {"code": "009150", "name": "삼성전기", "corr_target": "005930"},
            {"code": "006400", "name": "삼성SDI", "corr_target": "005930"},
            {"code": "005290", "name": "동진쎄미켐", "corr_target": "005930"},
        ]
    },
    "HBM/AI반도체": {
        "leaders": [
            {"code": "000660", "name": "SK하이닉스", "weight": 1.0},
        ],
        "followers": [
            {"code": "042700", "name": "한미반도체", "corr_target": "000660"},
            {"code": "403870", "name": "HPSP", "corr_target": "000660"},
            {"code": "058470", "name": "리노공업", "corr_target": "000660"},
            {"code": "036830", "name": "솔브레인홀딩스", "corr_target": "000660"},
            {"code": "025560", "name": "미래산업", "corr_target": "000660"},
            {"code": "185750", "name": "종근당", "corr_target": "000660"},
        ]
    },
    "디스플레이": {
        "leaders": [
            {"code": "034220", "name": "LG디스플레이", "weight": 1.0},
        ],
        "followers": [
            {"code": "131970", "name": "테스나", "corr_target": "034220"},
            {"code": "272290", "name": "이녹스첨단소재", "corr_target": "034220"},
            {"code": "096530", "name": "씨젠", "corr_target": "034220"},
            {"code": "036490", "name": "SK가스", "corr_target": "034220"},
        ]
    },
    # ==================== 2차전지/에너지 ====================
    "2차전지": {
        "leaders": [
            {"code": "373220", "name": "LG에너지솔루션", "weight": 1.0},
            {"code": "006400", "name": "삼성SDI", "weight": 0.9},
        ],
        "followers": [
            {"code": "247540", "name": "에코프로비엠", "corr_target": "373220"},
            {"code": "086520", "name": "에코프로", "corr_target": "373220"},
            {"code": "003670", "name": "포스코퓨처엠", "corr_target": "373220"},
            {"code": "051910", "name": "LG화학", "corr_target": "373220"},
            {"code": "096770", "name": "SK이노베이션", "corr_target": "006400"},
            {"code": "011790", "name": "SKC", "corr_target": "373220"},
            {"code": "108320", "name": "LX세미콘", "corr_target": "373220"},
            {"code": "006260", "name": "LS", "corr_target": "373220"},
        ]
    },
    "원전": {
        "leaders": [
            {"code": "034020", "name": "두산에너빌리티", "weight": 1.0},
        ],
        "followers": [
            {"code": "052690", "name": "한전기술", "corr_target": "034020"},
            {"code": "051600", "name": "한전KPS", "corr_target": "034020"},
            {"code": "083650", "name": "비에이치아이", "corr_target": "034020"},
            {"code": "105840", "name": "우진", "corr_target": "034020"},
            {"code": "013870", "name": "지투파워", "corr_target": "034020"},
            {"code": "092200", "name": "디아이씨", "corr_target": "034020"},
        ]
    },
    "전력설비/전선": {
        "leaders": [
            {"code": "267260", "name": "HD현대일렉트릭", "weight": 1.0},
            {"code": "010120", "name": "LS ELECTRIC", "weight": 0.9},
        ],
        "followers": [
            {"code": "298040", "name": "효성중공업", "corr_target": "267260"},
            {"code": "001440", "name": "대한전선", "corr_target": "010120"},
            {"code": "000500", "name": "가온전선", "corr_target": "010120"},
            {"code": "000480", "name": "조선내화", "corr_target": "267260"},
            {"code": "006260", "name": "LS", "corr_target": "010120"},
        ]
    },
    "전력/에너지": {
        "leaders": [
            {"code": "015760", "name": "한국전력", "weight": 1.0},
        ],
        "followers": [
            {"code": "036460", "name": "한국가스공사", "corr_target": "015760"},
            {"code": "017390", "name": "서울가스", "corr_target": "015760"},
            {"code": "034020", "name": "두산에너빌리티", "corr_target": "015760"},
            {"code": "267250", "name": "HD현대중공업", "corr_target": "015760"},
            {"code": "267260", "name": "HD현대일렉트릭", "corr_target": "015760"},
        ]
    },
    # ==================== 바이오/헬스케어 ====================
    "바이오": {
        "leaders": [
            {"code": "207940", "name": "삼성바이오로직스", "weight": 1.0},
            {"code": "068270", "name": "셀트리온", "weight": 0.9},
        ],
        "followers": [
            {"code": "326030", "name": "SK바이오팜", "corr_target": "207940"},
            {"code": "196170", "name": "알테오젠", "corr_target": "207940"},
            {"code": "145020", "name": "휴젤", "corr_target": "068270"},
            {"code": "141080", "name": "레고켐바이오", "corr_target": "068270"},
            {"code": "091990", "name": "셀트리온헬스케어", "corr_target": "068270"},
            {"code": "302440", "name": "SK바이오사이언스", "corr_target": "207940"},
            {"code": "328130", "name": "루닛", "corr_target": "207940"},
        ]
    },
    "제약": {
        "leaders": [
            {"code": "000100", "name": "유한양행", "weight": 1.0},
            {"code": "128940", "name": "한미약품", "weight": 0.9},
        ],
        "followers": [
            {"code": "006280", "name": "녹십자", "corr_target": "000100"},
            {"code": "185750", "name": "종근당", "corr_target": "000100"},
            {"code": "003060", "name": "에이프로젠", "corr_target": "128940"},
            {"code": "003850", "name": "보령", "corr_target": "000100"},
            {"code": "000020", "name": "동화약품", "corr_target": "000100"},
        ]
    },
    "의료기기": {
        "leaders": [
            {"code": "096530", "name": "씨젠", "weight": 1.0},
        ],
        "followers": [
            {"code": "048260", "name": "오스템임플란트", "corr_target": "096530"},
            {"code": "039840", "name": "디오", "corr_target": "096530"},
            {"code": "214370", "name": "케어젠", "corr_target": "096530"},
            {"code": "298380", "name": "에이비엘바이오", "corr_target": "096530"},
        ]
    },
    "의료AI": {
        "leaders": [
            {"code": "328130", "name": "루닛", "weight": 1.0},
        ],
        "followers": [
            {"code": "338220", "name": "뷰노", "corr_target": "328130"},
            {"code": "322510", "name": "제이엘케이", "corr_target": "328130"},
            {"code": "315640", "name": "딥노이드", "corr_target": "328130"},
        ]
    },
    # ==================== 플랫폼/IT서비스 ====================
    "플랫폼": {
        "leaders": [
            {"code": "035420", "name": "NAVER", "weight": 1.0},
            {"code": "035720", "name": "카카오", "weight": 0.9},
        ],
        "followers": [
            {"code": "377300", "name": "카카오페이", "corr_target": "035720"},
            {"code": "293490", "name": "카카오게임즈", "corr_target": "035720"},
            {"code": "263750", "name": "펄어비스", "corr_target": "035720"},
            {"code": "030200", "name": "KT", "corr_target": "035420"},
            {"code": "032640", "name": "LG유플러스", "corr_target": "035420"},
        ]
    },
    "AI/클라우드": {
        "leaders": [
            {"code": "018260", "name": "삼성에스디에스", "weight": 1.0},
        ],
        "followers": [
            {"code": "181710", "name": "NHN", "corr_target": "018260"},
            {"code": "035760", "name": "CJ ENM", "corr_target": "018260"},
            {"code": "030520", "name": "한글과컴퓨터", "corr_target": "018260"},
            {"code": "053800", "name": "안랩", "corr_target": "018260"},
        ]
    },
    # ==================== 엔터/콘텐츠 ====================
    "엔터": {
        "leaders": [
            {"code": "352820", "name": "하이브", "weight": 1.0},
        ],
        "followers": [
            {"code": "041510", "name": "에스엠", "corr_target": "352820"},
            {"code": "122870", "name": "와이지엔터테인먼트", "corr_target": "352820"},
            {"code": "035900", "name": "JYP Ent.", "corr_target": "352820"},
            {"code": "253450", "name": "스튜디오드래곤", "corr_target": "352820"},
        ]
    },
    "게임": {
        "leaders": [
            {"code": "259960", "name": "크래프톤", "weight": 1.0},
            {"code": "036570", "name": "엔씨소프트", "weight": 0.8},
        ],
        "followers": [
            {"code": "263750", "name": "펄어비스", "corr_target": "259960"},
            {"code": "078340", "name": "컴투스", "corr_target": "036570"},
            {"code": "112040", "name": "위메이드", "corr_target": "036570"},
            {"code": "293490", "name": "카카오게임즈", "corr_target": "259960"},
            {"code": "194480", "name": "데브시스터즈", "corr_target": "259960"},
            {"code": "069080", "name": "웹젠", "corr_target": "036570"},
        ]
    },
    # ==================== 조선/해운 ====================
    "조선": {
        "leaders": [
            {"code": "009540", "name": "HD한국조선해양", "weight": 1.0},
        ],
        "followers": [
            {"code": "010140", "name": "삼성중공업", "corr_target": "009540"},
            {"code": "042660", "name": "한화오션", "corr_target": "009540"},
            {"code": "329180", "name": "HD현대마린솔루션", "corr_target": "009540"},
            {"code": "010620", "name": "HD현대미포", "corr_target": "009540"},
            {"code": "267250", "name": "HD현대중공업", "corr_target": "009540"},
        ]
    },
    "해운": {
        "leaders": [
            {"code": "011200", "name": "HMM", "weight": 1.0},
        ],
        "followers": [
            {"code": "028670", "name": "팬오션", "corr_target": "011200"},
            {"code": "003480", "name": "한진중공업홀딩스", "corr_target": "011200"},
            {"code": "000700", "name": "유수홀딩스", "corr_target": "011200"},
        ]
    },
    # ==================== 방산/항공 ====================
    "방산": {
        "leaders": [
            {"code": "012450", "name": "한화에어로스페이스", "weight": 1.0},
        ],
        "followers": [
            {"code": "047810", "name": "한국항공우주", "corr_target": "012450"},
            {"code": "064350", "name": "현대로템", "corr_target": "012450"},
            {"code": "272210", "name": "한화시스템", "corr_target": "012450"},
            {"code": "000880", "name": "한화", "corr_target": "012450"},
            {"code": "009830", "name": "한화솔루션", "corr_target": "012450"},
        ]
    },
    "항공": {
        "leaders": [
            {"code": "003490", "name": "대한항공", "weight": 1.0},
        ],
        "followers": [
            {"code": "020560", "name": "아시아나항공", "corr_target": "003490"},
            {"code": "272450", "name": "진에어", "corr_target": "003490"},
            {"code": "089590", "name": "제주항공", "corr_target": "003490"},
            {"code": "039130", "name": "하나투어", "corr_target": "003490"},
        ]
    },
    # ==================== 자동차/부품 ====================
    "자동차": {
        "leaders": [
            {"code": "005380", "name": "현대차", "weight": 1.0},
            {"code": "000270", "name": "기아", "weight": 0.95},
        ],
        "followers": [
            {"code": "012330", "name": "현대모비스", "corr_target": "005380"},
            {"code": "018880", "name": "한온시스템", "corr_target": "005380"},
            {"code": "161390", "name": "한국타이어앤테크놀로지", "corr_target": "005380"},
            {"code": "011210", "name": "현대위아", "corr_target": "005380"},
            {"code": "204320", "name": "만도", "corr_target": "005380"},
            {"code": "298050", "name": "효성첨단소재", "corr_target": "005380"},
        ]
    },
    "로봇": {
        "leaders": [
            {"code": "454910", "name": "두산로보틱스", "weight": 1.0},
            {"code": "277810", "name": "레인보우로보틱스", "weight": 0.95},
        ],
        "followers": [
            {"code": "340930", "name": "뉴로메카", "corr_target": "454910"},
            {"code": "058610", "name": "에스피지", "corr_target": "277810"},
            {"code": "446070", "name": "이랜시스", "corr_target": "277810"},
            {"code": "313760", "name": "큐렉소", "corr_target": "454910"},
            {"code": "108490", "name": "로보티즈", "corr_target": "454910"},
            {"code": "090460", "name": "비에이치", "corr_target": "454910"},
            {"code": "264660", "name": "씨앤지하이테크", "corr_target": "454910"},
        ]
    },
    # ==================== 금융 ====================
    "은행": {
        "leaders": [
            {"code": "105560", "name": "KB금융", "weight": 1.0},
            {"code": "055550", "name": "신한지주", "weight": 0.95},
        ],
        "followers": [
            {"code": "086790", "name": "하나금융지주", "corr_target": "105560"},
            {"code": "316140", "name": "우리금융지주", "corr_target": "105560"},
            {"code": "024110", "name": "기업은행", "corr_target": "055550"},
            {"code": "175330", "name": "JB금융지주", "corr_target": "055550"},
            {"code": "138930", "name": "BNK금융지주", "corr_target": "055550"},
            {"code": "139130", "name": "DGB금융지주", "corr_target": "055550"},
        ]
    },
    "보험": {
        "leaders": [
            {"code": "000810", "name": "삼성화재", "weight": 1.0},
        ],
        "followers": [
            {"code": "001450", "name": "현대해상", "corr_target": "000810"},
            {"code": "005830", "name": "DB손해보험", "corr_target": "000810"},
            {"code": "138040", "name": "메리츠화재", "corr_target": "000810"},
            {"code": "088350", "name": "한화생명", "corr_target": "000810"},
            {"code": "032830", "name": "삼성생명", "corr_target": "000810"},
        ]
    },
    "증권": {
        "leaders": [
            {"code": "006800", "name": "미래에셋증권", "weight": 1.0},
        ],
        "followers": [
            {"code": "016360", "name": "삼성증권", "corr_target": "006800"},
            {"code": "071050", "name": "한국금융지주", "corr_target": "006800"},
            {"code": "005940", "name": "NH투자증권", "corr_target": "006800"},
            {"code": "003540", "name": "대신증권", "corr_target": "006800"},
            {"code": "030610", "name": "교보증권", "corr_target": "006800"},
        ]
    },
    # ==================== 건설/철강 ====================
    "건설": {
        "leaders": [
            {"code": "000720", "name": "현대건설", "weight": 1.0},
            {"code": "028260", "name": "삼성물산", "weight": 0.9},
        ],
        "followers": [
            {"code": "047040", "name": "대우건설", "corr_target": "000720"},
            {"code": "006360", "name": "GS건설", "corr_target": "000720"},
            {"code": "375500", "name": "DL이앤씨", "corr_target": "000720"},
            {"code": "000210", "name": "DL", "corr_target": "028260"},
            {"code": "005850", "name": "에스엘", "corr_target": "028260"},
        ]
    },
    "철강": {
        "leaders": [
            {"code": "005490", "name": "POSCO홀딩스", "weight": 1.0},
        ],
        "followers": [
            {"code": "004020", "name": "현대제철", "corr_target": "005490"},
            {"code": "001230", "name": "동국제강", "corr_target": "005490"},
            {"code": "103140", "name": "풍산", "corr_target": "005490"},
            {"code": "004890", "name": "동일산업", "corr_target": "005490"},
        ]
    },
    # ==================== 유통/소비재 ====================
    "유통": {
        "leaders": [
            {"code": "004170", "name": "신세계", "weight": 1.0},
        ],
        "followers": [
            {"code": "069960", "name": "현대백화점", "corr_target": "004170"},
            {"code": "023530", "name": "롯데쇼핑", "corr_target": "004170"},
            {"code": "139480", "name": "이마트", "corr_target": "004170"},
            {"code": "007070", "name": "GS리테일", "corr_target": "004170"},
            {"code": "282330", "name": "BGF리테일", "corr_target": "004170"},
        ]
    },
    "음식료": {
        "leaders": [
            {"code": "097950", "name": "CJ제일제당", "weight": 1.0},
        ],
        "followers": [
            {"code": "271560", "name": "오리온", "corr_target": "097950"},
            {"code": "004370", "name": "농심", "corr_target": "097950"},
            {"code": "003230", "name": "삼양식품", "corr_target": "097950"},
            {"code": "033780", "name": "KT&G", "corr_target": "097950"},
            {"code": "005300", "name": "롯데칠성", "corr_target": "097950"},
        ]
    },
    "K-푸드": {
        "leaders": [
            {"code": "003230", "name": "삼양식품", "weight": 1.0},
            {"code": "004370", "name": "농심", "weight": 0.8},
        ],
        "followers": [
            {"code": "005180", "name": "빙그레", "corr_target": "003230"},
            {"code": "271560", "name": "오리온", "corr_target": "004370"},
            {"code": "145990", "name": "삼양사", "corr_target": "003230"},
            {"code": "097950", "name": "CJ제일제당", "corr_target": "004370"},
            {"code": "005300", "name": "롯데칠성", "corr_target": "003230"},
        ]
    },
    "화장품": {
        "leaders": [
            {"code": "090430", "name": "아모레퍼시픽", "weight": 1.0},
        ],
        "followers": [
            {"code": "002790", "name": "아모레G", "corr_target": "090430"},
            {"code": "051900", "name": "LG생활건강", "corr_target": "090430"},
            {"code": "214150", "name": "클래시스", "corr_target": "090430"},
            {"code": "092730", "name": "네오팜", "corr_target": "090430"},
            {"code": "078520", "name": "에이블씨엔씨", "corr_target": "090430"},
        ]
    },
    "화장품OEM": {
        "leaders": [
            {"code": "192820", "name": "코스맥스", "weight": 1.0},
            {"code": "161890", "name": "한국콜마", "weight": 0.9},
        ],
        "followers": [
            {"code": "352480", "name": "씨앤씨인터내셔널", "corr_target": "192820"},
            {"code": "237690", "name": "에이블씨엔씨", "corr_target": "192820"},
            {"code": "226320", "name": "잇츠한불", "corr_target": "161890"},
            {"code": "241710", "name": "코스메카코리아", "corr_target": "192820"},
        ]
    },
    # ==================== 통신 ====================
    "통신": {
        "leaders": [
            {"code": "017670", "name": "SK텔레콤", "weight": 1.0},
        ],
        "followers": [
            {"code": "030200", "name": "KT", "corr_target": "017670"},
            {"code": "032640", "name": "LG유플러스", "corr_target": "017670"},
            {"code": "036570", "name": "엔씨소프트", "corr_target": "017670"},
        ]
    },
}


def calculate_score_v10(
    df: pd.DataFrame,
    ticker: str = None,
    market_data: Optional[Dict[str, pd.DataFrame]] = None,
    today_changes: Optional[Dict[str, float]] = None,
) -> Optional[Dict]:
    """
    V10 점수 계산 - Leader-Follower (대장주-종속주)

    Args:
        df: 해당 종목의 OHLCV 데이터프레임 (최소 60일 권장)
        ticker: 종목코드
        market_data: 테마 내 다른 종목들의 OHLCV 딕셔너리 {ticker: df}
        today_changes: 금일 종목별 등락률 {ticker: change_pct}

    Returns:
        점수 및 분석 결과 딕셔너리
    """
    if df is None or len(df) < 60:
        return None

    try:
        df = df.copy()
        df = _calculate_indicators(df)

        result = {
            'score': 0,
            'leader_score': 0,      # 대장주 움직임 (35점)
            'correlation_score': 0,  # 상관관계 (25점)
            'catchup_score': 0,      # 캐치업 갭 (25점)
            'technical_score': 0,    # 기술적 지지 (15점)
            'signals': [],
            'patterns': [],
            'indicators': {},
            'exit_strategy': {},
            'warnings': [],
            'disqualified': False,
            'disqualify_reason': None,
            'hold_days': 3,
            'version': 'v10',
            # V10 전용 필드
            'theme': None,
            'leader_info': None,
            'correlation': 0,
            'catchup_gap': 0,
        }

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 기본 지표 저장
        result['indicators'] = {
            'close': curr['Close'],
            'open': curr['Open'],
            'high': curr['High'],
            'low': curr['Low'],
            'volume': curr['Volume'],
            'change_pct': (curr['Close'] - prev['Close']) / prev['Close'] * 100,
            'ma20': curr['ma20'],
            'ma60': curr['ma60'],
            'rsi': curr['rsi'],
        }

        # 종목이 어떤 테마에 속하는지, 대장주인지 종속주인지 확인
        theme_info = _find_stock_theme(ticker)

        if not theme_info:
            # 테마 매핑에 없는 종목은 낮은 점수
            result['signals'].append('NOT_IN_THEME_MAP')
            result['score'] = 0
            return result

        result['theme'] = theme_info['theme']

        # 대장주인 경우 - 종속주 대상이 아님
        if theme_info['is_leader']:
            result['signals'].append('IS_LEADER_STOCK')
            result['disqualified'] = True
            result['disqualify_reason'] = 'LEADER_NOT_TARGET'
            return result

        # 종속주인 경우 - V10 전략 적용
        leader_code = theme_info['corr_target']
        leader_name = _get_stock_name(leader_code, theme_info['theme'])

        # ========== 과락 조건 체크 ==========
        disqualify = _check_disqualification_v10(df, today_changes, ticker)
        if disqualify['disqualified']:
            result['disqualified'] = True
            result['disqualify_reason'] = disqualify['reasons']
            result['signals'].append('DISQUALIFIED')
            return result

        # ========== 1. 대장주 움직임 분석 (최대 35점) ==========
        leader_change = today_changes.get(leader_code, 0) if today_changes else 0
        leader_score_result = _check_leader_movement(
            leader_code, leader_name, leader_change,
            market_data.get(leader_code) if market_data else None
        )
        result['leader_score'] = leader_score_result['score']
        result['signals'].extend(leader_score_result['signals'])
        result['leader_info'] = {
            'code': leader_code,
            'name': leader_name,
            'change_pct': leader_change,
        }

        # 대장주가 움직이지 않으면 기회 없음
        if leader_change < 2.0:
            result['signals'].append('LEADER_NOT_MOVING')
            result['score'] = max(0, result['leader_score'])
            return result

        # ========== 2. 상관관계 분석 (최대 25점) ==========
        my_change = result['indicators']['change_pct']
        corr_result = _check_correlation(
            df, market_data.get(leader_code) if market_data else None,
            my_change, leader_change
        )
        result['correlation_score'] = corr_result['score']
        result['signals'].extend(corr_result['signals'])
        result['correlation'] = corr_result['correlation']

        # ========== 3. 캐치업 갭 분석 (최대 25점) ==========
        catchup_result = _check_catchup_gap(my_change, leader_change, corr_result['correlation'])
        result['catchup_score'] = catchup_result['score']
        result['signals'].extend(catchup_result['signals'])
        result['catchup_gap'] = catchup_result['gap']

        # ========== 4. 기술적 지지 분석 (최대 15점) ==========
        technical_result = _check_technical_support(df)
        result['technical_score'] = technical_result['score']
        result['signals'].extend(technical_result['signals'])

        # ========== 최종 점수 ==========
        total = (result['leader_score'] + result['correlation_score'] +
                 result['catchup_score'] + result['technical_score'])
        result['score'] = max(0, min(100, total))

        # ========== 청산 전략 ==========
        result['exit_strategy'] = _calculate_exit_strategy_v10(
            df, result['score'], leader_change, result['catchup_gap']
        )

        return result

    except Exception as e:
        print(f"V10 점수 계산 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_score_v10_with_market_data(
    df: pd.DataFrame,
    ticker: str,
    market_data: Dict[str, pd.DataFrame],
    today_changes: Dict[str, float]
) -> Optional[Dict]:
    """마켓 데이터 포함 버전"""
    return calculate_score_v10(df, ticker, market_data, today_changes)


def get_follower_opportunities(
    today_changes: Dict[str, float],
    market_data: Optional[Dict[str, pd.DataFrame]] = None,
    min_leader_change: float = 3.0,
    max_follower_change: float = 1.5,
) -> List[Dict]:
    """
    오늘 캐치업 기회가 있는 종속주 목록 반환

    Args:
        today_changes: {종목코드: 등락률}
        market_data: {종목코드: OHLCV 데이터프레임}
        min_leader_change: 대장주 최소 상승률 (기본 3%)
        max_follower_change: 종속주 최대 상승률 (기본 1.5%)

    Returns:
        캐치업 기회 목록 (점수순 정렬)
    """
    opportunities = []

    for theme_name, theme_data in THEME_STOCK_MAP.items():
        # 대장주 상승률 확인
        leader_changes = []
        for leader in theme_data['leaders']:
            change = today_changes.get(leader['code'], 0)
            if change >= min_leader_change:
                leader_changes.append({
                    'code': leader['code'],
                    'name': leader['name'],
                    'change': change,
                    'weight': leader['weight']
                })

        if not leader_changes:
            continue

        # 가장 많이 오른 대장주
        best_leader = max(leader_changes, key=lambda x: x['change'] * x['weight'])

        # 종속주 중 덜 오른 종목 찾기
        for follower in theme_data['followers']:
            follower_change = today_changes.get(follower['code'], 0)

            # 종속주가 이미 많이 올랐으면 스킵
            if follower_change >= max_follower_change:
                continue

            # 해당 종속주의 타겟 대장주와 비교
            target_leader = follower.get('corr_target')
            target_change = today_changes.get(target_leader, 0) if target_leader else best_leader['change']

            if target_change < min_leader_change:
                continue

            # 캐치업 갭 계산
            catchup_gap = target_change - follower_change

            if catchup_gap < 2.0:  # 갭이 2% 미만이면 스킵
                continue

            # 상관관계 계산 (데이터 있으면)
            correlation = 0.7  # 기본값
            if market_data:
                follower_df = market_data.get(follower['code'])
                leader_df = market_data.get(target_leader)
                if follower_df is not None and leader_df is not None:
                    correlation = _calculate_correlation(follower_df, leader_df)

            # 기회 점수 계산 (간이)
            score = min(100, int(
                (target_change / 5) * 35 +  # 대장주 움직임
                (correlation / 0.9) * 25 +  # 상관관계
                (catchup_gap / 5) * 25 +    # 캐치업 갭
                15                           # 기본 기술적 지지
            ))

            opportunities.append({
                'theme': theme_name,
                'follower_code': follower['code'],
                'follower_name': _get_follower_name(follower['code'], theme_name),
                'follower_change': follower_change,
                'leader_code': target_leader,
                'leader_name': _get_stock_name(target_leader, theme_name),
                'leader_change': target_change,
                'catchup_gap': round(catchup_gap, 2),
                'correlation': round(correlation, 3),
                'score': score,
            })

    # 점수순 정렬
    opportunities.sort(key=lambda x: x['score'], reverse=True)
    return opportunities


# ============================================================
# 내부 함수들
# ============================================================

def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()

    # 이동평균선
    for p in [5, 10, 20, 60]:
        df[f'ma{p}'] = df['Close'].rolling(p, min_periods=1).mean()

    # 볼린저 밴드
    df['bb_middle'] = df['Close'].rolling(20, min_periods=1).mean()
    df['bb_std'] = df['Close'].rolling(20, min_periods=1).std()
    df['bb_upper'] = df['bb_middle'] + df['bb_std'] * 2
    df['bb_lower'] = df['bb_middle'] - df['bb_std'] * 2
    df['bb_position'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 0.0001)

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rs = gain / (loss + 0.0001)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['rsi'] = df['rsi'].fillna(50)

    # 거래량 비율
    df['vol_ma20'] = df['Volume'].rolling(20, min_periods=1).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_ma20']

    return df


def _find_stock_theme(ticker: str) -> Optional[Dict]:
    """종목이 속한 테마와 역할(대장주/종속주) 찾기"""
    if not ticker:
        return None

    for theme_name, theme_data in THEME_STOCK_MAP.items():
        # 대장주인지 확인
        for leader in theme_data['leaders']:
            if leader['code'] == ticker:
                return {
                    'theme': theme_name,
                    'is_leader': True,
                    'weight': leader['weight'],
                    'corr_target': None
                }

        # 종속주인지 확인
        for follower in theme_data['followers']:
            if follower['code'] == ticker:
                return {
                    'theme': theme_name,
                    'is_leader': False,
                    'corr_target': follower.get('corr_target'),
                }

    return None


def _get_stock_name(ticker: str, theme: str) -> str:
    """종목코드로 종목명 찾기"""
    if not ticker or not theme:
        return "알수없음"

    theme_data = THEME_STOCK_MAP.get(theme, {})

    for leader in theme_data.get('leaders', []):
        if leader['code'] == ticker:
            return leader['name']

    for follower in theme_data.get('followers', []):
        if follower['code'] == ticker:
            return follower.get('name', ticker)

    return ticker


def _get_follower_name(ticker: str, theme: str) -> str:
    """종속주 코드로 이름 찾기"""
    theme_data = THEME_STOCK_MAP.get(theme, {})
    for follower in theme_data.get('followers', []):
        if follower['code'] == ticker:
            return follower.get('name', ticker)
    return ticker


def _check_disqualification_v10(
    df: pd.DataFrame,
    today_changes: Optional[Dict[str, float]],
    ticker: str
) -> Dict:
    """V10 과락 조건"""
    result = {'disqualified': False, 'reasons': []}

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 1. 이미 과열 상태 (RSI 70 이상)
    if curr['rsi'] > 70:
        result['disqualified'] = True
        result['reasons'].append('RSI_OVERBOUGHT')

    # 2. 이미 많이 오른 경우 (+5% 이상)
    my_change = (curr['Close'] - prev['Close']) / prev['Close'] * 100
    if my_change >= 5:
        result['disqualified'] = True
        result['reasons'].append('ALREADY_SURGED')

    # 3. 거래대금 부족 (5억 미만)
    trading_value = curr['Close'] * curr['Volume']
    if trading_value < 500_000_000:
        result['disqualified'] = True
        result['reasons'].append('LOW_LIQUIDITY')

    # 4. 급락 중 (-5% 이하)
    if my_change <= -5:
        result['disqualified'] = True
        result['reasons'].append('FALLING_SHARPLY')

    return result


def _check_leader_movement(
    leader_code: str,
    leader_name: str,
    leader_change: float,
    leader_df: Optional[pd.DataFrame] = None
) -> Dict:
    """대장주 움직임 분석 (최대 35점)"""
    result = {'score': 0, 'signals': []}

    if leader_change < 2:
        result['signals'].append(f'LEADER_WEAK({leader_name}:{leader_change:.1f}%)')
        return result

    # 상승률에 따른 점수
    if leader_change >= 7:
        result['score'] += 35
        result['signals'].append(f'LEADER_EXPLOSIVE({leader_name}:+{leader_change:.1f}%)')
    elif leader_change >= 5:
        result['score'] += 28
        result['signals'].append(f'LEADER_STRONG({leader_name}:+{leader_change:.1f}%)')
    elif leader_change >= 4:
        result['score'] += 22
        result['signals'].append(f'LEADER_SOLID({leader_name}:+{leader_change:.1f}%)')
    elif leader_change >= 3:
        result['score'] += 16
        result['signals'].append(f'LEADER_RISING({leader_name}:+{leader_change:.1f}%)')
    elif leader_change >= 2:
        result['score'] += 10
        result['signals'].append(f'LEADER_MOVING({leader_name}:+{leader_change:.1f}%)')

    # 거래량 동반 여부 (데이터 있으면)
    if leader_df is not None and len(leader_df) >= 20:
        curr = leader_df.iloc[-1]
        vol_ma = leader_df['Volume'].rolling(20).mean().iloc[-1]
        if curr['Volume'] > vol_ma * 2:
            result['score'] = min(35, result['score'] + 5)
            result['signals'].append('LEADER_HIGH_VOLUME')

    return result


def _calculate_correlation(df1: pd.DataFrame, df2: pd.DataFrame, days: int = 60) -> float:
    """두 종목 간 상관계수 계산"""
    try:
        if df1 is None or df2 is None:
            return 0.7  # 기본값

        if len(df1) < days or len(df2) < days:
            days = min(len(df1), len(df2), 30)

        # 최근 N일 수익률
        returns1 = df1['Close'].pct_change().tail(days).dropna()
        returns2 = df2['Close'].pct_change().tail(days).dropna()

        if len(returns1) < 20 or len(returns2) < 20:
            return 0.7

        # 날짜 맞추기
        common_dates = returns1.index.intersection(returns2.index)
        if len(common_dates) < 20:
            return 0.7

        r1 = returns1.loc[common_dates]
        r2 = returns2.loc[common_dates]

        # 피어슨 상관계수
        correlation = r1.corr(r2)

        if pd.isna(correlation):
            return 0.7

        return max(0, min(1, correlation))

    except Exception:
        return 0.7


def _check_correlation(
    follower_df: pd.DataFrame,
    leader_df: Optional[pd.DataFrame],
    follower_change: float,
    leader_change: float
) -> Dict:
    """상관관계 분석 (최대 25점)"""
    result = {'score': 0, 'signals': [], 'correlation': 0}

    correlation = _calculate_correlation(follower_df, leader_df)
    result['correlation'] = correlation

    # 상관계수에 따른 점수
    if correlation >= 0.85:
        result['score'] += 25
        result['signals'].append(f'VERY_HIGH_CORR({correlation:.2f})')
    elif correlation >= 0.75:
        result['score'] += 20
        result['signals'].append(f'HIGH_CORR({correlation:.2f})')
    elif correlation >= 0.65:
        result['score'] += 15
        result['signals'].append(f'MODERATE_CORR({correlation:.2f})')
    elif correlation >= 0.55:
        result['score'] += 10
        result['signals'].append(f'LOW_CORR({correlation:.2f})')
    else:
        result['signals'].append(f'WEAK_CORR({correlation:.2f})')

    return result


def _check_catchup_gap(
    follower_change: float,
    leader_change: float,
    correlation: float
) -> Dict:
    """캐치업 갭 분석 (최대 25점)"""
    result = {'score': 0, 'signals': [], 'gap': 0}

    # 상관관계 기반 예상 움직임 vs 실제 움직임
    expected_move = leader_change * correlation
    actual_move = follower_change
    gap = expected_move - actual_move

    result['gap'] = round(gap, 2)

    # 갭이 클수록 높은 점수 (캐치업 여지가 큼)
    if gap >= 4:
        result['score'] += 25
        result['signals'].append(f'HUGE_GAP({gap:.1f}%)')
    elif gap >= 3:
        result['score'] += 20
        result['signals'].append(f'LARGE_GAP({gap:.1f}%)')
    elif gap >= 2:
        result['score'] += 15
        result['signals'].append(f'MODERATE_GAP({gap:.1f}%)')
    elif gap >= 1:
        result['score'] += 10
        result['signals'].append(f'SMALL_GAP({gap:.1f}%)')
    elif gap > 0:
        result['score'] += 5
        result['signals'].append(f'MINOR_GAP({gap:.1f}%)')
    else:
        result['signals'].append(f'NO_GAP({gap:.1f}%)')

    return result


def _check_technical_support(df: pd.DataFrame) -> Dict:
    """기술적 지지 분석 (최대 15점)"""
    result = {'score': 0, 'signals': []}

    curr = df.iloc[-1]

    # 1. MA20 위에 있으면 +5점
    if pd.notna(curr['ma20']) and curr['Close'] > curr['ma20']:
        result['score'] += 5
        result['signals'].append('ABOVE_MA20')

    # 2. 볼린저 밴드 하단 근처 (저평가 영역) +5점
    if curr['bb_position'] < 0.3:
        result['score'] += 5
        result['signals'].append('NEAR_BB_LOWER')
    elif curr['bb_position'] < 0.5:
        result['score'] += 3
        result['signals'].append('BB_MID_LOWER')

    # 3. RSI 50 미만 (과열 아님) +5점
    if 30 < curr['rsi'] < 50:
        result['score'] += 5
        result['signals'].append('RSI_HEALTHY')
    elif 50 <= curr['rsi'] < 60:
        result['score'] += 3
        result['signals'].append('RSI_NEUTRAL')

    result['score'] = min(15, result['score'])
    return result


def _calculate_exit_strategy_v10(
    df: pd.DataFrame,
    score: int,
    leader_change: float,
    catchup_gap: float
) -> Dict:
    """V10 청산 전략"""
    curr = df.iloc[-1]
    close = curr['Close']

    # 목표 캐치업: 갭의 70~80%
    if score >= 70:
        target_catchup = catchup_gap * 0.8
        stop_pct = -2.5
        hold_days = 3
    elif score >= 55:
        target_catchup = catchup_gap * 0.7
        stop_pct = -3.0
        hold_days = 3
    else:
        target_catchup = catchup_gap * 0.6
        stop_pct = -3.0
        hold_days = 2

    target_price = close * (1 + target_catchup / 100)
    stop_price = close * (1 + stop_pct / 100)

    return {
        'entry_price': close,
        'target_price': round(target_price, 0),
        'stop_price': round(stop_price, 0),
        'target_pct': round(target_catchup, 2),
        'stop_pct': stop_pct,
        'max_hold_days': hold_days,
        'leader_change': leader_change,
        'catchup_gap': catchup_gap,
        'risk_reward': round(abs(target_catchup / stop_pct), 2),
    }


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("V10 Leader-Follower (대장주-종속주) 전략")
    print("=" * 60)

    # 테스트용 시나리오:
    # SK하이닉스(대장주)가 +5% 상승
    # 한미반도체(종속주)가 +1% 상승 → 캐치업 기회

    today_changes = {
        "005930": 2.5,   # 삼성전자
        "000660": 5.0,   # SK하이닉스 (대장주 급등)
        "042700": 1.0,   # 한미반도체 (종속주 - 기회)
        "403870": 0.5,   # HPSP (종속주 - 기회)
        "089030": 4.5,   # 테크윙 (이미 따라감)
        "352820": 6.0,   # 하이브 (엔터 대장주)
        "041510": 1.5,   # 에스엠 (엔터 종속주)
    }

    print("\n[금일 등락률]")
    for code, change in today_changes.items():
        theme_info = _find_stock_theme(code)
        role = "대장주" if theme_info and theme_info['is_leader'] else "종속주"
        theme = theme_info['theme'] if theme_info else "없음"
        name = _get_stock_name(code, theme) if theme_info else code
        print(f"  {name}({code}): {change:+.1f}% [{theme}:{role}]")

    print("\n[캐치업 기회 분석]")
    opportunities = get_follower_opportunities(
        today_changes,
        market_data=None,  # 실제로는 OHLCV 데이터 전달
        min_leader_change=3.0,
        max_follower_change=2.0
    )

    if not opportunities:
        print("  캐치업 기회 없음")
    else:
        for i, opp in enumerate(opportunities, 1):
            print(f"\n  {i}. {opp['follower_name']} ({opp['follower_code']}) - {opp['theme']}")
            print(f"     대장주: {opp['leader_name']} +{opp['leader_change']:.1f}%")
            print(f"     종속주: +{opp['follower_change']:.1f}%")
            print(f"     캐치업 갭: {opp['catchup_gap']:.1f}%")
            print(f"     상관계수: {opp['correlation']:.2f}")
            print(f"     점수: {opp['score']}점")
