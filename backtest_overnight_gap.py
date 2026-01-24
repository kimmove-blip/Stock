#!/usr/bin/env python3
"""
오버나잇 갭 전략 백테스트

전략:
- 종가 매수 → 익일 시가 매도
- 하루만 보유 (오버나잇)
- 갭상승/갭하락 수익 실현

핵심 가정:
- "오늘 강했던 종목이 내일도 강하다" (모멘텀 연속성)
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from scoring import calculate_score_v5


class OvernightGapBacktester:
    """오버나잇 갭 전략 백테스터"""

    def __init__(
        self,
        max_workers: int = 10,
        top_n: int = 10,
        allocation: int = 300_000,
        min_score: int = 60,
        scoring_version: str = 'v5',
    ):
        self.max_workers = max_workers
        self.top_n = top_n  # 일일 매수 종목 수
        self.allocation = allocation  # 종목당 투자금
        self.min_score = min_score  # 최소 진입 점수
        self.scoring_version = scoring_version

        # 결과 저장
        self.trades: List[Dict] = []
        self.daily_results: List[Dict] = []
        self.stock_data_cache: Dict[str, pd.DataFrame] = {}
        self.stock_names: Dict[str, str] = {}

    def load_stock_list(self) -> pd.DataFrame:
        """KOSPI/KOSDAQ 종목 리스트 로드"""
        print("\n[1] 종목 리스트 로딩...")

        krx = fdr.StockListing("KRX")
        df = krx[['Code', 'Name', 'Market', 'Marcap', 'Amount', 'Close']].copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)

        # 시총 필터 (300억 ~ 1조)
        df = df[df['Marcap'] >= 30_000_000_000]
        df = df[df['Marcap'] <= 1_000_000_000_000]

        # 제외 종목
        exclude_keywords = [
            '스팩', 'SPAC', '리츠', 'ETF', 'ETN', '인버스', '레버리지',
            '합병', '정리매매', '관리종목', '투자주의', '투자경고', '투자위험',
            '1호', '2호', '3호', '4호', '5호', '6호', '7호', '8호', '9호', '10호',
        ]
        for kw in exclude_keywords:
            df = df[~df['Name'].str.contains(kw, case=False, na=False)]

        # 우선주 제외
        df = df[df['Code'].str[-1] == '0']

        self.all_stocks = df
        print(f"    → {len(df):,}개 종목 로드 완료")
        return df

    def load_stock_data(self, start_date: str, end_date: str):
        """종목 데이터 로드 (병렬 처리)"""
        print("\n[2] 종목 데이터 로딩 중...")

        if self.all_stocks is None:
            self.load_stock_list()

        stocks_list = self.all_stocks['Code'].tolist()
        stock_names_map = dict(zip(self.all_stocks['Code'], self.all_stocks['Name']))

        # 충분한 과거 데이터 (스코어링용 60일 + 백테스트 기간)
        extended_start = (datetime.strptime(start_date, '%Y%m%d') - timedelta(days=120)).strftime('%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y%m%d').strftime('%Y-%m-%d')

        def fetch_single(code: str) -> Optional[tuple]:
            try:
                df = fdr.DataReader(code, extended_start, end_dt)
                if df is None or len(df) < 60:
                    return None

                # 거래 없는 날 제외
                df = df[df['Volume'] > 0]

                if len(df) < 60:
                    return None

                return (code, df, stock_names_map.get(code, code))

            except Exception:
                return None

        success = 0
        fail = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_single, code): code for code in stocks_list}

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result:
                    ticker, df, name = result
                    self.stock_data_cache[ticker] = df
                    self.stock_names[ticker] = name
                    success += 1
                else:
                    fail += 1

                if i % 100 == 0:
                    print(f"    → {i}/{len(stocks_list)} 처리 ({success} 성공, {fail} 실패)")

        print(f"    → 총 {len(self.stock_data_cache):,}개 종목 데이터 로드 완료 ({fail}개 실패)")

    def get_trading_days(self, start_date: str, end_date: str) -> List[datetime]:
        """거래일 목록 조회"""
        print("\n[3] 거래일 조회...")

        try:
            start_dt = datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d').strftime('%Y-%m-%d')
            kospi = fdr.DataReader('KS11', start_dt, end_dt)
            trading_days = kospi.index.tolist()
            print(f"    → {len(trading_days)}개 거래일")
            return trading_days
        except Exception as e:
            print(f"거래일 조회 실패: {e}")
            return []

    def calculate_scores_for_date(self, trade_date: datetime) -> List[Dict]:
        """특정 날짜의 모든 종목 스코어 계산"""
        candidates = []

        for ticker, df in self.stock_data_cache.items():
            try:
                # 해당 날짜까지의 데이터만 사용
                df_until = df[df.index <= trade_date]
                if len(df_until) < 60:
                    continue

                # 해당 날짜가 데이터에 있는지 확인 (날짜만 비교)
                dates_only = df_until.index.normalize()
                if trade_date.normalize() not in dates_only:
                    continue

                # V5 스코어 계산
                result = calculate_score_v5(df_until)
                if result and result['score'] >= self.min_score:
                    today = df_until.iloc[-1]

                    # 상한가 종목 제외 (당일 등락률 +25% 이상 = 매수 불가)
                    if len(df_until) >= 2:
                        prev_close = df_until.iloc[-2]['Close']
                        today_change = (today['Close'] - prev_close) / prev_close * 100
                        if today_change >= 25:
                            continue  # 상한가 근접 - 매수 불가

                    candidates.append({
                        'ticker': ticker,
                        'name': self.stock_names.get(ticker, ticker),
                        'score': result['score'],
                        'close': today['Close'],  # 종가 (매수가)
                        'volume': today['Volume'],
                        'change_pct': today_change if len(df_until) >= 2 else 0,
                        'signals': result.get('signals', [])[:5],
                        'patterns': result.get('patterns', []),
                    })

            except Exception:
                continue

        # 점수 높은 순 정렬
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:self.top_n]

    def simulate_trade(self, entry_date: datetime, ticker: str, entry_price: float) -> Optional[Dict]:
        """단일 거래 시뮬레이션 (종가 매수 → 익일 시가 매도)"""
        try:
            df = self.stock_data_cache[ticker]

            # 익일 찾기
            future_dates = df[df.index > entry_date].index
            if len(future_dates) == 0:
                return None  # 다음 거래일 없음

            next_date = future_dates[0]
            next_day = df.loc[next_date]

            exit_price = next_day['Open']  # 익일 시가에 매도

            # 갭 비율 계산
            gap_pct = (exit_price - entry_price) / entry_price * 100

            # 투자 수량 및 손익 계산
            quantity = int(self.allocation / entry_price)
            if quantity == 0:
                return None

            invested = quantity * entry_price
            exit_amount = quantity * exit_price
            profit = exit_amount - invested
            profit_pct = (exit_price - entry_price) / entry_price * 100

            return {
                'ticker': ticker,
                'name': self.stock_names.get(ticker, ticker),
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'exit_date': next_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_price': exit_price,
                'gap_pct': gap_pct,
                'quantity': quantity,
                'invested': invested,
                'exit_amount': exit_amount,
                'profit': profit,
                'profit_pct': profit_pct,
                'is_win': profit > 0,
            }

        except Exception:
            return None

    def run_backtest(self, weeks: int = 12):
        """백테스트 실행"""
        # 기간 설정
        end_date = datetime.now() - timedelta(days=10)  # 최근 10일 제외 (데이터 안정성)
        start_date = end_date - timedelta(weeks=weeks)

        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')

        print("=" * 80)
        print("  오버나잇 갭 전략 백테스트 시스템")
        print("  종가 매수 → 익일 시가 매도")
        print("=" * 80)
        print(f"  기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} ({weeks}주)")
        print(f"  스코어링: {self.scoring_version.upper()} (장대양봉)")
        print(f"  투자 적격: {self.min_score}점 이상")
        print(f"  일일 매수: TOP {self.top_n} 종목")
        print(f"  종목당 투자: {self.allocation:,}원")
        print("=" * 80)

        # 종목 데이터 로드
        self.load_stock_list()
        self.load_stock_data(start_str, end_str)

        # 거래일 목록
        trading_days = self.get_trading_days(start_str, end_str)

        if len(trading_days) < 2:
            print("    → 거래일 부족")
            return

        # 마지막 날은 익일 시가가 없으므로 제외
        trading_days = trading_days[:-1]

        print(f"\n[4] 백테스트 실행 ({len(trading_days)}일)...")

        for i, trade_date in enumerate(trading_days, 1):
            date_str = trade_date.strftime('%Y%m%d')
            print(f"\r    {trade_date.strftime('%Y-%m-%d')} 처리 중... ({i}/{len(trading_days)}, {i/len(trading_days)*100:.1f}%)", end='')

            # 해당 날짜 종목 스코어링
            candidates = self.calculate_scores_for_date(trade_date)

            daily_trades = []
            daily_profit = 0
            daily_invested = 0

            for cand in candidates:
                trade = self.simulate_trade(trade_date, cand['ticker'], cand['close'])
                if trade:
                    trade['score'] = cand['score']
                    trade['signals'] = cand['signals']
                    trade['entry_change_pct'] = cand.get('change_pct', 0)  # 매수일 등락률
                    self.trades.append(trade)
                    daily_trades.append(trade)
                    daily_profit += trade['profit']
                    daily_invested += trade['invested']

            if daily_trades:
                self.daily_results.append({
                    'date': trade_date.strftime('%Y-%m-%d'),
                    'num_trades': len(daily_trades),
                    'invested': daily_invested,
                    'profit': daily_profit,
                    'profit_pct': daily_profit / daily_invested * 100 if daily_invested > 0 else 0,
                    'wins': sum(1 for t in daily_trades if t['is_win']),
                })

        print("\n    → 백테스트 완료")

        # 결과 저장
        self.save_results()

        # 결과 출력
        self.print_summary()

    def save_results(self):
        """결과 저장"""
        print("\n[5] 결과 저장 중...")

        today = datetime.now().strftime('%Y%m%d')
        output_dir = os.path.join(project_root, 'output')
        os.makedirs(output_dir, exist_ok=True)

        # Excel 저장
        excel_path = os.path.join(output_dir, f'backtest_overnight_gap_{today}.xlsx')

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # 거래 내역
            if self.trades:
                trades_df = pd.DataFrame(self.trades)
                trades_df.to_excel(writer, sheet_name='거래내역', index=False)

            # 일별 성과
            if self.daily_results:
                daily_df = pd.DataFrame(self.daily_results)
                daily_df.to_excel(writer, sheet_name='일별성과', index=False)

            # 요약
            summary = self._get_summary_dict()
            summary_df = pd.DataFrame([summary])
            summary_df.to_excel(writer, sheet_name='요약', index=False)

        print(f"    → Excel 저장: {excel_path}")

        # JSON 저장
        json_path = os.path.join(output_dir, f'backtest_overnight_gap_{today}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'summary': self._get_summary_dict(),
                'trades': self.trades,
                'daily_results': self.daily_results,
            }, f, ensure_ascii=False, indent=2, default=str)

        print(f"    → JSON 저장: {json_path}")

    def _get_summary_dict(self) -> Dict:
        """요약 통계"""
        if not self.trades:
            return {'total_trades': 0}

        total_trades = len(self.trades)
        wins = sum(1 for t in self.trades if t['is_win'])
        losses = total_trades - wins

        total_invested = sum(t['invested'] for t in self.trades)
        total_profit = sum(t['profit'] for t in self.trades)

        # 갭 분석
        gap_pcts = [t['gap_pct'] for t in self.trades]
        positive_gaps = [g for g in gap_pcts if g > 0]
        negative_gaps = [g for g in gap_pcts if g < 0]

        return {
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': wins / total_trades * 100,
            'total_invested': total_invested,
            'total_profit': total_profit,
            'profit_rate': total_profit / total_invested * 100 if total_invested > 0 else 0,
            'avg_gap_pct': np.mean(gap_pcts),
            'max_gap_pct': max(gap_pcts),
            'min_gap_pct': min(gap_pcts),
            'positive_gap_count': len(positive_gaps),
            'positive_gap_avg': np.mean(positive_gaps) if positive_gaps else 0,
            'negative_gap_count': len(negative_gaps),
            'negative_gap_avg': np.mean(negative_gaps) if negative_gaps else 0,
        }

    def print_summary(self):
        """결과 요약 출력"""
        summary = self._get_summary_dict()

        print("\n" + "=" * 80)
        print("  오버나잇 갭 전략 백테스트 결과")
        print("=" * 80)

        if summary['total_trades'] == 0:
            print("\n  거래 없음")
            return

        print(f"""
  총 거래: {summary['total_trades']}회
  승/패: {summary['wins']} / {summary['losses']}
  승률: {summary['win_rate']:.1f}%
  총 투자액: {summary['total_invested']:,.0f}원
  총 손익: {summary['total_profit']:+,.0f}원
  수익률: {summary['profit_rate']:+.2f}%

  --- 갭 분석 ---
  평균 갭: {summary['avg_gap_pct']:+.2f}%
  최대 갭: {summary['max_gap_pct']:+.2f}%
  최소 갭: {summary['min_gap_pct']:+.2f}%

  갭상승: {summary['positive_gap_count']}회 (평균 +{summary['positive_gap_avg']:.2f}%)
  갭하락: {summary['negative_gap_count']}회 (평균 {summary['negative_gap_avg']:.2f}%)
""")
        print("-" * 80)


def main():
    parser = argparse.ArgumentParser(description='오버나잇 갭 전략 백테스트')
    parser.add_argument('--weeks', type=int, default=12, help='백테스트 기간 (주)')
    parser.add_argument('--min-score', type=int, default=60, help='최소 진입 점수')
    parser.add_argument('--top-n', type=int, default=10, help='일일 매수 종목 수')
    parser.add_argument('--allocation', type=int, default=300_000, help='종목당 투자금')

    args = parser.parse_args()

    backtester = OvernightGapBacktester(
        top_n=args.top_n,
        allocation=args.allocation,
        min_score=args.min_score,
    )

    backtester.run_backtest(weeks=args.weeks)


if __name__ == '__main__':
    main()
