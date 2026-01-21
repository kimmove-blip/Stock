#!/usr/bin/env python3
"""
매수 제안 생성기
- 보유종목 제외
- 상한가 종목 제외
- 당일 거래 종목 제외 (왕복매매 방지)
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUT_DIR
from trading.trade_logger import TradeLogger, BuySuggestionManager


def get_user_holdings(user_id: int) -> set:
    """사용자 보유종목 코드 조회"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)

    if not api_key_data:
        return set()

    account_data = logger.get_real_account_balance(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=bool(api_key_data.get('is_mock', True))
    )

    holdings = [h for h in account_data.get('holdings', []) if h.get('quantity', 0) > 0]
    return set(h.get('stock_code') for h in holdings)


def get_today_sold_stocks(user_id: int) -> set:
    """당일 매도한 종목 코드 조회 (왕복매매 방지)

    매수 후 매도한 종목만 블랙리스트 대상
    단순 매수만 한 종목은 제외 안함 (보유중으로 제외됨)
    """
    logger = TradeLogger()
    today = datetime.now().strftime('%Y-%m-%d')

    trades = logger.get_trade_history(
        user_id=user_id,
        start_date=today,
        end_date=today
    )

    # 매도(sell) 거래만 필터링
    sold_codes = set(
        t.get('stock_code') for t in trades
        if t.get('stock_code') and t.get('side') == 'sell'
    )

    return sold_codes


def load_screening_scores(date_str: str = None) -> Dict:
    """스크리닝 점수 로드"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    json_path = OUTPUT_DIR / f"top100_{date_str}.json"

    if not json_path.exists():
        return {}

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {}
    for stock in data.get('stocks', []):
        code = stock.get('code')
        if code:
            result[code] = {
                'name': stock.get('name', code),
                'score': stock.get('score', 0),
                'close': stock.get('close', 0),
                'change_pct': stock.get('change_pct', 0),
            }

    return result


def load_prev_scores() -> Dict:
    """이전 거래일 점수 로드 (연속성 체크용)"""
    for offset in range(1, 5):
        prev_date = (datetime.now() - timedelta(days=offset)).strftime('%Y%m%d')
        prev_path = OUTPUT_DIR / f"top100_{prev_date}.json"

        if prev_path.exists():
            with open(prev_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            scores = {}
            for s in data.get('stocks', []):
                code = s.get('code')
                if code:
                    scores[code] = s.get('score', 0)
            return scores

    return {}


def generate_buy_suggestions(
    user_id: int,
    min_score: int = 75,
    require_continuity: bool = True,
    exclude_limit_up: bool = True,
    exclude_holdings: bool = True,
    exclude_today_traded: bool = True,
    limit_up_threshold: float = 29.0,
    save_to_db: bool = True,
    verbose: bool = True
) -> List[Dict]:
    """
    매수 제안 생성

    Args:
        user_id: 사용자 ID
        min_score: 최소 점수 (기본 75)
        require_continuity: 75-79점은 연속성 체크 필요 (기본 True)
        exclude_limit_up: 상한가 종목 제외 (기본 True)
        exclude_holdings: 보유종목 제외 (기본 True)
        exclude_today_traded: 당일 거래 종목 제외 (기본 True)
        limit_up_threshold: 상한가 판단 기준 (기본 29%)
        save_to_db: DB에 저장 여부 (기본 True)
        verbose: 상세 출력 (기본 True)

    Returns:
        생성된 제안 목록
    """
    if verbose:
        print(f"=== 매수 제안 생성 (user_id={user_id}) ===\n")

    # 필터링용 데이터 로드
    holdings = get_user_holdings(user_id) if exclude_holdings else set()
    sold_today = get_today_sold_stocks(user_id) if exclude_today_traded else set()
    today_scores = load_screening_scores()
    prev_scores = load_prev_scores() if require_continuity else {}

    if verbose:
        print(f"보유종목: {len(holdings)}개")
        print(f"당일매도(블랙리스트): {len(sold_today)}개")
        print(f"스크리닝종목: {len(today_scores)}개")
        print()

    # 후보 선정
    candidates = []
    excluded = {'holding': [], 'sold': [], 'limit_up': [], 'no_continuity': []}

    for code, info in today_scores.items():
        score = info.get('score', 0)
        name = info.get('name', code)
        change_pct = info.get('change_pct', 0)
        close = info.get('close', 0)

        if score < min_score:
            continue

        # 필터링 체크
        if exclude_holdings and code in holdings:
            excluded['holding'].append(f"{name}({code})")
            continue

        if exclude_today_traded and code in sold_today:
            excluded['sold'].append(f"{name}({code})")
            continue

        if exclude_limit_up and change_pct >= limit_up_threshold:
            excluded['limit_up'].append(f"{name}({code}) +{change_pct:.1f}%")
            continue

        # 75-79점 연속성 체크
        if require_continuity and 75 <= score < 80:
            prev_score = prev_scores.get(code, 0)
            if prev_score < 75:
                excluded['no_continuity'].append(f"{name}({code}) 이전{prev_score}점")
                continue
            reason = f"75-79점 연속 (이전 {prev_score}점)"
        elif score >= 80:
            reason = f"80점 이상 ({score}점)"
        else:
            reason = f"{score}점"

        candidates.append({
            'code': code,
            'name': name,
            'score': score,
            'close': close,
            'change_pct': change_pct,
            'reason': reason,
        })

    # 점수순 정렬
    candidates.sort(key=lambda x: x['score'], reverse=True)

    if verbose:
        print("제외된 종목:")
        if excluded['holding']:
            print(f"  보유중: {', '.join(excluded['holding'])}")
        if excluded['sold']:
            print(f"  당일매도(왕복매매방지): {', '.join(excluded['sold'])}")
        if excluded['limit_up']:
            print(f"  상한가: {', '.join(excluded['limit_up'])}")
        if excluded['no_continuity']:
            print(f"  연속성부족: {', '.join(excluded['no_continuity'])}")
        print()

    if not candidates:
        if verbose:
            print("매수 가능한 종목이 없습니다.")
        return []

    if verbose:
        print(f"매수 후보: {len(candidates)}개")

    # DB에 저장
    suggestions = []
    if save_to_db:
        manager = BuySuggestionManager(user_id=user_id)

        for c in candidates:
            current_price = c['close']
            if current_price <= 0:
                continue

            stop_loss_price = int(current_price * 0.94)  # -6% 손절
            target_price = int(current_price * 1.15)  # +15% 목표

            suggestion_id = manager.create_suggestion(
                stock_code=c['code'],
                stock_name=c['name'],
                score=c['score'],
                probability=min(c['score'], 85),
                confidence=min(c['score'] - 5, 80),
                current_price=current_price,
                recommended_price=current_price,
                target_price=target_price,
                stop_loss_price=stop_loss_price,
                buy_band_low=int(current_price * 0.97),
                buy_band_high=int(current_price * 1.03),
                signals=[c['reason']],
                expire_hours=24
            )

            c['suggestion_id'] = suggestion_id
            suggestions.append(c)

            if verbose:
                print(f"  ✓ {c['name']}({c['code']}): {c['score']}점 - ID {suggestion_id}")
    else:
        suggestions = candidates
        if verbose:
            for c in candidates:
                print(f"  - {c['name']}({c['code']}): {c['score']}점, {c['reason']}")

    if verbose:
        print(f"\n총 {len(suggestions)}개 제안 생성")

    return suggestions


def get_holdings_with_details(user_id: int) -> List[Dict]:
    """사용자 보유종목 상세 정보 조회"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)

    if not api_key_data:
        return []

    account_data = logger.get_real_account_balance(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=bool(api_key_data.get('is_mock', True))
    )

    return [h for h in account_data.get('holdings', []) if h.get('quantity', 0) > 0]


