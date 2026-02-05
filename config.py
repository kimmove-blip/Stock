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
    MODE = "full"  # 무조건 full 모드 사용
    TOP_N = 100  # 상위 N개 종목 선정
    MAX_WORKERS = 5  # 병렬 처리 워커 수 (크론 환경 안정성)
    MIN_MARKET_CAP = 30_000_000_000  # 최소 시가총액 (300억)
    MAX_MARKET_CAP = 1_000_000_000_000  # 최대 시가총액 (1조) - 대형 우량주 제외
    MIN_TRADING_AMOUNT = 300_000_000  # 최소 거래대금 (3억)
    MAX_PRICE = 100_000  # 최대 주가 (10만원)


class OutputConfig:
    """출력 파일 설정"""
    DATE_FORMAT = "%Y%m%d"
    _version = None  # 스크리닝 엔진 버전 (클래스 변수)

    @classmethod
    def set_version(cls, version):
        """스크리닝 엔진 버전 설정"""
        cls._version = version

    @classmethod
    def get_filepath(cls, file_type):
        """파일 타입별 경로 반환"""
        date_str = datetime.now().strftime(cls.DATE_FORMAT)

        # 버전이 설정되어 있고 v2가 아니면 파일명에 버전 포함
        version_suffix = f"_{cls._version}" if cls._version and cls._version != "v2" else ""

        extensions = {
            "excel": f"top100{version_suffix}_{date_str}.xlsx",
            "json": f"top100{version_suffix}_{date_str}.json",
            "csv": f"top100{version_suffix}_{date_str}.csv",
            "pdf": f"top100{version_suffix}_{date_str}.pdf",
        }

        filename = extensions.get(file_type, f"top100{version_suffix}_{date_str}.txt")
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


