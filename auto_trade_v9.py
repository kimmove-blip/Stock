#!/usr/bin/env python3
"""
V9 자동매매 - 갭 상승 확률 70%+ 종목 매수
- 매일 15:20 실행 (크론)
- auto 모드 계정만 자동 매수
"""
import sys
sys.path.insert(0, '/home/kimhc/Stock')

import pandas as pd
import numpy as np
from pykrx import stock
from pykrx.website.krx.market.ticker import StockTicker
import pickle
from datetime import datetime, timedelta
import sqlite3
import warnings
warnings.filterwarnings('ignore')

from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient

PROB_THRESHOLD = 0.70
MODEL_PATH = '/home/kimhc/Stock/models/gap_model_v9.pkl'
DB_PATH = '/home/kimhc/Stock/database/auto_trade.db'
LOG_FILE = '/home/kimhc/Stock/output/auto_trade_v9.log'

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

log("=" * 60)
log("V9 자동매매 시작")
log("=" * 60)

# =============================================================================
# 1. 모델 로드
# =============================================================================
log("[1] 모델 로드...")
try:
    with open(MODEL_PATH, 'rb') as f:
        data = pickle.load(f)
    model = data['model']
    fcols = data['features']
    log("    완료")
except Exception as e:
    log(f"    실패: {e}")
    sys.exit(1)

# =============================================================================
# 2. 최근 거래일 확인
# =============================================================================
log("[2] 최근 거래일 확인...")
# 테스트 모드: 특정 날짜 지정 가능
import sys
if len(sys.argv) > 1 and sys.argv[1].startswith('--date='):
    TARGET_DATE = sys.argv[1].split('=')[1]
    log(f"    테스트 모드: {TARGET_DATE}")
else:
    TARGET_DATE = None
    for i in range(10):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
        df = stock.get_market_ohlcv(date, date, '005930')
        if len(df) > 0:
            TARGET_DATE = date
            break

if not TARGET_DATE:
    log("    거래일 찾기 실패")
    sys.exit(1)

log(f"    {TARGET_DATE}")

# =============================================================================
# 3. 종목 정보 로드
# =============================================================================
log("[3] 종목 정보 로드...")
ticker_df = StockTicker().listed
ticker_df = ticker_df[ticker_df['시장'].isin(['STK', 'KSQ'])]
tickers = ticker_df.index.tolist()
ticker_names = ticker_df['종목'].to_dict()
log(f"    {len(tickers)}개 종목")

