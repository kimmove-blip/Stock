"""
스크리닝 시스템 설정 파일
"""

import os
from datetime import datetime
from pathlib import Path

# 기본 경로 설정
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

# 출력 디렉토리 생성
OUTPUT_DIR.mkdir(exist_ok=True)


class ScreeningConfig:
    """스크리닝 설정"""
    MODE = "quick"  # "quick" 또는 "full"
    TOP_N = 100  # 상위 N개 종목 선정
    MAX_WORKERS = 10  # 병렬 처리 워커 수
    MIN_MARKET_CAP = 30_000_000_000  # 최소 시가총액 (300억)
    MAX_MARKET_CAP = 1_000_000_000_000  # 최대 시가총액 (1조) - 대형 우량주 제외
    MIN_TRADING_AMOUNT = 300_000_000  # 최소 거래대금 (3억)
    MAX_PRICE = 100_000  # 최대 주가 (10만원)


class OutputConfig:
    """출력 파일 설정"""
    DATE_FORMAT = "%Y%m%d"

    @classmethod
    def get_filepath(cls, file_type):
        """파일 타입별 경로 반환"""
        date_str = datetime.now().strftime(cls.DATE_FORMAT)

        extensions = {
            "excel": f"top100_{date_str}.xlsx",
            "json": f"top100_{date_str}.json",
            "csv": f"top100_{date_str}.csv",
            "pdf": f"top100_{date_str}.pdf",
        }

        filename = extensions.get(file_type, f"top100_{date_str}.txt")
        return OUTPUT_DIR / filename


class SignalCategories:
    """신호 분류"""
    # 강력 매수 신호
    STRONG_BUY = [
        "GOLDEN_CROSS_20_60",
        "MACD_GOLDEN_CROSS",
        "SUPERTREND_BUY",
        "STOCH_GOLDEN_OVERSOLD",
        "MORNING_STAR",
        "PSAR_BUY_SIGNAL",
    ]

    # 매수 관심 신호
    BUY = [
        "GOLDEN_CROSS_5_20",
        "MA_ALIGNED",
        "RSI_OVERSOLD",
        "BB_LOWER_BOUNCE",
        "VOLUME_SURGE",
        "MFI_OVERSOLD",
        "OBV_ABOVE_MA",
        "ICHIMOKU_GOLDEN_CROSS",
        "CMF_STRONG_INFLOW",
        "BULLISH_ENGULFING",
    ]

    # 주의 신호
    CAUTION = [
        "RSI_OVERBOUGHT",
        "BB_UPPER_BREAK",
        "MFI_OVERBOUGHT",
        "DEAD_CROSS_5_20",
        "CMF_STRONG_OUTFLOW",
        "BEARISH_ENGULFING",
        "EVENING_STAR",
    ]


class ScheduleConfig:
    """스케줄러 설정"""
    RUN_HOUR = 18  # 실행 시각 (시)
    RUN_MINUTE = 0  # 실행 시각 (분)
    RUN_ON_WEEKEND = False  # 주말 실행 여부


class TelegramConfig:
    """텔레그램 봇 설정"""
    BOT_TOKEN = "8524957427:AAFnkZJACCJWm_pm0TXp-aXbsoZtnhJWjhM"
    CHAT_ID = "5411684999"
    ENABLED = True  # 텔레그램 알림 활성화 여부


class IndicatorWeights:
    """지표별 가중치"""
    # 강력 신호 (높은 가중치)
    GOLDEN_CROSS_20_60 = 25
    MACD_GOLDEN_CROSS = 20
    SUPERTREND_BUY = 20
    STOCH_GOLDEN_OVERSOLD = 20
    MORNING_STAR = 20
    PSAR_BUY_SIGNAL = 15

    # 매수 신호 (중간 가중치)
    GOLDEN_CROSS_5_20 = 15
    MA_ALIGNED = 15
    RSI_OVERSOLD = 15
    BB_LOWER_BOUNCE = 15
    VOLUME_SURGE = 15
    MFI_OVERSOLD = 15
    ICHIMOKU_GOLDEN_CROSS = 15
    CMF_STRONG_INFLOW = 10
    BULLISH_ENGULFING = 15
    OBV_ABOVE_MA = 10

    # 보조 신호 (낮은 가중치)
    RSI_RECOVERING = 5
    MACD_HIST_POSITIVE = 10
    MACD_HIST_RISING = 5
    BB_LOWER_TOUCH = 10
    STOCH_GOLDEN_CROSS = 10
    STOCH_OVERSOLD = 5
    ADX_STRONG_UPTREND = 15
    ADX_UPTREND = 10
    CCI_OVERSOLD = 10
    WILLR_OVERSOLD = 10
    OBV_RISING = 5
    MFI_LOW = 5
    VOLUME_HIGH = 10
    VOLUME_ABOVE_AVG = 5
    SUPERTREND_UPTREND = 5
    PSAR_UPTREND = 5
    ROC_POSITIVE_CROSS = 10
    ROC_STRONG_MOMENTUM = 5
    ICHIMOKU_ABOVE_CLOUD = 10
    CMF_POSITIVE = 5

    # 캔들 패턴
    HAMMER = 10
    INVERTED_HAMMER = 8
    DOJI = 3

    # 주의 신호 (음수 가중치)
    RSI_OVERBOUGHT = -10
    BB_UPPER_BREAK = -5
    MFI_OVERBOUGHT = -10
    DEAD_CROSS_5_20 = -15
    CMF_STRONG_OUTFLOW = -10
    BEARISH_ENGULFING = -10
    EVENING_STAR = -15
    CCI_OVERBOUGHT = -5
    WILLR_OVERBOUGHT = -5


