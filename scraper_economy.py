import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_economy_all():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []

    # -------------------------------------------------------------
    # PART 1: 네이버 경제 카테고리 6개 수집 (TOP 5)
    # -------------------------------------------------------------
    cat_targets = {
        "금융": "https://news.naver.com/breakingnews/section/101/259",
        "증권/주식": "https://news.naver.com/breakingnews/section/101/258",
        "산업/기업": "https://news.naver.com/breakingnews/section/101/261",
        "부동산": "https://news.naver.com/breakingnews/section/101/260",
        "글로벌 경제": "https://news.naver.com/breakingnews/section/101/262",
        "재테크/생활": "https://news.naver.com/breakingnews/section/101/310"
    }
    
    print("--- [1] 카테고리 6개 수집 시작 (TOP 5) ---")
    for cat_name, url in cat_targets.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8' # 글자 깨짐 방지
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
                
                if title and link and len(title) > 5:
                    if title not in seen_titles:
                        seen_titles.add(title)
                        news_list.append({
                            "category": cat_name,       
                            "press_name": press_name,   
                            "rank": f"{count}위",
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count > 5: # TOP 5로 조정
                            break
            print(f"[{cat_name}] {count-1}개 수집 성공")
        except Exception as e:
            print(f"{cat_name} 수집 에러: {e}")

    # -------------------------------------------------------------
    # PART 2: 요청하신 주요 신문사/경제지/방송사 15곳 지정 수집 (TOP 5)
    # -------------------------------------------------------------
    print("\n--- [2] 지정 언론사 15곳 수집 시작 (TOP 5) ---")
    
    # 대표님이 지정하신 주요 언론사 리스트
    TARGET_PRESSES = [
        "조선일보", "중앙일보", "동아일보", "매일경제", "한국경제", 
        "이데일리", "한경비즈니스", "파이낸셜뉴스", "연합뉴스", "머니투데이", 
        "이투데이", "KBS", "MBC", "SBS", "YTN", "JTBC"
    ]
    
    ranking_url = "https://news.naver.com/main/ranking/popularDay.naver"
    
    try:
        res = requests.get(ranking_url, headers=headers, timeout=10)
        res.encoding = res.apparent_encoding or 'utf-8' # 글자 깨짐 방지
        soup = BeautifulSoup(res.text, 'html.parser')
        
        boxes = soup.select('.rankingnews_box')
        
        for box in boxes:
            press_elem = box.select_one('.rankingnews_name')
            if not press_elem:
                continue
                
            press_name = press_elem.get_text(strip=True)
            
            # 지정된 언론사만 엄격히 추출
            if any(target in press_name for target in TARGET_PRESSES):
                items = box.select('.rankingnews_list li')
                count = 1
                
                for item in items:
                    title_elem = item.select_one('.list_title')
                    if not title_elem:
                        continue
                        
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    
                    if title and link:
                        news_list.append({
                            "category": press_name,
                            "press_name": press_name,
                            "rank": f"{count}위",
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count > 5: # TOP 5로 조정
                            break
                print(f"[{press_name}] 5개 수집 완료")
    except Exception as e:
        print(f"언론사 수집 중 에러: {e}")
        
    return news_list

def main():
    news_data = crawl_economy_all()
    
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