def get_stock_score(code: str, today_scores: Dict) -> int:
    """종목 점수 조회"""
    if code in today_scores:
        return today_scores[code].get('score', 50)
    return 50  # 기본값


def get_20day_ma(code: str) -> Optional[float]:
    """20일 이동평균 조회"""
    try:
        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()
        df = analyst.get_ohlcv(code, days=30)

        if df is not None and len(df) >= 20:
            return df['Close'].tail(20).mean()
    except Exception:
        pass

    return None


def generate_sell_suggestions(
    user_id: int,
    stop_loss_rate: float = -6.0,
    min_sell_score: int = 40,
    check_ma20: bool = True,
    save_to_db: bool = True,
    verbose: bool = True
) -> List[Dict]:
    """
    매도 제안 생성

    Args:
        user_id: 사용자 ID
        stop_loss_rate: 손절 기준 (기본 -6%)
        min_sell_score: 이 점수 미만이면 매도 제안 (기본 40점)
        check_ma20: 20일 이평선 하회 체크 (기본 True)
        save_to_db: DB에 저장 여부 (기본 True)
        verbose: 상세 출력 (기본 True)

    Returns:
        생성된 매도 제안 목록
    """
    if verbose:
        print(f"=== 매도 제안 생성 (user_id={user_id}) ===\n")

    # 보유종목 조회
    holdings = get_holdings_with_details(user_id)
    today_scores = load_screening_scores()

    if verbose:
        print(f"보유종목: {len(holdings)}개\n")

    if not holdings:
        if verbose:
            print("보유종목이 없습니다.")
        return []

    # 매도 후보 분석
    sell_candidates = []
    hold_stocks = []

    for h in holdings:
        code = h.get('stock_code')
        name = h.get('stock_name', code)
        quantity = h.get('quantity', 0)
        avg_price = h.get('avg_price', 0)
        current_price = h.get('current_price', 0)
        profit_rate = h.get('profit_rate', 0)

        if quantity <= 0 or current_price <= 0:
            continue

        # 점수 조회
        score = get_stock_score(code, today_scores)

        # 매도 사유 체크
        sell_reasons = []

        # 1. 손절 체크
        if profit_rate <= stop_loss_rate:
            sell_reasons.append(f"손절({profit_rate:.1f}% <= {stop_loss_rate}%)")

        # 2. 점수 하락 체크
        if score < min_sell_score:
            sell_reasons.append(f"점수하락({score}점 < {min_sell_score}점)")

        # 3. 20일 이평선 하회 체크
        if check_ma20:
            ma20 = get_20day_ma(code)
            if ma20 and current_price < ma20:
                sell_reasons.append(f"20MA하회(현재{current_price:,} < MA{ma20:,.0f})")

        if sell_reasons:
            sell_candidates.append({
                'code': code,
                'name': name,
                'quantity': quantity,
                'avg_price': avg_price,
                'current_price': current_price,
                'profit_rate': profit_rate,
                'score': score,
                'reasons': sell_reasons,
            })
        else:
            hold_stocks.append({
                'code': code,
                'name': name,
                'profit_rate': profit_rate,
                'score': score,
            })

    if verbose:
        if hold_stocks:
            print("유지 종목:")
            for h in hold_stocks:
                print(f"  ✓ {h['name']}({h['code']}): {h['score']}점, {h['profit_rate']:+.1f}%")
            print()

    if not sell_candidates:
        if verbose:
            print("매도 대상 종목이 없습니다.")
        return []

    if verbose:
        print(f"매도 후보: {len(sell_candidates)}개")

    # DB에 저장
    suggestions = []
    if save_to_db:
        manager = BuySuggestionManager(user_id=user_id)

        for c in sell_candidates:
            reason_str = ", ".join(c['reasons'])

            suggestion_id = manager.add_sell_suggestion(
                user_id=user_id,
                stock_code=c['code'],
                stock_name=c['name'],
                quantity=c['quantity'],
                avg_price=c['avg_price'],
                suggested_price=c['current_price'],
                profit_rate=c['profit_rate'],
                reason=reason_str
            )

            c['suggestion_id'] = suggestion_id
            suggestions.append(c)

            if verbose:
                print(f"  ⚠️ {c['name']}({c['code']}): {c['profit_rate']:+.1f}% - {reason_str}")
    else:
        suggestions = sell_candidates
        if verbose:
            for c in sell_candidates:
                print(f"  ⚠️ {c['name']}({c['code']}): {c['profit_rate']:+.1f}% - {', '.join(c['reasons'])}")

    if verbose:
        print(f"\n총 {len(suggestions)}개 매도 제안 생성")

    return suggestions


