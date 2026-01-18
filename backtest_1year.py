#!/usr/bin/env python3
"""
1년 백테스트 분석 모듈

과거 1년간의 각 거래일에 대해 기술적 분석을 수행하고,
선정된 종목의 적중률을 계산합니다.

사용법:
    python backtest_1year.py                    # 1년 백테스트 실행
    python backtest_1year.py --weeks 4          # 4주(약 20거래일) 백테스트
    python backtest_1year.py --resume           # 중단된 백테스트 재개
    python backtest_1year.py --report-only      # 기존 결과로 리포트만 생성
"""

import argparse
import json
import os
import pickle
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import time

warnings.filterwarnings("ignore")

from config import OUTPUT_DIR, get_signal_kr

# 백테스트 결과 저장 경로
BACKTEST_DIR = OUTPUT_DIR / "backtest_1year"
BACKTEST_DIR.mkdir(exist_ok=True)

CHECKPOINT_FILE = BACKTEST_DIR / "checkpoint.pkl"
RESULTS_FILE = BACKTEST_DIR / "backtest_results.json"
REPORT_FILE = BACKTEST_DIR / "backtest_1year_report.md"


class BacktestAnalyzer:
    """1년 백테스트 분석기"""

    def __init__(self, weeks: int = 52, top_n: int = 100):
        """
        Args:
            weeks: 백테스트 기간 (주 단위, 기본 52주 = 1년)
            top_n: 일별 선정 종목 수
        """
        self.weeks = weeks
        self.top_n = top_n
        self.trading_days = []
        self.all_stocks_cache = {}
        self.price_cache = {}

    def get_trading_days(self, end_date: datetime = None) -> List[str]:
        """과거 N주간의 거래일 목록 조회"""
        if end_date is None:
            end_date = datetime.now()

        # 시작일 계산 (N주 전)
        start_date = end_date - timedelta(weeks=self.weeks)

        # KOSPI 지수로 거래일 확인
        print(f"[1/5] 거래일 목록 조회 중 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})...")

        try:
            kospi = fdr.DataReader('KS11', start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            trading_days = [d.strftime('%Y-%m-%d') for d in kospi.index]

            # 최근 10일은 제외 (미래 데이터 검증 필요하므로)
            trading_days = trading_days[:-10]

            print(f"    → 총 {len(trading_days)}개 거래일 확인")
            self.trading_days = trading_days
            return trading_days
        except Exception as e:
            print(f"    → 거래일 조회 실패: {e}")
            return []

    def load_stock_list(self) -> pd.DataFrame:
        """KRX 종목 목록 로드"""
        print("[2/5] KRX 종목 목록 로딩 중...")

        try:
            krx = fdr.StockListing("KRX")

            # 필터링: 시총 300억 이상, 우선주/스팩/ETF 제외
            df = krx.copy()

            if "Marcap" in df.columns:
                df = df[df["Marcap"] >= 30_000_000_000]  # 300억 이상

            # 특수 종목 제외
            exclude_keywords = ["스팩", "SPAC", "리츠", "ETF", "ETN", "인버스", "레버리지"]
            for keyword in exclude_keywords:
                df = df[~df["Name"].str.contains(keyword, case=False, na=False)]

            # 우선주 제외
            df["Code"] = df["Code"].astype(str).str.zfill(6)
            df = df[df["Code"].str[-1] == "0"]

            print(f"    → {len(df):,}개 종목 로딩 완료")
            return df
        except Exception as e:
            print(f"    → 종목 목록 로딩 실패: {e}")
            return pd.DataFrame()

    def get_historical_ohlcv(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """특정 기간의 OHLCV 데이터 조회 (캐싱 적용)"""
        cache_key = f"{code}_{start_date}_{end_date}"

        if cache_key in self.price_cache:
            return self.price_cache[cache_key]

        try:
            df = fdr.DataReader(code, start_date, end_date)
            if not df.empty:
                self.price_cache[cache_key] = df
                return df
        except:
            pass
        return None

    def calculate_technical_score(self, df: pd.DataFrame) -> Tuple[int, List[str], Dict]:
        """
        기술적 분석 점수 계산 (technical_analyst.py와 동일한 로직)

        Returns:
            (score, signals, indicators)
        """
        import pandas_ta as ta

        if df is None or len(df) < 60:
            return 0, [], {}

        try:
            score = 0
            signals = []
            indicators = {}

            curr = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else curr

            close = curr['Close']
            volume = curr['Volume']

            # 이동평균선
            sma5 = ta.sma(df['Close'], length=5).iloc[-1]
            sma20 = ta.sma(df['Close'], length=20).iloc[-1]
            sma60 = ta.sma(df['Close'], length=60).iloc[-1]

            # 정배열 체크
            if pd.notna(sma5) and pd.notna(sma20) and pd.notna(sma60):
                if sma5 > sma20 > sma60:
                    score += 15
                    signals.append("MA_ALIGNED")

                # 골든크로스 (5/20)
                prev_sma5 = ta.sma(df['Close'], length=5).iloc[-2]
                prev_sma20 = ta.sma(df['Close'], length=20).iloc[-2]

                if pd.notna(prev_sma5) and pd.notna(prev_sma20):
                    if prev_sma5 < prev_sma20 and sma5 > sma20:
                        score += 15
                        signals.append("GOLDEN_CROSS_5_20")

            # RSI (technical_analyst.py와 동일)
            rsi = ta.rsi(df['Close'], length=14)
            if not rsi.empty and pd.notna(rsi.iloc[-1]):
                rsi_val = rsi.iloc[-1]
                indicators['RSI'] = round(rsi_val, 1)

                if rsi_val < 30:
                    score += 15
                    signals.append("RSI_OVERSOLD")
                elif rsi_val < 50:
                    score += 5
                elif rsi_val > 70:
                    score -= 10
                    signals.append("RSI_OVERBOUGHT")

            # 거래량 (technical_analyst.py와 동일)
            vol_ma = ta.sma(df['Volume'], length=20).iloc[-1]
            if pd.notna(vol_ma) and vol_ma > 0:
                vol_ratio = volume / vol_ma
                indicators['VOL_RATIO'] = round(vol_ratio, 2)

                if vol_ratio >= 2:
                    score += 15
                    signals.append("VOLUME_SURGE")
                elif vol_ratio >= 1.5:
                    score += 10
                    signals.append("VOLUME_HIGH")

            # MACD (technical_analyst.py와 동일)
            macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
            if macd is not None:
                macd_col = [c for c in macd.columns if c.startswith('MACD_')][0]
                signal_col = [c for c in macd.columns if 'MACDs' in c][0]
                hist_col = [c for c in macd.columns if 'MACDh' in c][0]

                curr_macd = macd.iloc[-1][macd_col]
                prev_macd = macd.iloc[-2][macd_col]
                curr_signal = macd.iloc[-1][signal_col]
                prev_signal = macd.iloc[-2][signal_col]
                curr_hist = macd.iloc[-1][hist_col]
                prev_hist = macd.iloc[-2][hist_col]

                if pd.notna(curr_macd) and pd.notna(curr_signal):
                    indicators['MACD'] = round(curr_macd, 2)

                    # MACD 골든크로스
                    if prev_macd < prev_signal and curr_macd > curr_signal:
                        score += 20
                        signals.append("MACD_GOLDEN_CROSS")
                    elif prev_hist < 0 and curr_hist > 0:
                        score += 15
                        signals.append("MACD_HIST_POSITIVE")
                    elif curr_hist > prev_hist:
                        score += 5

            # 볼린저 밴드
            bb = ta.bbands(df['Close'], length=20)
            if bb is not None and 'BBU_20_2.0' in bb.columns:
                bb_upper = bb['BBU_20_2.0'].iloc[-1]
                bb_lower = bb['BBL_20_2.0'].iloc[-1]

                if pd.notna(bb_upper) and close > bb_upper:
                    score += 10
                    signals.append("BB_UPPER_BREAK")
                elif pd.notna(bb_lower) and close < bb_lower:
                    score += 10
                    signals.append("BB_LOWER_TOUCH")

            # ADX (추세 강도)
            adx = ta.adx(df['High'], df['Low'], df['Close'])
            if adx is not None and 'ADX_14' in adx.columns:
                adx_val = adx['ADX_14'].iloc[-1]
                if pd.notna(adx_val):
                    indicators['ADX'] = round(adx_val, 1)
                    if adx_val > 25:
                        score += 10
                        signals.append("ADX_STRONG_TREND")

            # ROC (변화율)
            roc = ta.roc(df['Close'], length=10)
            if not roc.empty and pd.notna(roc.iloc[-1]):
                roc_val = roc.iloc[-1]
                indicators['ROC'] = round(roc_val, 2)
                if roc_val > 5:
                    score += 10
                    signals.append("ROC_STRONG_MOMENTUM")

            # Supertrend
            st = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
            if st is not None and 'SUPERTd_10_3.0' in st.columns:
                st_direction = st['SUPERTd_10_3.0'].iloc[-1]
                if pd.notna(st_direction) and st_direction == 1:
                    score += 10
                    signals.append("SUPERTREND_BUY")

            # PSAR
            psar = ta.psar(df['High'], df['Low'], df['Close'])
            if psar is not None:
                psar_long = psar.get('PSARl_0.02_0.2')
                if psar_long is not None and pd.notna(psar_long.iloc[-1]):
                    if close > psar_long.iloc[-1]:
                        score += 10
                        signals.append("PSAR_BUY_SIGNAL")

            # 스토캐스틱
            stoch = ta.stoch(df['High'], df['Low'], df['Close'])
            if stoch is not None and 'STOCHk_14_3_3' in stoch.columns:
                stoch_k = stoch['STOCHk_14_3_3'].iloc[-1]
                stoch_d = stoch['STOCHd_14_3_3'].iloc[-1]
                prev_k = stoch['STOCHk_14_3_3'].iloc[-2]
                prev_d = stoch['STOCHd_14_3_3'].iloc[-2]

                if pd.notna(stoch_k) and pd.notna(stoch_d):
                    if prev_k < prev_d and stoch_k > stoch_d:
                        score += 10
                        signals.append("STOCH_GOLDEN_CROSS")

            # CMF (Chaikin Money Flow)
            cmf = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'])
            if cmf is not None and not cmf.empty and pd.notna(cmf.iloc[-1]):
                cmf_val = cmf.iloc[-1]
                indicators['CMF'] = round(cmf_val, 3)
                if cmf_val > 0.1:
                    score += 10
                    signals.append("CMF_STRONG_INFLOW")

            # 점수 제한
            score = min(100, max(0, score))

            return score, signals, indicators

        except Exception as e:
            return 0, [], {}

    def analyze_single_day(self, analysis_date: str, stock_list: pd.DataFrame,
                          progress_callback=None) -> List[Dict]:
        """
        특정 날짜의 top100 종목 분석

        Args:
            analysis_date: 분석 기준일 (YYYY-MM-DD)
            stock_list: 분석 대상 종목 목록
            progress_callback: 진행률 콜백 함수

        Returns:
            선정된 종목 리스트
        """
        # 분석에 필요한 과거 데이터 기간 (1년)
        analysis_dt = datetime.strptime(analysis_date, '%Y-%m-%d')
        start_date = (analysis_dt - timedelta(days=400)).strftime('%Y-%m-%d')

        results = []

        def analyze_stock(stock_row):
            code = stock_row['Code']
            name = stock_row['Name']

            try:
                # 분석일까지의 데이터만 사용
                df = fdr.DataReader(code, start_date, analysis_date)

                if df is None or len(df) < 60:
                    return None

                # 분석일의 거래량/거래대금 체크
                last_row = df.iloc[-1]
                if 'Volume' in df.columns and last_row['Volume'] < 10000:
                    return None

                # 기술적 분석
                score, signals, indicators = self.calculate_technical_score(df)

                if score < 30:  # 최소 점수 기준
                    return None

                return {
                    'code': code,
                    'name': name,
                    'score': score,
                    'signals': signals,
                    'indicators': indicators,
                    'close': float(last_row['Close']),
                    'volume': int(last_row['Volume']),
                    'analysis_date': analysis_date
                }
            except Exception as e:
                return None

        # 병렬 처리
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = []
            for _, row in stock_list.iterrows():
                futures.append(executor.submit(analyze_stock, row))

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # 점수순 정렬 후 상위 N개
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:self.top_n]

    def check_hit(self, code: str, analysis_date: str, selection_price: float,
                 target_gain: float = 0.10, check_days: int = 3) -> Tuple[Optional[bool], Optional[float], Optional[int]]:
        """
        적중 여부 확인

        Args:
            code: 종목코드
            analysis_date: 선정일
            selection_price: 선정일 종가
            target_gain: 목표 수익률 (기본 10%)
            check_days: 확인 기간 (기본 3일)

        Returns:
            (적중여부, 최고수익률, 적중일)
        """
        try:
            analysis_dt = datetime.strptime(analysis_date, '%Y-%m-%d')
            start_date = (analysis_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            end_date = (analysis_dt + timedelta(days=check_days + 5)).strftime('%Y-%m-%d')

            df = fdr.DataReader(code, start_date, end_date)

            if df is None or df.empty:
                return None, None, None

            # 최대 check_days 거래일만 확인
            df = df.head(check_days)

            if df.empty:
                return None, None, None

            # 기간 내 최고가
            max_high = df['High'].max()
            max_return = (max_high - selection_price) / selection_price * 100

            # 목표가 도달 여부
            target_price = selection_price * (1 + target_gain)
            is_hit = max_high >= target_price

            hit_day = None
            if is_hit:
                for i, (idx, row) in enumerate(df.iterrows(), 1):
                    if row['High'] >= target_price:
                        hit_day = i
                        break

            return is_hit, max_return, hit_day

        except Exception as e:
            return None, None, None

    def run_backtest(self, resume: bool = False) -> Dict:
        """
        전체 백테스트 실행

        Args:
            resume: 중단된 백테스트 재개 여부
        """
        print("\n" + "=" * 70)
        print("  1년 백테스트 시작")
        print("  적중 기준: 선정일 종가 대비 3일 내 장중 최고가 10% 이상 상승")
        print("=" * 70)

        # 체크포인트 로드
        checkpoint = None
        completed_dates = set()
        all_results = []

        if resume and CHECKPOINT_FILE.exists():
            print("\n[재개] 이전 진행 상황 로딩 중...")
            with open(CHECKPOINT_FILE, 'rb') as f:
                checkpoint = pickle.load(f)
            completed_dates = set(checkpoint.get('completed_dates', []))
            all_results = checkpoint.get('results', [])
            print(f"    → {len(completed_dates)}일 분석 완료 상태에서 재개")

        # 거래일 목록
        trading_days = self.get_trading_days()
        if not trading_days:
            return {}

        # 종목 목록
        stock_list = self.load_stock_list()
        if stock_list.empty:
            return {}

        # 진행할 날짜 필터링
        remaining_days = [d for d in trading_days if d not in completed_dates]
        total_days = len(trading_days)

        print(f"\n[3/5] 일별 분석 시작 (총 {len(remaining_days)}일 / 전체 {total_days}일)")
        print("-" * 70)

        start_time = time.time()

        for i, analysis_date in enumerate(remaining_days):
            day_start = time.time()

            print(f"    [{len(completed_dates) + 1}/{total_days}] {analysis_date} 분석 중...", end=" ", flush=True)

            # 해당일 top100 분석
            day_results = self.analyze_single_day(analysis_date, stock_list)

            if not day_results:
                print("(데이터 없음)")
                completed_dates.add(analysis_date)
                continue

            # 적중률 검증
            hit_count = 0
            analyzed_count = 0

            for result in day_results:
                is_hit, max_return, hit_day = self.check_hit(
                    result['code'],
                    analysis_date,
                    result['close']
                )

                if is_hit is not None:
                    analyzed_count += 1
                    result['is_hit'] = is_hit
                    result['max_return'] = max_return
                    result['hit_day'] = hit_day

                    if is_hit:
                        hit_count += 1

            all_results.extend(day_results)
            completed_dates.add(analysis_date)

            # 진행률 출력
            day_time = time.time() - day_start
            hit_rate = (hit_count / analyzed_count * 100) if analyzed_count > 0 else 0
            print(f"적중 {hit_count}/{analyzed_count} ({hit_rate:.1f}%) [{day_time:.1f}초]")

            # 체크포인트 저장 (10일마다)
            if (len(completed_dates)) % 10 == 0:
                self._save_checkpoint(completed_dates, all_results)

        # 최종 저장
        self._save_checkpoint(completed_dates, all_results)

        elapsed = time.time() - start_time
        print(f"\n    → 분석 완료 (소요시간: {elapsed/60:.1f}분)")

        # 분석 결과
        print("\n[4/5] 적중률 분석 중...")
        analysis = self._analyze_results(all_results)

        # 리포트 생성
        print("\n[5/5] 리포트 생성 중...")
        self._generate_report(analysis, all_results)

        return analysis

    def _save_checkpoint(self, completed_dates: set, results: List[Dict]):
        """체크포인트 저장"""
        checkpoint = {
            'completed_dates': list(completed_dates),
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        with open(CHECKPOINT_FILE, 'wb') as f:
            pickle.dump(checkpoint, f)

    def _analyze_results(self, results: List[Dict]) -> Dict:
        """결과 분석"""
        if not results:
            return {}

        # 기본 통계
        analyzed = [r for r in results if r.get('is_hit') is not None]
        hits = [r for r in analyzed if r.get('is_hit')]

        total_count = len(analyzed)
        hit_count = len(hits)
        hit_rate = (hit_count / total_count * 100) if total_count > 0 else 0

        # 점수대별 통계
        score_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'returns': []})

        for r in analyzed:
            score = r.get('score', 0)
            max_return = r.get('max_return', 0)

            # 점수 구간
            if score >= 95:
                band = "95점 이상"
            elif score >= 90:
                band = "90-94점"
            elif score >= 85:
                band = "85-89점"
            elif score >= 80:
                band = "80-84점"
            elif score >= 70:
                band = "70-79점"
            elif score >= 60:
                band = "60-69점"
            else:
                band = "60점 미만"

            score_stats[band]['total'] += 1
            score_stats[band]['returns'].append(max_return or 0)
            if r.get('is_hit'):
                score_stats[band]['hit'] += 1

        # 신호별 통계
        signal_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'returns': []})

        for r in analyzed:
            signals = r.get('signals', [])
            max_return = r.get('max_return', 0)
            is_hit = r.get('is_hit', False)

            for signal in signals:
                signal_stats[signal]['total'] += 1
                signal_stats[signal]['returns'].append(max_return or 0)
                if is_hit:
                    signal_stats[signal]['hit'] += 1

        # 신호 조합별 통계 (2개 조합)
        combo_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'returns': []})

        for r in analyzed:
            signals = r.get('signals', [])
            max_return = r.get('max_return', 0)
            is_hit = r.get('is_hit', False)

            # 2개 신호 조합
            for i in range(len(signals)):
                for j in range(i + 1, len(signals)):
                    combo = tuple(sorted([signals[i], signals[j]]))
                    combo_stats[combo]['total'] += 1
                    combo_stats[combo]['returns'].append(max_return or 0)
                    if is_hit:
                        combo_stats[combo]['hit'] += 1

        # 일별 통계
        daily_stats = defaultdict(lambda: {'total': 0, 'hit': 0})

        for r in analyzed:
            date = r.get('analysis_date', '')
            daily_stats[date]['total'] += 1
            if r.get('is_hit'):
                daily_stats[date]['hit'] += 1

        return {
            'summary': {
                'total_days': len(daily_stats),
                'total_analyzed': total_count,
                'total_hits': hit_count,
                'hit_rate': round(hit_rate, 1),
                'avg_return': round(np.mean([r.get('max_return', 0) for r in analyzed if r.get('max_return') is not None]), 2)
            },
            'score_stats': dict(score_stats),
            'signal_stats': dict(signal_stats),
            'combo_stats': dict(combo_stats),
            'daily_stats': dict(daily_stats)
        }

    def _generate_report(self, analysis: Dict, results: List[Dict]):
        """마크다운 리포트 및 엑셀 상세 데이터 생성"""
        summary = analysis.get('summary', {})
        score_stats = analysis.get('score_stats', {})
        signal_stats = analysis.get('signal_stats', {})
        combo_stats = analysis.get('combo_stats', {})
        daily_stats = analysis.get('daily_stats', {})

        # 종목별/날짜별 상세 엑셀 생성
        self._generate_detail_excel(results)

        lines = []

        lines.append("# 1년 백테스트 분석 보고서")
        lines.append("")
        lines.append(f"**분석일**: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append(f"**분석 기간**: {min(daily_stats.keys()) if daily_stats else 'N/A'} ~ {max(daily_stats.keys()) if daily_stats else 'N/A'} ({summary.get('total_days', 0)}거래일)")
        lines.append(f"**분석 대상**: 일별 Top {self.top_n} 선정 종목 (총 {summary.get('total_analyzed', 0):,}건)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 1. 요약
        lines.append("## 1. 요약 (Executive Summary)")
        lines.append("")
        lines.append("| 지표 | 수치 |")
        lines.append("|------|------|")
        lines.append(f"| 전체 적중률 | **{summary.get('hit_rate', 0):.1f}%** |")
        lines.append(f"| 총 적중 건수 | {summary.get('total_hits', 0):,} / {summary.get('total_analyzed', 0):,} |")
        lines.append(f"| 평균 최고 수익률 | {summary.get('avg_return', 0):.1f}% |")

        # 고점수 적중률
        high_score_total = sum(score_stats.get(k, {}).get('total', 0) for k in ['95점 이상', '90-94점'])
        high_score_hit = sum(score_stats.get(k, {}).get('hit', 0) for k in ['95점 이상', '90-94점'])
        high_score_rate = (high_score_hit / high_score_total * 100) if high_score_total > 0 else 0
        lines.append(f"| 90점 이상 적중률 | **{high_score_rate:.1f}%** ({high_score_hit}/{high_score_total}) |")
        lines.append("")

        # 2. 점수대별 적중률
        lines.append("## 2. 점수대별 적중률")
        lines.append("")
        lines.append("| 점수 구간 | 분석 종목 | 적중 종목 | 적중률 | 평균 최고수익률 |")
        lines.append("|-----------|-----------|-----------|--------|-----------------|")

        score_order = ['95점 이상', '90-94점', '85-89점', '80-84점', '70-79점', '60-69점', '60점 미만']
        for band in score_order:
            stats = score_stats.get(band, {})
            total = stats.get('total', 0)
            hit = stats.get('hit', 0)
            rate = (hit / total * 100) if total > 0 else 0
            returns = stats.get('returns', [])
            avg_ret = np.mean(returns) if returns else 0
            if total > 0:
                lines.append(f"| {band} | {total:,} | {hit:,} | **{rate:.1f}%** | {avg_ret:.1f}% |")
        lines.append("")

        # 3. 신호별 적중률 (상위 15개)
        lines.append("## 3. 신호별 적중률 (Top 15)")
        lines.append("")
        lines.append("| 순위 | 신호 | 분석 | 적중 | 적중률 | 평균수익 |")
        lines.append("|------|------|------|------|--------|----------|")

        # 적중률 순 정렬 (최소 50건 이상)
        sorted_signals = []
        for signal, stats in signal_stats.items():
            if stats.get('total', 0) >= 50:
                rate = (stats['hit'] / stats['total'] * 100) if stats['total'] > 0 else 0
                avg_ret = np.mean(stats.get('returns', [])) if stats.get('returns') else 0
                sorted_signals.append((signal, stats['total'], stats['hit'], rate, avg_ret))

        sorted_signals.sort(key=lambda x: x[3], reverse=True)

        for i, (signal, total, hit, rate, avg_ret) in enumerate(sorted_signals[:15], 1):
            signal_kr = get_signal_kr(signal)
            lines.append(f"| {i} | {signal_kr} | {total:,} | {hit:,} | **{rate:.1f}%** | {avg_ret:.1f}% |")
        lines.append("")

        # 4. 2개 신호 조합 적중률 (상위 10개)
        lines.append("## 4. 2개 신호 조합 적중률 (Top 10)")
        lines.append("")
        lines.append("| 순위 | 신호 조합 | 분석 | 적중 | 적중률 | 평균수익 |")
        lines.append("|------|-----------|------|------|--------|----------|")

        sorted_combos = []
        for combo, stats in combo_stats.items():
            if stats.get('total', 0) >= 20:
                rate = (stats['hit'] / stats['total'] * 100) if stats['total'] > 0 else 0
                avg_ret = np.mean(stats.get('returns', [])) if stats.get('returns') else 0
                combo_name = " + ".join([get_signal_kr(s) for s in combo])
                sorted_combos.append((combo_name, stats['total'], stats['hit'], rate, avg_ret))

        sorted_combos.sort(key=lambda x: x[3], reverse=True)

        for i, (combo_name, total, hit, rate, avg_ret) in enumerate(sorted_combos[:10], 1):
            lines.append(f"| {i} | {combo_name} | {total:,} | {hit:,} | **{rate:.1f}%** | {avg_ret:.1f}% |")
        lines.append("")

        # 5. 일별 적중률 변동
        lines.append("## 5. 일별 적중률 분포")
        lines.append("")

        daily_rates = []
        for date, stats in daily_stats.items():
            rate = (stats['hit'] / stats['total'] * 100) if stats['total'] > 0 else 0
            daily_rates.append((date, stats['total'], stats['hit'], rate))

        daily_rates.sort(key=lambda x: x[3], reverse=True)

        lines.append("### 적중률 상위 10일")
        lines.append("| 날짜 | 분석 | 적중 | 적중률 |")
        lines.append("|------|------|------|--------|")
        for date, total, hit, rate in daily_rates[:10]:
            lines.append(f"| {date} | {total} | {hit} | **{rate:.1f}%** |")
        lines.append("")

        lines.append("### 적중률 하위 10일")
        lines.append("| 날짜 | 분석 | 적중 | 적중률 |")
        lines.append("|------|------|------|--------|")
        for date, total, hit, rate in daily_rates[-10:]:
            lines.append(f"| {date} | {total} | {hit} | {rate:.1f}% |")
        lines.append("")

        # 6. 결론
        lines.append("## 6. 결론 및 권고사항")
        lines.append("")
        lines.append("### 주요 발견사항")
        lines.append("")
        lines.append(f"1. **전체 적중률**: {summary.get('hit_rate', 0):.1f}% (1년 평균)")
        lines.append(f"2. **고점수 효과**: 90점 이상 종목의 적중률이 {high_score_rate:.1f}%로 전체 대비 유의미하게 높음")

        # 최고 신호
        if sorted_signals:
            best_signal = sorted_signals[0]
            lines.append(f"3. **최고 신호**: {get_signal_kr(best_signal[0])} ({best_signal[3]:.1f}% 적중률)")

        # 최고 조합
        if sorted_combos:
            best_combo = sorted_combos[0]
            lines.append(f"4. **최고 조합**: {best_combo[0]} ({best_combo[3]:.1f}% 적중률)")

        lines.append("")
        lines.append("### 권고 전략")
        lines.append("")
        lines.append("```")
        lines.append("점수: 90점 이상 우선 선정")
        if sorted_signals:
            lines.append(f"권장 신호: {get_signal_kr(sorted_signals[0][0])}")
        if sorted_combos:
            lines.append(f"권장 조합: {sorted_combos[0][0]}")
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*이 보고서는 과거 데이터 기반 분석으로, 미래 수익을 보장하지 않습니다.*")
        lines.append("")
        lines.append(f"**생성일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 파일 저장
        report_content = "\n".join(lines)

        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write(report_content)

        print(f"    → 리포트 저장: {REPORT_FILE}")

        # JSON 결과도 저장 (tuple 키를 문자열로 변환)
        json_safe_analysis = analysis.copy()
        if 'combo_stats' in json_safe_analysis:
            json_safe_analysis['combo_stats'] = {
                " + ".join(k) if isinstance(k, tuple) else k: v
                for k, v in analysis['combo_stats'].items()
            }

        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'analysis': json_safe_analysis,
                'generated_at': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

        print(f"    → 결과 데이터: {RESULTS_FILE}")

        return report_content

    def _generate_detail_excel(self, results: List[Dict]):
        """종목별/날짜별 상세 점수 엑셀 생성"""
        if not results:
            return

        DETAIL_FILE = BACKTEST_DIR / "backtest_detail.xlsx"

        # 결과를 DataFrame으로 변환
        rows = []
        for r in results:
            rows.append({
                '날짜': r.get('analysis_date', ''),
                '종목코드': r.get('code', ''),
                '종목명': r.get('name', ''),
                '점수': r.get('score', 0),
                '종가': r.get('close', 0),
                '거래량': r.get('volume', 0),
                '신호': ', '.join(r.get('signals', [])),
                '적중여부': '적중' if r.get('is_hit') else ('미적중' if r.get('is_hit') is False else '-'),
                '최고수익률': round(r.get('max_return', 0), 1) if r.get('max_return') is not None else '-',
                '적중일': r.get('hit_day', '-') if r.get('hit_day') else '-',
                'RSI': r.get('indicators', {}).get('RSI', '-'),
                '거래량비율': r.get('indicators', {}).get('VOL_RATIO', '-'),
                'ADX': r.get('indicators', {}).get('ADX', '-'),
            })

        df = pd.DataFrame(rows)

        # 엑셀 저장 (여러 시트)
        with pd.ExcelWriter(DETAIL_FILE, engine='openpyxl') as writer:
            # 전체 데이터
            df.to_excel(writer, sheet_name='전체데이터', index=False)

            # 날짜별 요약
            daily_summary = df.groupby('날짜').agg({
                '종목코드': 'count',
                '점수': 'mean',
                '적중여부': lambda x: (x == '적중').sum()
            }).rename(columns={
                '종목코드': '분석종목수',
                '점수': '평균점수',
                '적중여부': '적중종목수'
            })
            daily_summary['적중률'] = (daily_summary['적중종목수'] / daily_summary['분석종목수'] * 100).round(1)
            daily_summary = daily_summary.sort_index()
            daily_summary.to_excel(writer, sheet_name='날짜별요약')

            # 종목별 요약 (가장 많이 선정된 종목)
            stock_summary = df.groupby(['종목코드', '종목명']).agg({
                '날짜': 'count',
                '점수': 'mean',
                '적중여부': lambda x: (x == '적중').sum()
            }).rename(columns={
                '날짜': '선정횟수',
                '점수': '평균점수',
                '적중여부': '적중횟수'
            })
            stock_summary['적중률'] = (stock_summary['적중횟수'] / stock_summary['선정횟수'] * 100).round(1)
            stock_summary = stock_summary.sort_values('선정횟수', ascending=False)
            stock_summary.to_excel(writer, sheet_name='종목별요약')

            # 고점수 종목 (80점 이상)
            high_score = df[df['점수'] >= 80].sort_values(['점수', '날짜'], ascending=[False, True])
            high_score.to_excel(writer, sheet_name='고점수종목(80이상)', index=False)

        print(f"    → 상세 데이터: {DETAIL_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="1년 백테스트 분석",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--weeks", type=int, default=52,
        help="백테스트 기간 (주 단위, 기본 52주 = 1년)"
    )
    parser.add_argument(
        "--top", type=int, default=100,
        help="일별 선정 종목 수 (기본 100)"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="중단된 백테스트 재개"
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="기존 결과로 리포트만 생성"
    )

    args = parser.parse_args()

    analyzer = BacktestAnalyzer(weeks=args.weeks, top_n=args.top)

    if args.report_only:
        if CHECKPOINT_FILE.exists():
            print("[리포트 모드] 기존 결과로 리포트 생성 중...")
            with open(CHECKPOINT_FILE, 'rb') as f:
                checkpoint = pickle.load(f)
            results = checkpoint.get('results', [])
            analysis = analyzer._analyze_results(results)
            analyzer._generate_report(analysis, results)
        else:
            print("[오류] 기존 백테스트 결과가 없습니다. 먼저 백테스트를 실행하세요.")
    else:
        analyzer.run_backtest(resume=args.resume)

    print("\n[완료] 1년 백테스트 분석 완료")


if __name__ == "__main__":
    main()