class StrategyConfig:
    """
    매매 전략 임계값 설정

    이 값들은 백테스트 결과를 기반으로 최적화됨 (2026-02-04 기준)
    시간대별 전략 분리: Early Surge, 오전, 골든타임, 오후
    """

    # === 시간대 정의 ===
    EARLY_SURGE_START = (9, 10)   # 09:10 (hour, minute)
    EARLY_SURGE_END = (9, 25)     # 09:25
    MORNING_END_HOUR = 11         # 오전 전략: ~10:55
    GOLDEN_HOUR_START = 11        # 골든타임 시작: 11:00
    GOLDEN_HOUR_END = 13          # 골든타임 종료: 12:55
    AFTERNOON_END = (14, 50)      # 오후 전략 종료: 14:50
    CLOSING_START = (14, 55)      # 정리매도 시작: 14:55

    # === 매수 조건 (should_buy_advanced) - 시간대별 ===
    # Early Surge (09:10~09:25) - v2.2 완화
    EARLY_V2_MIN = 70            # V2 최소 점수 (85→80→70)
    EARLY_V4_MIN = 45            # V4 최소 점수 (60→55→45)

    # 오전 (09:30~10:55) - v2.2 완화
    MORNING_V2_MIN = 70          # V2 최소 점수 (80→75→70)
    MORNING_V4_MIN = 45          # V4 최소 점수 (55→50→45)

    # 골든타임 (11:00~12:55) - 완화 유지
    GOLDEN_V2_MIN = 70           # V2 최소 점수
    GOLDEN_V4_MIN = 45           # V4 최소 점수

    # 오후 (13:00~14:50) - v2.2 완화
    AFTERNOON_V2_MIN = 70        # V2 최소 점수 (85→80→70)
    AFTERNOON_V4_MIN = 45        # V4 최소 점수 (60→55→45)

    # 기본값 (하위 호환)
    BUY_V2_MIN = 75              # V2 기본 최소 점수
    BUY_V4_MIN = 50              # V4 기본 최소 점수
    BUY_V5_MIN = 45              # V5 최소 점수 (2026-02-05 추가)
    BUY_V4_DELTA_MAX = 0         # V4 델타 최대값 (급등중 제외)
    MAX_BUY_PER_RUN = 5          # 1회 실행당 최대 매수 종목 수 (v2.1)

    # === 등락률 필터 (v2.1) ===
    MIN_CHANGE_PCT = -5.0        # 최소 등락률 (%)
    MAX_CHANGE_PCT = 10.0        # 최대 등락률 (%) - 급등주 필터

    # === 연구 기반 전략 (2026-02-05 추가) ===
    # 1. 거래량 돌파 전략 (71% 승률)
    VOLUME_BREAKOUT_MIN = 1.5    # 거래량 배율 최소 (20일 평균 대비)
    VOLUME_BREAKOUT_STRONG = 2.0 # 강한 거래량 돌파
    VOLUME_EXPLOSION = 3.0       # 거래량 폭발 (78%+ 승률)

    # 2. 갭다운 역전 전략 (72% 승률)
    GAP_DOWN_MIN = -3.0          # 갭다운 최소 (%)
    GAP_DOWN_MAX = -0.5          # 갭다운 최대 (%)
    GAP_DOWN_V4_MIN = 50         # 갭다운 시 V4 최소 (수급 양호)

    # 3. ORB 전략 (Opening Range Breakout)
    ORB_START_MINUTE = 0         # ORB 시작 (09:00)
    ORB_END_MINUTE = 30          # ORB 종료 (09:30)
    ORB_CHANGE_MIN = 1.0         # ORB 돌파 최소 등락률 (%)

    # 연구 기반 전략 활성화
    USE_RESEARCH_STRATEGY = True  # True: 연구 기반, False: 기존 스코어 기반

    # === 홀딩 조건 (check_hold_condition) ===
    HOLD_V5_STRONG = 70          # V5 이상이면 강력 홀딩 (익일까지)
    HOLD_V5_MIN = 60             # V5 이상이면 일반 홀딩
    HOLD_V4_MIN = 55             # V4 이상이면 홀딩
    HOLD_V2_MIN = 60             # V2 이상이면 홀딩

    # === 매도 조건 ===
    SELL_V4_MAX = 40             # V4 미만이면 매도
    SELL_V2_MAX = 50             # V2 미만 AND V4 < 45 이면 매도
    SELL_V4_COMBINED = 45        # V2/V4 복합 조건용

    # === 손절 (시간대별 차등 적용) ===
    STOP_LOSS_RATE = 7.0         # 기본 손절 기준 (%)
    STOP_LOSS_MORNING = 5.0      # 오전 손절 (빠른 손절)
    STOP_LOSS_GOLDEN = 7.0       # 골든타임 손절 (현행 유지)
    STOP_LOSS_AFTERNOON = 4.0    # 오후 손절 (더 빠른 손절)

    # === 연구 기반 청산 전략 (2026-02-05 추가) ===
    # 시간 기반 청산 (567,000건 백테스트: 5일 보유가 최적)
    MAX_HOLDING_DAYS = 5         # 최대 보유 기간 (일)
    TIME_EXIT_ENABLED = True     # 시간 기반 청산 활성화

    # 익절 전략 (3:1 보상비율 기반)
    PROFIT_TARGET = 15.0         # 전량 익절 목표 (%)
    PARTIAL_PROFIT = 8.0         # 부분 익절 기준 (%)
    PARTIAL_SELL_RATIO = 0.5     # 부분 익절 시 매도 비율 (50%)
    PROFIT_EXIT_ENABLED = True   # 익절 전략 활성화

    # V5 기반 시간 청산 예외
    TIME_EXIT_V5_EXCEPTION = 65  # V5 이상이면 시간 청산 예외

    # === 시총별 상승률 제한 ===
    CHANGE_LIMIT_LARGE = 5.0     # 대형주 (1조+): 5%
    CHANGE_LIMIT_MID = 10.0      # 중형주 (3000억~1조): 10%
    CHANGE_LIMIT_SMALL = 15.0    # 소형주 (3000억 미만): 15%


class TelegramConfig:
    """텔레그램 봇 설정"""
    BOT_TOKEN = "8524957427:AAFnkZJACCJWm_pm0TXp-aXbsoZtnhJWjhM"
    CHAT_ID = "5411684999"
    ENABLED = True  # 텔레그램 알림 활성화 여부


