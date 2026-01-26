#!/usr/bin/env python3
"""
V9 갭상승 종목 종가 매수 스크립트
- auto 모드 계좌에 V9 상위 종목 분산 매수
"""

import os
import sys
import argparse
import pickle
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient


MODEL_PATH = Path(__file__).parent / "models" / "gap_model_v9.pkl"


def get_auto_users():
    """auto 모드 사용자 목록 조회"""
    logger = TradeLogger()
    with logger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM auto_trade_settings WHERE trade_mode = 'auto'")
        return [row['user_id'] for row in cursor.fetchall()]


def get_v9_top_stocks(top_n=5, max_price=200000, fast_mode=False):
    """V9 모델로 갭상승 확률 상위 종목 조회

    Args:
        top_n: 상위 N개 종목 반환
        max_price: 최대 주가 필터 (0이면 필터 없음)
        fast_mode: True면 거래대금 상위 500종목만 스캔 (빠른 모드)
    """
    from pykrx import stock
    from pykrx.website.krx.market.ticker import StockTicker
    import pandas as pd
    import numpy as np

    if not MODEL_PATH.exists():
        print(f"모델 파일 없음: {MODEL_PATH}")
        return []

    with open(MODEL_PATH, 'rb') as f:
        model_data = pickle.load(f)

    model = model_data['model']
    features = model_data['features']

    today = datetime.now().strftime('%Y%m%d')

    # 전 종목 조회 (StockTicker 사용)
    ticker_df = StockTicker().listed
    ticker_df = ticker_df[ticker_df['시장'].isin(['STK', 'KSQ'])]
    all_tickers = ticker_df.index.tolist()
    ticker_names = ticker_df['종목'].to_dict()

    # 빠른 모드: 최근 top100 결과 + 추가 종목만 스캔
    if fast_mode:
        print("빠른 모드: top100 기반 후보 종목 사용...")
        output_dir = Path(__file__).parent / "output"
        top100_files = sorted(output_dir.glob('top100_2*.json'), reverse=True)
        candidate_tickers = set()

        # top100 결과에서 종목 추출
        for json_file in top100_files[:3]:  # 최근 3일치
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # stocks 키 아래에 종목 리스트가 있는 경우
                stocks_list = data.get('stocks', data) if isinstance(data, dict) else data
                for item in stocks_list:
                    if isinstance(item, dict):
                        code = item.get('code') or item.get('ticker') or item.get('stock_code')
                        if code:
                            candidate_tickers.add(code)
            except Exception as e:
                print(f"  파일 로드 실패: {json_file.name} - {e}")

        # 후보가 있으면 사용
        if candidate_tickers:
            # 후보 + 추가 200개 (전체 리스트에서 샘플링)
            extra_tickers = [t for t in all_tickers if t not in candidate_tickers][:200]
            all_tickers = list(candidate_tickers) + extra_tickers
            print(f"  → {len(candidate_tickers)}개 top100 후보 + {len(extra_tickers)}개 추가 = {len(all_tickers)}종목")
        else:
            print("  → top100 후보 없음, 전체 스캔")

    print(f"V9 모델 예측 중... ({len(all_tickers)}종목)")

    results = []
    for i, ticker in enumerate(all_tickers):
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(all_tickers)}...")

        try:
            # 최근 60일 데이터
            df = stock.get_market_ohlcv_by_date(
                fromdate=(datetime.now() - pd.Timedelta(days=90)).strftime('%Y%m%d'),
                todate=today,
                ticker=ticker
            )

            if len(df) < 20:
                continue

            df = df.tail(60)

            # 거래대금 계산 (pykrx는 거래대금 컬럼 미제공)
            df['거래대금'] = df['거래량'] * df['종가']

            # 거래대금 필터 (30억 이상)
            if df['거래대금'].iloc[-1] < 3_000_000_000:
                continue

            # 현재가 필터 (max_price가 0보다 크면 적용)
            current_price = df['종가'].iloc[-1]
            if max_price > 0 and current_price > max_price:
                continue

            # 피처 계산
            row = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else row

            high, low, close, volume = row['고가'], row['저가'], row['종가'], row['거래량']
            open_price = row['시가']

            feature_dict = {
                'close_pos': (close - low) / (high - low) if high != low else 0.5,
                'close_high': close / high if high > 0 else 1,
                'is_bull': 1 if close > open_price else 0,
                'body_ratio': abs(close - open_price) / (high - low) if high != low else 0,
                'upper_wick': (high - max(open_price, close)) / (high - low) if high != low else 0,
                'lower_wick': (min(open_price, close) - low) / (high - low) if high != low else 0,
                'day_change': (close - prev['종가']) / prev['종가'] * 100 if prev['종가'] > 0 else 0,
                'dist_ma5': (close - df['종가'].tail(5).mean()) / df['종가'].tail(5).mean() * 100,
                'dist_ma20': (close - df['종가'].tail(20).mean()) / df['종가'].tail(20).mean() * 100,
                'vol_ratio': volume / df['거래량'].tail(20).mean() if df['거래량'].tail(20).mean() > 0 else 1,
                'vol_declining': 1 if volume < df['거래량'].tail(5).mean() else 0,
                'rsi': 50,  # 간략화
                'rsi_overbought': 0,
                'consec_bull': 0,
                'aligned': 1 if df['종가'].tail(5).mean() > df['종가'].tail(20).mean() else 0,
                'near_high_20d': close / df['고가'].tail(20).max() if df['고가'].tail(20).max() > 0 else 1,
                'from_low_20d': (close - df['저가'].tail(20).min()) / df['저가'].tail(20).min() * 100 if df['저가'].tail(20).min() > 0 else 0,
                'volatility': df['종가'].tail(20).std() / df['종가'].tail(20).mean() * 100,
                'trade_value': df['거래대금'].iloc[-1] / 1e8,
                'is_surge': 1 if (close - prev['종가']) / prev['종가'] * 100 > 5 else 0,
                'two_day_surge': 0
            }

            X = pd.DataFrame([feature_dict])[features]
            prob = model.predict_proba(X)[0][1]

            name = ticker_names.get(ticker, '')
            results.append({
                'ticker': ticker,
                'name': name,
                'price': int(current_price),
                'prob': float(prob)
            })

        except Exception:
            continue

    # 확률 높은 순 정렬
    results.sort(key=lambda x: x['prob'], reverse=True)

    return results[:top_n]


