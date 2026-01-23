"""
전종목 스크리닝 시스템
- KRX 전체 종목 로딩 (KOSPI + KOSDAQ)
- 다단계 필터링 파이프라인
- 병렬 처리로 속도 최적화
"""
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import time
from technical_analyst import TechnicalAnalyst
from config import calculate_signal_weight

warnings.filterwarnings("ignore")


class MarketScreener:
    """전종목 스크리닝 시스템"""
    def __init__(self, max_workers=10, scoring_version="v2", fetch_investor_data=False):
        self.tech_analyst = TechnicalAnalyst()
        self.max_workers = max_workers
        self.all_stocks = None
        self.filtered_stocks = None
        self.scoring_version = scoring_version
        self.fetch_investor_data = fetch_investor_data  # 네이버 수급 데이터 조회 여부

        # 스코어링 함수 로드
        from scoring import SCORING_FUNCTIONS
        self.scoring_func = SCORING_FUNCTIONS.get(scoring_version)
    def load_all_stocks(self):
        """KRX 전체 종목 로딩"""
        print("[1/5] KRX 전체 종목 로딩 중...")
        try:
            # KOSPI + KOSDAQ 전체 종목 가져오기
            krx = fdr.StockListing("KRX")
            # 필요한 컬럼만 선택 (Close 추가: 주가 필터용)
            columns_needed = ["Code", "Name", "Market", "Marcap", "Volume", "Amount", "Close"]
            available_cols = [c for c in columns_needed if c in krx.columns]
            self.all_stocks = krx[available_cols].copy()
            # 종목코드 6자리 맞추기
            self.all_stocks["Code"] = self.all_stocks["Code"].astype(str).str.zfill(6)
            print(f"    → 총 {len(self.all_stocks):,}개 종목 로딩 완료")
            return self.all_stocks
        except Exception as e:
            print(f"    → 종목 로딩 실패: {e}")
            return None
    def filter_by_liquidity(self, min_marcap=30_000_000_000, max_marcap=1_000_000_000_000, min_amount=300_000_000, max_price=None):
        """
        1차 필터링: 유동성 기준
        - min_marcap: 최소 시가총액 (기본 300억)
        - max_marcap: 최대 시가총액 (대형 우량주 제외용, 기본 1조)
        - min_amount: 최소 거래대금 (기본 3억)
        - max_price: 최대 주가 (기본 None, 제한 없음)
        """
        filter_desc = f"시총>{min_marcap / 1e8:.0f}억"
        if max_marcap:
            filter_desc += f", 시총<{max_marcap / 1e12:.0f}조"
        filter_desc += f", 거래대금>{min_amount / 1e8:.0f}억"
        if max_price:
            filter_desc += f", 주가<{max_price / 10000:.0f}만원"
        print(f"[2/5] 유동성 필터링 ({filter_desc})...")
        if self.all_stocks is None:
            self.load_all_stocks()
        df = self.all_stocks.copy()
        # 시가총액 필터 (Marcap 컬럼이 있는 경우)
        if "Marcap" in df.columns:
            df = df[df["Marcap"] >= min_marcap]
            if max_marcap:
                df = df[df["Marcap"] <= max_marcap]
        # 거래대금 필터 (Amount 컬럼이 있는 경우)
        if "Amount" in df.columns:
            df = df[df["Amount"] >= min_amount]
        # 주가 필터 (Close 컬럼이 있는 경우)
        if max_price and "Close" in df.columns:
            df["Close"] = pd.to_numeric(df["Close"], errors='coerce')
            df = df[df["Close"] <= max_price]
        self.filtered_stocks = df
        print(f"    → {len(df):,}개 종목 통과")
        return df
    def get_problem_stocks(self):
        """
        관리종목, 투자경고, 투자위험 종목 목록 조회 (KRX)
        """
        problem_codes = set()
        try:
            from pykrx import stock
            today = datetime.now().strftime("%Y%m%d")

            # 관리종목 조회 (KOSPI + KOSDAQ)
            for market in ["KOSPI", "KOSDAQ"]:
                try:
                    # 관리종목은 pykrx에서 직접 제공하지 않아 이름으로 필터
                    pass
                except:
                    pass
        except Exception as e:
            print(f"    → 문제종목 조회 실패: {e}")

        return problem_codes

    def filter_special_stocks(self):
        """
        관리종목, 정리매매, 스팩, 투자경고/위험 종목 제외
        """
        print("[3/5] 특수종목 제외 중...")
        if self.filtered_stocks is None:
            self.filter_by_liquidity()
        df = self.filtered_stocks.copy()
        original_count = len(df)

        # 종목명으로 특수종목 필터링 (관리종목, 투자주의, 투자경고, 투자위험 포함)
        exclude_keywords = [
            "스팩",
            "SPAC",
            "리츠",
            "ETF",
            "ETN",
            "인버스",
            "레버리지",
            "합병",
            "정리매매",
            "관리종목",
            "투자주의",
            "투자경고",
            "투자위험",
            "1호",
            "2호",
            "3호",
            "4호",
            "5호",
            "6호",
            "7호",
            "8호",
            "9호",
            "10호",
        ]
        for keyword in exclude_keywords:
            df = df[~df["Name"].str.contains(keyword, case=False, na=False)]

        # 우선주 제외 (종목코드 끝자리 0이 아닌 경우)
        # 예: 삼성전자우 005935 vs 삼성전자 005930
        df = df[df["Code"].str[-1] == "0"]

        # 주가 1,000원 미만 제외 비활성화
        # if "Close" in df.columns:
        #     df["Close"] = pd.to_numeric(df["Close"], errors='coerce')
        #     before_penny = len(df)
        #     df = df[df["Close"] >= 1000]
        #     penny_excluded = before_penny - len(df)
        #     if penny_excluded > 0:
        #         print(f"    → 1,000원 미만 {penny_excluded}개 제외")

        self.filtered_stocks = df
        print(f"    → {original_count - len(df):,}개 제외, {len(df):,}개 남음")
        return df
    def _analyze_single_stock(self, stock_info, mode="quick"):
        """
        단일 종목 분석 (병렬 처리용)
        mode: 'quick' (빠른 스크리닝) 또는 'full' (전체 분석)
        """
        code = stock_info["Code"]
        name = stock_info["Name"]
        try:
            # 주가 데이터 수집 (최근 1년)
            df = self.tech_analyst.get_ohlcv(code, days=365)
            if df is None or len(df) < 60:
                return None
            # 분석 수행
            if mode == "quick":
                result = self.tech_analyst.get_quick_score(df)
                if result is None:
                    return None
                return {
                    "code": code,
                    "name": name,
                    "market": stock_info.get("Market", ""),
                    "score": result["score"],
                    "signals": result["signals"],
                    "indicators": result["indicators"],
                    "close": result["close"],
                    "volume": result["volume"],
                    "change_pct": result["change_pct"],
                }
            else:
                # 스코어링 엔진 버전에 따라 다른 함수 사용
                if self.scoring_func:
                    result = self.scoring_func(df)
                else:
                    # 기본: 변별력 강화 버전 (래치 전략)
                    result = self.tech_analyst.analyze_trend_following_strict(df)

                if result is None:
                    return None

                indicators = result.get("indicators", {})

                # 선정 이유 생성
                reasons = []
                if indicators.get('sma20_slope', 0) > 3:
                    reasons.append(f"20일선 급등 ({indicators.get('sma20_slope', 0):.1f}%)")
                elif indicators.get('sma20_slope', 0) > 1.5:
                    reasons.append(f"20일선 상승 ({indicators.get('sma20_slope', 0):.1f}%)")

                if 'BREAKOUT_60D_HIGH' in result['signals']:
                    reasons.append("60일 신고가 돌파")
                elif 'NEAR_60D_HIGH' in result['signals']:
                    reasons.append("60일 고가 근접")

                rsi = indicators.get('rsi', 0)
                if 60 <= rsi <= 75:
                    reasons.append(f"RSI 적정 ({rsi:.0f})")
                elif rsi > 80:
                    reasons.append(f"RSI 강세 ({rsi:.0f})")

                vol_ratio = indicators.get('volume_ratio', 0)
                if vol_ratio >= 5:
                    reasons.append(f"거래량 폭발 ({vol_ratio:.1f}배)")
                elif vol_ratio >= 3:
                    reasons.append(f"거래량 급증 ({vol_ratio:.1f}배)")

                trading_value = indicators.get('trading_value_억', 0)
                if trading_value >= 500:
                    reasons.append(f"거래대금 {trading_value:.0f}억")
                elif trading_value >= 100:
                    reasons.append(f"거래대금 {trading_value:.0f}억")

                # 점수 추출 (v4는 result 최상위, v1-v3는 indicators 내부)
                trend_score = result.get("trend_score") or indicators.get("trend_score", 0)
                momentum_score = result.get("momentum_score") or indicators.get("momentum_score", 0)
                # v4는 supply_score, v1-v3는 volume_score
                volume_score = result.get("supply_score") or result.get("volume_score") or indicators.get("volume_score", 0)
                pattern_score = result.get("pattern_score") or indicators.get("pattern_score", 0)

                return {
                    "code": code,
                    "name": name,
                    "market": stock_info.get("Market", ""),
                    "score": result["score"],
                    "signals": result["signals"],
                    "patterns": result.get("patterns", []),
                    "indicators": indicators,
                    "close": indicators.get("close", 0),
                    "volume": indicators.get("volume", 0),
                    "change_pct": indicators.get("change_pct", 0),
                    # 개별 점수 (v1-v4 공통)
                    "trend_score": trend_score,
                    "momentum_score": momentum_score,
                    "volume_score": volume_score,  # v4에서는 supply_score
                    "pattern_score": pattern_score,  # v4 전용
                    # 지표
                    "sma20_slope": indicators.get("sma20_slope", 0),
                    "rsi": indicators.get("rsi", 0),
                    "volume_ratio": indicators.get("volume_ratio", 0),
                    "trading_value_억": indicators.get("trading_value_억", 0),
                    "high_60d_pct": indicators.get("high_60d_pct", 0),
                    "ma_status": indicators.get("ma_status", ""),
                    "selection_reasons": reasons,
                    # 버전 정보
                    "scoring_version": result.get("version", "v2"),
                }
        except Exception as e:
            # 에러 발생시 조용히 무시
            return None
    def screen_all(self, mode="quick", progress_interval=50):
        """
        전종목 기술적 스크리닝
        mode: 'quick' (빠른 스크리닝, 약 5분) 또는 'full' (전체 분석, 약 15분)
        """
        print(f"[4/5] 기술적 스크리닝 시작 ({mode} 모드)...")
        if self.filtered_stocks is None:
            self.filter_special_stocks()
        stocks_to_analyze = self.filtered_stocks.to_dict("records")
        total = len(stocks_to_analyze)
        results = []
        completed = 0
        start_time = time.time()
        print(
            f"    → {total:,}개 종목 분석 중 (병렬 처리: {self.max_workers} workers)..."
        )
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 모든 작업 제출
            future_to_stock = {
                executor.submit(self._analyze_single_stock, stock, mode): stock
                for stock in stocks_to_analyze
            }
            # 완료된 작업 수집 (타임아웃 30초)
            for future in as_completed(future_to_stock):
                completed += 1
                stock = future_to_stock[future]
                try:
                    result = future.result(timeout=30)
                    if result is not None:
                        results.append(result)
                except TimeoutError:
                    print(f"    ⚠ 타임아웃: {stock.get('Name', stock.get('Code'))} (30초 초과)")
                except Exception as e:
                    print(f"    ⚠ 오류: {stock.get('Name', stock.get('Code'))} - {e}")
                # 진행 상황 출력
                if completed % progress_interval == 0 or completed == total:
                    elapsed = time.time() - start_time
                    eta = (
                        (elapsed / completed) * (total - completed)
                        if completed > 0
                        else 0
                    )
                    print(
                        f"    → 진행: {completed:,}/{total:,} ({completed / total * 100:.1f}%) | "
                        f"유효: {len(results):,} | ETA: {eta:.0f}초"
                    )
        elapsed_total = time.time() - start_time
        print(
            f"    → 스크리닝 완료: {len(results):,}개 유효 종목 (소요시간: {elapsed_total:.1f}초)"
        )
        return results
    def get_top_stocks(self, results, top_n=100, min_score=30):
        """
        상위 종목 추출 (다중 정렬 기준 적용)
        """
        print(f"[5/5] 상위 {top_n}개 종목 선정 중...")
        # 최소 점수 이상만 필터
        filtered = [r for r in results if r["score"] >= min_score]
        # 다중 정렬 기준 함수
        def sort_key(stock):
            signals = stock.get("signals", [])
            # 1차: 점수 (내림차순)
            score_priority = stock["score"]
            # 2차: 총 신호 가중치 (높은 순서)
            total_weight = calculate_signal_weight(signals)
            # 3차: 신호 개수 (많은 순서)
            signal_count = len(signals)
            # 튜플 반환: (1차, 2차, 3차)
            return (-score_priority, -total_weight, -signal_count)
        # 다중 정렬 적용
        sorted_results = sorted(filtered, key=sort_key)
        # 상위 N개 추출
        top_stocks = sorted_results[:top_n]
        print(f"    → {len(top_stocks)}개 종목 선정 완료")
        return top_stocks

    def enrich_with_investor_data(self, results, max_stocks=200):
        """
        상위 종목에 네이버 금융 수급 데이터 추가 (V4 전용)

        Args:
            results: 스크리닝 결과 리스트
            max_stocks: 수급 데이터 조회할 최대 종목 수

        Returns:
            수급 데이터가 추가된 결과 리스트
        """
        if self.scoring_version != 'v4':
            return results

        if not self.fetch_investor_data:
            return results

        print(f"    → 상위 {min(len(results), max_stocks)}개 종목 수급 데이터 조회 중...")

        try:
            from naver_investor import get_investor_trends_batch
            from scoring.scoring_v4 import calculate_score_v4

            # 상위 종목 코드 추출
            codes = [r['code'] for r in results[:max_stocks]]

            # 일괄 조회
            start_time = time.time()
            investor_data = get_investor_trends_batch(codes, days=5, max_workers=self.max_workers)
            elapsed = time.time() - start_time
            print(f"    → 수급 데이터 조회 완료: {len(investor_data)}개 ({elapsed:.1f}초)")

            # 결과에 수급 데이터 추가 및 V4 재점수화
            enriched_count = 0
            for r in results[:max_stocks]:
                code = r['code']
                if code in investor_data:
                    inv = investor_data[code]

                    # 수급 데이터를 indicators에 추가
                    r['indicators']['foreign_net_5d'] = inv['foreign_net']
                    r['indicators']['institution_net_5d'] = inv['institution_net']
                    r['indicators']['foreign_hold_ratio'] = inv['foreign_hold_ratio']
                    r['indicators']['consecutive_foreign_buy'] = inv['consecutive_foreign_buy']

                    # 수급 점수 재계산 (최대 8점 추가)
                    supply_bonus = 0
                    total_inst_foreign = inv['foreign_net'] + inv['institution_net']

                    if total_inst_foreign > 0:
                        supply_bonus += 5
                        if 'INST_FOREIGN_BUY' not in r['signals']:
                            r['signals'].append('INST_FOREIGN_BUY')
                    elif total_inst_foreign < 0:
                        supply_bonus -= 3
                        if 'INST_FOREIGN_SELL' not in r['signals']:
                            r['signals'].append('INST_FOREIGN_SELL')

                    if inv['consecutive_foreign_buy'] >= 3:
                        supply_bonus += 3
                        if 'FOREIGN_CONSECUTIVE_BUY' not in r['signals']:
                            r['signals'].append('FOREIGN_CONSECUTIVE_BUY')

                    # 점수 업데이트
                    if supply_bonus != 0:
                        old_score = r['score']
                        # volume_score는 v4에서 supply_score
                        old_supply = r.get('volume_score', 0) or 0
                        new_supply = min(30, max(-8, old_supply + supply_bonus))
                        r['volume_score'] = new_supply
                        r['score'] = max(0, min(100, old_score + supply_bonus))

                    enriched_count += 1

            print(f"    → {enriched_count}개 종목 수급 데이터 반영 완료")

        except Exception as e:
            print(f"    → 수급 데이터 조회 실패: {e}")

        return results
    def run_full_screening(
        self,
        top_n=100,
        mode="quick",
        min_marcap=30_000_000_000,
        max_marcap=1_000_000_000_000,
        min_amount=300_000_000,
        max_price=None,
    ):
        """
        전체 스크리닝 파이프라인 실행
        Returns: (top_stocks, stats) 튜플
        """
        print("\n" + "=" * 60)
        print(f"  전종목 스크리닝 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")
        start_time = time.time()

        # 통계 수집용 딕셔너리
        stats = {}

        # 1. 전체 종목 로딩
        self.load_all_stocks()
        stats['total_stocks'] = len(self.all_stocks) if self.all_stocks is not None else 0

        # 2. 유동성 필터링
        self.filter_by_liquidity(min_marcap=min_marcap, max_marcap=max_marcap, min_amount=min_amount, max_price=max_price)
        stats['liquidity_passed'] = len(self.filtered_stocks) if self.filtered_stocks is not None else 0

        # 3. 특수종목 제외
        self.filter_special_stocks()
        stats['special_excluded'] = len(self.filtered_stocks) if self.filtered_stocks is not None else 0

        # 4. 기술적 스크리닝
        results = self.screen_all(mode=mode)
        stats['valid_analyzed'] = len(results)

        # 전종목 점수 저장 (code -> score 매핑)
        stats['all_scores'] = {r['code']: r.get('score', 0) for r in results}

        # 4.5 수급 데이터 추가 (V4 + fetch_investor_data 옵션)
        if self.scoring_version == 'v4' and self.fetch_investor_data:
            # 1차 정렬 후 상위 종목에만 수급 데이터 조회
            sorted_results = sorted(results, key=lambda x: -x['score'])
            results = self.enrich_with_investor_data(sorted_results, max_stocks=top_n * 2)
            stats['investor_data_fetched'] = True
        else:
            stats['investor_data_fetched'] = False

        # 5. 상위 종목 추출
        top_stocks = self.get_top_stocks(results, top_n=top_n)
        stats['final_selected'] = len(top_stocks)

        elapsed = time.time() - start_time
        stats['elapsed_seconds'] = elapsed
        print(f"\n총 소요시간: {elapsed / 60:.1f}분")

        return top_stocks, stats
