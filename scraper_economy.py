import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_economy_categories():
    # 네이버 경제 세부 카테고리 전체 8개 목록
    categories = {
        "금융": "https://news.naver.com/section/101/259",
        "증권 (투자)": "https://news.naver.com/section/101/258",
        "생활경제 (재테크)": "https://news.naver.com/section/101/310",
        "부동산": "https://news.naver.com/section/101/260",
        "산업/재계": "https://news.naver.com/section/101/261",
        "중기/벤처": "https://news.naver.com/section/101/771",
        "글로벌 경제": "https://news.naver.com/section/101/262",
        "경제 일반": "https://news.naver.com/section/101/263"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    all_news = []
    
    for cat_name, url in categories.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 각 카테고리의 주요 기사 추출
            articles = soup.select('.sa_text_title, .sh_text_headline, .sa_text_strong')
            seen_titles = set()
            
            count = 1
            for t in articles:
                title = t.get_text(strip=True)
                parent_a = t.find_parent('a') if t.name != 'a' else t
                
                if parent_a and parent_a.has_attr('href'):
                    link = parent_a['href']
                else:
                    continue
                    
                if len(title) >= 10 and title not in seen_titles:
                    seen_titles.add(title)
                    all_news.append({
                        "press_name": cat_name, # 언론사 이름 대신 '카테고리명'이 타이틀이 됨
                        "rank": f"{count}위",
                        "title": title,
                        "link": link
                    })
                    count += 1
                    if count > 5:
                        break
        except Exception as e:
            print(f"{cat_name} 수집 중 에러: {e}")
            
    return all_news

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
        
    print(f"완료: 총 {len(news_data)}개 기사 (카테고리 {len(news_data)//5}개) 수집됨.")

if __name__ == "__main__":
    main()