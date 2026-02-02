"""
배치 스코어러

목적:
- 다수 종목 병렬 스코어 계산
- 진행률 콜백 지원
- 성능 최적화 (IndicatorCache 활용)

사용법:
    from scoring.batch_scorer import BatchScorer

    scorer = BatchScorer(versions=['v2', 'v4'])

    # 기본 사용
    results = scorer.score_batch(stocks_dict)

    # 진행률 콜백
    def on_progress(completed, total, current_code):
        print(f"{completed}/{total}: {current_code}")

    results = scorer.score_batch(stocks_dict, on_progress=on_progress)

    # 병렬 처리
    results = scorer.score_batch(stocks_dict, parallel=True, max_workers=4)
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
import pandas as pd

from .indicators import calculate_base_indicators, IndicatorCache


@dataclass
class BatchResult:
    """배치 스코어 결과"""
    results: Dict[str, Dict]  # {종목코드: 스코어 결과}
    elapsed_seconds: float
    total_count: int
    success_count: int
    failed_count: int
    versions_used: List[str]
    cache_stats: Optional[Dict] = None

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count > 0 else 0.0

    def get_top_stocks(
        self,
        version: str = 'v2',
        min_score: int = 70,
        limit: int = 20
    ) -> List[Dict]:
        """상위 스코어 종목 반환"""
        scored = []
        for code, result in self.results.items():
            if version in result:
                score = result[version].get('score', 0)
                if score >= min_score:
                    scored.append({
                        'code': code,
                        'score': score,
                        'signals': result[version].get('signals', []),
                        **result.get('info', {})
                    })

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:limit]

    def to_dataframe(self, version: str = 'v2') -> pd.DataFrame:
        """결과를 DataFrame으로 변환"""
        rows = []
        for code, result in self.results.items():
            if version in result:
                row = {
                    'code': code,
                    'score': result[version].get('score', 0),
                    'signals': ','.join(result[version].get('signals', [])),
                }
                # 그룹 점수 추가
                for key, val in result[version].items():
                    if key.endswith('_score'):
                        row[key] = val
                rows.append(row)

        return pd.DataFrame(rows)


class BatchScorer:
    """배치 스코어러"""

    def __init__(
        self,
        versions: Optional[List[str]] = None,
        use_cache: bool = True,
        cache_maxsize: int = 1000
    ):
        """
        Args:
            versions: 계산할 스코어 버전 리스트 (기본: ['v2'])
            use_cache: 지표 캐시 사용 여부
            cache_maxsize: 캐시 최대 크기
        """
        self.versions = versions or ['v2']
        self.use_cache = use_cache

        if use_cache:
            self._cache = IndicatorCache(maxsize=cache_maxsize)
        else:
            self._cache = None

        # 버전별 함수 준비 (순환 임포트 방지를 위해 지연 로드)
        self._score_funcs = self._load_score_functions()

    def _load_score_functions(self) -> Dict:
        """스코어링 함수 로드 (순환 임포트 방지)"""
        from .scoring_v1 import calculate_score_v1
        from .scoring_v2 import calculate_score_v2
        from .scoring_v4 import calculate_score_v4
        from .scoring_v5 import calculate_score_v5

        available = {
            'v1': calculate_score_v1,
            'v2': calculate_score_v2,
            'v4': calculate_score_v4,
            'v5': calculate_score_v5,
        }

        funcs = {}
        for v in self.versions:
            if v in available:
                funcs[v] = available[v]
            else:
                print(f"경고: 알 수 없는 버전 '{v}'")

        return funcs

    def score_batch(
        self,
        stocks: Dict[str, pd.DataFrame],
        parallel: bool = False,
        max_workers: int = 4,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        stock_info: Optional[Dict[str, Dict]] = None
    ) -> BatchResult:
        """배치 스코어 계산

        Args:
            stocks: {종목코드: OHLCV DataFrame} 딕셔너리
            parallel: 병렬 처리 여부
            max_workers: 병렬 워커 수
            on_progress: 진행률 콜백 (completed, total, current_code)
            stock_info: {종목코드: {name, market, ...}} 추가 정보

        Returns:
            BatchResult 객체
        """
        start_time = time.time()
        total_count = len(stocks)
        results = {}
        failed_count = 0

        stock_info = stock_info or {}

        if parallel and max_workers > 1:
            results, failed_count = self._score_parallel(
                stocks, max_workers, on_progress, stock_info
            )
        else:
            results, failed_count = self._score_sequential(
                stocks, on_progress, stock_info
            )

        elapsed = time.time() - start_time

        return BatchResult(
            results=results,
            elapsed_seconds=elapsed,
            total_count=total_count,
            success_count=total_count - failed_count,
            failed_count=failed_count,
            versions_used=self.versions,
            cache_stats=self._cache.stats if self._cache else None
        )

    def _score_sequential(
        self,
        stocks: Dict[str, pd.DataFrame],
        on_progress: Optional[Callable],
        stock_info: Dict[str, Dict]
    ) -> tuple:
        """순차 처리"""
        results = {}
        failed_count = 0
        total = len(stocks)

        for i, (code, df) in enumerate(stocks.items()):
            try:
                result = self._score_one(code, df)
                if result:
                    result['info'] = stock_info.get(code, {})
                    results[code] = result
                else:
                    failed_count += 1
            except Exception as e:
                print(f"스코어 계산 오류 [{code}]: {e}")
                failed_count += 1

            if on_progress:
                on_progress(i + 1, total, code)

        return results, failed_count

    def _score_parallel(
        self,
        stocks: Dict[str, pd.DataFrame],
        max_workers: int,
        on_progress: Optional[Callable],
        stock_info: Dict[str, Dict]
    ) -> tuple:
        """병렬 처리"""
        results = {}
        failed_count = 0
        total = len(stocks)
        completed = 0

        def score_task(item):
            code, df = item
            try:
                result = self._score_one(code, df)
                return code, result
            except Exception as e:
                print(f"스코어 계산 오류 [{code}]: {e}")
                return code, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(score_task, item): item[0]
                for item in stocks.items()
            }

            for future in as_completed(futures):
                code = futures[future]
                try:
                    code, result = future.result()
                    if result:
                        result['info'] = stock_info.get(code, {})
                        results[code] = result
                    else:
                        failed_count += 1
                except Exception:
                    failed_count += 1

                completed += 1
                if on_progress:
                    on_progress(completed, total, code)

        return results, failed_count

    def _score_one(self, code: str, df: pd.DataFrame) -> Optional[Dict]:
        """단일 종목 스코어 계산"""
        if df is None or len(df) < 60:
            return None

        # 지표 계산 (캐시 사용)
        if self._cache:
            df_ind = self._cache.get_or_calculate(code, df)
        else:
            df_ind = calculate_base_indicators(df)

        result = {}

        for version, func in self._score_funcs.items():
            try:
                score_result = func(df_ind)
                if score_result:
                    result[version] = score_result
            except Exception as e:
                print(f"[{version}] 스코어 계산 오류 [{code}]: {e}")

        return result if result else None

    def clear_cache(self) -> None:
        """캐시 초기화"""
        if self._cache:
            self._cache.clear()

    @property
    def cache_stats(self) -> Optional[Dict]:
        """캐시 통계"""
        return self._cache.stats if self._cache else None


def score_stocks_batch(
    stocks: Dict[str, pd.DataFrame],
    versions: List[str] = None,
    parallel: bool = True,
    max_workers: int = 4,
    min_score: int = 0
) -> Dict[str, Dict]:
    """간편 배치 스코어 함수

    Args:
        stocks: {종목코드: DataFrame}
        versions: 스코어 버전 리스트
        parallel: 병렬 처리 여부
        max_workers: 워커 수
        min_score: 최소 점수 필터

    Returns:
        {종목코드: {v2: {...}, v4: {...}}}
    """
    scorer = BatchScorer(versions=versions or ['v2'])
    result = scorer.score_batch(
        stocks,
        parallel=parallel,
        max_workers=max_workers
    )

    # 최소 점수 필터링
    if min_score > 0:
        version = versions[0] if versions else 'v2'
        filtered = {}
        for code, scores in result.results.items():
            if version in scores and scores[version].get('score', 0) >= min_score:
                filtered[code] = scores
        return filtered

    return result.results


def get_top_scored_stocks(
    stocks: Dict[str, pd.DataFrame],
    version: str = 'v2',
    min_score: int = 70,
    limit: int = 20,
    stock_info: Optional[Dict[str, Dict]] = None
) -> List[Dict]:
    """상위 스코어 종목 조회

    Args:
        stocks: {종목코드: DataFrame}
        version: 스코어 버전
        min_score: 최소 점수
        limit: 최대 결과 수
        stock_info: {종목코드: {name, market}}

    Returns:
        상위 종목 리스트
    """
    scorer = BatchScorer(versions=[version])
    result = scorer.score_batch(
        stocks,
        parallel=True,
        max_workers=4,
        stock_info=stock_info
    )

    return result.get_top_stocks(version, min_score, limit)
