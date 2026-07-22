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
    # PART 1: 5개 순수 경제 카테고리 (필터 코드 전혀 없음)
    # -------------------------------------------------------------
    cat_targets = {
        "금융": "https://news.naver.com/breakingnews/section/101/259",
        "증권/주식": "https://news.naver.com/breakingnews/section/101/258",
        "산업/기업": "https://news.naver.com/breakingnews/section/101/261",
        "부동산": "https://news.naver.com/breakingnews/section/101/260",
        "글로벌 경제": "https://news.naver.com/breakingnews/section/101/262"
    }
    
    print("--- [1] 순수 경제 5대 섹션 수집 ---")
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

                # 조건 없이 단순 중복 검사 후 바로 수집
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
    # PART 2: 언론사 공식 사이트 경제 RSS 수집 (필터 코드 전혀 없음)
    # -------------------------------------------------------------
    print("\n--- [2] 언론사 직영 경제 RSS 수집 ---")
    
    PRESS_RSS_URLS = {
        "매일경제": "https://www.mk.co.kr/rss/30100041/",
        "한국경제": "https://www.hankyung.com/feed/economy",
        "이데일리": "https://rss.edaily.co.kr/edaily_news.xml",
        "파이낸셜뉴스": "https://www.fnnews.com/rss/fn_realnews_economy.xml",
        "조선일보": "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml",
        "연합뉴스": "https://www.yna.co.kr/rss/economy.xml"
    }

    for press_name, rss_url in PRESS_RSS_URLS.items():
        try:
            res = requests.get(rss_url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'xml')
            
            items = soup.find_all('item')
            seen_titles = set()
            count = 1
            
            for item in items:
                title_elem = item.find('title')
                link_elem = item.find('link')
                
                if not (title_elem and link_elem):
                    continue
                    
                title = title_elem.get_text(strip=True)
                link = link_elem.get_text(strip=True)
                
                title = BeautifulSoup(title, "html.parser").get_text(strip=True)

                # 조건 없이 단순 중복 검사 후 바로 수집
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
            print(f"[{press_name} 자체사이트] {count-1}개 수집 완료")
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