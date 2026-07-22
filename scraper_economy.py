import os
import json
import re
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
                
                if not (title_elem and link_elem):
                    continue
                
                title = title_elem.get_text(strip=True)
                link = link_elem.get('href', '')

                if title and link and len(title) > 5 and title not in seen_titles:
                    seen_titles.add(title)
                    news_list.append({
                        "category": cat_name,       
                        "press_name": cat_name, # 아임웹에서 '카드 제목'으로 묶어주는 기준키
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
    # PART 2: 언론사별 경제 전용 기사 수집 (URL 및 태그 구조 완전 수정)
    # -------------------------------------------------------------
    print("\n--- [2] 언론사별 경제 전용 기사 수집 ---")
    
    PRESS_IDS = {
        "매일경제": "009",
        "한국경제": "015",
        "이데일리": "018",
        "파이낸셜뉴스": "014",
        "조선비즈": "366", # 경제 전문
        "연합뉴스": "001",
        "머니투데이": "008",
        "아시아경제": "277", # 277은 이투데이가 아니라 아시아경제라 이름 수정
        "서울경제": "011"
    }
    
    # 경제지에 섞인 정치 기사 방어 필터
    exclude_keywords = ["오세훈", "선거", "투표", "국회", "대통령", "더불어민주당", "국민의힘", "정당", "탄핵", "공천", "검찰", "경찰", "재판"]

    for press_name, press_id in PRESS_IDS.items():
        try:
            # 실패 원인 해결: 네이버 언론사 홈 올바른 주소 형식
            url = f"https://media.naver.com/press/{press_id}"
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 실패 원인 해결: 언론사 홈에 맞는 전용 클래스 탐색
            items = soup.select('.press_news_title, .press_news_list .title, .cjs_t, .sa_text_title')
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
                    
                    if any(kw in clean_title for kw in exclude_keywords):
                        continue
                        
                    if clean_title not in seen_titles:
                        seen_titles.add(clean_title)
                        if not link.startswith('http'):
                            link = 'https://news.naver.com' + link
                        
                        news_list.append({
                            "category": press_name,
                            "press_name": press_name, # 아임웹에서 '카드 제목'으로 묶어주는 기준키
                            "rank": f"{count}위",
                            "title": clean_title,
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