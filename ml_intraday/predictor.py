#!/usr/bin/env python3
"""
실시간 예측 모듈

학습된 ML 모델을 사용하여 실시간 분봉 데이터에서 매수 신호를 예측합니다.
auto_trader.py와 통합하여 사용합니다.

사용법:
    from ml_intraday.predictor import IntradayPredictor

    predictor = IntradayPredictor()
    result = predictor.predict(stock_code, minute_bars_df)
"""

import os
import sys
import pickle
import functools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml_intraday.config import (
    MODEL_DIR, INTEGRATION_CONFIG,
    LABEL_ENCODING, LABEL_DECODING
)
from ml_intraday.engineer_features import (
    calculate_features_for_bar,
    calculate_rsi,
    calculate_macd,
    calculate_vwap,
    calculate_bollinger_bands
)

# 출력 즉시 플러시
print = functools.partial(print, flush=True)


class IntradayPredictor:
    """장중 매수 타이밍 예측기"""

    def __init__(self, horizon: str = '10min', model_path: str = None):
        """
        Args:
            horizon: 예측 범위 ('5min', '10min', '30min')
            model_path: 모델 파일 경로 (None이면 기본 경로)
        """
        self.horizon = horizon
        self.model = None
        self.feature_names = None
        self.model_info = None

        # 예측 캐시 (중복 호출 방지)
        self._cache = {}
        self._cache_ttl = INTEGRATION_CONFIG['prediction_cache_ttl']

        # 모델 로드
        self._load_model(model_path)

    def _load_model(self, model_path: str = None):
        """모델 로드"""
        if model_path is None:
            model_path = MODEL_DIR / f"intraday_lgbm_{self.horizon}.pkl"
        else:
            model_path = Path(model_path)

        if not model_path.exists():
            print(f"[IntradayPredictor] 모델 없음: {model_path}")
            return

        try:
            with open(model_path, 'rb') as f:
                data = pickle.load(f)

            self.model = data['model']
            self.feature_names = data['feature_names']
            self.model_info = {
                'horizon': data.get('horizon', self.horizon),
                'trained_at': data.get('trained_at', ''),
                'metrics': data.get('metrics', {}),
            }

            print(f"[IntradayPredictor] 모델 로드: {model_path.name}")
            if self.model_info['metrics']:
                win_rate = self.model_info['metrics'].get('buy_win_rate', 0)
                print(f"  학습 시 BUY 승률: {win_rate:.1%}")

        except Exception as e:
            print(f"[IntradayPredictor] 모델 로드 실패: {e}")

    def is_ready(self) -> bool:
        """모델 준비 여부"""
        return self.model is not None and self.feature_names is not None

    def _get_cache_key(self, code: str, time_str: str) -> str:
        """캐시 키 생성"""
        return f"{code}_{time_str}"

    def _is_cache_valid(self, key: str) -> bool:
        """캐시 유효성 확인"""
        if key not in self._cache:
            return False

        cached_time = self._cache[key].get('cached_at')
        if cached_time is None:
            return False

        elapsed = (datetime.now() - cached_time).total_seconds()
        return elapsed < self._cache_ttl

    def prepare_features_from_bars(
        self,
        df: pd.DataFrame,
        v2_score: float = 0,
        v4_score: float = 0,
        v5_score: float = 0,
        v2_delta: float = 0,
        v4_delta: float = 0
    ) -> Optional[pd.DataFrame]:
        """
        분봉 데이터에서 피처 추출

        Args:
            df: 분봉 데이터 (시간순 정렬, 최근 20봉 이상)
            v2_score: V2 스코어 (record_intraday_scores.py에서)
            v4_score: V4 스코어
            v5_score: V5 스코어
            v2_delta: V2 변화량
            v4_delta: V4 변화량

        Returns:
            피처 DataFrame (1행)
        """
        if df is None or len(df) < 20:
            return None

        # 마지막 봉에 대한 피처 계산
        df = df.sort_values('time').reset_index(drop=True)
        idx = len(df) - 1

        features = calculate_features_for_bar(df, idx)
        if features is None:
            return None

        # 스코어 추가
        features['v2_score'] = v2_score
        features['v4_score'] = v4_score
        features['v5_score'] = v5_score
        features['v2_delta'] = v2_delta
        features['v4_delta'] = v4_delta

        # 필요한 피처만 선택
        feature_dict = {col: features.get(col, 0) for col in self.feature_names}

        return pd.DataFrame([feature_dict])

    def predict(
        self,
        code: str,
        minute_bars: pd.DataFrame,
        v2_score: float = 0,
        v4_score: float = 0,
        v5_score: float = 0,
        v2_delta: float = 0,
        v4_delta: float = 0,
        use_cache: bool = True
    ) -> Dict:
        """
        매수 신호 예측

        Args:
            code: 종목코드
            minute_bars: 분봉 데이터 (최근 20봉 이상)
            v2_score: V2 스코어
            v4_score: V4 스코어
            v5_score: V5 스코어
            v2_delta: V2 변화량
            v4_delta: V4 변화량
            use_cache: 캐시 사용 여부

        Returns:
            {
                'code': 종목코드,
                'buy_prob': BUY 확률,
                'sell_prob': SELL 확률,
                'hold_prob': HOLD 확률,
                'prediction': 예측 라벨 (BUY/HOLD/SELL),
                'confidence': 신뢰도,
                'signal': 신호 강도 (0~1),
                'timestamp': 예측 시간,
            }
        """
        result = {
            'code': code,
            'buy_prob': 0,
            'sell_prob': 0,
            'hold_prob': 1,
            'prediction': 'HOLD',
            'confidence': 0,
            'signal': 0,
            'timestamp': datetime.now().isoformat(),
            'error': None,
        }

        if not self.is_ready():
            result['error'] = 'model_not_ready'
            return result

        if minute_bars is None or minute_bars.empty:
            result['error'] = 'no_data'
            return result

        # 시간 추출
        time_str = str(minute_bars.iloc[-1].get('time', ''))[:4]

        # 캐시 확인
        cache_key = self._get_cache_key(code, time_str)
        if use_cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]['result']

        try:
            # 피처 준비
            X = self.prepare_features_from_bars(
                minute_bars,
                v2_score, v4_score, v5_score,
                v2_delta, v4_delta
            )

            if X is None:
                result['error'] = 'feature_error'
                return result

            # NaN/Inf 처리
            X = X.fillna(0).replace([np.inf, -np.inf], 0)

            # 예측
            proba = self.model.predict_proba(X)[0]
            pred = self.model.predict(X)[0]

            result['buy_prob'] = float(proba[LABEL_ENCODING['BUY']])
            result['hold_prob'] = float(proba[LABEL_ENCODING['HOLD']])
            result['sell_prob'] = float(proba[LABEL_ENCODING['SELL']])
            result['prediction'] = LABEL_DECODING[int(pred)]
            result['confidence'] = float(max(proba))

            # 신호 강도 (BUY 확률 기반, SELL 확률 고려)
            result['signal'] = max(0, result['buy_prob'] - result['sell_prob'] * 0.5)

            # 캐시 저장
            if use_cache:
                self._cache[cache_key] = {
                    'result': result,
                    'cached_at': datetime.now()
                }

        except Exception as e:
            result['error'] = str(e)

        return result

    def should_buy(
        self,
        prediction: Dict,
        v2_score: float = 0,
        v4_score: float = 0
    ) -> Tuple[bool, str]:
        """
        매수 여부 판단 (하이브리드 전략)

        Args:
            prediction: predict() 결과
            v2_score: V2 스코어
            v4_score: V4 스코어

        Returns:
            (매수 여부, 사유)
        """
        buy_prob = prediction.get('buy_prob', 0)

        # 에러 체크
        if prediction.get('error'):
            return False, f"error:{prediction['error']}"

        # Strong BUY: ML 확률 + 스코어 모두 충족
        strong_buy = INTEGRATION_CONFIG['strong_buy']
        if (buy_prob >= strong_buy['ml_prob'] and
            v2_score >= strong_buy['v2_min'] and
            v4_score >= strong_buy['v4_min']):
            return True, 'strong_buy'

        # ML Priority BUY: ML 확률이 높으면 스코어 완화
        ml_priority = INTEGRATION_CONFIG['ml_priority_buy']
        if (buy_prob >= ml_priority['ml_prob'] and
            v2_score >= ml_priority['v2_min']):
            return True, 'ml_priority_buy'

        # ML Warning Skip: 스코어는 좋지만 ML이 경고
        ml_warning = INTEGRATION_CONFIG['ml_warning_skip']
        if (buy_prob <= ml_warning['ml_prob_max'] and
            v2_score >= ml_warning['v2_min']):
            return False, 'ml_warning'

        return False, 'no_signal'

    def batch_predict(
        self,
        stocks_data: Dict[str, Dict]
    ) -> List[Dict]:
        """
        여러 종목 일괄 예측

        Args:
            stocks_data: {code: {'minute_bars': df, 'v2_score': float, ...}}

        Returns:
            예측 결과 리스트 (buy_prob 내림차순 정렬)
        """
        results = []

        for code, data in stocks_data.items():
            prediction = self.predict(
                code=code,
                minute_bars=data.get('minute_bars'),
                v2_score=data.get('v2_score', 0),
                v4_score=data.get('v4_score', 0),
                v5_score=data.get('v5_score', 0),
                v2_delta=data.get('v2_delta', 0),
                v4_delta=data.get('v4_delta', 0),
            )

            # 매수 판단 추가
            should_buy, reason = self.should_buy(
                prediction,
                data.get('v2_score', 0),
                data.get('v4_score', 0)
            )
            prediction['should_buy'] = should_buy
            prediction['buy_reason'] = reason

            results.append(prediction)

        # BUY 확률 내림차순 정렬
        results.sort(key=lambda x: x['buy_prob'], reverse=True)

        return results

    def get_top_candidates(
        self,
        stocks_data: Dict[str, Dict],
        top_n: int = 10,
        min_prob: float = 0.5
    ) -> List[Dict]:
        """
        상위 매수 후보 반환

        Args:
            stocks_data: 종목별 데이터
            top_n: 반환할 상위 N개
            min_prob: 최소 BUY 확률

        Returns:
            상위 N개 예측 결과
        """
        all_predictions = self.batch_predict(stocks_data)

        # 필터링
        filtered = [
            p for p in all_predictions
            if p['buy_prob'] >= min_prob and not p.get('error')
        ]

        return filtered[:top_n]

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()


