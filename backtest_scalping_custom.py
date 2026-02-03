#!/usr/bin/env python3
"""
스캘핑 백테스트 시뮬레이션
조건:
- 익절: +2%
- 손절: -2%
- 최대 보유시간: 3분
- 재매수 허용 (블랙리스트 없음)
- 15:19 전량 매도
"""

import pandas as pd
import glob
from datetime import datetime, timedelta
from collections import defaultdict

# 설정 (실시간 테스트용)
PROFIT_TARGET = 3.0  # 익절 %
STOP_LOSS = -2.0     # 손절 %
MAX_HOLD_MINUTES = 15  # 최대 보유시간 (분)
CLOSE_TIME = "15:19"  # 전량 매도 시간
INVESTMENT_PER_TRADE = 100_000  # 거래당 투자금
TAX_FEE_RATE = 0.00203  # 세금+수수료 (매도대금의 0.203%)
MIN_V2_SCORE = 60  # V2 진입 조건

# 회전율 상위 20종목
TARGET_STOCKS = [
    '126640', '380550', '084670', '003310', '012210',
    '088130', '412350', '474170', '081180', '290660',
    '191410', '006220', '146060', '004560', '038460',
    '354200', '232680', '042940', '096690', '081580'
]

def load_intraday_data():
    """장중 스코어 데이터 로드"""
    files = sorted(glob.glob('/home/kimhc/Stock/output/intraday_scores/*.csv'))

    all_data = []
    for f in files:
        try:
            df = pd.read_csv(f)
            # 파일명에서 날짜/시간 추출 (YYYYMMDD_HHMM.csv)
            filename = f.split('/')[-1].replace('.csv', '')
            date_str = filename[:8]
            time_str = filename[9:13] if len(filename) > 9 else '0900'

            df['date'] = date_str
            df['time'] = time_str
            df['datetime'] = pd.to_datetime(date_str + time_str, format='%Y%m%d%H%M')
            df['code'] = df['code'].astype(str).str.zfill(6)

            all_data.append(df)
        except Exception as e:
            pass

    if not all_data:
        return None

    return pd.concat(all_data, ignore_index=True)

def simulate_scalping(data):
    """스캘핑 시뮬레이션"""

    # 대상 종목 필터
    data = data[data['code'].isin(TARGET_STOCKS)].copy()
    data = data.sort_values(['date', 'time', 'code'])

    # 날짜별 그룹
    dates = data['date'].unique()

    total_trades = []

    for date in dates:
        day_data = data[data['date'] == date].copy()

        # 종목별 시계열 정리
        stocks_timeline = {}
        for code in TARGET_STOCKS:
            stock_data = day_data[day_data['code'] == code].sort_values('time')
            if not stock_data.empty:
                stocks_timeline[code] = stock_data

        # 포지션 관리
        positions = {}  # {code: {'entry_price': x, 'entry_time': t, 'quantity': q}}

        # 시간대별 처리
        times = sorted(day_data['time'].unique())

        for t in times:
            current_time = t

            # 15:19 이후면 전량 매도
            if current_time >= "1519":
                for code, pos in list(positions.items()):
                    # 현재가 조회
                    stock_df = stocks_timeline.get(code)
                    if stock_df is not None:
                        current_row = stock_df[stock_df['time'] <= current_time].iloc[-1] if not stock_df[stock_df['time'] <= current_time].empty else None
                        if current_row is not None:
                            exit_price = current_row['close']
                            pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100
                            # 세금/수수료 차감 (매도대금의 0.203%)
                            sell_amount = exit_price * pos['quantity']
                            tax_fee = int(sell_amount * TAX_FEE_RATE)
                            gross_pnl = int(INVESTMENT_PER_TRADE * pnl_pct / 100)
                            pnl_amount = gross_pnl - tax_fee

                            total_trades.append({
                                'date': date,
                                'code': code,
                                'entry_time': pos['entry_time'],
                                'exit_time': current_time,
                                'entry_price': pos['entry_price'],
                                'exit_price': exit_price,
                                'pnl_pct': pnl_pct,
                                'pnl_amount': pnl_amount,
                                'tax_fee': tax_fee,
                                'exit_reason': '장마감정리'
                            })
                positions = {}
                continue

            # 각 종목 처리
            for code, stock_df in stocks_timeline.items():
                current_row = stock_df[stock_df['time'] == current_time]
                if current_row.empty:
                    continue
                current_row = current_row.iloc[0]
                current_price = current_row['close']

                # 포지션 있는 경우 - 청산 체크
                if code in positions:
                    pos = positions[code]
                    pnl_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100

                    # 보유시간 계산
                    entry_minutes = int(pos['entry_time'][:2]) * 60 + int(pos['entry_time'][2:])
                    current_minutes = int(current_time[:2]) * 60 + int(current_time[2:])
                    hold_minutes = current_minutes - entry_minutes

                    exit_reason = None

                    # 익절
                    if pnl_pct >= PROFIT_TARGET:
                        exit_reason = f'익절 {pnl_pct:.1f}%'
                    # 손절
                    elif pnl_pct <= STOP_LOSS:
                        exit_reason = f'손절 {pnl_pct:.1f}%'
                    # 시간초과
                    elif hold_minutes >= MAX_HOLD_MINUTES:
                        exit_reason = f'시간초과 {hold_minutes}분'

                    if exit_reason:
                        # 세금/수수료 차감 (매도대금의 0.203%)
                        sell_amount = current_price * pos['quantity']
                        tax_fee = int(sell_amount * TAX_FEE_RATE)
                        gross_pnl = int(INVESTMENT_PER_TRADE * pnl_pct / 100)
                        pnl_amount = gross_pnl - tax_fee

                        total_trades.append({
                            'date': date,
                            'code': code,
                            'entry_time': pos['entry_time'],
                            'exit_time': current_time,
                            'entry_price': pos['entry_price'],
                            'exit_price': current_price,
                            'pnl_pct': pnl_pct,
                            'pnl_amount': pnl_amount,
                            'tax_fee': tax_fee,
                            'exit_reason': exit_reason
                        })
                        del positions[code]

                # 포지션 없는 경우 - 진입 체크 (돌파 전략)
                if code not in positions and current_time < "1515":
                    # V2 >= 60 이고 변동성 있으면 진입
                    v2 = current_row.get('v2', 0)
                    change_pct = current_row.get('change_pct', 0)

                    # 진입 조건: V2 >= 70, 상승중 (0.5% ~ 5%)
                    if v2 >= MIN_V2_SCORE and 0.5 <= change_pct <= 5.0:
                        positions[code] = {
                            'entry_price': current_price,
                            'entry_time': current_time,
                            'quantity': int(INVESTMENT_PER_TRADE / current_price)
                        }

    return total_trades

