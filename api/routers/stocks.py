"""
종목 API 라우터
- 종목 검색, 상세 정보, 분석
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Tuple, Any
from functools import lru_cache
import sys
import os
import time
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.schemas.stock import StockSearch, StockDetail, StockAnalysis, FundamentalAnalysis
from api.dependencies import get_current_user

# 출력 디렉토리 경로
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'output')

# 주식 데이터 라이브러리 지연 임포트
_stock_utils = None


def get_stock_libs():
    """주식 데이터 라이브러리 로드"""
    global _stock_utils
    if _stock_utils is None:
        try:
            import FinanceDataReader as fdr

            def get_all_krx():
                return fdr.StockListing("KRX")

            def get_ohlcv(code, days=120):
                from datetime import datetime, timedelta
                start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                df = fdr.DataReader(code, start)
                if df is not None and not df.empty:
                    # 컬럼명 한글로 변환 (기존 코드 호환)
                    df = df.rename(columns={
                        'Open': '시가',
                        'High': '고가',
                        'Low': '저가',
                        'Close': '종가',
                        'Volume': '거래량'
                    })
                return df

            _stock_utils = {
                'fdr': fdr,
                'get_all_krx': get_all_krx,
                'get_ohlcv': get_ohlcv
            }
        except Exception as e:
            print(f"주식 라이브러리 로드 실패: {e}")
            _stock_utils = {}
    return _stock_utils


router = APIRouter()

# 종목 상세 캐시 (5분 TTL)
_stock_detail_cache: Dict[str, Tuple[Any, float]] = {}
_CACHE_TTL = 300  # 5분

# AI 분석 캐시 (10분 TTL)
_analysis_cache: Dict[str, Tuple[Any, float]] = {}
_ANALYSIS_CACHE_TTL = 600  # 10분

# KRX 종목 리스트 전역 캐시 (24시간 TTL) - 성능 최적화
_krx_listing_cache: Tuple[Any, float] = (None, 0)
_KRX_CACHE_TTL = 86400  # 24시간


def get_krx_listing():
    """KRX 종목 리스트 캐시 조회 (1시간 캐싱)"""
    global _krx_listing_cache
    data, timestamp = _krx_listing_cache
    if data is not None and time.time() - timestamp < _KRX_CACHE_TTL:
        return data

    try:
        libs = get_stock_libs()
        if libs:
            krx = libs['fdr'].StockListing("KRX")
            _krx_listing_cache = (krx, time.time())
            return krx
    except Exception as e:
        print(f"KRX 리스트 조회 실패: {e}")
    return None


def get_cached_stock_detail(code: str) -> Optional[Any]:
    """캐시된 종목 상세 조회"""
    if code in _stock_detail_cache:
        data, timestamp = _stock_detail_cache[code]
        if time.time() - timestamp < _CACHE_TTL:
            return data
        # 만료된 캐시 삭제
        del _stock_detail_cache[code]
    return None


def set_stock_detail_cache(code: str, data: Any):
    """종목 상세 캐시 저장"""
    _stock_detail_cache[code] = (data, time.time())
    # 캐시 크기 제한 (500개 초과 시 오래된 것 정리)
    if len(_stock_detail_cache) > 500:
        oldest = min(_stock_detail_cache.items(), key=lambda x: x[1][1])
        del _stock_detail_cache[oldest[0]]


def get_cached_analysis(code: str) -> Optional[Any]:
    """캐시된 AI 분석 조회"""
    if code in _analysis_cache:
        data, timestamp = _analysis_cache[code]
        if time.time() - timestamp < _ANALYSIS_CACHE_TTL:
            return data
        del _analysis_cache[code]
    return None


def set_analysis_cache(code: str, data: Any):
    """AI 분석 캐시 저장"""
    _analysis_cache[code] = (data, time.time())
    if len(_analysis_cache) > 200:
        oldest = min(_analysis_cache.items(), key=lambda x: x[1][1])
        del _analysis_cache[oldest[0]]


# 점수 평활화 캐시 (종목코드 → 이전 점수)
_score_history: Dict[str, float] = {}


def smooth_score(code: str, new_score: float, alpha: float = 0.4) -> float:
    """
    지수 이동 평균(EMA) 방식으로 점수 평활화
    점수 급변을 방지하여 안정적인 신호 제공

    alpha: 새 점수 반영 비율 (0.4 = 새 점수 40%, 이전 점수 60%)
    """
    prev_score = _score_history.get(code, new_score)
    smoothed = prev_score * (1 - alpha) + new_score * alpha
    _score_history[code] = smoothed
    return round(smoothed, 1)


# 전체 종목 목록 캐시 (1시간 TTL)
_all_stocks_cache: Optional[Tuple[List[dict], float]] = None
_ALL_STOCKS_CACHE_TTL = 3600  # 1시간


def get_all_stocks_cached() -> List[dict]:
    """전체 종목 목록 캐싱 조회"""
    global _all_stocks_cache

    if _all_stocks_cache is not None:
        data, timestamp = _all_stocks_cache
        if time.time() - timestamp < _ALL_STOCKS_CACHE_TTL:
            return data

    # 캐시 갱신
    libs = get_stock_libs()
    if not libs:
        return []

    try:
        krx = libs['get_all_krx']()
        if krx is None or krx.empty:
            return []

        stocks = []
        for _, r in krx.iterrows():
            stocks.append({
                'code': r['Code'],
                'name': r['Name'],
                'market': r.get('Market', 'KOSPI') if 'Market' in krx.columns else None
            })

        _all_stocks_cache = (stocks, time.time())
        return stocks
    except Exception as e:
        print(f"종목 목록 로드 실패: {e}")
        return []


@router.get("/list")
async def get_stock_list():
    """
    전체 종목 목록 (자동완성용)
    - 클라이언트에서 캐싱하여 즉시 검색에 사용
    - code, name, market만 반환 (가벼운 응답)
    """
    stocks = get_all_stocks_cached()
    return {"stocks": stocks, "count": len(stocks)}


def generate_natural_comment(score: float, signals: list, indicators: dict, prob_conf: dict) -> str:
    """
    자연어 형태의 AI 분석 코멘트 생성
    """
    probability = prob_conf.get('probability', 50)
    confidence = prob_conf.get('confidence', 50)
    bullish_count = prob_conf.get('bullish_signals', 0)
    bearish_count = prob_conf.get('bearish_signals', 0)

    # 1. 전체 방향성 판단
    if score >= 70:
        direction = "강세"
        direction_detail = "기술적 지표들이 강한 상승 신호를 보이고 있습니다."
    elif score >= 55:
        direction = "약세 상승"
        direction_detail = "전반적으로 긍정적인 흐름이나 신중한 접근이 필요합니다."
    elif score >= 45:
        direction = "중립"
        direction_detail = "현재 뚜렷한 방향성이 없어 관망이 권장됩니다."
    elif score >= 30:
        direction = "약세"
        direction_detail = "기술적 지표가 약세를 보이고 있어 주의가 필요합니다."
    else:
        direction = "강한 약세"
        direction_detail = "하락 신호가 우세하여 매수를 자제하는 것이 좋습니다."

    # 2. 핵심 신호 분석
    signal_details = []

    # 추세 관련
    if 'MA_ALIGNED' in signals:
        signal_details.append("이동평균선이 정배열 상태")
    if 'GOLDEN_CROSS_5_20' in signals or 'GOLDEN_CROSS_20_60' in signals:
        signal_details.append("골든크로스가 발생")
    if 'DEAD_CROSS_5_20' in signals:
        signal_details.append("데드크로스가 발생하여 하락 추세 전환 우려")

    # 모멘텀 관련
    if 'RSI_OVERSOLD' in signals:
        signal_details.append("RSI가 과매도 구간에서 반등 중")
    elif 'RSI_OVERBOUGHT' in signals:
        signal_details.append("RSI가 과매수 구간으로 조정 가능성")

    if 'MACD_GOLDEN_CROSS' in signals:
        signal_details.append("MACD 골든크로스로 상승 모멘텀 확인")
    elif 'MACD_HIST_POSITIVE' in signals:
        signal_details.append("MACD 히스토그램이 양전환")

    # 거래량 관련
    if 'VOLUME_SURGE' in signals:
        signal_details.append("거래량이 급증하며 관심도 상승")
    elif 'VOLUME_HIGH' in signals:
        signal_details.append("평균 이상의 거래량 동반")

    # 3. 신뢰도 기반 부가 설명
    if confidence >= 80:
        confidence_text = "신호의 일관성이 높아 신뢰도가 높습니다."
    elif confidence >= 60:
        confidence_text = "대체로 일관된 신호를 보이고 있습니다."
    else:
        confidence_text = "신호가 혼재되어 있어 추가 확인이 필요합니다."

    # 4. 최종 코멘트 조합
    comment_parts = [direction_detail]

    if signal_details:
        if len(signal_details) == 1:
            comment_parts.append(f"{signal_details[0]}이며, {confidence_text}")
        else:
            combined = ", ".join(signal_details[:-1]) + f", {signal_details[-1]}"
            comment_parts.append(f"{combined}입니다. {confidence_text}")
    else:
        comment_parts.append(confidence_text)

    # 5. 투자 참고 사항
    if score >= 60 and bullish_count >= 3:
        comment_parts.append("단기적으로 상승 가능성이 있으나, 분할 매수를 권장합니다.")
    elif score <= 40 and bearish_count >= 2:
        comment_parts.append("하락 리스크가 있으므로 손절 라인 설정을 권장합니다.")
    else:
        comment_parts.append("시장 상황을 주시하며 대응하시기 바랍니다.")

    return " ".join(comment_parts)


def get_top100_analysis(code: str) -> Optional[Dict]:
    """TOP100 JSON에서 분석 데이터 조회"""
    import json
    from pathlib import Path

    try:
        json_files = list(Path("/home/kimhc/Stock/output").glob("top100_*.json"))
        if json_files:
            latest = max(json_files, key=lambda x: x.stat().st_mtime)
            with open(latest) as f:
                data = json.load(f)
                # 'stocks' 또는 'items' 키 모두 지원
                stocks = data.get('stocks', data.get('items', []))
                for item in stocks:
                    if item.get('code') == code:
                        score = item.get('score', 50)
                        signals = item.get('signals', [])

                        # 점수 기반 의견 생성
                        if score >= 70:
                            opinion = '매수'
                        elif score >= 50:
                            opinion = '관망'
                        elif score >= 30:
                            opinion = '주의'
                        else:
                            opinion = '주의'

                        # 시그널 기반 코멘트 생성
                        signal_desc = {
                            'MA_ALIGNED': '✅ 이평선 정배열 (강한 상승 추세)',
                            'GOLDEN_CROSS_5_20': '✅ 단기 골든크로스 발생',
                            'GOLDEN_CROSS': '✅ 골든크로스 발생',
                            'DEATH_CROSS': '⚠️ 데드크로스 발생',
                            'MACD_GOLDEN_CROSS': '✅ MACD 골든크로스',
                            'MACD_HIST_POSITIVE': '✅ MACD 히스토그램 양전환',
                            'MACD_HIST_RISING': '📈 MACD 히스토그램 상승 중',
                            'VOLUME_SURGE': '🔥 거래량 급증',
                            'RSI_OVERSOLD': '✅ RSI 과매도 반등',
                            'RSI_RECOVERING': '📈 RSI 회복 중',
                            'RSI_OVERBOUGHT': '⚠️ RSI 과매수 주의',
                            'BB_LOWER_BOUNCE': '✅ 볼린저밴드 하단 반등',
                            'BB_LOWER_TOUCH': '✅ 볼린저밴드 하단 터치',
                            'BB_UPPER_BREAK': '⚠️ 볼린저밴드 상단 돌파',
                            'STOCH_GOLDEN_OVERSOLD': '✅ 스토캐스틱 과매도 골든크로스',
                            'STOCH_GOLDEN_CROSS': '✅ 스토캐스틱 골든크로스',
                            'STOCH_OVERSOLD': '✅ 스토캐스틱 과매도 구간',
                            'ADX_STRONG_UPTREND': '✅ ADX 강한 상승 추세',
                            'ADX_UPTREND': '📈 ADX 상승 추세',
                            'ADX_TREND_START': '📈 ADX 추세 시작',
                            'CCI_OVERSOLD_RECOVERY': '✅ CCI 과매도 회복',
                            'CCI_OVERBOUGHT': '⚠️ CCI 과매수 주의',
                            'WILLIAMS_OVERSOLD': '✅ 윌리엄스 %R 과매도',
                            'WILLIAMS_OVERBOUGHT': '⚠️ 윌리엄스 %R 과매수',
                            'WILLR_OVERBOUGHT': '⚠️ 윌리엄스 %R 과매수',
                            'WILLR_OVERSOLD': '✅ 윌리엄스 %R 과매도',
                            'OBV_RISING': '📈 OBV 상승 (매집 신호)',
                            'OBV_ABOVE_MA': '📈 OBV 이평선 돌파',
                            'MFI_OVERSOLD': '✅ MFI 과매도 (자금 유입 기대)',
                            'MFI_OVERBOUGHT': '⚠️ MFI 과매수 주의',
                            'SUPERTREND_BUY': '✅ 슈퍼트렌드 매수 신호',
                            'SUPERTREND_UPTREND': '📈 슈퍼트렌드 상승 추세',
                            'PSAR_BUY_SIGNAL': '✅ PSAR 매수 신호',
                            'ROC_POSITIVE_CROSS': '✅ ROC 양전환',
                            'ROC_STRONG_MOMENTUM': '📈 ROC 강한 모멘텀',
                            'ICHIMOKU_BULLISH': '✅ 일목균형 상승',
                            'CMF_STRONG_INFLOW': '✅ CMF 강한 자금 유입',
                            'CMF_POSITIVE': '📈 CMF 순매수',
                            'HAMMER': '✅ 망치형 캔들 (반등 신호)',
                            'BULLISH_ENGULFING': '✅ 상승 장악형 캔들',
                            'MORNING_STAR': '✅ 샛별형 패턴',
                            'BEARISH_ENGULFING': '⚠️ 하락 장악형 캔들',
                            'EVENING_STAR': '⚠️ 저녁별형 패턴',
                        }
                        comments = [signal_desc.get(s, s) for s in signals[:5]]
                        comment = '\n'.join(comments) if comments else f"AI 종합 점수: {score}점"

                        return {
                            'name': item.get('name', code),
                            'score': score,
                            'opinion': opinion,
                            'comment': comment,
                            'signals': signals
                        }
    except Exception as e:
        print(f"TOP100 분석 조회 실패: {e}")
    return None


@router.get("/search", response_model=List[StockSearch])
async def search_stocks(
    q: str = Query(..., min_length=1, description="검색어 (종목코드 또는 종목명)"),
    limit: int = Query(20, ge=1, le=100, description="최대 결과 수")
):
    """종목 검색 (캐시된 KRX 리스트 사용, 대소문자 무관)"""
    # 캐시된 KRX 리스트 사용 (24시간 캐싱으로 속도 향상)
    krx = get_krx_listing()
    if krx is None or krx.empty:
        return []

    try:
        results = []
        q_upper = q.upper()  # 종목코드는 대문자

        # 종목코드 정확 매칭 (대소문자 무관)
        code_match = krx[krx['Code'] == q_upper]
        if not code_match.empty:
            r = code_match.iloc[0]
            market = r.get('Market', 'KOSPI') if 'Market' in krx.columns else None
            return [StockSearch(code=r['Code'], name=r['Name'], market=market)]

        # 종목명 검색 (대소문자 무관)
        mask = krx['Name'].str.contains(q, case=False, na=False)
        for _, r in krx[mask].head(limit).iterrows():
            market = r.get('Market', None) if 'Market' in krx.columns else None
            results.append(StockSearch(code=r['Code'], name=r['Name'], market=market))

        return results

    except Exception as e:
        print(f"[Stock Search Error] {e}")
        raise HTTPException(status_code=500, detail="종목 검색 중 오류가 발생했습니다")


@lru_cache(maxsize=5000)
def get_stock_name(code: str) -> str:
    """TOP100 데이터 또는 FDR에서 종목명 조회 (LRU 캐시 적용)"""
    import json
    from pathlib import Path

    # 1. TOP100 JSON에서 조회
    try:
        json_files = list(Path("/home/kimhc/Stock/output").glob("top100_*.json"))
        if json_files:
            latest = max(json_files, key=lambda x: x.stat().st_mtime)
            with open(latest) as f:
                data = json.load(f)
                for item in data.get('items', []):
                    if item.get('code') == code:
                        return item.get('name', code)
    except:
        pass

    # 2. 캐시된 KRX 리스트에서 조회
    try:
        krx = get_krx_listing()
        if krx is not None:
            match = krx[krx['Code'] == code]
            if not match.empty:
                return match.iloc[0]['Name']
    except:
        pass

    return code


@router.get("/{code}", response_model=StockDetail)
async def get_stock_detail(code: str):
    """종목 상세 정보 - DB캐시 우선, KIS API 보조, FDR 폴백 (5분 캐싱)"""
    # 메모리 캐시 확인 - 있으면 실시간 가격만 업데이트해서 반환
    cached = get_cached_stock_detail(code)
    if cached:
        # 실시간 가격/등락률로 업데이트 (HTTP 호출 대신 직접 함수 사용)
        try:
            from api.routers.realtime import get_cached_realtime, set_realtime_cache, get_kis
            rt = get_cached_realtime(code)
            if not rt:
                kis = get_kis()
                if kis:
                    rt = kis.get_current_price(code)
                    if rt:
                        set_realtime_cache(code, rt)
            if rt:
                return StockDetail(
                    code=cached.code,
                    name=cached.name,
                    market=cached.market,
                    current_price=rt.get('current_price', cached.current_price),
                    change=rt.get('change', cached.change),
                    change_rate=rt.get('change_rate', cached.change_rate),
                    volume=rt.get('volume', cached.volume),
                    market_cap=cached.market_cap,
                    ma5=cached.ma5,
                    ma20=cached.ma20,
                    ma60=cached.ma60,
                    rsi=cached.rsi,
                    macd=cached.macd,
                    macd_signal=cached.macd_signal,
                    bb_mid=cached.bb_mid,
                    bb_upper=cached.bb_upper,
                    bb_lower=cached.bb_lower
                )
        except Exception as e:
            print(f"[stocks/{code}] 실시간 조회 실패: {e}")
        return cached

    stock_name = get_stock_name(code)

    # 1. DB 캐시에서 가격 조회 (네이버 금융 API로 5분마다 업데이트됨)
    kis_data = None
    try:
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cached_price = db.get_cached_price(code)
        if cached_price and cached_price.get('current_price'):
            kis_data = {
                'stock_code': code,
                'stock_name': cached_price.get('stock_name') or stock_name,
                'current_price': cached_price.get('current_price', 0),
                'change': cached_price.get('change', 0),
                'change_rate': cached_price.get('change_rate', 0),
                'volume': cached_price.get('volume', 0),
                'market_cap': 0,  # 캐시에 없음
            }
    except Exception as cache_err:
        print(f"DB 캐시 조회 오류: {cache_err}")

    # 2. 캐시 미스 시 KIS API로 실시간 시세 조회 (실전투자 URL 사용)
    if not kis_data:
        try:
            from api.services.kis_client import get_kis_client_for_prices
            kis = get_kis_client_for_prices()
            kis_data = kis.get_current_price(code)
        except Exception as kis_err:
            print(f"KIS API 오류: {kis_err}")

    # 3. 가격 데이터가 있으면 (DB캐시 또는 KIS API) 상세 정보 구성
    if kis_data:
        # 시가총액: KIS는 억 단위로 반환, 원 단위로 변환
        market_cap = kis_data.get('market_cap', 0)
        if market_cap:
            market_cap = market_cap * 100000000  # 억 -> 원

        # KIS에서 종목명이 있으면 사용, 없으면 로컬 데이터 사용
        name = kis_data.get('stock_name') or stock_name

        # 이동평균/RSI/MACD/피보나치는 FDR에서 계산
        ma5, ma20, ma60, rsi, macd, macd_signal = None, None, None, None, None, None
        bb_mid, bb_upper, bb_lower = None, None, None
        try:
            libs = get_stock_libs()
            if libs:
                get_ohlcv = libs['get_ohlcv']
                ohlcv = get_ohlcv(code, 90)  # 90일 (60거래일 확보용)
                if ohlcv is not None and not ohlcv.empty:
                    close = ohlcv['종가']
                    ma5 = round(close.tail(5).mean(), 0) if len(ohlcv) >= 5 else None
                    ma20 = round(close.tail(20).mean(), 0) if len(ohlcv) >= 20 else None
                    ma60 = round(close.tail(60).mean(), 0) if len(ohlcv) >= 60 else None
                    # RSI 계산
                    if len(ohlcv) >= 14:
                        delta = close.diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        rsi_series = 100 - (100 / (1 + rs))
                        rsi = round(rsi_series.iloc[-1], 2)
                    # MACD 계산
                    if len(ohlcv) >= 26:
                        ema12 = close.ewm(span=12, adjust=False).mean()
                        ema26 = close.ewm(span=26, adjust=False).mean()
                        macd_line = ema12 - ema26
                        signal_line = macd_line.ewm(span=9, adjust=False).mean()
                        macd = round(macd_line.iloc[-1], 2)
                        macd_signal = round(signal_line.iloc[-1], 2)
                    # 피보나치 61.8% 되돌림 (추천 매수가용)
                    if len(ohlcv) >= 60:
                        high60 = ohlcv['고가'].tail(60).max()
                        low60 = ohlcv['저가'].tail(60).min()
                        bb_mid = round(high60 - (high60 - low60) * 0.618, 0)  # 피보나치 61.8%
                        bb_upper = round(high60, 0)  # 60일 고점
                        bb_lower = round(low60, 0)   # 60일 저점
        except Exception as ma_err:
            print(f"이동평균 계산 오류: {ma_err}")

        # 시장 구분 조회 (KOSPI/KOSDAQ) - 캐시 사용
        market_type = None
        try:
            krx = get_krx_listing()
            if krx is not None:
                stock_info = krx[krx['Code'] == code]
                if not stock_info.empty and 'Market' in stock_info.columns:
                    market_type = stock_info.iloc[0]['Market']
        except Exception:
            pass

        # 실시간 가격/등락률/시가총액 조회 (DB캐시가 오래된 경우 대비)
        realtime_price = kis_data.get('current_price', 0)
        realtime_change = kis_data.get('change', 0)
        realtime_rate = kis_data.get('change_rate', 0)
        realtime_market_cap = market_cap  # 기본값
        try:
            # HTTP 호출 대신 직접 realtime 캐시/KIS API 사용 (deadlock 방지)
            from api.routers.realtime import get_cached_realtime, set_realtime_cache, get_kis
            rt_cached = get_cached_realtime(code)
            if rt_cached:
                realtime_price = rt_cached.get('current_price', realtime_price)
                realtime_change = rt_cached.get('change', realtime_change)
                realtime_rate = rt_cached.get('change_rate', realtime_rate)
                # 시가총액: 억원 단위로 반환되므로 원 단위로 변환
                if rt_cached.get('market_cap'):
                    realtime_market_cap = rt_cached.get('market_cap') * 100000000
            else:
                # 캐시 없으면 KIS API 직접 호출
                kis = get_kis()
                if kis:
                    rt_data = kis.get_current_price(code)
                    if rt_data:
                        realtime_price = rt_data.get('current_price', realtime_price)
                        realtime_change = rt_data.get('change', realtime_change)
                        realtime_rate = rt_data.get('change_rate', realtime_rate)
                        if rt_data.get('market_cap'):
                            realtime_market_cap = rt_data.get('market_cap') * 100000000
                        set_realtime_cache(code, rt_data)
        except Exception as e:
            print(f"[stocks/{code}] 실시간 조회 실패: {e}")
            pass  # 실패 시 기존 데이터 사용

        # 시가총액 업데이트
        if realtime_market_cap:
            market_cap = realtime_market_cap

        result = StockDetail(
            code=code,
            name=name,
            market=market_type,
            current_price=realtime_price,
            change=realtime_change,
            change_rate=realtime_rate,
            volume=kis_data.get('volume', 0),
            market_cap=market_cap,
            ma5=ma5,
            ma20=ma20,
            ma60=ma60,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            bb_mid=bb_mid,
            bb_upper=bb_upper,
            bb_lower=bb_lower
        )
        set_stock_detail_cache(code, result)
        return result

    # 4. DB캐시와 KIS 모두 실패 시 FDR로 폴백
    libs = get_stock_libs()
    if not libs:
        raise HTTPException(status_code=503, detail="주식 데이터 서비스 이용 불가")

    try:
        fdr = libs['fdr']
        get_ohlcv = libs['get_ohlcv']

        # OHLCV 데이터 직접 조회 (60일로 축소)
        ohlcv = get_ohlcv(code, 90)
        if ohlcv is None or ohlcv.empty:
            raise HTTPException(status_code=404, detail="가격 데이터를 가져올 수 없습니다")

        latest = ohlcv.iloc[-1]
        prev = ohlcv.iloc[-2] if len(ohlcv) > 1 else latest

        current_price = int(latest['종가'])
        change = int(current_price - prev['종가'])
        change_rate = round((change / prev['종가']) * 100, 2) if prev['종가'] > 0 else 0

        # 이동평균선
        ma5 = round(ohlcv['종가'].tail(5).mean(), 0) if len(ohlcv) >= 5 else None
        ma20 = round(ohlcv['종가'].tail(20).mean(), 0) if len(ohlcv) >= 20 else None
        ma60 = round(ohlcv['종가'].tail(60).mean(), 0) if len(ohlcv) >= 60 else None

        # RSI 계산
        rsi = None
        close = ohlcv['종가']
        if len(ohlcv) >= 14:
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi = round(rsi_series.iloc[-1], 2)

        # MACD 계산
        macd, macd_signal = None, None
        if len(ohlcv) >= 26:
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd = round(macd_line.iloc[-1], 2)
            macd_signal = round(signal_line.iloc[-1], 2)

        # 피보나치 61.8% 되돌림 (추천 매수가용)
        bb_mid, bb_upper, bb_lower = None, None, None
        if len(ohlcv) >= 60:
            high60 = ohlcv['고가'].tail(60).max()
            low60 = ohlcv['저가'].tail(60).min()
            bb_mid = round(high60 - (high60 - low60) * 0.618, 0)  # 피보나치 61.8%
            bb_upper = round(high60, 0)  # 60일 고점
            bb_lower = round(low60, 0)   # 60일 저점

        # 시가총액 조회 (캐시된 KRX 리스트 사용)
        market_cap = None
        market_type = None
        try:
            krx = get_krx_listing()
            if krx is not None:
                stock_info = krx[krx['Code'] == code]
                if not stock_info.empty:
                    row = stock_info.iloc[0]
                    # 시가총액 (Marcap 컬럼)
                    if 'Marcap' in row.index and row['Marcap']:
                        market_cap = int(row['Marcap'])
                    # 시장 구분
                    if 'Market' in row.index:
                        market_type = row['Market']
        except Exception as mc_err:
            print(f"시가총액 조회 실패: {mc_err}")

        # 실시간 가격/등락률 조회 (FDR 데이터가 오래된 경우 대비)
        realtime_price = current_price
        realtime_change = change
        realtime_rate = change_rate
        try:
            import httpx
            resp = httpx.get(f"http://localhost:8000/api/realtime/price/{code}", timeout=5.0)
            if resp.status_code == 200:
                rt_data = resp.json()
                realtime_price = rt_data.get('current_price', realtime_price)
                realtime_change = rt_data.get('change', realtime_change)
                realtime_rate = rt_data.get('change_rate', realtime_rate)
        except Exception:
            pass  # 실패 시 FDR 데이터 사용

        result = StockDetail(
            code=code,
            name=stock_name,  # 이미 위에서 조회함
            market=market_type,
            current_price=realtime_price,
            change=realtime_change,
            change_rate=realtime_rate,
            volume=int(latest['거래량']),
            market_cap=market_cap,
            ma5=ma5,
            ma20=ma20,
            ma60=ma60,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            bb_mid=bb_mid,
            bb_upper=bb_upper,
            bb_lower=bb_lower
        )
        set_stock_detail_cache(code, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Stock Detail Error] {e}")
        raise HTTPException(status_code=500, detail="종목 정보 조회 중 오류가 발생했습니다")


def get_intraday_score(code: str, score_version: str = 'v5'):
    """장중 스코어 CSV에서 특정 종목 점수 조회"""
    import glob
    import pandas as pd

    code = code.zfill(6)
    intraday_dir = os.path.join(OUTPUT_DIR, 'intraday_scores')
    csv_files = sorted(glob.glob(os.path.join(intraday_dir, "*.csv")))

    if not csv_files:
        return None

    latest_csv = csv_files[-1]

    try:
        df = pd.read_csv(latest_csv)
        df['code'] = df['code'].astype(str).str.zfill(6)
    except Exception:
        return None

    # 스코어 컬럼 확인
    score_col = score_version
    if score_col not in df.columns:
        score_col = 'v5'
        if score_col not in df.columns:
            return None

    # 종목 검색
    stock_row = df[df['code'] == code]
    if stock_row.empty:
        return {"in_target": False}  # 분석 대상 아님

    row = stock_row.iloc[0]
    signals_str = str(row.get('signals', ''))
    signals = [s.strip() for s in signals_str.split(',') if s.strip()]

    return {
        "in_target": True,
        "score": int(row.get(score_col, 0)),
        "name": row.get('name', ''),
        "signals": signals,
        "change_pct": round(float(row.get('change_pct', 0)), 2)
    }


@router.get("/{code}/analysis", response_model=StockAnalysis)
async def analyze_stock(
    code: str,
    score_version: str = Query("v5", description="스코어 버전 (v1, v2, v3.5, v4, v5, v6, v7, v8)")
):
    """종목 AI 분석 (장중 스코어 우선, 없으면 TOP100/실시간 계산)"""
    # 유효한 스코어 버전 확인
    valid_versions = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']
    if score_version not in valid_versions:
        score_version = 'v5'

    # 1. 장중 스코어 CSV 확인 (최우선)
    intraday = get_intraday_score(code, score_version)
    if intraday:
        if not intraday.get("in_target"):
            # 분석 대상 종목이 아님 (896개에 포함 안됨) - score를 None으로 반환
            return StockAnalysis(
                code=code,
                name="",
                score=None,  # 프론트에서 "-"로 표시
                opinion="분석대상외",
                probability=None,
                confidence=None,
                technical_score=None,
                signals={},
                signal_descriptions=["분석 대상 종목이 아닙니다"],
                support_resistance=None,
                price_history=None,
                comment="이 종목은 현재 장중 스코어링 대상에 포함되지 않습니다."
            )

        # 장중 스코어가 있음 - 이를 기반으로 분석 반환
        score = intraday["score"]
        signals_list = intraday.get("signals", [])

        # 의견 계산
        if score >= 65:
            opinion = "매수"
        elif score >= 50:
            opinion = "관망"
        else:
            opinion = "주의"

        # 확률/신뢰도 계산
        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()
        prob_conf = analyst.calculate_probability_confidence(score, signals_list)

        # 신호 설명 변환
        signal_map = {
            'MA_ALIGNED': '✅ 이평선 정배열 (강한 상승 추세)',
            'GOLDEN_CROSS_5_20': '✅ 단기 골든크로스 (5/20일선)',
            'GOLDEN_CROSS_20_60': '✅ 중기 골든크로스 (20/60일선)',
            'DEAD_CROSS_5_20': '⚠️ 단기 데드크로스 (하락 주의)',
            'RSI_OVERSOLD': '✅ RSI 과매도 (반등 기대)',
            'RSI_RECOVERING': '📈 RSI 회복 중',
            'RSI_OVERBOUGHT': '⚠️ RSI 과매수 (조정 주의)',
            'MACD_GOLDEN_CROSS': '✅ MACD 골든크로스',
            'VOLUME_SURGE': '🔥 거래량 급증',
            'BB_LOWER_BOUNCE': '✅ 볼린저밴드 하단 반등',
            'VOLUME_EXPLOSION': '🔥 거래량 폭발',
            'BULLISH_CANDLE': '✅ 장대양봉',
        }
        desc_list = [signal_map.get(s, s) for s in signals_list if s in signal_map][:6]

        # 코멘트 생성
        comment = generate_natural_comment(score, signals_list, {}, prob_conf)

        # 가격 히스토리와 지지/저항선 추가
        price_history = None
        support_resistance = None
        try:
            libs = get_stock_libs()
            if libs:
                get_ohlcv = libs['get_ohlcv']
                ohlcv = get_ohlcv(code, 365)
                if ohlcv is not None and len(ohlcv) >= 20:
                    ohlcv = ohlcv.rename(columns={
                        '시가': 'Open', '고가': 'High', '저가': 'Low',
                        '종가': 'Close', '거래량': 'Volume'
                    })
                    ohlcv['MA5'] = ohlcv['Close'].rolling(window=5).mean()
                    ohlcv['MA20'] = ohlcv['Close'].rolling(window=20).mean()
                    price_history = []
                    for i in range(-20, 0):
                        row = ohlcv.iloc[i]
                        price_history.append({
                            'date': row.name.strftime('%m/%d'),
                            'close': int(row['Close']),
                            'ma5': round(float(row['MA5']), 0) if not pd.isna(row['MA5']) else None,
                            'ma20': round(float(row['MA20']), 0) if not pd.isna(row['MA20']) else None,
                        })
                    from technical_analyst import TechnicalAnalyst
                    analyst = TechnicalAnalyst()
                    sr_levels = analyst.calculate_support_resistance(ohlcv)
                    if sr_levels:
                        from api.schemas.stock import SupportResistance
                        support_resistance = SupportResistance(**sr_levels)
        except Exception as e:
            print(f"Intraday 히스토리 조회 오류: {e}")

        return StockAnalysis(
            code=code,
            name=intraday.get("name", ""),
            score=score,  # 장중 스코어는 평활화 없이 원본 사용
            opinion=opinion,
            probability=prob_conf['probability'],
            confidence=prob_conf['confidence'],
            technical_score=score,
            signals={},
            signal_descriptions=desc_list,
            support_resistance=support_resistance,
            price_history=price_history,
            comment=comment
        )

    # 2. 캐시 확인 (장중 스코어가 없을 때)
    cached = get_cached_analysis(code)
    if cached:
        return cached

    # 3. TOP100 데이터에 있으면 바로 반환 (즉시 응답)
    top100_data = get_top100_analysis(code)
    if top100_data:
        stock_name = top100_data['name']
        score = top100_data['score']
        opinion = top100_data['opinion']
        signals_list = top100_data.get('signals', [])

        # 점수 기반 의견 (없으면 생성)
        if not opinion:
            if score >= 70:
                opinion = '매수'
            elif score >= 50:
                opinion = '관망'
            elif score >= 30:
                opinion = '주의'
            else:
                opinion = '주의'

        # 확률/신뢰도 계산 (TOP100용 간이 계산)
        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()
        prob_conf = analyst.calculate_probability_confidence(score, signals_list)

        # 신호 설명 변환 (TOP100용)
        top100_signal_map = {
            'MA_ALIGNED': '✅ 이평선 정배열 (강한 상승 추세)',
            'GOLDEN_CROSS_5_20': '✅ 단기 골든크로스 (5/20일선)',
            'GOLDEN_CROSS_20_60': '✅ 중기 골든크로스 (20/60일선)',
            'DEAD_CROSS_5_20': '⚠️ 단기 데드크로스 (하락 주의)',
            'RSI_OVERSOLD': '✅ RSI 과매도 (반등 기대)',
            'RSI_RECOVERING': '📈 RSI 회복 중',
            'RSI_OVERBOUGHT': '⚠️ RSI 과매수 (조정 주의)',
            'MACD_GOLDEN_CROSS': '✅ MACD 골든크로스',
            'VOLUME_SURGE': '🔥 거래량 급증',
            'BB_LOWER_BOUNCE': '✅ 볼린저밴드 하단 반등',
        }
        desc_list = [top100_signal_map.get(s, s) for s in signals_list if s in top100_signal_map][:6]

        # 자연어 코멘트 생성
        comment = generate_natural_comment(score, signals_list, {}, prob_conf)

        # TOP100도 가격 히스토리와 지지/저항선 추가
        price_history = None
        support_resistance = None
        try:
            libs = get_stock_libs()
            if libs:
                get_ohlcv = libs['get_ohlcv']
                ohlcv = get_ohlcv(code, 365)
                if ohlcv is not None and len(ohlcv) >= 20:
                    # 컬럼명 변환
                    ohlcv = ohlcv.rename(columns={
                        '시가': 'Open', '고가': 'High', '저가': 'Low',
                        '종가': 'Close', '거래량': 'Volume'
                    })
                    # 이동평균
                    ohlcv['MA5'] = ohlcv['Close'].rolling(window=5).mean()
                    ohlcv['MA20'] = ohlcv['Close'].rolling(window=20).mean()
                    # 가격 히스토리
                    price_history = []
                    for i in range(-20, 0):
                        row = ohlcv.iloc[i]
                        price_history.append({
                            'date': row.name.strftime('%m/%d'),
                            'close': int(row['Close']),
                            'ma5': round(float(row['MA5']), 0) if not pd.isna(row['MA5']) else None,
                            'ma20': round(float(row['MA20']), 0) if not pd.isna(row['MA20']) else None,
                        })
                    # 지지/저항선
                    sr_levels = analyst.calculate_support_resistance(ohlcv)
                    if sr_levels:
                        from api.schemas.stock import SupportResistance
                        support_resistance = SupportResistance(**sr_levels)
        except Exception as e:
            print(f"TOP100 히스토리 조회 오류: {e}")

        # 점수 평활화 적용
        smoothed = smooth_score(code, score)

        result = StockAnalysis(
            code=code,
            name=stock_name,
            score=smoothed,
            opinion=opinion,
            probability=prob_conf['probability'],
            confidence=prob_conf['confidence'],
            technical_score=score,  # 원본 점수는 기술적 점수로 보존
            signals={},
            signal_descriptions=desc_list,
            support_resistance=support_resistance,
            price_history=price_history,
            comment=comment
        )
        set_analysis_cache(code, result)
        return result

    # 3. TOP100에 없으면 실시간 분석
    libs = get_stock_libs()
    if not libs:
        raise HTTPException(status_code=503, detail="주식 데이터 서비스 이용 불가")

    try:
        fdr = libs['fdr']
        get_ohlcv = libs['get_ohlcv']

        # 종목명 조회 (캐시 사용)
        name = get_stock_name(code)

        # OHLCV 데이터
        ohlcv = get_ohlcv(code, 365)
        if ohlcv is None or ohlcv.empty:
            raise HTTPException(status_code=404, detail="가격 데이터를 가져올 수 없습니다")

        # 컬럼명 영문으로 변환 (TechnicalAnalyst는 영문 컬럼명 사용)
        ohlcv = ohlcv.rename(columns={
            '시가': 'Open',
            '고가': 'High',
            '저가': 'Low',
            '종가': 'Close',
            '거래량': 'Volume'
        })

        # 기술적 분석 (변별력 강화 버전 사용)
        from technical_analyst import TechnicalAnalyst
        analyst = TechnicalAnalyst()
        result = analyst.analyze_trend_following_strict(ohlcv)

        if result is None:
            # fallback: 기존 analyze_full 사용
            result = analyst.analyze_full(ohlcv)
            if result is None:
                result = {'score': 50, 'indicators': {}, 'signals': []}

        score = result.get('score', 50)
        indicators = result.get('indicators', {})
        signal_list = result.get('signals', [])

        # 점수 기반 의견 결정
        if score >= 70:
            opinion = '매수'
        elif score >= 50:
            opinion = '관망'
        elif score >= 30:
            opinion = '주의'
        else:
            opinion = '주의'

        # 신호 정리
        signals = {
            'rsi': indicators.get('rsi'),
            'macd': indicators.get('macd'),
            'macd_signal': indicators.get('macd_signal'),
            'bb_position': indicators.get('bb_position'),
            'trend': 'bullish' if 'MA_ALIGNED' in signal_list else 'neutral',
            'volume_signal': indicators.get('volume_signal'),
            'candle_patterns': result.get('patterns', [])
        }

        # 신호를 전문적인 코멘트로 변환
        signal_descriptions = {
            'MA_ALIGNED': '✅ 이평선 정배열 (강한 상승 추세)',
            'GOLDEN_CROSS_5_20': '✅ 단기 골든크로스 발생 (5/20일선)',
            'GOLDEN_CROSS_20_60': '✅ 중기 골든크로스 발생 (20/60일선)',
            'DEAD_CROSS_5_20': '⚠️ 단기 데드크로스 발생 (하락 주의)',
            'RSI_OVERSOLD': '✅ RSI 과매도 구간 (반등 기대)',
            'RSI_RECOVERING': '📈 RSI 회복 중 (상승 전환 가능성)',
            'RSI_OVERBOUGHT': '⚠️ RSI 과매수 구간 (조정 주의)',
            'MACD_GOLDEN_CROSS': '✅ MACD 골든크로스 (강력 매수 신호)',
            'MACD_HIST_POSITIVE': '✅ MACD 히스토그램 양전환',
            'MACD_HIST_RISING': '📈 MACD 히스토그램 상승 중',
            'BB_LOWER_BOUNCE': '✅ 볼린저밴드 하단 반등 (저점 매수 기회)',
            'BB_LOWER_TOUCH': '✅ 볼린저밴드 하단 터치 (반등 기대)',
            'BB_UPPER_BREAK': '⚠️ 볼린저밴드 상단 돌파 (단기 과열)',
            'STOCH_GOLDEN_OVERSOLD': '✅ 스토캐스틱 과매도 골든크로스 (강력 반등 신호)',
            'STOCH_GOLDEN_CROSS': '✅ 스토캐스틱 골든크로스',
            'STOCH_OVERSOLD': '✅ 스토캐스틱 과매도 구간',
            'ADX_STRONG_UPTREND': '✅ ADX 강한 상승 추세 확인',
            'ADX_UPTREND': '📈 ADX 상승 추세',
            'CCI_OVERSOLD': '✅ CCI 과매도 구간',
            'CCI_OVERBOUGHT': '⚠️ CCI 과매수 구간',
            'WILLR_OVERSOLD': '✅ 윌리엄스 %R 과매도',
            'WILLR_OVERBOUGHT': '⚠️ 윌리엄스 %R 과매수',
            'VOLUME_SURGE': '🔥 거래량 급증 (평균 대비 2배 이상)',
            'VOLUME_HIGH': '📊 거래량 증가 (평균 대비 1.5배)',
            'VOLUME_ABOVE_AVG': '📊 평균 이상 거래량',
            'OBV_ABOVE_MA': '✅ OBV 이평선 상회 (매집 진행)',
            'OBV_RISING': '📈 OBV 상승 추세',
            'MFI_OVERSOLD': '✅ MFI 과매도 (자금 유입 기대)',
            'MFI_LOW': '📈 MFI 저점 구간',
            'MFI_OVERBOUGHT': '⚠️ MFI 과매수 (자금 유출 주의)',
            'SUPERTREND_BUY': '✅ 슈퍼트렌드 매수 신호 전환',
            'SUPERTREND_UPTREND': '📈 슈퍼트렌드 상승 추세',
            'PSAR_BUY_SIGNAL': '✅ PSAR 매수 신호',
            'PSAR_UPTREND': '📈 PSAR 상승 추세',
            'ROC_POSITIVE_CROSS': '✅ ROC 양전환 (모멘텀 회복)',
            'ROC_STRONG_MOMENTUM': '📈 ROC 강한 모멘텀',
            'ICHIMOKU_GOLDEN_CROSS': '✅ 일목균형표 전환선/기준선 골든크로스',
            'ICHIMOKU_ABOVE_CLOUD': '✅ 가격이 구름대 위 (상승 추세)',
            'CMF_STRONG_INFLOW': '✅ CMF 강한 자금 유입',
            'CMF_POSITIVE': '📈 CMF 양수 (순매수)',
            'CMF_STRONG_OUTFLOW': '⚠️ CMF 강한 자금 유출',
            'HAMMER': '✅ 망치형 캔들 (반등 신호)',
            'INVERTED_HAMMER': '✅ 역망치형 캔들 (반등 가능)',
            'BULLISH_ENGULFING': '✅ 상승 장악형 캔들 (강력 매수)',
            'BEARISH_ENGULFING': '⚠️ 하락 장악형 캔들 (하락 주의)',
            'DOJI': '📊 도지 캔들 (변곡점 가능)',
            'MORNING_STAR': '✅ 샛별형 패턴 (강력 반등 신호)',
            'EVENING_STAR': '⚠️ 저녁별형 패턴 (하락 전환 주의)',
            # 52주 신고가/신저가
            'NEW_HIGH_52W': '🚀 52주 신고가 근접',
            'BREAKOUT_52W_HIGH': '🚀 52주 신고가 돌파!',
            'NEW_LOW_52W': '⚠️ 52주 신저가 근접',
        }

        # 상승확률 및 신뢰도 계산
        prob_conf = analyst.calculate_probability_confidence(score, signal_list)
        probability = prob_conf['probability']
        confidence = prob_conf['confidence']

        # 지지/저항선 계산
        sr_levels = analyst.calculate_support_resistance(ohlcv)
        support_resistance = None
        if sr_levels:
            from api.schemas.stock import SupportResistance
            support_resistance = SupportResistance(**sr_levels)

        # 신호 설명 리스트 생성 (불릿 포인트용)
        desc_list = [signal_descriptions.get(s) for s in signal_list if s in signal_descriptions][:6]

        # 자연어 코멘트 생성
        comment = generate_natural_comment(score, signal_list, indicators, prob_conf)

        # 가격 히스토리 생성 (차트용 - 최근 20일)
        price_history = []
        if len(ohlcv) >= 20:
            # 이동평균 계산
            ohlcv['MA5'] = ohlcv['Close'].rolling(window=5).mean()
            ohlcv['MA20'] = ohlcv['Close'].rolling(window=20).mean()

            for i in range(-20, 0):
                row = ohlcv.iloc[i]
                price_history.append({
                    'date': row.name.strftime('%m/%d'),
                    'close': int(row['Close']),
                    'ma5': round(float(row['MA5']), 0) if not pd.isna(row['MA5']) else None,
                    'ma20': round(float(row['MA20']), 0) if not pd.isna(row['MA20']) else None,
                })

        # 점수 평활화 적용
        smoothed = smooth_score(code, score)

        result = StockAnalysis(
            code=code,
            name=name,
            score=smoothed,
            opinion=opinion,
            probability=probability,
            confidence=confidence,
            technical_score=score,  # 원본 점수는 기술적 점수로 보존
            signals=signals,
            signal_descriptions=desc_list,
            support_resistance=support_resistance,
            price_history=price_history if price_history else None,
            comment=comment
        )
        set_analysis_cache(code, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Stock Analysis Error] {e}")
        raise HTTPException(status_code=500, detail="종목 분석 중 오류가 발생했습니다")


# 펀더멘탈 분석 캐시 (1시간 TTL)
_fundamental_cache: Dict[str, Tuple[Any, float]] = {}
_FUNDAMENTAL_CACHE_TTL = 3600  # 1시간


@router.get("/{code}/fundamental", response_model=FundamentalAnalysis)
async def get_fundamental(code: str):
    """
    종목 펀더멘탈 분석 (DART API 연동)

    - 최근 3년 재무제표 데이터
    - ROE, 부채비율, 유동비율, 영업이익률
    - 펀더멘탈 점수 및 AI 분석 코멘트
    """
    # 캐시 확인
    if code in _fundamental_cache:
        data, timestamp = _fundamental_cache[code]
        if time.time() - timestamp < _FUNDAMENTAL_CACHE_TTL:
            return data
        del _fundamental_cache[code]

    try:
        # 종목명 조회
        stock_name = get_stock_name(code)

        # DART 서비스로 펀더멘탈 분석
        from api.services.dart_service import DartService
        dart = DartService()
        analysis = dart.get_fundamental_analysis(code, stock_name)

        if not analysis:
            raise HTTPException(
                status_code=404,
                detail="펀더멘탈 데이터를 조회할 수 없습니다"
            )

        result = FundamentalAnalysis(**analysis)

        # 캐시 저장
        _fundamental_cache[code] = (result, time.time())
        if len(_fundamental_cache) > 200:
            oldest = min(_fundamental_cache.items(), key=lambda x: x[1][1])
            del _fundamental_cache[oldest[0]]

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Fundamental Analysis Error] {e}")
        raise HTTPException(
            status_code=500,
            detail="펀더멘탈 분석 중 오류가 발생했습니다"
        )
