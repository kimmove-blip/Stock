import streamlit as st
import pandas as pd
import os
import time
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 모듈 가져오기
from dart_analyst import FundamentalAnalyst
from technical_analyst import TechnicalAnalyst
from sentiment_analyst import SentimentAnalyst
from stock_utils import get_kospi_top_list, get_all_krx_stocks, find_dart_code
from config import get_signal_kr, get_signal_description
import FinanceDataReader as fdr

# --- [설정] ---
load_dotenv()
st.set_page_config(page_title="AI 주식 분석", page_icon="📈", layout="wide")
WATCHLIST_FILE = "watchlist.json"

# --- [세션 상태 초기화] ---
defaults = {
    'page': 'home',
    'selected_stock': None,
    'analysis_result': None,
    'quick_result': None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- [스타일] ---
st.markdown("""
<style>
/* 기본 배경 */
.main { background-color: #0E1117; }
.block-container { padding-top: 1rem !important; padding-bottom: 3rem !important; }
header[data-testid="stHeader"] { display: none; }
#MainMenu { visibility: hidden; }

/* 전체 텍스트 가독성 향상 - 어두운 색으로 변경 */
.stMarkdown, .stText, p, span, div { color: #1a1a1a !important; }
.stApp { background-color: #f5f5f5 !important; }

/* 다크모드 강제 적용 해제 - 라이트모드 호환 */
.main { background-color: #f5f5f5 !important; }

/* 타이틀 */
.main-title {
    font-size: 28px; font-weight: 800;
    background: linear-gradient(90deg, #667eea, #764ba2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 5px;
}
.sub-title { font-size: 14px; color: #555 !important; margin-bottom: 20px; }

/* 검색 박스 강조 */
.search-container {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 25px;
    margin-bottom: 20px;
}
.search-title {
    font-size: 18px; font-weight: bold; color: #fff !important;
    margin-bottom: 15px;
}

/* 빠른 액션 카드 */
.quick-card {
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 15px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.quick-card:hover {
    border-color: #58a6ff;
    transform: translateY(-2px);
}
.quick-icon { font-size: 28px; margin-bottom: 8px; }
.quick-label { font-size: 13px; color: #333 !important; }

/* 결과 카드 */
.result-card {
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.stock-name { font-size: 16px; font-weight: bold; color: #1a1a1a !important; }
.stock-info { font-size: 13px; color: #333 !important; margin-top: 5px; }
.score-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: bold;
}
.score-high { background: #238636; color: white !important; }
.score-mid { background: #9e6a03; color: white !important; }
.score-low { background: #da3633; color: white !important; }

/* 티커 바 */
.ticker-bar {
    display: flex;
    justify-content: space-around;
    background-color: #1E1E1E;
    border: 1px solid #444;
    border-radius: 10px;
    padding: 15px 10px;
    margin-bottom: 15px;
}
.ticker-item { text-align: center; flex: 1; }
.ticker-label { font-size: 12px; color: #ccc !important; margin-bottom: 2px; }
.ticker-value { font-size: 18px; font-weight: bold; color: #fff !important; }
.ticker-sub { font-size: 12px; color: #7eb8ff !important; }

/* 분석 박스 */
.analysis-box {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 5px solid #238636;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 15px;
    line-height: 1.7;
    color: #1a1a1a !important;
}

/* 상세 정보 */
.detail-container {
    background-color: #fff;
    border-radius: 8px;
    padding: 15px;
    border: 1px solid #ddd;
}
.detail-category {
    font-size: 13px; font-weight: bold; color: #2563eb !important;
    margin-top: 12px; margin-bottom: 8px;
    border-bottom: 1px solid #e5e5e5; padding-bottom: 5px;
}
.detail-category:first-child { margin-top: 0; }
.detail-row {
    display: flex; justify-content: space-between;
    padding: 8px 0; border-bottom: 1px solid #f0f0f0;
}
.detail-row:last-child { border-bottom: none; }
.detail-label { font-size: 14px; color: #333 !important; }
.detail-value { font-size: 14px; font-weight: bold; color: #1a1a1a !important; }

/* 버튼 스타일 */
div.stButton > button {
    border-radius: 8px;
    font-weight: 500;
}

/* 탭 스타일 - 가독성 향상 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: #2d333b;
    padding: 5px;
    border-radius: 10px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 10px 20px;
    color: #fff !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #ffffff !important;
    background-color: #444c56;
}
.stTabs [aria-selected="true"] {
    color: #ffffff !important;
    background-color: #238636 !important;
}

/* Expander 스타일 */
.streamlit-expanderHeader {
    color: #1a1a1a !important;
    font-weight: 600;
}
.streamlit-expanderContent {
    color: #1a1a1a !important;
}

/* 메트릭 스타일 */
[data-testid="stMetricLabel"] {
    color: #555 !important;
}
[data-testid="stMetricValue"] {
    color: #1a1a1a !important;
}

/* Caption 스타일 */
.stCaption, small {
    color: #555 !important;
}

/* 입력 필드, 셀렉트박스 등 */
.stTextInput label, .stSelectbox label, .stSlider label {
    color: #1a1a1a !important;
}
.stTextInput input, .stSelectbox > div > div {
    color: #1a1a1a !important;
    background-color: #fff !important;
    border: 1px solid #ddd !important;
}

/* Alert 박스 (info, success, warning, error) */
.stAlert > div {
    color: #1a1a1a !important;
}

/* Streamlit 기본 요소들 */
.element-container {
    color: #1a1a1a !important;
}

/* 라디오, 체크박스 라벨 */
.stRadio label, .stCheckbox label {
    color: #1a1a1a !important;
}

/* 슬라이더 */
.stSlider > div > div > div {
    color: #1a1a1a !important;
}

/* Progress bar 텍스트 */
.stProgress > div > div {
    color: #1a1a1a !important;
}

/* st.info, st.success, st.warning 내부 텍스트 */
[data-testid="stNotification"] p,
[data-testid="stNotification"] span,
.stAlert p {
    color: #1a1a1a !important;
    font-weight: 500;
}

/* Markdown 텍스트 */
.stMarkdown p, .stMarkdown li, .stMarkdown span {
    color: #1a1a1a !important;
}

/* 사이드바 */
section[data-testid="stSidebar"] {
    background-color: #f0f0f0;
}
section[data-testid="stSidebar"] * {
    color: #1a1a1a !important;
}
</style>
""", unsafe_allow_html=True)

# --- [데이터 관리] ---
THEMES = {
    "2차전지": ["373220", "006400", "051910", "247540", "086520", "003670"],
    "AI/반도체": ["005930", "000660", "042700", "071050", "000210", "263750"],
    "바이오": ["207940", "068270", "000100", "128940", "302440"],
    "자동차": ["005380", "000270", "012330", "009900"],
    "플랫폼": ["035420", "035720", "251270", "036570"]
}

def load_watchlists():
    if not os.path.exists(WATCHLIST_FILE): return {"기본": []}
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"기본": data} if isinstance(data, list) else data
    except: return {"기본": []}