def print_results(trades):
    """결과 출력"""
    if not trades:
        print("거래 없음")
        return

    df = pd.DataFrame(trades)

    print("=" * 70)
    print("스캘핑 백테스트 결과")
    print("=" * 70)
    print(f"조건: 익절 +{PROFIT_TARGET}%, 손절 {STOP_LOSS}%, 최대보유 {MAX_HOLD_MINUTES}분")
    print(f"대상: 회전율 TOP 20 종목")
    print(f"투자금/거래: {INVESTMENT_PER_TRADE:,}원")
    print("=" * 70)

    # 전체 통계
    total_trades = len(df)
    win_trades = len(df[df['pnl_pct'] > 0])
    loss_trades = len(df[df['pnl_pct'] < 0])
    even_trades = len(df[df['pnl_pct'] == 0])

    win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0

    total_pnl = df['pnl_amount'].sum()
    avg_pnl = df['pnl_pct'].mean()
    max_win = df['pnl_pct'].max()
    max_loss = df['pnl_pct'].min()

    print(f"\n[전체 통계]")
    print(f"  총 거래: {total_trades}건")
    print(f"  승/패/무: {win_trades}/{loss_trades}/{even_trades}")
    print(f"  승률: {win_rate:.1f}%")
    print(f"  평균 수익률: {avg_pnl:+.2f}%")
    print(f"  최대 수익: {max_win:+.2f}%")
    print(f"  최대 손실: {max_loss:+.2f}%")
    print(f"  총 손익: {total_pnl:+,}원")

    # 청산 사유별 통계
    print(f"\n[청산 사유별]")
    for reason in df['exit_reason'].unique():
        subset = df[df['exit_reason'].str.contains(reason.split()[0])]
        cnt = len(subset)
        pnl = subset['pnl_amount'].sum()
        print(f"  {reason.split()[0]}: {cnt}건, {pnl:+,}원")

    # 날짜별 통계
    print(f"\n[날짜별 손익]")
    for date in sorted(df['date'].unique()):
        day_df = df[df['date'] == date]
        day_trades = len(day_df)
        day_pnl = day_df['pnl_amount'].sum()
        day_win = len(day_df[day_df['pnl_pct'] > 0])
        day_rate = day_win / day_trades * 100 if day_trades > 0 else 0
        print(f"  {date}: {day_trades}건, 승률 {day_rate:.0f}%, 손익 {day_pnl:+,}원")

    # 상위 거래
    print(f"\n[최고 수익 거래 TOP 5]")
    top5 = df.nlargest(5, 'pnl_pct')
    for _, row in top5.iterrows():
        print(f"  {row['date']} {row['entry_time']}~{row['exit_time']} {row['code']}: {row['pnl_pct']:+.2f}% ({row['pnl_amount']:+,}원)")

    print(f"\n[최대 손실 거래 TOP 5]")
    bottom5 = df.nsmallest(5, 'pnl_pct')
    for _, row in bottom5.iterrows():
        print(f"  {row['date']} {row['entry_time']}~{row['exit_time']} {row['code']}: {row['pnl_pct']:+.2f}% ({row['pnl_amount']:+,}원)")

    print("=" * 70)

if __name__ == "__main__":
    print("장중 데이터 로드 중...")
    data = load_intraday_data()

    if data is None:
        print("데이터 로드 실패")
        exit(1)

    print(f"데이터 로드 완료: {len(data)}건, {data['date'].nunique()}일")

    print("\n시뮬레이션 실행 중...")
    trades = simulate_scalping(data)

    print_results(trades)
