import os
import json
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

def crawl_realestate_news():
    url = "https://news.naver.com/breakingnews/section/101/260"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        print(f"페이지를 불러오지 못했습니다. 에러 코드: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    news_data = []

    # 경제(101) > 부동산(260) 하위 섹션 "최신 기사" 목록. data-sid2=260으로 부동산 전용임이 보장되어
    # 다른 경제 하위 카테고리나 정치/사회 기사가 섞이지 않는다.
    items = soup.select('.section_latest_article .sa_list li.sa_item')

    for item in items[:30]:
        title_elem = item.select_one('.sa_text_strong')
        link_elem = item.select_one('.sa_text_title')

        if not (title_elem and link_elem):
            continue

        press_elem = item.select_one('.sa_text_press')
        time_elem = item.select_one('.sa_text_datetime b')
        thumb_elem = item.select_one('.sa_thumb img')

        title = title_elem.get_text(strip=True)
        link = link_elem.get('href', '')
        press_name = press_elem.get_text(strip=True) if press_elem else ""
        upload_time = time_elem.get_text(strip=True) if time_elem else ""
        thumbnail = (thumb_elem.get('src') or thumb_elem.get('data-src') or '') if thumb_elem else ""

        news_data.append({
            "press_name": press_name,
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

    file_path = os.path.join("data", "realestate_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    print(f"성공! 총 {len(news_data)}개의 부동산 뉴스가 {file_path}에 저장되었습니다.")

if __name__ == "__main__":
    crawl_realestate_news()
