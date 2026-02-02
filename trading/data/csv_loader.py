"""
장중 스코어 CSV 로더 모듈

목적:
- intraday_scores CSV 파일 로딩 통합
- 파일 신선도 체크 (15분 이내)
- 표준 파싱 로직

사용법:
    from trading.data import IntradayScoreLoader, load_latest_scores

    # 기본 사용
    loader = IntradayScoreLoader()
    df = loader.load_latest()

    # 특정 날짜 로드
    df = loader.load_by_date('20260128')

    # 간편 함수
    df = load_latest_scores()
"""

import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass


# 기본 경로
DEFAULT_SCORE_DIR = Path('/home/kimhc/Stock/output/intraday_scores')


@dataclass
class ScoreData:
    """스코어 데이터 결과"""
    df: pd.DataFrame
    file_path: str
    file_time: datetime
    is_fresh: bool  # 15분 이내 여부
    record_count: int

    @property
    def age_minutes(self) -> float:
        """파일 생성 후 경과 시간 (분)"""
        return (datetime.now() - self.file_time).total_seconds() / 60


class IntradayScoreLoader:
    """장중 스코어 CSV 로더

    CSV 파일 형식:
    - 파일명: YYYYMMDD_HHMM.csv (예: 20260128_1030.csv)
    - 컬럼: code, name, market, open, high, low, close, prev_close,
            change_pct, volume, volume_ratio, prev_amount, prev_marcap,
            buy_strength, foreign_net, inst_net, rel_strength,
            v1, v2, v4, v5, signals
    """

    # CSV 컬럼 타입 정의
    COLUMN_TYPES = {
        'code': str,
        'name': str,
        'market': str,
        'open': float,
        'high': float,
        'low': float,
        'close': float,
        'prev_close': float,
        'change_pct': float,
        'volume': int,
        'volume_ratio': float,
        'prev_amount': float,
        'prev_marcap': float,
        'buy_strength': float,
        'foreign_net': float,
        'inst_net': float,
        'rel_strength': float,
        'v1': int,
        'v2': int,
        'v4': int,
        'v5': int,
        'signals': str,
    }

    # 필수 컬럼
    REQUIRED_COLUMNS = {'code', 'name', 'close', 'volume', 'v2'}

    def __init__(
        self,
        score_dir: Optional[str] = None,
        max_age_minutes: int = 15
    ):
        """
        Args:
            score_dir: 스코어 CSV 디렉토리 경로
            max_age_minutes: 신선도 판정 기준 (분)
        """
        self.score_dir = Path(score_dir) if score_dir else DEFAULT_SCORE_DIR
        self.max_age_minutes = max_age_minutes

    def load_latest(self, min_freshness: bool = False) -> Optional[ScoreData]:
        """가장 최근 스코어 파일 로드

        Args:
            min_freshness: True면 신선하지 않은 파일은 None 반환

        Returns:
            ScoreData 또는 None
        """
        latest_file = self._get_latest_file()
        if not latest_file:
            return None

        result = self._load_file(latest_file)

        if min_freshness and result and not result.is_fresh:
            return None

        return result

    def load_by_date(
        self,
        date: str,
        time: Optional[str] = None
    ) -> Optional[ScoreData]:
        """특정 날짜/시간 스코어 파일 로드

        Args:
            date: 날짜 (YYYYMMDD)
            time: 시간 (HHMM), 없으면 해당 날짜 최신

        Returns:
            ScoreData 또는 None
        """
        if time:
            file_path = self.score_dir / f"{date}_{time}.csv"
            if file_path.exists():
                return self._load_file(file_path)
            return None

        # 해당 날짜의 최신 파일
        pattern = f"{date}_*.csv"
        files = sorted(self.score_dir.glob(pattern), reverse=True)
        if files:
            return self._load_file(files[0])

        return None

    def load_sequence(
        self,
        date: str,
        limit: int = 10
    ) -> List[ScoreData]:
        """특정 날짜의 연속 스코어 파일들 로드

        Args:
            date: 날짜 (YYYYMMDD)
            limit: 최대 로드 파일 수

        Returns:
            ScoreData 리스트 (시간순)
        """
        pattern = f"{date}_*.csv"
        files = sorted(self.score_dir.glob(pattern))[:limit]

        results = []
        for file_path in files:
            result = self._load_file(file_path)
            if result:
                results.append(result)

        return results

    def get_score_for_stock(
        self,
        stock_code: str,
        versions: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """특정 종목의 최신 스코어 조회

        Args:
            stock_code: 종목 코드
            versions: 조회할 버전 리스트 (기본: ['v2'])

        Returns:
            {'v2': 85, 'v4': 72, ...} 또는 None
        """
        data = self.load_latest()
        if not data:
            return None

        versions = versions or ['v2']

        # 종목 필터
        row = data.df[data.df['code'] == stock_code]
        if row.empty:
            return None

        row = row.iloc[0]
        result = {'code': stock_code, 'name': row.get('name', '')}

        for v in versions:
            if v in row.index:
                result[v] = int(row[v]) if pd.notna(row[v]) else 0

        return result

    def get_top_stocks(
        self,
        version: str = 'v2',
        min_score: int = 70,
        limit: int = 20
    ) -> List[Dict]:
        """상위 스코어 종목 조회

        Args:
            version: 스코어 버전 (v1, v2, v4, v5)
            min_score: 최소 점수
            limit: 최대 종목 수

        Returns:
            종목 정보 리스트
        """
        data = self.load_latest()
        if not data:
            return []

        df = data.df

        if version not in df.columns:
            return []

        # 필터 및 정렬
        filtered = df[df[version] >= min_score].copy()
        filtered = filtered.sort_values(version, ascending=False).head(limit)

        results = []
        for _, row in filtered.iterrows():
            results.append({
                'code': row['code'],
                'name': row.get('name', ''),
                'score': int(row[version]),
                'close': row.get('close', 0),
                'change_pct': row.get('change_pct', 0),
                'volume_ratio': row.get('volume_ratio', 1.0),
                'signals': row.get('signals', ''),
            })

        return results

    def _get_latest_file(self) -> Optional[Path]:
        """가장 최근 CSV 파일 경로"""
        if not self.score_dir.exists():
            return None

        files = sorted(self.score_dir.glob('*.csv'), reverse=True)
        return files[0] if files else None

    def _load_file(self, file_path: Path) -> Optional[ScoreData]:
        """CSV 파일 로드"""
        try:
            # 파일 시간 파싱 (YYYYMMDD_HHMM.csv)
            file_name = file_path.stem
            try:
                file_time = datetime.strptime(file_name, '%Y%m%d_%H%M')
            except ValueError:
                # 파일 수정 시간 사용
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)

            # CSV 로드
            df = pd.read_csv(
                file_path,
                dtype={'code': str},
                low_memory=False
            )

            # 컬럼 검증
            if not self.REQUIRED_COLUMNS.issubset(df.columns):
                missing = self.REQUIRED_COLUMNS - set(df.columns)
                print(f"CSV 필수 컬럼 누락: {missing}")
                return None

            # 타입 변환
            df = self._convert_types(df)

            # 신선도 판정
            age_minutes = (datetime.now() - file_time).total_seconds() / 60
            is_fresh = age_minutes <= self.max_age_minutes

            return ScoreData(
                df=df,
                file_path=str(file_path),
                file_time=file_time,
                is_fresh=is_fresh,
                record_count=len(df)
            )

        except Exception as e:
            print(f"CSV 로드 오류 ({file_path}): {e}")
            return None

    def _convert_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """컬럼 타입 변환"""
        for col, dtype in self.COLUMN_TYPES.items():
            if col in df.columns:
                try:
                    if dtype == int:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                    elif dtype == float:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                    elif dtype == str:
                        df[col] = df[col].fillna('').astype(str)
                except Exception:
                    pass
        return df