# =============================================================================
# 4. 피처 계산 및 예측
# =============================================================================
def calc_features(df):
    """백테스트와 동일한 20+ 피처 계산"""
    if len(df) < 21:
        return None
    idx = len(df) - 1
    row = df.iloc[idx]
    prev_rows = df.iloc[idx-20:idx]

    o, h, l, c, v = row['시가'], row['고가'], row['저가'], row['종가'], row['거래량']
    if o == 0 or c == 0 or v == 0:
        return None

    f = {}
    body = abs(c - o)
    total_range = h - l if h > l else 1

    f['close_pos'] = (c - l) / total_range if total_range > 0 else 0.5
    f['close_high'] = (c - l) / (h - l) if h > l else 0.5
    f['is_bull'] = 1 if c > o else 0
    f['body_ratio'] = body / total_range if total_range > 0 else 0
    f['upper_wick'] = (h - max(o, c)) / total_range if total_range > 0 else 0
    f['lower_wick'] = (min(o, c) - l) / total_range if total_range > 0 else 0

    prev_close = df.iloc[idx-1]['종가']
    f['day_change'] = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0

    ma5 = prev_rows['종가'].tail(5).mean()
    ma20 = prev_rows['종가'].mean()
    f['dist_ma5'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0
    f['dist_ma20'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

    avg_vol = prev_rows['거래량'].mean()
    f['vol_ratio'] = v / avg_vol if avg_vol > 0 else 1

    recent_vol = prev_rows['거래량'].tail(5).mean()
    older_vol = prev_rows['거래량'].head(15).mean()
    f['vol_declining'] = 1 if recent_vol < older_vol * 0.7 else 0

    changes = prev_rows['종가'].diff()
    gains = changes.where(changes > 0, 0).mean()
    losses = (-changes.where(changes < 0, 0)).mean()
    f['rsi'] = gains / (gains + losses) * 100 if gains + losses > 0 else 50
    f['rsi_overbought'] = 1 if f['rsi'] > 70 else 0

    recent_5 = df.iloc[idx-4:idx+1]
    f['consec_bull'] = sum(1 for i in range(len(recent_5))
                           if recent_5.iloc[i]['종가'] > recent_5.iloc[i]['시가'])

    ma5_val = df.iloc[idx-4:idx+1]['종가'].mean()
    ma10_val = df.iloc[idx-9:idx+1]['종가'].mean()
    ma20_val = df.iloc[idx-19:idx+1]['종가'].mean()
    f['aligned'] = 1 if c > ma5_val > ma10_val > ma20_val else 0

    high_20d = prev_rows['고가'].max()
    low_20d = prev_rows['저가'].min()
    f['near_high_20d'] = c / high_20d if high_20d > 0 else 0
    f['from_low_20d'] = (c - low_20d) / low_20d * 100 if low_20d > 0 else 0

    f['volatility'] = prev_rows['종가'].pct_change().std() * 100
    f['trade_value'] = row['거래량'] * c / 100000000
    f['is_surge'] = 1 if f['day_change'] >= 15 else 0

    if idx >= 2:
        prev_prev_close = df.iloc[idx-2]['종가']
        two_day_change = (c - prev_prev_close) / prev_prev_close * 100
        f['two_day_surge'] = 1 if two_day_change >= 20 else 0
    else:
        f['two_day_surge'] = 0

    f['close'] = c
    return f

log(f"[4] {TARGET_DATE} 종목 스캔...")
start = (datetime.strptime(TARGET_DATE, '%Y%m%d') - timedelta(days=60)).strftime('%Y%m%d')

predictions = []
for i, ticker in enumerate(tickers):
    if (i + 1) % 500 == 0:
        log(f"    {i+1}/{len(tickers)}...")
    try:
        df = stock.get_market_ohlcv(start, TARGET_DATE, ticker)
        if len(df) < 21:
            continue
        if df.index[-1].strftime('%Y%m%d') != TARGET_DATE:
            continue

        f = calc_features(df)
        if f is None or f['trade_value'] < 50:
            continue
        if not (-15 <= f['day_change'] <= 25):
            continue

        close = f.pop('close')
        prob = model.predict_proba(pd.DataFrame([f])[fcols])[0][1]

        if prob >= PROB_THRESHOLD:
            predictions.append({
                'ticker': ticker,
                'name': ticker_names.get(ticker, ''),
                'prob': prob,
                'close': int(close)
            })
    except:
        pass

predictions.sort(key=lambda x: x['prob'], reverse=True)
log(f"    {len(predictions)}개 종목 선정")

if not predictions:
    log("매수 대상 종목 없음. 종료.")
    sys.exit(0)

# 상위 5개만
predictions = predictions[:5]
log("    상위 5개:")
for p in predictions:
    log(f"      {p['ticker']} {p['name']} - 확률 {p['prob']*100:.1f}%")

# =============================================================================
# 5. 자동매매 계정 조회 및 매수 실행
# =============================================================================
log("[5] 자동매매 실행...")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# trading_enabled=1인 계정 조회 (auto + semi 모드)
cursor.execute("""
    SELECT s.user_id, s.max_per_stock, s.trade_mode, k.app_key, k.app_secret, k.account_number, k.is_mock
    FROM auto_trade_settings s
    JOIN api_key_settings k ON s.user_id = k.user_id
    WHERE s.trading_enabled = 1 AND s.trade_mode IN ('auto', 'semi')
""")
accounts = cursor.fetchall()
conn.close()

if not accounts:
    log("    자동매매 계정 없음")
    sys.exit(0)

trade_logger = TradeLogger()

for user_id, max_per_stock, trade_mode, app_key_enc, app_secret_enc, account_enc, is_mock in accounts:
    log(f"\n  [User {user_id}] {'모의' if is_mock else '실전'}투자 ({trade_mode} 모드)")

    try:
        # API 키 복호화
        api_key_data = trade_logger.get_api_key_settings(user_id)
        if not api_key_data:
            log(f"    API 키 없음")
            continue

        # KIS 클라이언트 생성
        client = KISClient(
            app_key=api_key_data['app_key'],
            app_secret=api_key_data['app_secret'],
            account_number=api_key_data['account_number'],
            account_product_code=api_key_data.get('account_product_code', '01'),
            is_virtual=bool(api_key_data.get('is_mock', True))
        )

        # 현금 잔고 확인
        balance = client.get_account_balance()
        if not balance:
            log(f"    잔고 조회 실패")
            continue

        cash = balance.get('summary', {}).get('cash_balance', 0)
        log(f"    현금 잔고: {cash:,}원")

        # 종목당 투자금액
        invest_per_stock = min(max_per_stock, cash // len(predictions))
        if invest_per_stock < 50000:
            log(f"    투자금액 부족 ({invest_per_stock:,}원)")
            continue

        log(f"    종목당 투자: {invest_per_stock:,}원")

        # 매수 실행 또는 제안
        for p in predictions:
            ticker = p['ticker']
            name = p['name']

            # 현재가 조회
            price_data = client.get_current_price(ticker)
            if not price_data:
                log(f"    {name}: 현재가 조회 실패")
                continue

            current_price = price_data.get('current_price', 0)
            if current_price <= 0:
                continue

            # 매수 수량 계산
            quantity = invest_per_stock // current_price
            if quantity <= 0:
                log(f"    {name}: 매수 수량 0")
                continue

            if trade_mode == 'auto':
                # AUTO 모드: 자동 매수 주문
                log(f"    {name}({ticker}): {quantity}주 @ {current_price:,}원 [자동매수]")
                result = client.place_order(
                    stock_code=ticker,
                    side='buy',
                    quantity=quantity,
                    price=0,  # 시장가
                    order_type='01'
                )

                if result.get('success'):
                    log(f"      → 주문 성공: {result.get('order_no')}")
                    trade_logger.log_order(
                        user_id=user_id,
                        stock_code=ticker,
                        stock_name=name,
                        side='buy',
                        quantity=quantity,
                        price=current_price,
                        order_no=result.get('order_no'),
                        reason=f"V9 자동매매 (확률 {p['prob']*100:.1f}%)"
                    )
                else:
                    log(f"      → 주문 실패: {result.get('error')}")

            else:
                # SEMI 모드: 매수 제안만 등록
                log(f"    {name}({ticker}): {quantity}주 @ {current_price:,}원 [제안등록]")
                try:
                    trade_logger.add_buy_suggestion(
                        user_id=user_id,
                        stock_code=ticker,
                        stock_name=name,
                        target_price=current_price,
                        quantity=quantity,
                        reason=f"V9 갭상승 확률 {p['prob']*100:.1f}%",
                        score=int(p['prob'] * 100)
                    )
                    log(f"      → 제안 등록 완료")
                except Exception as e:
                    log(f"      → 제안 등록 실패: {e}")

            # 주문 간 딜레이
            import time
            time.sleep(0.5)

    except Exception as e:
        log(f"    에러: {e}")

log("\n" + "=" * 60)
log("V9 자동매매 완료")
log("=" * 60)
