import streamlit as st
import pandas as pd
import os
import time
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 인증 및 DB 모듈 (가벼움)
from auth import StockAuthenticator
from database import DatabaseManager
from config import get_signal_kr, get_signal_description

# 무거운 모듈은 lazy import (필요할 때만 로드)
def get_analysts():
    """분석 모듈 lazy import"""
    if 'analysts_loaded' not in st.session_state:
        from dart_analyst import FundamentalAnalyst
        from technical_analyst import TechnicalAnalyst
        from sentiment_analyst import SentimentAnalyst
        st.session_state['FundamentalAnalyst'] = FundamentalAnalyst
        st.session_state['TechnicalAnalyst'] = TechnicalAnalyst
        st.session_state['SentimentAnalyst'] = SentimentAnalyst
        st.session_state['analysts_loaded'] = True
    return (st.session_state['FundamentalAnalyst'],
            st.session_state['TechnicalAnalyst'],
            st.session_state['SentimentAnalyst'])

def get_stock_utils():
    """주식 유틸 lazy import"""
    if 'stock_utils_loaded' not in st.session_state:
        from stock_utils import get_kospi_top_list, get_all_krx_stocks, find_dart_code
        st.session_state['get_kospi_top_list'] = get_kospi_top_list
        st.session_state['get_all_krx_stocks'] = get_all_krx_stocks
        st.session_state['find_dart_code'] = find_dart_code
        st.session_state['stock_utils_loaded'] = True
    return (st.session_state['get_kospi_top_list'],
            st.session_state['get_all_krx_stocks'],
            st.session_state['find_dart_code'])

def get_fdr():
    """FinanceDataReader lazy import"""
    if 'fdr' not in st.session_state:
        import FinanceDataReader as fdr
        st.session_state['fdr'] = fdr
    return st.session_state['fdr']

def get_plotly():
    """Plotly lazy import"""
    if 'plotly_loaded' not in st.session_state:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        st.session_state['go'] = go
        st.session_state['make_subplots'] = make_subplots
        st.session_state['plotly_loaded'] = True
    return st.session_state['go'], st.session_state['make_subplots']

# --- [설정] ---
load_dotenv()
st.set_page_config(page_title="Kim's AI 주식 분석", page_icon="📈", layout="wide")

# 애플 홈 화면 아이콘 설정 (JavaScript로 head에 추가)
st.markdown("""
<script>
(function() {
    if (!document.querySelector('link[rel="apple-touch-icon"]')) {
        var link = document.createElement('link');
        link.rel = 'apple-touch-icon';
        link.href = '/app/static/apple-touch-icon.png';
        document.head.appendChild(link);

        var meta1 = document.createElement('meta');
        meta1.name = 'apple-mobile-web-app-capable';
        meta1.content = 'yes';
        document.head.appendChild(meta1);

        var meta2 = document.createElement('meta');
        meta2.name = 'apple-mobile-web-app-title';
        meta2.content = 'AI주식분석';
        document.head.appendChild(meta2);
    }
})();
</script>
""", unsafe_allow_html=True)

WATCHLIST_FILE = "watchlist.json"

# --- [인증 시스템 초기화] ---
# session_state로 관리 (캐시 사용 시 위젯 경고 발생)
def get_auth():
    if 'auth' not in st.session_state:
        st.session_state['auth'] = StockAuthenticator()
    return st.session_state['auth']

@st.cache_resource
def get_db():
    return DatabaseManager()

auth = get_auth()
db = get_db()

