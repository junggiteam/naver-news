import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_naver_news(url, category_name):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 네이버 기사 제목 및 링크 추적
        titles = soup.select('.sa_text_title, .sh_text_headline, .sa_text_strong')
        seen_titles = set()
        
        count = 1
        for t in titles:
            title = t.get_text(strip=True)
            parent_a = t.find_parent('a')
            
            if parent_a and parent_a.has_attr('href'):
                link = parent_a['href']
            else:
                continue
                
            if len(title) >= 10 and title not in seen_titles:
                seen_titles.add(title)
                news_list.append({
                    "press_name": category_name,
                    "rank": f"{count}위",
                    "title": title,
                    "link": link
                })
                count += 1
                if count > 5:
                    break
    except Exception as e:
        print(f"Error crawling {category_name}: {e}")
        
    return news_list

def main():
    targets = {
        "금융/증권": "https://news.naver.com/section/101",
        "산업/재계": "https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2=261",
        "매일경제": "https://media.naver.com/press/009",
        "한국경제": "https://media.naver.com/press/015",
        "머니투데이": "https://media.naver.com/press/008"
    }
    
    all_news = []
    for cat, url in targets.items():
        items = crawl_naver_news(url, cat)
        all_news.extend(items)
        
    os.makedirs("data", exist_ok=True)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "news": all_news
    }
    
    file_path = os.path.join("data", "economy_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"수집 완료: 총 {len(all_news)}개 기사 저장됨.")

if __name__ == "__main__":
    main()