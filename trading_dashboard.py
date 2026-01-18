#!/usr/bin/env python3
"""
자동매매 결과 대시보드

사용법:
    python trading_dashboard.py                  # 기본 실행 (포트 5001)
    python trading_dashboard.py --port 8080      # 포트 지정
    python trading_dashboard.py --host 0.0.0.0   # 외부 접속 허용

접속:
    http://localhost:5001
"""

import argparse
import json
import sqlite3
import subprocess
import os
import signal
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request

# 프로젝트 경로
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "database" / "auto_trade.db"
CONFIG_PATH = BASE_DIR / "config.py"
PID_FILE = BASE_DIR / ".auto_trader.pid"

app = Flask(__name__)

# HTML 템플릿
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>자동매매 대시보드</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 12px;
            font-size: 12px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 15px; }
        header h1 { font-size: 1.2rem; color: #fff; margin-bottom: 3px; }
        header p { color: #888; font-size: 0.7rem; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 8px;
            margin-bottom: 15px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 10px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .stat-card .label { color: #888; font-size: 0.6rem; margin-bottom: 3px; }
        .stat-card .value { font-size: 0.85rem; font-weight: 700; }
        .stat-card .value.positive { color: #4ade80; }
        .stat-card .value.negative { color: #f87171; }
        .stat-card .value.neutral { color: #60a5fa; }
        .stat-card .sub { color: #666; font-size: 0.55rem; margin-top: 2px; }
        .section {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 12px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .section h2 { font-size: 0.85rem; margin-bottom: 10px; color: #fff; }
        table { width: 100%; border-collapse: collapse; font-size: 0.7rem; }
        th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { color: #888; font-weight: 500; font-size: 0.65rem; }
        td { font-size: 0.7rem; }
        .badge { display: inline-block; padding: 2px 6px; border-radius: 10px; font-size: 0.6rem; font-weight: 600; }
        .badge.buy { background: rgba(74,222,128,0.2); color: #4ade80; }
        .badge.sell { background: rgba(248,113,113,0.2); color: #f87171; }
        .profit { color: #4ade80; }
        .loss { color: #f87171; }
        .chart-container { height: 180px; margin-top: 10px; }
        .btn {
            padding: 8px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.7rem;
            font-weight: 600;
            border: none;
            transition: all 0.2s;
        }
        .btn-start { background: #4ade80; color: #000; }
        .btn-start:hover { background: #22c55e; }
        .btn-stop { background: #f87171; color: #fff; }
        .btn-stop:hover { background: #ef4444; }
        .btn-save { background: #60a5fa; color: #fff; }
        .btn-save:hover { background: #3b82f6; }
        .btn-refresh { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2); }
        .btn-refresh:hover { background: rgba(255,255,255,0.2); }
        .mode-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.6rem;
            font-weight: 600;
            margin-left: 6px;
        }
        .mode-badge.virtual { background: rgba(251,191,36,0.2); color: #fbbf24; }
        .mode-badge.real { background: rgba(239,68,68,0.2); color: #ef4444; }
        .status-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 10px;
            font-size: 0.65rem;
            font-weight: 600;
        }
        .status-badge.running { background: rgba(74,222,128,0.2); color: #4ade80; }
        .status-badge.stopped { background: rgba(107,114,128,0.2); color: #9ca3af; }
        .empty-state { text-align: center; padding: 20px; color: #666; font-size: 0.7rem; }
        .control-panel {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }
        .settings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 10px;
        }
        .setting-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .setting-item label {
            color: #888;
            font-size: 0.65rem;
        }
        .setting-item input, .setting-item select {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 6px;
            padding: 6px 8px;
            color: #fff;
            font-size: 0.7rem;
        }
        .setting-item input:focus, .setting-item select:focus {
            outline: none;
            border-color: #60a5fa;
        }
        .setting-item .hint {
            color: #666;
            font-size: 0.55rem;
        }
        .toast {
            position: fixed;
            bottom: 10px;
            right: 10px;
            padding: 10px 16px;
            border-radius: 6px;
            color: #fff;
            font-weight: 500;
            font-size: 0.7rem;
            display: none;
            z-index: 1000;
        }
        .toast.success { background: #22c55e; }
        .toast.error { background: #ef4444; }
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: repeat(3, 1fr); }
            .control-panel { justify-content: center; }
            .settings-grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>자동매매 대시보드
                <span class="mode-badge {{ 'virtual' if is_virtual else 'real' }}">{{ '모의투자' if is_virtual else '실전투자' }}</span>
            </h1>
            <p>마지막 업데이트: {{ last_update }}</p>
        </header>

        <!-- 제어 패널 -->
        <div class="section">
            <div class="control-panel">
                <span class="status-badge {{ 'running' if is_running else 'stopped' }}">
                    {{ '실행 중' if is_running else '정지됨' }}
                </span>
                {% if is_running %}
                <button class="btn btn-stop" onclick="stopTrader()">정지</button>
                {% else %}
                <button class="btn btn-start" onclick="startTrader()">실행</button>
                {% endif %}
                <button class="btn btn-start" onclick="runOnce()">1회 실행</button>
                <button class="btn btn-refresh" onclick="location.reload()">새로고침</button>
            </div>
        </div>

        <!-- 계좌 현황 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">총 자산</div>
                <div class="value neutral">{{ "{:,}".format(summary.total_assets) }}원</div>
                <div class="sub">{{ "API 연결됨" if summary.api_connected else "API 연결 안됨" }}</div>
            </div>
            <div class="stat-card">
                <div class="label">현금 잔고</div>
                <div class="value neutral">{{ "{:,}".format(summary.cash_balance) }}원</div>
            </div>
            <div class="stat-card">
                <div class="label">평가 금액</div>
                <div class="value neutral">{{ "{:,}".format(summary.total_eval_amount) }}원</div>
            </div>
            <div class="stat-card">
                <div class="label">총 손익</div>
                <div class="value {{ 'positive' if summary.total_profit >= 0 else 'negative' }}">
                    {{ "{:+,}".format(summary.total_profit) }}원
                </div>
                <div class="sub">{{ "{:+.2f}".format(summary.profit_rate * 100) }}%</div>
            </div>
            <div class="stat-card">
                <div class="label">보유 종목</div>
                <div class="value neutral">{{ summary.holdings_count }}개</div>
                <div class="sub">최대 {{ config.max_holdings }}개</div>
            </div>
            <div class="stat-card">
                <div class="label">승률</div>
                <div class="value {{ 'positive' if summary.win_rate >= 0.5 else 'negative' }}">
                    {{ "{:.1f}".format(summary.win_rate * 100) }}%
                </div>
                <div class="sub">{{ summary.winning_trades }}/{{ summary.total_trades }} 거래</div>
            </div>
        </div>

        <!-- 설정 -->
        <div class="section">
            <h2>매매 설정</h2>
            <form id="settingsForm">
                <div class="settings-grid">
                    <div class="setting-item">
                        <label>최소 매수 점수</label>
                        <input type="number" name="min_buy_score" value="{{ config.min_buy_score }}" min="50" max="100">
                        <span class="hint">50~100 (높을수록 엄격)</span>
                    </div>
                    <div class="setting-item">
                        <label>손절률 (%)</label>
                        <input type="number" name="stop_loss_pct" value="{{ (config.stop_loss_pct * 100)|round(1) }}" step="0.5" min="-20" max="0">
                        <span class="hint">-20 ~ 0 (예: -7)</span>
                    </div>
                    <div class="setting-item">
                        <label>매도 점수</label>
                        <input type="number" name="min_hold_score" value="{{ config.min_hold_score }}" min="0" max="70">
                        <span class="hint">이 점수 이하면 매도</span>
                    </div>
                    <div class="setting-item">
                        <label>종목당 투자비율 (%)</label>
                        <input type="number" name="max_position_pct" value="{{ (config.max_position_pct * 100)|round(1) }}" step="0.5" min="1" max="20">
                        <span class="hint">1~20 (예: 5)</span>
                    </div>
                    <div class="setting-item">
                        <label>최대 보유 종목</label>
                        <input type="number" name="max_holdings" value="{{ config.max_holdings }}" min="1" max="20">
                        <span class="hint">1~20개</span>
                    </div>
                    <div class="setting-item">
                        <label>일일 최대 거래</label>
                        <input type="number" name="max_daily_trades" value="{{ config.max_daily_trades }}" min="1" max="50">
                        <span class="hint">1~50회</span>
                    </div>
                    <div class="setting-item">
                        <label>최대 보유 기간 (일)</label>
                        <input type="number" name="max_hold_days" value="{{ config.max_hold_days }}" min="1" max="30">
                        <span class="hint">1~30일</span>
                    </div>
                </div>
                <div style="margin-top: 20px;">
                    <button type="submit" class="btn btn-save">설정 저장</button>
                </div>
            </form>
        </div>

        <!-- 보유 종목 -->
        <div class="section">
            <h2>보유 종목</h2>
            {% if holdings %}
            <table>
                <thead>
                    <tr>
                        <th>종목명</th>
                        <th>수량</th>
                        <th>평균단가</th>
                        <th>현재가</th>
                        <th>수익률</th>
                    </tr>
                </thead>
                <tbody>
                    {% for h in holdings %}
                    <tr>
                        <td>{{ h.stock_name }}</td>
                        <td>{{ h.quantity }}주</td>
                        <td>{{ "{:,}".format(h.avg_price) }}원</td>
                        <td>{{ "{:,}".format(h.current_price) }}원</td>
                        <td class="{{ 'profit' if h.profit_rate >= 0 else 'loss' }}">
                            {{ "{:+.2f}".format(h.profit_rate * 100) }}%
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">보유 종목이 없습니다</div>
            {% endif %}
        </div>

        <!-- 최근 거래 -->
        <div class="section">
            <h2>최근 거래 내역</h2>
            {% if trades %}
            <table>
                <thead>
                    <tr>
                        <th>일시</th>
                        <th>종목명</th>
                        <th>유형</th>
                        <th>수량</th>
                        <th>가격</th>
                        <th>사유</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in trades %}
                    <tr>
                        <td>{{ t.trade_date }} {{ t.trade_time }}</td>
                        <td>{{ t.stock_name }}</td>
                        <td><span class="badge {{ t.side }}">{{ '매수' if t.side == 'buy' else '매도' }}</span></td>
                        <td>{{ t.quantity }}주</td>
                        <td>{{ "{:,}".format(t.price) }}원</td>
                        <td>{{ t.trade_reason or '-' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">거래 내역이 없습니다</div>
            {% endif %}
        </div>

        <!-- 일별 성과 차트 -->
        <div class="section">
            <h2>일별 성과</h2>
            <div class="chart-container">
                <canvas id="performanceChart"></canvas>
            </div>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
        function showToast(message, type) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast ' + type;
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }

        function startTrader() {
            fetch('/api/trader/start', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 1000);
                });
        }

        function stopTrader() {
            fetch('/api/trader/stop', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 1000);
                });
        }

        function runOnce() {
            showToast('자동매매 1회 실행 중...', 'success');
            fetch('/api/trader/run-once', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 2000);
                });
        }

        document.getElementById('settingsForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const data = Object.fromEntries(formData.entries());

            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                showToast(data.message, data.success ? 'success' : 'error');
            });
        });

        // 차트
        const ctx = document.getElementById('performanceChart').getContext('2d');
        const performanceData = {{ performance_json | safe }};

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: performanceData.map(d => d.date),
                datasets: [{
                    label: '총 자산',
                    data: performanceData.map(d => d.total_assets),
                    borderColor: '#60a5fa',
                    backgroundColor: 'rgba(96, 165, 250, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#888' } } },
                scales: {
                    x: { ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: {
                        ticks: { color: '#666', callback: v => v.toLocaleString() + '원' },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    }
                }
            }
        });
    </script>
</body>
</html>
"""


def get_db_connection():
    """DB 연결"""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_account_from_api():
    """KIS API에서 실시간 계좌 정보 조회"""
    try:
        from api.services.kis_client import KISClient
        from config import AutoTraderConfig

        client = KISClient(is_virtual=AutoTraderConfig.IS_VIRTUAL)
        balance = client.get_account_balance()

        if balance:
            return {
                "holdings": balance.get("holdings", []),
                "summary": balance.get("summary", {}),
                "success": True
            }
    except Exception as e:
        print(f"API 조회 실패: {e}")

    return {"holdings": [], "summary": {}, "success": False}


def get_config():
    """현재 설정 조회"""
    try:
        from config import AutoTraderConfig
        return {
            "is_virtual": AutoTraderConfig.IS_VIRTUAL,
            "min_buy_score": AutoTraderConfig.MIN_BUY_SCORE,
            "stop_loss_pct": AutoTraderConfig.STOP_LOSS_PCT,
            "min_hold_score": AutoTraderConfig.MIN_HOLD_SCORE,
            "max_position_pct": AutoTraderConfig.MAX_POSITION_PCT,
            "max_holdings": AutoTraderConfig.MAX_HOLDINGS,
            "max_daily_trades": AutoTraderConfig.MAX_DAILY_TRADES,
            "max_hold_days": AutoTraderConfig.MAX_HOLD_DAYS,
        }
    except:
        return {
            "is_virtual": True,
            "min_buy_score": 80,
            "stop_loss_pct": -0.07,
            "min_hold_score": 40,
            "max_position_pct": 0.05,
            "max_holdings": 10,
            "max_daily_trades": 10,
            "max_hold_days": 10,
        }


def save_config(settings):
    """설정 저장"""
    import re
    import importlib
    try:
        config_content = CONFIG_PATH.read_text(encoding='utf-8')

        mappings = {
            'min_buy_score': ('MIN_BUY_SCORE = ', int),
            'stop_loss_pct': ('STOP_LOSS_PCT = ', lambda x: float(x) / 100),
            'min_hold_score': ('MIN_HOLD_SCORE = ', int),
            'max_position_pct': ('MAX_POSITION_PCT = ', lambda x: float(x) / 100),
            'max_holdings': ('MAX_HOLDINGS = ', int),
            'max_daily_trades': ('MAX_DAILY_TRADES = ', int),
            'max_hold_days': ('MAX_HOLD_DAYS = ', int),
        }

        for key, (prefix, converter) in mappings.items():
            if key in settings:
                value = converter(settings[key])
                pattern = rf"({prefix})[^\n#]+"
                replacement = f"{prefix}{value}"
                config_content = re.sub(pattern, replacement, config_content)

        CONFIG_PATH.write_text(config_content, encoding='utf-8')

        # config 모듈 reload (캐시된 import 갱신)
        import config
        importlib.reload(config)

        return True
    except Exception as e:
        print(f"설정 저장 실패: {e}")
        return False


def is_trader_running():
    """자동매매 실행 중인지 확인"""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            PID_FILE.unlink(missing_ok=True)
    return False


def create_scheduler_script(script_path: Path):
    """자동매매 스케줄러 스크립트 생성"""
    # logs 디렉토리 생성
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    scheduler_code = '''#!/usr/bin/env python3
"""
자동매매 스케줄러
- 장 시간 동안 주기적으로 자동매매 실행
- 08:50 ~ 15:20 (평일만)
"""
import time
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auto_trader import AutoTrader

MARKET_OPEN = (8, 50)   # 장 시작 전 매매 (08:50)
MARKET_CLOSE = (15, 20) # 장 마감 전 매매 (15:20)
RUN_INTERVAL = 3600     # 1시간마다 체크 (초)

def is_market_hours():
    """장 시간인지 확인"""
    now = datetime.now()
    # 주말 제외
    if now.weekday() >= 5:
        return False
    # 시간 체크
    current_minutes = now.hour * 60 + now.minute
    open_minutes = MARKET_OPEN[0] * 60 + MARKET_OPEN[1]
    close_minutes = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    return open_minutes <= current_minutes <= close_minutes

def main():
    print(f"[{datetime.now()}] 자동매매 스케줄러 시작")
    last_run_date = None

    while True:
        now = datetime.now()
        today = now.date()

        # 장 시간이고, 오늘 아직 실행 안 했으면 실행
        if is_market_hours() and last_run_date != today:
            print(f"\\n[{now}] 자동매매 실행")
            try:
                trader = AutoTrader(dry_run=False)
                result = trader.run()
                print(f"결과: {result.get('status')}")
                last_run_date = today
            except Exception as e:
                print(f"오류: {e}")

        # 대기
        time.sleep(RUN_INTERVAL)

if __name__ == "__main__":
    main()
'''
    script_path.write_text(scheduler_code, encoding='utf-8')
    script_path.chmod(0o755)


def get_summary(days=30):
    """성과 요약"""
    account = get_account_from_api()
    api_summary = account.get("summary", {})

    total_trades = 0
    wins = 0

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins
            FROM trade_log
            WHERE trade_date >= ? AND status = 'executed' AND side = 'sell'
        """, (start_date,))
        trade_stats = cursor.fetchone()
        conn.close()

        total_trades = trade_stats["total"] if trade_stats else 0
        wins = trade_stats["wins"] if trade_stats and trade_stats["wins"] else 0

    total_eval = api_summary.get("total_eval_amount", 0)
    cash = api_summary.get("cash_balance", 0)
    total_assets = total_eval + cash if total_eval else cash

    return {
        "total_assets": total_assets,
        "cash_balance": cash,
        "total_eval_amount": total_eval,
        "total_profit": api_summary.get("total_profit_loss", 0),
        "profit_rate": api_summary.get("profit_rate", 0) / 100 if api_summary.get("profit_rate") else 0,
        "win_rate": wins / total_trades if total_trades > 0 else 0,
        "winning_trades": wins,
        "total_trades": total_trades,
        "holdings_count": len(account.get("holdings", [])),
        "api_connected": account.get("success", False)
    }


def get_holdings():
    """보유 종목"""
    account = get_account_from_api()
    if not account.get("success"):
        return []

    holdings = []
    for h in account.get("holdings", []):
        avg_price = h.get("avg_price", 0)
        current_price = h.get("current_price", 0)
        profit_rate = h.get("profit_rate", 0) / 100 if h.get("profit_rate") else 0

        holdings.append({
            "stock_code": h.get("stock_code"),
            "stock_name": h.get("stock_name"),
            "quantity": h.get("quantity", 0),
            "avg_price": avg_price,
            "current_price": current_price,
            "profit_rate": profit_rate,
        })

    return holdings


def get_trades(limit=20):
    """최근 거래 내역"""
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM trade_log
        ORDER BY trade_date DESC, trade_time DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_performance(days=30):
    """일별 성과"""
    conn = get_db_connection()
    if not conn:
        return []

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trade_date, total_assets, total_profit
        FROM daily_performance
        WHERE trade_date >= ?
        ORDER BY trade_date ASC
    """, (start_date,))
    rows = cursor.fetchall()
    conn.close()

    return [{"date": row["trade_date"], "total_assets": row["total_assets"], "total_profit": row["total_profit"]} for row in rows]


@app.route("/")
def dashboard():
    """메인 대시보드"""
    config = get_config()
    summary = get_summary()
    holdings = get_holdings()
    trades = get_trades()
    performance = get_performance()

    return render_template_string(
        DASHBOARD_HTML,
        summary=summary,
        holdings=holdings,
        trades=trades,
        config=config,
        performance_json=json.dumps(performance),
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        is_virtual=config.get("is_virtual", True),
        is_running=is_trader_running()
    )


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    """설정 저장 API"""
    data = request.json
    if save_config(data):
        return jsonify({"success": True, "message": "설정이 저장되었습니다"})
    return jsonify({"success": False, "message": "설정 저장 실패"})


@app.route("/api/trader/start", methods=["POST"])
def api_start_trader():
    """자동매매 시작 (스케줄러 모드)"""
    if is_trader_running():
        return jsonify({"success": False, "message": "이미 실행 중입니다"})

    try:
        # 스케줄러 스크립트 실행
        scheduler_script = BASE_DIR / "auto_trader_scheduler.py"

        # 스케줄러 스크립트가 없으면 생성
        if not scheduler_script.exists():
            create_scheduler_script(scheduler_script)

        # 백그라운드로 실행
        process = subprocess.Popen(
            [str(BASE_DIR / "venv/bin/python"), str(scheduler_script)],
            stdout=open(BASE_DIR / "logs" / "scheduler.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )

        # PID 저장
        PID_FILE.write_text(str(process.pid))

        return jsonify({"success": True, "message": f"자동매매 스케줄러 시작 (PID: {process.pid})"})
    except Exception as e:
        return jsonify({"success": False, "message": f"시작 실패: {e}"})


@app.route("/api/trader/stop", methods=["POST"])
def api_stop_trader():
    """자동매매 정지"""
    if not is_trader_running():
        return jsonify({"success": False, "message": "실행 중이 아닙니다"})

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return jsonify({"success": True, "message": "자동매매가 정지되었습니다"})
    except Exception as e:
        return jsonify({"success": False, "message": f"정지 실패: {e}"})


@app.route("/api/trader/run-once", methods=["POST"])
def api_run_once():
    """자동매매 1회 실행 (실제 매매)"""
    try:
        # logs 디렉토리 생성
        logs_dir = BASE_DIR / "logs"
        logs_dir.mkdir(exist_ok=True)

        script_path = BASE_DIR / "auto_trader.py"
        log_file = logs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        subprocess.Popen(
            [str(BASE_DIR / "venv/bin/python"), str(script_path)],
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        return jsonify({"success": True, "message": "자동매매 1회 실행 중... (로그: logs/)"})
    except Exception as e:
        return jsonify({"success": False, "message": f"실행 실패: {e}"})


@app.route("/api/summary")
def api_summary():
    return jsonify(get_summary())


@app.route("/api/holdings")
def api_holdings():
    return jsonify(get_holdings())


@app.route("/api/trades")
def api_trades():
    return jsonify(get_trades())


def main():
    parser = argparse.ArgumentParser(description="자동매매 대시보드")
    parser.add_argument("--host", default="127.0.0.1", help="호스트")
    parser.add_argument("--port", type=int, default=5001, help="포트")
    parser.add_argument("--debug", action="store_true", help="디버그 모드")
    args = parser.parse_args()

    print(f"\n자동매매 대시보드 시작")
    print(f"접속 주소: http://{args.host}:{args.port}")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
