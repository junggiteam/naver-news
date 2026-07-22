import os
import json
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_economy_news():
    # 네이버 경제 뉴스의 각 세부 분야별 주소
    categories = {
        "기업 (산업/재계)": "https://news.naver.com/section/101/261",
        "금융": "https://news.naver.com/section/101/259",
        "투자 (증권)": "https://news.naver.com/section/101/258",
        "재테크 (생활경제)": "https://news.naver.com/section/101/310",
        "경제 일반": "https://news.naver.com/section/101/263"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    news_data = []
    
    # 각 분야별로 돌면서 메인 헤드라인 기사 5개씩 수집
    for cat_name, url in categories.items():
        try:
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 네이버 섹션별 주요뉴스 제목을 담고 있는 클래스
            articles = soup.select('.sa_text_title')[:5] 
            
            for idx, article in enumerate(articles, 1):
                title = article.get_text(strip=True)
                link = article.get('href', '')
                
                news_data.append({
                    "press_name": cat_name, # 언론사 대신 '분야'를 넣어서 아임웹과 호환
                    "rank": f"{idx}위",
                    "title": title,
                    "link": link
                })
        except Exception as e:
            print(f"{cat_name} 수집 중 에러 발생: {e}")

    os.makedirs("data", exist_ok=True)
    
    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "news": news_data
    }
    
    # 새로운 이름의 파일(economy_news.json)로 분리해서 저장
    file_path = os.path.join("data", "economy_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"성공! 총 {len(news_data)}개의 경제 뉴스가 {file_path}에 저장되었습니다.")

if __name__ == "__main__":
    crawl_economy_news()