# 싱글톤 인스턴스
_predictor_instance: Optional[IntradayPredictor] = None


def get_predictor(horizon: str = '10min') -> IntradayPredictor:
    """싱글톤 예측기 인스턴스 반환"""
    global _predictor_instance

    if _predictor_instance is None or _predictor_instance.horizon != horizon:
        _predictor_instance = IntradayPredictor(horizon)

    return _predictor_instance


def predict_stock(
    code: str,
    minute_bars: pd.DataFrame,
    v2_score: float = 0,
    v4_score: float = 0,
    v5_score: float = 0
) -> Dict:
    """
    단일 종목 예측 (편의 함수)

    Args:
        code: 종목코드
        minute_bars: 분봉 데이터
        v2_score: V2 스코어
        v4_score: V4 스코어
        v5_score: V5 스코어

    Returns:
        예측 결과
    """
    predictor = get_predictor()
    return predictor.predict(code, minute_bars, v2_score, v4_score, v5_score)


# CLI 테스트
def main():
    import argparse

    parser = argparse.ArgumentParser(description="실시간 예측 테스트")
    parser.add_argument("--code", type=str, default="005930", help="종목코드")
    parser.add_argument("--horizon", type=str, default="10min", help="예측 범위")

    args = parser.parse_args()

    print("=" * 60)
    print("  IntradayPredictor 테스트")
    print("=" * 60)

    predictor = IntradayPredictor(args.horizon)

    if not predictor.is_ready():
        print("\n[에러] 모델이 준비되지 않았습니다.")
        print("       먼저 train_model.py 실행 필요")
        return

    print(f"\n모델 정보:")
    print(f"  Horizon: {predictor.model_info['horizon']}")
    print(f"  학습 시점: {predictor.model_info['trained_at']}")
    print(f"  피처 수: {len(predictor.feature_names)}")

    # 테스트 데이터 생성 (더미)
    print(f"\n테스트 예측 (더미 데이터)...")

    # 더미 분봉 데이터 (30봉)
    np.random.seed(42)
    base_price = 70000
    dummy_bars = pd.DataFrame({
        'time': [f"{9+i//12:02d}{(i%12)*5:02d}00" for i in range(30)],
        'open': [base_price + np.random.randn() * 500 for _ in range(30)],
        'high': [base_price + 500 + np.random.randn() * 300 for _ in range(30)],
        'low': [base_price - 500 + np.random.randn() * 300 for _ in range(30)],
        'close': [base_price + np.random.randn() * 500 for _ in range(30)],
        'volume': [np.random.randint(10000, 100000) for _ in range(30)],
    })

    result = predictor.predict(
        code=args.code,
        minute_bars=dummy_bars,
        v2_score=75,
        v4_score=55,
        v5_score=40
    )

    print(f"\n예측 결과:")
    print(f"  종목: {result['code']}")
    print(f"  BUY 확률: {result['buy_prob']:.1%}")
    print(f"  HOLD 확률: {result['hold_prob']:.1%}")
    print(f"  SELL 확률: {result['sell_prob']:.1%}")
    print(f"  예측: {result['prediction']}")
    print(f"  신뢰도: {result['confidence']:.1%}")
    print(f"  신호 강도: {result['signal']:.2f}")

    # 매수 판단
    should_buy, reason = predictor.should_buy(result, v2_score=75, v4_score=55)
    print(f"\n매수 판단: {should_buy} ({reason})")


if __name__ == "__main__":
    main()
