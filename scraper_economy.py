import os
import json
import re
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_pure_economy_sections():
    # 정치 이슈가 섞이지 않는 순수 네이버 경제 하위 섹션별 공식 리스트
    targets = [
        {"name": "금융", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=259"},
        {"name": "증권/투자", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=258"},
        {"name": "재테크", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=310"},
        {"name": "부동산", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=260"},
        {"name": "산업/재계", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261"},
        {"name": "글로벌 경제", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=262"},
        {"name": "경제 일반", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=263"}
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    for target in targets:
        try:
            res = requests.get(target["url"], headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 각 섹션 리스트에서 기사 요소 추출
            items = soup.select('.list_body.newsflash_body ul li a, .sa_text_title, .cluster_text_headline')
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
    news_data = crawl_pure_economy_sections()
    
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