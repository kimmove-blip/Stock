#!/usr/bin/env python3
"""
매일 장마감 후 실행: 내일 관심 종목 100선

사용법:
    python daily_top100.py              # 기본 실행 (quick 모드)
    python daily_top100.py --full       # 전체 분석 모드
    python daily_top100.py --top 50     # 상위 50개만
    python daily_top100.py --email      # 실행 후 이메일 발송
    python daily_top100.py --schedule   # 스케줄러 모드 (18:00 자동 실행 + 이메일)
"""

import argparse
import json
import os
import sys
from datetime import datetime
import pandas as pd
import time

from market_screener import MarketScreener, SignalFilter, format_result_table
from config import (
    ScreeningConfig,
    OutputConfig,
    SignalCategories,
    OUTPUT_DIR,
    SIGNAL_NAMES_KR,
    get_signal_kr,
)
from email_sender import send_daily_report
from pdf_generator import generate_detailed_pdf
from result_tracker import update_with_next_day_results


def run_screening(mode="quick", top_n=100):
    """스크리닝 실행"""
    print("\n" + "=" * 70)
    print(f"  내일 관심 종목 {top_n}선 스크리닝")
    print(f"  실행시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  모드: {'전체 분석' if mode == 'full' else '빠른 스크리닝'}")
    print("=" * 70)

    # 스크리너 초기화
    screener = MarketScreener(max_workers=ScreeningConfig.MAX_WORKERS)

    # 스크리닝 실행
    results = screener.run_full_screening(
        top_n=top_n * 2,  # 필터링 여유분
        mode=mode,
        min_marcap=ScreeningConfig.MIN_MARKET_CAP,
        min_amount=ScreeningConfig.MIN_TRADING_AMOUNT,
    )

    return results


def categorize_results(results):
    """결과 분류 (강력매수 / 매수 / 관심)"""
    categorized = {"strong_buy": [], "buy": [], "watch": []}

    for r in results:
        signals = r.get("signals", [])

        # 강력 매수: 강력 신호 포함 + 주의 신호 없음
        has_strong = any(s in signals for s in SignalCategories.STRONG_BUY)
        has_caution = any(s in signals for s in SignalCategories.CAUTION)

        if has_strong and not has_caution:
            categorized["strong_buy"].append(r)
        elif not has_caution and r["score"] >= 50:
            categorized["buy"].append(r)
        else:
            categorized["watch"].append(r)

    return categorized


