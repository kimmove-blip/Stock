import streamlit as st
import pandas as pd
import os
import time
import json
import plotly.express as px
from dotenv import load_dotenv

# 모듈 가져오기
from dart_analyst import FundamentalAnalyst
from technical_analyst import TechnicalAnalyst
from sentiment_analyst import SentimentAnalyst
from stock_utils import get_kospi_top_list, get_all_krx_stocks, find_dart_code

# 환경설정
load_dotenv()
st.set_page_config(page_title="AI 주식 스캐너", page_icon="$", layout="wide")
WATCHLIST_FILE = "watchlist.json"

# --- [테마 데이터] ---
THEMES = {
    "2차전지 (Battery)": ["373220", "006400", "051910", "247540", "086520", "003670"],
    "AI & 반도체": ["005930", "000660", "042700", "071050", "000210", "263750"],
    "바이오 (Bio)": ["207940", "068270", "000100", "128940", "302440"],
    "자동차 (Car)": ["005380", "000270", "012330", "009900"],
    "인터넷/플랫폼": ["035420", "035720", "251270", "036570"]
}

# --- [함수] 데이터 관리 ---
def load_watchlists():
    if not os.path.exists(WATCHLIST_FILE): return {"기본 리스트": []}
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"기본 리스트": data} if isinstance(data, list) else data
    except: return {"기본 리스트": []}

def save_watchlists(data):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_screening_targets(mode, limit=30):
    import FinanceDataReader as fdr
    targets = []
    
    if mode == "전일 급등락 (>10%)":
        df = fdr.StockListing("KRX")
        volatility_df = df[abs(df['ChagesRatio']) >= 10].copy()
        volatility_df = volatility_df.sort_values(by='Amount', ascending=False).head(limit)
        for _, row in volatility_df.iterrows():
            targets.append({"code": row['Code'], "name": row['Name'], "dart": None})
            
    elif mode == "KOSPI 상위":
        df = fdr.StockListing("KOSPI").sort_values('Marcap', ascending=False).head(limit)
        for _, row in df.iterrows(): targets.append({"code": row['Code'], "name": row['Name'], "dart": None})
    elif mode == "KOSDAQ 상위":
        df = fdr.StockListing("KOSDAQ").sort_values('Marcap', ascending=False).head(limit)
        for _, row in df.iterrows(): targets.append({"code": row['Code'], "name": row['Name'], "dart": None})
    elif mode in THEMES:
        krx = get_all_krx_stocks()
        for code in THEMES[mode]:
            found = krx[krx['Code'] == code]
            if not found.empty: targets.append({"code": code, "name": found.iloc[0]['Name'], "dart": None})
    return targets

# --- [함수] 분석 엔진 ---
@st.cache_resource
def load_analysts():
    fund = FundamentalAnalyst(os.getenv("DART_API_KEY"))
    tech = TechnicalAnalyst()
    sent = SentimentAnalyst()
    return fund, tech, sent

def run_analysis(stock, fund, tech, sent):
    results = {
        "종목명": stock['name'], "코드": stock['code'], 
        "종합점수": 0, "등급": "N/A",
        "f_reasons": [], "f_details": {}, "t_reasons": [], "t_details": {}, "s_reasons": [], "s_details": {}
    }
    
    dart_code = stock.get('dart') or find_dart_code(stock['code'])

    # 1. 재무
    f_score = 0
    if dart_code:
        try:
            f_data = fund.get_financials(dart_code, "2023")
            if f_data is not None:
                f_score, f_reasons, f_details = fund.analyze(f_data)
                results.update({'f_reasons': f_reasons, 'f_details': f_details})
        except: pass
    
    # 2. 차트
    t_score = 0
    current_price = 0
    try:
        t_data = tech.get_ohlcv(stock['code'])
        t_score, t_reasons, t_details = tech.analyze(t_data)
        results.update({'t_reasons': t_reasons, 't_details': t_details})
        current_price = int(t_details.get('현재가', '0').replace(',', '').replace('원', ''))
        results['현재가'] = t_details.get('현재가', '0')
        results['전일비'] = t_details.get('전일비', 0)
        results['등락률'] = t_details.get('등락률', 0.0)
    except: pass

    # 3. 심리
    s_total = 0
    try:
        n_score, n_reasons, _ = sent.get_news_sentiment(stock['code'])
        d_score, d_reasons, _ = sent.get_discussion_buzz(stock['code'])
        s_total = max(0, min(30, 15 + n_score + d_score))
        results.update({'s_reasons': n_reasons + d_reasons, 's_details': {"뉴스점수": n_score, "토론방점수": d_score}})
    except: pass

    # 종합 점수
    raw_total = f_score + t_score + s_total
    if not dart_code or (f_score == 0 and dart_code):
        final_total = int((t_score + s_total) * (100/60))
        results['비고'] = "재무N/A"
    else:
        final_total = raw_total
        results['비고'] = ""
    
    results.update({'종합점수': final_total, '재무': f_score, '차트': t_score, '심리': s_total})
    
    if final_total >= 80: results['등급'], mul = "[S]강력매수", 1.20
    elif final_total >= 60: results['등급'], mul = "[A]매수", 1.10
    elif final_total >= 40: results['등급'], mul = "[B]관망", 1.05
    else: results['등급'], mul = "[C]매도", 1.0
    
    results['목표주가'] = f"{int(current_price * mul):,}원"
    return results

