import os
import json
import re
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_rich_economy_news():
    # 주요 경제 언론사 및 핵심 카테고리를 대거 포함하여 풍성하게 수집
    targets = [
        {"name": "매일경제", "url": "https://media.naver.com/press/009"},
        {"name": "한국경제", "url": "https://media.naver.com/press/015"},
        {"name": "머니투데이", "url": "https://media.naver.com/press/008"},
        {"name": "서울경제", "url": "https://media.naver.com/press/011"},
        {"name": "이데일리", "url": "https://media.naver.com/press/018"},
        {"name": "아시아경제", "url": "https://media.naver.com/press/277"},
        {"name": "파이낸셜뉴스", "url": "https://media.naver.com/press/014"},
        {"name": "조선비즈", "url": "https://media.naver.com/press/366"},
        {"name": "금융/증권", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=259"},
        {"name": "부동산/재테크", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=260"},
        {"name": "산업/재계", "url": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261"}
    ]
    
    # 경제 뉴스에 섞여 들어오는 정치·사회 이슈 키워드 차단 목록
    exclude_keywords = [
        "오세훈", "선거", "투표", "국회", "대통령", "더불어민주당", "국민의힘", 
        "정당", "장관", "탄핵", "공천", "의원", "당대표", "검찰", "경찰", 
        "재판", "법원", "고발", "구속", "징역", "벌금", "시장직", "민주교육"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    for target in targets:
        try:
            res = requests.get(target["url"], headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
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
                    
                    # 정치/사회 이슈 키워드가 포함된 기사는 제외
                    if any(kw in clean_title for kw in exclude_keywords):
                        continue
                        
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
    news_data = crawl_rich_economy_news()
    
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
        
    print(f"수집 완료: 총 {len(news_data)}개 순수 경제 기사 저장됨.")

if __name__ == "__main__":
    main()