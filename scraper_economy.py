import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_economy_news():
    # 네이버 뉴스 경제 세부 카테고리 (6개 분야로 확장)
    targets = {
        "금융": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=259",
        "증권/주식": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=258",
        "산업/기업": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261",
        "부동산": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=260",
        "글로벌 경제": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=262",
        "재테크/생활": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=310"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    for cat_name, url in targets.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.content, 'html.parser', from_encoding='euc-kr')
            
            articles = soup.select('.list_body.newsflash_body ul li')
            seen_titles = set()
            count = 1
            
            for li in articles:
                a_tags = li.select('a')
                if not a_tags:
                    continue
                
                target_a = a_tags[1] if len(a_tags) > 1 else a_tags[0]
                title = target_a.get_text(strip=True)
                link = target_a.get('href', '')
                
                # 언론사 이름 추출 부분 (이전 코드에 없던 핵심 로직)
                press_elem = li.select_one('.writing')
                press_name = press_elem.get_text(strip=True) if press_elem else "언론사"
                
                if title and link and len(title) > 5:
                    if title not in seen_titles:
                        seen_titles.add(title)
                        news_list.append({
                            "category": cat_name,       
                            "press_name": press_name,   
                            "rank": f"{count}",
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count > 10: 
                            break
        except Exception as e:
            print(f"{cat_name} 수집 에러: {e}")
            
    return news_list

def main():
    news_data = crawl_economy_news()
    
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
        
    print(f"경제 뉴스 수집 완료: 총 {len(news_data)}개 기사 저장됨.")

if __name__ == "__main__":
    main()