def save_watchlists(data):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def search_stocks(keyword):
    """종목 검색"""
    if not keyword: return []
    try:
        krx = get_all_krx_stocks()
        if krx is None: return []

        # 코드 정확 매칭
        code_match = krx[krx['Code'] == keyword]
        if not code_match.empty:
            r = code_match.iloc[0]
            return [{"code": r['Code'], "name": r['Name']}]

        # 이름 검색
        mask = krx['Name'].str.contains(keyword, case=False, na=False)
        results = []
        for _, r in krx[mask].head(20).iterrows():
            results.append({"code": r['Code'], "name": r['Name']})
        return results
    except:
        return []

def get_screening_targets(mode, limit=20):
    targets = []
    try:
        if mode == "급등락":
            df = fdr.StockListing("KRX")
            col = 'ChagesRatio' if 'ChagesRatio' in df.columns else 'ChangeRate'
            vol = df[abs(df[col]) >= 5].sort_values('Amount', ascending=False).head(limit)
            for _, r in vol.iterrows():
                targets.append({"code": str(r['Code']), "name": r['Name']})
        elif mode in ["KOSPI", "KOSDAQ"]:
            df = fdr.StockListing(mode).sort_values('Marcap', ascending=False).head(limit)
            for _, r in df.iterrows():
                targets.append({"code": str(r['Code']), "name": r['Name']})
        elif mode in THEMES:
            krx = get_all_krx_stocks()
            for c in THEMES[mode]:
                f = krx[krx['Code'] == c]
                if not f.empty:
                    targets.append({"code": c, "name": f.iloc[0]['Name']})
    except: pass
    return targets

