import os
import re
import json
import time
import random
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)  # 재시도 사이 대기 시간(초)


def fetch_with_retry(url, headers, label, timeout=10):
    """요청 실패(타임아웃/5xx 등 비정상 응답) 시 최대 MAX_RETRIES회까지 재시도.
    모두 실패하면 None을 반환해 호출부에서 해당 페이지를 건너뛸 수 있게 한다."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response
            print(f"[{label}] 응답이 비정상입니다 (상태 코드 {response.status_code}) - {attempt}/{MAX_RETRIES}회 시도")
        except requests.exceptions.RequestException as e:
            print(f"[{label}] 요청 중 오류가 발생했습니다: {e} - {attempt}/{MAX_RETRIES}회 시도")

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(*RETRY_WAIT_RANGE)
            print(f"[{label}] {wait_seconds:.1f}초 대기 후 재시도합니다...")
            time.sleep(wait_seconds)

    print(f"[{label}] 페이지 3회 재시도 후 실패")
    return None


def parse_time_to_iso(text, now_kst):
    """네이버가 제공하는 상대/절대 시간 표기를 크롤링 시점(now_kst) 기준
    ISO 8601 절대 시각 문자열로 변환. 인식하지 못하면 빈 문자열을 반환."""
    text = (text or "").strip()
    if not text:
        return ""

    if text in ("방금전", "방금 전"):
        return now_kst.isoformat()

    match = re.match(r'^(\d+)분전$', text)
    if match:
        return (now_kst - timedelta(minutes=int(match.group(1)))).isoformat()

    match = re.match(r'^(\d+)시간전$', text)
    if match:
        return (now_kst - timedelta(hours=int(match.group(1)))).isoformat()

    match = re.match(r'^(\d+)일전$', text)
    if match:
        return (now_kst - timedelta(days=int(match.group(1)))).isoformat()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=now_kst.tzinfo).isoformat()
        except ValueError:
            continue

    return ""


def crawl_economy_section_news():
    url = "https://news.naver.com/section/101"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    response = fetch_with_retry(url, headers, "경제 뉴스")
    if response is None:
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    news_data = []

    # 한국 표준시(KST = UTC + 9시간) 적용, 상대 시간 파싱 기준 시점으로도 사용
    kst_timezone = timezone(timedelta(hours=9))
    now_kst_dt = datetime.now(kst_timezone)
    now_kst_minute = now_kst_dt.replace(second=0, microsecond=0)

    # 경제 섹션(101) 전용 "최신 기사" 목록. 헤드라인 블록과 달리 언론사/시간이 함께 제공되고
    # section1_id가 101로 고정되어 정치/사회/연예 기사가 섞이지 않는다.
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
        published_at = parse_time_to_iso(upload_time, now_kst_minute)

        news_data.append({
            "press_name": press_name,
            "title": title,
            "link": link,
            "thumbnail": thumbnail,
            "upload_time": upload_time,
            "published_at": published_at
        })

    os.makedirs("data", exist_ok=True)

    output = {
        "updated_at": now_kst_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "news": news_data
    }

    file_path = os.path.join("data", "economy_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    print(f"성공! 총 {len(news_data)}개의 경제 뉴스가 {file_path}에 저장되었습니다.")


def main():
    crawl_economy_section_news()


if __name__ == "__main__":
    main()
