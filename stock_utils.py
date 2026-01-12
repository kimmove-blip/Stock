import FinanceDataReader as fdr
import OpenDartReader
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# DART 객체 생성 (캐싱하여 속도 향상)
@st.cache_resource
def get_dart_reader():
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        return None
    try:
        # 이 단계에서 모든 종목의 고유번호 리스트를 다운로드합니다 (최초 1회 약간 걸림)
        dart = OpenDartReader(api_key)
        return dart
    except Exception as e:
        print(f"DART 연결 실패: {e}")
        return None

def find_dart_code(stock_code):
    """
    종목코드(005930)를 주면 DART고유번호(00126380)를 찾아주는 함수
    """
    dart = get_dart_reader()
    if dart is None:
        return None
    
    try:
        # OpenDartReader는 종목코드로 고유번호를 찾는 기능을 제공합니다.
        # find_corp_code는 종목코드를 입력받아 고유번호를 반환합니다.
        result = dart.find_corp_code(stock_code)
        return result
    except:
        return None

@st.cache_data
def get_all_krx_stocks():
    """KRX 전체 종목 리스트 (검색용)"""
    try:
        df = fdr.StockListing('KRX')
        df = df[['Code', 'Name', 'Market']]
        return df
    except:
        return None

def get_kospi_top_list(limit=10):
    """(기존 기능 유지) Top 리스트 가져오기"""
    df = fdr.StockListing('KOSPI')
    if 'Marcap' in df.columns:
        df = df.sort_values(by='Marcap', ascending=False)
    
    top_df = df.head(limit)
    stock_list = []
    
    # 여기서 DART 코드를 미리 찾지 않고, 분석 시점에 찾도록 구조를 가볍게 합니다.
    for _, row in top_df.iterrows():
        stock_list.append({
            "code": row['Code'],
            "name": row['Name'],
            "dart": None # 나중에 동적으로 찾음
        })
    return stock_list