def save_results(results, top_n=100):
    """결과 저장 (Excel, JSON, CSV, PDF)"""
    print("\n[저장] 결과 파일 생성 중...")

    # 상위 N개만 추출
    top_results = results[:top_n]

    # 1. Excel 저장
    excel_path = OutputConfig.get_filepath("excel")
    df = create_dataframe(top_results)
    df.to_excel(excel_path, index=False, engine="openpyxl")
    print(f"    → Excel: {excel_path}")

    # 2. JSON 저장
    json_path = OutputConfig.get_filepath("json")
    save_json(top_results, json_path)
    print(f"    → JSON: {json_path}")

    # 3. CSV 저장
    csv_path = OutputConfig.get_filepath("csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"    → CSV: {csv_path}")

    # 4. PDF 저장
    pdf_path = OutputConfig.get_filepath("pdf")
    generate_detailed_pdf(top_results, pdf_path)
    print(f"    → PDF: {pdf_path}")

    return excel_path, json_path, csv_path


def create_dataframe(results):
    """결과를 DataFrame으로 변환"""
    rows = []

    for i, r in enumerate(results, 1):
        signals = r.get("signals", [])
        patterns = r.get("patterns", [])
        indicators = r.get("indicators", {})

        # 신호를 한글로 변환
        safe_signals = signals or []
        signals_kr = [get_signal_kr(s) for s in safe_signals[:5]]  # 상위 5개

        # 목표가 계산 (점수 기반)
        score = r["score"]
        close_price = int(r.get("close", 0))
        if score >= 80:
            target_mul = 1.20
        elif score >= 60:
            target_mul = 1.10
        elif score >= 40:
            target_mul = 1.05
        else:
            target_mul = 1.0
        target_price = int(close_price * target_mul)

        row = {
            "순위": i,
            "종목코드": r["code"],
            "종목명": r["name"],
            "시장": r["market"],
            "종합점수": r["score"],
            "현재가": close_price,
            "목표가": target_price,
            "기대수익률(%)": round((target_mul - 1) * 100, 1),
            "등락률(%)": round(r.get("change_pct", 0), 2),
            "거래량": int(r.get("volume", 0)),
            "주요신호": " | ".join(signals_kr),
            "캔들패턴": " | ".join(patterns) if patterns else "-",
        }

        # 주요 지표 추가 (full 모드일 때)
        if indicators:
            row["RSI"] = (
                round(indicators.get("rsi", 0), 1) if indicators.get("rsi") else "-"
            )
            row["MACD"] = (
                round(indicators.get("macd", 0), 2) if indicators.get("macd") else "-"
            )
            row["ADX"] = (
                round(indicators.get("adx", 0), 1) if indicators.get("adx") else "-"
            )
            row["MFI"] = (
                round(indicators.get("mfi", 0), 1) if indicators.get("mfi") else "-"
            )
            row["거래량배율"] = (
                round(indicators.get("volume_ratio", 0), 2)
                if indicators.get("volume_ratio")
                else "-"
            )

        rows.append(row)

    return pd.DataFrame(rows)


def save_json(results, filepath):
    """JSON 형식으로 저장"""
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_count": len(results),
        "stocks": [],
    }

    for r in results:
        # 목표가 계산
        score = r["score"]
        close_price = r.get("close", 0)
        if score >= 80:
            target_mul = 1.20
        elif score >= 60:
            target_mul = 1.10
        elif score >= 40:
            target_mul = 1.05
        else:
            target_mul = 1.0
        target_price = int(close_price * target_mul)

        stock = {
            "code": r["code"],
            "name": r["name"],
            "market": r["market"],
            "score": r["score"],
            "close": r.get("close", 0),
            "target_price": target_price,
            "expected_return": round((target_mul - 1) * 100, 1),
            "change_pct": round(r.get("change_pct", 0), 2),
            "volume": r.get("volume", 0),
            "signals": r.get("signals", []),
            "patterns": r.get("patterns", []),
        }

        # 지표 추가
        if "indicators" in r:
            stock["indicators"] = {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in r["indicators"].items()
            }

        output["stocks"].append(stock)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def print_summary(results, categorized):
    """결과 요약 출력"""
    print("\n" + "=" * 70)
    print("  스크리닝 결과 요약")
    print("=" * 70)

    print(f"\n  총 분석 종목: {len(results):,}개")
    print(f"  - 강력 매수: {len(categorized['strong_buy'])}개")
    print(f"  - 매수 관심: {len(categorized['buy'])}개")
    print(f"  - 일반 관심: {len(categorized['watch'])}개")

    # 강력 매수 종목 출력
    if categorized["strong_buy"]:
        print("\n" + "-" * 70)
        print("  [강력 매수 후보]")
        print("-" * 70)
        for r in categorized["strong_buy"][:10]:
            signals = [get_signal_kr(s) for s in r.get("signals", [])[:3]]
            print(
                f"  {r['code']} {r['name']:<12} 점수:{r['score']:>3} | {', '.join(signals)}"
            )

    # 상위 20개 종목 테이블
    print("\n")
    format_result_table(results, max_rows=20)


