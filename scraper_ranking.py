import os
import re
import json
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_ranking_news():
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

    ranking_boxes = soup.select('.rankingnews_box')

    for box in ranking_boxes:
        press_elem = box.select_one('.rankingnews_name')
        press_name = press_elem.get_text(strip=True) if press_elem else "알 수 없는 언론사"

        items = box.select('.rankingnews_list li')
        for item in items:
            rank_elem = item.select_one('.list_ranking_num')
            title_elem = item.select_one('.list_title')
            time_elem = item.select_one('.list_time')
            thumb_elem = item.select_one('.list_img img')

            if not title_elem:
                continue

            rank_match = re.match(r'\d+', rank_elem.get_text(strip=True)) if rank_elem else None
            rank = int(rank_match.group()) if rank_match else None

            # 1~5위만 수집
            if rank is None or rank > 5:
                continue

            title = title_elem.get_text(strip=True)
            link = title_elem.get('href', '')
            upload_time = time_elem.get_text(strip=True) if time_elem else ""
            thumbnail = (thumb_elem.get('src') or thumb_elem.get('data-src') or '') if thumb_elem else ""

            news_data.append({
                "press_name": press_name,
                "rank": rank,
                "title": title,
                "link": link,
                "thumbnail": thumbnail,
                "upload_time": upload_time
            })

    os.makedirs("data", exist_ok=True)

    # 한국 표준시(KST = UTC + 9시간) 적용
    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "news": news_data
    }

    file_path = os.path.join("data", "ranking_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    print(f"성공! 총 {len(news_data)}개의 랭킹 뉴스가 {file_path}에 저장되었습니다.")

if __name__ == "__main__":
    crawl_ranking_news()
