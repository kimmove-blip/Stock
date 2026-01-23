"""
LLM 기반 자율 트레이더 (Green Light 모드)

AI가 모든 트레이딩 결정을 자율적으로 수행하는 모듈
- Claude, OpenAI, Gemini 지원
- 과거 결정 학습 기능
- 시장 컨텍스트 분석
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class LLMTrader:
    """LLM 기반 자율 트레이더"""

    SUPPORTED_PROVIDERS = ['claude', 'openai', 'gemini']

    # 각 provider별 기본 모델
    DEFAULT_MODELS = {
        'claude': 'claude-sonnet-4-20250514',
        'openai': 'gpt-4o',
        'gemini': 'gemini-2.0-flash'
    }

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str = None,
        user_id: int = None
    ):
        """
        Args:
            provider: LLM 제공자 (claude/openai/gemini)
            api_key: API 키
            model: 사용할 모델명 (None이면 기본 모델 사용)
            user_id: 사용자 ID
        """
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"지원하지 않는 provider: {provider}. 지원: {self.SUPPORTED_PROVIDERS}")

        self.provider = provider
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODELS.get(provider)
        self.user_id = user_id
        self.client = None
        self._init_client()

    def _init_client(self):
        """LLM 클라이언트 초기화"""
        if self.provider == 'claude':
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("anthropic 패키지 설치 필요: pip install anthropic")

        elif self.provider == 'openai':
            try:
                import openai
                self.client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("openai 패키지 설치 필요: pip install openai")

        elif self.provider == 'gemini':
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model)
            except ImportError:
                raise ImportError("google-generativeai 패키지 설치 필요: pip install google-generativeai")

    def build_context(
        self,
        portfolio: Dict,
        top100: List[Dict],
        market_info: Dict,
        past_feedback: List[Dict] = None
    ) -> Dict:
        """
        AI에게 전달할 컨텍스트 구성

        Args:
            portfolio: 포트폴리오 현황 (cash, holdings)
            top100: TOP 100 종목 리스트
            market_info: 시장 정보 (코스피, 코스닥 지수)
            past_feedback: 과거 매매 피드백 리스트

        Returns:
            컨텍스트 딕셔너리
        """
        now = datetime.now()

        context = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "trading_day": now.strftime("%A"),  # 요일
            "market_info": market_info or {},
            "portfolio": portfolio or {"cash": 0, "holdings": []},
            "top_opportunities": top100[:20] if top100 else [],  # 상위 20개만
            "past_feedback": past_feedback or []
        }

        return context

    def _load_prompt_template(self) -> str:
        """프롬프트 템플릿 로드"""
        prompt_path = Path(__file__).parent / "prompts" / "greenlight_prompt.txt"

        if prompt_path.exists():
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()

        # 기본 프롬프트
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """기본 프롬프트 반환"""
        return """당신은 완전한 자율권을 가진 AI 주식 트레이더입니다.

## 권한
- 모든 매수/매도 결정권
- 포지션 크기 제한 없음 (몰빵 가능)
- 손절/익절 규칙 없음 - 당신이 판단

## 규칙
- TOP 100 유니버스 내에서만 매수 가능
- 현금이 충분해야 매수 가능
- 보유 종목만 매도 가능

## 과거 매매 피드백
{past_feedback}

위 피드백에서 패턴을 학습하세요:
- 어떤 조건에서 수익이 났는가?
- 어떤 실수를 반복했는가?

## 현재 시장 상황
- 코스피: {kospi_index} ({kospi_change}%)
- 코스닥: {kosdaq_index} ({kosdaq_change}%)
- 시간: {current_time}

## 현재 포트폴리오
총 자산: {total_value}원
현금: {cash}원
보유 종목:
{holdings_summary}

## TOP 매수 기회 (AI 점수순)
{top_opportunities}

