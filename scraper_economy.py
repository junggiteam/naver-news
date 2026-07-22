import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

def crawl_all_economy_ranking():
    # 종합 뉴스와 동일한 랭킹 페이지 구조에서 경제 섹션 데이터 추출
    url = "https://news.naver.com/main/ranking/popularDay.naver?sectionId=101"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    news_list = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 랭킹 페이지 내의 모든 언론사 카드 박스 탐색
        press_boxes = soup.select('.rankingnews_box')
        
        for box in press_boxes:
            # 언론사 이름 추출
            press_name_tag = box.select_one('.rankingnews_name')
            if not press_name_tag:
                continue
            press_name = press_name_tag.get_text(strip=True)
            
            # 해당 언론사의 상위 5개 기사 수집
            articles = box.select('.rankingnews_list li')
            count = 1
            
            for li in articles:
                a_tag = li.select_one('a')
                if not a_tag:
                    continue
                
                title = a_tag.get_text(strip=True)
                link = a_tag.get('href', '')
                
                if title and link:
                    if not link.startswith('http'):
                        link = 'https://news.naver.com' + link
                        
                    news_list.append({
                        "press_name": press_name,
                        "rank": f"{count}위",
                        "title": title,
                        "link": link
                    })
                    count += 1
                    if count > 5:
                        break
                        
    except Exception as e:
        print(f"경제 전체 랭킹 수집 중 에러: {e}")
        
    return news_list

def main():
    all_news = crawl_all_economy_ranking()
    
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
        
    print(f"수집 완료: 총 {len(all_news)}개 기사 (언론사 약 {len(all_news)//5}개) 저장됨.")

if __name__ == "__main__":
    main()