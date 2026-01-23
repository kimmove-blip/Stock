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
from result_tracker import update_with_next_day_results, get_previous_result_file, get_yesterday_results, create_two_sheet_excel
from streak_tracker import (
    calculate_streak_and_rank_change,
    format_rank_change,
    format_streak,
    get_streak_stats,
    apply_streak_weighted_score,
    classify_stocks,
    get_classification_stats
)
from technical_analyst import apply_signal_reliability_weights


def run_screening(mode="quick", top_n=100, scoring_version="v2", fetch_investor_data=False):
    """스크리닝 실행
    Returns: (results, stats) 튜플

    Args:
        mode: 'quick' 또는 'full'
        top_n: 선정할 종목 수
        scoring_version: 스크리닝 엔진 버전 (v1~v4)
        fetch_investor_data: 네이버 수급 데이터 조회 여부 (v4 전용)
    """
    version_names = {
        'v1': '종합 기술적 분석',
        'v2': '추세 추종 강화',
        'v3': '래치 전략',
        'v4': 'Hybrid Sniper'
    }
    print("\n" + "=" * 70)
    print(f"  내일 관심 종목 {top_n}선 스크리닝")
    print(f"  실행시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  모드: {'전체 분석' if mode == 'full' else '빠른 스크리닝'}")
    print(f"  스크리닝 엔진: {scoring_version.upper()} ({version_names.get(scoring_version, '')})")
    if fetch_investor_data and scoring_version == 'v4':
        print(f"  수급 데이터: 네이버 금융 (기관/외국인)")
    print("=" * 70)

    # 스크리너 초기화
    screener = MarketScreener(
        max_workers=ScreeningConfig.MAX_WORKERS,
        scoring_version=scoring_version,
        fetch_investor_data=fetch_investor_data
    )

    # 스크리닝 실행 (통계도 함께 반환)
    results, stats = screener.run_full_screening(
        top_n=top_n * 2,  # 필터링 여유분
        mode=mode,
        min_marcap=ScreeningConfig.MIN_MARKET_CAP,
        max_marcap=ScreeningConfig.MAX_MARKET_CAP,
        min_amount=ScreeningConfig.MIN_TRADING_AMOUNT,
    )

    # 스크리닝 버전 저장
    stats['scoring_version'] = scoring_version

    return results, stats


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


