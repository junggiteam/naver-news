import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_economy_news():
    # 100% 안정적으로 데이터를 긁어오는 네이버 뉴스 전통 리스트 페이지
    targets = {
        "금융": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=259",
        "증권/투자": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=258",
        "재테크": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=310",
        "부동산": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=260",
        "산업/재계": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    for cat_name, url in targets.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 리스트 페이지 내 기사 제목 및 링크 추출
            items = soup.select('.list_body.newsflash_body ul li a')
            seen_titles = set()
            
            count = 1
            for a in items:
                title = a.get_text(strip=True)
                link = a.get('href', '')
                
                if title and link and len(title) > 5:
                    if title not in seen_titles:
                        seen_titles.add(title)
                        news_list.append({
                            "press_name": cat_name,
                            "rank": f"{count}위",
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count > 5:
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
        
    print(f"수집 완료: 총 {len(news_data)}개 기사 저장됨.")

if __name__ == "__main__":
    main()