# --- [세션 상태 초기화] ---
defaults = {
    'page': 'home',
    'selected_stock': None,
    'analysis_result': None,
    'quick_result': None,
    'previous_tab': 0,  # 이전 탭 인덱스
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- [스타일] ---
st.markdown("""
<style>

/* 기본 배경 */
.main { background-color: #0E1117; }
.block-container { padding-top: 0 !important; padding-bottom: 3rem !important; margin-top: 0 !important; }
[data-testid="stAppViewContainer"] { padding-top: 0 !important; }
[data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
.main > div:first-child { padding-top: 0 !important; }
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
    padding: 15px 20px;
    margin-bottom: 10px;
}
.search-title {
    font-size: 18px; font-weight: bold; color: #fff !important;
    margin-bottom: 0;
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
    background-color: #e8eaed;
    position: relative;
    overflow-x: auto;
    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;
}
/* 탭 스크롤 힌트 (좌우 그라데이션) */
.stTabs [data-baseweb="tab-list"]::before,
.stTabs [data-baseweb="tab-list"]::after {
    content: '';
    position: sticky;
    top: 0;
    bottom: 0;
    width: 30px;
    min-width: 30px;
    pointer-events: none;
    z-index: 10;
}
.stTabs [data-baseweb="tab-list"]::before {
    left: 0;
    background: linear-gradient(to right, #e8eaed 30%, transparent);
}
.stTabs [data-baseweb="tab-list"]::after {
    right: 0;
    background: linear-gradient(to left, #e8eaed 30%, transparent);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 12px 24px;
    color: #333 !important;
    font-weight: 600 !important;
    background-color: transparent;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #1a1a1a !important;
    background-color: #fff;
}
.stTabs [aria-selected="true"] {
    color: #fff !important;
    background-color: #4a7c59 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.15);
}
/* 탭 내부 텍스트 강제 적용 */
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span {
    color: inherit !important;
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
    "2차전지": ["373220", "006400", "051910", "247540", "086520", "003670", "096770", "012450", "298040", "064350"],
    "AI/반도체": ["005930", "000660", "042700", "071050", "000210", "263750", "058470", "036930", "035420", "017670"],
    "바이오": ["207940", "068270", "000100", "128940", "302440", "145020", "141080", "357780", "096530", "091990"],
    "자동차/전기차": ["005380", "000270", "012330", "161390", "018880", "011210", "204320", "064350", "317280", "900140"],
    "조선/해운": ["010140", "009540", "042660", "329180", "011200", "010620", "005880", "028670", "003490"],
    "방산/우주항공": ["012450", "047810", "000880", "001340", "006260", "071970", "032350", "103140", "298040"],
    "로봇/자동화": ["267260", "090460", "108320", "336370", "049800", "090470", "064290", "404950", "278280"],
    "엔터/미디어": ["352820", "122870", "060300", "035900", "035420", "041510", "035760", "067160", "293480"],
    "게임": ["036570", "251270", "263750", "112040", "078340", "194480", "069080", "348830"],
    "금융/은행": ["105560", "055550", "086790", "024110", "316140", "138930", "003550", "000810"],
    "건설/인프라": ["000720", "047040", "000210", "006360", "034220", "035150", "004220", "002380"],
    "화장품/소비재": ["090430", "003600", "377300", "285130", "263060", "348210", "214150", "069960"],
    "친환경/ESG": ["117580", "336260", "281740", "282690", "099220", "290650", "095700", "012320"],
    "음식료": ["097950", "271560", "005180", "280360", "004370", "007310", "014680", "033780"],
    "플랫폼/IT": ["035420", "035720", "251270", "036570", "030200", "017670", "259960", "053800"],
}

def load_watchlists_db(user_id):
    """사용자별 관심종목 로드 (DB)"""
    if not user_id:
        return {"기본": []}
    watchlists = db.get_watchlists(user_id)
    # DB 결과를 기존 형식으로 변환
    result = {}
    for item in watchlists:
        category = item['category']
        if category not in result:
            result[category] = []
        result[category].append({
            'code': item['stock_code'],
            'name': item['stock_name']
        })
    if not result:
        result = {"기본": []}
    return result

def add_to_watchlist_db(user_id, category, code, name):
    """관심종목 추가 (DB)"""
    return db.add_to_watchlist(user_id, category, code, name)

def remove_from_watchlist_db(user_id, category, code):
    """관심종목 삭제 (DB)"""
    db.remove_from_watchlist(user_id, category, code)

# 기존 파일 기반 함수 (마이그레이션용으로 유지)
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
        _, get_all_krx, _ = get_stock_utils()
        krx = get_all_krx()
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
        fdr = get_fdr()
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
            _, get_all_krx, _ = get_stock_utils()
            krx = get_all_krx()
            for c in THEMES[mode]:
                f = krx[krx['Code'] == c]
                if not f.empty:
                    targets.append({"code": c, "name": f.iloc[0]['Name']})
    except: pass
    return targets

# --- [분석 엔진] ---
@st.cache_resource(ttl=3600)  # 1시간마다 새로 로드
def load_analysts():
    FundamentalAnalyst, TechnicalAnalyst, SentimentAnalyst = get_analysts()
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

    _, _, find_dart = get_stock_utils()
    dart = stock.get('dart') or find_dart(stock['code'])

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

    col1, col2 = st.columns([5, 1])
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
            if st.button("🔍", key=unique_key, help="상세보기"):
                # 이전 탭 저장 (key_suffix로 판단)
                if key_suffix.startswith("quick"):
                    st.session_state['previous_tab'] = 0
                elif key_suffix.startswith("screen"):
                    st.session_state['previous_tab'] = 1
                elif key_suffix.startswith("watch"):
                    st.session_state['previous_tab'] = 2
                else:
                    st.session_state['previous_tab'] = 0
                st.session_state['selected_stock'] = stock
                st.session_state['page'] = 'detail'
                st.rerun()

def show_detail_page(stock):
    """상세 페이지"""
    if st.button("← 뒤로가기", type="secondary"):
        # 이전 탭으로 돌아가기 (JavaScript로 탭 클릭)
        tab_idx = st.session_state.get('previous_tab', 0)
        st.markdown(f"""
        <script>
        setTimeout(function() {{
            var tabs = document.querySelectorAll('[data-baseweb="tab"]');
            if (tabs && tabs[{tab_idx}]) tabs[{tab_idx}].click();
        }}, 100);
        </script>
        """, unsafe_allow_html=True)
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

    # 관심종목 추가 (로그인 사용자 - 게스트 포함)
    is_logged_in = st.session_state.get('authentication_status', False)
    is_guest_user = st.session_state.get('is_guest', False)
    current_user_id = auth.get_user_id()

    if is_logged_in:
        if is_guest_user:
            if 'guest_watchlists' not in st.session_state:
                st.session_state['guest_watchlists'] = {"기본": []}
            watchlists = st.session_state['guest_watchlists']
        else:
            watchlists = load_watchlists_db(current_user_id)

        with st.expander("⭐ 관심종목에 추가"):
            # 카테고리 목록 + 새 카테고리 입력
            categories = list(watchlists.keys())
            list_name = st.selectbox("리스트 선택", categories, label_visibility="collapsed")
            new_category = st.text_input("또는 새 리스트 이름", placeholder="새 리스트 만들기")

            if st.button("추가하기", type="primary"):
                target_category = new_category if new_category else list_name
                if is_guest_user:
                    # 게스트용 세션 기반 관심종목 추가
                    if target_category not in st.session_state['guest_watchlists']:
                        st.session_state['guest_watchlists'][target_category] = []
                    existing_codes = [s['code'] for s in st.session_state['guest_watchlists'][target_category]]
                    if stock['code'] not in existing_codes:
                        st.session_state['guest_watchlists'][target_category].append({
                            'code': stock['code'],
                            'name': stock['name']
                        })
                        st.success(f"'{target_category}'에 추가했습니다!")
                    else:
                        st.info("이미 추가된 종목입니다.")
                else:
                    if add_to_watchlist_db(current_user_id, target_category, stock['code'], stock['name']):
                        st.success(f"'{target_category}'에 추가했습니다!")
                    else:
                        st.info("이미 추가된 종목입니다.")

def draw_chart(code):
    """주가 차트"""
    go, make_subplots = get_plotly()
    fdr = get_fdr()
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

# ============== 로그인/회원가입 페이지 ==============

def show_login_page():
    """로그인/회원가입 페이지"""
    st.markdown("<div class='main-title'>📈 Kim's AI 주식 분석</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>로그인 후 이용해주세요</div>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔐 로그인", "📝 회원가입"])

    with tab1:
        auth.login()

        if st.session_state.get('authentication_status') == False:
            st.error("아이디 또는 비밀번호가 잘못되었습니다.")

        # 게스트 로그인
        st.markdown("---")
        if st.button("👤 게스트로 둘러보기", use_container_width=True):
            st.session_state['authentication_status'] = True
            st.session_state['username'] = 'guest'
            st.session_state['name'] = '게스트'
            st.session_state['is_guest'] = True
            st.rerun()

    with tab2:
        success, msg = auth.register_user()
        if success:
            st.success(msg)
            st.info("로그인 탭에서 로그인해주세요.")
        elif msg:
            st.error(msg)

# --- [인증 체크] ---
if not auth.is_authenticated:
    show_login_page()
    st.stop()

# 로그인된 사용자 정보
is_guest = st.session_state.get('is_guest', False)
if is_guest:
    user_id = None
    user_name = "게스트"
else:
    user_id = auth.get_user_id()
    user_name = auth.current_name or "사용자"

# ============== 메인 UI ==============

# 상세 페이지
if st.session_state['page'] == 'detail' and st.session_state['selected_stock']:
    show_detail_page(st.session_state['selected_stock'])

# 홈 페이지
else:
    # 오른쪽 상단: 사용자 이름 (제일 위)
    st.markdown("""<style>[data-testid="stPopover"] button { white-space: nowrap !important; }</style>""", unsafe_allow_html=True)
    _, btn_user = st.columns([3, 1])
    with btn_user:
        with st.popover(f"👤{user_name[:3]}"):
            # 게스트가 아닌 경우에만 설정 표시
            if not is_guest:
                menu_tab = st.radio("", ["로그아웃", "📱 텔레그램 알림"], label_visibility="collapsed", horizontal=True)
            else:
                menu_tab = "로그아웃"

            if menu_tab == "로그아웃":
                st.write("로그아웃 하시겠습니까?")
                if st.button("로그아웃", type="primary", use_container_width=True):
                    # 쿠키 삭제 (JavaScript)
                    st.markdown("""
                    <script>
                    document.cookie = 'stock_auth_cookie=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
                    </script>
                    """, unsafe_allow_html=True)
                    # session_state 초기화
                    st.session_state['authentication_status'] = None
                    st.session_state['username'] = None
                    st.session_state['name'] = None
                    st.session_state['logout'] = True
                    st.rerun()

            elif menu_tab == "📱 텔레그램 알림":
                st.markdown("#### 하락 알림 설정")

                # 현재 설정 조회
                current_user_id = auth.get_user_id()
                telegram_settings = db.get_telegram_settings(current_user_id) if current_user_id else {'chat_id': '', 'enabled': False}

                # 이미 연동된 경우
                if telegram_settings['chat_id']:
                    st.success(f"✅ 연동됨: {telegram_settings['chat_id']}")
                    enabled_input = st.toggle("알림 활성화", value=telegram_settings['enabled'], key="telegram_enabled_toggle")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("📤 테스트 전송", use_container_width=True):
                            from telegram_notifier import TelegramNotifier
                            notifier = TelegramNotifier()
                            if notifier.verify_chat_id(telegram_settings['chat_id']):
                                st.success("✅ 전송됨!")
                            else:
                                st.error("❌ 실패")
                    with col2:
                        if st.button("🔄 재연동", use_container_width=True):
                            db.update_telegram_settings(current_user_id, '', False)
                            st.rerun()

                    # 활성화 상태 변경 시 자동 저장
                    if enabled_input != telegram_settings['enabled']:
                        db.update_telegram_settings(current_user_id, telegram_settings['chat_id'], enabled_input)
                        st.rerun()

                # 연동 안 된 경우
                else:
                    st.markdown("""
**연동 방법:**
1. 아래 링크 클릭 → 텔레그램 봇 열기
2. **시작** 버튼 누르기
3. **연동 확인** 버튼 클릭
                    """)

                    # 텔레그램 봇 링크
                    st.link_button("📱 텔레그램 봇 열기", "https://t.me/fa_hckim0402_bot", use_container_width=True)

                    # 연동 확인 버튼
                    if st.button("🔗 연동 확인", type="primary", use_container_width=True):
                        from telegram_notifier import TelegramNotifier
                        from config import TelegramConfig
                        import requests

                        # getUpdates로 최근 메시지 확인
                        try:
                            response = requests.get(
                                f"https://api.telegram.org/bot{TelegramConfig.BOT_TOKEN}/getUpdates",
                                timeout=10
                            )
                            data = response.json()
                            if data.get('ok') and data.get('result'):
                                # 가장 최근 메시지의 chat_id
                                latest = data['result'][-1]
                                chat_id = str(latest['message']['chat']['id'])
                                user_name = latest['message']['from'].get('first_name', '')

                                # 저장 및 테스트 메시지 전송
                                db.update_telegram_settings(current_user_id, chat_id, True)
                                notifier = TelegramNotifier()
                                notifier.send_message(chat_id, f"🎉 {user_name}님, 연동 완료!\n포트폴리오 하락 알림을 받으실 수 있습니다.")
                                st.success(f"✅ 연동 완료! ({user_name})")
                                st.rerun()
                            else:
                                st.warning("⚠️ 봇에 메시지를 보내주세요")
                        except Exception as e:
                            st.error(f"❌ 연동 실패: {e}")

    # 상단 헤더
    st.markdown("<div class='main-title'>📈 Kim's AI 주식 분석</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>종목을 검색하거나 AI 추천을 받아보세요</div>", unsafe_allow_html=True)

    # === 메인 탭 ===
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 종목 검색", "🏆 AI 추천", "⭐ 관심종목", "💼 내 포트폴리오"])

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
        if is_guest:
            st.caption("💡 게스트 모드: 데이터는 세션 종료 시 사라집니다.")
            # 게스트용 세션 기반 관심종목
            if 'guest_watchlists' not in st.session_state:
                st.session_state['guest_watchlists'] = {"기본": []}
            watchlists = st.session_state['guest_watchlists']
        else:
            watchlists = load_watchlists_db(user_id)

        col1, col2 = st.columns([3, 1])
        with col1:
            current_list = st.selectbox("관심종목 리스트", list(watchlists.keys()), label_visibility="collapsed")
        with col2:
            with st.popover("⚙️ 관리"):
                new_name = st.text_input("새 리스트 이름")
                if st.button("리스트 생성"):
                    if new_name and new_name not in watchlists:
                        if is_guest:
                            st.session_state['guest_watchlists'][new_name] = []
                            st.success(f"'{new_name}' 리스트 생성됨")
                            st.rerun()
                        else:
                            st.info(f"'{new_name}' 리스트가 준비되었습니다. 종목을 추가하면 생성됩니다.")
                            st.session_state['new_category'] = new_name
                if current_list != "기본":
                    if st.button("현재 리스트 삭제", type="secondary"):
                        if is_guest:
                            del st.session_state['guest_watchlists'][current_list]
                        else:
                            db.delete_watchlist_category(user_id, current_list)
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
                        if is_guest:
                            st.session_state['guest_watchlists'][current_list] = [
                                s for s in st.session_state['guest_watchlists'][current_list]
                                if s['code'] != stock['code']
                            ]
                        else:
                            remove_from_watchlist_db(user_id, current_list, stock['code'])
                        st.rerun()

            # 분석 결과 표시
            if st.session_state.get('analysis_result'):
                st.markdown("---")
                st.markdown("### 📊 분석 결과")
                for i, stock in enumerate(st.session_state['analysis_result']):
                    show_stock_card(stock, key_suffix=f"watch_{i}")

    # --- 탭4: 내 포트폴리오 ---
    with tab4:
        if is_guest:
            st.caption("💡 게스트 모드: 데이터는 세션 종료 시 사라집니다.")
            # 게스트용 세션 기반 포트폴리오
            if 'guest_portfolio' not in st.session_state:
                st.session_state['guest_portfolio'] = []
            portfolio_items = st.session_state['guest_portfolio']
        else:
            # DB에서 포트폴리오 로드
            portfolio_items = db.get_portfolio(user_id)

        # 새로고침 버튼으로 분석 시작 요청된 경우
        if st.session_state.get('run_portfolio_analysis') and portfolio_items:
            st.session_state['run_portfolio_analysis'] = False
            from portfolio_advisor import PortfolioAdvisor
            advisor = PortfolioAdvisor()
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            total = len(portfolio_items)
            for idx, item in enumerate(portfolio_items):
                code = item['stock_code']
                name = item['stock_name'] or code
                buy_price = float(item['buy_price'])
                status_text.text(f"분석 중: {name} ({idx+1}/{total})")
                analysis = advisor.analyze_stock(code, buy_price)
                if analysis:
                    results.append({
                        'code': code, 'name': name, 'buy_price': buy_price,
                        'quantity': int(item['quantity']), **analysis
                    })
                progress_bar.progress((idx + 1) / total)
            progress_bar.empty()
            status_text.empty()
            st.session_state['portfolio_results'] = results
            st.rerun()

        # 분석 결과가 있으면 먼저 표시
        has_results = st.session_state.get('portfolio_results') is not None

        if has_results:
            # 스크롤 처리 (iframe 방식)
            if st.session_state.get('scroll_to_top'):
                st.markdown("""
                <iframe src="about:blank" style="display:none" onload="
                    this.parentElement.scrollIntoView();
                    window.parent.document.body.scrollTop = 0;
                    window.parent.document.documentElement.scrollTop = 0;
                "></iframe>
                """, unsafe_allow_html=True)
                st.session_state['scroll_to_top'] = False

            results = st.session_state['portfolio_results']

            # 요약 계산
            total_invest = sum(r['buy_price'] * r['quantity'] for r in results if r['buy_price'] > 0)
            total_current = sum(r['current_price'] * r['quantity'] for r in results)
            total_profit = total_current - total_invest
            profit_rate = (total_profit / total_invest * 100) if total_invest > 0 else 0

            # 의견별 분류
            opinion_counts = {}
            for r in results:
                op = r['opinion']
                opinion_counts[op] = opinion_counts.get(op, 0) + 1

            # 제목 + 새로고침 (한 줄)
            title_col, refresh_col = st.columns([6, 1])
            with title_col:
                st.markdown("### 📊 분석 결과 요약")
            with refresh_col:
                if st.button("🔄", key="refresh_analysis", help="분석 다시 실행"):
                    st.session_state['run_portfolio_analysis'] = True
                    st.rerun()

            # 요약 테이블 (세로형 - 모바일 친화적)
            profit_color = "#C53030" if total_profit < 0 else "#2F855A"
            summary_html = f"""
            <table style="width:100%;border-collapse:collapse;margin:15px 0;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                <tr>
                    <th style="padding:10px 15px;text-align:left;background:#f7fafc;border-bottom:1px solid #e2e8f0;width:40%;">종목수</th>
                    <td style="padding:10px 15px;text-align:right;font-weight:bold;border-bottom:1px solid #e2e8f0;">{len(results)}개</td>
                </tr>
                <tr>
                    <th style="padding:10px 15px;text-align:left;background:#f7fafc;border-bottom:1px solid #e2e8f0;">총 투자금</th>
                    <td style="padding:10px 15px;text-align:right;border-bottom:1px solid #e2e8f0;">{total_invest:,.0f}원</td>
                </tr>
                <tr>
                    <th style="padding:10px 15px;text-align:left;background:#f7fafc;border-bottom:1px solid #e2e8f0;">총 평가금</th>
                    <td style="padding:10px 15px;text-align:right;border-bottom:1px solid #e2e8f0;">{total_current:,.0f}원</td>
                </tr>
                <tr>
                    <th style="padding:10px 15px;text-align:left;background:#f7fafc;border-bottom:1px solid #e2e8f0;">총 손익</th>
                    <td style="padding:10px 15px;text-align:right;font-weight:bold;color:{profit_color};border-bottom:1px solid #e2e8f0;">{total_profit:+,.0f}원</td>
                </tr>
                <tr>
                    <th style="padding:10px 15px;text-align:left;background:#f7fafc;">수익률</th>
                    <td style="padding:10px 15px;text-align:right;font-size:20px;font-weight:bold;color:{profit_color};">{profit_rate:+.1f}%</td>
                </tr>
            </table>
            """
            st.markdown(summary_html, unsafe_allow_html=True)

            # 의견 분포 (가로형 뱃지)
            opinion_badges = ""
            opinion_colors = {
                '강력매도': '#C53030', '매도': '#E53E3E', '손절': '#C53030', '손절검토': '#DD6B20',
                '추가매수': '#2F855A', '보유': '#3182CE', '관망': '#718096'
            }
            for op, count in opinion_counts.items():
                color = opinion_colors.get(op, '#718096')
                opinion_badges += f'<span style="display:inline-block;background:{color};color:white;padding:6px 14px;border-radius:20px;margin:4px;font-weight:bold;">{op}: {count}개</span>'

            st.markdown(f"""
            <div style="margin:15px 0;">
                <strong>의견 분포:</strong><br>
                {opinion_badges}
            </div>
            """, unsafe_allow_html=True)

            # 경고/추천 알림
            sell_list = [r for r in results if r['opinion'] in ['강력매도', '매도', '손절', '손절검토']]
            buy_list = [r for r in results if r['opinion'] == '추가매수']

            if sell_list:
                sell_names = ", ".join([s['name'] for s in sell_list])
                st.markdown(f"""
                <div style="background:#FED7D7;padding:12px 15px;border-radius:8px;border-left:4px solid #C53030;margin:10px 0;">
                    <strong style="color:#C53030;">⚠️ 매도/손절 검토:</strong> {sell_names}
                </div>
                """, unsafe_allow_html=True)

            if buy_list:
                buy_names = ", ".join([s['name'] for s in buy_list])
                st.markdown(f"""
                <div style="background:#C6F6D5;padding:12px 15px;border-radius:8px;border-left:4px solid #2F855A;margin:10px 0;">
                    <strong style="color:#2F855A;">💡 추가매수 고려:</strong> {buy_names}
                </div>
                """, unsafe_allow_html=True)

            # 종목별 현황
            st.markdown("---")
            st.markdown("### 📈 종목별 현황")

            sort_by = st.selectbox("정렬", ["수익률 높은 순", "수익률 낮은 순", "점수 높은 순", "점수 낮은 순"], label_visibility="collapsed")

            if sort_by == "점수 높은 순":
                results_sorted = sorted(results, key=lambda x: x['score'], reverse=True)
            elif sort_by == "점수 낮은 순":
                results_sorted = sorted(results, key=lambda x: x['score'])
            elif sort_by == "수익률 높은 순":
                results_sorted = sorted(results, key=lambda x: x['profit_rate'], reverse=True)
            else:
                results_sorted = sorted(results, key=lambda x: x['profit_rate'])

            for i, r in enumerate(results_sorted):
                profit_pct = r['profit_rate']
                profit_color = "#C53030" if profit_pct < 0 else "#2F855A"
                profit_bg = "#FFF5F5" if profit_pct < 0 else "#F0FFF4"
                opinion_emoji = {'강력매도': '🚨', '매도': '📉', '손절': '⛔', '손절검토': '⚠️', '추가매수': '💰', '보유': '✅', '관망': '👀'}.get(r['opinion'], '📌')

                header_html = f"""
                <div style="background:{profit_bg};padding:12px 15px;border-radius:8px;margin:8px 0;border-left:4px solid {profit_color};">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <strong style="font-size:15px;">{r['name']}</strong>
                        <span style="font-size:18px;font-weight:bold;color:{profit_color};">{profit_pct:+.1f}%</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;color:#555;font-size:13px;">
                        <span>{r['code']} &nbsp; 점수: {r['score']}</span>
                        <span>{opinion_emoji} {r['opinion']}</span>
                    </div>
                </div>
                """
                st.markdown(header_html, unsafe_allow_html=True)

                with st.expander(f"상세 보기 - {r['name']}", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**매수가:** {r['buy_price']:,.0f}원")
                        st.markdown(f"**현재가:** {r['current_price']:,.0f}원")
                        st.markdown(f"**수량:** {r['quantity']}주")
                    with col2:
                        profit_amount = (r['current_price'] - r['buy_price']) * r['quantity']
                        st.markdown(f"**평가손익:** {profit_amount:+,.0f}원")
                        st.markdown(f"**기술점수:** {r['score']}점")

                    st.markdown(f"**💡 의견 사유:** {r['reason']}")

                    signals = r.get('signals', [])
                    if signals:
                        signals_kr = [get_signal_kr(s) for s in signals[:5]]
                        st.markdown(f"**📊 신호:** {', '.join(signals_kr)}")

            # CSV 다운로드
            st.markdown("---")
            df_download = pd.DataFrame([{
                '종목코드': r['code'],
                '종목명': r['name'],
                '매수가': r['buy_price'],
                '현재가': int(r['current_price']),
                '수익률(%)': round(r['profit_rate'], 2),
                '점수': r['score'],
                '의견': r['opinion'],
                '사유': r['reason']
            } for r in results])

            csv = df_download.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "📥 결과 다운로드 (CSV)",
                csv,
                file_name=f"portfolio_advice_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

            # 결과 초기화 버튼
            if st.button("🔄 다시 분석하기", use_container_width=True):
                st.session_state['portfolio_results'] = None
                st.rerun()

        # 보유 주식 관리 섹션 (분석 결과 아래 또는 결과 없을 때 위에)
        st.markdown("---")
        st.markdown("### 💼 보유 주식 관리")

        # 파일 업로드
        with st.expander("📂 파일로 일괄 등록"):
            uploaded_file = st.file_uploader(
                "Excel/CSV 파일",
                type=['xlsx', 'xls', 'csv'],
                help="종목코드, 매수가, 수량 컬럼 필요"
            )

            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        upload_df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
                    else:
                        xl = pd.ExcelFile(uploaded_file)
                        if '잔고' in xl.sheet_names:
                            upload_df = pd.read_excel(uploaded_file, sheet_name='잔고')
                        else:
                            upload_df = pd.read_excel(uploaded_file)

                    st.dataframe(upload_df, use_container_width=True)

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("기존 데이터에 추가", type="secondary"):
                            count = 0
                            for _, row in upload_df.iterrows():
                                code = str(row.get('종목코드', '')).zfill(6)
                                if not code or code == '000000':
                                    continue
                                name = row.get('종목명', '')
                                buy_price = float(row.get('매수가', 0))
                                qty = int(row.get('잔고수량', row.get('수량', 1)))
                                buy_date = row.get('최종매수일', row.get('매수일'))
                                if pd.notna(buy_date):
                                    buy_date = str(buy_date)[:10]
                                else:
                                    buy_date = None
                                if qty > 0:
                                    db.add_portfolio_item(user_id, code, name, buy_price, qty, buy_date)
                                    count += 1
                            st.success(f"{count}개 종목 추가됨")
                            st.rerun()
                    with col2:
                        if st.button("전체 교체", type="primary"):
                            db.clear_portfolio(user_id)
                            count = 0
                            for _, row in upload_df.iterrows():
                                code = str(row.get('종목코드', '')).zfill(6)
                                if not code or code == '000000':
                                    continue
                                name = row.get('종목명', '')
                                buy_price = float(row.get('매수가', 0))
                                qty = int(row.get('잔고수량', row.get('수량', 1)))
                                buy_date = row.get('최종매수일', row.get('매수일'))
                                if pd.notna(buy_date):
                                    buy_date = str(buy_date)[:10]
                                else:
                                    buy_date = None
                                if qty > 0:
                                    db.add_portfolio_item(user_id, code, name, buy_price, qty, buy_date)
                                    count += 1
                            st.success(f"포트폴리오 교체 완료 ({count}개 종목)")
                            st.rerun()
                except Exception as e:
                    st.error(f"파일 로드 실패: {e}")

        # 포트폴리오 다시 로드
        if is_guest:
            portfolio_items = st.session_state.get('guest_portfolio', [])
        else:
            portfolio_items = db.get_portfolio(user_id)

        st.markdown("---")

        if not portfolio_items:
            st.info("포트폴리오가 비어있습니다. 종목을 추가하세요.")
            # 빈 포트폴리오일 때 추가 버튼
            with st.popover("➕ 종목 추가"):
                add_code = st.text_input("종목코드", placeholder="005930", key="empty_add_code")
                add_name = st.text_input("종목명", placeholder="삼성전자", key="empty_add_name")
                add_price = st.number_input("매수가", min_value=0, step=100, key="empty_add_price")
                add_qty = st.number_input("수량", min_value=1, step=1, value=1, key="empty_add_qty")
                if st.button("추가", type="primary", use_container_width=True, key="empty_add_btn"):
                    if add_code and add_qty > 0:
                        if is_guest:
                            import uuid
                            new_item = {
                                'id': str(uuid.uuid4()),
                                'stock_code': str(add_code).zfill(6),
                                'stock_name': add_name,
                                'buy_price': add_price,
                                'quantity': add_qty
                            }
                            st.session_state['guest_portfolio'].append(new_item)
                        else:
                            db.add_portfolio_item(user_id, str(add_code).zfill(6), add_name, add_price, add_qty, None)
                        st.success("추가됨")
                        st.rerun()
        else:
            st.markdown(f"### 📋 보유 종목 ({len(portfolio_items)}개)")

            # 표 형식으로 표시
            portfolio_df = pd.DataFrame([{
                '종목명': (p['stock_name'] or '')[:8],
                '코드': p['stock_code'],
                '매수가': f"{int(p['buy_price']):,}",
                '수량': f"{int(p['quantity']):,}"
            } for p in portfolio_items])

            st.dataframe(
                portfolio_df,
                use_container_width=True,
                hide_index=True,
                height=(len(portfolio_items) + 1) * 35 + 10
            )

            # 버튼들 (추가/수정/삭제) - 모바일에서도 가로 배치
            st.markdown("""
            <style>
            @media (max-width: 640px) {
                [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.5rem !important; }
                [data-testid="stHorizontalBlock"] > div { min-width: 0 !important; }
            }
            </style>
            """, unsafe_allow_html=True)
            col_add, col_edit, col_del = st.columns(3)
            with col_add:
                with st.popover("➕ 추가"):
                    add_code = st.text_input("종목코드", placeholder="005930", key="quick_add_code")
                    add_name = st.text_input("종목명", placeholder="삼성전자", key="quick_add_name")
                    add_price = st.number_input("매수가", min_value=0, step=100, key="quick_add_price")
                    add_qty = st.number_input("수량", min_value=1, step=1, value=1, key="quick_add_qty")
                    if st.button("추가", type="primary", use_container_width=True, key="quick_add_btn"):
                        if add_code and add_qty > 0:
                            if is_guest:
                                import uuid
                                new_item = {
                                    'id': str(uuid.uuid4()),
                                    'stock_code': str(add_code).zfill(6),
                                    'stock_name': add_name,
                                    'buy_price': add_price,
                                    'quantity': add_qty
                                }
                                st.session_state['guest_portfolio'].append(new_item)
                            else:
                                db.add_portfolio_item(user_id, str(add_code).zfill(6), add_name, add_price, add_qty, None)
                            st.success("추가됨")
                            st.rerun()
            with col_edit:
                with st.popover("✏️ 수정"):
                    edit_options = {f"{p['stock_name'] or p['stock_code']}": p for p in portfolio_items}
                    edit_selected = st.selectbox("종목 선택", list(edit_options.keys()), key="edit_select")
                    if edit_selected:
                        edit_item = edit_options[edit_selected]
                        new_price = st.number_input("매수가", value=int(edit_item['buy_price']), min_value=0, step=100, key="edit_price")
                        new_qty = st.number_input("수량", value=int(edit_item['quantity']), min_value=1, step=1, key="edit_qty")
                        if st.button("저장", type="primary", use_container_width=True, key="edit_save_btn"):
                            if is_guest:
                                for p in st.session_state['guest_portfolio']:
                                    if p['id'] == edit_item['id']:
                                        p['buy_price'] = new_price
                                        p['quantity'] = new_qty
                                        break
                            else:
                                db.update_portfolio_item(edit_item['id'], buy_price=new_price, quantity=new_qty)
                            st.success("수정됨")
                            st.rerun()
            with col_del:
                with st.popover("🗑️ 삭제"):
                    del_options = {f"{p['stock_name'] or p['stock_code']}": p['id'] for p in portfolio_items}
                    del_selected = st.selectbox("종목 선택", list(del_options.keys()), key="del_select")
                    if st.button("삭제", type="secondary", use_container_width=True):
                        if is_guest:
                            st.session_state['guest_portfolio'] = [
                                p for p in st.session_state['guest_portfolio']
                                if p['id'] != del_options[del_selected]
                            ]
                        else:
                            db.delete_portfolio_item(del_options[del_selected])
                            st.rerun()

            # 분석 시작 버튼 (컬럼 밖에서 전체 너비)
            st.markdown("")
            if st.button("🚀 포트폴리오 분석 시작", type="primary", use_container_width=True, key="portfolio_analyze_btn"):
                from portfolio_advisor import PortfolioAdvisor

                advisor = PortfolioAdvisor()

                progress_bar = st.progress(0)
                status_text = st.empty()

                results = []
                total = len(portfolio_items)

                for idx, item in enumerate(portfolio_items):
                    code = item['stock_code']
                    name = item['stock_name'] or code
                    buy_price = float(item['buy_price'])

                    status_text.text(f"분석 중: {name} ({idx+1}/{total})")

                    analysis = advisor.analyze_stock(code, buy_price)
                    if analysis:
                        results.append({
                            'code': code,
                            'name': name,
                            'buy_price': buy_price,
                            'quantity': int(item['quantity']),
                            **analysis
                        })

                    progress_bar.progress((idx + 1) / total)

                progress_bar.empty()
                status_text.empty()

                st.session_state['portfolio_results'] = results
                st.rerun()