# --- [분석 엔진] ---
@st.cache_resource(ttl=3600)  # 1시간마다 새로 로드
def load_analysts():
    return FundamentalAnalyst(os.getenv("DART_API_KEY", "")), TechnicalAnalyst(), SentimentAnalyst()

def run_analysis(stock, fund, tech, sent):
    res = {
        "name": stock['name'], "code": stock['code'],
        "score": 0, "grade": "N/A",
        "price": 0, "change": 0.0, "target": 0,
        "f_score": 0, "t_score": 0, "s_score": 0,
        "reasons": [], "f_details": {}, "t_details": {}, "s_details": {},
        "signals": [], "patterns": []
    }

    dart = stock.get('dart') or find_dart_code(stock['code'])

    # 1. 재무
    if dart:
        try:
            fd = fund.get_financials(dart, "2023")
            if fd:
                res['f_score'], f_reasons, res['f_details'] = fund.analyze(fd)
                res['reasons'].extend(f_reasons[:2])
        except: pass

    # 2. 차트 (전체 기술적 분석 적용)
    try:
        td = tech.get_ohlcv(stock['code'])
        if td is not None and len(td) >= 60:
            full_result = tech.analyze_full(td)

            if full_result:
                # 기술적 점수 (60점 만점으로 정규화)
                raw_score = full_result.get('score', 0)
                res['t_score'] = min(60, max(0, int(raw_score * 0.6)))

                # 신호 및 패턴
                signals = full_result.get('signals', [])
                patterns = full_result.get('patterns', [])
                indicators = full_result.get('indicators', {})

                res['signals'] = signals
                res['patterns'] = patterns

                # 가격 정보
                close_price = indicators.get('close', 0)
                res['price'] = int(close_price) if close_price else 0
                change_pct = indicators.get('change_pct', 0)
                res['change'] = round(float(change_pct), 2) if change_pct else 0.0

                # 상세 정보
                res['t_details'] = {
                    '현재가': f"{res['price']:,}원",
                    '등락률': res['change'],
                    'RSI': f"{indicators.get('rsi', 0):.1f}" if indicators.get('rsi') else '-',
                    'MACD': f"{indicators.get('macd', 0):.2f}" if indicators.get('macd') else '-',
                    'ADX': f"{indicators.get('adx', 0):.1f}" if indicators.get('adx') else '-',
                    'MFI': f"{indicators.get('mfi', 0):.1f}" if indicators.get('mfi') else '-',
                    '거래량배율': f"{indicators.get('volume_ratio', 0):.1f}x" if indicators.get('volume_ratio') else '-',
                }

                # 신호를 한글로 변환하여 reasons에 추가
                for sig in signals[:3]:
                    sig_kr = get_signal_kr(sig)
                    if sig_kr != sig:  # 한글 변환된 경우만
                        res['reasons'].append(f"📊 {sig_kr}")

                # 패턴 추가
                for pat in patterns[:2]:
                    res['reasons'].append(f"🕯️ {pat} 패턴 감지")
    except Exception as e:
        res['reasons'].append(f"⚠️ 차트 분석 오류: {str(e)[:30]}")

    # 3. 심리
    try:
        n, nr, _ = sent.get_news_sentiment(stock['code'])
        d, dr, _ = sent.get_discussion_buzz(stock['code'])
        res['s_score'] = max(0, min(20, 10 + n + d))
        res['s_details'] = {"뉴스": n, "토론": d}
        if nr: res['reasons'].append(nr[0])
    except: pass

    # 종합
    total = res['f_score'] + res['t_score'] + res['s_score']
    if not dart or res['f_score'] == 0:
        total = int((res['t_score'] + res['s_score']) * (100 / 80))
    res['score'] = total

    if total >= 80: res['grade'], mul = "강력매수", 1.2
    elif total >= 60: res['grade'], mul = "매수", 1.1
    elif total >= 40: res['grade'], mul = "관망", 1.05
    else: res['grade'], mul = "매도", 1.0

    res['target'] = int(res['price'] * mul)
    return res

