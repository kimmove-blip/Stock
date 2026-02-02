"""
Stock Analysis Orchestrator

에이전트 조율 및 분석 파이프라인 관리

사용법:
    # 단일 종목 분석
    from agents.orchestrator import StockOrchestrator
    orch = StockOrchestrator()
    result = orch.analyze_stock("005930")

    # 포트폴리오 분석
    result = orch.analyze_portfolio(user_id=2)

    # 매매 신호 생성
    signal = orch.generate_signal("005930")
"""

from datetime import datetime
from typing import Optional
from pathlib import Path
import json


class StockOrchestrator:
    """주식 분석 에이전트 오케스트레이터

    여러 에이전트의 작업을 조율하고 결과를 통합합니다.
    """

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.output_dir = self.base_dir / "output"

    def analyze_stock(
        self,
        stock_code: str,
        include_prediction: bool = False,
        include_sector: bool = False,
    ) -> dict:
        """
        단일 종목 종합 분석

        분석 파이프라인:
        1. MarketDataAgent: 시세 데이터 수집
        2. TechnicalAgent: 기술적 분석
        3. ScoringAgent: V1~V10 스코어 계산
        4. PatternAgent: 패턴 감지
        5. (선택) PredictionAgent: V9 갭상승 예측
        6. (선택) SectorAgent: 섹터/테마 분석
        7. SignalAgent: 최종 신호 생성

        Args:
            stock_code: 종목코드 (6자리)
            include_prediction: V9 예측 포함 여부
            include_sector: 섹터 분석 포함 여부

        Returns:
            종합 분석 결과 딕셔너리
        """
        result = {
            "stock_code": stock_code,
            "analyzed_at": datetime.now().isoformat(),
            "pipeline": [],
            "analysis": {},
            "signal": None,
            "errors": [],
        }

        # 이 메서드는 Claude Code Task 도구를 통해 실행됨
        # 각 단계에서 해당 에이전트 프롬프트를 참조

        pipeline_steps = [
            ("market-data", f"종목 {stock_code} 시세 데이터 수집"),
            ("technical", f"종목 {stock_code} 기술적 분석"),
            ("scoring", f"종목 {stock_code} V1~V10 스코어 계산"),
            ("pattern", f"종목 {stock_code} 차트 패턴 감지"),
        ]

        if include_prediction:
            pipeline_steps.append(
                ("prediction", f"종목 {stock_code} V9 갭상승 확률 예측")
            )

        if include_sector:
            pipeline_steps.append(
                ("sector", f"종목 {stock_code} 섹터/테마 분석")
            )

        pipeline_steps.append(
            ("signal", f"종목 {stock_code} 분석 결과 기반 매매 신호 생성")
        )

        result["pipeline"] = [
            {"agent": agent, "task": task}
            for agent, task in pipeline_steps
        ]

        return result

    def analyze_portfolio(self, user_id: int) -> dict:
        """
        포트폴리오 종합 분석

        분석 파이프라인:
        1. 보유 종목 조회
        2. 각 종목별 ScoringAgent 분석
        3. PortfolioAgent: 포트폴리오 최적화 제안
        4. RiskAgent: 리스크 평가

        Args:
            user_id: 사용자 ID

        Returns:
            포트폴리오 분석 결과
        """
        result = {
            "user_id": user_id,
            "analyzed_at": datetime.now().isoformat(),
            "pipeline": [
                {"agent": "monitor", "task": f"사용자 {user_id} 보유 종목 조회"},
                {"agent": "scoring", "task": "보유 종목별 V2 스코어 계산"},
                {"agent": "portfolio", "task": "포트폴리오 분산/최적화 분석"},
                {"agent": "risk", "task": "포트폴리오 리스크 평가"},
            ],
            "holdings": [],
            "portfolio_analysis": {},
            "risk_assessment": {},
            "recommendations": [],
        }

        return result

    def generate_signal(
        self,
        stock_code: str,
        context: Optional[dict] = None,
    ) -> dict:
        """
        매매 신호 생성

        Args:
            stock_code: 종목코드
            context: 추가 컨텍스트 (기존 분석 결과 등)

        Returns:
            매매 신호 결과
        """
        result = {
            "stock_code": stock_code,
            "generated_at": datetime.now().isoformat(),
            "signal": None,
            "confidence": 0.0,
            "reasons": [],
            "action_plan": {},
        }

        # SignalAgent 호출
        result["pipeline"] = [
            {"agent": "scoring", "task": f"종목 {stock_code} 스코어 계산"},
            {"agent": "technical", "task": f"종목 {stock_code} 기술적 분석"},
            {"agent": "risk", "task": f"종목 {stock_code} 리스크 평가"},
            {"agent": "signal", "task": "분석 결과 종합하여 매매 신호 생성"},
        ]

        return result

    def scan_market(
        self,
        min_score: int = 70,
        min_trading_value: int = 50,  # 억원
        max_results: int = 20,
    ) -> dict:
        """
        시장 전체 스캔

        Args:
            min_score: 최소 V2 스코어
            min_trading_value: 최소 거래대금 (억원)
            max_results: 최대 결과 수

        Returns:
            스캔 결과
        """
        result = {
            "scanned_at": datetime.now().isoformat(),
            "filters": {
                "min_score": min_score,
                "min_trading_value": min_trading_value,
            },
            "pipeline": [
                {"agent": "market-data", "task": "전 종목 시세 수집"},
                {"agent": "scoring", "task": f"V2≥{min_score} 종목 필터링"},
                {"agent": "signal", "task": "상위 종목 신호 생성"},
            ],
            "candidates": [],
        }

        return result

    def execute_trade(
        self,
        user_id: int,
        stock_code: str,
        order_type: str,  # BUY or SELL
        quantity: int,
        price: int = 0,  # 0이면 시장가
    ) -> dict:
        """
        매매 실행 (주의: 실제 주문 발생)

        Args:
            user_id: 사용자 ID
            stock_code: 종목코드
            order_type: BUY 또는 SELL
            quantity: 수량
            price: 가격 (0이면 시장가)

        Returns:
            주문 결과
        """
        result = {
            "user_id": user_id,
            "stock_code": stock_code,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "requested_at": datetime.now().isoformat(),
            "pipeline": [
                {"agent": "risk", "task": "주문 전 리스크 검증"},
                {"agent": "order", "task": "주문 실행"},
                {"agent": "monitor", "task": "체결 확인"},
            ],
            "order_result": None,
        }

        return result

    def generate_report(
        self,
        user_id: int,
        report_type: str = "daily",  # daily, weekly, monthly
        output_format: str = "json",  # json, pdf
    ) -> dict:
        """
        리포트 생성

        Args:
            user_id: 사용자 ID
            report_type: 리포트 유형
            output_format: 출력 형식

        Returns:
            리포트 생성 결과
        """
        result = {
            "user_id": user_id,
            "report_type": report_type,
            "output_format": output_format,
            "generated_at": datetime.now().isoformat(),
            "pipeline": [
                {"agent": "monitor", "task": "거래 내역 조회"},
                {"agent": "report", "task": f"{report_type} 리포트 생성"},
            ],
            "output_path": None,
        }

        return result


