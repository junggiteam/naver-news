import os
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup

def crawl_naver_news():
    url = "https://news.naver.com/main/ranking/popularDay.naver"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"페이지를 불러오지 못했습니다. 에러 코드: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    news_data = []
    
    # 언론사별 랭킹 박스 파싱
    ranking_boxes = soup.select('.rankingnews_box')
    
    for box in ranking_boxes:
        # 언론사 이름 추출 (유연한 태그 탐색)
        press_elem = box.select_one('.rankingnews_name') or box.select_one('strong') or box.select_one('.rankingnews_box_head_title')
        press_name = press_elem.get_text(strip=True) if press_elem else "알 수 없는 언론사"
        
        items = box.select('.rankingnews_list li')
        for item in items:
            # 순위 추출
            rank_elem = item.select_one('.list_num') or item.select_one('em')
            # 제목 및 링크 추출
            title_elem = item.select_one('.list_title') or item.select_one('a')
            
            if title_elem:
                rank = rank_elem.get_text(strip=True) if rank_elem else ""
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')
                
                news_data.append({
                    "press_name": press_name,
                    "rank": rank,
                    "title": title,
                    "link": link
                })

    os.makedirs("data", exist_ok=True)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "news": news_data
    }
    
    file_path = os.path.join("data", "latest_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"성공! 총 {len(news_data)}개의 뉴스가 {file_path}에 저장되었습니다.")

if __name__ == "__main__":
    crawl_naver_news()