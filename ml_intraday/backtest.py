#!/usr/bin/env python3
"""
백테스트 모듈

학습된 ML 모델의 성과를 시뮬레이션합니다.

사용법:
    python ml_intraday/backtest.py                     # 기본 백테스트
    python ml_intraday/backtest.py --report            # 상세 리포트
    python ml_intraday/backtest.py --threshold 0.7    # 확률 임계값 변경
"""

import os
import sys
import argparse
import functools
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml_intraday.config import (
    OUTPUT_DIR, MODEL_DIR, BACKTEST_CONFIG,
    LABEL_ENCODING, LABEL_DECODING
)

# 출력 즉시 플러시
print = functools.partial(print, flush=True)


class BacktestEngine:
    """백테스트 엔진"""

    def __init__(
        self,
        initial_capital: float = 100_000_000,  # 1억
        commission: float = None,
        slippage: float = None,
        tax: float = None
    ):
        self.initial_capital = initial_capital

        # 거래 비용
        self.commission = commission or BACKTEST_CONFIG['commission']
        self.slippage = slippage or BACKTEST_CONFIG['slippage']
        self.tax = tax or BACKTEST_CONFIG['tax']

        # 총 비용률 (편도)
        self.cost_rate = self.commission + self.slippage

        # 상태 초기화
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.capital = self.initial_capital
        self.positions = {}  # {code: {'shares': N, 'avg_price': P, 'entry_time': T}}
        self.trades = []  # 거래 기록
        self.equity_curve = []  # 자산 곡선
        self.daily_returns = []  # 일별 수익률

    def buy(
        self,
        code: str,
        price: float,
        amount: float,
        timestamp: str,
        signal_prob: float = 0
    ) -> bool:
        """
        매수 실행

        Args:
            code: 종목코드
            price: 매수가
            amount: 매수금액
            timestamp: 시간
            signal_prob: ML 신호 확률

        Returns:
            성공 여부
        """
        if amount > self.capital:
            amount = self.capital

        if amount < 10000:  # 최소 1만원
            return False

        # 슬리피지 적용
        buy_price = price * (1 + self.slippage)

        # 수수료 적용
        cost = amount * self.commission
        shares = int((amount - cost) / buy_price)

        if shares <= 0:
            return False

        actual_amount = shares * buy_price + cost

        # 자본 차감
        self.capital -= actual_amount

        # 포지션 추가
        if code in self.positions:
            # 추가 매수 (평균 단가 계산)
            pos = self.positions[code]
            total_shares = pos['shares'] + shares
            total_cost = pos['shares'] * pos['avg_price'] + shares * buy_price
            self.positions[code] = {
                'shares': total_shares,
                'avg_price': total_cost / total_shares,
                'entry_time': pos['entry_time'],
            }
        else:
            self.positions[code] = {
                'shares': shares,
                'avg_price': buy_price,
                'entry_time': timestamp,
            }

        # 거래 기록
        self.trades.append({
            'timestamp': timestamp,
            'code': code,
            'action': 'BUY',
            'price': buy_price,
            'shares': shares,
            'amount': actual_amount,
            'signal_prob': signal_prob,
        })

        return True

    def sell(
        self,
        code: str,
        price: float,
        timestamp: str,
        reason: str = ''
    ) -> Optional[Dict]:
        """
        매도 실행

        Args:
            code: 종목코드
            price: 매도가
            timestamp: 시간
            reason: 매도 사유

        Returns:
            거래 결과 딕셔너리
        """
        if code not in self.positions:
            return None

        pos = self.positions[code]
        shares = pos['shares']

        # 슬리피지 적용
        sell_price = price * (1 - self.slippage)

        # 세금 + 수수료
        gross_amount = shares * sell_price
        tax_cost = gross_amount * self.tax
        commission_cost = gross_amount * self.commission
        net_amount = gross_amount - tax_cost - commission_cost

        # 수익률 계산
        entry_amount = shares * pos['avg_price']
        profit = net_amount - entry_amount
        profit_pct = profit / entry_amount * 100

        # 자본 추가
        self.capital += net_amount

        # 포지션 제거
        del self.positions[code]

        # 거래 기록
        trade = {
            'timestamp': timestamp,
            'code': code,
            'action': 'SELL',
            'price': sell_price,
            'shares': shares,
            'amount': net_amount,
            'entry_price': pos['avg_price'],
            'entry_time': pos['entry_time'],
            'profit': profit,
            'profit_pct': profit_pct,
            'reason': reason,
        }
        self.trades.append(trade)

        return trade

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """현재 포트폴리오 가치 계산"""
        holdings_value = 0
        for code, pos in self.positions.items():
            price = current_prices.get(code, pos['avg_price'])
            holdings_value += pos['shares'] * price

        return self.capital + holdings_value

    def record_equity(self, timestamp: str, current_prices: Dict[str, float]):
        """자산 곡선 기록"""
        value = self.get_portfolio_value(current_prices)
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': value,
            'capital': self.capital,
            'holdings_value': value - self.capital,
            'n_positions': len(self.positions),
        })