class ScoreDeltaAnalyzer:
    """스코어 변화량 분석기

    연속된 CSV 파일을 비교하여 스코어 변화(delta) 분석
    """

    def __init__(self, loader: Optional[IntradayScoreLoader] = None):
        self.loader = loader or IntradayScoreLoader()

    def analyze_delta(
        self,
        date: str,
        versions: List[str] = None
    ) -> Optional[pd.DataFrame]:
        """해당 날짜 스코어 변화량 분석

        Args:
            date: 날짜 (YYYYMMDD)
            versions: 분석할 버전 리스트

        Returns:
            변화량이 추가된 DataFrame
        """
        versions = versions or ['v2', 'v4']

        # 연속 파일 로드
        sequence = self.loader.load_sequence(date, limit=20)
        if len(sequence) < 2:
            return None

        # 최신 2개 비교
        prev_data = sequence[-2]
        curr_data = sequence[-1]

        prev_df = prev_data.df.set_index('code')
        curr_df = curr_data.df.set_index('code')

        # 공통 종목만
        common_codes = prev_df.index.intersection(curr_df.index)
        if len(common_codes) == 0:
            return None

        result = curr_df.loc[common_codes].copy()

        # 델타 계산
        for v in versions:
            if v in prev_df.columns and v in curr_df.columns:
                delta_col = f'{v}_delta'
                result[delta_col] = (
                    curr_df.loc[common_codes, v] -
                    prev_df.loc[common_codes, v]
                )

        # 시간 정보 추가
        result['prev_time'] = prev_data.file_time.strftime('%H:%M')
        result['curr_time'] = curr_data.file_time.strftime('%H:%M')

        return result.reset_index()

    def get_rising_stocks(
        self,
        date: str,
        version: str = 'v2',
        min_delta: int = 5
    ) -> List[Dict]:
        """스코어 상승 종목 조회

        Args:
            date: 날짜
            version: 스코어 버전
            min_delta: 최소 상승폭

        Returns:
            상승 종목 리스트
        """
        df = self.analyze_delta(date, versions=[version])
        if df is None:
            return []

        delta_col = f'{version}_delta'
        if delta_col not in df.columns:
            return []

        rising = df[df[delta_col] >= min_delta].copy()
        rising = rising.sort_values(delta_col, ascending=False)

        results = []
        for _, row in rising.iterrows():
            results.append({
                'code': row['code'],
                'name': row.get('name', ''),
                'score': int(row[version]),
                'delta': int(row[delta_col]),
                'change_pct': row.get('change_pct', 0),
            })

        return results


# 편의 함수

def get_latest_score_file(
    score_dir: Optional[str] = None
) -> Optional[str]:
    """가장 최근 스코어 파일 경로 반환"""
    loader = IntradayScoreLoader(score_dir=score_dir)
    data = loader.load_latest()
    return data.file_path if data else None


def load_latest_scores(
    score_dir: Optional[str] = None,
    min_freshness: bool = False
) -> Optional[pd.DataFrame]:
    """최신 스코어 DataFrame 반환

    Args:
        score_dir: 스코어 디렉토리
        min_freshness: 신선하지 않으면 None 반환

    Returns:
        스코어 DataFrame
    """
    loader = IntradayScoreLoader(score_dir=score_dir)
    data = loader.load_latest(min_freshness=min_freshness)
    return data.df if data else None


def get_stock_score(
    stock_code: str,
    version: str = 'v2',
    score_dir: Optional[str] = None
) -> Optional[int]:
    """특정 종목 스코어 조회"""
    loader = IntradayScoreLoader(score_dir=score_dir)
    result = loader.get_score_for_stock(stock_code, versions=[version])
    return result.get(version) if result else None
