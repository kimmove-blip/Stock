"""
이메일 발송 모듈
스크리닝 결과를 이메일로 전송
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class EmailSender:
    """이메일 발송 클래스"""

    def __init__(self, use_db_subscribers=False):
        # 환경변수에서 설정 로드
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL", "")
        self.sender_password = os.getenv("SENDER_PASSWORD", "")  # 앱 비밀번호

        # DB 구독자 목록 또는 환경변수 수신자 목록
        if use_db_subscribers:
            self.recipient_emails = self._get_db_subscribers()
        else:
            self.recipient_emails = os.getenv("RECIPIENT_EMAILS", "").split(",")

    def _get_db_subscribers(self):
        """DB에서 이메일 구독자 목록 조회"""
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            subscribers = db.get_email_subscribers()
            # 환경변수의 기본 수신자도 포함
            env_recipients = os.getenv("RECIPIENT_EMAILS", "").split(",")
            all_recipients = list(set(subscribers + [e.strip() for e in env_recipients if e.strip()]))
            return all_recipients if all_recipients else [""]
        except Exception as e:
            print(f"[이메일] DB 구독자 조회 실패: {e}")
            return os.getenv("RECIPIENT_EMAILS", "").split(",")

    def is_configured(self):
        """이메일 설정이 완료되었는지 확인"""
        return bool(self.sender_email and self.sender_password and self.recipient_emails and self.recipient_emails[0])

    def send_report(self, subject, body_html, attachments=None):
        """
        리포트 이메일 발송

        Args:
            subject: 이메일 제목
            body_html: HTML 형식의 본문
            attachments: 첨부파일 경로 리스트 (선택)
        """
        if not self.is_configured():
            print("[이메일] 설정이 완료되지 않았습니다. .env 파일을 확인하세요.")
            return False

        try:
            # 이메일 메시지 생성
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = ", ".join(self.recipient_emails)

            # HTML 본문 추가
            html_part = MIMEText(body_html, 'html', 'utf-8')
            msg.attach(html_part)

            # 첨부파일 추가
            if attachments:
                for file_path in attachments:
                    if Path(file_path).exists():
                        self._attach_file(msg, file_path)

            # SMTP 서버 연결 및 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            print(f"[이메일] 발송 완료: {', '.join(self.recipient_emails)}")
            return True

        except Exception as e:
            print(f"[이메일] 발송 실패: {e}")
            return False

    def _attach_file(self, msg, file_path):
        """파일 첨부"""
        file_path = Path(file_path)

        with open(file_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="{file_path.name}"'
        )
        msg.attach(part)


def create_email_body(results, date_str=None):
    """
    스크리닝 결과로 이메일 본문 HTML 생성
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 상위 100개로 제한
    results = results[:100]

    # 상위 20개 종목 테이블 생성
    top_20 = results[:20]
    rows_html = ""

    for i, r in enumerate(top_20, 1):
        change = r.get('change_pct', 0)
        change_color = '#c53030' if change >= 0 else '#2b6cb0'
        change_sign = '+' if change >= 0 else ''

        rows_html += f"""
        <tr>
            <td style="text-align:center;">{i}</td>
            <td style="text-align:center;">{r['code']}</td>
            <td>{r['name']}</td>
            <td style="text-align:center;">{r['market']}</td>
            <td style="text-align:center;font-weight:bold;">{r['score']}</td>
            <td style="text-align:right;">{r.get('close', 0):,.0f}</td>
            <td style="text-align:right;color:{change_color};">{change_sign}{change:.2f}%</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }}
            h1 {{
                color: #1a365d;
                border-bottom: 3px solid #2c5282;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #2c5282;
                margin-top: 30px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
            }}
            th, td {{
                border: 1px solid #cbd5e0;
                padding: 10px;
                text-align: left;
            }}
            th {{
                background-color: #2c5282;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f7fafc;
            }}
            .disclaimer {{
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
            }}
            .summary {{
                background-color: #ebf8ff;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .criteria {{
                background-color: #f0fff4;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .criteria ul {{
                margin: 10px 0;
                padding-left: 20px;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e2e8f0;
                font-size: 12px;
                color: #718096;
            }}
        </style>
    </head>
    <body>
        <h1>Kim's AI - 내일의 관심 종목 TOP 100</h1>
        <p>분석일: {date_str}</p>

        <div class="disclaimer">
            <strong>투자 유의사항</strong><br><br>
            본 자료는 기술적 분석에 기반한 참고 자료이며, 투자 권유가 아닙니다.<br>
            투자 판단에 따른 손익은 전적으로 투자자 본인에게 귀속됩니다.<br>
            <br>
            <strong>본 자료의 무단 전재 및 재배포를 금지합니다.</strong>
        </div>

        <div class="summary">
            <strong>요약</strong><br>
            총 선정 종목: {len(results)}개<br>
            점수 범위: {min(r['score'] for r in results):.0f} ~ {max(r['score'] for r in results):.0f}점
        </div>

        <div class="criteria">
            <strong>선정 기준</strong>
            <ul>
                <li>시가총액: 300억 ~ 1조원</li>
                <li>거래대금: 3억원 이상</li>
                <li>주가: 10만원 이하</li>
                <li>분석 방법: 18개 기술적 지표 + 캔들패턴 종합</li>
            </ul>
        </div>

        <h2>상위 20개 종목</h2>
        <table>
            <thead>
                <tr>
                    <th style="width:50px;">순위</th>
                    <th style="width:80px;">종목코드</th>
                    <th>종목명</th>
                    <th style="width:80px;">시장</th>
                    <th style="width:60px;">점수</th>
                    <th style="width:100px;">현재가</th>
                    <th style="width:80px;">등락률</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <p>전체 {len(results)}개 종목의 상세 분석 결과는 첨부된 PDF 파일을 확인하세요.</p>

        <div class="footer">
            <p>Generated by Kim's AI v1.0 | {date_str}</p>
            <p>본 분석은 기술적 지표 기반이며, 투자 판단의 참고 자료로만 활용하시기 바랍니다.</p>
            <p><strong>무단 전재 및 재배포를 금지합니다.</strong></p>
        </div>
    </body>
    </html>
    """

    return html