def load_model(horizon: str = '10min'):
    """학습된 모델 로드"""
    model_path = MODEL_DIR / f"intraday_lgbm_{horizon}.pkl"

    if not model_path.exists():
        print(f"[에러] 모델 파일 없음: {model_path}")
        return None, None

    with open(model_path, 'rb') as f:
        data = pickle.load(f)

    return data['model'], data['feature_names']


def load_test_data(horizon: str = '10min') -> pd.DataFrame:
    """테스트 데이터 로드"""
    data_path = OUTPUT_DIR / f"labeled_{horizon}.parquet"

    if not data_path.exists():
        print(f"[에러] 데이터 없음: {data_path}")
        return pd.DataFrame()

    df = pd.read_parquet(data_path)

    # 마지막 15% 데이터만 (테스트셋)
    dates = sorted(df['date'].unique())
    n_test = max(1, int(len(dates) * 0.15))
    test_dates = dates[-n_test:]

    test_df = df[df['date'].isin(test_dates)]

    return test_df


def run_backtest(
    horizon: str = '10min',
    min_probability: float = 0.6,
    max_positions: int = 5,
    position_size: float = 0.1,  # 총 자산의 10%
    use_scores: bool = True
) -> Dict:
    """
    백테스트 실행

    Args:
        horizon: 예측 범위
        min_probability: 최소 BUY 확률
        max_positions: 최대 포지션 수
        position_size: 포지션 크기 (자산 대비 비율)
        use_scores: V2/V4 스코어 필터 사용

    Returns:
        백테스트 결과
    """
    print("=" * 60)
    print("  백테스트")
    print("=" * 60)

    # 모델 로드
    print(f"\n[1] 모델 로드 (horizon={horizon})...")
    model, feature_names = load_model(horizon)
    if model is None:
        return {}

    # 데이터 로드
    print(f"\n[2] 테스트 데이터 로드...")
    df = load_test_data(horizon)
    if df.empty:
        return {}

    print(f"  {len(df):,}샘플, {df['date'].nunique()}일")

    # 피처 준비
    X = df[feature_names].fillna(0).replace([np.inf, -np.inf], 0)

    # 예측
    print(f"\n[3] 예측...")
    proba = model.predict_proba(X)
    df['buy_prob'] = proba[:, LABEL_ENCODING['BUY']]
    df['sell_prob'] = proba[:, LABEL_ENCODING['SELL']]
    df['pred'] = model.predict(X)

    # 백테스트 엔진
    print(f"\n[4] 백테스트 실행...")
    engine = BacktestEngine()

    # 날짜+시간순 정렬
    df = df.sort_values(['date', 'time']).reset_index(drop=True)

    # 시뮬레이션
    buy_signals = 0
    filtered_by_score = 0

    for date in df['date'].unique():
        day_df = df[df['date'] == date]

        # 일별 처리
        for _, row in day_df.iterrows():
            code = row['code']
            price = row['close']
            timestamp = f"{row['date']}_{row['time']}"
            buy_prob = row['buy_prob']

            # 현재 포트폴리오 가치
            current_prices = {code: row['close']}
            for pos_code in engine.positions:
                pos_price = day_df[day_df['code'] == pos_code]['close'].iloc[-1] if pos_code in day_df['code'].values else engine.positions[pos_code]['avg_price']
                current_prices[pos_code] = pos_price

            portfolio_value = engine.get_portfolio_value(current_prices)

            # 매도 조건 체크 (보유 종목)
            if code in engine.positions:
                pos = engine.positions[code]
                pnl_pct = (price - pos['avg_price']) / pos['avg_price'] * 100

                # 손절
                if pnl_pct <= BACKTEST_CONFIG['stop_loss'] * 100:
                    engine.sell(code, price, timestamp, 'stop_loss')
                    continue

                # 익절
                if pnl_pct >= BACKTEST_CONFIG['take_profit'] * 100:
                    engine.sell(code, price, timestamp, 'take_profit')
                    continue

                # SELL 신호
                if row['sell_prob'] > 0.6:
                    engine.sell(code, price, timestamp, 'ml_signal')
                    continue

            # 매수 조건 체크
            if buy_prob >= min_probability:
                buy_signals += 1

                # 포지션 수 제한
                if len(engine.positions) >= max_positions:
                    continue

                # 스코어 필터
                if use_scores:
                    v2 = row.get('v2_score', 0)
                    v4 = row.get('v4_score', 0)

                    if v2 < BACKTEST_CONFIG['min_score_v2'] or v4 < BACKTEST_CONFIG['min_score_v4']:
                        filtered_by_score += 1
                        continue

                # 매수 금액
                buy_amount = portfolio_value * position_size

                engine.buy(code, price, buy_amount, timestamp, buy_prob)

        # 일말 청산 (장 종료 시 모든 포지션 청산)
        closing_time = day_df[day_df['time'] >= '150000']
        if not closing_time.empty:
            for code in list(engine.positions.keys()):
                code_df = closing_time[closing_time['code'] == code]
                if not code_df.empty:
                    price = code_df.iloc[-1]['close']
                    engine.sell(code, price, f"{date}_closing", 'day_end')

        # 자산 기록
        engine.record_equity(date, current_prices)

    # 결과 분석
    print(f"\n[5] 결과 분석...")
    results = analyze_results(engine, buy_signals, filtered_by_score)

    return results


