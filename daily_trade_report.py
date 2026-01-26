#!/usr/bin/env python3
"""
자동매매 일일 보고서 생성기
- 매일 오후 4시에 실행
- 김브로 (user_id=7) 계좌 기준
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from weasyprint import HTML, CSS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading.trade_logger import TradeLogger
from pdf_generator import get_base_css


def get_daily_report_css():
    """일일 보고서용 CSS"""
    base = get_base_css()
    extra = """
    .summary-box {
        background: linear-gradient(135deg, #f6f9fc 0%, #eef2f7 100%);
        border: 1px solid #cbd5e0;
        border-radius: 8px;
        padding: 15px;
        margin: 15px 0;
    }
    .profit { color: #c53030; font-weight: bold; }
    .loss { color: #2b6cb0; font-weight: bold; }
    .badge-new {
        display: inline-block;
        background: #48bb78;
        color: white;
        font-size: 8pt;
        padding: 2px 6px;
        border-radius: 4px;
        margin-left: 5px;
    }
    .badge-sold {
        display: inline-block;
        background: #ed8936;
        color: white;
        font-size: 8pt;
        padding: 2px 6px;
        border-radius: 4px;
        margin-left: 5px;
    }
    .account-table {
        width: 100%;
        margin: 15px 0;
    }
    .account-table td:first-child {
        background-color: #edf2f7;
        font-weight: bold;
        width: 25%;
    }
    .account-table td:nth-child(2) {
        text-align: right;
        width: 25%;
    }
    .account-table td:nth-child(3) {
        text-align: right;
        width: 20%;
        color: #718096;
    }
    .account-table td:nth-child(4) {
        text-align: right;
        width: 15%;
    }
    .account-table td:nth-child(5) {
        width: 15%;
    }
    .change-positive { color: #c53030; }
    .change-negative { color: #2b6cb0; }
    .trade-table { width: 100%; margin: 10px 0; }
    .trade-table th { background-color: #2c5282; color: white; }
    .holdings-table { width: 100%; margin: 10px 0; }
    .holdings-table th { background-color: #2c5282; color: white; }
    .no-data {
        color: #718096;
        font-style: italic;
        padding: 20px;
        text-align: center;
        background: #f7fafc;
        border-radius: 8px;
    }
    /* 페이지 나눔 방지 - 제목과 표가 같이 이동 */
    .section {
        page-break-inside: avoid;
        break-inside: avoid;
    }
    h2 {
        page-break-after: avoid;
        break-after: avoid;
    }
    table {
        page-break-inside: avoid;
        break-inside: avoid;
    }
    .summary-box {
        page-break-inside: avoid;
        break-inside: avoid;
    }
    """
    return base + extra


def format_change(current, previous, is_rate=False):
    """변동 포맷"""
    if previous is None or previous == 0:
        return "-", ""
    diff = current - previous
    if is_rate:
        sign = "+" if diff >= 0 else ""
        cls = "change-positive" if diff >= 0 else "change-negative"
        return f"{sign}{diff:.2f}%p", cls
    else:
        sign = "+" if diff >= 0 else ""
        cls = "change-positive" if diff >= 0 else "change-negative"
        return f"{sign}{diff:,.0f}", cls


def generate_daily_report_html(user_id: int, report_date: str = None, save_snapshot: bool = True):
    """일일 보고서 HTML 생성"""
    logger = TradeLogger()

    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    today = report_date.replace("-", "")
    yesterday = (datetime.strptime(report_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y%m%d")

    # 사용자 정보
    api_key_data = logger.get_api_key_settings(user_id)
    if not api_key_data:
        return None

    # 사용자 이름은 stock_data.db에서 조회
    import sqlite3 as sqlite3_module
    stock_db_path = Path(__file__).parent / "database" / "stock_data.db"
    with sqlite3_module.connect(str(stock_db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        user_name = row[0] if row else f'사용자 {user_id}'

    is_mock = bool(api_key_data.get('is_mock', True))
    account_type = "모의투자" if is_mock else "실전투자"
    account_number = api_key_data.get('account_number', '')

    # 실시간 계좌 정보
    account_data = logger.get_real_account_balance(
        app_key=api_key_data.get('app_key'),
        app_secret=api_key_data.get('app_secret'),
        account_number=account_number,
        account_product_code=api_key_data.get('account_product_code', '01'),
        is_mock=is_mock
    )

    # 오늘 거래 내역
    trades = logger.get_trade_history(user_id, start_date=report_date, end_date=report_date)
    today_trades = [t for t in trades if t.get('status') == 'executed']  # 체결된 것만
    today_buys = [t for t in today_trades if t.get('side') == 'buy']
    today_sells = [t for t in today_trades if t.get('side') == 'sell']

    # 오늘 매수한 종목 코드
    today_bought_codes = {t.get('stock_code') for t in today_buys}

    # 현재 보유 종목
    holdings = [h for h in account_data.get('holdings', []) if h.get('quantity', 0) > 0]

    # 계좌 현황
    summary = account_data.get('summary', {})
    d2_cash = summary.get('d2_cash_balance', 0) or summary.get('deposit', 0)  # D+2 예수금
    stock_eval = summary.get('total_eval_amount', 0) or summary.get('stock_eval', 0)  # 보유종목 평가액
    total_assets = d2_cash + stock_eval  # 총 자산 = D+2 예수금 + 보유종목 평가액
    total_profit = summary.get('total_profit_loss', 0) or summary.get('total_profit', 0)
    profit_rate = summary.get('profit_rate', 0)

    # 전일 자산 조회 (DB에서)
    prev_day = logger.get_previous_day_assets(user_id)
    prev_total_assets = prev_day.get('total_assets', 0) if prev_day else None
    prev_d2_cash = prev_day.get('d2_cash', 0) if prev_day else None
    prev_holdings_value = prev_day.get('holdings_value', 0) if prev_day else None
    prev_date = prev_day.get('trade_date', '-') if prev_day else '-'

    # 전일 대비 증감
    if prev_total_assets:
        asset_diff = total_assets - prev_total_assets
        asset_diff_rate = (asset_diff / prev_total_assets * 100) if prev_total_assets > 0 else 0
        asset_diff_str, asset_diff_cls = format_change(total_assets, prev_total_assets)
    else:
        asset_diff = 0
        asset_diff_rate = 0
        asset_diff_str = "-"
        asset_diff_cls = ""

    # 최초 투자 대비 증감 (auto_trade_settings에서 initial_investment 조회)
    initial_investment = None
    try:
        with logger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT initial_investment FROM auto_trade_settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row and row['initial_investment']:
                initial_investment = row['initial_investment']
    except Exception:
        pass

    if initial_investment and initial_investment > 0:
        initial_diff = total_assets - initial_investment
        initial_diff_rate = (initial_diff / initial_investment * 100)
        initial_diff_cls = "change-positive" if initial_diff >= 0 else "change-negative"
    else:
        initial_diff = 0
        initial_diff_rate = 0
        initial_diff_cls = ""

    # 오늘 실현손익 계산 (매도 거래에서)
    realized_profit = sum((t.get('profit_loss') or 0) for t in today_sells)

    # 오늘 자산 스냅샷 저장
    if save_snapshot:
        logger.save_daily_performance(
            user_id=user_id,
            total_assets=total_assets,
            d2_cash=d2_cash,
            holdings_value=stock_eval,
            total_invested=summary.get('total_invested', 0),
            total_profit=total_profit,
            holdings_count=len(holdings)
        )
        print(f"  자산 스냅샷 저장: 총 {total_assets:,}원 (D+2: {d2_cash:,}, 주식: {stock_eval:,})")

    # 계좌현황 테이블 (항목 / 금액 / 전일 금액 / 증감 / 비고)
    account_rows = f"""
    <tr>
        <td>총 자산</td>
        <td><strong>{total_assets:,.0f}원</strong></td>
        <td>{prev_total_assets:,.0f}원</td>
        <td class="{asset_diff_cls}">{asset_diff_str}</td>
        <td>현금 + 보유종목</td>
    </tr>
    <tr>
        <td>현금</td>
        <td>{d2_cash:,.0f}원</td>
        <td>{prev_d2_cash:,.0f}원</td>
        <td>{format_change(d2_cash, prev_d2_cash)[0]}</td>
        <td></td>
    </tr>
    <tr>
        <td>보유종목 평가</td>
        <td>{stock_eval:,.0f}원</td>
        <td>{prev_holdings_value:,.0f}원</td>
        <td>{format_change(stock_eval, prev_holdings_value)[0]}</td>
        <td></td>
    </tr>
    <tr>
        <td>총 평가손익</td>
        <td class="{'profit' if total_profit >= 0 else 'loss'}">{total_profit:+,.0f}원</td>
        <td>-</td>
        <td>-</td>
        <td>매입가 대비</td>
    </tr>
    <tr>
        <td>총 수익률</td>
        <td class="{'profit' if profit_rate >= 0 else 'loss'}">{profit_rate:+.2f}%</td>
        <td>-</td>
        <td>-</td>
        <td></td>
    </tr>
    <tr>
        <td>오늘 실현손익</td>
        <td class="{'profit' if realized_profit >= 0 else 'loss'}">{realized_profit:+,.0f}원</td>
        <td>-</td>
        <td>-</td>
        <td>매도 시 확정</td>
    </tr>
    """ if prev_total_assets else f"""
    <tr>
        <td>총 자산</td>
        <td><strong>{total_assets:,.0f}원</strong></td>
        <td>-</td>
        <td>-</td>
        <td>현금 + 보유종목</td>
    </tr>
    <tr>
        <td>현금</td>
        <td>{d2_cash:,.0f}원</td>
        <td>-</td>
        <td>-</td>
        <td></td>
    </tr>
    <tr>
        <td>보유종목 평가</td>
        <td>{stock_eval:,.0f}원</td>
        <td>-</td>
        <td>-</td>
        <td></td>
    </tr>
    <tr>
        <td>총 평가손익</td>
        <td class="{'profit' if total_profit >= 0 else 'loss'}">{total_profit:+,.0f}원</td>
        <td>-</td>
        <td>-</td>
        <td>매입가 대비</td>
    </tr>
    <tr>
        <td>총 수익률</td>
        <td class="{'profit' if profit_rate >= 0 else 'loss'}">{profit_rate:+.2f}%</td>
        <td>-</td>
        <td>-</td>
        <td></td>
    </tr>
    <tr>
        <td>오늘 실현손익</td>
        <td class="{'profit' if realized_profit >= 0 else 'loss'}">{realized_profit:+,.0f}원</td>
        <td>-</td>
        <td>-</td>
        <td>매도 시 확정</td>
    </tr>
    """

    # 오늘 거래 내역 테이블
    trades_html = ""
    if today_buys:
        trades_html += "<h3>오늘 매수</h3><table class='trade-table'>"
        trades_html += "<tr><th>종목</th><th>수량</th><th>단가</th><th>금액</th><th>시간</th></tr>"
        for t in today_buys:
            amount = t.get('quantity', 0) * t.get('price', 0)
            time_str = t.get('trade_time', '')[:5] if t.get('trade_time') else ''
            trades_html += f"""<tr>
                <td>{t.get('stock_name', t.get('stock_code'))}</td>
                <td style='text-align:right'>{t.get('quantity', 0):,}주</td>
                <td style='text-align:right'>{t.get('price', 0):,}원</td>
                <td style='text-align:right'>{amount:,}원</td>
                <td style='text-align:center'>{time_str}</td>
            </tr>"""
        trades_html += "</table>"

    if today_sells:
        trades_html += "<h3>오늘 매도</h3><table class='trade-table'>"
        trades_html += "<tr><th>종목</th><th>수량</th><th>매수가</th><th>매도가</th><th>매도금액</th><th>매매손익</th></tr>"
        for t in today_sells:
            qty = t.get('quantity', 0)
            sell_price = t.get('price', 0)
            profit = t.get('profit_loss', 0) or 0
            # 매도금액은 DB의 amount (순매도금액, 수수료 공제 후)
            net_amount = t.get('amount', 0) or (qty * sell_price)
            # 매수가 역산: 매수가 = (순매도금액 - 손익) / 수량
            buy_price = int((net_amount - profit) / qty) if qty > 0 else 0
            profit_cls = 'profit' if profit >= 0 else 'loss'
            trades_html += f"""<tr>
                <td>{t.get('stock_name', t.get('stock_code'))}</td>
                <td style='text-align:right'>{qty:,}주</td>
                <td style='text-align:right'>{buy_price:,}원</td>
                <td style='text-align:right'>{sell_price:,}원</td>
                <td style='text-align:right'>{net_amount:,}원</td>
                <td style='text-align:right' class='{profit_cls}'>{profit:+,}원</td>
            </tr>"""
        trades_html += "</table>"
        trades_html += "<p style='font-size: 8pt; color: #718096; margin-top: 5px;'>* 매도금액은 매도가 × 수량에서 세금과 수수료를 공제한 금액입니다.</p>"

    if not today_buys and not today_sells:
        trades_html = "<div class='no-data'>오늘 거래 내역이 없습니다.</div>"

    # 보유 종목 테이블
    holdings_html = ""
    if holdings:
        # 합계 계산
        total_eval_amount = sum(h.get('eval_amount', 0) or 0 for h in holdings)
        total_profit_loss = sum(h.get('profit_loss', 0) or 0 for h in holdings)
        total_buy_amount = sum((h.get('avg_price', 0) or 0) * (h.get('quantity', 0) or 0) for h in holdings)
        total_profit_rate = (total_profit_loss / total_buy_amount * 100) if total_buy_amount > 0 else 0

        holdings_html = "<table class='holdings-table'>"
        holdings_html += "<tr><th>종목</th><th>수량</th><th>평단가</th><th>현재가</th><th>평가금액</th><th>손익</th><th>수익률</th></tr>"
        for h in sorted(holdings, key=lambda x: x.get('profit_rate', 0), reverse=True):
            profit_loss = h.get('profit_loss', 0) or 0
            profit_rate = h.get('profit_rate', 0) or 0
            profit_cls = 'profit' if profit_rate >= 0 else 'loss'
            badge = "<span class='badge-new'>NEW</span>" if h.get('stock_code') in today_bought_codes else ""
            holdings_html += f"""<tr>
                <td>{h.get('stock_name', h.get('stock_code'))}{badge}</td>
                <td style='text-align:right'>{h.get('quantity', 0):,}주</td>
                <td style='text-align:right'>{h.get('avg_price', 0):,}원</td>
                <td style='text-align:right'>{h.get('current_price', 0):,}원</td>
                <td style='text-align:right'>{h.get('eval_amount', 0):,}원</td>
                <td style='text-align:right' class='{profit_cls}'>{profit_loss:+,}원</td>
                <td style='text-align:right' class='{profit_cls}'>{profit_rate:+.2f}%</td>
            </tr>"""
        # 합계 행
        total_cls = 'profit' if total_profit_loss >= 0 else 'loss'
        holdings_html += f"""<tr style='background-color: #edf2f7; font-weight: bold;'>
            <td>합계</td>
            <td></td>
            <td></td>
            <td></td>
            <td style='text-align:right'>{total_eval_amount:,}원</td>
            <td style='text-align:right' class='{total_cls}'>{total_profit_loss:+,}원</td>
            <td style='text-align:right' class='{total_cls}'>{total_profit_rate:+.2f}%</td>
        </tr>"""
        holdings_html += "</table>"
    else:
        holdings_html = "<div class='no-data'>보유 종목이 없습니다.</div>"

    # 오늘 거래 요약
    buy_count = len(today_buys)
    sell_count = len(today_sells)
    buy_total = sum(t.get('quantity', 0) * t.get('price', 0) for t in today_buys)
    sell_total = sum(t.get('quantity', 0) * t.get('price', 0) for t in today_sells)
    # realized_profit은 위에서 이미 계산됨

    # 전일대비 + 최초투자대비 요약 박스
    if prev_total_assets:
        daily_box_html = f"""
        <div class='summary-box' style='background: linear-gradient(135deg, #e6fffa 0%, #ebf8ff 100%); border-color: #4fd1c5;'>
            <strong style='font-size: 12pt;'>전일 대비</strong><br>
            <span style='font-size: 18pt; font-weight: bold;' class='{asset_diff_cls}'>
                {asset_diff:+,.0f}원 ({asset_diff_rate:+.2f}%)
            </span><br>
            <span style='font-size: 9pt; color: #718096;'>
                {prev_date} {prev_total_assets:,}원 → {report_date} {total_assets:,}원
            </span>
        </div>
        """
    else:
        daily_box_html = f"""
        <div class='summary-box' style='background: linear-gradient(135deg, #fefcbf 0%, #fef3c7 100%); border-color: #ecc94b;'>
            <strong>전일 데이터 없음</strong><br>
            <span style='font-size: 9pt; color: #718096;'>
                내일부터 전일대비 증감이 표시됩니다. 오늘 총 자산: {total_assets:,}원
            </span>
        </div>
        """

    # 최초 투자 대비 박스
    if initial_investment and initial_investment > 0:
        initial_box_html = f"""
        <div class='summary-box' style='background: linear-gradient(135deg, #faf5ff 0%, #e9d8fd 100%); border-color: #9f7aea;'>
            <strong style='font-size: 12pt;'>최초 투자 대비</strong><br>
            <span style='font-size: 18pt; font-weight: bold;' class='{initial_diff_cls}'>
                {initial_diff:+,.0f}원 ({initial_diff_rate:+.2f}%)
            </span><br>
            <span style='font-size: 9pt; color: #718096;'>
                최초 {initial_investment:,}원 → 현재 {total_assets:,}원
            </span>
        </div>
        """
    else:
        initial_box_html = ""

    # 두 박스를 나란히 표시
    daily_summary_html = f"""
    <div style='display: flex; gap: 15px; flex-wrap: wrap;'>
        <div style='flex: 1; min-width: 250px;'>{daily_box_html}</div>
        <div style='flex: 1; min-width: 250px;'>{initial_box_html}</div>
    </div>
    """

    trade_summary_html = f"""
    <div class='summary-box'>
        <strong>오늘 거래 요약</strong><br>
        매수: {buy_count}건 ({buy_total:,}원) |
        매도: {sell_count}건 ({sell_total:,}원) |
        실현손익: <span class="{'profit' if realized_profit >= 0 else 'loss'}">{realized_profit:+,}원</span>
    </div>
    """

    # HTML 조립
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>일일 자동매매 보고서 - {report_date}</title>
    </head>
    <body>
        <div class="watermark">Kim's AI</div>

        <div class="header-logo">Kim's AI</div>
        <h1>일일 자동매매 보고서</h1>

        <div class="header-info">
            <strong>보고일:</strong> {report_date} &nbsp;|&nbsp;
            <strong>계정:</strong> {user_name} &nbsp;|&nbsp;
            <strong>계좌:</strong> 한국투자증권 {account_number} ({account_type})
        </div>

        {daily_summary_html}

        <div class="section">
            <h2>계좌 현황</h2>
            <table class="account-table">
                <tr><th>항목</th><th>금액</th><th>전일</th><th>증감</th><th>비고</th></tr>
                {account_rows}
            </table>
        </div>

        {trade_summary_html}

        <div class="section">
            <h2>오늘 거래 내역</h2>
            {trades_html}
        </div>

        <div class="section">
            <h2>현재 보유 종목 ({len(holdings)}개)</h2>
            {holdings_html}
        </div>

        <div class="footer">
            <p style="text-align: center;">Generated by Kim's AI - Auto Trade System</p>
            <p style="text-align: center; font-size: 8pt; color: #999;">
                본 보고서는 자동매매 시스템에 의해 생성되었습니다.
            </p>
        </div>
    </body>
    </html>
    """

    return html


def generate_daily_report_pdf(user_id: int, output_path: str = None, report_date: str = None, save_snapshot: bool = True):
    """일일 보고서 PDF 생성"""
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    if output_path is None:
        # 사용자 이름 조회
        import sqlite3 as sqlite3_module
        stock_db_path = Path(__file__).parent / "database" / "stock_data.db"
        with sqlite3_module.connect(str(stock_db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            user_name = row[0] if row else f'user{user_id}'

        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        date_str = report_date.replace("-", "")
        output_path = str(output_dir / f"daily_trade_report_{user_name}_{date_str}.pdf")

    html = generate_daily_report_html(user_id, report_date, save_snapshot=save_snapshot)
    if html is None:
        print(f"사용자 {user_id}의 API 키가 설정되지 않았습니다.")
        return None

    css = CSS(string=get_daily_report_css())
    HTML(string=html).write_pdf(output_path, stylesheets=[css])

    print(f"일일 보고서 생성 완료: {output_path}")
    return output_path


def save_all_users_snapshot():
    """모든 자동매매 사용자의 자산 스냅샷 저장 (크론용)"""
    logger = TradeLogger()

    # API 키가 설정된 모든 사용자 조회
    with logger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_id FROM api_key_settings WHERE app_key IS NOT NULL")
        users = [row['user_id'] for row in cursor.fetchall()]

    print(f"자산 스냅샷 저장 시작 ({len(users)}명)")
    for user_id in users:
        try:
            api_key_data = logger.get_api_key_settings(user_id)
            if not api_key_data:
                continue

            account_data = logger.get_real_account_balance(
                app_key=api_key_data.get('app_key'),
                app_secret=api_key_data.get('app_secret'),
                account_number=api_key_data.get('account_number'),
                account_product_code=api_key_data.get('account_product_code', '01'),
                is_mock=bool(api_key_data.get('is_mock', True))
            )

            summary = account_data.get('summary', {})
            d2_cash = summary.get('d2_cash_balance', 0) or summary.get('deposit', 0)
            stock_eval = summary.get('total_eval_amount', 0) or summary.get('stock_eval', 0)
            total_assets = d2_cash + stock_eval
            holdings = [h for h in account_data.get('holdings', []) if h.get('quantity', 0) > 0]

            logger.save_daily_performance(
                user_id=user_id,
                total_assets=total_assets,
                d2_cash=d2_cash,
                holdings_value=stock_eval,
                total_invested=summary.get('total_invested', 0),
                total_profit=summary.get('total_profit_loss', 0) or summary.get('total_profit', 0),
                holdings_count=len(holdings)
            )
            user_name = api_key_data.get('name', f'사용자 {user_id}')
            print(f"  [{user_id}] {user_name}: {total_assets:,}원 저장 완료")
        except Exception as e:
            print(f"  [{user_id}] 에러: {e}")

    print("자산 스냅샷 저장 완료")


def send_report_email(user_id: int, pdf_path: str):
    """개별 사용자에게 보고서 이메일 발송"""
    import sqlite3 as sqlite3_module
    from email_sender import EmailSender

    # 사용자 정보 조회
    stock_db_path = Path(__file__).parent / "database" / "stock_data.db"
    with sqlite3_module.connect(str(stock_db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, email FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            print(f"  [{user_id}] 사용자 정보 없음")
            return False
        user_name, user_email = row

    if not user_email:
        print(f"  [{user_id}] {user_name}: 이메일 주소 없음")
        return False

    # 이메일 발송
    sender = EmailSender()
    if not sender.is_configured():
        print(f"  [{user_id}] 이메일 설정 필요 (.env 파일)")
        return False

    # 수신자를 해당 사용자로 설정
    sender.recipient_emails = [user_email]

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[Kim's AI] 일일 자동매매 보고서 ({date_str})"

    body_html = f"""
    <html>
    <body style="font-family: sans-serif;">
        <h2>안녕하세요 {user_name}님,</h2>
        <p>오늘의 자동매매 일일 보고서를 첨부합니다.</p>
        <p>첨부된 PDF 파일을 확인해주세요.</p>
        <br>
        <p style="color: #666; font-size: 12px;">
            본 메일은 Kim's AI 자동매매 시스템에서 자동 발송되었습니다.
        </p>
    </body>
    </html>
    """

    try:
        success = sender.send_report(subject, body_html, attachments=[pdf_path])
        if success:
            print(f"  [{user_id}] {user_name} ({user_email}): 이메일 발송 완료")
        return success
    except Exception as e:
        print(f"  [{user_id}] {user_name}: 이메일 발송 실패 - {e}")
        return False


def generate_all_reports_and_email():
    """모든 사용자 보고서 생성 및 이메일 발송"""
    from trading.trade_logger import TradeLogger

    logger = TradeLogger()

    # API 키가 설정된 모든 사용자 조회
    with logger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_id FROM api_key_settings WHERE app_key IS NOT NULL")
        users = [row['user_id'] for row in cursor.fetchall()]

    print(f"일일 보고서 생성 시작 ({len(users)}명)")

    for user_id in users:
        try:
            # 보고서 생성 (스냅샷 저장 포함)
            pdf_path = generate_daily_report_pdf(user_id=user_id, save_snapshot=True)
            if pdf_path:
                # 이메일 발송
                send_report_email(user_id, pdf_path)
        except Exception as e:
            print(f"  [{user_id}] 에러: {e}")

    print("일일 보고서 생성 및 발송 완료")


def main():
    parser = argparse.ArgumentParser(description='자동매매 일일 보고서 생성')
    parser.add_argument('--user-id', type=int, help='사용자 ID')
    parser.add_argument('--date', type=str, help='보고서 날짜 (YYYY-MM-DD, 기본: 오늘)')
    parser.add_argument('--output', type=str, help='출력 파일 경로')
    parser.add_argument('--no-save', action='store_true', help='스냅샷 저장 안함')
    parser.add_argument('--snapshot-only', action='store_true', help='스냅샷만 저장 (보고서 생성 안함)')
    parser.add_argument('--all', action='store_true', help='모든 사용자 보고서 생성')
    parser.add_argument('--email', action='store_true', help='이메일 발송')
    args = parser.parse_args()

    if args.snapshot_only:
        save_all_users_snapshot()
        return

    if args.all:
        if args.email:
            generate_all_reports_and_email()
        else:
            # 모든 사용자 보고서 생성 (이메일 없이)
            from trading.trade_logger import TradeLogger
            logger = TradeLogger()
            with logger._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT user_id FROM api_key_settings WHERE app_key IS NOT NULL")
                users = [row['user_id'] for row in cursor.fetchall()]
            print(f"일일 보고서 생성 시작 ({len(users)}명)")
            for user_id in users:
                generate_daily_report_pdf(user_id=user_id, save_snapshot=not args.no_save)
        return

    # 단일 사용자 보고서
    user_id = args.user_id or 7
    pdf_path = generate_daily_report_pdf(
        user_id=user_id,
        output_path=args.output,
        report_date=args.date,
        save_snapshot=not args.no_save
    )

    if args.email and pdf_path:
        send_report_email(user_id, pdf_path)


if __name__ == "__main__":
    main()