def send_daily_report(results, pdf_path=None):
    """
    일일 리포트 발송

    Args:
        results: 스크리닝 결과 리스트
        pdf_path: PDF 첨부파일 경로
    """
    sender = EmailSender(use_db_subscribers=True)

    if not sender.is_configured():
        print("[이메일] 설정이 필요합니다. .env 파일에 다음 항목을 추가하세요:")
        print("  SMTP_SERVER=smtp.gmail.com")
        print("  SMTP_PORT=587")
        print("  SENDER_EMAIL=your_email@gmail.com")
        print("  SENDER_PASSWORD=your_app_password")
        print("  RECIPIENT_EMAILS=recipient1@email.com,recipient2@email.com")
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[Kim's AI] 내일의 관심 종목 TOP 100 ({date_str})"

    body = create_email_body(results, date_str)

    attachments = []
    if pdf_path and Path(pdf_path).exists():
        attachments.append(pdf_path)

    return sender.send_report(subject, body, attachments)


def send_test_report(test_email=None):
    """
    테스트 리포트 발송 (특정 이메일로만)

    Args:
        test_email: 테스트 수신 이메일 (None이면 환경변수 첫 번째 수신자)
    """
    import json

    # 최신 TOP100 JSON 파일 로드
    output_dir = Path(__file__).parent / "output"
    json_files = sorted(output_dir.glob("top100_*.json"), reverse=True)

    if not json_files:
        print("[테스트] TOP100 파일이 없습니다.")
        return False

    with open(json_files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data.get('stocks', data.get('items', []))[:100]

    if not results:
        print("[테스트] 결과 데이터가 없습니다.")
        return False

    # 발송자 설정
    sender = EmailSender(use_db_subscribers=False)

    if not sender.sender_email or not sender.sender_password:
        print("[테스트] 이메일 설정이 필요합니다.")
        return False

    # 테스트 수신자 설정
    if test_email:
        sender.recipient_emails = [test_email]
    else:
        # 첫 번째 수신자만 사용
        sender.recipient_emails = [sender.recipient_emails[0]]

    print(f"[테스트] 수신자: {sender.recipient_emails[0]}")

    # 이메일 발송
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[Kim's AI] 내일의 관심 종목 TOP 100 ({date_str}) - 테스트"
    body = create_email_body(results, date_str)

    # PDF 첨부
    pdf_files = sorted(output_dir.glob("top100_*.pdf"), reverse=True)
    attachments = [str(pdf_files[0])] if pdf_files else []

    return sender.send_report(subject, body, attachments)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 테스트 모드
        test_email = sys.argv[2] if len(sys.argv) > 2 else None
        send_test_report(test_email)
    else:
        # 기본 정보 출력
        sender = EmailSender()
        print(f"이메일 설정 완료: {sender.is_configured()}")
        print(f"SMTP 서버: {sender.smtp_server}")
        print(f"발신자: {sender.sender_email}")
        print(f"수신자: {sender.recipient_emails}")