## 응답 형식 (반드시 JSON만 출력)
```json
{{
  "market_analysis": "시장 분석 1-2문장",
  "decisions": [
    {{
      "action": "BUY|SELL|HOLD",
      "stock_code": "종목코드",
      "stock_name": "종목명",
      "quantity": 수량,
      "reason": "결정 사유",
      "confidence": 0.0~1.0
    }}
  ],
  "risk_assessment": "현재 포트폴리오 위험도 평가"
}}
```"""

    def _format_prompt(self, context: Dict) -> str:
        """컨텍스트를 프롬프트에 적용"""
        template = self._load_prompt_template()

        # 시장 정보
        market = context.get('market_info', {})
        kospi = market.get('kospi', {})
        kosdaq = market.get('kosdaq', {})

        # 포트폴리오 정보
        portfolio = context.get('portfolio', {})
        holdings = portfolio.get('holdings', [])
        cash = portfolio.get('cash', 0)
        total_value = cash + sum(h.get('eval_amount', 0) for h in holdings)

        # 보유 종목 요약
        holdings_lines = []
        for h in holdings:
            profit_rate = h.get('profit_rate', 0)
            sign = '+' if profit_rate >= 0 else ''
            change_pct = h.get('change_pct', 0)  # 당일 등락률

            # 상한가/하한가 상태
            if change_pct >= 29:
                status = " [상한가-매도가능]"
            elif change_pct <= -29:
                status = " [하한가-매도불가]"
            else:
                status = ""

            holdings_lines.append(
                f"- {h.get('stock_name', '?')} ({h.get('stock_code', '?')}): "
                f"{h.get('quantity', 0)}주, 수익률 {sign}{profit_rate:.1f}%, 당일 {change_pct:+.1f}%{status}"
            )
        holdings_summary = '\n'.join(holdings_lines) if holdings_lines else "없음"

        # TOP 기회
        top_opportunities = context.get('top_opportunities', [])
        top_lines = []
        for t in top_opportunities[:10]:
            change_pct = t.get('change_pct', 0)
            # 상한가/하한가 판단 (±29% 이상)
            if change_pct >= 29:
                status = " [상한가-매수불가]"
            elif change_pct <= -29:
                status = " [하한가-매도불가]"
            elif change_pct >= 25:
                status = " [상한가근접-주의]"
            elif change_pct <= -25:
                status = " [하한가근접-주의]"
            else:
                status = ""

            price = t.get('price') or t.get('close', 0)
            top_lines.append(
                f"- {t.get('name', '?')} ({t.get('code', '?')}): "
                f"점수 {t.get('score', 0)}점, 현재가 {price:,.0f}원, 등락률 {change_pct:+.1f}%{status}"
            )
        top_summary = '\n'.join(top_lines) if top_lines else "데이터 없음"

        # 과거 피드백
        past_feedback = context.get('past_feedback', [])
        feedback_lines = []
        for f in past_feedback[:10]:
            result = f'+{f.get("profit_rate", 0):.1f}%' if f.get('profit_rate', 0) >= 0 else f'{f.get("profit_rate", 0):.1f}%'
            feedback_lines.append(
                f"- {f.get('action', '?')} {f.get('stock_code', '?')}: 결과 {result}, {f.get('feedback_note', '')}"
            )
        feedback_summary = '\n'.join(feedback_lines) if feedback_lines else "피드백 데이터 없음"

        # 템플릿 치환
        prompt = template.format(
            kospi_index=kospi.get('index', 0),
            kospi_change=f"{kospi.get('change_pct', 0):+.2f}",
            kosdaq_index=kosdaq.get('index', 0),
            kosdaq_change=f"{kosdaq.get('change_pct', 0):+.2f}",
            current_time=context.get('timestamp', ''),
            total_value=f"{total_value:,}",
            cash=f"{cash:,}",
            holdings_summary=holdings_summary,
            top_opportunities=top_summary,
            past_feedback=feedback_summary
        )

        return prompt

    def get_trading_decisions(self, context: Dict) -> Dict:
        """
        AI에게 트레이딩 결정 요청

        Args:
            context: build_context()로 생성한 컨텍스트

        Returns:
            {
                "market_analysis": str,
                "decisions": [...],
                "risk_assessment": str,
                "raw_response": str,
                "full_prompt": str
            }
        """
        prompt = self._format_prompt(context)

        # ========================================================
        # [기록] AI에게 보내는 전체 프롬프트 로그 출력
        # ========================================================
        print("\n" + "=" * 70)
        print("  [LLM PROMPT - 전체 프롬프트]")
        print("=" * 70)
        print(prompt)
        print("=" * 70 + "\n")

        try:
            if self.provider == 'claude':
                response = self._call_claude(prompt)
            elif self.provider == 'openai':
                response = self._call_openai(prompt)
            elif self.provider == 'gemini':
                response = self._call_gemini(prompt)
            else:
                raise ValueError(f"지원하지 않는 provider: {self.provider}")

            # ========================================================
            # [기록] AI 응답 전체 로그 출력
            # ========================================================
            print("\n" + "=" * 70)
            print("  [LLM RESPONSE - AI 응답]")
            print("=" * 70)
            print(response)
            print("=" * 70 + "\n")

            # 응답 파싱
            result = self._parse_response(response)
            result['raw_response'] = response
            result['full_prompt'] = prompt  # 전체 프롬프트 저장
            result['prompt_summary'] = prompt[:500]  # 호환성 유지

            return result

        except Exception as e:
            print(f"[LLMTrader] AI 호출 실패: {e}")
            return {
                "error": str(e),
                "market_analysis": "",
                "decisions": [],
                "risk_assessment": "",
                "raw_response": ""
            }

    def _call_claude(self, prompt: str) -> str:
        """Claude API 호출"""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text

    def _call_openai(self, prompt: str) -> str:
        """OpenAI API 호출"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "당신은 한국 주식 전문 AI 트레이더입니다. 반드시 JSON 형식으로만 응답하세요."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2048,
            temperature=0.7
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        """Gemini API 호출"""
        response = self.client.generate_content(prompt)
        return response.text

    def _parse_response(self, raw_response: str) -> Dict:
        """
        AI 응답 파싱

        Args:
            raw_response: AI 원본 응답

        Returns:
            파싱된 결정 딕셔너리
        """
        default_result = {
            "market_analysis": "",
            "decisions": [],
            "risk_assessment": ""
        }

        try:
            # JSON 블록 추출 (```json ... ``` 또는 { ... })
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_response)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 직접 JSON 찾기
                json_match = re.search(r'\{[\s\S]*\}', raw_response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    print("[LLMTrader] JSON을 찾을 수 없음")
                    return default_result

            parsed = json.loads(json_str)

            # 결정 검증
            decisions = parsed.get('decisions', [])
            valid_decisions = []

            for d in decisions:
                action = d.get('action', '').upper()
                if action not in ['BUY', 'SELL', 'HOLD']:
                    continue

                # HOLD는 건너뛰기 (실행할 게 없음)
                if action == 'HOLD':
                    continue

                stock_code = d.get('stock_code', '')
                quantity = d.get('quantity', 0)

                if not stock_code or quantity <= 0:
                    continue

                valid_decisions.append({
                    "action": action,
                    "stock_code": stock_code,
                    "stock_name": d.get('stock_name', ''),
                    "quantity": quantity,
                    "reason": d.get('reason', ''),
                    "confidence": min(1.0, max(0.0, d.get('confidence', 0.5)))
                })

            return {
                "market_analysis": parsed.get('market_analysis', ''),
                "decisions": valid_decisions,
                "risk_assessment": parsed.get('risk_assessment', '')
            }

        except json.JSONDecodeError as e:
            print(f"[LLMTrader] JSON 파싱 실패: {e}")
            print(f"[LLMTrader] 원본: {raw_response[:500]}")
            return default_result
        except Exception as e:
            print(f"[LLMTrader] 응답 파싱 실패: {e}")
            return default_result

    def validate_decisions(
        self,
        decisions: List[Dict],
        portfolio: Dict,
        top100_codes: List[str]
    ) -> List[Dict]:
        """
        결정 유효성 검증

        Args:
            decisions: AI 결정 리스트
            portfolio: 포트폴리오 현황
            top100_codes: TOP 100 종목 코드 리스트

        Returns:
            유효한 결정만 필터링된 리스트
        """
        valid = []
        cash = portfolio.get('cash', 0)
        holdings = {h.get('stock_code'): h for h in portfolio.get('holdings', [])}

        for d in decisions:
            action = d.get('action')
            stock_code = d.get('stock_code')
            quantity = d.get('quantity', 0)

            if action == 'BUY':
                # TOP 100에 있는지 확인
                if stock_code not in top100_codes:
                    print(f"[LLMTrader] {stock_code}는 TOP 100에 없음 - 매수 불가")
                    continue

                # 현금 충분한지는 실행 시점에 확인 (가격 변동 있을 수 있음)
                valid.append(d)

            elif action == 'SELL':
                # 보유 종목인지 확인
                if stock_code not in holdings:
                    print(f"[LLMTrader] {stock_code}는 보유 종목이 아님 - 매도 불가")
                    continue

                # 보유 수량 확인
                held_qty = holdings[stock_code].get('quantity', 0)
                if quantity > held_qty:
                    print(f"[LLMTrader] {stock_code} 요청 {quantity}주 > 보유 {held_qty}주 - 조정")
                    d['quantity'] = held_qty

                valid.append(d)

        return valid


def test_llm_trader():
    """간단한 테스트"""
    # 환경변수에서 API 키 가져오기
    import os

    api_key = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('OPENAI_API_KEY')
    provider = 'claude' if os.environ.get('ANTHROPIC_API_KEY') else 'openai'

    if not api_key:
        print("API 키가 설정되지 않았습니다.")
        return

    trader = LLMTrader(provider=provider, api_key=api_key)

    context = trader.build_context(
        portfolio={
            "cash": 5000000,
            "holdings": [
                {"stock_code": "005930", "stock_name": "삼성전자", "quantity": 10, "eval_amount": 700000, "profit_rate": 5.0}
            ]
        },
        top100=[
            {"code": "000660", "name": "SK하이닉스", "score": 92, "price": 180000},
            {"code": "035720", "name": "카카오", "score": 85, "price": 45000},
        ],
        market_info={
            "kospi": {"index": 2650, "change_pct": -0.5},
            "kosdaq": {"index": 850, "change_pct": 1.2}
        },
        past_feedback=[
            {"action": "BUY", "stock_code": "005930", "profit_rate": 15.0, "feedback_note": "좋은결정"},
        ]
    )

    result = trader.get_trading_decisions(context)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_llm_trader()
