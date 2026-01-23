"""
DART API Service - 펀더멘탈 분석 데이터 조회
DB 캐싱으로 DART API 호출 최소화 (연/분기 보고서 지원)
"""
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

import OpenDartReader
import pandas as pd


# 보고서 타입 정의
REPORT_TYPES = {
    'annual': {'code': '11011', 'name': '사업보고서', 'month': 3},
    'q1': {'code': '11013', 'name': '1분기보고서', 'month': 5},
    'q2': {'code': '11012', 'name': '반기보고서', 'month': 8},
    'q3': {'code': '11014', 'name': '3분기보고서', 'month': 11},
}

DB_PATH = '/home/kimhc/Stock/database/stock_data.db'


@contextmanager
def get_db_connection():
    """DB 연결 컨텍스트 매니저"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


class DartService:
    """DART API 서비스 클래스 (DB 캐싱)"""
    _instance = None
    _dart = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def dart(self) -> OpenDartReader:
        """OpenDartReader 인스턴스 (지연 로딩)"""
        if DartService._dart is None:
            api_key = os.getenv("DART_API_KEY")
            if not api_key:
                raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다")
            DartService._dart = OpenDartReader(api_key)
        return DartService._dart

    def get_corp_code(self, stock_code: str) -> Optional[str]:
        """종목코드(6자리) → DART 고유번호(8자리) 변환"""
        try:
            return self.dart.find_corp_code(stock_code)
        except Exception as e:
            print(f"DART 고유번호 조회 실패 ({stock_code}): {e}")
            return None

    def get_from_db(self, stock_code: str, years: int = 3) -> List[Dict]:
        """DB에서 펀더멘탈 데이터 조회"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM fundamental_data
                WHERE stock_code = ?
                ORDER BY year DESC,
                    CASE report_type
                        WHEN 'annual' THEN 4
                        WHEN 'q3' THEN 3
                        WHEN 'q2' THEN 2
                        WHEN 'q1' THEN 1
                    END DESC
                LIMIT ?
            """, (stock_code, years * 4))  # 연 4개 보고서 * years

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_latest_from_db(self, stock_code: str) -> Optional[Dict]:
        """DB에서 최신 펀더멘탈 데이터 1개 조회"""
        data = self.get_from_db(stock_code, years=1)
        return data[0] if data else None

    def save_to_db(self, stock_code: str, stock_name: str, year: int,
                   report_type: str, data: Dict):
        """펀더멘탈 데이터 DB 저장"""
        report_code = REPORT_TYPES[report_type]['code']

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO fundamental_data (
                    stock_code, stock_name, year, report_type, report_code,
                    revenue, operating_income, net_income,
                    total_assets, total_liabilities, total_equity,
                    current_assets, current_liabilities,
                    roe, debt_ratio, liquidity_ratio, operating_margin,
                    dart_rcept_no, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                stock_code, stock_name, year, report_type, report_code,
                data.get('revenue'), data.get('operating_income'), data.get('net_income'),
                data.get('total_assets'), data.get('total_liabilities'), data.get('total_equity'),
                data.get('current_assets'), data.get('current_liabilities'),
                data.get('roe'), data.get('debt_ratio'), data.get('liquidity_ratio'),
                data.get('operating_margin'), data.get('rcept_no')
            ))
            conn.commit()

    def fetch_from_dart(self, stock_code: str, year: int, report_type: str) -> Optional[Dict]:
        """DART API에서 재무데이터 조회"""
        corp_code = self.get_corp_code(stock_code)
        if not corp_code:
            return None

        report_code = REPORT_TYPES[report_type]['code']

        try:
            df = self.dart.finstate(corp_code, str(year), reprt_code=report_code)

            if df is None or df.empty:
                return None

            # 연결재무제표(CFS) 우선, 없으면 개별재무제표(OFS)
            if 'fs_div' in df.columns:
                cfs_data = df[df['fs_div'] == 'CFS']
                if cfs_data.empty:
                    cfs_data = df[df['fs_div'] == 'OFS']
                df = cfs_data

            if df.empty:
                return None

            # 데이터 추출
            data = self._extract_financial_data(df)

            # 비율 계산
            data.update(self._calculate_ratios(data))

            # 접수번호 저장
            if 'rcept_no' in df.columns:
                data['rcept_no'] = df.iloc[0]['rcept_no']

            return data

        except Exception as e:
            print(f"DART API 조회 실패 ({stock_code}, {year}, {report_type}): {e}")
            return None

    def _extract_financial_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """DataFrame에서 재무 데이터 추출"""

        def get_amount(account_names: List[str]) -> Optional[int]:
            """계정명으로 금액 조회 (억원 단위로 변환)"""
            for name in account_names:
                mask = df['account_nm'].str.contains(name, na=False)
                if mask.any():
                    row = df[mask].iloc[0]
                    if 'thstrm_amount' in row and pd.notna(row['thstrm_amount']):
                        try:
                            amount_str = str(row['thstrm_amount']).replace(',', '')
                            amount = int(float(amount_str))
                            return amount // 100_000_000
                        except:
                            pass
            return None

        return {
            'revenue': get_amount(['매출액', '수익(매출액)', '영업수익']),
            'operating_income': get_amount(['영업이익', '영업이익(손실)']),
            'net_income': get_amount(['당기순이익', '당기순이익(손실)', '분기순이익']),
            'total_assets': get_amount(['자산총계']),
            'total_liabilities': get_amount(['부채총계']),
            'total_equity': get_amount(['자본총계']),
            'current_assets': get_amount(['유동자산']),
            'current_liabilities': get_amount(['유동부채']),
        }

    def _calculate_ratios(self, data: Dict) -> Dict[str, Optional[float]]:
        """재무비율 계산"""
        ratios = {
            'roe': None,
            'debt_ratio': None,
            'liquidity_ratio': None,
            'operating_margin': None,
        }

        # ROE = 당기순이익 / 자본총계 * 100
        if data.get('net_income') and data.get('total_equity') and data['total_equity'] > 0:
            ratios['roe'] = round(data['net_income'] / data['total_equity'] * 100, 2)

        # 부채비율 = 부채총계 / 자본총계 * 100
        if data.get('total_liabilities') and data.get('total_equity') and data['total_equity'] > 0:
            ratios['debt_ratio'] = round(data['total_liabilities'] / data['total_equity'] * 100, 2)

        # 유동비율 = 유동자산 / 유동부채 * 100
        if data.get('current_assets') and data.get('current_liabilities') and data['current_liabilities'] > 0:
            ratios['liquidity_ratio'] = round(
                data['current_assets'] / data['current_liabilities'] * 100, 2
            )

        # 영업이익률 = 영업이익 / 매출액 * 100
        if data.get('operating_income') and data.get('revenue') and data['revenue'] > 0:
            ratios['operating_margin'] = round(data['operating_income'] / data['revenue'] * 100, 2)

        return ratios

    def ensure_data_exists(self, stock_code: str, stock_name: str = "") -> bool:
        """
        DB에 데이터가 없으면 DART에서 가져와 저장
        Returns: 데이터 존재 여부
        """
        existing = self.get_from_db(stock_code, years=1)

        if existing:
            return True

        # DB에 없으면 DART에서 가져오기
        current_year = datetime.now().year
        latest_year = current_year - 2  # 가장 최신 확정 사업보고서 연도

        # 최근 3년 사업보고서 가져오기
        for year in range(latest_year - 2, latest_year + 1):
            data = self.fetch_from_dart(stock_code, year, 'annual')
            if data:
                self.save_to_db(stock_code, stock_name, year, 'annual', data)

        return bool(self.get_from_db(stock_code, years=1))

    def get_fundamental_analysis(self, stock_code: str, stock_name: str = "") -> Dict[str, Any]:
        """
        펀더멘탈 종합 분석 결과 반환 (DB 우선, 없으면 DART 조회)
        """
        # DB에 데이터 확보
        self.ensure_data_exists(stock_code, stock_name)

        # DB에서 조회
        db_data = self.get_from_db(stock_code, years=3)

        if not db_data:
            return {
                'code': stock_code,
                'name': stock_name,
                'level': '보통',
                'score': 50,
                'comment': '재무데이터를 조회할 수 없습니다.',
                'roe': None,
                'debt_ratio': None,
                'liquidity_ratio': None,
                'operating_margin': None,
                'financials': [],
            }

        # 최신 데이터에서 비율 가져오기
        latest = db_data[0]

        # 연도별 데이터 정리 (중복 제거, 사업보고서 우선)
        seen_years = set()
        financials = []
        for row in db_data:
            year = row['year']
            if year not in seen_years:
                seen_years.add(year)
                financials.append({
                    'year': str(year),
                    'revenue': row['revenue'],
                    'operating_income': row['operating_income'],
                    'net_income': row['net_income'],
                    'report_type': row['report_type'],
                })

        # 연도순 정렬
        financials.sort(key=lambda x: x['year'])

        # YOY 계산
        for i in range(1, len(financials)):
            prev_rev = financials[i-1].get('revenue')
            curr_rev = financials[i].get('revenue')
            if prev_rev and curr_rev and prev_rev > 0:
                financials[i]['revenue_yoy'] = round((curr_rev - prev_rev) / prev_rev * 100, 1)

        # 점수 계산
        ratios = {
            'roe': latest['roe'],
            'debt_ratio': latest['debt_ratio'],
            'liquidity_ratio': latest['liquidity_ratio'],
            'operating_margin': latest['operating_margin'],
        }
        score = self._calculate_score(ratios, financials)
        level = "높음" if score >= 70 else "보통" if score >= 40 else "낮음"

        # 코멘트 생성
        comment = self._generate_comment(stock_name, ratios, financials, level)

        return {
            'code': stock_code,
            'name': stock_name or latest.get('stock_name', ''),
            'level': level,
            'score': score,
            'comment': comment,
            'roe': latest['roe'],
            'debt_ratio': latest['debt_ratio'],
            'liquidity_ratio': latest['liquidity_ratio'],
            'operating_margin': latest['operating_margin'],
            'financials': financials,
        }

    def _calculate_score(self, ratios: Dict, financials: List[Dict]) -> int:
        """펀더멘탈 점수 계산 (0-100)"""
        score = 50

        roe = ratios.get('roe')
        if roe is not None:
            if roe >= 15:
                score += 25
            elif roe >= 10:
                score += 20
            elif roe >= 5:
                score += 10
            elif roe >= 0:
                score += 5
            else:
                score -= 10

        debt_ratio = ratios.get('debt_ratio')
        if debt_ratio is not None:
            if debt_ratio < 50:
                score += 25
            elif debt_ratio < 100:
                score += 20
            elif debt_ratio < 150:
                score += 10
            elif debt_ratio < 200:
                score += 5
            else:
                score -= 10

        op_margin = ratios.get('operating_margin')
        if op_margin is not None:
            if op_margin >= 15:
                score += 15
            elif op_margin >= 10:
                score += 12
            elif op_margin >= 5:
                score += 8
            elif op_margin > 0:
                score += 5
            else:
                score -= 10

        if financials and len(financials) >= 2:
            latest_yoy = financials[-1].get('revenue_yoy')
            if latest_yoy is not None:
                if latest_yoy >= 20:
                    score += 10
                elif latest_yoy >= 10:
                    score += 7
                elif latest_yoy >= 0:
                    score += 5
                else:
                    score -= 5

        return max(0, min(100, score))

    def _generate_comment(self, stock_name: str, ratios: Dict,
                          financials: List[Dict], level: str) -> str:
        """AI 펀더멘탈 분석 코멘트 생성"""
        if not financials:
            return f"{stock_name}의 재무데이터를 조회할 수 없습니다."

        comments = []

        roe = ratios.get('roe')
        if roe is not None:
            if roe >= 15:
                comments.append(f"ROE {roe:.1f}%로 자기자본 수익성이 우수합니다")
            elif roe >= 10:
                comments.append(f"ROE {roe:.1f}%로 양호한 수익성을 보입니다")
            elif roe >= 0:
                comments.append(f"ROE {roe:.1f}%로 수익성 개선이 필요합니다")
            else:
                comments.append(f"ROE {roe:.1f}%로 적자 상태입니다")

        debt_ratio = ratios.get('debt_ratio')
        if debt_ratio is not None:
            if debt_ratio < 100:
                comments.append(f"부채비율 {debt_ratio:.0f}%로 재무구조가 안정적입니다")
            elif debt_ratio < 200:
                comments.append(f"부채비율 {debt_ratio:.0f}%로 보통 수준입니다")
            else:
                comments.append(f"부채비율 {debt_ratio:.0f}%로 재무 위험이 있습니다")

        if len(financials) >= 2 and financials[-1].get('revenue_yoy') is not None:
            yoy = financials[-1]['revenue_yoy']
            if yoy >= 10:
                comments.append(f"매출이 전년 대비 {yoy:.1f}% 성장했습니다")
            elif yoy >= 0:
                comments.append(f"매출이 {yoy:.1f}% 소폭 증가했습니다")
            else:
                comments.append(f"매출이 {abs(yoy):.1f}% 감소했습니다")

        if level == "높음":
            summary = "전반적으로 재무건전성이 우수하여 안정적인 투자가 가능합니다."
        elif level == "보통":
            summary = "재무상태가 보통 수준으로 추가적인 분석이 필요합니다."
        else:
            summary = "재무 지표가 부정적으로 신중한 투자 판단이 요구됩니다."

        if comments:
            return ". ".join(comments) + ". " + summary
        return summary

    def update_stock_reports(self, stock_code: str, stock_name: str = ""):
        """
        특정 종목의 모든 보고서 업데이트 (분기/반기/사업보고서)
        새로 공시된 보고서만 가져옴
        """
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 조회할 연도/보고서 목록 결정
        reports_to_fetch = []

        for year in range(current_year - 2, current_year + 1):
            for report_type, info in REPORT_TYPES.items():
                # 공시 시점 체크 (해당 연도의 보고서가 공시되었는지)
                if year == current_year:
                    if current_month < info['month']:
                        continue
                elif year == current_year - 1:
                    # 작년 보고서는 올해 공시됨
                    if info['month'] > current_month:
                        continue

                reports_to_fetch.append((year, report_type))

        # DB에 없는 것만 가져오기
        for year, report_type in reports_to_fetch:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM fundamental_data
                    WHERE stock_code = ? AND year = ? AND report_type = ?
                """, (stock_code, year, report_type))

                if cursor.fetchone():
                    continue  # 이미 있음

            # DART에서 가져오기
            print(f"[DART] {stock_code} {year}년 {report_type} 조회 중...")
            data = self.fetch_from_dart(stock_code, year, report_type)
            if data:
                self.save_to_db(stock_code, stock_name, year, report_type, data)
                print(f"[DART] {stock_code} {year}년 {report_type} 저장 완료")


    # ============================================================
    # V3.5 신규: 5% 대량보유 공시 및 CB/BW 조회
    # ============================================================

    def get_major_shareholders(self, stock_code: str, days: int = 90) -> List[Dict]:
        """
        5% 대량보유 공시 조회 (최근 N일)

        OpenDartReader의 major_shareholders() 사용

        Args:
            stock_code: 종목코드 (6자리)
            days: 조회 기간 (기본 90일)

        Returns:
            [
                {
                    'name': 보고자명,
                    'ownership_pct': 보유 비율 (%),
                    'change_pct': 변동 비율 (%),
                    'purpose': 보유 목적 ('management' | 'investment' | 'other'),
                    'report_date': 보고일,
                    'shares': 보유 주식수,
                }
            ]
        """
        result = []

        try:
            corp_code = self.get_corp_code(stock_code)
            if not corp_code:
                return result

            # 날짜 범위 설정
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            # DART API 호출 - 대량보유 상황보고
            # OpenDartReader의 major_shareholders() 메서드 사용
            df = self.dart.major_shareholders(corp_code, start_date, end_date)

            if df is None or df.empty:
                return result

            for _, row in df.iterrows():
                # 보유 목적 분류
                purpose_raw = str(row.get('stkhldr_motive', '')).lower()
                if '경영참가' in purpose_raw or '경영권' in purpose_raw:
                    purpose = 'management'
                elif '단순투자' in purpose_raw:
                    purpose = 'investment'
                else:
                    purpose = 'other'

                # 보유 비율 파싱
                ownership_str = str(row.get('trmend_posesn_stock_qota_rt', '0'))
                try:
                    ownership_pct = float(ownership_str.replace('%', '').replace(',', ''))
                except:
                    ownership_pct = 0

                # 변동 비율 파싱
                change_str = str(row.get('change_stock_qota_rt', '0'))
                try:
                    change_pct = float(change_str.replace('%', '').replace(',', ''))
                except:
                    change_pct = 0

                # 보유 주식수
                shares_str = str(row.get('trmend_posesn_stock_co', '0'))
                try:
                    shares = int(shares_str.replace(',', ''))
                except:
                    shares = 0

                result.append({
                    'name': row.get('repror', ''),
                    'ownership_pct': ownership_pct,
                    'change_pct': change_pct,
                    'purpose': purpose,
                    'report_date': row.get('rcept_dt', ''),
                    'shares': shares,
                })

        except Exception as e:
            print(f"5% 공시 조회 실패 ({stock_code}): {e}")

        return result

    def get_convertible_bonds(self, stock_code: str, days: int = 365) -> List[Dict]:
        """
        CB/BW (전환사채/신주인수권부사채) 공시 조회

        Args:
            stock_code: 종목코드 (6자리)
            days: 조회 기간 (기본 365일)

        Returns:
            [
                {
                    'type': 'CB' | 'BW',
                    'conversion_price': 전환가액,
                    'amount': 발행 금액 (억원),
                    'maturity_date': 만기일,
                    'issue_date': 발행일,
                    'description': 상세 내용,
                }
            ]
        """
        result = []

        try:
            corp_code = self.get_corp_code(stock_code)
            if not corp_code:
                return result

            # 날짜 범위 설정
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            # DART 공시 검색 - 전환사채, 신주인수권부사채 키워드
            # OpenDartReader의 list() 메서드로 공시 목록 조회
            keywords = ['전환사채', '신주인수권부사채', 'CB', 'BW']

            for keyword in keywords:
                try:
                    df = self.dart.list(corp_code, start=start_date, end=end_date, kind='A')

                    if df is None or df.empty:
                        continue

                    # 키워드가 포함된 공시 필터링
                    mask = df['report_nm'].str.contains(keyword, na=False)
                    filtered = df[mask]

                    for _, row in filtered.iterrows():
                        # CB/BW 타입 판별
                        report_name = str(row.get('report_nm', ''))
                        if '전환사채' in report_name or 'CB' in report_name.upper():
                            cb_type = 'CB'
                        elif '신주인수권' in report_name or 'BW' in report_name.upper():
                            cb_type = 'BW'
                        else:
                            continue

                        # 중복 체크 (같은 날짜 + 같은 타입)
                        issue_date = row.get('rcept_dt', '')
                        if any(r['issue_date'] == issue_date and r['type'] == cb_type for r in result):
                            continue

                        result.append({
                            'type': cb_type,
                            'conversion_price': 0,  # 상세 공시에서 추출 필요
                            'amount': 0,  # 상세 공시에서 추출 필요
                            'maturity_date': '',
                            'issue_date': issue_date,
                            'description': report_name,
                        })

                except Exception:
                    continue

        except Exception as e:
            print(f"CB/BW 공시 조회 실패 ({stock_code}): {e}")

        return result

    def get_disclosure_data_for_scoring(self, stock_code: str, current_price: float = 0) -> Dict:
        """
        V3.5 스코어링을 위한 공시 데이터 종합 조회

        Args:
            stock_code: 종목코드
            current_price: 현재가 (CB/BW 오버행 계산용)

        Returns:
            {
                'major_shareholders': [...],
                'cb_bw': [...],
                'current_price': float,
            }
        """
        return {
            'major_shareholders': self.get_major_shareholders(stock_code, days=90),
            'cb_bw': self.get_convertible_bonds(stock_code, days=365),
            'current_price': current_price,
        }


def get_dart_service() -> DartService:
    return DartService()


# 편의 함수: V3.5 스코어링용 공시 데이터 조회
def get_disclosure_data(stock_code: str, current_price: float = 0) -> Dict:
    """
    V3.5 스코어링을 위한 공시 데이터 조회 (편의 함수)

    Args:
        stock_code: 종목코드
        current_price: 현재가

    Returns:
        disclosure_data 딕셔너리 (V3.5 calculate_score_v3_5()에 전달)
    """
    service = get_dart_service()
    return service.get_disclosure_data_for_scoring(stock_code, current_price)
