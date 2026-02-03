#!/usr/bin/env python3
"""
아침 시황 브리핑 에이전트
- 해외증시, 환율, VIX, 선물 데이터 수집
- 투자 스탠스 결정 (공격적/중립/보수적/방어적)
- 이메일 발송

Usage:
    python morning_briefing.py              # 콘솔 출력
    python morning_briefing.py --email      # 이메일 발송
    python morning_briefing.py --json       # JSON 출력
"""

import argparse
import json
from datetime import datetime, timedelta
from typing import Optional
import sys

try:
    import yfinance as yf
except ImportError:
    print("yfinance 설치 필요: pip install yfinance")
    sys.exit(1)


# ============================================================
# 설정
# ============================================================

# 수집할 티커
TICKERS = {
    # 미국 증시
    "nasdaq": "^IXIC",
    "sp500": "^GSPC",
    "dow": "^DJI",
    "vix": "^VIX",
    # 아시아
    "nikkei": "^N225",
    "shanghai": "000001.SS",
    "hangseng": "^HSI",
    # 환율
    "usd_krw": "KRW=X",
    "usd_jpy": "JPY=X",
    # 원자재
    "wti": "CL=F",
    "gold": "GC=F",
    # 선물 (한국 선물은 yfinance에서 지원 안됨, 대체 지표 사용)
    # "kospi_future": "KS=F",  # 미지원
}

# 스탠스별 투자 배수
STANCE_MULTIPLIERS = {
    "공격적": 1.2,
    "적극적": 1.1,
    "중립": 1.0,
    "보수적": 0.8,
    "방어적": 0.5,
    "회피": 0.3,
}


# ============================================================
# 데이터 수집
# ============================================================

def fetch_market_data() -> dict:
    """해외증시 및 지표 데이터 수집"""
    data = {}

    for name, ticker in TICKERS.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")

            if len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                previous = hist['Close'].iloc[-2]
                change = ((current - previous) / previous) * 100

                data[name] = {
                    "price": round(current, 2),
                    "change": round(change, 2),
                    "previous": round(previous, 2),
                }
            elif len(hist) == 1:
                data[name] = {
                    "price": round(hist['Close'].iloc[-1], 2),
                    "change": 0.0,
                    "previous": round(hist['Close'].iloc[-1], 2),
                }
        except Exception as e:
            print(f"[WARN] {name} 데이터 수집 실패: {e}")
            data[name] = {"price": 0, "change": 0, "previous": 0, "error": str(e)}

    return data


def fetch_news_headlines() -> list:
    """주요 뉴스 헤드라인 (추후 구현)"""
    # TODO: 네이버/구글 뉴스 크롤링 또는 뉴스 API 연동
    return [
        "* 뉴스 수집 기능은 추후 구현 예정",
    ]


# ============================================================
# 스탠스 계산
# ============================================================

def calculate_stance(data: dict) -> tuple:
    """
    시장 데이터 기반 투자 스탠스 결정

    Returns:
        (stance: str, multiplier: float, score: int, reasons: list)
    """
    score = 0
    reasons = []

    # 1. 나스닥 (가중치 높음 - 한국 기술주 연동)
    nasdaq = data.get("nasdaq", {})
    nasdaq_change = nasdaq.get("change", 0)

    if nasdaq_change >= 2.0:
        score += 3
        reasons.append(f"나스닥 급등 +{nasdaq_change}%")
    elif nasdaq_change >= 1.0:
        score += 2
        reasons.append(f"나스닥 상승 +{nasdaq_change}%")
    elif nasdaq_change >= 0.3:
        score += 1
        reasons.append(f"나스닥 소폭 상승 +{nasdaq_change}%")
    elif nasdaq_change <= -3.0:
        score -= 4
        reasons.append(f"나스닥 급락 {nasdaq_change}% ⚠️")
    elif nasdaq_change <= -2.0:
        score -= 3
        reasons.append(f"나스닥 큰 폭 하락 {nasdaq_change}%")
    elif nasdaq_change <= -1.0:
        score -= 2
        reasons.append(f"나스닥 하락 {nasdaq_change}%")
    elif nasdaq_change <= -0.3:
        score -= 1
        reasons.append(f"나스닥 소폭 하락 {nasdaq_change}%")

    # 2. S&P500
    sp500 = data.get("sp500", {})
    sp500_change = sp500.get("change", 0)

    if sp500_change >= 1.0:
        score += 1
        reasons.append(f"S&P500 상승 +{sp500_change}%")
    elif sp500_change <= -1.0:
        score -= 1
        reasons.append(f"S&P500 하락 {sp500_change}%")

    # 3. VIX (공포지수) - 낮을수록 좋음
    vix = data.get("vix", {})
    vix_price = vix.get("price", 20)

    if vix_price < 15:
        score += 2
        reasons.append(f"VIX {vix_price} (매우 안정)")
    elif vix_price < 20:
        score += 1
        reasons.append(f"VIX {vix_price} (안정)")
    elif vix_price > 30:
        score -= 3
        reasons.append(f"VIX {vix_price} (공포) ⚠️")
    elif vix_price > 25:
        score -= 2
        reasons.append(f"VIX {vix_price} (불안)")

    # 4. 환율 (원화 강세 = 외국인 유입)
    usd_krw = data.get("usd_krw", {})
    krw_change = usd_krw.get("change", 0)

    if krw_change <= -0.5:  # 원화 강세 (달러 약세)
        score += 1
        reasons.append(f"원화 강세 (외국인 유입 기대)")
    elif krw_change >= 1.0:  # 원화 약세 (달러 강세)
        score -= 1
        reasons.append(f"원화 약세 {krw_change}% (외국인 이탈 우려)")

    # 5. 아시아 증시
    nikkei = data.get("nikkei", {})
    nikkei_change = nikkei.get("change", 0)

    if nikkei_change >= 1.0:
        score += 1
        reasons.append(f"닛케이 상승 +{nikkei_change}%")
    elif nikkei_change <= -1.0:
        score -= 1
        reasons.append(f"닛케이 하락 {nikkei_change}%")

    # 6. 금 (안전자산 선호 지표)
    gold = data.get("gold", {})
    gold_change = gold.get("change", 0)

    if gold_change >= 2.0:
        score -= 1
        reasons.append(f"금 급등 +{gold_change}% (안전자산 선호)")
    elif gold_change <= -1.0:
        score += 1
        reasons.append(f"금 하락 {gold_change}% (위험자산 선호)")

    # 스탠스 결정
    if score >= 5:
        stance = "공격적"
    elif score >= 3:
        stance = "적극적"
    elif score >= 1:
        stance = "중립"
    elif score >= -1:
        stance = "보수적"
    elif score >= -3:
        stance = "방어적"
    else:
        stance = "회피"

    multiplier = STANCE_MULTIPLIERS[stance]

    return stance, multiplier, score, reasons


