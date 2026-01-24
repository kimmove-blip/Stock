#!/usr/bin/env python3
"""
V7 스윙 백테스트 시스템

V7 Trend Momentum Predictor 전용 백테스트:
- 매매 규칙: 다음날 시가 매수 → 목표가/손절가/트레일링스탑/시간손절 청산
- 목표가: 진입가 + ATR × 1.5
- 손절가: 진입가 - ATR × 0.8
- 트레일링: ATR×0.5 수익 시 본전 스탑
- 시간손절: 최대 3일 홀딩
- 2일차 손실 시 조기 청산
- 투자 적격: 60점 이상
"""

import os
import sys
import json
import pickle
import argparse
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
CHECKPOINT_DIR = OUTPUT_DIR / "backtest_v7"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

from scoring import calculate_score_v7


class SwingBacktestV7:
    """V7 스윙 백테스트 시스템"""

    def __init__(self, max_workers: int = 10, top_n: int = 10,
                 allocation: int = 300_000, min_score: int = 60,
                 target_mult: float = 1.5, stop_mult: float = 0.8,
                 max_hold_days: int = 3, no_marcap_limit: bool = False,
                 use_optimal_filter: bool = False):
        self.max_workers = max_workers
        self.stock_data_cache: Dict[str, pd.DataFrame] = {}
        self.all_stocks: Optional[pd.DataFrame] = None
        self.trading_days: List[datetime] = []

        self.top_n = top_n
        self.allocation = allocation
        self.min_score = min_score
        self.target_mult = target_mult
        self.stop_mult = stop_mult
        self.max_hold_days = max_hold_days
        self.no_marcap_limit = no_marcap_limit
        self.use_optimal_filter = use_optimal_filter  # V7.1 최적 필터

        self.results = {
            'daily': [],
            'trades': [],
        }

    def load_stock_list(self) -> pd.DataFrame:
        """종목 리스트 로드"""
        print("[1] 종목 리스트 로딩...")
        krx = fdr.StockListing("KRX")

        df = krx[['Code', 'Name', 'Market', 'Marcap', 'Amount', 'Close']].copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)

        df = df[df['Marcap'] >= 30_000_000_000]

        if not self.no_marcap_limit:
            df = df[df['Marcap'] <= 1_000_000_000_000]

        exclude_keywords = [
            '스팩', 'SPAC', '리츠', 'ETF', 'ETN', '인버스', '레버리지',
            '합병', '정리매매', '관리종목', '투자주의', '투자경고', '투자위험',
            '1호', '2호', '3호', '4호', '5호', '6호', '7호', '8호', '9호', '10호',
        ]
        for kw in exclude_keywords:
            df = df[~df['Name'].str.contains(kw, case=False, na=False)]

        df = df[df['Code'].str[-1] == '0']

        self.all_stocks = df
        print(f"    → {len(df):,}개 종목 로드 완료")
        return df

    def get_trading_days(self, start_date: str, end_date: str) -> List[datetime]:
        """거래일 목록 조회"""
        try:
            kospi = fdr.DataReader('KS11', start_date, end_date)
            return kospi.index.tolist()
        except Exception as e:
            print(f"거래일 조회 실패: {e}")
            return []

    def preload_all_ohlcv(self, start_date: str, end_date: str):
        """모든 종목 OHLCV 데이터 로드"""
        print(f"\n[2] 종목 데이터 로딩 중...")
        if self.all_stocks is None:
            self.load_stock_list()

        stocks_list = self.all_stocks['Code'].tolist()
        loaded = 0
        failed = 0

        def load_single(code):
            try:
                load_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
                load_end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=10)).strftime("%Y-%m-%d")
                df = fdr.DataReader(code, load_start, load_end)
                if df is not None and not df.empty and len(df) >= 60:
                    return code, df
            except:
                pass
            return code, None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(load_single, code): code for code in stocks_list}
            for future in as_completed(futures):
                code, df = future.result()
                if df is not None:
                    self.stock_data_cache[code] = df
                    loaded += 1
                else:
                    failed += 1

                if (loaded + failed) % 100 == 0:
                    print(f"    → {loaded + failed}/{len(stocks_list)} 처리 ({loaded} 성공, {failed} 실패)")

        print(f"    → 총 {loaded}개 종목 데이터 로드 완료 ({failed}개 실패)")
        return loaded

    def calculate_v7_scores(self, analysis_date: datetime) -> List[Dict]:
        """특정 날짜 기준으로 V7 스코어 계산"""
        date_str = analysis_date.strftime("%Y-%m-%d")
        results = []

        for code, df in self.stock_data_cache.items():
            try:
                df_filtered = df[df.index <= date_str].copy()
                if len(df_filtered) < 60:
                    continue

                stock_info = self.all_stocks[self.all_stocks['Code'] == code]
                if stock_info.empty:
                    continue
                name = stock_info.iloc[0]['Name']
                market = stock_info.iloc[0]['Market']

                v7_result = calculate_score_v7(df_filtered)
                if v7_result and not v7_result.get('disqualified') and v7_result['score'] >= self.min_score:
                    # V7.1 최적 필터: 추세<=15 & 모멘텀>=12 (역발상 반등 조건)
                    if self.use_optimal_filter:
                        if v7_result['trend_score'] > 15 or v7_result['momentum_score'] < 12:
                            continue  # 필터 조건 미충족 시 스킵
                    results.append({
                        'code': code,
                        'name': name,
                        'market': market,
                        'score': v7_result['score'],
                        'trend_score': v7_result['trend_score'],
                        'momentum_score': v7_result['momentum_score'],
                        'energy_score': v7_result['energy_score'],
                        'support_score': v7_result['support_score'],
                        'signals': v7_result['signals'],
                        'patterns': v7_result['patterns'],
                        'warnings': v7_result['warnings'],
                        'exit_strategy': v7_result['exit_strategy'],
                        'close': df_filtered.iloc[-1]['Close'],
                        'atr': v7_result['exit_strategy']['atr'],
                    })

            except Exception as e:
                continue

        return results

    def select_top_stocks(self, scored_stocks: List[Dict]) -> List[Dict]:
        """TOP N 종목 선정"""
        sorted_stocks = sorted(scored_stocks, key=lambda x: -x['score'])

        selected = []
        rank = 1

        for stock in sorted_stocks:
            if rank > self.top_n:
                break

            if stock['close'] > self.allocation:
                continue

            stock_with_rank = stock.copy()
            stock_with_rank['rank'] = rank
            stock_with_rank['allocation'] = self.allocation
            selected.append(stock_with_rank)
            rank += 1

        return selected

    def get_future_ohlcv(self, code: str, current_date: datetime, days: int = 10) -> Optional[pd.DataFrame]:
        """현재 날짜 이후 OHLCV 데이터 조회"""
        if code not in self.stock_data_cache:
            return None

        df = self.stock_data_cache[code]
        current_str = current_date.strftime("%Y-%m-%d")

        future_df = df[df.index > current_str].head(days + 1)
        if future_df.empty:
            return None

        return future_df

    def simulate_swing_trade_v7(self, stock: Dict, screening_date: datetime, max_gap_pct: float = 10.0) -> Optional[Dict]:
        """V7 스윙 거래 시뮬레이션 (트레일링 스탑, 조기 청산 포함)"""
        code = stock['code']

        future_df = self.get_future_ohlcv(code, screening_date, self.max_hold_days + 1)
        if future_df is None or len(future_df) < 2:
            return None

        entry_day = future_df.iloc[0]
        entry_date = future_df.index[0]
        entry_price = entry_day['Open']

        prev_close = stock['close']

        gap_pct = (entry_price - prev_close) / prev_close * 100
        if gap_pct >= max_gap_pct:
            return {
                'success': False,
                'reason': 'GAP_UP_SKIP',
                'gap_pct': round(gap_pct, 2),
                'code': code,
                'name': stock['name'],
            }

        atr = stock['atr']
        target_price = entry_price + (atr * self.target_mult)
        stop_price = entry_price - (atr * self.stop_mult)
        trailing_trigger = entry_price + (atr * 0.5)
        trailing_active = False

        shares = int(self.allocation // entry_price)
        if shares == 0:
            return None

        invested = shares * entry_price

        result = {
            'success': True,
            'screening_date': screening_date.strftime("%Y-%m-%d"),
            'entry_date': entry_date.strftime("%Y-%m-%d"),
            'code': code,
            'name': stock['name'],
            'market': stock['market'],
            'score': stock['score'],
            'trend_score': stock['trend_score'],
            'momentum_score': stock['momentum_score'],
            'energy_score': stock['energy_score'],
            'support_score': stock['support_score'],
            'rank': stock.get('rank', 0),
            'allocation': self.allocation,
            'prev_close': prev_close,
            'entry_price': entry_price,
            'gap_pct': round(gap_pct, 2),
            'target_price': round(target_price, 2),
            'stop_price': round(stop_price, 2),
            'shares': shares,
            'invested': invested,
            'exit_date': None,
            'exit_price': None,
            'exit_reason': None,
            'hold_days': 0,
            'pnl': 0,
            'return_pct': 0,
            'signals': stock['signals'][:5],
            'patterns': stock['patterns'],
            'warnings': stock['warnings'],
        }

        for day_offset in range(1, min(len(future_df), self.max_hold_days + 1)):
            day_data = future_df.iloc[day_offset]
            day_date = future_df.index[day_offset]

            # 트레일링 스탑 활성화
            if day_data['High'] >= trailing_trigger and not trailing_active:
                trailing_active = True
                stop_price = max(stop_price, entry_price)

            # 목표가 도달
            if day_data['High'] >= target_price:
                result['exit_date'] = day_date.strftime("%Y-%m-%d")
                result['exit_price'] = target_price
                result['exit_reason'] = 'TARGET_HIT'
                result['hold_days'] = day_offset
                break

            # 손절가 이탈
            if day_data['Low'] <= stop_price:
                result['exit_date'] = day_date.strftime("%Y-%m-%d")
                result['exit_price'] = stop_price
                result['exit_reason'] = 'TRAILING_STOP' if trailing_active else 'STOP_HIT'
                result['hold_days'] = day_offset
                break

            # 2일차 손실 시 조기 청산
            if day_offset >= 2 and day_data['Close'] < entry_price:
                result['exit_date'] = day_date.strftime("%Y-%m-%d")
                result['exit_price'] = day_data['Close']
                result['exit_reason'] = 'EARLY_EXIT'
                result['hold_days'] = day_offset
                break

            # 마지막 날 종가 청산
            if day_offset == self.max_hold_days or day_offset == len(future_df) - 1:
                result['exit_date'] = day_date.strftime("%Y-%m-%d")
                result['exit_price'] = day_data['Close']
                result['exit_reason'] = 'TIME_EXIT'
                result['hold_days'] = day_offset
                break

        if result['exit_price']:
            revenue = shares * result['exit_price']
            result['pnl'] = round(revenue - invested, 0)
            result['return_pct'] = round((result['exit_price'] - entry_price) / entry_price * 100, 2)

        return result

    def save_checkpoint(self, processed_days: int):
        """체크포인트 저장"""
        checkpoint_file = CHECKPOINT_DIR / "checkpoint_v7.pkl"
        with open(checkpoint_file, 'wb') as f:
            pickle.dump({
                'processed_days': processed_days,
                'results': self.results,
            }, f)
        print(f"    체크포인트 저장 완료 ({processed_days}일 처리)")

    def run_backtest(self, weeks: int = 52, resume: bool = False):
        """백테스트 실행"""
        print("\n" + "=" * 80)
        print("  V7 Trend Momentum Predictor 백테스트 시스템")
        print("  스윙 트레이딩: 목표가/손절가/트레일링스탑/조기청산")
        print("=" * 80)

        end_date = datetime.now() - timedelta(days=10)
        start_date = end_date - timedelta(weeks=weeks)

        print(f"  기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} ({weeks}주)")
        print(f"  목표가: 진입가 + ATR × {self.target_mult}")
        print(f"  손절가: 진입가 - ATR × {self.stop_mult}")
        print(f"  트레일링: ATR×0.5 수익 시 본전 스탑")
        print(f"  시간손절: 최대 {self.max_hold_days}일 홀딩")
        print(f"  2일차 손실 시 조기 청산")
        print(f"  투자 적격: {self.min_score}점 이상")
        print(f"  투자 한도: TOP {self.top_n} 종목 각 {self.allocation:,}원")
        print(f"  갭상승 스킵: 10% 이상")
        if self.use_optimal_filter:
            print(f"  ★ V7.1 최적 필터: 추세<=15 & 모멘텀>=12")
        print("=" * 80)

        start_idx = 0

        self.load_stock_list()
        self.preload_all_ohlcv(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )

        print(f"\n[3] 거래일 조회...")
        self.trading_days = self.get_trading_days(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
        self.trading_days = self.trading_days[:-self.max_hold_days]
        print(f"    → {len(self.trading_days)}개 거래일")

        print(f"\n[4] 백테스트 실행...")

        for i, screening_date in enumerate(self.trading_days[start_idx:], start=start_idx):
            date_str = screening_date.strftime("%Y-%m-%d")
            progress = (i + 1) / len(self.trading_days) * 100
            print(f"\r    {date_str} 처리 중... ({i + 1}/{len(self.trading_days)}, {progress:.1f}%)", end="", flush=True)

            scored_stocks = self.calculate_v7_scores(screening_date)
            selected = self.select_top_stocks(scored_stocks)

            daily_result = {
                'screening_date': date_str,
                'candidates': len(scored_stocks),
                'selected': len(selected),
                'trades': [],
                'skipped': [],
                'total_invested': 0,
                'total_pnl': 0,
                'wins': 0,
                'losses': 0,
            }

            for stock in selected:
                trade = self.simulate_swing_trade_v7(stock, screening_date)
                if trade is None:
                    continue

                if not trade['success']:
                    daily_result['skipped'].append(trade)
                    continue

                daily_result['trades'].append(trade)
                daily_result['total_invested'] += trade['invested']
                daily_result['total_pnl'] += trade['pnl']
                if trade['pnl'] > 0:
                    daily_result['wins'] += 1
                else:
                    daily_result['losses'] += 1

                self.results['trades'].append(trade)

            self.results['daily'].append(daily_result)

            if (i + 1) % 10 == 0:
                self.save_checkpoint(i + 1)

        print(f"\n    → 백테스트 완료")

        self.save_results()
        self.print_summary()

    def save_results(self):
        """결과 저장"""
        print(f"\n[5] 결과 저장 중...")
        date_str = datetime.now().strftime("%Y%m%d")

        excel_path = OUTPUT_DIR / f"backtest_swing_v7_{date_str}.xlsx"

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            trades = self.results['trades']
            if trades:
                total_trades = len(trades)
                wins = len([t for t in trades if t['pnl'] > 0])
                total_invested = sum(t['invested'] for t in trades)
                total_pnl = sum(t['pnl'] for t in trades)

                target_hits = [t for t in trades if t['exit_reason'] == 'TARGET_HIT']
                stop_hits = [t for t in trades if t['exit_reason'] == 'STOP_HIT']
                trailing_stops = [t for t in trades if t['exit_reason'] == 'TRAILING_STOP']
                early_exits = [t for t in trades if t['exit_reason'] == 'EARLY_EXIT']
                time_exits = [t for t in trades if t['exit_reason'] == 'TIME_EXIT']

                summary_data = [{
                    '항목': '총 거래 수', '값': total_trades,
                }, {
                    '항목': '승리', '값': wins,
                }, {
                    '항목': '패배', '값': total_trades - wins,
                }, {
                    '항목': '승률(%)', '값': round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
                }, {
                    '항목': '총 투자액', '값': int(total_invested),
                }, {
                    '항목': '총 손익', '값': int(total_pnl),
                }, {
                    '항목': '수익률(%)', '값': round(total_pnl / total_invested * 100, 2) if total_invested > 0 else 0,
                }, {
                    '항목': '평균 홀딩일', '값': round(sum(t['hold_days'] for t in trades) / total_trades, 1) if total_trades > 0 else 0,
                }, {
                    '항목': '---', '값': '---',
                }, {
                    '항목': '목표가 청산', '값': len(target_hits),
                }, {
                    '항목': '손절가 청산', '값': len(stop_hits),
                }, {
                    '항목': '트레일링 스탑', '값': len(trailing_stops),
                }, {
                    '항목': '조기 청산', '값': len(early_exits),
                }, {
                    '항목': '시간 청산', '값': len(time_exits),
                }]

                pd.DataFrame(summary_data).to_excel(writer, sheet_name='요약', index=False)

            if trades:
                trade_data = []
                for t in trades:
                    trade_data.append({
                        '스크리닝일': t['screening_date'],
                        '진입일': t['entry_date'],
                        '청산일': t['exit_date'],
                        '종목코드': t['code'],
                        '종목명': t['name'],
                        '점수': t['score'],
                        '추세': t['trend_score'],
                        '모멘텀': t['momentum_score'],
                        '에너지': t['energy_score'],
                        '수급': t['support_score'],
                        '진입가': int(t['entry_price']),
                        '갭(%)': t['gap_pct'],
                        '청산가': int(t['exit_price']) if t['exit_price'] else 0,
                        '청산사유': t['exit_reason'],
                        '홀딩일': t['hold_days'],
                        '손익': int(t['pnl']),
                        '수익률(%)': t['return_pct'],
                    })

                pd.DataFrame(trade_data).to_excel(writer, sheet_name='거래상세', index=False)

            # 청산유형별 성과
            if trades:
                exit_types = ['TARGET_HIT', 'STOP_HIT', 'TRAILING_STOP', 'EARLY_EXIT', 'TIME_EXIT']
                exit_data = []
                for exit_type in exit_types:
                    type_trades = [t for t in trades if t['exit_reason'] == exit_type]
                    if type_trades:
                        wins = len([t for t in type_trades if t['pnl'] > 0])
                        total_pnl = sum(t['pnl'] for t in type_trades)
                        total_invested = sum(t['invested'] for t in type_trades)
                        exit_data.append({
                            '청산유형': exit_type,
                            '거래수': len(type_trades),
                            '승률(%)': round(wins / len(type_trades) * 100, 1),
                            '총손익': int(total_pnl),
                            '평균수익률(%)': round(sum(t['return_pct'] for t in type_trades) / len(type_trades), 2),
                        })

                pd.DataFrame(exit_data).to_excel(writer, sheet_name='청산유형별', index=False)

        print(f"    → Excel 저장: {excel_path}")

        # JSON
        json_path = OUTPUT_DIR / f"backtest_swing_v7_{date_str}.json"
        trades = self.results['trades']
        if trades:
            json_data = {
                'run_date': date_str,
                'config': {
                    'target_mult': self.target_mult,
                    'stop_mult': self.stop_mult,
                    'max_hold_days': self.max_hold_days,
                    'min_score': self.min_score,
                },
                'summary': {
                    'total_trades': len(trades),
                    'wins': len([t for t in trades if t['pnl'] > 0]),
                    'win_rate': round(len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100, 1),
                    'total_pnl': int(sum(t['pnl'] for t in trades)),
                    'return_pct': round(sum(t['pnl'] for t in trades) / sum(t['invested'] for t in trades) * 100, 2),
                },
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            print(f"    → JSON 저장: {json_path}")

    def print_summary(self):
        """결과 요약 출력"""
        print("\n" + "=" * 80)
        print("  V7 Trend Momentum Predictor 백테스트 결과")
        print("=" * 80)

        trades = self.results['trades']
        if not trades:
            print("  거래 없음")
            return

        total_trades = len(trades)
        wins = len([t for t in trades if t['pnl'] > 0])
        total_invested = sum(t['invested'] for t in trades)
        total_pnl = sum(t['pnl'] for t in trades)

        print(f"\n  총 거래: {total_trades}회")
        print(f"  승/패: {wins} / {total_trades - wins}")
        print(f"  승률: {wins / total_trades * 100:.1f}%")
        print(f"  총 투자액: {total_invested:,.0f}원")
        print(f"  총 손익: {total_pnl:+,.0f}원")
        print(f"  수익률: {total_pnl / total_invested * 100:+.2f}%")
        print(f"  평균 홀딩일: {sum(t['hold_days'] for t in trades) / total_trades:.1f}일")

        print(f"\n  --- 청산 유형별 ---")
        for exit_type in ['TARGET_HIT', 'STOP_HIT', 'TRAILING_STOP', 'EARLY_EXIT', 'TIME_EXIT']:
            type_trades = [t for t in trades if t['exit_reason'] == exit_type]
            if type_trades:
                type_wins = len([t for t in type_trades if t['pnl'] > 0])
                type_pnl = sum(t['pnl'] for t in type_trades)
                print(f"  {exit_type}: {len(type_trades)}회, 승률 {type_wins/len(type_trades)*100:.1f}%, 손익 {type_pnl:+,.0f}원")

        print("-" * 80)


def main():
    parser = argparse.ArgumentParser(description='V7 스윙 백테스트')
    parser.add_argument('--weeks', type=int, default=52, help='백테스트 기간 (주 단위)')
    parser.add_argument('--workers', type=int, default=10, help='병렬 처리 워커 수')
    parser.add_argument('--top-n', type=int, default=10, help='TOP N 종목 수')
    parser.add_argument('--allocation', type=int, default=300_000, help='종목당 투자 금액')
    parser.add_argument('--min-score', type=int, default=60, help='최소 투자 점수')
    parser.add_argument('--target-mult', type=float, default=1.5, help='목표가 ATR 배율')
    parser.add_argument('--stop-mult', type=float, default=0.8, help='손절가 ATR 배율')
    parser.add_argument('--max-hold', type=int, default=3, help='최대 홀딩일')
    parser.add_argument('--no-marcap-limit', action='store_true', help='시총 상한 제거')
    parser.add_argument('--optimal-filter', action='store_true', help='V7.1 최적 필터 (추세<=15 & 모멘텀>=12)')
    args = parser.parse_args()

    backtester = SwingBacktestV7(
        max_workers=args.workers,
        top_n=args.top_n,
        allocation=args.allocation,
        min_score=args.min_score,
        target_mult=args.target_mult,
        stop_mult=args.stop_mult,
        max_hold_days=args.max_hold,
        no_marcap_limit=args.no_marcap_limit,
        use_optimal_filter=args.optimal_filter,
    )
    backtester.run_backtest(weeks=args.weeks)


if __name__ == "__main__":
    main()
