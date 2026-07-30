"""DART(전자공시시스템) Open API에서 오늘의 주요사항보고 공시를 가져온다.

정기공시/발행공시 등 대량의 잡다한 공시를 다 보여주면 노이즈가 크므로,
DART가 자체적으로 분류해 둔 공시유형 중 "B(주요사항보고)"만 필터링한다.
유상증자/합병/자기주식처분 등 실제로 중요한 이벤트 위주라 노이즈가 적다.
"""

import os
import json
import time
import random
from datetime import datetime, timezone, timedelta
import requests

DART_API_KEY = os.environ.get("DART_API_KEY", "")
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)  # 재시도 사이 대기 시간(초)


def fetch_with_retry(params, label):
    """요청 실패(타임아웃/5xx 등 비정상 응답) 시 최대 MAX_RETRIES회까지 재시도.
    모두 실패하면 None을 반환."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(DART_LIST_URL, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            print(f"[{label}] 응답이 비정상입니다 (상태 코드 {response.status_code}) - {attempt}/{MAX_RETRIES}회 시도")
        except requests.exceptions.RequestException as e:
            print(f"[{label}] 요청 중 오류가 발생했습니다: {e} - {attempt}/{MAX_RETRIES}회 시도")

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(*RETRY_WAIT_RANGE)
            print(f"[{label}] {wait_seconds:.1f}초 대기 후 재시도합니다...")
            time.sleep(wait_seconds)

    print(f"[{label}] 페이지 3회 재시도 후 실패")
    return None


def crawl_dart_filings():
    if not DART_API_KEY:
        print("DART_API_KEY 없음 - DART 공시 수집 생략")
        return

    kst_timezone = timezone(timedelta(hours=9))
    today = datetime.now(kst_timezone).strftime("%Y%m%d")

    params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de": today,
        "end_de": today,
        "pblntf_ty": "B",  # 주요사항보고
        "page_no": 1,
        "page_count": 100,
    }

    data = fetch_with_retry(params, "DART 공시")
    if data is None:
        return

    status = data.get("status")
    if status == "013":
        # 013 = 조회된 데이터가 없습니다 (오늘 해당 유형 공시가 없는 정상 상황)
        filings_raw = []
    elif status != "000":
        print(f"DART API 오류 (status={status}): {data.get('message')}")
        return
    else:
        filings_raw = data.get("list", [])

    filings = []
    for item in filings_raw:
        rcept_no = item.get("rcept_no", "")
        filings.append({
            "corp_name": item.get("corp_name", ""),
            "report_nm": item.get("report_nm", "").strip(),
            "rcept_dt": item.get("rcept_dt", ""),
            "rcept_no": rcept_no,
            "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else "",
        })

    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")
    output = {"updated_at": now_kst, "filings": filings}

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "dart_filings.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"성공! 오늘 주요사항보고 공시 {len(filings)}건이 {file_path}에 저장되었습니다.")


def main():
    crawl_dart_filings()


if __name__ == "__main__":
    main()
