import os
import sys
import argparse
from dotenv import load_dotenv
import FinanceDataReader as fdr
import OpenDartReader

# 우리가 만든 모듈들 가져오기
from dart_analyst import FundamentalAnalyst
from technical_analyst import TechnicalAnalyst
from sentiment_analyst import SentimentAnalyst

# 환경 변수 로드
load_dotenv()

def get_dart_reader():
    """DART API 연결"""
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        print("⚠️ DART_API_KEY가 설정되지 않았습니다. 재무 분석이 제한됩니다.")
        return None
    try:
        return OpenDartReader(api_key)
    except Exception as e:
        print(f"⚠️ DART 연결 실패: {e}")
        return None

def search_stock(keyword):
    """종목명 또는 코드로 검색"""
    try:
        df = fdr.StockListing('KRX')
        # 코드로 검색
        code_match = df[df['Code'] == keyword]
        if not code_match.empty:
            row = code_match.iloc[0]
            return {"code": row['Code'], "name": row['Name']}

        # 종목명으로 검색 (부분 일치)
        name_match = df[df['Name'].str.contains(keyword, case=False, na=False)]
        if name_match.empty:
            return None

        if len(name_match) == 1:
            row = name_match.iloc[0]
            return {"code": row['Code'], "name": row['Name']}

        # 여러 개 일치 시 선택
        print(f"\n🔍 '{keyword}' 검색 결과 ({len(name_match)}개):")
        for i, (_, row) in enumerate(name_match.head(10).iterrows(), 1):
            print(f"   {i}. {row['Name']} ({row['Code']}) - {row.get('Market', 'KRX')}")

        if len(name_match) > 10:
            print(f"   ... 외 {len(name_match) - 10}개 (더 구체적인 검색어를 입력하세요)")

        while True:
            choice = input("\n번호를 선택하세요 (0=취소): ").strip()
            if choice == '0':
                return None
            try:
                idx = int(choice) - 1
                if 0 <= idx < min(10, len(name_match)):
                    row = name_match.iloc[idx]
                    return {"code": row['Code'], "name": row['Name']}
            except ValueError:
                pass
            print("잘못된 입력입니다.")
    except Exception as e:
        print(f"검색 중 오류: {e}")
        return None

def interactive_mode():
    """대화형 모드로 종목 선택"""
    print("\n" + "=" * 60)
    print("🔎 종목 검색 모드")
    print("=" * 60)
    print("종목명 또는 종목코드를 입력하세요.")
    print("예시: 삼성전자, 005930, 카카오, 네이버")
    print("-" * 60)

    while True:
        keyword = input("\n검색어 (q=종료): ").strip()
        if keyword.lower() == 'q':
            return None
        if not keyword:
            continue

        result = search_stock(keyword)
        if result:
            confirm = input(f"\n'{result['name']}' ({result['code']})을(를) 분석할까요? (Y/n): ").strip().lower()
            if confirm != 'n':
                return result
        else:
            print("❌ 검색 결과가 없습니다. 다시 시도해주세요.")

def analyze_stock(stock_code, stock_name, dart_code=None):
    """주식 분석 실행"""
    target_year = "2023"

    print(f"\n🚀 [{stock_name}] AI 주식 분석 시스템 가동 시작...")
    print("=" * 60)

    # 1. 인스턴스 생성
    try:
        fund_analyst = FundamentalAnalyst(os.getenv("DART_API_KEY"))
        tech_analyst = TechnicalAnalyst()
        sent_analyst = SentimentAnalyst()
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return

    # DART 코드 자동 검색
    if not dart_code:
        dart = get_dart_reader()
        if dart:
            try:
                dart_code = dart.find_corp_code(stock_code)
            except:
                dart_code = None

    # 2. 분석 실행

    # (A) 펀더멘털 분석 (가중치 20%)
    print("\n[1] 🏢 펀더멘털(재무) 분석 중...")
    f_score, f_reasons, f_details = 0, [], {}
    if dart_code:
        f_data = fund_analyst.get_financials(dart_code, target_year)
        if f_data is not None:
            f_score, f_reasons, f_details = fund_analyst.analyze(f_data)
    else:
        print("   ⚠️ DART 코드를 찾을 수 없어 재무 분석을 건너뜁니다.")
    print(f"   -> 점수: {f_score} / 20")

    # (B) 테크니컬 분석 (가중치 60%)
    print("\n[2] 📈 테크니컬(차트) 분석 중...")
    t_data = tech_analyst.get_ohlcv(stock_code)
    t_score, t_reasons, t_details = tech_analyst.analyze(t_data)
    print(f"   -> 점수: {t_score} / 60")

    # (C) 센티멘트 분석 (가중치 20%)
    print("\n[3] 📢 센티멘트(심리) 분석 중...")
    n_score, n_reasons, n_titles = sent_analyst.get_news_sentiment(stock_code)
    d_score, d_reasons, d_titles = sent_analyst.get_discussion_buzz(stock_code)

    s_total_score = 10 + n_score + d_score
    s_total_score = max(0, min(20, s_total_score))

    print(f"   -> 뉴스 점수: {n_score}, 토론방 점수: {d_score}")
    print(f"   -> 종합 심리 점수: {s_total_score} / 20")

    # 3. 종합 결과 산출
    total_score = f_score + t_score + s_total_score

    # DART 코드 없는 경우 비율 조정
    if not dart_code:
        total_score = int((t_score + s_total_score) * (100 / 80))

    if total_score >= 80: grade = "💎 강력 매수 (Strong Buy)"
    elif total_score >= 60: grade = "💰 매수 (Buy)"
    elif total_score >= 40: grade = "🤔 관망 (Hold)"
    else: grade = "😱 매도 (Sell)"

    # 4. 최종 리포트 출력
    print("\n" + "=" * 60)
    print(f"📄 [{stock_name}] 최종 투자 분석 리포트")
    print("=" * 60)
    print(f"🏆 종합 점수: {total_score}점 / 100점")
    print(f"🏁 투자 의견: {grade}")
    print("-" * 60)

    print("\n1. 🏢 펀더멘털 (재무)")
    if f_details:
        for k, v in f_details.items(): print(f"   - {k}: {v}")
        for r in f_reasons: print(f"   - {r}")
    else:
        print("   - 데이터 없음")

    print("\n2. 📈 테크니컬 (차트)")
    for k, v in t_details.items(): print(f"   - {k}: {v}")
    for r in t_reasons: print(f"   - {r}")

    print("\n3. 📢 센티멘트 (심리)")
    if n_reasons: print(f"   - 뉴스 동향: {n_reasons[0]}")
    if n_titles: print(f"     (헤드라인: {n_titles[0]})")
    if d_reasons: print(f"   - 토론방 동향: {d_reasons[0]}")

    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(
        description="AI 주식 분석 시스템",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python main.py                    # 대화형 모드
  python main.py 삼성전자            # 종목명으로 분석
  python main.py 005930             # 종목코드로 분석
  python main.py -c 005930          # 종목코드 직접 지정
        """
    )
    parser.add_argument('keyword', nargs='?', help='종목명 또는 종목코드')
    parser.add_argument('-c', '--code', help='종목코드 직접 지정')

    args = parser.parse_args()

    stock = None

    # 명령줄 인자로 종목 지정
    if args.code:
        stock = search_stock(args.code)
    elif args.keyword:
        stock = search_stock(args.keyword)
    else:
        # 대화형 모드
        stock = interactive_mode()

    if stock:
        analyze_stock(stock['code'], stock['name'])
    else:
        print("\n분석을 취소했습니다.")

if __name__ == "__main__":
    main()