class SignalFilter:
    """특정 신호 기반 필터링"""
    # 강력 매수 신호
    STRONG_BUY_SIGNALS = [
        "GOLDEN_CROSS_20_60",  # 중장기 골든크로스
        "MACD_GOLDEN_CROSS",  # MACD 골든크로스
        "SUPERTREND_BUY",  # 슈퍼트렌드 매수 전환
        "STOCH_GOLDEN_OVERSOLD",  # 과매도 구간 스토캐스틱 골든크로스
        "MORNING_STAR",  # 샛별형 캔들
        "PSAR_BUY_SIGNAL",  # PSAR 매수 전환
    ]
    # 매수 관심 신호
    BUY_SIGNALS = [
        "GOLDEN_CROSS_5_20",  # 단기 골든크로스
        "MA_ALIGNED",  # 이평선 정배열
        "RSI_OVERSOLD",  # RSI 과매도
        "BB_LOWER_BOUNCE",  # 볼린저 하단 반등
        "VOLUME_SURGE",  # 거래량 급증
        "MFI_OVERSOLD",  # MFI 과매도
        "OBV_ABOVE_MA",  # OBV 이평선 위
        "ICHIMOKU_GOLDEN_CROSS",  # 일목 골든크로스
        "CMF_STRONG_INFLOW",  # 강한 자금 유입
        "BULLISH_ENGULFING",  # 상승 장악형
    ]
    # 주의 신호
    CAUTION_SIGNALS = [
        "RSI_OVERBOUGHT",  # RSI 과매수
        "BB_UPPER_BREAK",  # 볼린저 상단 돌파
        "MFI_OVERBOUGHT",  # MFI 과매수
        "DEAD_CROSS_5_20",  # 데드크로스
        "CMF_STRONG_OUTFLOW",  # 강한 자금 유출
        "BEARISH_ENGULFING",  # 하락 장악형
        "EVENING_STAR",  # 저녁별형
    ]
    @classmethod
    def filter_by_signals(cls, results, required_signals=None, exclude_signals=None):
        """
        특정 신호 기반 필터링
        - required_signals: 반드시 포함해야 할 신호 (OR 조건)
        - exclude_signals: 제외할 신호 (하나라도 있으면 제외)
        """
        filtered = []
        for r in results:
            signals = r.get("signals", [])
            # 제외 신호 체크
            if exclude_signals:
                if any(s in signals for s in exclude_signals):
                    continue
            # 필수 신호 체크 (OR 조건)
            if required_signals:
                if not any(s in signals for s in required_signals):
                    continue
            filtered.append(r)
        return filtered
    @classmethod
    def get_strong_buy_candidates(cls, results):
        """강력 매수 후보 추출"""
        return cls.filter_by_signals(
            results,
            required_signals=cls.STRONG_BUY_SIGNALS,
            exclude_signals=cls.CAUTION_SIGNALS,
        )
    @classmethod
    def get_buy_candidates(cls, results):
        """매수 관심 후보 추출"""
        return cls.filter_by_signals(
            results,
            required_signals=cls.BUY_SIGNALS,
            exclude_signals=cls.CAUTION_SIGNALS,
        )
