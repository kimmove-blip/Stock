import requests
from bs4 import BeautifulSoup

class SentimentAnalyst:
    def __init__(self):
        # API 키 없이 크롤링만 사용하므로 초기화 내용 없음
        pass

    def get_news_sentiment(self, code):
        """
        [수정됨] API 대신 네이버 금융 '뉴스/공시' 탭을 크롤링합니다.
        """
        # 네이버 금융 종목별 뉴스 리스트 URL
        url = f"https://finance.naver.com/item/news_news.nhn?code={code}"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            res = requests.get(url, headers=headers)
            # 네이버 금융은 가끔 인코딩 문제가 있어 euc-kr로 변환 필요할 수 있음
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            
            # 뉴스 제목 추출
            titles = soup.select('.title')
            
            score = 0
            reasons = []
            analyzed_titles = []

            # 긍정/부정 키워드 (조금 더 늘렸습니다)
            good_words = ["수주", "계약", "최대", "호재", "급등", "상승", "흑자", "성장", "돌파", "기대"]
            bad_words = ["적자", "하락", "급락", "손실", "배임", "횡령", "우려", "약세", "둔화", "불안"]
            
            for t in titles[:30]: # 최근 15개 뉴스만 분석
                title_text = t.get_text().strip()
                analyzed_titles.append(title_text)
                
                if any(w in title_text for w in good_words):
                    score += 1
                if any(w in title_text for w in bad_words):
                    score -= 1
            
            # 결과 텍스트 생성
            if score >= 3:
                reasons.append(f"🔥 뉴스 분위기 좋음 (긍정 키워드 우세, 점수: {score})")
            elif score <= -3:
                reasons.append(f"🥶 뉴스 분위기 냉랭 (부정 키워드 우세, 점수: {score})")
            else:
                reasons.append(f"😐 뉴스 분위기 중립 (점수: {score})")
                
            return score, reasons, analyzed_titles
            
        except Exception as e:
            return 0, [f"뉴스 크롤링 실패: {e}"], []

    def get_discussion_buzz(self, code):
        """
        네이버 금융 종목토론실 크롤링
        """
        url = f"https://finance.naver.com/item/board.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            titles = soup.select('td.title a')
            
            buzz_score = 0
            detected_titles = []
            
            # 키워드 감지 로직
            panic_words = ["한강", "구조대", "망했", "손절", "돔황차", "폭락", "하락", "물려"]
            hope_words = ["가즈아", "상한가", "떡상", "존버", "찬티", "상승", "수익", "축하"]
            
            for t in titles[:20]:
                text = t.get_text().strip()
                # 제목에서 '답글' 표시 등의 공백 제거
                clean_text = " ".join(text.split()) 
                
                if any(w in clean_text for w in panic_words):
                    buzz_score -= 1
                    detected_titles.append(f"😨 {clean_text}")
                elif any(w in clean_text for w in hope_words):
                    buzz_score += 1
                    detected_titles.append(f"🤑 {clean_text}")
            
            reasons = []
            if buzz_score <= -2: # 기준을 조금 낮춤
                reasons.append("📉 토론방 공포/실망감 감지")
            elif buzz_score >= 2:
                reasons.append("📈 토론방 기대감 고조")
            else:
                reasons.append("💬 토론방 분위기 관망/잡담 위주")
                
            return buzz_score, reasons, detected_titles
            
        except Exception as e:
            return 0, [f"토론방 크롤링 실패: {e}"], []

# --- 실행부 ---
if __name__ == "__main__":
    analyst = SentimentAnalyst()
    
    code = "005930" # 삼성전자
    print(f"📰 삼성전자({code}) 센티멘트 분석 시작...\n")
    
    # 1. 뉴스 분석 (크롤링 버전)
    n_score, n_reasons, n_titles = analyst.get_news_sentiment(code)
    print(f"[뉴스 분석] 점수: {n_score}")
    print(f"진단: {n_reasons[0]}")
    if n_titles:
        print(f"최신 헤드라인: {n_titles[0]} 외 {len(n_titles)-1}건")
    
    print("-" * 30)
    
    # 2. 토론방 분석
    d_score, d_reasons, d_titles = analyst.get_discussion_buzz(code)
    print(f"[토론방 분석] 점수: {d_score}")
    print(f"진단: {d_reasons[0]}")
    
    if d_titles:
        print("\n[🔥 감지된 게시글]")
        for t in d_titles:
            print(t)
    else:
        print("\n(특이 키워드가 포함된 게시글이 없습니다)")