# 신호 이름 한글 변환
SIGNAL_NAMES_KR = {
    # 이동평균선
    "MA_ALIGNED": "이평선 정배열",
    "GOLDEN_CROSS_5_20": "골든크로스(5/20)",
    "GOLDEN_CROSS_20_60": "골든크로스(20/60)",
    "DEAD_CROSS_5_20": "데드크로스(5/20)",

    # RSI
    "RSI_OVERSOLD": "RSI 과매도",
    "RSI_RECOVERING": "RSI 회복중",
    "RSI_OVERBOUGHT": "RSI 과매수",

    # MACD
    "MACD_GOLDEN_CROSS": "MACD 골든크로스",
    "MACD_HIST_POSITIVE": "MACD 히스토그램 양전환",
    "MACD_HIST_RISING": "MACD 히스토그램 상승",

    # 볼린저밴드
    "BB_LOWER_BOUNCE": "볼린저 하단 반등",
    "BB_LOWER_TOUCH": "볼린저 하단 터치",
    "BB_UPPER_BREAK": "볼린저 상단 돌파",

    # 스토캐스틱
    "STOCH_GOLDEN_OVERSOLD": "스토캐스틱 과매도 골든",
    "STOCH_GOLDEN_CROSS": "스토캐스틱 골든크로스",
    "STOCH_OVERSOLD": "스토캐스틱 과매도",

    # ADX
    "ADX_STRONG_UPTREND": "강한 상승추세",
    "ADX_UPTREND": "상승추세",

    # CCI
    "CCI_OVERSOLD": "CCI 과매도",
    "CCI_OVERBOUGHT": "CCI 과매수",

    # Williams %R
    "WILLR_OVERSOLD": "Williams 과매도",
    "WILLR_OVERBOUGHT": "Williams 과매수",

    # OBV
    "OBV_ABOVE_MA": "OBV 이평선 상회",
    "OBV_RISING": "OBV 상승",

    # MFI
    "MFI_OVERSOLD": "MFI 과매도",
    "MFI_LOW": "MFI 낮음",
    "MFI_OVERBOUGHT": "MFI 과매수",

    # 거래량
    "VOLUME_SURGE": "거래량 급증",
    "VOLUME_HIGH": "거래량 증가",
    "VOLUME_ABOVE_AVG": "거래량 평균 상회",

    # Supertrend
    "SUPERTREND_BUY": "슈퍼트렌드 매수전환",
    "SUPERTREND_UPTREND": "슈퍼트렌드 상승",

    # PSAR
    "PSAR_BUY_SIGNAL": "PSAR 매수신호",
    "PSAR_UPTREND": "PSAR 상승추세",

    # ROC
    "ROC_POSITIVE_CROSS": "ROC 양전환",
    "ROC_STRONG_MOMENTUM": "ROC 강한 모멘텀",

    # 일목균형표
    "ICHIMOKU_GOLDEN_CROSS": "일목 골든크로스",
    "ICHIMOKU_ABOVE_CLOUD": "일목 구름대 상회",

    # CMF
    "CMF_STRONG_INFLOW": "강한 자금 유입",
    "CMF_POSITIVE": "자금 유입",
    "CMF_STRONG_OUTFLOW": "강한 자금 유출",

    # 캔들 패턴
    "HAMMER": "망치형",
    "INVERTED_HAMMER": "역망치형",
    "BULLISH_ENGULFING": "상승장악형",
    "BEARISH_ENGULFING": "하락장악형",
    "DOJI": "도지",
    "MORNING_STAR": "샛별형",
    "EVENING_STAR": "저녁별형",
}