def analyze_results(
    engine: BacktestEngine,
    total_signals: int,
    filtered_signals: int
) -> Dict:
    """백테스트 결과 분석"""
    trades_df = pd.DataFrame(engine.trades)
    equity_df = pd.DataFrame(engine.equity_curve)

    # 매도 거래만 (수익 계산 가능)
    sell_trades = trades_df[trades_df['action'] == 'SELL']

    results = {
        'total_signals': total_signals,
        'filtered_by_score': filtered_signals,
        'total_trades': len(sell_trades),
    }

    if sell_trades.empty:
        print("  거래 없음")
        return results

    # 승률
    wins = sell_trades[sell_trades['profit'] > 0]
    results['win_rate'] = len(wins) / len(sell_trades)
    results['wins'] = len(wins)
    results['losses'] = len(sell_trades) - len(wins)

    # 수익률 통계
    results['avg_return'] = sell_trades['profit_pct'].mean()
    results['median_return'] = sell_trades['profit_pct'].median()
    results['std_return'] = sell_trades['profit_pct'].std()
    results['total_profit'] = sell_trades['profit'].sum()

    # 최종 자산
    results['final_equity'] = engine.capital
    results['total_return'] = (results['final_equity'] - engine.initial_capital) / engine.initial_capital * 100

    # 최대 낙폭 (MDD)
    if not equity_df.empty:
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
        results['max_drawdown'] = equity_df['drawdown'].min()
    else:
        results['max_drawdown'] = 0

    # Sharpe Ratio (일별 수익률 기준)
    if len(equity_df) > 1:
        equity_df['daily_return'] = equity_df['equity'].pct_change()
        daily_returns = equity_df['daily_return'].dropna()
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            results['sharpe_ratio'] = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            results['sharpe_ratio'] = 0
    else:
        results['sharpe_ratio'] = 0

    # 매도 사유별 통계
    reason_stats = sell_trades.groupby('reason').agg({
        'profit_pct': ['count', 'mean'],
        'profit': 'sum'
    }).round(2)

    # 출력
    print("\n" + "=" * 40)
    print("  백테스트 결과")
    print("=" * 40)
    print(f"\n[거래 통계]")
    print(f"  총 신호: {results['total_signals']:,}")
    print(f"  스코어 필터: {results['filtered_by_score']:,}")
    print(f"  실행 거래: {results['total_trades']:,}")
    print(f"  승: {results['wins']:,}, 패: {results['losses']:,}")
    print(f"  승률: {results['win_rate']*100:.1f}%")

    print(f"\n[수익률]")
    print(f"  평균: {results['avg_return']:.2f}%")
    print(f"  중앙값: {results['median_return']:.2f}%")
    print(f"  표준편차: {results['std_return']:.2f}%")
    print(f"  총 수익: {results['total_profit']:,.0f}원")

    print(f"\n[포트폴리오]")
    print(f"  초기 자산: {engine.initial_capital:,.0f}원")
    print(f"  최종 자산: {results['final_equity']:,.0f}원")
    print(f"  총 수익률: {results['total_return']:.2f}%")
    print(f"  최대 낙폭: {results['max_drawdown']:.2f}%")
    print(f"  Sharpe Ratio: {results['sharpe_ratio']:.2f}")

    print(f"\n[매도 사유별]")
    print(reason_stats.to_string())

    # 결과 저장
    results['trades'] = trades_df.to_dict('records')
    results['equity_curve'] = equity_df.to_dict('records')

    return results


