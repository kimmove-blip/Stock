#!/usr/bin/env python3
"""
V9 보유종목 진단 - 내일 갭 상승 확률 분석 및 매도
- 매일 15:10 실행 (크론)
- 보유 종목의 갭 상승 확률 계산
- 확률 50% 미만: auto→자동매도, semi→매도제안
"""
import sys
sys.path.insert(0, '/home/kimhc/Stock')

import pandas as pd
import numpy as np
from pykrx import stock
import pickle
from datetime import datetime, timedelta
import sqlite3
import warnings
warnings.filterwarnings('ignore')

from trading.trade_logger import TradeLogger
from api.services.kis_client import KISClient

SELL_THRESHOLD = 0.50  # 50% 미만이면 매도
MODEL_PATH = '/home/kimhc/Stock/models/gap_model_v9.pkl'
DB_PATH = '/home/kimhc/Stock/database/auto_trade.db'
LOG_FILE = '/home/kimhc/Stock/output/auto_trade_v9_diagnose.log'

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

log("=" * 60)
log("V9 보유종목 진단 시작")
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
    log(f"    완료 (피처 {len(fcols)}개)")
except Exception as e:
    log(f"    실패: {e}")
    sys.exit(1)

# =============================================================================
# 2. 최근 거래일 확인
# =============================================================================
log("[2] 최근 거래일 확인...")
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
# 3. 피처 계산 함수 (백테스트와 동일)
# =============================================================================
def calculate_features(df, idx):
    if idx < 20:
        return None

    row = df.iloc[idx]
    prev_rows = df.iloc[idx-20:idx]

    o, h, l, c, v = row['시가'], row['고가'], row['저가'], row['종가'], row['거래량']

    if o == 0 or c == 0 or v == 0:
        return None

    features = {}

    body = abs(c - o)
    total_range = h - l if h > l else 1

    features['close_pos'] = (c - l) / total_range if total_range > 0 else 0.5
    features['close_high'] = (c - l) / (h - l) if h > l else 0.5
    features['is_bull'] = 1 if c > o else 0
    features['body_ratio'] = body / total_range if total_range > 0 else 0
    features['upper_wick'] = (h - max(o, c)) / total_range if total_range > 0 else 0
    features['lower_wick'] = (min(o, c) - l) / total_range if total_range > 0 else 0

    prev_close = df.iloc[idx-1]['종가']
    features['day_change'] = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0

    ma5 = prev_rows['종가'].tail(5).mean()
    ma20 = prev_rows['종가'].mean()
    features['dist_ma5'] = (c - ma5) / ma5 * 100 if ma5 > 0 else 0
    features['dist_ma20'] = (c - ma20) / ma20 * 100 if ma20 > 0 else 0

    avg_vol = prev_rows['거래량'].mean()
    features['vol_ratio'] = v / avg_vol if avg_vol > 0 else 1

    recent_vol = prev_rows['거래량'].tail(5).mean()
    older_vol = prev_rows['거래량'].head(15).mean()
    features['vol_declining'] = 1 if recent_vol < older_vol * 0.7 else 0

    changes = prev_rows['종가'].diff()
    gains = changes.where(changes > 0, 0).mean()
    losses = (-changes.where(changes < 0, 0)).mean()
    features['rsi'] = gains / (gains + losses) * 100 if gains + losses > 0 else 50
    features['rsi_overbought'] = 1 if features['rsi'] > 70 else 0

    recent_5 = df.iloc[idx-4:idx+1]
    features['consec_bull'] = sum(1 for i in range(len(recent_5))
                                   if recent_5.iloc[i]['종가'] > recent_5.iloc[i]['시가'])

    ma5_val = df.iloc[idx-4:idx+1]['종가'].mean()
    ma10_val = df.iloc[idx-9:idx+1]['종가'].mean()
    ma20_val = df.iloc[idx-19:idx+1]['종가'].mean()
    features['aligned'] = 1 if c > ma5_val > ma10_val > ma20_val else 0

    high_20d = prev_rows['고가'].max()
    low_20d = prev_rows['저가'].min()
    features['near_high_20d'] = c / high_20d if high_20d > 0 else 0
    features['from_low_20d'] = (c - low_20d) / low_20d * 100 if low_20d > 0 else 0

    features['volatility'] = prev_rows['종가'].pct_change().std() * 100
    features['trade_value'] = row['거래량'] * c / 100000000
    features['is_surge'] = 1 if features['day_change'] >= 15 else 0

    if idx >= 2:
        prev_prev_close = df.iloc[idx-2]['종가']
        two_day_change = (c - prev_prev_close) / prev_prev_close * 100
        features['two_day_surge'] = 1 if two_day_change >= 20 else 0
    else:
        features['two_day_surge'] = 0

    return features

