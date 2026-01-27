#!/usr/bin/env python3
"""
일일매매 백테스트 시스템

V1, V2, V4, 평균 스코어링으로 1년간 일일매매 시뮬레이션
- 매매 규칙: 순위별 차등 한도로 다음날 시가 매수 → 당일 종가 매도
- 순위별 한도: 1위 50만원, 2위 45만원, ..., 10위 5만원
"""

import os
import sys
import json
import pickle
import argparse
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

warnings.filterwarnings("ignore")

# 프로젝트 경로 설정
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
CHECKPOINT_DIR = OUTPUT_DIR / "backtest_1year"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# 스코어링 함수 import
from scoring import calculate_score_v1, calculate_score_v2, calculate_score_v4, calculate_score_v5


class DailyTradeBacktest:
    """일일매매 백테스트 시스템"""

    def __init__(self, max_workers: int = 10, engines: List[str] = None,
                 top_n: int = 10, fixed_allocation: int = None,
                 score_based: bool = False, no_marcap_limit: bool = False):
        self.max_workers = max_workers
        self.stock_data_cache: Dict[str, pd.DataFrame] = {}
        self.all_stocks: Optional[pd.DataFrame] = None
        self.trading_days: List[datetime] = []

        # 실행할 엔진 설정 (기본: 전체)
        self.engines = engines or ['v1', 'v2', 'v4', 'avg']

        # TOP N 설정 (기본: 10)
        self.top_n = top_n

        # 고정 투자금액 (None이면 차등 금액 사용)
        self.fixed_allocation = fixed_allocation

        # 점수 기반 투자 모드 (85점↑: 50만원, 75~84점: 20만원)
        self.score_based = score_based

        # 시총 상한 제거 여부
        self.no_marcap_limit = no_marcap_limit

        # 케이스별 결과 저장
        self.results = {
            'v1': {'daily': [], 'trades': []},
            'v2': {'daily': [], 'trades': []},
            'v4': {'daily': [], 'trades': []},
            'v5': {'daily': [], 'trades': []},
            'avg': {'daily': [], 'trades': []},
        }

    def get_allocation(self, rank: int) -> int:
        """순위별 투자 한도 계산
        - fixed_allocation 설정 시: 모든 순위 동일 금액
        - 미설정 시: 차등 금액 (1위 50만원 ~ 10위 5만원)
        """
        if rank < 1 or rank > self.top_n:
            return 0

        # 고정 금액 모드
        if self.fixed_allocation:
            return self.fixed_allocation

        # 차등 금액 모드 (기존)
        return (11 - rank) * 50_000

    def load_stock_list(self) -> pd.DataFrame:
        """종목 리스트 로드 (시총 300억 이상, 특수종목 제외)"""
        print("[1] 종목 리스트 로딩...")
        krx = fdr.StockListing("KRX")

        # 기본 필터링
        df = krx[['Code', 'Name', 'Market', 'Marcap', 'Amount', 'Close']].copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)

        # 시총 300억 이상
        df = df[df['Marcap'] >= 30_000_000_000]

        # 시총 상한 (옵션)
        if not self.no_marcap_limit:
            df = df[df['Marcap'] <= 1_000_000_000_000]

        # 특수 종목 제외
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

    def get_trading_days(self, start_date: str, end_date: str) -> List[datetime]:
        """거래일 목록 조회 (KOSPI 지수 기준)"""
        try:
            kospi = fdr.DataReader('KS11', start_date, end_date)
            return kospi.index.tolist()
        except Exception as e:
            print(f"거래일 조회 실패: {e}")
            return []

    def load_stock_ohlcv(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """종목 OHLCV 데이터 조회 (캐싱 적용)"""
        if code in self.stock_data_cache:
            df = self.stock_data_cache[code]
            return df[(df.index >= start_date) & (df.index <= end_date)]

        try:
            # 분석에 필요한 여유 기간 포함 (400일)
            load_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
            df = fdr.DataReader(code, load_start, end_date)
            if df is not None and not df.empty:
                self.stock_data_cache[code] = df
                return df[(df.index >= start_date) & (df.index <= end_date)]
        except:
            pass
        return None

    def preload_all_ohlcv(self, start_date: str, end_date: str):
        """모든 종목 OHLCV 데이터 미리 로드"""
        print(f"\n[2] 종목 데이터 로딩 중...")
        if self.all_stocks is None:
            self.load_stock_list()

        stocks_list = self.all_stocks['Code'].tolist()
        loaded = 0
        failed = 0

        # 병렬 로드
        def load_single(code):
            try:
                load_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
                # 다음날 매매를 위해 추가 기간 필요
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

    def calculate_scores_at_date(self, analysis_date: datetime) -> Dict[str, List[Dict]]:
        """특정 날짜 기준으로 모든 종목 스코어 계산 (선택된 엔진만)"""
        date_str = analysis_date.strftime("%Y-%m-%d")
        results = {'v1': [], 'v2': [], 'v4': [], 'v5': []}

        # 평균 계산이 필요한 경우 모든 엔진 계산
        need_all = 'avg' in self.engines

        for code, df in self.stock_data_cache.items():
            try:
                # 분석일까지의 데이터만 사용
                df_filtered = df[df.index <= date_str].copy()
                if len(df_filtered) < 60:
                    continue

                # 종목 정보
                stock_info = self.all_stocks[self.all_stocks['Code'] == code]
                if stock_info.empty:
                    continue
                name = stock_info.iloc[0]['Name']
                market = stock_info.iloc[0]['Market']

                # V1 스코어 (필요시만)
                if 'v1' in self.engines or need_all:
                    v1_result = calculate_score_v1(df_filtered)
                    if v1_result:
                        results['v1'].append({
                            'code': code,
                            'name': name,
                            'market': market,
                            'score': v1_result['score'],
                            'close': df_filtered.iloc[-1]['Close'],
                        })

                # V2 스코어 (필요시만)
                if 'v2' in self.engines or need_all:
                    v2_result = calculate_score_v2(df_filtered)
                    if v2_result:
                        results['v2'].append({
                            'code': code,
                            'name': name,
                            'market': market,
                            'score': v2_result['score'],
                            'close': df_filtered.iloc[-1]['Close'],
                        })

                # V4 스코어 (필요시만)
                if 'v4' in self.engines or need_all:
                    v4_result = calculate_score_v4(df_filtered)
                    if v4_result:
                        results['v4'].append({
                            'code': code,
                            'name': name,
                            'market': market,
                            'score': v4_result['score'],
                            'close': df_filtered.iloc[-1]['Close'],
                        })

                # V5 스코어 (필요시만)
                if 'v5' in self.engines:
                    v5_result = calculate_score_v5(df_filtered)
                    if v5_result:
                        results['v5'].append({
                            'code': code,
                            'name': name,
                            'market': market,
                            'score': v5_result['score'],
                            'close': df_filtered.iloc[-1]['Close'],
                        })

            except Exception as e:
                continue

        return results

    def calculate_average_scores(self, v1_results: List[Dict], v2_results: List[Dict],
                                  v4_results: List[Dict]) -> List[Dict]:
        """평균 점수 계산 (3개 엔진 모두에 존재하는 종목만)"""
        # 코드별 점수 매핑
        v1_map = {r['code']: r for r in v1_results}
        v2_map = {r['code']: r for r in v2_results}
        v4_map = {r['code']: r for r in v4_results}

        # 교집합 종목
        common_codes = set(v1_map.keys()) & set(v2_map.keys()) & set(v4_map.keys())

        avg_results = []
        for code in common_codes:
            v1 = v1_map[code]
            v2 = v2_map[code]
            v4 = v4_map[code]
            avg_score = (v1['score'] + v2['score'] + v4['score']) / 3

            avg_results.append({
                'code': code,
                'name': v1['name'],
                'market': v1['market'],
                'score': round(avg_score, 1),
                'close': v1['close'],
                'v1_score': v1['score'],
                'v2_score': v2['score'],
                'v4_score': v4['score'],
            })

        return avg_results

    def select_top10_with_skip(self, scored_stocks: List[Dict]) -> List[Dict]:
        """TOP N 선정 (한도 내 매수 불가 시 스킵)"""
        # 점수 내림차순 정렬
        sorted_stocks = sorted(scored_stocks, key=lambda x: -x['score'])

        selected = []
        rank = 1

        for stock in sorted_stocks:
            if rank > self.top_n:
                break

            allocation = self.get_allocation(rank)
            close_price = stock['close']

            # 1주도 못 사는 경우 스킵
            if close_price > allocation:
                continue

            stock_with_rank = stock.copy()
            stock_with_rank['rank'] = rank
            stock_with_rank['allocation'] = allocation
            selected.append(stock_with_rank)
            rank += 1

        return selected

    def select_by_score(self, scored_stocks: List[Dict]) -> List[Dict]:
        """점수 기준 종목 선정 (50점↑: 30만원)"""
        selected = []
        rank = 1

        for stock in scored_stocks:
            score = stock['score']

            # 50점 이상만 30만원 투자
            if score >= 50:
                allocation = 300_000
            else:
                continue  # 50점 미만은 투자 안함

            close_price = stock['close']

            # 1주도 못 사는 경우 스킵
            if close_price > allocation:
                continue

            stock_with_rank = stock.copy()
            stock_with_rank['rank'] = rank
            stock_with_rank['allocation'] = allocation
            selected.append(stock_with_rank)
            rank += 1

        return selected

    def get_next_trading_day_ohlcv(self, code: str, current_date: datetime) -> Optional[Dict]:
        """다음 거래일의 시가/종가 조회 (전일 종가 포함)"""
        if code not in self.stock_data_cache:
            return None

        df = self.stock_data_cache[code]
        current_str = current_date.strftime("%Y-%m-%d")

        # 현재 날짜(스크리닝일)의 종가 조회
        current_df = df[df.index <= current_str]
        if current_df.empty:
            return None
        prev_close = current_df.iloc[-1]['Close']

        # 현재 날짜 이후 데이터 찾기
        future_df = df[df.index > current_str]
        if future_df.empty:
            return None

        next_day = future_df.iloc[0]
        return {
            'date': future_df.index[0],
            'open': next_day['Open'],
            'close': next_day['Close'],
            'high': next_day['High'],
            'low': next_day['Low'],
            'prev_close': prev_close,  # 전일 종가 추가
        }

    def simulate_trade(self, allocation: int, buy_price: float, sell_price: float) -> Optional[Dict]:
        """단일 거래 시뮬레이션"""
        # 유효하지 않은 가격 체크
        if buy_price <= 0 or sell_price <= 0 or not np.isfinite(buy_price) or not np.isfinite(sell_price):
            return None

        shares = int(allocation // buy_price)
        if shares == 0:
            return None

        invested = shares * buy_price
        revenue = shares * sell_price
        pnl = revenue - invested
        return_pct = (pnl / invested) * 100 if invested > 0 else 0

        return {
            'shares': shares,
            'invested': invested,
            'revenue': revenue,
            'pnl': pnl,
            'return_pct': round(return_pct, 2),
        }

    def simulate_daily_trades(self, engine: str, selected_stocks: List[Dict],
                              screening_date: datetime, max_gap_pct: float = 15.0) -> Dict:
        """일일 매매 시뮬레이션

        Args:
            max_gap_pct: 최대 허용 갭 상승률 (기본 15%). 시가가 전일 종가 대비 이 비율 이상 상승 시 매수 스킵
        """
        trades = []
        skipped_trades = []  # 갭 상승으로 스킵된 종목
        total_invested = 0
        total_pnl = 0

        for stock in selected_stocks:
            # 다음 거래일 데이터 조회
            next_day = self.get_next_trading_day_ohlcv(stock['code'], screening_date)
            if next_day is None:
                continue

            # 시가 갭 상승률 체크 (전일 종가 대비)
            prev_close = next_day.get('prev_close', 0)
            if prev_close > 0:
                gap_pct = (next_day['open'] - prev_close) / prev_close * 100
                if gap_pct >= max_gap_pct:
                    # 갭 상승 15% 이상 → 매수 스킵
                    skipped_trades.append({
                        'code': stock['code'],
                        'name': stock['name'],
                        'gap_pct': round(gap_pct, 2),
                        'reason': f'갭상승 {gap_pct:.1f}% >= {max_gap_pct}%'
                    })
                    continue

            # 거래 시뮬레이션
            result = self.simulate_trade(
                allocation=stock['allocation'],
                buy_price=next_day['open'],
                sell_price=next_day['close']
            )

            if result is None:
                continue

            # 갭 상승률 계산
            gap_pct = 0
            if prev_close > 0:
                gap_pct = (next_day['open'] - prev_close) / prev_close * 100

            trade = {
                'rank': stock['rank'],
                'code': stock['code'],
                'name': stock['name'],
                'market': stock['market'],
                'score': stock['score'],
                'allocation': stock['allocation'],
                'prev_close': prev_close,
                'buy_price': next_day['open'],
                'sell_price': next_day['close'],
                'gap_pct': round(gap_pct, 2),  # 갭 상승률 기록
                'shares': result['shares'],
                'invested': result['invested'],
                'pnl': result['pnl'],
                'return_pct': result['return_pct'],
            }

            # 평균 엔진인 경우 개별 점수도 추가
            if 'v1_score' in stock:
                trade['v1_score'] = stock['v1_score']
                trade['v2_score'] = stock['v2_score']
                trade['v4_score'] = stock['v4_score']

            trades.append(trade)
            total_invested += result['invested']
            total_pnl += result['pnl']

        # 다음 거래일 계산
        if trades:
            trade_date = self.get_next_trading_day_ohlcv(trades[0]['code'], screening_date)
            trade_date_str = trade_date['date'].strftime("%Y-%m-%d") if trade_date else ""
        else:
            trade_date_str = ""

        return {
            'screening_date': screening_date.strftime("%Y-%m-%d"),
            'trade_date': trade_date_str,
            'engine': engine,
            'trades': trades,
            'skipped_trades': skipped_trades,  # 갭 상승으로 스킵된 종목
            'total_invested': total_invested,
            'total_pnl': round(total_pnl, 0),
            'return_pct': round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0,
            'trade_count': len(trades),
            'skipped_count': len(skipped_trades),  # 스킵된 종목 수
        }

    def save_checkpoint(self, processed_days: int, checkpoint_data: Dict):
        """체크포인트 저장"""
        checkpoint_file = CHECKPOINT_DIR / "checkpoint.pkl"
        with open(checkpoint_file, 'wb') as f:
            pickle.dump({
                'processed_days': processed_days,
                'results': self.results,
                'checkpoint_data': checkpoint_data,
            }, f)
        print(f"    체크포인트 저장 완료 ({processed_days}일 처리)")

    def load_checkpoint(self) -> Optional[Dict]:
        """체크포인트 로드"""
        checkpoint_file = CHECKPOINT_DIR / "checkpoint.pkl"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, 'rb') as f:
                    data = pickle.load(f)
                print(f"    체크포인트 로드 완료 ({data['processed_days']}일 처리됨)")
                self.results = data['results']
                return data
            except:
                pass
        return None

    def run_backtest(self, weeks: int = 52, resume: bool = False):
        """백테스트 실행"""
        print("\n" + "=" * 80)
        print("  일일매매 백테스트 시스템")
        print("  V1 / V2 / V4 / 평균 스코어링 비교")
        print("=" * 80)

        # 기간 설정
        end_date = datetime.now() - timedelta(days=5)  # 최근 5일은 제외 (미래 데이터 방지)
        start_date = end_date - timedelta(weeks=weeks)

        print(f"  기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} ({weeks}주)")
        print(f"  매매 규칙: 다음날 시가 매수 → 당일 종가 매도")
        if self.score_based:
            print(f"  투자 기준: 점수 기반 (50점↑: 30만원)")
        elif self.fixed_allocation:
            print(f"  투자 한도: TOP {self.top_n} 종목 각 {self.fixed_allocation:,}원")
        else:
            print(f"  순위별 한도: 1위 50만원 ~ 10위 5만원")
        if self.no_marcap_limit:
            print(f"  시총 조건: 300억 이상 (상한 없음)")
        print(f"  스킵 조건: 시가 갭 상승 15% 이상 시 매수 제외")
        print("=" * 80)

        # 체크포인트 복구
        start_idx = 0
        if resume:
            checkpoint = self.load_checkpoint()
            if checkpoint:
                start_idx = checkpoint['processed_days']

        # 데이터 로드
        self.load_stock_list()
        self.preload_all_ohlcv(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )

        # 거래일 조회
        print(f"\n[3] 거래일 조회...")
        self.trading_days = self.get_trading_days(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
        # 마지막 1일은 제외 (다음날 매매를 위해)
        self.trading_days = self.trading_days[:-1]
        print(f"    → {len(self.trading_days)}개 거래일")

        # 백테스트 실행
        print(f"\n[4] 백테스트 실행...")

        for i, screening_date in enumerate(self.trading_days[start_idx:], start=start_idx):
            date_str = screening_date.strftime("%Y-%m-%d")
            progress = (i + 1) / len(self.trading_days) * 100
            print(f"\r    {date_str} 처리 중... ({i + 1}/{len(self.trading_days)}, {progress:.1f}%)", end="", flush=True)

            # 스코어 계산 (선택된 엔진만)
            scores = self.calculate_scores_at_date(screening_date)

            # 평균 점수 계산 (필요시)
            avg_scores = []
            if 'avg' in self.engines:
                avg_scores = self.calculate_average_scores(
                    scores['v1'], scores['v2'], scores['v4']
                )

            # 선택된 엔진별 종목 선정 및 매매 시뮬레이션
            engine_score_map = {'v1': scores['v1'], 'v2': scores['v2'], 'v4': scores['v4'], 'v5': scores['v5'], 'avg': avg_scores}
            for engine in self.engines:
                engine_scores = engine_score_map.get(engine, [])
                # 점수 기반 모드 vs TOP N 모드
                if self.score_based:
                    selected = self.select_by_score(engine_scores)
                else:
                    selected = self.select_top10_with_skip(engine_scores)
                daily_result = self.simulate_daily_trades(engine, selected, screening_date)

                self.results[engine]['daily'].append(daily_result)
                self.results[engine]['trades'].extend(daily_result['trades'])

            # 체크포인트 저장 (10일마다)
            if (i + 1) % 10 == 0:
                self.save_checkpoint(i + 1, {})

        print(f"\n    → 백테스트 완료")

        # 결과 저장
        self.save_results()
        self.print_summary()

    def save_results(self):
        """결과 저장 (Excel, JSON)"""
        print(f"\n[5] 결과 저장 중...")
        date_str = datetime.now().strftime("%Y%m%d")

        # Excel 저장
        excel_path = OUTPUT_DIR / f"backtest_daily_trade_{date_str}.xlsx"

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # Sheet 1: 요약
            summary_data = []
            for engine in self.engines:
                trades = self.results[engine]['trades']
                daily_results = self.results[engine]['daily']
                if not trades:
                    continue

                total_trades = len(trades)
                wins = len([t for t in trades if t['pnl'] > 0])
                total_invested = sum(t['invested'] for t in trades)
                total_pnl = sum(t['pnl'] for t in trades)
                total_skipped = sum(d.get('skipped_count', 0) for d in daily_results)

                summary_data.append({
                    '케이스': engine.upper(),
                    '총거래수': total_trades,
                    '갭스킵': total_skipped,  # 갭 상승으로 스킵된 종목 수
                    '승리': wins,
                    '패배': total_trades - wins,
                    '승률(%)': round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
                    '총투자액': int(total_invested),
                    '총손익': int(total_pnl),
                    '수익률(%)': round(total_pnl / total_invested * 100, 2) if total_invested > 0 else 0,
                    '평균손익': int(total_pnl / total_trades) if total_trades > 0 else 0,
                })

            pd.DataFrame(summary_data).to_excel(writer, sheet_name='요약', index=False)

            # Sheet 2: 일별결과
            daily_data = []
            for engine in self.engines:
                for daily in self.results[engine]['daily']:
                    daily_data.append({
                        '스크리닝일': daily['screening_date'],
                        '매매일': daily['trade_date'],
                        '케이스': engine.upper(),
                        '거래수': daily['trade_count'],
                        '투자액': int(daily['total_invested']),
                        '손익': int(daily['total_pnl']),
                        '수익률(%)': daily['return_pct'],
                    })

            pd.DataFrame(daily_data).to_excel(writer, sheet_name='일별결과', index=False)

            # Sheet 3: 거래상세
            trade_data = []
            for engine in self.engines:
                for daily in self.results[engine]['daily']:
                    for trade in daily['trades']:
                        row = {
                            '스크리닝일': daily['screening_date'],
                            '매매일': daily['trade_date'],
                            '케이스': engine.upper(),
                            '순위': trade['rank'],
                            '종목코드': trade['code'],
                            '종목명': trade['name'],
                            '시장': trade['market'],
                            '점수': trade['score'],
                            '한도': trade['allocation'],
                            '전일종가': int(trade.get('prev_close', 0)),
                            '매수가': int(trade['buy_price']),
                            '갭(%)': trade.get('gap_pct', 0),  # 갭 상승률 추가
                            '매도가': int(trade['sell_price']),
                            '수량': trade['shares'],
                            '투자액': int(trade['invested']),
                            '손익': int(trade['pnl']),
                            '수익률(%)': trade['return_pct'],
                        }
                        # 평균 엔진인 경우 개별 점수 추가
                        if 'v1_score' in trade:
                            row['V1점수'] = trade['v1_score']
                            row['V2점수'] = trade['v2_score']
                            row['V4점수'] = trade['v4_score']
                        trade_data.append(row)

            pd.DataFrame(trade_data).to_excel(writer, sheet_name='거래상세', index=False)

            # Sheet 4: 순위별 성과
            rank_data = []
            for engine in self.engines:
                trades = self.results[engine]['trades']
                for rank in range(1, 11):
                    rank_trades = [t for t in trades if t['rank'] == rank]
                    if not rank_trades:
                        continue

                    wins = len([t for t in rank_trades if t['pnl'] > 0])
                    total_pnl = sum(t['pnl'] for t in rank_trades)
                    total_invested = sum(t['invested'] for t in rank_trades)

                    rank_data.append({
                        '케이스': engine.upper(),
                        '순위': rank,
                        '한도': self.get_allocation(rank),
                        '거래수': len(rank_trades),
                        '승률(%)': round(wins / len(rank_trades) * 100, 1),
                        '총손익': int(total_pnl),
                        '수익률(%)': round(total_pnl / total_invested * 100, 2) if total_invested > 0 else 0,
                    })

            pd.DataFrame(rank_data).to_excel(writer, sheet_name='순위별성과', index=False)

        print(f"    → Excel 저장: {excel_path}")

        # JSON 저장 (요약만)
        json_path = OUTPUT_DIR / f"backtest_daily_trade_{date_str}.json"
        json_data = {
            'run_date': date_str,
            'period': {
                'start': self.trading_days[0].strftime("%Y-%m-%d") if self.trading_days else '',
                'end': self.trading_days[-1].strftime("%Y-%m-%d") if self.trading_days else '',
                'trading_days': len(self.trading_days),
            },
            'summary': summary_data,
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"    → JSON 저장: {json_path}")

    def print_summary(self):
        """결과 요약 출력"""
        print("\n" + "=" * 80)
        print("  백테스트 결과 요약")
        print("  (시가 갭 상승 15% 이상 종목 제외)")
        print("=" * 80)

        print(f"\n{'케이스':<8} {'총거래':<8} {'갭스킵':<8} {'승률':<8} {'총투자액':<15} {'총손익':<12} {'수익률':<10}")
        print("-" * 80)

        for engine in self.engines:
            trades = self.results[engine]['trades']
            daily_results = self.results[engine]['daily']
            if not trades:
                continue

            total_trades = len(trades)
            total_skipped = sum(d.get('skipped_count', 0) for d in daily_results)
            wins = len([t for t in trades if t['pnl'] > 0])
            win_rate = wins / total_trades * 100 if total_trades > 0 else 0
            total_invested = sum(t['invested'] for t in trades)
            total_pnl = sum(t['pnl'] for t in trades)
            return_pct = total_pnl / total_invested * 100 if total_invested > 0 else 0

            print(f"{engine.upper():<8} {total_trades:<8} {total_skipped:<8} {win_rate:>6.1f}% {total_invested:>13,}원 {total_pnl:>+10,.0f}원 {return_pct:>+7.2f}%")

        print("-" * 80)

        # 순위별 요약
        print(f"\n순위별 성과 (전체 케이스 합산)")
        print(f"{'순위':<6} {'한도':<10} {'거래수':<8} {'승률':<8} {'총손익':<12} {'수익률':<10}")
        print("-" * 60)

        for rank in range(1, 11):
            all_rank_trades = []
            for engine in self.engines:
                all_rank_trades.extend([t for t in self.results[engine]['trades'] if t['rank'] == rank])

            if not all_rank_trades:
                continue

            wins = len([t for t in all_rank_trades if t['pnl'] > 0])
            total_pnl = sum(t['pnl'] for t in all_rank_trades)
            total_invested = sum(t['invested'] for t in all_rank_trades)
            return_pct = total_pnl / total_invested * 100 if total_invested > 0 else 0

            print(f"{rank}위     {self.get_allocation(rank):>8,}원 {len(all_rank_trades):<8} {wins/len(all_rank_trades)*100:>6.1f}% {total_pnl:>+10,.0f}원 {return_pct:>+7.2f}%")


def main():
    parser = argparse.ArgumentParser(description='일일매매 백테스트')
    parser.add_argument('--weeks', type=int, default=52, help='백테스트 기간 (주 단위, 기본: 52주)')
    parser.add_argument('--workers', type=int, default=10, help='병렬 처리 워커 수 (기본: 10)')
    parser.add_argument('--resume', action='store_true', help='체크포인트에서 재개')
    parser.add_argument('--engines', type=str, default='v1,v2,v4,avg',
                        help='실행할 엔진 (쉼표 구분, 기본: v1,v2,v4,avg)')
    parser.add_argument('--top-n', type=int, default=10, help='TOP N 종목 수 (기본: 10)')
    parser.add_argument('--fixed-amount', type=int, default=None,
                        help='고정 투자금액 (미설정 시 차등 금액)')
    parser.add_argument('--score-based', action='store_true',
                        help='점수 기반 투자 (85점↑: 50만원, 75~84점: 20만원)')
    parser.add_argument('--no-marcap-limit', action='store_true',
                        help='시총 상한 제거 (기본: 1조 이하)')
    args = parser.parse_args()

    engines = [e.strip().lower() for e in args.engines.split(',')]
    backtester = DailyTradeBacktest(
        max_workers=args.workers,
        engines=engines,
        top_n=args.top_n,
        fixed_allocation=args.fixed_amount,
        score_based=args.score_based,
        no_marcap_limit=args.no_marcap_limit
    )
    backtester.run_backtest(weeks=args.weeks, resume=args.resume)


if __name__ == "__main__":
    main()
