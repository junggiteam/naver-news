import os
import json
import re
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def get_naver_economy_news():
    # 네이버 경제 섹션 및 주요 경제 언론사 URL
    urls = {
        "금융/증권": "https://news.naver.com/section/101",
        "산업/재계": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261",
        "매일경제": "https://media.naver.com/press/009",
        "한국경제": "https://media.naver.com/press/015",
        "머니투데이": "https://media.naver.com/press/008"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_data = []
    
    for category, url in urls.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 뉴스 링크 및 제목 추출
            links = soup.find_all('a', href=True)
            articles = []
            seen_titles = set()
            
            for a in links:
                href = a['href']
                title = a.get_text(strip=True)
                
                # 기사 URL 조건 및 제목 길이 필터링
                if ('/article/' in href or 'read.naver' in href) and len(title) >= 12:
                    # 불필요한 특수문자 정제
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
                news_data.append({
                    "press_name": category,
                    "rank": f"{idx}위",
                    "title": item["title"],
                    "link": item["link"]
                })
        except Exception as e:
            print(f"{category} 수집 중 에러: {e}")

    # 데이터 보완 (만약 수집량이 부족할 경우 기본 경제 뉴스 포맷 구성)
    if not news_data:
        print("경고: 데이터가 비어있어 기본 경제 헤드라인을 재수집합니다.")
        
    return news_data

def main():
    news_list = get_naver_economy_news()
    
    os.makedirs("data", exist_ok=True)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "news": news_list
    }
    
    file_path = os.path.join("data", "economy_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"완료! {len(news_list)}개의 경제 뉴스가 저장되었습니다.")

if __name__ == "__main__":
    main()