def get_stock_probability(ticker):
    """종목의 갭 상승 확률 계산"""
    try:
        start = (datetime.strptime(TARGET_DATE, '%Y%m%d') - timedelta(days=60)).strftime('%Y%m%d')
        df = stock.get_market_ohlcv(start, TARGET_DATE, ticker)

        if len(df) < 21:
            return None
        if df.index[-1].strftime('%Y%m%d') != TARGET_DATE:
            return None

        features = calculate_features(df, len(df) - 1)
        if features is None:
            return None

        X = pd.DataFrame([features])[fcols]
        prob = model.predict_proba(X)[0][1]
        return prob
    except Exception as e:
        return None

# =============================================================================
# 4. 계정별 보유종목 진단 및 매도
# =============================================================================
log("[3] 계정별 보유종목 진단...")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT s.user_id, s.trade_mode, k.is_mock
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

for user_id, trade_mode, is_mock in accounts:
    log(f"\n  [User {user_id}] {'모의' if is_mock else '실전'}투자 ({trade_mode} 모드)")

    try:
        # API 키 로드
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

        # 보유종목 조회
        balance = client.get_account_balance()
        if not balance:
            log(f"    잔고 조회 실패")
            continue

        holdings = balance.get('holdings', [])
        if not holdings:
            log(f"    보유종목 없음")
            continue

        log(f"    보유종목 {len(holdings)}개 진단 중...")

        sell_candidates = []

        for h in holdings:
            ticker = h.get('stock_code', '')
            name = h.get('stock_name', '')
            qty = h.get('quantity', 0)

            if qty <= 0:
                continue

            prob = get_stock_probability(ticker)

            if prob is None:
                log(f"      {name}: 확률 계산 불가")
                continue

            status = "유지" if prob >= SELL_THRESHOLD else "매도대상"
            log(f"      {name}: 갭상승 확률 {prob*100:.1f}% → {status}")

            if prob < SELL_THRESHOLD:
                sell_candidates.append({
                    'ticker': ticker,
                    'name': name,
                    'quantity': qty,
                    'prob': prob
                })

        if not sell_candidates:
            log(f"    매도 대상 없음")
            continue

        log(f"    매도 대상 {len(sell_candidates)}개")

        # 매도 실행 또는 제안
        for s in sell_candidates:
            ticker = s['ticker']
            name = s['name']
            qty = s['quantity']
            prob = s['prob']

            if trade_mode == 'auto':
                # AUTO 모드: 자동 매도
                log(f"    {name}: {qty}주 매도 [자동매도]")
                result = client.place_order(
                    stock_code=ticker,
                    side='sell',
                    quantity=qty,
                    price=0,
                    order_type='01'
                )

                if result.get('success'):
                    log(f"      → 주문 성공: {result.get('order_no')}")
                    trade_logger.log_order(
                        user_id=user_id,
                        stock_code=ticker,
                        stock_name=name,
                        side='sell',
                        quantity=qty,
                        price=0,
                        order_no=result.get('order_no'),
                        reason=f"V9 진단매도 (갭확률 {prob*100:.1f}% < 50%)"
                    )
                else:
                    log(f"      → 주문 실패: {result.get('error')}")

            else:
                # SEMI 모드: 매도 제안
                log(f"    {name}: {qty}주 매도 [제안등록]")
                try:
                    # 현재가 조회
                    price_data = client.get_current_price(ticker)
                    current_price = price_data.get('current_price', 0) if price_data else 0

                    trade_logger.add_sell_suggestion(
                        user_id=user_id,
                        stock_code=ticker,
                        stock_name=name,
                        target_price=current_price,
                        quantity=qty,
                        reason=f"V9 갭확률 {prob*100:.1f}% (50% 미만)"
                    )
                    log(f"      → 제안 등록 완료")
                except Exception as e:
                    log(f"      → 제안 등록 실패: {e}")

            import time
            time.sleep(0.5)

    except Exception as e:
        log(f"    에러: {e}")

log("\n" + "=" * 60)
log("V9 보유종목 진단 완료")
log("=" * 60)
