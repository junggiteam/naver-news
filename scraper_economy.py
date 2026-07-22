import os
import json
import re
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_economy_categories():
    # 네이버 경제 세부 카테고리 8개 목록
    categories = {
        "금융": "https://news.naver.com/section/101/259",
        "증권/투자": "https://news.naver.com/section/101/258",
        "재테크/생활경제": "https://news.naver.com/section/101/310",
        "부동산": "https://news.naver.com/section/101/260",
        "산업/재계": "https://news.naver.com/section/101/261",
        "중기/벤처": "https://news.naver.com/section/101/771",
        "글로벌 경제": "https://news.naver.com/section/101/262",
        "경제 일반": "https://news.naver.com/section/101/263"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    for cat_name, url in categories.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 클래스 이름에 의존하지 않고 /article/ 링크 패턴을 직접 탐색하는 견고한 방식
            links = soup.find_all('a', href=True)
            articles = []
            seen_titles = set()
            
            for a in links:
                href = a['href']
                title = a.get_text(strip=True)
                
                if '/article/' in href and len(title) >= 10:
                    clean_title = re.sub(r'\s+', ' ', title)
                    if clean_title not in seen_titles:
                        seen_titles.add(clean_title)
                        if not href.startswith('http'):
                            href = 'https://news.naver.com' + href
                        articles.append({
                            "title": clean_title,
                            "link": href
                        })
                        if len(articles) >= 5:
                            break
                            
            for idx, item in enumerate(articles, 1):
                news_list.append({
                    "press_name": cat_name,
                    "rank": f"{idx}위",
                    "title": item["title"],
                    "link": item["link"]
                })
        except Exception as e:
            print(f"{cat_name} 수집 에러: {e}")
            
    return news_list

def main():
    news_data = crawl_economy_categories()
    
    os.makedirs("data", exist_ok=True)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "news": news_data
    }
    
    file_path = os.path.join("data", "economy_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"완료: 총 {len(news_data)}개 기사 수집됨.")

if __name__ == "__main__":
    main()