class AutoTraderConfig:
    """자동매매 설정"""
    # 투자 모드 (True: 모의투자, False: 실전투자)
    IS_VIRTUAL = True

    # 모의투자 초기 자금 (1억원)
    VIRTUAL_INITIAL_CASH = 100_000_000

    # 매매 모드 ("auto": 자동매매, "semi-auto": 반자동 매수제안)
    TRADE_MODE = "auto"

    # 매수 제안 설정 (semi-auto 모드용)
    SUGGESTION_EXPIRE_HOURS = 24    # 매수 제안 만료 시간 (시간)
    MAX_PENDING_SUGGESTIONS = 10    # 최대 대기 제안 수
    TARGET_PROFIT_PCT = 0.20        # 목표 수익률 (+20%)
    SUGGESTED_STOP_LOSS_PCT = -0.1# 제안 손절률 (-10%)
    BUY_BAND_PCT = 0.03             # 매수 밴드 (±3%)

    # 매매 규칙
    MIN_BUY_SCORE = 65  # 최소 매수 점수 (V5 전략: 65점)
    MIN_VOLUME_RATIO = 1.0          # 최소 거래량 비율 (20일 평균 대비)

    # 포지션 관리
    MAX_PER_STOCK = 200000  # 종목당 최대 투자금액 (원)
    MAX_HOLDINGS = 20       # 최대 보유 종목 수
    MAX_DAILY_TRADES = 30   # 일일 최대 거래 횟수

    # 손절/매도
    STOP_LOSS_PCT = -0.1# 손절 비율 (-7%)
    TAKE_PROFIT_PCT = None          # 익절 비활성화 (신호 기반 매도)
    MIN_HOLD_SCORE = 50  # V5 전략: 50점 미만 시 매도
    MAX_HOLD_DAYS = 10# 최대 보유 기간 (일)

    # 수수료/세금 (비율)
    COMMISSION_RATE = 0.00015       # 매매 수수료 0.015% (매수/매도 각각)
    TAX_RATE_KOSPI = 0.0033         # KOSPI 세금 0.33% (증권거래세 0.18% + 농특세 0.15%)
    TAX_RATE_KOSDAQ = 0.0018        # KOSDAQ 세금 0.18% (증권거래세만)

    # 시초가 갭 전략 설정
    GAP_STRATEGY_ENABLED = True     # 갭 전략 활성화 여부
    LIMIT_UP_THRESHOLD = 25.0       # 상한가 판정 기준 (등락률 25% 이상)

    # 상한가 종목 갭 조건
    LIMIT_UP_GAP_MIN = 5.0          # 상한가 종목: 최소 갭 5%
    LIMIT_UP_GAP_MAX = 15.0         # 상한가 종목: 최대 갭 15%

    # 일반 종목 갭 조건
    NORMAL_GAP_MIN = 3.0            # 일반 종목: 최소 갭 3% (황금구간 시작)
    NORMAL_GAP_IDEAL_MAX = 8.0      # 일반 종목: 이상적 갭 상한 8%
    NORMAL_GAP_MAX = 10.0           # 일반 종목: 최대 갭 10% (초과시 스킵)

    # 신뢰도 높은 매수 신호 (이 신호들 중 하나 이상 포함 시 매수)
    STRONG_BUY_SIGNALS = [
        "GOLDEN_CROSS_20_60",
        "MACD_GOLDEN_CROSS",
        "SUPERTREND_BUY",
        "STOCH_GOLDEN_OVERSOLD",
        "MORNING_STAR",
        "MA_ALIGNED",
    ]

    # 매도 신호 (이 신호들 중 2개 이상 발생 시 매도)
    SELL_SIGNALS = [
        "RSI_OVERBOUGHT",
        "MACD_DEAD_CROSS",
        "DEAD_CROSS_5_20",
        "DEAD_CROSS_20_60",
        "BB_UPPER_BREAK",
        "BEARISH_ENGULFING",
        "EVENING_STAR",
        "SUPERTREND_SELL",
        "PSAR_SELL_SIGNAL",
    ]

    # 알림 설정
    TELEGRAM_NOTIFY = True          # 텔레그램 알림 활성화

    # 긴급 정지 조건
    MAX_DAILY_LOSS_PCT = -0.05      # 일일 최대 손실률 (-5%)
    EMERGENCY_STOP = False          # 긴급 정지 플래그


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


