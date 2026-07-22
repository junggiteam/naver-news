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
    # PART 1: 순수 경제 카테고리 6개 (TOP 5)
    # -------------------------------------------------------------
    cat_targets = {
        "금융": "https://news.naver.com/breakingnews/section/101/259",
        "증권/주식": "https://news.naver.com/breakingnews/section/101/258",
        "산업/기업": "https://news.naver.com/breakingnews/section/101/261",
        "부동산": "https://news.naver.com/breakingnews/section/101/260",
        "글로벌 경제": "https://news.naver.com/breakingnews/section/101/262",
        "재테크/투자": "https://news.naver.com/breakingnews/section/101/310"
    }
    
    print("--- [1] 순수 경제 분야별 6개 섹션 수집 (TOP 5) ---")
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
                        if count > 5:
                            break
            print(f"[{cat_name}] {count-1}개 수집 성공")
        except Exception as e:
            print(f"{cat_name} 수집 에러: {e}")

    # -------------------------------------------------------------
    # PART 2: 메이저 언론사별 '경제 섹션(101)' 기사만 엄격 추출 (TOP 5)
    # (정치/사회/연예/생활 등 기타 분야 100% 차단)
    # -------------------------------------------------------------
    print("\n--- [2] 지정 언론사별 '경제 전용' 기사만 수집 (TOP 5) ---")
    
    # 주요 언론사 고유 ID (네이버 경제 섹션 전용)
    PRESS_IDS = {
        "조선일보": "023",
        "중앙일보": "025",
        "동아일보": "020",
        "매일경제": "009",
        "한국경제": "015",
        "이데일리": "018",
        "한경비즈니스": "050",
        "파이낸셜뉴스": "014",
        "연합뉴스": "001",
        "머니투데이": "008",
        "이투데이": "277",
        "KBS": "056",
        "MBC": "214",
        "SBS": "055",
        "YTN": "052",
        "JTBC": "437"
    }
    
    # 금지 단어 키워드 (정치/사회 이슈 차단용 2차 필터)
    FORBIDDEN_KEYWORDS = ["대통령", "여당", "야당", "국회", "검찰", "경찰", "사고", "살인", "연예", "아이돌", "체포", "구속"]

    for press_name, press_id in PRESS_IDS.items():
        try:
            # 네이버 뉴스 '경제 섹션(101)' 내 해당 언론사 속보/주요 뉴스 URL
            url = f"https://news.naver.com/breakingnews/section/101/{press_id}"
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            articles = soup.select('.sa_text')
            
            # 속보 페이지에 데이터가 적을 경우 경제 헤드라인 차선책 적용
            if not articles:
                url_alt = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={press_id}&sid1=101"
                res_alt = requests.get(url_alt, headers=headers, timeout=10)
                res_alt.encoding = res_alt.apparent_encoding or 'utf-8'
                soup = BeautifulSoup(res_alt.text, 'html.parser')
                articles = soup.select('.type06_headline li, .type06 li')

            seen_titles = set()
            count = 1
            
            for article in articles:
                title_elem = article.select_one('.sa_text_title strong') or article.select_one('a')
                link_elem = article.select_one('.sa_text_title') or article.select_one('a')
                
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                link = link_elem.get('href', '') if link_elem else ''
                
                # 금지 키워드 검사 (정치/사회 분야 확실히 필터링)
                if any(bad in title for bad in FORBIDDEN_KEYWORDS):
                    continue

                if title and link and len(title) > 5:
                    if title not in seen_titles:
                        seen_titles.add(title)
                        news_list.append({
                            "category": press_name,
                            "press_name": press_name,
                            "rank": f"{count}위",
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count > 5: # TOP 5
                            break
                            
            print(f"[{press_name} 경제] {count-1}개 수집 완료")
        except Exception as e:
            print(f"[{press_name}] 수집 에러: {e}")
        
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
        
    print(f"\n최종 수집 완료: 총 {len(news_data)}개 순수 경제 기사 저장됨.")

if __name__ == "__main__":
    main()