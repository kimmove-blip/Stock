#!/usr/bin/env python3
"""
장중 스크리닝 상세 디버그 리포트
- 10분마다 실행하여 푸시알림으로 리포트 전송
- 왜 샀는지, 왜 안 샀는지, 왜 팔았는지 상세 분석
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import OUTPUT_DIR, ScreeningConfig
from market_screener import MarketScreener
from trading.trade_logger import TradeLogger
from api.routers.push import send_push_to_user
from database.db_manager import DatabaseManager


def get_account_balance(user_id: int):
    """계좌 잔고 조회"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return None

    return logger.get_real_account_balance(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=bool(api_key_data.get('is_mock', True))
    )


def get_user_settings(user_id: int):
    """사용자 자동매매 설정 조회"""
    import sqlite3
    conn = sqlite3.connect('/home/kimhc/Stock/database/auto_trade.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM auto_trade_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def get_prev_scores():
    """이전 스크리닝 점수 로드"""
    prev_scores = {}
    try:
        # 장중 스크리닝 파일에서 로드
        intraday_files = sorted(OUTPUT_DIR.glob("intraday_*.json"), reverse=True)
        if len(intraday_files) >= 1:
            with open(intraday_files[0], 'r', encoding='utf-8') as f:
                prev_data = json.load(f)
                for s in prev_data.get("stocks", []):
                    prev_scores[s.get("code")] = s.get("score", 0)
    except Exception as e:
        print(f"이전 스크리닝 로드 실패: {e}")

    # 오늘 JSON에서도 로드
    try:
        today_str = datetime.now().strftime('%Y%m%d')
        json_path = OUTPUT_DIR / f"top100_{today_str}.json"
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_scores = data.get('screening_stats', {}).get('all_scores', {})
                for code, score in all_scores.items():
                    if code not in prev_scores:
                        prev_scores[code] = score
    except:
        pass

    return prev_scores


def get_today_traded_stocks(user_id: int):
    """오늘 거래한 종목 목록"""
    logger = TradeLogger()
    return logger.get_today_traded_stocks(user_id)


def run_debug_report(user_id: int = 7, send_push: bool = True):
    """상세 디버그 리포트 생성 및 전송"""
    now = datetime.now()
    report_lines = []
    report_lines.append(f"=== 장중 스크리닝 리포트 ===")
    report_lines.append(f"시간: {now.strftime('%H:%M:%S')}")
    report_lines.append("")

    # 1. 장 시간 체크
    market_open = now.replace(hour=9, minute=0, second=0)
    market_close = now.replace(hour=15, minute=20, second=0)

    if now < market_open or now > market_close:
        report_lines.append("장 운영 시간 외 (09:00~15:20)")
        report = "\n".join(report_lines)
        print(report)
        if send_push:
            send_push_to_user(user_id, "장중 리포트", report[:500])
        return

    # 2. 사용자 설정 확인
    settings = get_user_settings(user_id)
    min_buy_score = settings.get('min_buy_score', 80)
    max_holdings = settings.get('max_holdings', 20)
    trading_enabled = settings.get('trading_enabled', 1)

    report_lines.append(f"[설정] 매수기준: {min_buy_score}점, 최대보유: {max_holdings}개")
    report_lines.append(f"[설정] 거래활성화: {'O' if trading_enabled else 'X'}")

    if not trading_enabled:
        report_lines.append("\n거래가 비활성화되어 있습니다!")
        report = "\n".join(report_lines)
        print(report)
        if send_push:
            send_push_to_user(user_id, "장중 리포트", report[:500])
        return

    # 3. 계좌 잔고 조회
    balance = get_account_balance(user_id)
    if not balance:
        report_lines.append("\n계좌 조회 실패!")
        report = "\n".join(report_lines)
        print(report)
        if send_push:
            send_push_to_user(user_id, "장중 리포트", report[:500])
        return

    all_holdings = balance.get("holdings", [])
    holdings = [h for h in all_holdings if h.get("quantity", 0) > 0]
    summary = balance.get("summary", {})
    d2_cash = summary.get("d2_cash_balance", 0) or summary.get("cash_balance", 0)
    max_buy_amt = summary.get("max_buy_amt", 0) or d2_cash

    report_lines.append(f"[계좌] 예수금: {d2_cash:,}원, 주문가능: {max_buy_amt:,}원")
    report_lines.append(f"[계좌] 보유종목: {len(holdings)}/{max_holdings}개")
    report_lines.append("")

    # 4. 보유 종목 매도 진단
    sell_score = settings.get('sell_score', 40)
    stop_loss = settings.get('stop_loss_rate', -10)

    if holdings:
        report_lines.append("=== 보유 종목 매도 진단 ===")
        report_lines.append(f"[기준] 매도점수: {sell_score}점 미만, 손절: {stop_loss}%")
        report_lines.append("")

        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()

        for h in holdings:
            code = h.get('stock_code')
            name = h.get('stock_name', code)
            qty = h.get('quantity', 0)
            profit_rate = h.get('profit_rate', 0)
            current_price = h.get('current_price', 0)

            # 점수 및 20일선 조회
            try:
                df = analyst.get_ohlcv(code, days=120)
                if df is not None and len(df) >= 60:
                    result = analyst.analyze_trend_following_strict(df)
                    score = result.get("score", 50) if result else 50
                    signals = result.get("signals", []) if result else []
                    sma20 = float(df['Close'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 0
                else:
                    score = 50
                    signals = []
                    sma20 = 0
            except Exception as e:
                print(f"    점수 조회 오류 ({code}): {e}")
                score = 50
                signals = []
                sma20 = 0

            # 매도 조건 체크
            sell_reasons = []
            should_sell = False

            if score < sell_score:
                sell_reasons.append(f"점수{score}<{sell_score}")
                should_sell = True

            if sma20 > 0 and current_price > 0 and current_price < sma20:
                sell_reasons.append(f"20일선이탈({current_price:,}<{int(sma20):,})")
                should_sell = True

            if profit_rate <= stop_loss:
                sell_reasons.append(f"손절({profit_rate:.1f}%<={stop_loss}%)")
                should_sell = True

            # 결과 출력
            status = "⚠️ 매도필요" if should_sell else "✓ 보유유지"
            reason_str = ", ".join(sell_reasons) if sell_reasons else f"점수{score}점, 수익{profit_rate:+.1f}%"
            report_lines.append(f"  {name}: {status}")
            report_lines.append(f"    └ {reason_str}")

        report_lines.append("")

    # 5. 전종목 스크리닝
    print("전종목 스크리닝 중...")
    screener = MarketScreener(max_workers=ScreeningConfig.MAX_WORKERS)
    top_stocks, stats = screener.run_full_screening(
        top_n=ScreeningConfig.TOP_N,
        mode="strict",
        min_marcap=ScreeningConfig.MIN_MARKET_CAP,
        max_marcap=ScreeningConfig.MAX_MARKET_CAP,
        min_amount=ScreeningConfig.MIN_TRADING_AMOUNT,
    )

    if not top_stocks:
        report_lines.append("스크리닝 결과 없음")
        report = "\n".join(report_lines)
        print(report)
        if send_push:
            send_push_to_user(user_id, "장중 리포트", report[:500])
        return

    # 6. 시간대별 거래량 보정
    hour = now.hour
    if hour < 10:
        volume_multiplier = 4.0
    elif hour < 11:
        volume_multiplier = 2.5
    elif hour < 14:
        volume_multiplier = 1.5
    else:
        volume_multiplier = 1.0

    report_lines.append(f"[스크리닝] 총 {len(top_stocks)}종목, 거래량보정: x{volume_multiplier}")
    report_lines.append("")

    # 7. 이전 점수 로드
    prev_scores = get_prev_scores()

    # 8. 당일 거래 종목 (블랙리스트)
    today_traded = get_today_traded_stocks(user_id)
    holding_codes = {h.get("stock_code") for h in holdings}
    remaining_slots = max_holdings - len(holdings)

    # 9. 80점 이상 종목 분석
    stocks_80plus = [s for s in top_stocks if s.get("score", 0) >= 80]
    stocks_75to79 = [s for s in top_stocks if 75 <= s.get("score", 0) < 80]

    report_lines.append(f"=== 80점 이상: {len(stocks_80plus)}종목 ===")

    buy_candidates = []
    for stock in stocks_80plus[:10]:  # 최대 10개 분석
        code = stock.get("code")
        name = stock.get("name")
        score = stock.get("score", 0)
        volume_ratio = stock.get("indicators", {}).get("volume_ratio", 1.0)
        adjusted_volume = volume_ratio * volume_multiplier
        change_pct = stock.get("change_pct", 0)

        reasons = []
        can_buy = True

        # 거래량 체크
        if adjusted_volume < 1.5:
            reasons.append(f"거래량부족({volume_ratio:.1f}x{volume_multiplier}={adjusted_volume:.1f}<1.5)")
            can_buy = False

        # 이미 보유 중
        if code in holding_codes:
            reasons.append("이미보유")
            can_buy = False

        # 당일 거래 이력
        if code in today_traded:
            reasons.append("당일거래(왕복방지)")
            can_buy = False

        # 슬롯 부족
        if remaining_slots <= 0:
            reasons.append("슬롯없음")
            can_buy = False

        # 상한가 체크
        if change_pct >= 29:
            reasons.append(f"상한가근접({change_pct:+.1f}%)")
            can_buy = False

        # 예수금 부족
        price = int(stock.get("close", 0))
        if price > 0 and max_buy_amt < price:
            reasons.append(f"예수금부족")
            can_buy = False

        if can_buy:
            buy_candidates.append(stock)
            status = "매수가능"
        else:
            status = ", ".join(reasons)

        report_lines.append(f"  {name}({code}): {score}점 -> {status}")

    if not stocks_80plus:
        report_lines.append("  (없음)")
    report_lines.append("")

    # 10. 75~79점 종목 분석 (연속성 체크)
    report_lines.append(f"=== 75~79점: {len(stocks_75to79)}종목 ===")

    for stock in stocks_75to79[:10]:
        code = stock.get("code")
        name = stock.get("name")
        score = stock.get("score", 0)
        prev_score = prev_scores.get(code, 0)
        volume_ratio = stock.get("indicators", {}).get("volume_ratio", 1.0)
        adjusted_volume = volume_ratio * volume_multiplier
        change_pct = stock.get("change_pct", 0)

        reasons = []
        can_buy = True

        # 연속성 체크
        if prev_score < 75:
            reasons.append(f"연속성부족(이전{prev_score}점)")
            can_buy = False

        # 거래량 체크
        if adjusted_volume < 1.5:
            reasons.append(f"거래량부족({adjusted_volume:.1f})")
            can_buy = False

        # 이미 보유 중
        if code in holding_codes:
            reasons.append("이미보유")
            can_buy = False

        # 당일 거래 이력
        if code in today_traded:
            reasons.append("당일거래")
            can_buy = False

        # 상한가 체크
        if change_pct >= 29:
            reasons.append(f"상한가({change_pct:+.1f}%)")
            can_buy = False

        if can_buy and min_buy_score <= 75:
            buy_candidates.append(stock)
            status = f"매수가능(이전{prev_score}점)"
        elif can_buy:
            status = f"점수미달(설정{min_buy_score}점)"
        else:
            status = ", ".join(reasons)

        report_lines.append(f"  {name}: {score}점(이전{prev_score}점) -> {status}")

    if not stocks_75to79:
        report_lines.append("  (없음)")
    report_lines.append("")

    # 11. 최종 요약
    report_lines.append("=== 최종 요약 ===")
    report_lines.append(f"매수가능 후보: {len(buy_candidates)}종목")
    report_lines.append(f"남은 슬롯: {remaining_slots}개")
    report_lines.append(f"주문가능금액: {max_buy_amt:,}원")

    if buy_candidates and remaining_slots > 0:
        report_lines.append("")
        report_lines.append("[매수 예정]")
        for c in buy_candidates[:remaining_slots]:
            name = c.get("name")
            score = c.get("score")
            report_lines.append(f"  {name}: {score}점")
    elif not buy_candidates:
        report_lines.append("\n매수 조건 충족 종목 없음")
    elif remaining_slots <= 0:
        report_lines.append("\n보유 슬롯이 가득 참")

    # 12. 리포트 출력 및 푸시 전송
    report = "\n".join(report_lines)
    print(report)

    if send_push:
        # 푸시는 500자 제한이므로 요약본 전송
        push_summary = []
        push_summary.append(f"[{now.strftime('%H:%M')}] 장중 스크리닝")
        push_summary.append(f"80+: {len(stocks_80plus)}종목 / 75~79: {len(stocks_75to79)}종목")
        push_summary.append(f"보유: {len(holdings)}/{max_holdings} / 예수금: {max_buy_amt:,}원")
        push_summary.append(f"매수가능: {len(buy_candidates)}종목")

        if buy_candidates:
            push_summary.append("")
            for c in buy_candidates[:3]:
                name = c.get("name")
                score = c.get("score")
                push_summary.append(f"  {name}: {score}점")
            if len(buy_candidates) > 3:
                push_summary.append(f"  외 {len(buy_candidates)-3}종목")

        push_text = "\n".join(push_summary)
        send_push_to_user(user_id, "장중 스크리닝 리포트", push_text)
        print(f"\n푸시 알림 전송 완료 (user_id={user_id})")

        # 알림 기록에도 저장 (시간별로 다른 코드 사용하여 중복 방지)
        try:
            db = DatabaseManager()
            time_code = f"REPORT_{now.strftime('%H%M')}"
            db.add_alert_history(
                user_id=user_id,
                stock_code=time_code,
                alert_type="장중리포트",
                message=report,
                stock_name="장중 스크리닝"
            )
            print("알림 기록 저장 완료")
        except Exception as e:
            print(f"알림 기록 저장 실패: {e}")

    # 13. JSON 파일로 상세 리포트 저장
    try:
        report_path = OUTPUT_DIR / f"intraday_report_{now.strftime('%Y%m%d_%H%M')}.json"
        report_data = {
            "timestamp": now.isoformat(),
            "user_id": user_id,
            "settings": {
                "min_buy_score": min_buy_score,
                "max_holdings": max_holdings,
            },
            "account": {
                "cash": d2_cash,
                "max_buy_amt": max_buy_amt,
                "holdings_count": len(holdings),
                "remaining_slots": remaining_slots,
            },
            "screening": {
                "total": len(top_stocks),
                "score_80plus": len(stocks_80plus),
                "score_75to79": len(stocks_75to79),
                "volume_multiplier": volume_multiplier,
            },
            "buy_candidates": [
                {"code": c.get("code"), "name": c.get("name"), "score": c.get("score")}
                for c in buy_candidates
            ],
            "stocks_80plus": [
                {"code": s.get("code"), "name": s.get("name"), "score": s.get("score"), "volume_ratio": s.get("indicators", {}).get("volume_ratio", 1.0)}
                for s in stocks_80plus[:20]
            ],
            "stocks_75to79": [
                {"code": s.get("code"), "name": s.get("name"), "score": s.get("score"), "prev_score": prev_scores.get(s.get("code"), 0)}
                for s in stocks_75to79[:20]
            ],
            "holdings": [
                {"code": h.get("stock_code"), "name": h.get("stock_name"), "profit_rate": h.get("profit_rate", 0)}
                for h in holdings
            ],
        }
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"리포트 저장: {report_path}")
    except Exception as e:
        print(f"리포트 저장 실패: {e}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="장중 스크리닝 디버그 리포트")
    parser.add_argument("--user-id", type=int, default=7, help="사용자 ID (기본: 7)")
    parser.add_argument("--no-push", action="store_true", help="푸시 알림 전송 안함")
    args = parser.parse_args()

    run_debug_report(user_id=args.user_id, send_push=not args.no_push)