# ============================================================
# 브리핑 생성
# ============================================================

def generate_briefing(data: dict, stance: str, multiplier: float,
                      score: int, reasons: list) -> str:
    """텍스트 브리핑 생성"""

    now = datetime.now()
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

    def fmt_change(val):
        if val > 0:
            return f"+{val}%"
        return f"{val}%"

    def get_arrow(val):
        if val > 0.3:
            return "↑"
        elif val < -0.3:
            return "↓"
        return "→"

    # 데이터 추출
    nasdaq = data.get("nasdaq", {})
    sp500 = data.get("sp500", {})
    dow = data.get("dow", {})
    vix = data.get("vix", {})
    nikkei = data.get("nikkei", {})
    shanghai = data.get("shanghai", {})
    hangseng = data.get("hangseng", {})
    usd_krw = data.get("usd_krw", {})
    wti = data.get("wti", {})
    gold = data.get("gold", {})

    # 스탠스별 이모지
    stance_emoji = {
        "공격적": "🚀",
        "적극적": "📈",
        "중립": "⚖️",
        "보수적": "🛡️",
        "방어적": "⚠️",
        "회피": "🚨",
    }

    # 투자금 조정 안내
    if multiplier > 1.0:
        invest_guide = f"투자금 +{int((multiplier-1)*100)}% 증가"
    elif multiplier < 1.0:
        invest_guide = f"투자금 {int((1-multiplier)*100)}% 축소"
    else:
        invest_guide = "투자금 유지"

    briefing = f"""
═══════════════════════════════════════════════════════════
  📊 {now.strftime('%Y-%m-%d')} ({weekday_kr}) 아침 시황 브리핑
═══════════════════════════════════════════════════════════

【미국 증시】
  • 나스닥:  {nasdaq.get('price', 'N/A'):>10,}  {fmt_change(nasdaq.get('change', 0)):>7}  {get_arrow(nasdaq.get('change', 0))}
  • S&P500:  {sp500.get('price', 'N/A'):>10,}  {fmt_change(sp500.get('change', 0)):>7}  {get_arrow(sp500.get('change', 0))}
  • 다우:    {dow.get('price', 'N/A'):>10,}  {fmt_change(dow.get('change', 0)):>7}  {get_arrow(dow.get('change', 0))}
  • VIX:     {vix.get('price', 'N/A'):>10}   {'(안정)' if vix.get('price', 20) < 20 else '(불안)' if vix.get('price', 20) < 25 else '(공포)'}

【아시아 증시】
  • 닛케이:  {nikkei.get('price', 'N/A'):>10,}  {fmt_change(nikkei.get('change', 0)):>7}  {get_arrow(nikkei.get('change', 0))}
  • 상해:    {shanghai.get('price', 'N/A'):>10,}  {fmt_change(shanghai.get('change', 0)):>7}  {get_arrow(shanghai.get('change', 0))}
  • 항셍:    {hangseng.get('price', 'N/A'):>10,}  {fmt_change(hangseng.get('change', 0)):>7}  {get_arrow(hangseng.get('change', 0))}

【환율 / 원자재】
  • USD/KRW: {usd_krw.get('price', 'N/A'):>10,}  {fmt_change(usd_krw.get('change', 0)):>7}
  • WTI:     ${wti.get('price', 'N/A'):>9}  {fmt_change(wti.get('change', 0)):>7}
  • 금:      ${gold.get('price', 'N/A'):>9,}  {fmt_change(gold.get('change', 0)):>7}

【기타】
  • 금 상승률이 높으면 안전자산 선호 심리

═══════════════════════════════════════════════════════════
  {stance_emoji.get(stance, '📊')} 투자 스탠스: {stance} ({invest_guide})
     점수: {score}점 / 배수: {multiplier}x
═══════════════════════════════════════════════════════════

【판단 근거】
"""

    for reason in reasons:
        briefing += f"  • {reason}\n"

    # 섹터 추천
    briefing += "\n【오늘의 주목 섹터】\n"

    if nasdaq.get('change', 0) > 1.0:
        briefing += "  • 반도체/IT: 나스닥 강세로 수혜 예상\n"
    if wti.get('change', 0) > 2.0:
        briefing += "  • 정유/화학: 유가 상승 수혜\n"
    elif wti.get('change', 0) < -2.0:
        briefing += "  • 항공/운송: 유가 하락 수혜\n"
    if vix.get('price', 20) > 25:
        briefing += "  • 방어주/배당주: 변동성 확대 시 안전자산 선호\n"
    if score >= 3:
        briefing += "  • 성장주/테마주: 리스크온 환경\n"
    elif score <= -2:
        briefing += "  • 현금 비중 확대 권장\n"

    briefing += f"""
═══════════════════════════════════════════════════════════
  ⏰ 생성 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}
═══════════════════════════════════════════════════════════
"""

    return briefing


