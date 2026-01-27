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
from trading.trade_logger import BuySuggestionManager, TradeLogger

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
    <!-- AJAX로 새로고침 (모달 열려있으면 건너뜀) -->
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
        .stat-card.clickable { cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
        .stat-card.clickable:hover { transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        /* 모달 스타일 */
        .modal {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 1000;
            display: flex; align-items: center; justify-content: center;
        }
        .modal-content {
            background: #1a1a2e; border-radius: 12px; width: 95%; max-width: 600px;
            max-height: 80vh; overflow: hidden; border: 1px solid rgba(255,255,255,0.1);
        }
        .modal-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .modal-header h3 { margin: 0; font-size: 0.9rem; color: #fff; }
        .close-btn { font-size: 1.5rem; cursor: pointer; color: #888; }
        .close-btn:hover { color: #fff; }
        .modal-body { padding: 16px; overflow-y: auto; max-height: calc(80vh - 60px); }
        .trade-date-group { margin-bottom: 16px; }
        .trade-date-header { color: #888; font-size: 0.7rem; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .trade-item {
            display: grid; grid-template-columns: 1fr auto; gap: 8px;
            padding: 10px; background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 8px;
        }
        .trade-item .stock-name { font-weight: 600; color: #fff; font-size: 0.8rem; }
        .trade-item .trade-detail { color: #888; font-size: 0.65rem; margin-top: 4px; }
        .trade-item .trade-result { text-align: right; }
        .trade-item .profit-amount { font-size: 0.8rem; font-weight: 600; }
        .trade-item .profit-rate { font-size: 0.65rem; }
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
        .collapsible {
            cursor: pointer;
            user-select: none;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .collapsible:hover { color: #60a5fa; }
        #settingsIcon { font-size: 0.7rem; transition: transform 0.2s; }
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

        <!-- 계좌 현황 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">투자금액</div>
                <div class="value neutral">{{ "{:,}".format(summary.invested_amount) }}원</div>
            </div>
            <div class="stat-card">
                <div class="label">평가금액</div>
                <div class="value neutral">{{ "{:,}".format(summary.total_eval_amount) }}원</div>
            </div>
            <div class="stat-card">
                <div class="label">실현손익</div>
                <div class="value {{ 'positive' if summary.realized_profit|default(0) >= 0 else 'negative' }}">
                    {{ "{:+,}".format(summary.realized_profit|default(0)) }}원
                </div>
            </div>
            <div class="stat-card">
                <div class="label">총손익</div>
                <div class="value {{ 'positive' if summary.total_profit >= 0 else 'negative' }}">
                    {{ "{:+,}".format(summary.total_profit) }}원
                </div>
                <div class="sub">{{ "{:+.2f}".format(summary.profit_rate * 100) }}%</div>
            </div>
            <div class="stat-card">
                <div class="label">보유종목</div>
                <div class="value neutral">{{ summary.holdings_count }}개</div>
                <div class="sub">최대 {{ config.max_holdings }}개</div>
            </div>
            <div class="stat-card clickable" onclick="showTradeHistory()">
                <div class="label">승률</div>
                <div class="value {{ 'positive' if summary.win_rate >= 0.5 else 'negative' }}">
                    {{ "{:.1f}".format(summary.win_rate * 100) }}%
                </div>
                <div class="sub">{{ summary.winning_trades }}/{{ summary.total_trades }} 거래</div>
            </div>
        </div>

        <!-- 거래 내역 모달 -->
        <div id="tradeHistoryModal" class="modal" style="display: none;">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>거래 내역</h3>
                    <span class="close-btn" onclick="closeTradeHistory()">&times;</span>
                </div>
                <div class="modal-body" id="tradeHistoryBody">
                    <p>로딩 중...</p>
                </div>
            </div>
        </div>

        <!-- 설정 및 제어 -->
        <div class="section">
            <h2 class="collapsible" onclick="toggleSettings()">
                <span id="settingsIcon">▶</span> 설정 및 제어
                <span class="status-badge {{ 'running' if is_running else 'stopped' }}" style="margin-left: 10px;">
                    {{ '실행 중' if is_running else '정지됨' }}
                </span>
            </h2>
            <div id="settingsForm" style="display: none;">
                <!-- 제어 버튼 -->
                <div style="margin-bottom: 20px; padding: 10px; background: rgba(255,255,255,0.03); border-radius: 6px;">
                    <label style="color: #888; font-size: 0.65rem; display: block; margin-bottom: 8px;">자동매매 제어</label>
                    <div class="control-panel">
                        {% if is_running %}
                        <button class="btn btn-stop" onclick="stopTrader()">정지</button>
                        {% else %}
                        <button class="btn btn-start" onclick="startTrader()">실행</button>
                        {% endif %}
                        <button class="btn btn-start" onclick="runOnce()">1회 실행</button>
                        <button class="btn btn-refresh" onclick="location.reload()">새로고침</button>
                        {% if is_virtual %}
                        <button class="btn btn-stop" onclick="resetVirtualBalance()" style="margin-left: 10px;">잔고 리셋</button>
                        {% endif %}
                    </div>
                </div>

                <!-- 매매 설정 -->
                <form id="settingsFormInner">
                    <div class="settings-grid">
                        <div class="setting-item">
                            <label>매매 모드</label>
                            <select name="trade_mode">
                                <option value="auto" {{ 'selected' if config.trade_mode == 'auto' else '' }}>자동매매 (Auto)</option>
                                <option value="semi-auto" {{ 'selected' if config.trade_mode == 'semi-auto' else '' }}>반자동 (Semi-Auto)</option>
                            </select>
                            <span class="hint">auto: 즉시매수 / semi-auto: 제안승인</span>
                        </div>
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
                    <div style="margin-top: 20px; display: flex; align-items: center; gap: 10px;">
                        <input type="password" id="adminPassword" placeholder="비밀번호" style="width: 100px; padding: 8px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; color: #fff; font-size: 0.7rem;">
                        <button type="submit" class="btn btn-save">설정 저장</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- 매수 대기열 -->
        <div class="section">
            <h2>📊 매수 대기열 <span style="font-size: 0.65rem; color: #888;">({{ buy_candidates|length }}개 대기)</span></h2>
            {% if buy_candidates %}
            <table>
                <thead>
                    <tr>
                        <th>종목명</th>
                        <th>점수</th>
                        <th>현재가</th>
                        <th>추천가</th>
                        <th>밴드상한</th>
                        <th>상태</th>
                    </tr>
                </thead>
                <tbody>
                    {% for c in buy_candidates %}
                    <tr>
                        <td>{{ c.stock_name }}</td>
                        <td><span class="badge buy">{{ c.score }}점</span></td>
                        <td>{{ "{:,}".format(c.current_price) }}원</td>
                        <td>{{ "{:,}".format(c.recommended_price) }}원</td>
                        <td>{{ "{:,}".format(c.buy_band_high) }}원</td>
                        <td>
                            {% if c.current_price <= c.buy_band_high %}
                            <span class="badge buy">매수가능</span>
                            {% else %}
                            <span style="color: #888; font-size: 0.6rem;">가격대기 ({{ "{:.1f}".format((c.current_price - c.buy_band_high) / c.buy_band_high * 100) }}%↑)</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">매수 조건 충족 종목이 없습니다</div>
            {% endif %}
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

        function toggleSettings() {
            const form = document.getElementById('settingsForm');
            const icon = document.getElementById('settingsIcon');
            if (form.style.display === 'none') {
                form.style.display = 'block';
                icon.textContent = '▼';
            } else {
                form.style.display = 'none';
                icon.textContent = '▶';
            }
        }

        function showTradeHistory() {
            document.getElementById('tradeHistoryModal').style.display = 'flex';
            fetch('/api/trade-history')
                .then(res => res.json())
                .then(data => {
                    const body = document.getElementById('tradeHistoryBody');
                    if (!data.trades || data.trades.length === 0) {
                        body.innerHTML = '<p style="color: #888; text-align: center;">거래 내역이 없습니다.</p>';
                        return;
                    }
                    // 날짜별로 그룹화
                    const grouped = {};
                    data.trades.forEach(t => {
                        const date = t.trade_date;
                        if (!grouped[date]) grouped[date] = [];
                        grouped[date].push(t);
                    });
                    let html = '';
                    Object.keys(grouped).sort().reverse().forEach(date => {
                        html += `<div class="trade-date-group">`;
                        html += `<div class="trade-date-header">${date}</div>`;
                        grouped[date].forEach(t => {
                            const profitClass = t.profit_loss >= 0 ? 'profit' : 'loss';
                            const profitSign = t.profit_loss >= 0 ? '+' : '';
                            const rateSign = t.profit_rate >= 0 ? '+' : '';
                            html += `
                                <div class="trade-item">
                                    <div>
                                        <div class="stock-name">${t.stock_name}</div>
                                        <div class="trade-detail">
                                            매수 ${t.buy_price?.toLocaleString() || '-'}원 → 매도 ${t.sell_price?.toLocaleString() || '-'}원 (${t.quantity}주)
                                        </div>
                                        <div class="trade-detail">
                                            매수금액 ${t.buy_amount?.toLocaleString() || '-'}원 / 매도금액 ${t.sell_amount?.toLocaleString() || '-'}원
                                        </div>
                                    </div>
                                    <div class="trade-result">
                                        <div class="profit-amount ${profitClass}">${profitSign}${t.profit_loss?.toLocaleString() || 0}원</div>
                                        <div class="profit-rate ${profitClass}">${rateSign}${(t.profit_rate * 100).toFixed(1)}%</div>
                                    </div>
                                </div>
                            `;
                        });
                        html += '</div>';
                    });
                    body.innerHTML = html;
                })
                .catch(err => {
                    document.getElementById('tradeHistoryBody').innerHTML = '<p style="color: #f87171;">데이터 로딩 실패</p>';
                });
        }

        function closeTradeHistory() {
            document.getElementById('tradeHistoryModal').style.display = 'none';
        }

        // 모달 바깥 클릭 시 닫기
        document.getElementById('tradeHistoryModal')?.addEventListener('click', function(e) {
            if (e.target === this) closeTradeHistory();
        });

        function getPassword() {
            return document.getElementById('adminPassword').value;
        }

        function checkPassword() {
            const pwd = getPassword();
            if (pwd !== '8864') {
                showToast('비밀번호가 올바르지 않습니다', 'error');
                return false;
            }
            return true;
        }

        function startTrader() {
            if (!checkPassword()) return;
            fetch('/api/trader/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: getPassword() })
            })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 1000);
                });
        }

        function stopTrader() {
            if (!checkPassword()) return;
            fetch('/api/trader/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: getPassword() })
            })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 1000);
                });
        }

        function runOnce() {
            if (!checkPassword()) return;
            showToast('자동매매 1회 실행 중...', 'success');
            fetch('/api/trader/run-once', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: getPassword() })
            })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 2000);
                });
        }

        function resetVirtualBalance() {
            if (!checkPassword()) return;
            if (!confirm('가상 잔고를 초기 금액으로 리셋하시겠습니까?')) return;

            fetch('/api/virtual-balance/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: getPassword() })
            })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 1000);
                });
        }

        function approveSuggestion(id) {
            fetch('/api/suggestions/' + id + '/approve', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 500);
                });
        }

        function rejectSuggestion(id) {
            fetch('/api/suggestions/' + id + '/reject', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 500);
                });
        }

        document.getElementById('settingsFormInner').addEventListener('submit', function(e) {
            e.preventDefault();
            if (!checkPassword()) return;

            const formData = new FormData(this);
            const data = Object.fromEntries(formData.entries());
            data.password = getPassword();

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

        // 20초마다 자동 새로고침 (모달 열려있으면 건너뜀)
        setInterval(() => {
            const modal = document.getElementById('tradeHistoryModal');
            if (modal && modal.style.display !== 'none') {
                console.log('모달 열려있음 - 새로고침 건너뜀');
                return;
            }
            location.reload();
        }, 20000);
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
            "trade_mode": getattr(AutoTraderConfig, 'TRADE_MODE', 'auto'),
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
            "trade_mode": "auto",
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
            'trade_mode': ('TRADE_MODE = ', lambda x: f'"{x}"'),
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
        except PermissionError:
            # 다른 사용자가 실행한 프로세스 - 실행 중으로 간주
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
    config = get_config()
    is_virtual = config.get("is_virtual", True)

    # 거래 통계 조회
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

    # 모의투자: 가상 잔고 사용
    if is_virtual:
        try:
            logger = TradeLogger()

            # 가상 잔고 없으면 초기화
            virtual_balance = logger.get_virtual_balance()
            if not virtual_balance:
                from config import AutoTraderConfig
                initial_cash = getattr(AutoTraderConfig, 'VIRTUAL_INITIAL_CASH', 100_000_000)
                logger.init_virtual_balance(initial_cash)
                virtual_balance = logger.get_virtual_balance()

            # 보유 종목의 현재 평가금액 계산
            holdings = logger.get_holdings()
            total_eval = 0
            invested_amount = 0

            if holdings:
                # API에서 현재가 조회해서 평가금액 계산
                account = get_account_from_api()
                api_holdings = {h.get('stock_code'): h for h in account.get('holdings', [])}

                for h in holdings:
                    stock_code = h.get('stock_code')
                    quantity = h.get('quantity', 0)
                    avg_price = h.get('avg_price', 0)

                    # API 데이터가 있으면 현재가 사용, 없으면 평균단가 사용
                    if stock_code in api_holdings:
                        current_price = api_holdings[stock_code].get('current_price', avg_price)
                    else:
                        current_price = avg_price

                    total_eval += current_price * quantity
                    invested_amount += avg_price * quantity

                # 평가금액 업데이트
                logger.update_virtual_eval(total_eval)

            summary = logger.get_virtual_summary()
            realized_profit = summary.get('total_profit', 0)  # 실현손익
            unrealized_profit = total_eval - invested_amount  # 미실현손익 = 평가금액 - 투자금액
            total_profit = realized_profit + unrealized_profit  # 총손익 = 실현 + 미실현
            total_assets = summary.get('current_cash', 0) + total_eval

            return {
                "total_assets": total_assets,
                "invested_amount": invested_amount,
                "total_eval_amount": total_eval,
                "cash_balance": summary.get('current_cash', 0),
                "total_profit": total_profit,
                "realized_profit": realized_profit,
                "unrealized_profit": unrealized_profit,
                "profit_rate": total_profit / invested_amount if invested_amount > 0 else 0,
                "win_rate": wins / total_trades if total_trades > 0 else 0,
                "winning_trades": wins,
                "total_trades": total_trades,
                "holdings_count": len(holdings),
                "api_connected": True,
                "is_virtual_balance": True
            }
        except Exception as e:
            print(f"가상 잔고 조회 실패: {e}")

    # 실전투자 또는 가상잔고 실패 시: API 사용
    account = get_account_from_api()
    api_summary = account.get("summary", {})

    total_eval = api_summary.get("total_eval_amount", 0)
    cash = api_summary.get("cash_balance", 0)
    total_assets = total_eval + cash if total_eval else cash

    holdings = account.get("holdings", [])
    invested_amount = sum(
        h.get("avg_price", 0) * h.get("quantity", 0) for h in holdings
    )

    # 미실현손익 = 평가금액 - 투자금액
    unrealized_profit = total_eval - invested_amount
    # API에서 실현손익 (없으면 0)
    realized_profit = api_summary.get("total_profit_loss", 0) - unrealized_profit if api_summary.get("total_profit_loss") else 0
    # 총손익 = 실현 + 미실현
    total_profit = realized_profit + unrealized_profit

    return {
        "total_assets": total_assets,
        "invested_amount": invested_amount,
        "total_eval_amount": total_eval,
        "cash_balance": cash,
        "total_profit": total_profit,
        "realized_profit": realized_profit,
        "unrealized_profit": unrealized_profit,
        "profit_rate": api_summary.get("profit_rate", 0) / 100 if api_summary.get("profit_rate") else 0,
        "win_rate": wins / total_trades if total_trades > 0 else 0,
        "winning_trades": wins,
        "total_trades": total_trades,
        "holdings_count": len(holdings),
        "api_connected": account.get("success", False),
        "is_virtual_balance": False
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

    # 매수 대기열 조회
    buy_candidates = []
    try:
        from auto_trader import AutoTrader
        trader = AutoTrader(dry_run=True)
        analysis = trader.load_analysis_results()
        if analysis:
            candidates = trader.filter_buy_candidates(analysis)
            # 이미 보유 중인 종목 제외
            holding_codes = {h.get('stock_code') for h in holdings}
            buy_candidates = [c for c in candidates if c.get('stock_code') not in holding_codes]
    except Exception as e:
        print(f"매수 대기열 조회 실패: {e}")

    return render_template_string(
        DASHBOARD_HTML,
        summary=summary,
        holdings=holdings,
        trades=trades,
        config=config,
        buy_candidates=buy_candidates,
        performance_json=json.dumps(performance),
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        is_virtual=config.get("is_virtual", True),
        is_running=is_trader_running()
    )


ADMIN_PASSWORD = "8864"


def check_password(data):
    """비밀번호 확인"""
    return data.get("password") == ADMIN_PASSWORD


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    """설정 저장 API"""
    data = request.json
    if not check_password(data):
        return jsonify({"success": False, "message": "비밀번호가 올바르지 않습니다"})

    if save_config(data):
        return jsonify({"success": True, "message": "설정이 저장되었습니다"})
    return jsonify({"success": False, "message": "설정 저장 실패"})


@app.route("/api/trader/start", methods=["POST"])
def api_start_trader():
    """자동매매 시작 (스케줄러 모드)"""
    data = request.json or {}
    if not check_password(data):
        return jsonify({"success": False, "message": "비밀번호가 올바르지 않습니다"})

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
    data = request.json or {}
    if not check_password(data):
        return jsonify({"success": False, "message": "비밀번호가 올바르지 않습니다"})

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
    data = request.json or {}
    if not check_password(data):
        return jsonify({"success": False, "message": "비밀번호가 올바르지 않습니다"})

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


@app.route("/api/trade-history")
def api_trade_history():
    """완료된 거래 내역 (매수-매도 매칭)"""
    try:
        logger = TradeLogger()
        with logger._get_connection() as conn:
            cursor = conn.cursor()
            # 매도 기록에서 매수 정보와 함께 조회
            cursor.execute("""
                SELECT
                    s.trade_date,
                    s.stock_code,
                    s.stock_name,
                    b.price as buy_price,
                    s.price as sell_price,
                    s.quantity,
                    b.price * s.quantity as buy_amount,
                    s.price * s.quantity as sell_amount,
                    s.profit_loss,
                    s.profit_rate
                FROM trade_log s
                LEFT JOIN trade_log b ON s.stock_code = b.stock_code
                    AND b.side = 'buy' AND b.status = 'executed'
                WHERE s.side = 'sell' AND s.status = 'executed'
                ORDER BY s.trade_date DESC, s.created_at DESC
                LIMIT 100
            """)
            rows = cursor.fetchall()
            trades = [dict(row) for row in rows]
        return jsonify({"success": True, "trades": trades})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "trades": []})


@app.route("/api/suggestions")
def api_suggestions():
    """매수 대기열 조회"""
    try:
        suggestion_manager = BuySuggestionManager()
        suggestions = suggestion_manager.get_pending_suggestions()
        return jsonify({"success": True, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/suggestions/<int:suggestion_id>/approve", methods=["POST"])
def api_approve_suggestion(suggestion_id):
    """매수 제안 승인"""
    try:
        suggestion_manager = BuySuggestionManager()
        suggestion = suggestion_manager.get_suggestion(suggestion_id)

        if not suggestion:
            return jsonify({"success": False, "message": "제안을 찾을 수 없습니다"})

        if suggestion_manager.approve_suggestion(suggestion_id):
            return jsonify({
                "success": True,
                "message": f"{suggestion.get('stock_name', '')} 매수 제안 승인됨"
            })
        else:
            return jsonify({"success": False, "message": "승인 처리 실패"})
    except Exception as e:
        return jsonify({"success": False, "message": f"오류: {e}"})


@app.route("/api/suggestions/<int:suggestion_id>/reject", methods=["POST"])
def api_reject_suggestion(suggestion_id):
    """매수 제안 거부"""
    try:
        suggestion_manager = BuySuggestionManager()
        suggestion = suggestion_manager.get_suggestion(suggestion_id)

        if not suggestion:
            return jsonify({"success": False, "message": "제안을 찾을 수 없습니다"})

        if suggestion_manager.reject_suggestion(suggestion_id):
            return jsonify({
                "success": True,
                "message": f"{suggestion.get('stock_name', '')} 매수 제안 거부됨"
            })
        else:
            return jsonify({"success": False, "message": "거부 처리 실패"})
    except Exception as e:
        return jsonify({"success": False, "message": f"오류: {e}"})


@app.route("/api/suggestions/stats")
def api_suggestion_stats():
    """매수 제안 통계"""
    try:
        suggestion_manager = BuySuggestionManager()
        stats = suggestion_manager.get_statistics()
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/virtual-balance/reset", methods=["POST"])
def api_reset_virtual_balance():
    """가상 잔고 리셋"""
    try:
        data = request.json or {}
        password = data.get("password", "")

        # 비밀번호 확인
        if password != "8864":
            return jsonify({"success": False, "message": "비밀번호가 올바르지 않습니다"})

        from config import AutoTraderConfig
        initial_cash = getattr(AutoTraderConfig, 'VIRTUAL_INITIAL_CASH', 100_000_000)

        logger = TradeLogger()
        logger.reset_virtual_balance(initial_cash)

        return jsonify({"success": True, "message": f"가상 잔고가 {initial_cash:,}원으로 리셋되었습니다"})
    except Exception as e:
        return jsonify({"success": False, "message": f"오류: {e}"})


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