def run_with_schedule(send_email=True):
    """스케줄러 모드: 지정된 시간에 자동 실행"""
    from config import ScheduleConfig
    import schedule

    def job():
        print(f"\n[스케줄] 자동 실행 시작: {datetime.now()}")

        # 전날 결과 추적
        print("\n[1단계] 전날 선정 종목 실적 추적")
        update_with_next_day_results()

        # 스크리닝 실행
        print("\n[2단계] 오늘의 스크리닝 실행")
        results = run_screening(mode=ScreeningConfig.MODE, top_n=ScreeningConfig.TOP_N)

        if not results:
            print("[스케줄] 스크리닝 결과 없음")
            return

        categorized = categorize_results(results)
        save_results(results, top_n=ScreeningConfig.TOP_N)
        print_summary(results, categorized)

        # 이메일 발송
        if send_email:
            pdf_path = OutputConfig.get_filepath("pdf")
            send_daily_report(results, pdf_path=pdf_path)

    # 스케줄 등록
    run_time = f"{ScheduleConfig.RUN_HOUR:02d}:{ScheduleConfig.RUN_MINUTE:02d}"
    schedule.every().monday.at(run_time).do(job)
    schedule.every().tuesday.at(run_time).do(job)
    schedule.every().wednesday.at(run_time).do(job)
    schedule.every().thursday.at(run_time).do(job)
    schedule.every().friday.at(run_time).do(job)

    if ScheduleConfig.RUN_ON_WEEKEND:
        schedule.every().saturday.at(run_time).do(job)
        schedule.every().sunday.at(run_time).do(job)

    print(f"[스케줄러] 매일 {run_time}에 자동 실행됩니다.")
    print(f"[스케줄러] 이메일 발송: {'활성화' if send_email else '비활성화'}")
    print("[스케줄러] Ctrl+C로 종료")

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="매일 장마감 후 관심 종목 100선 스크리닝",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python daily_top100.py              # 빠른 스크리닝 (기본)
  python daily_top100.py --full       # 전체 분석 (더 정확, 더 느림)
  python daily_top100.py --top 50     # 상위 50개만 선정
  python daily_top100.py --schedule   # 18:00 자동 실행 모드
        """,
    )

    parser.add_argument(
        "--full", action="store_true", help="전체 분석 모드 (더 많은 지표, 더 느림)"
    )
    parser.add_argument(
        "--top", type=int, default=100, help="선정할 종목 수 (기본: 100)"
    )
    parser.add_argument(
        "--schedule", action="store_true", help="스케줄러 모드 (매일 18:00 자동 실행)"
    )
    parser.add_argument("--email", action="store_true", help="실행 후 이메일 발송")
    parser.add_argument(
        "--no-save", action="store_true", help="파일 저장 안함 (화면 출력만)"
    )

    args = parser.parse_args()

    # 스케줄러 모드
    if args.schedule:
        try:
            run_with_schedule()
        except KeyboardInterrupt:
            print("\n[종료] 스케줄러가 중지되었습니다.")
            sys.exit(0)
        return

    # 일반 실행
    mode = "full" if args.full else "quick"

    try:
        # 전날 결과 추적 (다음날 실적 기록)
        print("\n[1단계] 전날 선정 종목 실적 추적")
        print("-" * 50)
        update_with_next_day_results()

        # 스크리닝 실행
        print("\n[2단계] 오늘의 스크리닝 실행")
        print("-" * 50)
        results = run_screening(mode=mode, top_n=args.top)

        if not results:
            print("\n[오류] 스크리닝 결과가 없습니다.")
            sys.exit(1)

        # 결과 분류
        categorized = categorize_results(results)

        # 결과 저장
        if not args.no_save:
            excel_path, json_path, csv_path = save_results(results, top_n=args.top)

        # 요약 출력
        print_summary(results, categorized)

        # 이메일 발송
        if args.email:
            pdf_path = OutputConfig.get_filepath("pdf")
            send_daily_report(results, pdf_path=pdf_path)

        print("\n" + "=" * 70)
        print(f"  완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70 + "\n")

    except KeyboardInterrupt:
        print("\n[중단] 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[오류] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
