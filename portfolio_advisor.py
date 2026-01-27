#!/usr/bin/env python3
"""
보유 주식 포트폴리오 분석기
- 보유 주식의 매도/보유/추가매수 의견 제공
- Excel/CSV 입력, PDF/Excel 출력

사용법:
    python portfolio_advisor.py                    # 기본 실행
    python portfolio_advisor.py -i my_stocks.xlsx  # 입력 파일 지정
    python portfolio_advisor.py --email            # 이메일 발송
"""

import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import json

from technical_analyst import TechnicalAnalyst
from config import get_signal_kr, OUTPUT_DIR
from email_sender import EmailSender


class PortfolioAdvisor:
    """보유 주식 분석 및 의견 제공"""

    def __init__(self):
        self.analyst = TechnicalAnalyst()
        self.portfolio = None
        self.analysis_results = []

    def load_portfolio(self, filepath):
        """
        보유 주식 파일 로드
        필수 컬럼: 종목코드, 매수가, 수량
        선택 컬럼: 종목명, 매수일
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")

        # 파일 형식에 따라 로드
        if filepath.suffix.lower() in ['.xlsx', '.xls']:
            # '잔고' 시트가 있으면 사용, 없으면 첫 번째 시트 사용
            xl = pd.ExcelFile(filepath)
            if '잔고' in xl.sheet_names:
                df = pd.read_excel(filepath, sheet_name='잔고')
            else:
                df = pd.read_excel(filepath)
        elif filepath.suffix.lower() == '.csv':
            df = pd.read_csv(filepath, encoding='utf-8-sig')
        else:
            raise ValueError(f"지원하지 않는 파일 형식: {filepath.suffix}")

        # 컬럼명 정규화
        df.columns = df.columns.str.strip()

        # 필수 컬럼 확인
        required_cols = ['종목코드']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"필수 컬럼이 없습니다: {col}")

        # 종목코드 6자리 맞추기
        df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)

        # 매수가가 없으면 0으로 설정
        if '매수가' not in df.columns:
            df['매수가'] = 0

        # 잔고수량 컬럼 처리 (잔고수량 → 수량으로 매핑)
        if '잔고수량' in df.columns:
            df['수량'] = df['잔고수량']
        elif '수량' not in df.columns:
            df['수량'] = 1

        # 최종매수일 → 매수일 매핑
        if '최종매수일' in df.columns and '매수일' not in df.columns:
            df['매수일'] = df['최종매수일']

        # 잔고수량 0인 항목 제외
        before_count = len(df)
        df = df[df['수량'] > 0]
        excluded = before_count - len(df)
        if excluded > 0:
            print(f"[필터] 잔고수량 0인 {excluded}개 종목 제외")

        self.portfolio = df
        print(f"[로드] {len(df)}개 종목 로드 완료")
        return df

    def analyze_stock(self, code, buy_price=0):
        """단일 종목 분석"""
        try:
            # 주가 데이터 수집
            df = self.analyst.get_ohlcv(code, days=365)
            if df is None or len(df) < 60:
                return None

            # 기술적 분석
            result = self.analyst.analyze_full(df)
            if result is None:
                return None

            # 현재가
            current_price = df.iloc[-1]['Close']

            # 수익률 계산
            if buy_price > 0:
                profit_rate = ((current_price - buy_price) / buy_price) * 100
            else:
                profit_rate = 0

            # 의견 결정
            opinion, reason = self._decide_opinion(result, profit_rate)

            return {
                'current_price': current_price,
                'profit_rate': profit_rate,
                'score': result['score'],
                'signals': result['signals'],
                'patterns': result['patterns'],
                'indicators': result['indicators'],
                'opinion': opinion,
                'reason': reason
            }

        except Exception as e:
            print(f"    [오류] {code}: {e}")
            return None

    def _decide_opinion(self, analysis, profit_rate):
        """
        매도/보유/추가매수 의견 결정

        기준:
        1. 기술적 점수 + 신호
        2. 현재 수익률
        3. 위험 신호 여부
        4. 점수 기반 매도 신호 필터링 (점수 >= 70이면 매도 신호 무시)
        """
        score = analysis['score']
        signals = analysis['signals'] or []

        # 위험 신호
        danger_signals = [
            'DEAD_CROSS_20_60', 'MACD_DEAD_CROSS', 'RSI_OVERBOUGHT',
            'BEARISH_ENGULFING', 'EVENING_STAR', 'SUPERTREND_SELL'
        ]

        # 긍정 신호
        positive_signals = [
            'GOLDEN_CROSS_20_60', 'MACD_GOLDEN_CROSS', 'RSI_OVERSOLD',
            'BULLISH_ENGULFING', 'MORNING_STAR', 'SUPERTREND_BUY',
            'MA_ALIGNED', 'BB_LOWER_BOUNCE'
        ]

        has_danger = any(s in signals for s in danger_signals)
        has_positive = any(s in signals for s in positive_signals)
        danger_count = sum(1 for s in signals if s in danger_signals)
        positive_count = sum(1 for s in signals if s in positive_signals)

        # 1. 손절 권장 (점수와 무관하게 항상 적용)
        if profit_rate < -15 and score < 40:
            return '손절', f'손실률 {profit_rate:.1f}%, 반등 신호 약함'

        if profit_rate < -20:
            return '손절검토', f'손실률 {profit_rate:.1f}%, 추가 하락 위험'

        # 2. 점수 기반 필터링: 점수 >= 70이면 매도 신호 무시
        if score >= 70:
            if has_positive or profit_rate < 0:
                return '추가매수', f'기술적 점수 우수({score}점), 반등 예상'
            return '보유', f'점수 우수({score}점), 추세 유지 중'

        # 3. 과열 주의: 위험 신호 2개 이상 (점수 < 70)
        if danger_count >= 2:
            return '과열 주의', '위험 신호 다수 감지'

        # 4. 주의 권장 (점수 < 70)
        if has_danger:
            return '주의', '하락 신호 감지'

        if score < 30:
            return '주의', f'기술적 점수 낮음({score}점)'

        # 5. 추가매수
        if has_positive and profit_rate < -5 and score >= 50:
            return '추가매수', f'긍정 신호 감지, 저점 매수 기회'

        # 6. 보유 (기본)
        if score >= 50:
            if profit_rate > 0:
                return '보유', f'점수 양호({score}점), 추세 유지 중'
            else:
                return '보유', f'점수 양호({score}점), 반등 대기'

        if 30 <= score < 50:
            return '관망', f'점수 보통({score}점), 추세 확인 필요'

        return '보유', '추가 분석 필요'

    def analyze_portfolio(self):
        """전체 포트폴리오 분석"""
        if self.portfolio is None:
            raise ValueError("먼저 포트폴리오를 로드하세요")

        print(f"\n[분석] {len(self.portfolio)}개 종목 분석 시작...")
        print("-" * 50)

        results = []

        for idx, row in self.portfolio.iterrows():
            code = row['종목코드']
            name = row.get('종목명', code)
            buy_price = float(row.get('매수가', 0))
            quantity = int(row.get('수량', 1))

            print(f"  분석 중: {name} ({code})...", end=' ')

            analysis = self.analyze_stock(code, buy_price)

            if analysis:
                result = {
                    'code': code,
                    'name': name,
                    'buy_price': buy_price,
                    'quantity': quantity,
                    'current_price': analysis['current_price'],
                    'profit_rate': analysis['profit_rate'],
                    'profit_amount': (analysis['current_price'] - buy_price) * quantity if buy_price > 0 else 0,
                    'score': analysis['score'],
                    'opinion': analysis['opinion'],
                    'reason': analysis['reason'],
                    'signals': analysis['signals'],
                    'patterns': analysis['patterns'],
                    'indicators': analysis['indicators']
                }
                results.append(result)
                print(f"→ {analysis['opinion']} (점수: {analysis['score']})")
            else:
                print("→ 분석 실패")

        self.analysis_results = results
        print("-" * 50)
        print(f"[완료] {len(results)}개 종목 분석 완료")

        return results

    def get_summary(self):
        """포트폴리오 요약"""
        if not self.analysis_results:
            return None

        total_investment = sum(r['buy_price'] * r['quantity'] for r in self.analysis_results if r['buy_price'] > 0)
        total_current = sum(r['current_price'] * r['quantity'] for r in self.analysis_results)
        total_profit = sum(r['profit_amount'] for r in self.analysis_results)

        # 의견별 분류
        opinions = {}
        for r in self.analysis_results:
            op = r['opinion']
            if op not in opinions:
                opinions[op] = []
            opinions[op].append(r)

        return {
            'total_stocks': len(self.analysis_results),
            'total_investment': total_investment,
            'total_current': total_current,
            'total_profit': total_profit,
            'total_profit_rate': (total_profit / total_investment * 100) if total_investment > 0 else 0,
            'opinions': opinions
        }

    def save_excel(self, output_path=None):
        """Excel 파일로 저장"""
        if not self.analysis_results:
            print("[오류] 분석 결과가 없습니다")
            return None

        if output_path is None:
            date_str = datetime.now().strftime("%Y%m%d")
            output_path = Path(OUTPUT_DIR) / f"portfolio_advice_{date_str}.xlsx"

        # DataFrame 생성
        rows = []
        for r in self.analysis_results:
            signals_kr = [get_signal_kr(s) for s in (r['signals'] or [])[:3]]

            rows.append({
                '종목코드': r['code'],
                '종목명': r['name'],
                '매수가': r['buy_price'],
                '현재가': int(r['current_price']),
                '수량': r['quantity'],
                '수익률(%)': round(r['profit_rate'], 2),
                '평가손익': int(r['profit_amount']),
                '기술점수': r['score'],
                '의견': r['opinion'],
                '사유': r['reason'],
                '주요신호': ' | '.join(signals_kr)
            })

        df = pd.DataFrame(rows)

        # Excel 저장 (스타일 적용)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='포트폴리오 분석', index=False)

            # 요약 시트 추가
            summary = self.get_summary()
            if summary:
                summary_data = {
                    '항목': ['총 종목수', '총 투자금', '총 평가금', '총 손익', '총 수익률(%)'],
                    '값': [
                        summary['total_stocks'],
                        f"{summary['total_investment']:,.0f}원",
                        f"{summary['total_current']:,.0f}원",
                        f"{summary['total_profit']:,.0f}원",
                        f"{summary['total_profit_rate']:.2f}%"
                    ]
                }

                # 의견별 종목 수
                for op, stocks in summary['opinions'].items():
                    summary_data['항목'].append(f'{op} 종목수')
                    summary_data['값'].append(len(stocks))

                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='요약', index=False)

        print(f"[저장] Excel: {output_path}")
        return output_path

    def save_pdf(self, output_path=None):
        """PDF 파일로 저장"""
        if not self.analysis_results:
            print("[오류] 분석 결과가 없습니다")
            return None

        if output_path is None:
            date_str = datetime.now().strftime("%Y%m%d")
            output_path = Path(OUTPUT_DIR) / f"portfolio_advice_{date_str}.pdf"

        html_content = self._create_html_report()

        try:
            from weasyprint import HTML, CSS

            css = CSS(string='''
                @page { size: A4; margin: 1.5cm; }
                body { font-family: 'Malgun Gothic', sans-serif; font-size: 10pt; }
                h1 { color: #1a365d; border-bottom: 2px solid #2c5282; padding-bottom: 10px; }
                h2 { color: #2c5282; margin-top: 20px; }
                table { border-collapse: collapse; width: 100%; margin: 15px 0; }
                th, td { border: 1px solid #cbd5e0; padding: 8px; text-align: left; }
                th { background-color: #2c5282; color: white; }
                tr:nth-child(even) { background-color: #f7fafc; }
                .sell { color: #c53030; font-weight: bold; }
                .buy { color: #2f855a; font-weight: bold; }
                .hold { color: #744210; }
                .summary-box { background: #ebf8ff; padding: 12px; border-radius: 8px; margin: 15px 0; font-size: 9pt; }
                .warning { background: #fff5f5; border-left: 4px solid #c53030; padding: 10px; margin: 10px 0; }
                .positive { background: #f0fff4; border-left: 4px solid #2f855a; padding: 10px; margin: 10px 0; }
            ''')

            HTML(string=html_content).write_pdf(output_path, stylesheets=[css])
            print(f"[저장] PDF: {output_path}")
            return output_path

        except ImportError:
            print("[오류] weasyprint가 설치되지 않았습니다")
            return None

    def _create_html_report(self):
        """HTML 리포트 생성"""
        summary = self.get_summary()
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 의견별 색상
        opinion_class = {
            '강력매도': 'sell', '매도': 'sell', '손절': 'sell', '손절검토': 'sell',
            '추가매수': 'buy',
            '보유': 'hold', '관망': 'hold'
        }

        # 종목 테이블
        rows_html = ""
        for r in self.analysis_results:
            profit_color = '#c53030' if r['profit_rate'] < 0 else '#2f855a'
            op_class = opinion_class.get(r['opinion'], 'hold')
            signals_kr = [get_signal_kr(s) for s in (r['signals'] or [])[:2]]

            rows_html += f'''
            <tr>
                <td>{r['code']}</td>
                <td>{r['name']}</td>
                <td style="text-align:right;">{r['buy_price']:,.0f}</td>
                <td style="text-align:right;">{r['current_price']:,.0f}</td>
                <td style="text-align:right;color:{profit_color};">{r['profit_rate']:+.1f}%</td>
                <td style="text-align:center;">{r['score']}</td>
                <td class="{op_class}" style="text-align:center;">{r['opinion']}</td>
                <td style="font-size:9pt;">{r['reason']}</td>
            </tr>
            '''

        # 매도 권장 종목
        sell_stocks = [r for r in self.analysis_results if r['opinion'] in ['강력매도', '매도', '손절', '손절검토']]
        sell_html = ""
        if sell_stocks:
            sell_html = '<div class="warning"><strong>매도/손절 권장 종목:</strong><br>'
            for s in sell_stocks:
                sell_html += f"• {s['name']} ({s['opinion']}): {s['reason']}<br>"
            sell_html += '</div>'

        # 추가매수 권장 종목
        buy_stocks = [r for r in self.analysis_results if r['opinion'] == '추가매수']
        buy_html = ""
        if buy_stocks:
            buy_html = '<div class="positive"><strong>추가매수 고려 종목:</strong><br>'
            for s in buy_stocks:
                buy_html += f"• {s['name']} (점수: {s['score']}): {s['reason']}<br>"
            buy_html += '</div>'

        html = f'''
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"></head>
        <body>
            <h1>보유 주식 포트폴리오 분석</h1>
            <p>분석일시: {date_str}</p>

            <div class="summary-box">
                <strong>요약</strong> | {summary['total_stocks']}종목 | 투자 {summary['total_investment']:,.0f}원 | 평가 {summary['total_current']:,.0f}원 | 손익 {summary['total_profit']:+,.0f}원 ({summary['total_profit_rate']:+.1f}%)
            </div>

            {sell_html}
            {buy_html}

            <h2>종목별 분석</h2>
            <table>
                <thead>
                    <tr>
                        <th>코드</th>
                        <th>종목명</th>
                        <th>매수가</th>
                        <th>현재가</th>
                        <th>수익률</th>
                        <th>점수</th>
                        <th>의견</th>
                        <th>사유</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>

            <div style="margin-top:30px;font-size:9pt;color:#718096;">
                <p>※ 본 분석은 기술적 지표 기반이며, 투자 판단의 참고 자료로만 활용하시기 바랍니다.</p>
                <p>※ 실제 투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다.</p>
            </div>
        </body>
        </html>
        '''

        return html

    def send_email(self, pdf_path=None, excel_path=None):
        """이메일 발송"""
        sender = EmailSender()

        if not sender.is_configured():
            print("[이메일] 설정이 필요합니다. .env 파일을 확인하세요.")
            return False

        summary = self.get_summary()
        date_str = datetime.now().strftime("%Y-%m-%d")

        subject = f"[포트폴리오 분석] 보유 주식 의견 ({date_str})"

        # 이메일 본문
        body = f'''
        <html>
        <body style="font-family: 'Malgun Gothic', sans-serif;">
            <h2>보유 주식 포트폴리오 분석 결과</h2>
            <p>분석일: {date_str}</p>

            <div style="background:#ebf8ff;padding:15px;border-radius:8px;margin:15px 0;">
                <strong>요약</strong><br>
                총 {summary['total_stocks']}종목 |
                손익 {summary['total_profit']:+,.0f}원 ({summary['total_profit_rate']:+.1f}%)
            </div>

            <h3>의견 분포</h3>
            <ul>
        '''

        for op, stocks in summary['opinions'].items():
            body += f'<li><strong>{op}</strong>: {len(stocks)}종목'
            if stocks:
                names = [s['name'] for s in stocks[:3]]
                body += f' ({", ".join(names)}{"..." if len(stocks) > 3 else ""})'
            body += '</li>'

        body += '''
            </ul>
            <p>상세 분석 결과는 첨부 파일을 확인하세요.</p>

            <div style="margin-top:20px;font-size:11px;color:#718096;">
                ※ 본 분석은 기술적 지표 기반이며, 투자 판단의 참고 자료로만 활용하시기 바랍니다.
            </div>
        </body>
        </html>
        '''

        attachments = []
        if pdf_path and Path(pdf_path).exists():
            attachments.append(str(pdf_path))
        if excel_path and Path(excel_path).exists():
            attachments.append(str(excel_path))

        return sender.send_report(subject, body, attachments)


def create_sample_portfolio():
    """샘플 포트폴리오 파일 생성"""
    sample_data = {
        '종목코드': ['005930', '000660', '035420', '051910', '006400'],
        '종목명': ['삼성전자', 'SK하이닉스', 'NAVER', 'LG화학', '삼성SDI'],
        '매수가': [72000, 130000, 350000, 500000, 400000],
        '수량': [10, 5, 3, 2, 2],
        '매수일': ['2024-06-01', '2024-07-15', '2024-08-01', '2024-05-20', '2024-09-01']
    }

    df = pd.DataFrame(sample_data)
    sample_path = Path(OUTPUT_DIR) / 'my_portfolio_sample.xlsx'
    df.to_excel(sample_path, index=False)
    print(f"[샘플] 포트폴리오 샘플 파일 생성: {sample_path}")
    return sample_path


def main():
    parser = argparse.ArgumentParser(
        description="보유 주식 포트폴리오 분석 - 매도/보유/추가매수 의견 제공",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python portfolio_advisor.py                      # 샘플로 테스트
  python portfolio_advisor.py -i my_stocks.xlsx    # 내 포트폴리오 분석
  python portfolio_advisor.py -i my_stocks.csv --email  # 분석 후 이메일 발송
  python portfolio_advisor.py --create-sample      # 샘플 파일 생성
        """
    )

    parser.add_argument('-i', '--input', type=str, help='보유 주식 파일 경로 (Excel/CSV)')
    parser.add_argument('--email', action='store_true', help='이메일 발송')
    parser.add_argument('--create-sample', action='store_true', help='샘플 포트폴리오 파일 생성')
    parser.add_argument('--no-pdf', action='store_true', help='PDF 생성 안함')

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  보유 주식 포트폴리오 분석기")
    print("=" * 60)

    # 샘플 파일 생성
    if args.create_sample:
        create_sample_portfolio()
        return

    # 입력 파일 결정
    if args.input:
        input_path = args.input
    else:
        # 기본 경로에서 찾기
        default_paths = [
            Path(OUTPUT_DIR) / 'my_portfolio.xlsx',
            Path(OUTPUT_DIR) / 'my_portfolio.csv',
            Path('.') / 'my_portfolio.xlsx',
            Path('.') / 'my_portfolio.csv',
        ]

        input_path = None
        for p in default_paths:
            if p.exists():
                input_path = p
                break

        if input_path is None:
            # 샘플로 테스트
            print("\n[안내] 포트폴리오 파일이 없어 샘플로 테스트합니다.")
            input_path = create_sample_portfolio()

    try:
        advisor = PortfolioAdvisor()

        # 포트폴리오 로드
        advisor.load_portfolio(input_path)

        # 분석 실행
        advisor.analyze_portfolio()

        # 요약 출력
        summary = advisor.get_summary()
        print("\n" + "=" * 60)
        print("  분석 결과 요약")
        print("=" * 60)
        print(f"\n  총 종목수: {summary['total_stocks']}개")
        print(f"  총 투자금: {summary['total_investment']:,.0f}원")
        print(f"  총 평가금: {summary['total_current']:,.0f}원")
        print(f"  총 손익: {summary['total_profit']:+,.0f}원 ({summary['total_profit_rate']:+.1f}%)")
        print("\n  [의견별 분류]")
        for op, stocks in summary['opinions'].items():
            stock_names = [s['name'] for s in stocks]
            print(f"  - {op}: {len(stocks)}종목 ({', '.join(stock_names[:3])}{'...' if len(stocks) > 3 else ''})")

        # 파일 저장
        print("\n" + "-" * 60)
        excel_path = advisor.save_excel()

        pdf_path = None
        if not args.no_pdf:
            pdf_path = advisor.save_pdf()

        # 이메일 발송
        if args.email:
            advisor.send_email(pdf_path=pdf_path, excel_path=excel_path)

        print("\n" + "=" * 60)
        print(f"  완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n[오류] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