# 신호 설명
SIGNAL_DESCRIPTIONS = {
    # 이동평균선
    "MA_ALIGNED": "단기/중기/장기 이평선이 정배열을 형성하여 상승 추세가 확립됨",
    "GOLDEN_CROSS_5_20": "5일선이 20일선을 상향 돌파하여 단기 매수 신호 발생",
    "GOLDEN_CROSS_20_60": "20일선이 60일선을 상향 돌파하여 중장기 상승 추세 전환",
    "DEAD_CROSS_5_20": "5일선이 20일선을 하향 돌파하여 단기 하락 신호 발생",

    # RSI
    "RSI_OVERSOLD": "RSI 30 이하로 과매도 구간 진입, 반등 가능성 높음",
    "RSI_RECOVERING": "RSI가 과매도 구간에서 회복 중",
    "RSI_OVERBOUGHT": "RSI 70 이상으로 과매수 구간, 조정 가능성 있음",

    # MACD
    "MACD_GOLDEN_CROSS": "MACD가 시그널선을 상향 돌파하여 매수 타이밍 포착",
    "MACD_HIST_POSITIVE": "MACD 히스토그램이 음에서 양으로 전환",
    "MACD_HIST_RISING": "MACD 히스토그램이 상승 중으로 모멘텀 개선",

    # 볼린저밴드
    "BB_LOWER_BOUNCE": "볼린저밴드 하단에서 반등하여 저점 매수 기회",
    "BB_LOWER_TOUCH": "볼린저밴드 하단 터치로 과매도 상태",
    "BB_UPPER_BREAK": "볼린저밴드 상단 돌파로 단기 과열 상태",

    # 스토캐스틱
    "STOCH_GOLDEN_OVERSOLD": "과매도 구간에서 스토캐스틱 골든크로스 발생, 강력 매수 신호",
    "STOCH_GOLDEN_CROSS": "스토캐스틱 K선이 D선을 상향 돌파",
    "STOCH_OVERSOLD": "스토캐스틱 20 이하 과매도 구간",

    # ADX
    "ADX_STRONG_UPTREND": "ADX 25 이상으로 강한 상승 추세 확인",
    "ADX_UPTREND": "ADX 상승으로 추세 강화 중",

    # 거래량
    "VOLUME_SURGE": "거래량이 평균 대비 2배 이상 급증",
    "VOLUME_HIGH": "거래량이 평균 대비 1.5배 이상 증가",
    "VOLUME_ABOVE_AVG": "거래량이 평균을 상회",

    # Supertrend
    "SUPERTREND_BUY": "슈퍼트렌드 지표가 매수 전환, 추세 상승 시작",
    "SUPERTREND_UPTREND": "슈퍼트렌드 상승 추세 유지 중",

    # PSAR
    "PSAR_BUY_SIGNAL": "파라볼릭 SAR 매수 전환으로 추세 반전 신호",
    "PSAR_UPTREND": "파라볼릭 SAR 상승 추세 유지",

    # 일목균형표
    "ICHIMOKU_GOLDEN_CROSS": "일목균형표 전환선/기준선 골든크로스",
    "ICHIMOKU_ABOVE_CLOUD": "가격이 일목균형표 구름대 상단 위치",

    # CMF
    "CMF_STRONG_INFLOW": "CMF 0.2 이상으로 강한 자금 유입 확인",
    "CMF_POSITIVE": "CMF 양수로 자금 유입 중",
    "CMF_STRONG_OUTFLOW": "CMF -0.2 이하로 강한 자금 유출 주의",

    # 캔들 패턴
    "HAMMER": "망치형 패턴으로 하락 추세 반전 가능성",
    "INVERTED_HAMMER": "역망치형 패턴으로 상승 전환 가능성",
    "BULLISH_ENGULFING": "상승장악형 패턴으로 강한 매수세 유입",
    "BEARISH_ENGULFING": "하락장악형 패턴으로 강한 매도세 유입",
    "DOJI": "도지 패턴으로 추세 전환 가능성",
    "MORNING_STAR": "샛별형 패턴으로 강력한 상승 반전 신호",
    "EVENING_STAR": "저녁별형 패턴으로 강력한 하락 반전 신호",

    # MFI
    "MFI_OVERSOLD": "MFI 20 이하 과매도로 반등 기대",
    "MFI_LOW": "MFI 낮아 매수 기회 포착 가능",
    "MFI_OVERBOUGHT": "MFI 80 이상 과매수로 조정 가능성",

    # OBV
    "OBV_ABOVE_MA": "OBV가 이동평균 위에서 거래량 흐름 양호",
    "OBV_RISING": "OBV 상승으로 매수세 강화",

    # CCI/Williams
    "CCI_OVERSOLD": "CCI -100 이하 과매도 구간",
    "CCI_OVERBOUGHT": "CCI 100 이상 과매수 구간",
    "WILLR_OVERSOLD": "Williams %R -80 이하 과매도",
    "WILLR_OVERBOUGHT": "Williams %R -20 이상 과매수",

    # ROC
    "ROC_POSITIVE_CROSS": "ROC가 0선 상향 돌파로 상승 모멘텀 전환",
    "ROC_STRONG_MOMENTUM": "ROC 5% 이상으로 강한 상승 모멘텀",
}


def get_signal_kr(signal_code):
    """신호 코드를 한글로 변환"""
    return SIGNAL_NAMES_KR.get(signal_code, signal_code)


def get_signal_description(signal_code):
    """신호 설명 반환"""
    return SIGNAL_DESCRIPTIONS.get(signal_code, "")


def calculate_signal_weight(signals):
    """신호 목록의 총 가중치 계산"""
    total_weight = 0
    weights_dict = vars(IndicatorWeights)

    for signal in signals:
        weight = weights_dict.get(signal, 0)
        if isinstance(weight, int):
            total_weight += weight

    return total_weight
