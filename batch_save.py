import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# 모듈 가져오기
from dart_analyst import FundamentalAnalyst
from technical_analyst import TechnicalAnalyst
from sentiment_analyst import SentimentAnalyst

load_dotenv()

# --- 분석 대상 리스트 (이름, 종목코드, DART고유번호) ---
# DART 고유번호는 Open DART 웹사이트나 별도 API로 확인 가능
TARGET_STOCKS = [
    {"name": "삼성전자", "code": "005930", "dart": "00126380"},
    {"name": "SK하이닉스", "code": "000660", "dart": "00164779"},
    {"name": "현대차", "code": "005380", "dart": "00164742"},
    {"name": "NAVER", "code": "035420", "dart": "00266961"},
    {"name": "카카오", "code": "035720", "dart": "00258801"}
]

def analyze_one_stock(stock_info, fund, tech, sent):
    """단일 종목을 분석하여 딕셔너리(Row) 형태로 반환"""
    name = stock_info['name']
    code = stock_info['code']
    dart_code = stock_info['dart']
    
    print(f"[{name}] 분석 진행 중...", end=" ", flush=True)
    
    # 결과 저장용 딕셔너리
    row = {
        "종목명": name,
        "종목코드": code,
        "분석일시": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    try:
        # 1. 재무 분석 (40점)
        f_data = fund.get_financials(dart_code, "2023") # 2023년 결산 기준
        f_score, _, f_details = fund.analyze(f_data)
        row['재무점수'] = f_score
        row.update(f_details) # 유동비율, 부채비율 등 상세 수치 추가

        # 2. 차트 분석 (30점)
        t_data = tech.get_ohlcv(code)
        t_score, _, t_details = tech.analyze(t_data)
        row['차트점수'] = t_score
        row.update(t_details) # RSI, 현재가 등 추가

        # 3. 심리 분석 (30점)
        n_score, _, _ = sent.get_news_sentiment(code)
        d_score, _, _ = sent.get_discussion_buzz(code)
        s_total = max(0, min(30, 15 + n_score + d_score))
        row['심리점수'] = s_total
        row['뉴스점수'] = n_score
        row['토론방점수'] = d_score

        # 4. 종합 점수 및 등급
        total_score = f_score + t_score + s_total
        row['종합점수'] = total_score
        
        if total_score >= 80: row['투자의견'] = "[S] 강력 매수"
        elif total_score >= 60: row['투자의견'] = "[A] 매수"
        elif total_score >= 40: row['투자의견'] = "[B] 관망"
        else: row['투자의견'] = "[C] 매도"

        print(f"[OK] 완료 (점수: {total_score})")
        return row

    except Exception as e:
        print(f"[ERR] 실패 ({e})")
        row['투자의견'] = "분석실패"
        return row

def main():
    print(f">> 총 {len(TARGET_STOCKS)}개 종목 일괄 분석 시작...\n")
    
    # 분석가 인스턴스 생성 (한 번만 생성해서 계속 재사용)
    fund_analyst = FundamentalAnalyst(os.getenv("DART_API_KEY"))
    tech_analyst = TechnicalAnalyst()
    sent_analyst = SentimentAnalyst()

    results = []
    
    # 반복문 실행
    for stock in TARGET_STOCKS:
        result_row = analyze_one_stock(stock, fund_analyst, tech_analyst, sent_analyst)
        results.append(result_row)

    # DataFrame 변환
    df = pd.DataFrame(results)
    
    # 컬럼 순서 보기 좋게 정렬 (존재하는 컬럼만 선택)
    cols = ['종목명', '투자의견', '종합점수', '현재가', '재무점수', '차트점수', '심리점수', 
            '유동비율', '부채비율', '영업이익률', 'RSI']
    
    # 실제 데이터에 있는 컬럼만 골라내기 (에러 방지)
    final_cols = [c for c in cols if c in df.columns]
    df = df[final_cols]

    # 엑셀 저장
    file_name = f"stock_report_{datetime.now().strftime('%Y%m%d')}.xlsx"
    df.to_excel(file_name, index=False)
    
    print("\n" + "="*50)
    print(f"[SAVE] 분석 완료! 파일이 저장되었습니다: {file_name}")
    print("="*50)
    print(df[['종목명', '종합점수', '투자의견']]) # 요약 출력

if __name__ == "__main__":
    main()