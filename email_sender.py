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

    def __init__(self):
        # 환경변수에서 설정 로드
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL", "")
        self.sender_password = os.getenv("SENDER_PASSWORD", "")  # 앱 비밀번호
        self.recipient_emails = os.getenv("RECIPIENT_EMAILS", "").split(",")

    def is_configured(self):
        """이메일 설정이 완료되었는지 확인"""
        return bool(self.sender_email and self.sender_password and self.recipient_emails[0])

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
            .summary {{
                background-color: #ebf8ff;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
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
        <h1>내일 관심 종목 TOP 100</h1>
        <p>분석일: {date_str}</p>

        <div class="summary">
            <strong>요약</strong><br>
            총 선정 종목: {len(results)}개<br>
            점수 범위: {min(r['score'] for r in results):.0f} ~ {max(r['score'] for r in results):.0f}점
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
            <p>이 메일은 자동 발송되었습니다.</p>
            <p>※ 본 분석은 기술적 지표 기반이며, 투자 판단의 참고 자료로만 활용하시기 바랍니다.</p>
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
    sender = EmailSender()

    if not sender.is_configured():
        print("[이메일] 설정이 필요합니다. .env 파일에 다음 항목을 추가하세요:")
        print("  SMTP_SERVER=smtp.gmail.com")
        print("  SMTP_PORT=587")
        print("  SENDER_EMAIL=your_email@gmail.com")
        print("  SENDER_PASSWORD=your_app_password")
        print("  RECIPIENT_EMAILS=recipient1@email.com,recipient2@email.com")
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[주식 스크리닝] 내일 관심 종목 TOP 100 ({date_str})"

    body = create_email_body(results, date_str)

    attachments = []
    if pdf_path and Path(pdf_path).exists():
        attachments.append(pdf_path)

    return sender.send_report(subject, body, attachments)


if __name__ == "__main__":
    # 테스트
    sender = EmailSender()
    print(f"이메일 설정 완료: {sender.is_configured()}")
    print(f"SMTP 서버: {sender.smtp_server}")
    print(f"발신자: {sender.sender_email}")
    print(f"수신자: {sender.recipient_emails}")