class SignalReliability:
    """
    신호별 신뢰도 설정 (방안 D)
    - 백테스트 결과 기반으로 조정
    - 100%가 기본, 낮을수록 가중치 감소
    """
    # 고신뢰 신호 (70%+ 적중률)
    GOLDEN_CROSS_20_60 = 100      # 중장기 신호, 높은 신뢰도
    MA_ALIGNED = 110              # 정배열, 신뢰도 높음 (보너스)
    MACD_GOLDEN_CROSS = 100       # 중기 신호
    ADX_STRONG_UPTREND = 105      # 추세 확인, 신뢰도 높음

    # 중간 신뢰 신호 (50~70% 적중률)
    RSI_OVERSOLD = 90             # 반등 기대
    BB_LOWER_BOUNCE = 90          # 저점 반등
    SUPERTREND_BUY = 95           # 추세 전환
    ICHIMOKU_GOLDEN_CROSS = 90    # 일목 신호
    ICHIMOKU_ABOVE_CLOUD = 95     # 일목 구름대
    MFI_OVERSOLD = 85             # 자금흐름
    STOCH_GOLDEN_OVERSOLD = 90    # 스토캐스틱
    CMF_STRONG_INFLOW = 85        # 자금유입

    # 저신뢰 신호 (40~50% 적중률, 단기/노이즈)
    GOLDEN_CROSS_5_20 = 60        # 단기 신호, 변동성 높음
    VOLUME_SURGE = 50             # 일시적 급등 가능성
    VOLUME_HIGH = 55              # 거래량 증가
    VOLUME_ABOVE_AVG = 60         # 거래량
    PSAR_BUY_SIGNAL = 70          # PSAR 전환
    ROC_POSITIVE_CROSS = 65       # ROC 전환

    # 보조 신호 (보너스 역할, 단독 신뢰 낮음)
    RSI_RECOVERING = 70
    MACD_HIST_POSITIVE = 75
    MACD_HIST_RISING = 60
    BB_LOWER_TOUCH = 70
    STOCH_GOLDEN_CROSS = 75
    STOCH_OVERSOLD = 65
    ADX_UPTREND = 80
    CCI_OVERSOLD = 70
    WILLR_OVERSOLD = 70
    OBV_ABOVE_MA = 75
    OBV_RISING = 65
    MFI_LOW = 60
    SUPERTREND_UPTREND = 70
    PSAR_UPTREND = 65
    ROC_STRONG_MOMENTUM = 70
    CMF_POSITIVE = 70

    # 캔들 패턴 (단독 신뢰 낮음, 보조 역할)
    HAMMER = 65
    INVERTED_HAMMER = 60
    BULLISH_ENGULFING = 75
    MORNING_STAR = 80
    DOJI = 50


class StreakConfig:
    """
    신호 지속성 설정 (방안 A)
    - 연속 출현 일수에 따른 가중치 배율
    """
    # 연속 출현 일수별 배율
    STREAK_WEIGHTS = {
        1: 0.5,   # 신규 신호 (약하게)
        2: 0.8,   # 2일 연속
        3: 1.0,   # 3일 연속 (확인됨)
        4: 1.1,   # 4일 연속
        5: 1.2,   # 5일+ (강력한 신호)
    }

    # 최대 배율 (5일 이상)
    MAX_STREAK_WEIGHT = 1.2

    # 신규 진입 종목 페널티 (NEW 종목은 점수 감소)
    NEW_ENTRY_PENALTY = 0.8

    @classmethod
    def get_streak_weight(cls, streak_days: int) -> float:
        """연속 출현 일수에 따른 가중치 반환"""
        if streak_days >= 5:
            return cls.MAX_STREAK_WEIGHT
        return cls.STREAK_WEIGHTS.get(streak_days, 0.5)


class ClassificationConfig:
    """
    2단계 분류 설정 (방안 C)
    - 안정 추천 vs 신규 관심
    """
    # 안정 추천 기준
    STABLE_MIN_STREAK = 3         # 최소 연속 출현 일수
    STABLE_MIN_SCORE = 50         # 최소 점수

    # 신규 관심 기준
    NEW_MIN_SCORE = 40            # 최소 점수

    # 분류별 최대 종목 수
    MAX_STABLE = 50               # 안정 추천 최대 50개
    MAX_NEW = 50                  # 신규 관심 최대 50개


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
