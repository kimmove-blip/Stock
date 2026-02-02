"""
Stock Analysis Agent System

Claude Code Task 도구를 활용한 주식 분석/예측 전문 서브에이전트 시스템

에이전트 유형:
- Data Agents: 데이터 수집 (MarketData, InvestorFlow, Macro)
- Analysis Agents: 분석/예측 (Technical, Scoring, Pattern, Sector, Prediction)
- Strategy Agents: 전략 (Signal, Risk, Portfolio)
- Execution Agents: 실행 (Order, Monitor, Report)

사용법:
    # Claude Code Task 도구 호출 시
    Task(
        subagent_type="stock-scoring",
        prompt="삼성전자(005930) V1~V10 스코어 계산"
    )

    # 또는 orchestrator 사용
    from agents.orchestrator import StockOrchestrator
    orch = StockOrchestrator()
    result = orch.analyze_stock("005930")
"""

from pathlib import Path

# 에이전트 프롬프트 디렉토리
PROMPTS_DIR = Path(__file__).parent / "prompts"
SCHEMAS_DIR = Path(__file__).parent / "schemas"

# 에이전트 타입 정의
AGENT_TYPES = {
    # Data Agents
    "market-data": {
        "name": "MarketDataAgent",
        "description": "실시간 시세, OHLCV, 거래량 데이터 수집",
        "prompt_file": "market_data_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "investor-flow": {
        "name": "InvestorFlowAgent",
        "description": "외국인/기관/개인 수급 데이터 분석",
        "prompt_file": "investor_flow_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "macro": {
        "name": "MacroAgent",
        "description": "나스닥, 환율, 금리 등 매크로 지표 수집",
        "prompt_file": "macro_agent.md",
        "tools": ["Read", "Bash", "WebFetch"],
    },

    # Analysis Agents
    "technical": {
        "name": "TechnicalAgent",
        "description": "기술적 분석 (이평선, RSI, MACD, 볼린저밴드)",
        "prompt_file": "technical_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "scoring": {
        "name": "ScoringAgent",
        "description": "V1~V10 스코어 계산 및 통합",
        "prompt_file": "scoring_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "pattern": {
        "name": "PatternAgent",
        "description": "차트 패턴 감지 (VCP, 장대양봉, 역배열)",
        "prompt_file": "pattern_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "sector": {
        "name": "SectorAgent",
        "description": "섹터/테마 분석, 대장주-종속주 관계",
        "prompt_file": "sector_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "prediction": {
        "name": "PredictionAgent",
        "description": "ML 기반 갭상승 예측 (V9)",
        "prompt_file": "prediction_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },

    # Strategy Agents
    "signal": {
        "name": "SignalAgent",
        "description": "매수/매도 신호 생성",
        "prompt_file": "signal_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "risk": {
        "name": "RiskAgent",
        "description": "리스크 평가, 포지션 사이징",
        "prompt_file": "risk_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "portfolio": {
        "name": "PortfolioAgent",
        "description": "포트폴리오 최적화, 분산투자 검토",
        "prompt_file": "portfolio_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },

    # Execution Agents
    "order": {
        "name": "OrderAgent",
        "description": "주문 생성 및 체결 관리",
        "prompt_file": "order_agent.md",
        "tools": ["Read", "Bash"],
    },
    "monitor": {
        "name": "MonitorAgent",
        "description": "보유종목 실시간 모니터링",
        "prompt_file": "monitor_agent.md",
        "tools": ["Read", "Bash", "Grep", "Glob"],
    },
    "report": {
        "name": "ReportAgent",
        "description": "성과 분석, 리포트 생성",
        "prompt_file": "report_agent.md",
        "tools": ["Read", "Bash", "Write"],
    },
}


def get_agent_prompt(agent_type: str) -> str:
    """에이전트 프롬프트 파일 내용 반환"""
    if agent_type not in AGENT_TYPES:
        raise ValueError(f"Unknown agent type: {agent_type}")

    prompt_file = PROMPTS_DIR / AGENT_TYPES[agent_type]["prompt_file"]
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    return prompt_file.read_text(encoding="utf-8")


def list_agents() -> dict:
    """사용 가능한 에이전트 목록 반환"""
    return {
        agent_type: {
            "name": info["name"],
            "description": info["description"],
        }
        for agent_type, info in AGENT_TYPES.items()
    }


def get_agent_info(agent_type: str) -> dict:
    """특정 에이전트 정보 반환"""
    if agent_type not in AGENT_TYPES:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return AGENT_TYPES[agent_type]


__all__ = [
    "AGENT_TYPES",
    "PROMPTS_DIR",
    "SCHEMAS_DIR",
    "get_agent_prompt",
    "list_agents",
    "get_agent_info",
]