# Claude Code Task 호출용 헬퍼 함수
def get_analysis_prompt(stock_code: str, analysis_type: str = "full") -> str:
    """
    주식 분석용 Claude Code Task 프롬프트 생성

    Args:
        stock_code: 종목코드
        analysis_type: 분석 유형 (full, quick, signal)

    Returns:
        Task 프롬프트 문자열
    """
    if analysis_type == "full":
        return f"""
종목 {stock_code} 종합 분석을 수행합니다.

1단계: MarketDataAgent 프롬프트 참조하여 시세 데이터 수집
2단계: TechnicalAgent 프롬프트 참조하여 기술적 분석
3단계: ScoringAgent 프롬프트 참조하여 V1~V10 스코어 계산
4단계: PatternAgent 프롬프트 참조하여 차트 패턴 감지
5단계: SignalAgent 프롬프트 참조하여 최종 매매 신호 생성

각 단계별 결과를 JSON 형식으로 통합하여 반환합니다.
"""
    elif analysis_type == "quick":
        return f"""
종목 {stock_code} 빠른 분석을 수행합니다.

ScoringAgent 프롬프트 참조하여:
1. V2 스코어 계산
2. 주요 신호 확인
3. 간단한 매매 권고

결과를 JSON 형식으로 반환합니다.
"""
    elif analysis_type == "signal":
        return f"""
종목 {stock_code} 매매 신호만 생성합니다.

SignalAgent 프롬프트 참조하여:
1. 기술적 분석 수행
2. 스코어 기반 신호 강도 계산
3. BUY/HOLD/SELL 결정

결과를 JSON 형식으로 반환합니다.
"""
    else:
        raise ValueError(f"Unknown analysis type: {analysis_type}")


def get_portfolio_prompt(user_id: int) -> str:
    """
    포트폴리오 분석용 프롬프트 생성
    """
    return f"""
사용자 {user_id}의 포트폴리오를 분석합니다.

1단계: MonitorAgent 참조하여 보유 종목 조회
2단계: 각 종목별 ScoringAgent로 V2 스코어 계산
3단계: PortfolioAgent 참조하여 분산투자 분석
4단계: RiskAgent 참조하여 리스크 평가
5단계: 리밸런싱 제안 생성

결과를 JSON 형식으로 반환합니다.
"""


def get_scan_prompt(
    min_score: int = 70,
    min_trading_value: int = 50,
) -> str:
    """
    시장 스캔용 프롬프트 생성
    """
    return f"""
시장 전체를 스캔하여 매수 후보를 찾습니다.

조건:
- V2 스코어 {min_score}점 이상
- 거래대금 {min_trading_value}억원 이상

1단계: MarketDataAgent로 전 종목 시세 수집
2단계: ScoringAgent로 V2 스코어 계산 및 필터링
3단계: SignalAgent로 상위 종목 매매 신호 생성

상위 20개 종목을 JSON 형식으로 반환합니다.
"""


__all__ = [
    "StockOrchestrator",
    "get_analysis_prompt",
    "get_portfolio_prompt",
    "get_scan_prompt",
]
