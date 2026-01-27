"""
장중 스코어 CSV 모니터링 모듈
10분마다 기록되는 V1~V10 스코어를 로드하고 필터링
"""

import os
import glob
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ScoreMonitor:
    """장중 스코어 CSV 모니터"""

    def __init__(self, scores_dir: str = None):
        """
        Args:
            scores_dir: 스코어 CSV 디렉토리 (기본: output/intraday_scores/)
        """
        if scores_dir is None:
            scores_dir = Path(__file__).parent.parent.parent / "output" / "intraday_scores"
        self.scores_dir = Path(scores_dir)

        # CSV 컬럼 정의
        self.score_columns = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9_prob']
        self.price_columns = ['open', 'high', 'low', 'close', 'prev_close', 'change_pct']

    def get_latest_file(self, date: str = None) -> Optional[Path]:
        """
        최신 스코어 CSV 파일 경로 반환

        Args:
            date: 날짜 (YYYYMMDD). None이면 오늘

        Returns:
            최신 CSV 파일 경로 또는 None
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')

        pattern = self.scores_dir / f"{date}_*.csv"
        files = sorted(glob.glob(str(pattern)), reverse=True)

        if files:
            return Path(files[0])
        return None

    def get_latest_scores(self, date: str = None) -> Optional[pd.DataFrame]:
        """
        최신 스코어 데이터프레임 로드

        Args:
            date: 날짜 (YYYYMMDD). None이면 오늘

        Returns:
            스코어 DataFrame 또는 None
        """
        csv_file = self.get_latest_file(date)
        if csv_file is None:
            return None

        try:
            df = pd.read_csv(csv_file, dtype={'code': str})
            # 코드 6자리 패딩
            df['code'] = df['code'].str.zfill(6)
            return df
        except Exception as e:
            print(f"스코어 CSV 로드 실패: {e}")
            return None

    def get_file_timestamp(self, date: str = None) -> Optional[datetime]:
        """
        최신 파일의 타임스탬프 반환

        Args:
            date: 날짜 (YYYYMMDD)

        Returns:
            파일명에서 추출한 datetime
        """
        csv_file = self.get_latest_file(date)
        if csv_file is None:
            return None

        # 파일명: YYYYMMDD_HHMM.csv
        filename = csv_file.stem  # 20260127_1433
        try:
            return datetime.strptime(filename, '%Y%m%d_%H%M')
        except ValueError:
            return None

    def filter_by_score(
        self,
        df: pd.DataFrame,
        score_column: str,
        min_score: int,
        max_score: int = 100
    ) -> pd.DataFrame:
        """
        특정 스코어 범위로 필터링

        Args:
            df: 스코어 DataFrame
            score_column: 스코어 컬럼 (v1, v2, v3.5, v4, v5, v6, v7, v8)
            min_score: 최소 스코어
            max_score: 최대 스코어

        Returns:
            필터링된 DataFrame
        """
        if score_column not in df.columns:
            return pd.DataFrame()

        mask = (df[score_column] >= min_score) & (df[score_column] <= max_score)
        return df[mask].copy()

    def filter_by_amount(
        self,
        df: pd.DataFrame,
        min_amount: int = 5_000_000_000  # 50억
    ) -> pd.DataFrame:
        """
        거래대금 필터링

        Args:
            df: 스코어 DataFrame
            min_amount: 최소 거래대금 (원)

        Returns:
            필터링된 DataFrame
        """
        if 'prev_amount' not in df.columns:
            return df

        return df[df['prev_amount'] >= min_amount].copy()

    def filter_by_price_change(
        self,
        df: pd.DataFrame,
        min_change: float = None,
        max_change: float = None
    ) -> pd.DataFrame:
        """
        등락률 필터링

        Args:
            df: 스코어 DataFrame
            min_change: 최소 등락률 (%)
            max_change: 최대 등락률 (%)

        Returns:
            필터링된 DataFrame
        """
        if 'change_pct' not in df.columns:
            return df

        result = df.copy()

        if min_change is not None:
            result = result[result['change_pct'] >= min_change]
        if max_change is not None:
            result = result[result['change_pct'] <= max_change]

        return result

    def filter_by_signals(
        self,
        df: pd.DataFrame,
        required_signals: List[str] = None,
        excluded_signals: List[str] = None
    ) -> pd.DataFrame:
        """
        시그널 기반 필터링

        Args:
            df: 스코어 DataFrame
            required_signals: 필수 포함 시그널 (예: ['MA_ALIGNED', 'MACD_BULL'])
            excluded_signals: 제외 시그널 (예: ['RSI_OVERBOUGHT'])

        Returns:
            필터링된 DataFrame
        """
        if 'signals' not in df.columns:
            return df

        result = df.copy()

        if required_signals:
            for signal in required_signals:
                mask = result['signals'].str.contains(signal, na=False)
                result = result[mask]

        if excluded_signals:
            for signal in excluded_signals:
                mask = ~result['signals'].str.contains(signal, na=False)
                result = result[mask]

        return result

    def get_top_stocks(
        self,
        score_column: str = 'v2',
        top_n: int = 20,
        min_score: int = 60,
        min_amount: int = 5_000_000_000,
        max_change: float = 15.0,
        date: str = None
    ) -> pd.DataFrame:
        """
        상위 종목 조회 (종합 필터링)

        Args:
            score_column: 정렬 기준 스코어
            top_n: 상위 N개
            min_score: 최소 스코어
            min_amount: 최소 거래대금
            max_change: 최대 등락률 (상한가 제외)
            date: 날짜

        Returns:
            상위 종목 DataFrame
        """
        df = self.get_latest_scores(date)
        if df is None or df.empty:
            return pd.DataFrame()

        # 필터링
        df = self.filter_by_score(df, score_column, min_score)
        df = self.filter_by_amount(df, min_amount)
        df = self.filter_by_price_change(df, max_change=max_change)

        # 정렬 및 상위 N개
        if score_column in df.columns:
            df = df.sort_values(score_column, ascending=False).head(top_n)

        return df

    def get_v2_trend_candidates(
        self,
        min_score: int = 75,
        min_amount: int = 5_000_000_000,
        date: str = None
    ) -> pd.DataFrame:
        """
        V2 추세추종 전략 후보 종목

        Args:
            min_score: 최소 V2 스코어
            min_amount: 최소 거래대금
            date: 날짜

        Returns:
            후보 종목 DataFrame
        """
        df = self.get_latest_scores(date)
        if df is None or df.empty:
            return pd.DataFrame()

        # V2 기준 필터링
        df = self.filter_by_score(df, 'v2', min_score)
        df = self.filter_by_amount(df, min_amount)

        # 추세 관련 시그널 필터
        df = self.filter_by_signals(
            df,
            required_signals=['MA_ALIGNED'],
            excluded_signals=['RSI_OVERBOUGHT']
        )

        # 상한가(+29%) 제외
        df = self.filter_by_price_change(df, max_change=28.0)

        return df.sort_values('v2', ascending=False)

    def get_v8_bounce_candidates(
        self,
        min_score: int = 70,
        min_amount: int = 5_000_000_000,
        date: str = None
    ) -> pd.DataFrame:
        """
        V8 역발상반등 전략 후보 종목

        Args:
            min_score: 최소 V8 스코어
            min_amount: 최소 거래대금
            date: 날짜

        Returns:
            후보 종목 DataFrame
        """
        df = self.get_latest_scores(date)
        if df is None or df.empty:
            return pd.DataFrame()

        # V8 기준 필터링
        df = self.filter_by_score(df, 'v8', min_score)
        df = self.filter_by_amount(df, min_amount)

        # 역발상: 하락 후 반등 중인 종목
        # V8은 약세종목 모멘텀 반전에 특화
        df = self.filter_by_price_change(df, min_change=-5.0, max_change=10.0)

        return df.sort_values('v8', ascending=False)

    def get_v10_follower_candidates(
        self,
        min_correlation: float = 0.6,
        leader_min_change: float = 3.0,
        date: str = None
    ) -> pd.DataFrame:
        """
        V10 대장주-종속주 전략 후보 종목
        (실제 V10 점수 계산은 별도 로직 필요)

        Args:
            min_correlation: 최소 상관계수
            leader_min_change: 대장주 최소 상승률
            date: 날짜

        Returns:
            후보 종목 DataFrame (추후 V10 엔진과 연동)
        """
        # V10은 실시간 대장주-종속주 관계 분석 필요
        # 여기서는 기본 필터링만 수행
        df = self.get_latest_scores(date)
        if df is None or df.empty:
            return pd.DataFrame()

        # 거래대금 필터
        df = self.filter_by_amount(df, 5_000_000_000)

        # 아직 덜 오른 종목 (대장주 대비 언더퍼폼)
        df = self.filter_by_price_change(df, min_change=-2.0, max_change=5.0)

        return df

    def get_all_candidates(
        self,
        strategies: Dict = None,
        date: str = None
    ) -> Dict[str, pd.DataFrame]:
        """
        모든 전략별 후보 종목 조회

        Args:
            strategies: 전략별 설정 (없으면 기본값 사용)
            date: 날짜

        Returns:
            전략명 -> DataFrame 매핑
        """
        if strategies is None:
            strategies = {
                'v2_trend': {'min_score': 75},
                'v8_bounce': {'min_score': 70}
            }

        results = {}

        if 'v2_trend' in strategies:
            params = strategies['v2_trend']
            results['v2_trend'] = self.get_v2_trend_candidates(
                min_score=params.get('min_score', 75),
                date=date
            )

        if 'v8_bounce' in strategies:
            params = strategies['v8_bounce']
            results['v8_bounce'] = self.get_v8_bounce_candidates(
                min_score=params.get('min_score', 70),
                date=date
            )

        if 'v10_follower' in strategies:
            params = strategies['v10_follower']
            results['v10_follower'] = self.get_v10_follower_candidates(
                min_correlation=params.get('min_correlation', 0.6),
                leader_min_change=params.get('leader_min_change', 3.0),
                date=date
            )

        return results

    def compare_scores(
        self,
        code: str,
        date: str = None
    ) -> Optional[Dict]:
        """
        특정 종목의 모든 버전 스코어 비교

        Args:
            code: 종목코드
            date: 날짜

        Returns:
            버전별 스코어 딕셔너리
        """
        df = self.get_latest_scores(date)
        if df is None or df.empty:
            return None

        code = str(code).zfill(6)
        row = df[df['code'] == code]

        if row.empty:
            return None

        row = row.iloc[0]

        result = {
            'code': code,
            'name': row.get('name', ''),
            'close': row.get('close', 0),
            'change_pct': row.get('change_pct', 0),
            'scores': {}
        }

        for col in self.score_columns:
            if col in row:
                result['scores'][col] = row[col]

        if 'signals' in row:
            result['signals'] = row['signals']

        return result


if __name__ == "__main__":
    # 테스트
    monitor = ScoreMonitor()

    print("=== 최신 스코어 파일 ===")
    latest = monitor.get_latest_file()
    print(f"파일: {latest}")
    print(f"시간: {monitor.get_file_timestamp()}")

    print("\n=== V2 추세추종 후보 (상위 10개) ===")
    v2_df = monitor.get_v2_trend_candidates(min_score=70)
    if not v2_df.empty:
        for _, row in v2_df.head(10).iterrows():
            print(f"{row['code']} {row['name']:12s} V2={row['v2']:3.0f} {row['change_pct']:+6.2f}%")

    print("\n=== V8 역발상 후보 (상위 5개) ===")
    v8_df = monitor.get_v8_bounce_candidates(min_score=60)
    if not v8_df.empty:
        for _, row in v8_df.head(5).iterrows():
            print(f"{row['code']} {row['name']:12s} V8={row['v8']:3.0f} {row['change_pct']:+6.2f}%")