# ================= UI 레이아웃 =================
st.title("AI Financial Analyst Dashboard")

# --- 사이드바 ---
st.sidebar.header("모드 선택")
mode = st.sidebar.radio("메뉴를 선택하세요", ["[*] 내 관심종목 분석", "[#] AI 종목 추천 (스크리닝)"])

if 'last_mode' not in st.session_state: st.session_state['last_mode'] = mode
if st.session_state['last_mode'] != mode:
    st.session_state['analysis_result'] = None
    st.session_state['last_mode'] = mode
    st.rerun()

st.sidebar.markdown("---")
analysis_targets = []
all_watchlists = load_watchlists() # 전역 로드

if mode == "⭐ 내 관심종목 분석":
    list_names = list(all_watchlists.keys())
    selected_list_name = st.sidebar.selectbox("리스트 선택", list_names)
    current_stocks = all_watchlists[selected_list_name]
    
    with st.sidebar.expander("⚙️ 리스트 관리"):
        new_list_name = st.text_input("새 리스트 이름")
        if st.button("생성"):
            if new_list_name and new_list_name not in all_watchlists:
                all_watchlists[new_list_name] = []
                save_watchlists(all_watchlists)
                st.rerun()
        if st.button("삭제", type="primary"):
            if selected_list_name != "기본 리스트":
                del all_watchlists[selected_list_name]
                save_watchlists(all_watchlists)
                st.rerun()

    krx_df = get_all_krx_stocks()
    if krx_df is not None:
        st.sidebar.subheader("🔍 종목 추가")
        search_options = krx_df['Name'] + " (" + krx_df['Code'] + ")"
        selected_option = st.sidebar.selectbox("검색", options=search_options, index=None, placeholder="종목명/코드...", label_visibility="collapsed")
        if selected_option:
            name_part = selected_option.split(" (")[0]
            code_part = selected_option.split(" (")[1].replace(")", "")
            if st.sidebar.button(f"➕ '{name_part}' 추가"):
                if not any(s['code'] == code_part for s in current_stocks):
                    current_stocks.append({"code": code_part, "name": name_part})
                    all_watchlists[selected_list_name] = current_stocks
                    save_watchlists(all_watchlists)
                    st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"📋 {selected_list_name} ({len(current_stocks)}개)")
    for stock in current_stocks:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.text(stock['name'])
        if c2.button("X", key=f"d_{stock['code']}"):
            current_stocks = [s for s in current_stocks if s['code'] != stock['code']]
            all_watchlists[selected_list_name] = current_stocks
            save_watchlists(all_watchlists)
            st.rerun()
    analysis_targets = current_stocks

else: # AI 추천 모드
    st.sidebar.header("🏆 조건 설정")
    screen_type = st.sidebar.selectbox("테마 선택", ["KOSPI 상위", "KOSDAQ 상위", "🎢 전일 급등락 (>10%)"] + list(THEMES.keys()))
    if st.sidebar.button("🔍 종목 발굴 시작", type="primary"):
        analysis_targets = get_screening_targets(screen_type, limit=30)
        st.session_state['pending_targets'] = analysis_targets

# ================= 메인 로직 =================
trigger_analysis = False
targets_to_run = []

if mode == "⭐ 내 관심종목 분석":
    if st.button("🚀 분석 시작 (Start Analysis)", type="primary"):
        trigger_analysis = True
        targets_to_run = analysis_targets
elif mode == "🏆 AI 종목 추천 (스크리닝)":
    if 'pending_targets' in st.session_state:
        trigger_analysis = True
        targets_to_run = st.session_state.pop('pending_targets')

if trigger_analysis:
    if not targets_to_run:
        st.warning("분석할 종목이 없습니다.")
    else:
        fund, tech, sent = load_analysts()
        st.info(f"데이터 수집 및 AI 분석 중... (총 {len(targets_to_run)}종목)")
        
        progress_bar = st.progress(0)
        final_data = []
        
        for i, stock in enumerate(targets_to_run):
            res = run_analysis(stock, fund, tech, sent)
            final_data.append(res)
            progress_bar.progress((i + 1) / len(targets_to_run))
        
        time.sleep(0.5)
        progress_bar.empty()
        
        df = pd.DataFrame(final_data)
        if not df.empty:
            df = df.sort_values(by=['종합점수', '심리'], ascending=[False, False]).reset_index(drop=True)
            df.index += 1
            df['순위'] = df.index
            
        st.session_state['analysis_result'] = df
        st.rerun()