def generate_json_output(data: dict, stance: str, multiplier: float,
                         score: int, reasons: list) -> dict:
    """JSON 형식 출력"""
    return {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "generated_at": datetime.now().isoformat(),
        "market_data": data,
        "stance": {
            "name": stance,
            "multiplier": multiplier,
            "score": score,
            "reasons": reasons,
        },
    }


# ============================================================
# 이메일 발송
# ============================================================

def send_email(briefing: str, stance: str):
    """이메일 발송 (email_sender 모듈 사용)"""
    try:
        from email_sender import EmailSender

        sender = EmailSender(use_db_subscribers=True)

        if not sender.is_configured():
            print("[ERROR] 이메일 설정이 필요합니다. .env 파일을 확인하세요.")
            return False

        now = datetime.now()
        subject = f"[시황브리핑] {now.strftime('%m/%d')} 투자스탠스: {stance}"

        # 텍스트를 HTML로 변환 (줄바꿈 및 고정폭 폰트)
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Malgun Gothic', monospace; }}
                pre {{
                    background-color: #1a1a2e;
                    color: #eaeaea;
                    padding: 20px;
                    border-radius: 10px;
                    font-size: 14px;
                    line-height: 1.4;
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>
            <pre>{briefing}</pre>
        </body>
        </html>
        """

        return sender.send_report(subject, html_body)

    except ImportError as e:
        print(f"[ERROR] email_sender 모듈 로드 실패: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 이메일 발송 실패: {e}")
        return False


# ============================================================
# auto_trader.py 연동
# ============================================================

def save_stance_for_auto_trader(stance: str, multiplier: float, data: dict):
    """auto_trader.py가 읽을 수 있도록 스탠스 저장"""
    output = {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "stance": stance,
        "multiplier": multiplier,
        "nasdaq_change": data.get("nasdaq", {}).get("change", 0),
        "vix": data.get("vix", {}).get("price", 20),
        "generated_at": datetime.now().isoformat(),
    }

    output_path = "/home/kimhc/Stock/output/morning_stance.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] 스탠스 저장: {output_path}")
    return output_path


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='아침 시황 브리핑 에이전트')
    parser.add_argument('--email', action='store_true', help='이메일 발송')
    parser.add_argument('--json', action='store_true', help='JSON 출력')
    parser.add_argument('--save', action='store_true', help='auto_trader용 스탠스 저장')
    args = parser.parse_args()

    print("[1/4] 해외증시 데이터 수집 중...")
    data = fetch_market_data()

    print("[2/4] 투자 스탠스 계산 중...")
    stance, multiplier, score, reasons = calculate_stance(data)

    print("[3/4] 브리핑 생성 중...")

    if args.json:
        output = generate_json_output(data, stance, multiplier, score, reasons)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        briefing = generate_briefing(data, stance, multiplier, score, reasons)
        print(briefing)

    print("[4/4] 후처리...")

    # auto_trader용 스탠스 저장
    if args.save or args.email:
        save_stance_for_auto_trader(stance, multiplier, data)

    # 이메일 발송
    if args.email:
        briefing = generate_briefing(data, stance, multiplier, score, reasons)
        send_email(briefing, stance)

    print(f"\n[완료] 투자 스탠스: {stance} (배수: {multiplier}x)")


if __name__ == "__main__":
    main()
