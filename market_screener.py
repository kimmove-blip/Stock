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
    def __init__(self, max_workers=10):
        self.tech_analyst = TechnicalAnalyst()
        self.max_workers = max_workers
        self.all_stocks = None
        self.filtered_stocks = None
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
                result = self.tech_analyst.analyze_full(df)
                if result is None:
                    return None
                return {
                    "code": code,
                    "name": name,
                    "market": stock_info.get("Market", ""),
                    "score": result["score"],
                    "signals": result["signals"],
                    "patterns": result["patterns"],
                    "indicators": result["indicators"],
                    "close": result["indicators"].get("close", 0),
                    "volume": result["indicators"].get("volume", 0),
                    "change_pct": result["indicators"].get("change_pct", 0),
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
            # 완료된 작업 수집
            for future in as_completed(future_to_stock):
                completed += 1
                result = future.result()
                if result is not None:
                    results.append(result)
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
    def run_full_screening(
        self,
        top_n=100,
        mode="quick",
        min_marcap=50_000_000_000,
        max_marcap=None,
        min_amount=1_000_000_000,
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