if 'analysis_result' in st.session_state and st.session_state['analysis_result'] is not None:
    df = st.session_state['analysis_result']
    
    st.success(f"✅ 분석 완료! ({len(df)}개 종목)")
    display_df = df.head(20) if mode == "🏆 AI 종목 추천 (스크리닝)" else df
    display_df['전일비_표시'] = display_df.apply(lambda x: f"{x['등락률']:+.2f}%", axis=1)

    cols = ["순위", "등급", "종목명", "코드", "종합점수", "현재가", "전일비_표시", "목표주가", "재무", "차트", "심리", "비고"]
    def color_grade(v):
        s = str(v)
        if '강력매수' in s: return 'color: #00CC96; font-weight: bold'
        elif '매수' in s: return 'color: #636EFA; font-weight: bold'
        elif '매도' in s: return 'color: #EF553B; font-weight: bold'
        return ''
    def color_change(v):
        if '+' in str(v): return 'color: #EF553B'
        elif '-' in str(v): return 'color: #636EFA'
        return ''

    st.dataframe(display_df[cols].style.applymap(color_grade, subset=['등급']).applymap(color_change, subset=['전일비_표시']), use_container_width=True)

    st.markdown("---")
    st.subheader("🧐 상세 분석 리포트")
    
    stock_list = display_df['종목명'].tolist()
    pick = st.selectbox("종목 선택", stock_list)
    
    if pick:
        row = df[df['종목명'] == pick].iloc[0]
        
        with st.container():
            # [NEW] 관심종목 추가 버튼 배치 (제목 옆에)
            c_title, c_add = st.columns([3, 1])
            with c_title:
                st.markdown(f"## {row['종목명']} ({row['코드']})")
            
            with c_add:
                # 스크리닝 모드일 때만 저장 버튼 표시
                if mode == "🏆 AI 종목 추천 (스크리닝)":
                    target_list = st.selectbox("저장할 리스트", list(all_watchlists.keys()), label_visibility="collapsed")
                    if st.button(f"⭐ {target_list}에 추가"):
                        target_code = row['코드']
                        target_name = row['종목명']
                        
                        # 중복 체크
                        if any(s['code'] == target_code for s in all_watchlists[target_list]):
                            st.toast(f"이미 '{target_list}'에 있는 종목입니다.", icon="⚠️")
                        else:
                            all_watchlists[target_list].append({"code": target_code, "name": target_name})
                            save_watchlists(all_watchlists)
                            st.toast(f"'{target_name}'을(를) '{target_list}'에 저장했습니다!", icon="✅")

            # 핵심 지표
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("종합 점수", f"{row['종합점수']}점", row['등급'])
            
            change_val = row.get('전일비', 0)
            change_pct = row.get('등락률', 0.0)
            m2.metric("현재가", row['현재가'], f"{change_val:,.0f}원 ({change_pct:+.2f}%)")
            
            m3.metric("목표가", row['목표주가'])
            
            try:
                cur_n = int(row['현재가'].replace(',', '').replace('원', ''))
                tar_n = int(row['목표주가'].replace(',', '').replace('원', ''))
                up = round((tar_n - cur_n)/cur_n * 100, 1)
                m4.metric("상승여력", f"+{up}%" if up>0 else "0%")
            except: m4.metric("상승여력", "-")
            
            st.markdown("---")
            k1, k2, k3 = st.columns(3)
            with k1:
                st.write(f"##### 🏢 재무 ({row['재무']}점)")
                if row['f_details']:
                    for k,v in row['f_details'].items(): st.caption(f"{k}: {v}")
                    for r in row['f_reasons']: st.write(f"- {r}")
                else: st.caption("데이터 없음")
            with k2:
                st.write(f"##### 📈 차트 ({row['차트']}점)")
                if row['t_details']:
                    st.caption(f"RSI: {row['t_details'].get('RSI')}")
                    for r in row['t_reasons']: st.write(f"- {r}")
                else: st.caption("데이터 없음")
            with k3:
                st.write(f"##### 📢 심리 ({row['심리']}점)")
                if row['s_details']:
                    st.caption(f"뉴스: {row['s_details'].get('뉴스점수')} / 토론: {row['s_details'].get('토론방점수')}")
                    for r in row['s_reasons']: st.write(f"- {r}")
                else: st.caption("데이터 없음")

elif mode == "⭐ 내 관심종목 분석":
    st.info("👈 왼쪽 사이드바에서 관심종목을 확인하고 '분석 시작' 버튼을 누르세요.")
else:
    st.info("👈 왼쪽 사이드바에서 테마를 선택하고 '종목 발굴 시작'을 누르세요.")