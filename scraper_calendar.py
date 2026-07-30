"""경제 일정 캘린더: 미국 FOMC 회의는 연준 홈페이지에서 매번 자동 수집,
한국은행 금융통화위원회(통화정책방향 결정회의) 일정은 연 1회 수동 갱신되는
시드 데이터를 사용한다.

BOK 일정을 자동 스크레이핑하지 않는 이유: bok.or.kr의 회의일정 캘린더
페이지는 JS로 렌더링되는 SPA라 정적 요청으로는 날짜를 가져올 수 없고,
보도자료도 전체 일정을 hwp/pdf 첨부파일로만 제공해 안정적인 자동 파싱이
어렵다. 반면 이 일정은 매년 10월경 다음 해 전체가 한 번에 공식 발표되고
그 뒤로 바뀌지 않으므로, 발표될 때 BOK_SCHEDULE에 한 해 분량을 추가하는
것으로 충분하다.
"""

import os
import re
import json
import time
import random
from datetime import datetime, date, timezone, timedelta
import requests
from bs4 import BeautifulSoup

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)

# 한국은행 금융통화위원회 "통화정책방향 결정회의"(기준금리 결정) 일정.
# 출처: 한국은행 보도자료 "2026년 금융통화위원회 정기회의 개최 및 의사록
# 공개 예정일정" (2025-10-30 공보 2025-10-24호, bok.or.kr).
# 매년 10월 말경 다음 해 일정이 발표되므로, 발표되면 여기에 새 연도를
# 추가해서 갱신할 것 (그 전까지는 이전 연도 값이 그대로 유지됨).
BOK_SCHEDULE = {
    2026: [
        "2026-01-15", "2026-02-26", "2026-04-10", "2026-05-28",
        "2026-07-16", "2026-08-27", "2026-10-22", "2026-11-26",
    ],
}


def fetch_with_retry(url, label):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.text
            print(f"[{label}] 응답이 비정상입니다 (상태 코드 {response.status_code}) - {attempt}/{MAX_RETRIES}회 시도")
        except requests.exceptions.RequestException as e:
            print(f"[{label}] 요청 중 오류가 발생했습니다: {e} - {attempt}/{MAX_RETRIES}회 시도")

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(*RETRY_WAIT_RANGE)
            print(f"[{label}] {wait_seconds:.1f}초 대기 후 재시도합니다...")
            time.sleep(wait_seconds)

    print(f"[{label}] 페이지 3회 재시도 후 실패")
    return None


def _parse_fomc_day(month_name, day_text, year):
    """'15-16*', '8-9*', '27-28' 같은 표기에서 회의 마지막 날(결정 발표일)을 반환."""
    cleaned = day_text.replace("*", "").strip()
    last_day = cleaned.split("-")[-1].strip()
    try:
        return datetime.strptime(f"{year} {month_name} {last_day}", "%Y %B %d").date()
    except ValueError:
        return None


def crawl_fomc_meetings(year):
    html = fetch_with_retry(FOMC_URL, "FOMC 일정")
    if html is None:
        return []

    marker = f"{year} FOMC Meetings"
    start = html.find(marker)
    if start == -1:
        print(f"[calendar] FOMC 페이지에서 '{marker}' 구간을 찾지 못했습니다 (페이지 구조가 바뀌었을 수 있음)")
        return []

    # 다음 연도 패널이 시작되는 지점(대체로 바로 다음에 나오는 'YYYY FOMC Meetings')까지만 잘라서 파싱
    next_marker_pos = html.find("FOMC Meetings", start + len(marker))
    end = next_marker_pos - 40 if next_marker_pos != -1 else len(html)
    chunk = html[start:end]

    soup = BeautifulSoup(chunk, "html.parser")
    months = soup.select(".fomc-meeting__month")
    dates = soup.select(".fomc-meeting__date")

    meetings = []
    for month_el, date_el in zip(months, dates):
        month_name = month_el.get_text(strip=True)
        day_text = date_el.get_text(strip=True)
        parsed = _parse_fomc_day(month_name, day_text, year)
        if parsed:
            meetings.append(parsed.isoformat())

    return meetings


def build_calendar():
    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone)
    today = now_kst.date()
    current_year = today.year

    events = []

    for d in crawl_fomc_meetings(current_year):
        events.append({"date": d, "event": "FOMC 회의(미국 기준금리 결정)", "country": "US"})
    # 연말에는 다음 해 일정도 이미 공개되어 있으므로 함께 수집
    if today.month >= 11:
        for d in crawl_fomc_meetings(current_year + 1):
            events.append({"date": d, "event": "FOMC 회의(미국 기준금리 결정)", "country": "US"})

    for year, dates_list in BOK_SCHEDULE.items():
        for d in dates_list:
            events.append({"date": d, "event": "한국은행 금융통화위원회(기준금리 결정)", "country": "KR"})

    # 지난 일정은 제외하고, 날짜순으로 정렬해서 "다가오는 일정"만 남긴다
    upcoming = sorted(
        (e for e in events if e["date"] >= today.isoformat()),
        key=lambda e: e["date"],
    )

    output = {
        "updated_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
        "events": upcoming,
    }

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "economic_calendar.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"성공! 다가오는 경제 일정 {len(upcoming)}건이 {file_path}에 저장되었습니다.")


def main():
    build_calendar()


if __name__ == "__main__":
    main()