def format_result_table(results, max_rows=20):
    """결과를 테이블 형식으로 출력"""
    if not results:
        print("결과 없음")
        return
    print("\n" + "=" * 100)
    print(
        f"{'순위':>4} | {'종목코드':^8} | {'종목명':<15} | {'시장':^6} | {'점수':>5} | {'현재가':>12} | {'등락률':>8} | 주요 신호"
    )
    print("-" * 100)
    for i, r in enumerate(results[:max_rows], 1):
        signals = r.get("signals", [])[:3]  # 상위 3개 신호만
        signals_str = ", ".join(signals) if signals else "-"
        close = r.get("close", 0)
        change = r.get("change_pct", 0)
        change_sign = "+" if change >= 0 else ""
        print(
            f"{i:>4} | {r['code']:^8} | {r['name']:<15} | {r['market']:^6} | "
            f"{r['score']:>5.0f} | {close:>12,.0f} | {change_sign}{change:>6.2f}% | {signals_str}"
        )
    print("=" * 100)
if __name__ == "__main__":
    # 테스트 실행
    screener = MarketScreener(max_workers=10)
    # 빠른 스크리닝 (약 5분)
    top_stocks = screener.run_full_screening(
        top_n=100,
        mode="quick",
        min_marcap=30_000_000_000,  # 시총 300억 이상
        min_amount=300_000_000,  # 거래대금 3억 이상
    )
    # 결과 출력
    format_result_table(top_stocks, max_rows=30)
