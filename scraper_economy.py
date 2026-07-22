import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_pure_economy_news():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []

    # -------------------------------------------------------------
    # PART 1: 네이버 핵심 경제 5대 카테고리 (TOP 5)
    # -------------------------------------------------------------
    cat_targets = {
        "금융": "https://news.naver.com/breakingnews/section/101/259",
        "증권/주식": "https://news.naver.com/breakingnews/section/101/258",
        "산업/기업": "https://news.naver.com/breakingnews/section/101/261",
        "부동산": "https://news.naver.com/breakingnews/section/101/260",
        "글로벌 경제": "https://news.naver.com/breakingnews/section/101/262"
    }
    
    print("--- [1] 네이버 핵심 경제 5대 카테고리 수집 ---")
    for cat_name, url in cat_targets.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            articles = soup.select('.sa_text')
            seen_titles = set()
            count = 1
            
            for article in articles:
                title_elem = article.select_one('.sa_text_title strong') or article.select_one('.sa_text_title')
                link_elem = article.select_one('.sa_text_title')
                press_elem = article.select_one('.sa_text_press')
                
                if not (title_elem and link_elem):
                    continue
                
                title = title_elem.get_text(strip=True)
                link = link_elem.get('href', '')
                press_name = press_elem.get_text(strip=True) if press_elem else "언론사"

                if title and link and len(title) > 5 and title not in seen_titles:
                    seen_titles.add(title)
                    news_list.append({
                        "category": cat_name,       
                        "press_name": press_name,   
                        "rank": f"{count}위",
                        "title": title,
                        "link": link
                    })
                    count += 1
                    if count > 5:
                        break
            print(f"[{cat_name}] {count-1}개 수집 성공")
        except Exception as e:
            print(f"{cat_name} 수집 에러: {e}")

    # -------------------------------------------------------------
    # PART 2: 언론사별 '경제 섹션(101)' 뉴스 100% 보장 수집
    # -------------------------------------------------------------
    print("\n--- [2] 언론사별 경제 전용 기사 수집 ---")
    
    PRESS_IDS = {
        "매일경제": "009",
        "한국경제": "015",
        "이데일리": "018",
        "파이낸셜뉴스": "014",
        "조선일보": "023",
        "연합뉴스": "001",
        "머니투데이": "008",
        "이투데이": "277",
        "서울경제": "011"
    }

    for press_name, press_id in PRESS_IDS.items():
        try:
            # 네이버 내 해당 언론사의 순수 경제(101) 섹션 목록 주소
            url = f"https://news.naver.com/breakingnews/section/101/{press_id}"
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            articles = soup.select('.sa_text')
            seen_titles = set()
            count = 1
            
            for article in articles:
                title_elem = article.select_one('.sa_text_title strong') or article.select_one('.sa_text_title')
                link_elem = article.select_one('.sa_text_title')
                
                if not (title_elem and link_elem):
                    continue
                    
                title = title_elem.get_text(strip=True)
                link = link_elem.get('href', '')
                
                if title and link and len(title) > 5 and title not in seen_titles:
                    seen_titles.add(title)
                    news_list.append({
                        "category": press_name,
                        "press_name": press_name,
                        "rank": f"{count}위",
                        "title": title,
                        "link": link
                    })
                    count += 1
                    if count > 5:
                        break
            print(f"[{press_name}] {count-1}개 수집 성공")
        except Exception as e:
            print(f"[{press_name}] 크롤링 에러: {e}")
        
    return news_list

def main():
    news_data = crawl_pure_economy_news()
    
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
        
    print(f"\n최종 수집 완료: 총 {len(news_data)}개 기사 저장됨.")

if __name__ == "__main__":
    main()