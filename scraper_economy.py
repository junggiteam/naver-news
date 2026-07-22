import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_economy_press_news():
    # 대한민국 주요 경제/비즈니스 전문 언론사 목록 (10개사)
    press_list = [
        {"name": "매일경제", "url": "https://media.naver.com/press/009"},
        {"name": "한국경제", "url": "https://media.naver.com/press/015"},
        {"name": "머니투데이", "url": "https://media.naver.com/press/008"},
        {"name": "서울경제", "url": "https://media.naver.com/press/011"},
        {"name": "이데일리", "url": "https://media.naver.com/press/018"},
        {"name": "아시아경제", "url": "https://media.naver.com/press/277"},
        {"name": "헤럴드경제", "url": "https://media.naver.com/press/016"},
        {"name": "파이낸셜뉴스", "url": "https://media.naver.com/press/014"},
        {"name": "조선비즈", "url": "https://media.naver.com/press/366"},
        {"name": "디지털타임스", "url": "https://media.naver.com/press/029"}
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    all_news = []
    
    for press in press_list:
        try:
            res = requests.get(press["url"], headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 해당 언론사의 기사 링크 및 제목 추출
            a_tags = soup.find_all('a', href=True)
            articles = []
            seen_titles = set()
            
            for a in a_tags:
                href = a['href']
                title = a.get_text(strip=True)
                
                if '/article/' in href and len(title) >= 10:
                    if title not in seen_titles:
                        seen_titles.add(title)
                        if not href.startswith('http'):
                            href = 'https://news.naver.com' + href
                        articles.append({
                            "title": title,
                            "link": href
                        })
                        if len(articles) >= 5:
                            break
                            
            for idx, item in enumerate(articles, 1):
                all_news.append({
                    "press_name": press["name"],
                    "rank": f"{idx}위",
                    "title": item["title"],
                    "link": item["link"]
                })
        except Exception as e:
            print(f"{press['name']} 수집 중 에러: {e}")
            
    return all_news

def main():
    news_data = crawl_economy_press_news()
    
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
        
    print(f"수집 완료: 총 {len(news_data)}개 기사 저장됨.")

if __name__ == "__main__":
    main()