# --- [UI 컴포넌트] ---
def show_stock_card(stock, show_action=True, key_suffix=""):
    """종목 결과 카드"""
    score = stock['score']
    if score >= 70: badge_class = "score-high"
    elif score >= 50: badge_class = "score-mid"
    else: badge_class = "score-low"

    grade_emoji = {"강력매수": "💎", "매수": "💰", "관망": "🤔", "매도": "📉"}.get(stock['grade'], "")
    change_color = "#ff4b4b" if stock['change'] > 0 else "#4b89ff" if stock['change'] < 0 else "#888"

    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"""
        <div class="result-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span class="stock-name">{stock['name']}</span>
                    <span style="color:#666; font-size:12px; margin-left:8px;">{stock['code']}</span>
                </div>
                <span class="score-badge {badge_class}">{score}점 {grade_emoji}</span>
            </div>
            <div class="stock-info">
                현재가 <b style="color:#1a1a1a">{stock['price']:,}원</b>
                <span style="color:{change_color}; margin-left:10px;">{stock['change']:+.2f}%</span>
                <span style="margin-left:15px;">목표가 <b style="color:#238636">{stock['target']:,}원</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        if show_action:
            unique_key = f"detail_{stock['code']}_{key_suffix}" if key_suffix else f"detail_{stock['code']}_{id(stock)}"
            if st.button("상세보기", key=unique_key, use_container_width=True):
                st.session_state['selected_stock'] = stock
                st.session_state['page'] = 'detail'
                st.rerun()

def show_detail_page(stock):
    """상세 페이지"""
    if st.button("← 뒤로가기", type="secondary"):
        st.session_state['page'] = 'home'
        st.session_state['selected_stock'] = None
        st.rerun()

    st.markdown(f"## {stock['name']} ({stock['code']})")

    # 티커 바
    change_color = "#ff4b4b" if stock['change'] > 0 else "#4b89ff" if stock['change'] < 0 else "#888"
    grade_emoji = {"강력매수": "💎", "매수": "💰", "관망": "🤔", "매도": "📉"}.get(stock['grade'], "")

    st.markdown(f"""
    <div class="ticker-bar">
        <div class="ticker-item">
            <div class="ticker-label">현재가</div>
            <div class="ticker-value">{stock['price']:,}</div>
            <div class="ticker-sub" style="color:{change_color}">{stock['change']:+.2f}%</div>
        </div>
        <div class="ticker-item">
            <div class="ticker-label">목표가</div>
            <div class="ticker-value" style="color:#4CAF50">{stock['target']:,}</div>
            <div class="ticker-sub">AI 예측</div>
        </div>
        <div class="ticker-item">
            <div class="ticker-label">종합점수</div>
            <div class="ticker-value">{stock['score']}점</div>
            <div class="ticker-sub">{grade_emoji} {stock['grade']}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # AI 분석 의견
    reasons_html = "<br>".join([f"• {r}" for r in stock['reasons'][:5]]) if stock['reasons'] else "분석 데이터 수집 중..."
    st.markdown(f"""
    <div class="analysis-box">
        <div style="color:#58a6ff; font-weight:bold; margin-bottom:10px;">🤖 AI 투자 포인트</div>
        {reasons_html}
    </div>
    """, unsafe_allow_html=True)

    # 차트
    st.markdown("#### 📊 주가 차트")
    fig = draw_chart(stock['code'])
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})

    # 기술적 신호
    signals = stock.get('signals', [])
    patterns = stock.get('patterns', [])
    if signals or patterns:
        with st.expander("📊 기술적 신호 분석", expanded=True):
            if signals:
                st.markdown("**매매 신호:**")
                for sig in signals[:6]:
                    sig_kr = get_signal_kr(sig)
                    sig_desc = get_signal_description(sig)
                    # 매수/주의 신호 구분
                    if any(x in sig for x in ['OVERBOUGHT', 'DEAD', 'OUTFLOW', 'BEARISH', 'EVENING']):
                        st.warning(f"**{sig_kr}**\n\n{sig_desc}")
                    else:
                        st.success(f"**{sig_kr}**\n\n{sig_desc}")
            if patterns:
                st.markdown("**캔들 패턴:**")
                for pat in patterns[:3]:
                    pat_desc = get_signal_description(pat)
                    st.info(f"**{pat}**: {pat_desc}" if pat_desc else f"**{pat}**")

    # 상세 점수
    with st.expander("📋 상세 채점표", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("재무 점수", f"{stock['f_score']}/20")
            for k, v in stock.get('f_details', {}).items():
                st.caption(f"{k}: {v}")
        with c2:
            st.metric("차트 점수", f"{stock['t_score']}/60")
            for k, v in list(stock.get('t_details', {}).items()):
                st.caption(f"{k}: {v}")
        with c3:
            st.metric("심리 점수", f"{stock['s_score']}/20")
            for k, v in stock.get('s_details', {}).items():
                st.caption(f"{k}: {v}점")

    # 관심종목 추가
    watchlists = load_watchlists()
    with st.expander("⭐ 관심종목에 추가"):
        list_name = st.selectbox("리스트 선택", list(watchlists.keys()), label_visibility="collapsed")
        if st.button("추가하기", type="primary"):
            if not any(s['code'] == stock['code'] for s in watchlists[list_name]):
                watchlists[list_name].append({"code": stock['code'], "name": stock['name']})
                save_watchlists(watchlists)
                st.success(f"'{list_name}'에 추가했습니다!")
            else:
                st.info("이미 추가된 종목입니다.")

def draw_chart(code):
    """주가 차트"""
    try:
        df = fdr.DataReader(code, datetime.now() - timedelta(days=180), datetime.now())
        if df.empty: return go.Figure()
    except: return go.Figure()

    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='주가', increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1), name='5일'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='purple', width=1), name='20일'), row=1, col=1)

    colors = ['#ef4444' if c >= o else '#3b82f6' for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

    fig.update_layout(
        height=350, margin=dict(l=0, r=0, t=10, b=10),
        plot_bgcolor='#1E1E1E', paper_bgcolor='#1E1E1E',
        font=dict(color='white'), showlegend=False,
        xaxis_rangeslider_visible=False
    )
    fig.update_xaxes(showgrid=True, gridcolor='#333', rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(showgrid=True, gridcolor='#333', tickformat=",")

    return fig

# ============== 메인 UI ==============

# 상세 페이지
if st.session_state['page'] == 'detail' and st.session_state['selected_stock']:
    show_detail_page(st.session_state['selected_stock'])

# 홈 페이지
else:
    st.markdown("<div class='main-title'>📈 AI 주식 분석</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>종목을 검색하거나 AI 추천을 받아보세요</div>", unsafe_allow_html=True)

    # === 메인 탭 ===
    tab1, tab2, tab3 = st.tabs(["🔍 종목 검색", "🏆 AI 추천", "⭐ 관심종목"])

    # --- 탭1: 종목 검색 ---
    with tab1:
        st.markdown("""
        <div class="search-container">
            <div class="search-title">🔍 종목명 또는 코드로 검색</div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([4, 1])
        with col1:
            keyword = st.text_input("검색", placeholder="예: 삼성전자, 005930, 카카오...", label_visibility="collapsed")
        with col2:
            search_btn = st.button("검색", type="primary", use_container_width=True)

        if keyword or search_btn:
            results = search_stocks(keyword)
            if results:
                st.markdown(f"**{len(results)}개 종목 검색됨**")

                # 검색 결과에서 바로 분석
                selected = st.selectbox(
                    "분석할 종목 선택",
                    options=range(len(results)),
                    format_func=lambda i: f"{results[i]['name']} ({results[i]['code']})",
                    label_visibility="collapsed"
                )

                if st.button("🚀 이 종목 분석하기", type="primary"):
                    with st.spinner(f"{results[selected]['name']} 분석 중..."):
                        fund, tech, sent = load_analysts()
                        result = run_analysis(results[selected], fund, tech, sent)
                        st.session_state['quick_result'] = result

                # 빠른 분석 결과
                if st.session_state.get('quick_result'):
                    st.markdown("---")
                    st.markdown("### 분석 결과")
                    show_stock_card(st.session_state['quick_result'], key_suffix="quick")
            else:
                st.warning("검색 결과가 없습니다.")

    # --- 탭2: AI 추천 ---
    with tab2:
        st.markdown("### 🏆 AI 종목 스크리닝")
        st.caption("조건에 맞는 종목을 찾아 AI가 분석합니다")

        col1, col2 = st.columns(2)
        with col1:
            screen_type = st.selectbox(
                "스크리닝 조건",
                ["KOSPI 시총 상위", "KOSDAQ 시총 상위", "전일 급등락"] + [f"테마: {t}" for t in THEMES.keys()]
            )
        with col2:
            limit = st.slider("분석 종목 수", 5, 30, 10)

        if st.button("🔍 스크리닝 시작", type="primary", use_container_width=True):
            # 조건에 따른 종목 가져오기
            if "KOSPI" in screen_type:
                targets = get_screening_targets("KOSPI", limit)
            elif "KOSDAQ" in screen_type:
                targets = get_screening_targets("KOSDAQ", limit)
            elif "급등락" in screen_type:
                targets = get_screening_targets("급등락", limit)
            else:
                theme = screen_type.replace("테마: ", "")
                targets = get_screening_targets(theme, limit)

            if targets:
                fund, tech, sent = load_analysts()
                progress = st.progress(0)
                status = st.empty()
                results = []

                for i, stock in enumerate(targets):
                    status.text(f"분석 중: {stock['name']} ({i+1}/{len(targets)})")
                    results.append(run_analysis(stock, fund, tech, sent))
                    progress.progress((i + 1) / len(targets))

                progress.empty()
                status.empty()

                # 점수순 정렬
                results.sort(key=lambda x: x['score'], reverse=True)
                st.session_state['analysis_result'] = results
                st.rerun()
            else:
                st.warning("조건에 맞는 종목이 없습니다.")

        # 스크리닝 결과 표시
        if st.session_state.get('analysis_result'):
            st.markdown("---")
            st.markdown(f"### 📊 분석 결과 ({len(st.session_state['analysis_result'])}개)")

            for i, stock in enumerate(st.session_state['analysis_result']):
                show_stock_card(stock, key_suffix=f"screen_{i}")

    # --- 탭3: 관심종목 ---
    with tab3:
        watchlists = load_watchlists()

        col1, col2 = st.columns([3, 1])
        with col1:
            current_list = st.selectbox("관심종목 리스트", list(watchlists.keys()), label_visibility="collapsed")
        with col2:
            with st.popover("⚙️ 관리"):
                new_name = st.text_input("새 리스트 이름")
                if st.button("리스트 생성"):
                    if new_name and new_name not in watchlists:
                        watchlists[new_name] = []
                        save_watchlists(watchlists)
                        st.rerun()
                if current_list != "기본":
                    if st.button("현재 리스트 삭제", type="secondary"):
                        del watchlists[current_list]
                        save_watchlists(watchlists)
                        st.rerun()

        stocks = watchlists.get(current_list, [])

        if not stocks:
            st.info("관심종목이 없습니다. 종목 검색 후 추가해보세요!")
        else:
            st.markdown(f"**{len(stocks)}개 종목**")

            if st.button("🚀 전체 분석", type="primary"):
                fund, tech, sent = load_analysts()
                progress = st.progress(0)
                results = []

                for i, stock in enumerate(stocks):
                    results.append(run_analysis(stock, fund, tech, sent))
                    progress.progress((i + 1) / len(stocks))

                progress.empty()
                results.sort(key=lambda x: x['score'], reverse=True)
                st.session_state['analysis_result'] = results
                st.rerun()

            # 종목 목록
            for stock in stocks:
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{stock['name']}** `{stock['code']}`")
                with col2:
                    if st.button("삭제", key=f"del_{stock['code']}"):
                        watchlists[current_list] = [s for s in stocks if s['code'] != stock['code']]
                        save_watchlists(watchlists)
                        st.rerun()

            # 분석 결과 표시
            if st.session_state.get('analysis_result'):
                st.markdown("---")
                st.markdown("### 📊 분석 결과")
                for i, stock in enumerate(st.session_state['analysis_result']):
                    show_stock_card(stock, key_suffix=f"watch_{i}")
