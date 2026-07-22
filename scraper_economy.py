import os
import json
import re
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_economy_comprehensive():
    # 주요 경제 전문 언론사 및 핵심 카테고리 전체 통합 목록
    targets = [
        {"name": "매일경제", "url": "https://media.naver.com/press/009"},
        {"name": "한국경제", "url": "https://media.naver.com/press/015"},
        {"name": "머니투데이", "url": "https://media.naver.com/press/008"},
        {"name": "서울경제", "url": "https://media.naver.com/press/011"},
        {"name": "이데일리", "url": "https://media.naver.com/press/018"},
        {"name": "아시아경제", "url": "https://media.naver.com/press/277"},
        {"name": "헤럴드경제", "url": "https://media.naver.com/press/016"},
        {"name": "파이낸셜뉴스", "url": "https://media.naver.com/press/014"},
        {"name": "조선비즈", "url": "https://media.naver.com/press/366"},
        {"name": "디지털타임스", "url": "https://media.naver.com/press/029"},
        {"name": "금융/증권", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=259"},
        {"name": "재테크/부동산", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=260"},
        {"name": "산업/재계", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261"}
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    for target in targets:
        try:
            res = requests.get(target["url"], headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 언론사 페이지 및 카테고리 페이지의 기사 요소 탐색
            items = soup.select('.press_news_title, .press_news_list .title, .sa_text_title, .list_body.newsflash_body ul li a, .cluster_text_headline')
            if not items:
                items = soup.find_all('a', href=True)
            
            seen_titles = set()
            count = 1
            
            for item in items:
                title = item.get_text(strip=True)
                link = item.get('href', '') if item.name == 'a' else (item.find_parent('a')['href'] if item.find_parent('a') else '')
                
                if not link and item.name != 'a':
                    a_tag = item.select_one('a')
                    if a_tag:
                        title = a_tag.get_text(strip=True)
                        link = a_tag.get('href', '')
                        
                if title and link and ('/article/' in link or 'mnews.naver.com' in link) and len(title) >= 10:
                    clean_title = re.sub(r'\s+', ' ', title)
                    if clean_title not in seen_titles:
                        seen_titles.add(clean_title)
                        if not link.startswith('http'):
                            link = 'https://news.naver.com' + link
                        news_list.append({
                            "press_name": target["name"],
                            "rank": f"{count}위",
                            "title": clean_title,
                            "link": link
                        })
                        count += 1
                        if count > 5:
                            break
        except Exception as e:
            print(f"{target['name']} 수집 에러: {e}")
            
    return news_list

def main():
    news_data = crawl_economy_comprehensive()
    
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