def generate_all_suggestions(
    user_id: int,
    min_buy_score: int = 75,
    stop_loss_rate: float = -6.0,
    min_sell_score: int = 40,
    save_to_db: bool = True,
    verbose: bool = True
) -> Dict:
    """
    매수/매도 제안 모두 생성

    Args:
        user_id: 사용자 ID
        min_buy_score: 최소 매수 점수
        stop_loss_rate: 손절 기준
        min_sell_score: 매도 점수 기준
        save_to_db: DB 저장 여부
        verbose: 상세 출력

    Returns:
        {'buy': [...], 'sell': [...]}
    """
    buy_suggestions = generate_buy_suggestions(
        user_id=user_id,
        min_score=min_buy_score,
        save_to_db=save_to_db,
        verbose=verbose
    )

    if verbose:
        print()

    sell_suggestions = generate_sell_suggestions(
        user_id=user_id,
        stop_loss_rate=stop_loss_rate,
        min_sell_score=min_sell_score,
        save_to_db=save_to_db,
        verbose=verbose
    )

    return {
        'buy': buy_suggestions,
        'sell': sell_suggestions,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="매수/매도 제안 생성")
    parser.add_argument("--user-id", type=int, required=True, help="사용자 ID")
    parser.add_argument("--min-score", type=int, default=75, help="최소 매수 점수")
    parser.add_argument("--stop-loss", type=float, default=-6.0, help="손절 기준 (%)")
    parser.add_argument("--buy-only", action="store_true", help="매수 제안만")
    parser.add_argument("--sell-only", action="store_true", help="매도 제안만")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 안함")

    args = parser.parse_args()

    if args.buy_only:
        generate_buy_suggestions(
            user_id=args.user_id,
            min_score=args.min_score,
            save_to_db=not args.dry_run,
        )
    elif args.sell_only:
        generate_sell_suggestions(
            user_id=args.user_id,
            stop_loss_rate=args.stop_loss,
            save_to_db=not args.dry_run,
        )
    else:
        generate_all_suggestions(
            user_id=args.user_id,
            min_buy_score=args.min_score,
            stop_loss_rate=args.stop_loss,
            save_to_db=not args.dry_run,
        )
