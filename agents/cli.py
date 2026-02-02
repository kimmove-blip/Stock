#!/usr/bin/env python3
"""
에이전트 CLI 러너

사용법:
    python -m agents.cli scoring 005930
    python -m agents.cli technical 005930
    python -m agents.cli signal 005930
    python -m agents.cli analyze 005930 --full
    python -m agents.cli monitor --user 2
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_scoring_agent(ticker: str, version: str = "all") -> dict:
    """ScoringAgent 실행"""
    from pykrx import stock
    from scoring import calculate_score, compare_scores
    from scoring.indicators import calculate_base_indicators

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=90)
    df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)

    if df is None or len(df) < 20:
        return {"error": "데이터 부족", "stock_code": ticker}

    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})

    if version == "all":
        results = compare_scores(df)
        scores = {v: data['score'] for v, data in results.items()}
        signals = results.get('v2', {}).get('signals', [])
    else:
        result = calculate_score(df, version)
        scores = {version: result.get('score', 0)}
        signals = result.get('signals', [])

    return {
        "agent": "ScoringAgent",
        "stock_code": ticker,
        "stock_name": name,
        "calculated_at": datetime.now().isoformat(),
        "scores": scores,
        "signals": signals[:5],
        "recommendation": "BUY" if scores.get('v2', 0) >= 65 else "HOLD" if scores.get('v2', 0) >= 50 else "SELL"
    }


def run_technical_agent(ticker: str) -> dict:
    """TechnicalAgent 실행"""
    from pykrx import stock
    from scoring.indicators import (
        calculate_base_indicators,
        check_ma_status,
        check_rsi_status,
        check_volume_status
    )

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=120)
    df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)

    if df is None or len(df) < 20:
        return {"error": "데이터 부족", "stock_code": ticker}

    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue'})
    if 'TradingValue' not in df.columns:
        df['TradingValue'] = df['Close'] * df['Volume']

    df = calculate_base_indicators(df)

    ma_status = check_ma_status(df)
    rsi_status = check_rsi_status(df)
    vol_status = check_volume_status(df)

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    change_pct = (curr['Close'] / prev['Close'] - 1) * 100

    return {
        "agent": "TechnicalAgent",
        "stock_code": ticker,
        "stock_name": name,
        "analyzed_at": datetime.now().isoformat(),
        "price": {
            "current": int(curr['Close']),
            "change_pct": round(change_pct, 2)
        },
        "moving_averages": {
            "status": ma_status['status'],
            "sma20_slope": round(ma_status.get('sma20_slope', 0), 2),
            "distance_to_sma20": round(ma_status.get('distance_to_sma20', 0), 2)
        },
        "momentum": {
            "rsi": round(rsi_status.get('rsi', 50), 1),
            "rsi_zone": rsi_status.get('zone')
        },
        "volume": {
            "vol_ratio": round(vol_status.get('vol_ratio', 1), 2),
            "level": vol_status.get('level'),
            "trading_value_억": round(vol_status.get('trading_value_억', 0), 1)
        },
        "signals": {
            "buy": [],
            "sell": [],
            "overall": "BULLISH" if ma_status['status'] == 'aligned' else "BEARISH" if ma_status['status'] == 'reverse_aligned' else "NEUTRAL"
        }
    }


def run_pattern_agent(ticker: str) -> dict:
    """PatternAgent 실행"""
    from pykrx import stock
    from scoring.indicators import (
        calculate_base_indicators,
        detect_vcp_pattern,
        detect_obv_divergence,
        check_ma_status
    )

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=120)
    df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)

    if df is None or len(df) < 20:
        return {"error": "데이터 부족", "stock_code": ticker}

    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})
    df = calculate_base_indicators(df)

    patterns = []
    curr = df.iloc[-1]

    # VCP 패턴
    vcp = detect_vcp_pattern(df)
    if vcp['detected']:
        patterns.append({
            "name": "VCP",
            "type": "bullish",
            "confidence": 0.75,
            "details": f"수축률 {vcp['contraction_pct']:.1f}%"
        })

    # OBV 다이버전스
    obv_div = detect_obv_divergence(df)
    if obv_div['bullish_divergence']:
        patterns.append({
            "name": "OBV 상승 다이버전스",
            "type": "bullish",
            "confidence": 0.70,
            "details": "가격 하락 + OBV 상승"
        })
    if obv_div['bearish_divergence']:
        patterns.append({
            "name": "OBV 하락 다이버전스",
            "type": "bearish",
            "confidence": 0.65,
            "details": "가격 상승 + OBV 하락"
        })

    # 이평선 상태
    ma_status = check_ma_status(df)
    if ma_status['status'] == 'aligned':
        patterns.append({
            "name": "정배열",
            "type": "bullish",
            "confidence": 0.55,
            "details": "상승 추세"
        })
    elif ma_status['status'] == 'reverse_aligned':
        patterns.append({
            "name": "역배열",
            "type": "bearish",
            "confidence": 0.80,
            "details": "하락 추세"
        })

    # 눌림목
    high_20d = df['High'].tail(20).max()
    pullback_pct = (high_20d - curr['Close']) / high_20d * 100
    if 5 <= pullback_pct <= 15 and ma_status['status'] == 'aligned':
        patterns.append({
            "name": "눌림목",
            "type": "bullish",
            "confidence": 0.60,
            "details": f"고점 대비 {pullback_pct:.1f}% 조정"
        })

    bullish = [p for p in patterns if p['type'] == 'bullish']
    bearish = [p for p in patterns if p['type'] == 'bearish']

    return {
        "agent": "PatternAgent",
        "stock_code": ticker,
        "stock_name": name,
        "analyzed_at": datetime.now().isoformat(),
        "patterns": patterns,
        "summary": {
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "dominant_signal": "BULLISH" if len(bullish) > len(bearish) else "BEARISH" if len(bearish) > len(bullish) else "NEUTRAL"
        }
    }


def run_signal_agent(ticker: str) -> dict:
    """SignalAgent 실행"""
    from pykrx import stock
    from scoring import calculate_score
    from scoring.indicators import (
        calculate_base_indicators,
        check_ma_status,
        check_rsi_status,
        check_volume_status,
        detect_obv_divergence,
        detect_vcp_pattern
    )

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=120)
    df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)

    if df is None or len(df) < 20:
        return {"error": "데이터 부족", "stock_code": ticker}

    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})
    df = calculate_base_indicators(df)

    # 스코어 계산
    score_result = calculate_score(df, 'v2')
    v2_score = score_result.get('score', 0)

    # 기술적 상태
    ma_status = check_ma_status(df)
    rsi_status = check_rsi_status(df)
    vol_status = check_volume_status(df)
    obv_div = detect_obv_divergence(df)
    vcp = detect_vcp_pattern(df)

    curr = df.iloc[-1]

    # 기술적 점수 (30%)
    tech_score = 50
    if ma_status['status'] == 'aligned':
        tech_score += 15
    elif ma_status['status'] == 'reverse_aligned':
        tech_score -= 30

    rsi = rsi_status.get('rsi', 50)
    if 40 <= rsi <= 70:
        tech_score += 10
    elif rsi < 30:
        tech_score += 5
    elif rsi > 80:
        tech_score -= 15

    if curr.get('MACDh', 0) > 0:
        tech_score += 10

    slope = ma_status.get('sma20_slope', 0)
    if slope > 1:
        tech_score += 10
    elif slope < -2:
        tech_score -= 15

    tech_score = max(0, min(100, tech_score))

    # 수급 점수 (20%)
    supply_score = 50
    vol_level = vol_status.get('level', 'normal')
    if vol_level == 'explosion':
        supply_score += 25
    elif vol_level == 'surge':
        supply_score += 15
    elif vol_level == 'high':
        supply_score += 10
    elif vol_level == 'low':
        supply_score -= 10

    if obv_div.get('bullish_divergence'):
        supply_score += 15
    elif obv_div.get('bearish_divergence'):
        supply_score -= 15

    supply_score = max(0, min(100, supply_score))

    # 패턴 점수 (15%)
    pattern_score = 50
    if vcp.get('detected'):
        pattern_score += 25
    pattern_score = max(0, min(100, pattern_score))

    # 종합 신호 계산
    total_signal = (
        v2_score * 0.35 +
        tech_score * 0.30 +
        supply_score * 0.20 +
        pattern_score * 0.15
    )

    # 과락 체크
    knockout = None
    if v2_score == 0:
        knockout = "역배열 (V2=0)"
    elif rsi > 85:
        knockout = f"극단적 과매수 (RSI={rsi:.0f})"
    elif slope < -3:
        knockout = f"급락 추세 (기울기={slope:.1f}%)"

    # 신호 결정
    if knockout:
        decision = "SELL"
        confidence = 0.9
    elif total_signal >= 80:
        decision = "STRONG_BUY"
        confidence = 0.85
    elif total_signal >= 65:
        decision = "BUY"
        confidence = 0.70
    elif total_signal >= 50:
        decision = "HOLD"
        confidence = 0.55
    elif total_signal >= 35:
        decision = "WEAK_SELL"
        confidence = 0.60
    else:
        decision = "SELL"
        confidence = 0.75

    return {
        "agent": "SignalAgent",
        "stock_code": ticker,
        "stock_name": name,
        "generated_at": datetime.now().isoformat(),
        "analysis": {
            "scoring": {"v2_score": v2_score, "weight": 0.35},
            "technical": {"score": tech_score, "weight": 0.30},
            "supply_demand": {"score": supply_score, "weight": 0.20},
            "pattern": {"score": pattern_score, "weight": 0.15}
        },
        "signal": {
            "total_score": round(total_signal, 1),
            "decision": decision,
            "confidence": confidence,
            "knockout": knockout
        }
    }


def run_risk_agent(ticker: str) -> dict:
    """RiskAgent 실행"""
    import numpy as np
    from pykrx import stock
    from scoring.indicators import calculate_base_indicators

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=90)
    df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)

    if df is None or len(df) < 20:
        return {"error": "데이터 부족", "stock_code": ticker}

    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue'})
    if 'TradingValue' not in df.columns:
        df['TradingValue'] = df['Close'] * df['Volume']

    df = calculate_base_indicators(df)
    curr = df.iloc[-1]

    # 변동성
    volatility_20d = df['Close'].tail(20).pct_change().std() * np.sqrt(252) * 100

    # MDD
    rolling_max = df['Close'].tail(60).cummax()
    drawdown = (df['Close'].tail(60) - rolling_max) / rolling_max * 100
    mdd = drawdown.min()

    # 유동성
    avg_trading_value = df['TradingValue'].tail(20).mean() / 1e8

    # 기술적 리스크
    rsi = curr.get('RSI', 50)
    tech_risk = 0
    if rsi > 75:
        tech_risk += 2
    if curr.get('BB_POSITION', 0.5) > 0.9:
        tech_risk += 2
    if curr.get('MA_REVERSE_ALIGNED', False):
        tech_risk += 3

    # 종합 리스크 점수
    risk_score = 50
    risk_score += min(20, volatility_20d / 2)
    risk_score += min(15, abs(mdd) / 2)
    risk_score -= min(15, avg_trading_value / 100)
    risk_score += tech_risk * 5
    risk_score = max(0, min(100, risk_score))

    risk_level = "CRITICAL" if risk_score > 75 else "HIGH" if risk_score > 60 else "MEDIUM" if risk_score > 40 else "LOW"

    # 손절가
    curr_price = curr['Close']
    atr = curr.get('ATR', curr_price * 0.02)

    return {
        "agent": "RiskAgent",
        "stock_code": ticker,
        "stock_name": name,
        "analyzed_at": datetime.now().isoformat(),
        "risk_metrics": {
            "volatility_20d": round(volatility_20d, 1),
            "mdd_60d": round(mdd, 1),
            "avg_trading_value_억": round(avg_trading_value, 0),
            "liquidity_risk": "LOW" if avg_trading_value > 500 else "MEDIUM" if avg_trading_value > 100 else "HIGH"
        },
        "risk_score": int(risk_score),
        "risk_level": risk_level,
        "stop_loss": {
            "recommended": int(curr_price * 0.97),
            "recommended_pct": -3.0,
            "atr_based": int(curr_price - 2 * atr)
        }
    }


def run_macro_agent() -> dict:
    """MacroAgent 실행"""
    from trading.nasdaq_monitor import get_nasdaq_previous_change, get_adjusted_investment_amount

    nasdaq_change, nasdaq_date = get_nasdaq_previous_change()
    nasdaq_change = float(nasdaq_change)

    adjusted, multiplier, _ = get_adjusted_investment_amount(200000)

    # 리스크 평가
    if nasdaq_change < -3:
        risk_level = "HIGH"
        action = "REDUCE"
    elif nasdaq_change < -2:
        risk_level = "ELEVATED"
        action = "CAUTIOUS"
    elif nasdaq_change < -1:
        risk_level = "MODERATE"
        action = "CAUTIOUS"
    elif nasdaq_change > 1:
        risk_level = "LOW"
        action = "AGGRESSIVE"
    else:
        risk_level = "NORMAL"
        action = "NORMAL"

    return {
        "agent": "MacroAgent",
        "analyzed_at": datetime.now().isoformat(),
        "us_market": {
            "nasdaq_change_pct": nasdaq_change,
            "nasdaq_date": nasdaq_date
        },
        "investment_adjustment": {
            "multiplier": multiplier,
            "base_amount": 200000,
            "adjusted_amount": adjusted
        },
        "risk_assessment": {
            "risk_level": risk_level,
            "action": action
        }
    }


def run_investor_agent(ticker: str) -> dict:
    """InvestorFlowAgent 실행 - 수급 분석"""
    from pykrx import stock

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=45)

    try:
        df = stock.get_market_trading_value_by_date(
            start.strftime('%Y%m%d'),
            end.strftime('%Y%m%d'),
            ticker
        )

        if df is None or len(df) == 0:
            return {"error": "수급 데이터 없음", "stock_code": ticker, "agent": "InvestorFlowAgent"}

        df = df.rename(columns={
            '기관합계': 'inst',
            '외국인합계': 'foreign',
            '개인': 'individual'
        })

        # 기간별 누적
        cumulative = {}
        for days in [5, 10, 20]:
            period = df.tail(days)
            cumulative[f"{days}d"] = {
                "foreign_억": round(period['foreign'].sum() / 1e8, 0),
                "inst_억": round(period['inst'].sum() / 1e8, 0),
                "individual_억": round(period['individual'].sum() / 1e8, 0)
            }

        # 연속 매수일
        foreign_consec = 0
        for val in df['foreign'].iloc[::-1]:
            if val > 0:
                foreign_consec += 1
            else:
                break

        inst_consec = 0
        for val in df['inst'].iloc[::-1]:
            if val > 0:
                inst_consec += 1
            else:
                break

        # 수급 점수
        score = 50
        f_20d = df.tail(20)['foreign'].sum()
        i_20d = df.tail(20)['inst'].sum()

        if f_20d > 0:
            score += 15 if f_20d > 100_000_000_000 else 10
        else:
            score -= 10

        if i_20d > 0:
            score += 15 if i_20d > 50_000_000_000 else 10
        else:
            score -= 5

        if foreign_consec >= 5:
            score += 10
        if inst_consec >= 5:
            score += 10

        return {
            "agent": "InvestorFlowAgent",
            "stock_code": ticker,
            "stock_name": name,
            "analyzed_at": datetime.now().isoformat(),
            "cumulative": cumulative,
            "consecutive_buy_days": {
                "foreign": foreign_consec,
                "inst": inst_consec
            },
            "supply_score": score,
            "interpretation": "강한 매집" if score >= 70 else "약한 매집" if score >= 55 else "중립" if score >= 45 else "매도 우세"
        }

    except Exception as e:
        return {"error": str(e), "stock_code": ticker, "agent": "InvestorFlowAgent"}


def run_monitor_agent(tickers: list, avg_prices: dict = None) -> dict:
    """MonitorAgent 실행 - 보유종목 모니터링"""
    from pykrx import stock
    from scoring import calculate_score

    if avg_prices is None:
        avg_prices = {}

    end = datetime.now()
    start = end - timedelta(days=90)

    holdings_status = []
    alerts = []

    for ticker in tickers:
        try:
            name = stock.get_market_ticker_name(ticker)
            df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
            df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})

            curr = df.iloc[-1]
            prev = df.iloc[-2]
            current_price = curr['Close']
            change_pct = (current_price / prev['Close'] - 1) * 100

            avg = avg_prices.get(ticker, current_price)
            profit_pct = (current_price / avg - 1) * 100

            # V2 스코어
            result = calculate_score(df, 'v2')
            v2 = result.get('score', 0)

            # 상태 판정
            if profit_pct <= -5:
                status = "DANGER"
                alerts.append({"type": "STOP_LOSS", "stock": name, "code": ticker, "profit_pct": profit_pct})
            elif profit_pct <= -3:
                status = "WARNING"
                alerts.append({"type": "WARNING", "stock": name, "code": ticker, "profit_pct": profit_pct})
            elif v2 == 0:
                status = "DANGER"
                alerts.append({"type": "V2_ZERO", "stock": name, "code": ticker, "v2": v2})
            elif profit_pct >= 10:
                status = "TAKE_PROFIT"
                alerts.append({"type": "TAKE_PROFIT", "stock": name, "code": ticker, "profit_pct": profit_pct})
            elif profit_pct >= 5:
                status = "HEALTHY"
            else:
                status = "NORMAL"

            holdings_status.append({
                "code": ticker,
                "name": name,
                "current_price": int(current_price),
                "avg_price": int(avg),
                "change_pct": round(change_pct, 2),
                "profit_pct": round(profit_pct, 2),
                "v2_score": v2,
                "status": status
            })

        except Exception as e:
            holdings_status.append({
                "code": ticker,
                "error": str(e)
            })

    return {
        "agent": "MonitorAgent",
        "monitored_at": datetime.now().isoformat(),
        "holdings_count": len(tickers),
        "holdings": holdings_status,
        "alerts": alerts,
        "summary": {
            "danger": len([h for h in holdings_status if h.get('status') == 'DANGER']),
            "warning": len([h for h in holdings_status if h.get('status') == 'WARNING']),
            "healthy": len([h for h in holdings_status if h.get('status') in ['HEALTHY', 'NORMAL']]),
            "alerts_count": len(alerts)
        }
    }


def run_report_agent(ticker: str) -> dict:
    """ReportAgent 실행 - 종목 분석 리포트 생성"""
    from pykrx import stock
    from scoring import compare_scores
    from scoring.indicators import (
        calculate_base_indicators,
        check_ma_status,
        check_rsi_status,
        check_volume_status
    )

    name = stock.get_market_ticker_name(ticker)

    end = datetime.now()
    start = end - timedelta(days=120)
    df = stock.get_market_ohlcv(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume', '거래대금': 'TradingValue'})

    if 'TradingValue' not in df.columns:
        df['TradingValue'] = df['Close'] * df['Volume']

    df = calculate_base_indicators(df)

    scores = compare_scores(df)
    ma_status = check_ma_status(df)
    rsi_status = check_rsi_status(df)
    vol_status = check_volume_status(df)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 52주 고저
    high_52w = df['High'].max()
    low_52w = df['Low'].min()

    return {
        "agent": "ReportAgent",
        "generated_at": datetime.now().isoformat(),
        "stock_info": {
            "code": ticker,
            "name": name,
            "market": "KOSPI" if ticker[0] == '0' else "KOSDAQ"
        },
        "price": {
            "current": int(curr['Close']),
            "open": int(curr['Open']),
            "high": int(curr['High']),
            "low": int(curr['Low']),
            "change_pct": round((curr['Close']/prev['Close']-1)*100, 2),
            "high_52w": int(high_52w),
            "low_52w": int(low_52w),
            "position_52w": round((curr['Close'] - low_52w) / (high_52w - low_52w) * 100, 1) if high_52w != low_52w else 50
        },
        "scores": {v: s['score'] for v, s in scores.items()},
        "technical": {
            "ma_status": ma_status['status'],
            "sma20_slope": round(ma_status.get('sma20_slope', 0), 2),
            "distance_to_sma20": round(ma_status.get('distance_to_sma20', 0), 2),
            "rsi": round(rsi_status.get('rsi', 50), 1),
            "rsi_zone": rsi_status.get('zone'),
            "vol_ratio": round(vol_status.get('vol_ratio', 1), 2),
            "vol_level": vol_status.get('level'),
            "trading_value_억": round(vol_status.get('trading_value_억', 0), 1)
        },
        "recommendation": "BUY" if scores.get('v2', {}).get('score', 0) >= 65 else "HOLD" if scores.get('v2', {}).get('score', 0) >= 50 else "SELL"
    }


def run_full_analysis(ticker: str) -> dict:
    """종합 분석 (오케스트레이터)"""
    results = {
        "stock_code": ticker,
        "analyzed_at": datetime.now().isoformat(),
        "agents": {}
    }

    # 1. Scoring
    results["agents"]["scoring"] = run_scoring_agent(ticker)

    # 2. Technical
    results["agents"]["technical"] = run_technical_agent(ticker)

    # 3. Pattern
    results["agents"]["pattern"] = run_pattern_agent(ticker)

    # 4. Signal
    results["agents"]["signal"] = run_signal_agent(ticker)

    # 5. Risk
    results["agents"]["risk"] = run_risk_agent(ticker)

    # 6. Macro
    results["agents"]["macro"] = run_macro_agent()

    # 종합 요약
    signal = results["agents"]["signal"].get("signal", {})
    results["summary"] = {
        "decision": signal.get("decision", "UNKNOWN"),
        "confidence": signal.get("confidence", 0),
        "v2_score": results["agents"]["scoring"].get("scores", {}).get("v2", 0),
        "risk_level": results["agents"]["risk"].get("risk_level", "UNKNOWN"),
        "market_condition": results["agents"]["macro"].get("risk_assessment", {}).get("risk_level", "UNKNOWN")
    }

    return results


def main():
    parser = argparse.ArgumentParser(description="주식 분석 에이전트 CLI")
    parser.add_argument("agent", choices=[
        "scoring", "technical", "pattern", "signal", "risk", "macro",
        "investor", "monitor", "report", "analyze"
    ], help="실행할 에이전트")
    parser.add_argument("ticker", nargs="?", help="종목코드 (6자리) 또는 쉼표로 구분된 종목코드들")
    parser.add_argument("--version", "-v", default="all", help="스코어 버전 (scoring 에이전트용)")
    parser.add_argument("--full", action="store_true", help="전체 분석 (analyze용)")
    parser.add_argument("--pretty", "-p", action="store_true", help="JSON 포맷팅")

    args = parser.parse_args()

    # 에이전트 실행
    if args.agent == "scoring":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_scoring_agent(args.ticker, args.version)

    elif args.agent == "technical":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_technical_agent(args.ticker)

    elif args.agent == "pattern":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_pattern_agent(args.ticker)

    elif args.agent == "signal":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_signal_agent(args.ticker)

    elif args.agent == "risk":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_risk_agent(args.ticker)

    elif args.agent == "macro":
        result = run_macro_agent()

    elif args.agent == "investor":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_investor_agent(args.ticker)

    elif args.agent == "monitor":
        if not args.ticker:
            print("종목코드가 필요합니다 (쉼표로 구분)", file=sys.stderr)
            sys.exit(1)
        tickers = [t.strip() for t in args.ticker.split(',')]
        result = run_monitor_agent(tickers)

    elif args.agent == "report":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_report_agent(args.ticker)

    elif args.agent == "analyze":
        if not args.ticker:
            print("종목코드가 필요합니다", file=sys.stderr)
            sys.exit(1)
        result = run_full_analysis(args.ticker)

    else:
        print(f"알 수 없는 에이전트: {args.agent}", file=sys.stderr)
        sys.exit(1)

    # 출력
    if args.pretty:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