def save_backtest_report(results: Dict, horizon: str = '10min'):
    """백테스트 리포트 저장"""
    if not results:
        return

    # 거래 내역 저장
    if 'trades' in results:
        trades_df = pd.DataFrame(results['trades'])
        trades_path = OUTPUT_DIR / f"backtest_trades_{horizon}.csv"
        trades_df.to_csv(trades_path, index=False)
        print(f"\n거래 내역: {trades_path}")

    # 자산 곡선 저장
    if 'equity_curve' in results:
        equity_df = pd.DataFrame(results['equity_curve'])
        equity_path = OUTPUT_DIR / f"backtest_equity_{horizon}.csv"
        equity_df.to_csv(equity_path, index=False)
        print(f"자산 곡선: {equity_path}")

    # 요약 저장
    summary = {k: v for k, v in results.items() if k not in ['trades', 'equity_curve']}
    summary_df = pd.DataFrame([summary])
    summary_path = OUTPUT_DIR / f"backtest_summary_{horizon}.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"요약: {summary_path}")


def optimize_threshold(horizon: str = '10min'):
    """
    최적 확률 임계값 탐색
    """
    print("=" * 60)
    print("  임계값 최적화")
    print("=" * 60)

    thresholds = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]
    results_list = []

    for threshold in thresholds:
        print(f"\n--- 임계값: {threshold} ---")
        results = run_backtest(
            horizon=horizon,
            min_probability=threshold,
            use_scores=True
        )

        if results:
            results['threshold'] = threshold
            results_list.append({
                'threshold': threshold,
                'win_rate': results.get('win_rate', 0),
                'avg_return': results.get('avg_return', 0),
                'total_trades': results.get('total_trades', 0),
                'sharpe_ratio': results.get('sharpe_ratio', 0),
                'max_drawdown': results.get('max_drawdown', 0),
            })

    # 결과 비교
    if results_list:
        compare_df = pd.DataFrame(results_list)
        print("\n" + "=" * 60)
        print("  임계값별 결과 비교")
        print("=" * 60)
        print(compare_df.to_string(index=False))

        # 최적 임계값 (Sharpe 기준)
        best = compare_df.loc[compare_df['sharpe_ratio'].idxmax()]
        print(f"\n최적 임계값 (Sharpe 기준): {best['threshold']}")


def main():
    parser = argparse.ArgumentParser(description="백테스트")
    parser.add_argument(
        "--horizon",
        type=str,
        default="2min",  # 스캘핑 기본값
        choices=["1min", "2min", "3min", "5min"],  # 스캘핑용
        help="예측 범위"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="최소 BUY 확률"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="상세 리포트 저장"
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="임계값 최적화"
    )
    parser.add_argument(
        "--no-scores",
        action="store_true",
        help="스코어 필터 비활성화"
    )

    args = parser.parse_args()

    if args.optimize:
        optimize_threshold(args.horizon)
    else:
        results = run_backtest(
            horizon=args.horizon,
            min_probability=args.threshold,
            use_scores=not args.no_scores
        )

        if args.report and results:
            save_backtest_report(results, args.horizon)


if __name__ == "__main__":
    main()
