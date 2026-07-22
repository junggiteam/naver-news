import os
import json
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def get_category_news(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        articles = []
        seen_titles = set()
        
        # 네이버 기사 상세 페이지 URL 패턴('/article/')을 가진 태그를 직접 추적
        a_tags = soup.find_all('a', href=True)
        
        for a in a_tags:
            href = a['href']
            if '/article/' not in href:
                continue
                
            title = a.get_text(strip=True)
            
            # 너무 짧은 단어나 중복 제목 제외 (10자 이상 진짜 기사 제목만 필터링)
            if len(title) < 10 or title in seen_titles:
                continue
                
            if not href.startswith('http'):
                href = 'https://news.naver.com' + href
                
            seen_titles.add(title)
            articles.append({
                "title": title,
                "link": href
            })
            
            if len(articles) >= 5:
                break
                
        return articles
    except Exception as e:
        print(f"수집 중 에러 발생 ({url}): {e}")
        return []

def crawl_economy_news():
    categories = {
        "기업 (산업/재계)": "https://news.naver.com/section/101/261",
        "금융": "https://news.naver.com/section/101/259",
        "투자 (증권)": "https://news.naver.com/section/101/258",
        "재테크 (생활경제)": "https://news.naver.com/section/101/310",
        "경제 일반": "https://news.naver.com/section/101/263"
    }
    
    news_data = []
    
    for cat_name, url in categories.items():
        # 1차: 데스크톱 주소로 기사 수집
        items = get_category_news(url)
        
        # 2차 백업: 수집 실패 시 모바일 주소로 재시도
        if not items:
            m_url = url.replace("https://news.naver.com", "https://m.news.naver.com")
            items = get_category_news(m_url)
            
        for idx, item in enumerate(items, 1):
            news_data.append({
                "press_name": cat_name,
                "rank": f"{idx}위",
                "title": item["title"],
                "link": item["link"]
            })

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