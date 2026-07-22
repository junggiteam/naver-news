import os
import json
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_economy_news():
    categories = {
        "기업 (산업/재계)": "https://news.naver.com/section/101/261",
        "금융": "https://news.naver.com/section/101/259",
        "투자 (증권)": "https://news.naver.com/section/101/258",
        "재테크 (생활경제)": "https://news.naver.com/section/101/310",
        "경제 일반": "https://news.naver.com/section/101/263"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    news_data = []
    
    for cat_name, url in categories.items():
        try:
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 네이버 섹션별 주요 기사 제목 태그들을 다각도로 탐색
            articles = soup.select('.sa_text_title, .sa_text_strong, .sh_text_headline, .sa_text a')
            
            count = 0
            seen_titles = set()
            
            for article in articles:
                title = article.get_text(strip=True)
                # 링크 가져오기
                link = article.get('href', '') if article.name == 'a' else ''
                if not link and article.find_parent('a'):
                    link = article.find_parent('a').get('href', '')
                
                # 유효한 제목과 링크만 중복 없이 5개 수집
                if title and link and title not in seen_titles:
                    seen_titles.add(title)
                    count += 1
                    news_data.append({
                        "press_name": cat_name,
                        "rank": f"{count}위",
                        "title": title,
                        "link": link
                    })
                    if count >= 5:
                        break
        except Exception as e:
            print(f"{cat_name} 수집 중 에러 발생: {e}")

    os.makedirs("data", exist_ok=True)
    
    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "news": news_data
    }
    
    file_path = os.path.join("data", "economy_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"성공! 총 {len(news_data)}개의 경제 뉴스가 {file_path}에 저장되었습니다.")

if __name__ == "__main__":
    crawl_economy_news()