def get_account_balance(user_id):
    """계좌 잔고 조회"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return 0, False

    account_data = logger.get_real_account_balance(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=bool(api_key_data.get('is_mock', True))
    )

    summary = account_data.get('summary', {})
    d2_cash = summary.get('d2_cash_balance', 0) or summary.get('deposit', 0)
    is_mock = bool(api_key_data.get('is_mock', True))

    return d2_cash, is_mock


def buy_stocks(user_id, stocks, dry_run=False):
    """종목 분산 매수"""
    logger = TradeLogger()
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        print(f"  [user {user_id}] API 키 없음")
        return []

    d2_cash, is_mock = get_account_balance(user_id)
    print(f"  [user {user_id}] D+2 예수금: {d2_cash:,}원 ({'모의' if is_mock else '실전'})")

    if d2_cash <= 0:
        print(f"  [user {user_id}] 예수금 부족")
        return []

    client = KISClient(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=api_key_data.get('account_number'),
        is_virtual=is_mock
    )

    # 종목당 투자금액
    per_stock = d2_cash // len(stocks)

    results = []
    for s in stocks:
        ticker = s['ticker']
        name = s['name']
        price = s['price']
        prob = s['prob']

        quantity = per_stock // price
        if quantity <= 0:
            print(f"  {name}: 수량 부족 (가격 {price:,}원, 투자금 {per_stock:,}원)")
            continue

        print(f"  [user {user_id}] {name}({ticker}) {quantity}주 @ {price:,}원 매수 (확률 {prob:.1%})...")

        if dry_run:
            print(f"    [DRY RUN] 매수 주문 스킵")
            results.append({'stock_name': name, 'quantity': quantity, 'price': price, 'status': 'dry_run'})
            continue

        try:
            result = client.place_order(
                stock_code=ticker,
                order_type='buy',
                quantity=quantity,
                price=0,  # 시장가
                order_dv='01'
            )

            if result and result.get('rt_cd') == '0':
                order_no = result.get('output', {}).get('ODNO', '')
                print(f"    매수 주문 성공: 주문번호 {order_no}")

                logger.log_trade(
                    user_id=user_id,
                    stock_code=ticker,
                    stock_name=name,
                    side='buy',
                    quantity=quantity,
                    price=price,
                    order_no=order_no,
                    status='pending',
                    trade_reason='V9 갭상승 종가 매수'
                )

                results.append({'stock_name': name, 'quantity': quantity, 'price': price, 'status': 'ordered'})
            else:
                msg = result.get('msg1', '') if result else 'Unknown error'
                print(f"    매수 주문 실패: {msg}")
                results.append({'stock_name': name, 'quantity': quantity, 'status': 'failed', 'error': msg})

        except Exception as e:
            print(f"    매수 주문 에러: {e}")
            results.append({'stock_name': name, 'quantity': quantity, 'status': 'error', 'error': str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(description='V9 갭상승 종목 종가 매수')
    parser.add_argument('--buy', action='store_true', help='매수 주문 실행')
    parser.add_argument('--list', action='store_true', help='V9 상위 종목 조회만')
    parser.add_argument('--top', type=int, default=5, help='상위 N개 종목')
    parser.add_argument('--max-price', type=int, default=0, help='최대 주가 (0=무제한)')
    parser.add_argument('--fast', action='store_true', help='빠른 모드 (거래대금 상위 500종목만)')
    parser.add_argument('--use-latest', action='store_true', help='최근 저장된 결과 사용')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드')
    parser.add_argument('--user-id', type=int, help='특정 사용자만')
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"V9 갭상승 종가 매수 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # 최근 저장된 결과 사용
    if args.use_latest:
        output_dir = Path(__file__).parent / "output"
        json_files = sorted(output_dir.glob("v9_result_*.json"), reverse=True)
        if json_files:
            latest_file = json_files[0]
            print(f"최근 결과 로드: {latest_file.name}")
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            stocks = data['stocks'][:args.top]
            print(f"  저장 시간: {data['timestamp']}")
        else:
            print("저장된 V9 결과 없음, 새로 예측 실행")
            stocks = get_v9_top_stocks(top_n=args.top, max_price=args.max_price, fast_mode=args.fast)
    else:
        # V9 상위 종목 조회
        stocks = get_v9_top_stocks(top_n=args.top, max_price=args.max_price, fast_mode=args.fast)

    if not stocks:
        print("V9 상위 종목 없음")
        return

    print(f"\n=== V9 상위 {len(stocks)}종목 ===")
    for i, s in enumerate(stocks, 1):
        print(f"  {i}. {s['name']}({s['ticker']}): {s['price']:,}원, 확률 {s['prob']:.1%}")

    # 결과 JSON 저장 (--use-latest가 아닐 때만)
    if not args.use_latest:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = Path(__file__).parent / "output" / f"v9_result_{timestamp}.json"
        result_data = {
            'timestamp': datetime.now().isoformat(),
            'top_n': args.top,
            'fast_mode': args.fast,
            'stocks': stocks
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: {output_path}")

    if args.list:
        return

    if args.buy:
        if args.user_id:
            users = [args.user_id]
        else:
            users = get_auto_users()

        print(f"\n대상 사용자: {users}")

        for user_id in users:
            print(f"\n--- User {user_id} ---")
            results = buy_stocks(user_id, stocks, dry_run=args.dry_run)

    print(f"\n{'='*50}")
    print("완료")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
