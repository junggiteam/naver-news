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
    
    # 🚫 강력 필터링 키워드 (인사, 동정, 연예, 정치, 사회 이슈 완전 차단)
    FORBIDDEN_KEYWORDS = [
        "[인사]", "인사]", "(인사)", "[부음]", "부음]", "(부음)", "프로필",
        "대통령", "여당", "야당", "국회", "검찰", "경찰", "사고", "살인", 
        "연예", "아이돌", "체포", "구속", "영화", "배우", "평론가", "호프", 
        "소림축구", "비하", "논란", "일침", "소울커피", "먹튀"
    ]

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
                
                if any(bad in title for bad in FORBIDDEN_KEYWORDS):
                    continue

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
    # PART 2: 주요 언론사별 '순수 경제 기사만' 5개 보장 수집
    # -------------------------------------------------------------
    print("\n--- [2] 지정 언론사별 '경제 전용' 기사 수집 (TOP 5 보장) ---")
    
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

    for press_name, press_id in PRESS_IDS.items():
        try:
            seen_titles = set()
            collected_articles = []
            
            # 1차 시도: 네이버 뉴스 경제 섹션(101) 속보
            url = f"https://news.naver.com/breakingnews/section/101/{press_id}"
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            articles = soup.select('.sa_text, .news_list li, .type06_headline li, .type06 li')
            
            for article in articles:
                title_elem = article.select_one('.sa_text_title strong') or article.select_one('.sa_text_title') or article.select_one('a')
                link_elem = article.select_one('.sa_text_title') or article.select_one('a')
                
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                link = link_elem.get('href', '') if link_elem else ''
                
                if any(bad in title for bad in FORBIDDEN_KEYWORDS):
                    continue

                if title and link and len(title) > 5 and title not in seen_titles:
                    seen_titles.add(title)
                    collected_articles.append((title, link))

            # 2차 시도: 부족할 경우 추가 수집
            if len(collected_articles) < 5:
                url_rank = f"https://news.naver.com/main/ranking/office.naver?officeId={press_id}"
                res_rank = requests.get(url_rank, headers=headers, timeout=10)
                res_rank.encoding = res_rank.apparent_encoding or 'utf-8'
                soup_rank = BeautifulSoup(res_rank.text, 'html.parser')
                
                rank_items = soup_rank.select('.rankingnews_list li')
                for item in rank_items:
                    title_elem = item.select_one('.list_title')
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    
                    if any(bad in title for bad in FORBIDDEN_KEYWORDS):
                        continue
                        
                    if title and link and len(title) > 5 and title not in seen_titles:
                        seen_titles.add(title)
                        collected_articles.append((title, link))
                        if len(collected_articles) >= 5:
                            break

            count = 1
            for title, link in collected_articles[:5]:
                news_list.append({
                    "category": press_name,
                    "press_name": press_name,
                    "rank": f"{count}위",
                    "title": title,
                    "link": link
                })
                count += 1
                
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