def save_results(results, top_n=100, yesterday_df=None, yesterday_summary=None, stats=None, apply_improvements=True):
    """결과 저장 (Excel 2시트, JSON, CSV, PDF)

    파일명 형식: top100_{version}_{date}.{ext}
    - v2는 기본값이므로 버전 생략: top100_20260123.pdf
    - v1, v3, v4는 버전 포함: top100_v4_20260123.pdf

    Args:
        results: 스크리닝 결과
        top_n: 상위 N개 선정
        yesterday_df: 전날 결과
        yesterday_summary: 전날 요약
        stats: 통계 정보
        apply_improvements: 신뢰도 개선 적용 여부
    """
    # 스크리닝 버전 설정 (파일명에 반영)
    scoring_version = stats.get('scoring_version', 'v2') if stats else 'v2'
    OutputConfig.set_version(scoring_version)
    print("\n[저장] 결과 파일 생성 중...")

    # 상위 N개만 추출
    top_results = results[:top_n]

    # 연속 출현 및 순위 변동 계산
    print("    → 연속 출현/순위 변동 계산 중...")
    top_results = calculate_streak_and_rank_change(top_results)
    streak_stats = get_streak_stats(top_results)
    print(f"    → 신규 진입: {streak_stats['new_entries']}개, 연속 유지: {streak_stats['continued']}개")

    # 신뢰도 개선 적용 (방안 A + D)
    if apply_improvements:
        print("    → 분류 처리 중...")

        # 신뢰도/지속성 가중치 비활성화 (원점수 사용)
        # # 1. 신호별 신뢰도 가중치 적용 (방안 D)
        # for r in top_results:
        #     signals = r.get('signals', [])
        #     base_score = r.get('score', 0)
        #     adjusted_score, reliability_info = apply_signal_reliability_weights(signals, base_score)
        #     r['reliability_adjusted_score'] = adjusted_score
        #     r['reliability_info'] = reliability_info

        # # 2. 신호 지속성 가중치 적용 (방안 A)
        # top_results = apply_streak_weighted_score(top_results)

        # 3. 2단계 분류 (방안 C)
        stable, new_interest = classify_stocks(top_results)
        class_stats = get_classification_stats(stable, new_interest)
        print(f"    → 안정 추천: {class_stats['stable']['count']}개, 신규 관심: {class_stats['new_interest']['count']}개")

        # 분류 정보 추가
        for r in stable:
            r['classification'] = 'stable'
        for r in new_interest:
            r['classification'] = 'new'

        # stats에 분류 통계 추가
        if stats:
            stats['classification_stats'] = class_stats

    # stats에 streak 통계 추가
    if stats:
        stats['streak_stats'] = streak_stats

    # DataFrame 생성 (CSV용)
    df = create_dataframe(top_results)

    # 1. Excel 저장 (2개 시트: 내일의 관심종목 + 전일 결과)
    excel_path = OutputConfig.get_filepath("excel")
    create_two_sheet_excel(top_results, yesterday_df, yesterday_summary, excel_path)
    print(f"    → Excel: {excel_path} (2개 시트)")

    # 2. JSON 저장
    json_path = OutputConfig.get_filepath("json")
    save_json(top_results, json_path, stats=stats)
    print(f"    → JSON: {json_path}")

    # 3. CSV 저장
    csv_path = OutputConfig.get_filepath("csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"    → CSV: {csv_path}")

    # 4. PDF 저장 (통계 포함)
    pdf_path = OutputConfig.get_filepath("pdf")
    generate_detailed_pdf(top_results, pdf_path, stats=stats)
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

        # 조정된 점수 사용
        score = r.get("adjusted_score", r["score"])
        original_score = r.get("original_score", r["score"])
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

        # 순위 변동 및 연속 출현
        rank_change = r.get("rank_change")
        streak = r.get("streak", 1)
        rank_change_str = format_rank_change(rank_change)
        streak_str = format_streak(streak)

        # 분류 정보
        classification = r.get("classification", "")
        class_str = "★" if classification == "stable" else ("NEW" if classification == "new" else "-")

        row = {
            "순위": i,
            "종목코드": r["code"],
            "종목명": r["name"],
            "분류": class_str,
            "변동": rank_change_str,
            "연속": streak_str,
            "시장": r["market"],
            "종합점수": score,
            "원점수": original_score,
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


def save_json(results, filepath, stats=None):
    """JSON 형식으로 저장"""
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_count": len(results),
        "screening_stats": stats or {},
        "stocks": [],
    }

    for r in results:
        # 조정된 점수 사용 (있으면)
        score = r.get("adjusted_score", r["score"])
        original_score = r.get("original_score", r["score"])
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
            "score": score,
            "original_score": original_score,
            "close": r.get("close", 0),
            "target_price": target_price,
            "expected_return": round((target_mul - 1) * 100, 1),
            "change_pct": round(r.get("change_pct", 0), 2),
            "volume": r.get("volume", 0),
            "signals": r.get("signals", []),
            "patterns": r.get("patterns", []),
            # 개별 점수 (v1-v4)
            "trend_score": r.get("trend_score"),
            "momentum_score": r.get("momentum_score"),
            "volume_score": r.get("volume_score"),
            "pattern_score": r.get("pattern_score"),
            "scoring_version": r.get("scoring_version"),
            # 연속 출현 및 순위 변동
            "streak": r.get("streak", 1),
            "rank_change": r.get("rank_change"),  # None이면 NEW
            "prev_rank": r.get("prev_rank"),
            # 신뢰도 개선 정보
            "streak_weight": r.get("streak_weight", 1.0),
            "classification": r.get("classification", ""),  # stable 또는 new
        }

        # 지표 추가 (numpy 타입을 Python 기본 타입으로 변환)
        if "indicators" in r:
            import numpy as np
            def convert_value(v):
                if isinstance(v, (np.integer, np.int64, np.int32)):
                    return int(v)
                elif isinstance(v, (np.floating, np.float64, np.float32)):
                    return round(float(v), 4)
                elif isinstance(v, float):
                    return round(v, 4)
                return v
            stock["indicators"] = {
                k: convert_value(v) for k, v in r["indicators"].items()
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

    # 2단계 분류 통계
    stable = [r for r in results if r.get('classification') == 'stable']
    new_interest = [r for r in results if r.get('classification') == 'new']

    if stable or new_interest:
        print("\n" + "-" * 70)
        print("  [신뢰도 기반 분류]")
        print("-" * 70)
        print(f"  - 안정 추천 (3일+ 연속): {len(stable)}개")
        print(f"  - 신규 관심 (NEW/단기): {len(new_interest)}개")

    # 안정 추천 종목 (최대 10개)
    if stable:
        print("\n" + "-" * 70)
        print("  [안정 추천 종목] (3일 이상 연속 출현)")
        print("-" * 70)
        for r in stable[:10]:
            signals = [get_signal_kr(s) for s in r.get("signals", [])[:2]]
            streak = r.get('streak', 1)
            adj_score = r.get('adjusted_score', r.get('score', 0))
            orig_score = r.get('original_score', r.get('score', 0))
            print(
                f"  {r['code']} {r['name']:<10} "
                f"연속:{streak}일 점수:{adj_score:>2}({orig_score:>2}) | {', '.join(signals)}"
            )

    # 강력 매수 종목 출력
    if categorized["strong_buy"]:
        print("\n" + "-" * 70)
        print("  [강력 매수 후보]")
        print("-" * 70)
        for r in categorized["strong_buy"][:10]:
            signals = [get_signal_kr(s) for s in r.get("signals", [])[:3]]
            adj_score = r.get('adjusted_score', r.get('score', 0))
            print(
                f"  {r['code']} {r['name']:<12} 점수:{adj_score:>3} | {', '.join(signals)}"
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
        print("-" * 50)
        prev_file = get_previous_result_file()
        yesterday_df, yesterday_summary = None, None
        if prev_file:
            yesterday_df, yesterday_summary = get_yesterday_results(prev_file)
            if yesterday_summary:
                print(f"[추적] 전날 파일: {prev_file}")
                print(f"    - 총 투자금: {yesterday_summary.get('total_investment', 0):,}원")
                print(f"    - 총 회수금: {yesterday_summary.get('total_returns', 0):,}원")
                print(f"    - 총 수익금: {yesterday_summary.get('total_profit', 0):,}원 ({yesterday_summary.get('total_profit_rate', 0)}%)")
        else:
            print("[추적] 전날 파일 없음")

        # 스크리닝 실행
        print("\n[2단계] 오늘의 스크리닝 실행")
        print("-" * 50)
        results, stats = run_screening(mode=ScreeningConfig.MODE, top_n=ScreeningConfig.TOP_N)

        if not results:
            print("[스케줄] 스크리닝 결과 없음")
            return

        categorized = categorize_results(results)
        save_results(results, top_n=ScreeningConfig.TOP_N, yesterday_df=yesterday_df, yesterday_summary=yesterday_summary, stats=stats)
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
    parser.add_argument(
        "--version", "-v", type=str, default="v2",
        choices=["v1", "v2", "v3", "v4"],
        help="스크리닝 엔진 버전 (기본: v2)"
    )
    parser.add_argument(
        "--investor", action="store_true",
        help="네이버 금융 기관/외국인 수급 데이터 포함 (v4 전용)"
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

    # 일반 실행 (무조건 full 모드)
    mode = "full"

    try:
        # 전날 결과 추적 (다음날 실적 기록)
        print("\n[1단계] 전날 선정 종목 실적 추적")
        print("-" * 50)
        prev_file = get_previous_result_file()
        yesterday_df, yesterday_summary = None, None
        if prev_file:
            yesterday_df, yesterday_summary = get_yesterday_results(prev_file)
            if yesterday_summary:
                print(f"[추적] 전날 파일: {prev_file}")
                print(f"    - 총 투자금: {yesterday_summary.get('total_investment', 0):,}원")
                print(f"    - 총 회수금: {yesterday_summary.get('total_returns', 0):,}원")
                print(f"    - 총 수익금: {yesterday_summary.get('total_profit', 0):,}원 ({yesterday_summary.get('total_profit_rate', 0)}%)")
                print(f"    - 수익 종목: {yesterday_summary.get('success_count', 0)}개")
                print(f"    - 손실 종목: {yesterday_summary.get('fail_count', 0)}개")
        else:
            print("[추적] 전날 파일 없음")

        # 스크리닝 실행
        print("\n[2단계] 오늘의 스크리닝 실행")
        print("-" * 50)
        results, stats = run_screening(
            mode=mode,
            top_n=args.top,
            scoring_version=args.version,
            fetch_investor_data=args.investor
        )

        if not results:
            print("\n[오류] 스크리닝 결과가 없습니다.")
            sys.exit(1)

        # 결과 분류
        categorized = categorize_results(results)

        # 결과 저장 (args.top 개수만큼)
        if not args.no_save:
            excel_path, json_path, csv_path = save_results(
                results, top_n=args.top,
                yesterday_df=yesterday_df,
                yesterday_summary=yesterday_summary,
                stats=stats
            )

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
