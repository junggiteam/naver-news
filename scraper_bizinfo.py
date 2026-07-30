"""기업마당(bizinfo.go.kr) Open API에서 정부지원사업 공고를 가져온다.

"정부지원사업"과 "소상공인 정책자금"을 같은 API 한 번으로 커버한다:
응답의 trgetNm(지원대상) 필드가 "소상공인"을 포함하는 것만 따로 추려
소상공인 전용 섹션으로 쓴다 (API 자체에 서버측 대상 필터 파라미터가
없어 실제 호출로 확인함 - 그래서 넉넉히 받아 클라이언트에서 거른다).
"""

import os
import re
import json
import time
import random
from datetime import datetime, timezone, timedelta
import requests

BIZINFO_API_KEY = os.environ.get("BIZINFO_API_KEY", "")
BIZINFO_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)  # 재시도 사이 대기 시간(초)
FETCH_COUNT = 100  # 최신순으로 넉넉히 받아서 클라이언트에서 소상공인만 추가로 거름


def fetch_with_retry(params, label):
    """요청 실패(타임아웃/5xx/JSON 파싱 오류 등) 시 최대 MAX_RETRIES회까지 재시도.
    모두 실패하면 None을 반환."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(BIZINFO_URL, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            print(f"[{label}] 응답이 비정상입니다 (상태 코드 {response.status_code}) - {attempt}/{MAX_RETRIES}회 시도")
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"[{label}] 요청 중 오류가 발생했습니다: {e} - {attempt}/{MAX_RETRIES}회 시도")

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(*RETRY_WAIT_RANGE)
            print(f"[{label}] {wait_seconds:.1f}초 대기 후 재시도합니다...")
            time.sleep(wait_seconds)

    print(f"[{label}] 페이지 3회 재시도 후 실패")
    return None


def _strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = text.replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _simplify(item):
    return {
        "title": (item.get("pblancNm") or "").strip(),
        "target": item.get("trgetNm", ""),
        "field": item.get("pldirSportRealmLclasCodeNm", ""),
        "org": item.get("jrsdInsttNm") or item.get("excInsttNm") or "",
        "apply_period": item.get("reqstBeginEndDe", ""),
        "summary": _strip_html(item.get("bsnsSumryCn", ""))[:200],
        "link": item.get("pblancUrl", ""),
        "created_at": item.get("creatPnttm", ""),
    }


def crawl_support_programs():
    if not BIZINFO_API_KEY:
        print("BIZINFO_API_KEY 없음 - 정부지원사업 공고 수집 생략")
        return

    params = {
        "crtfcKey": BIZINFO_API_KEY,
        "dataType": "json",
        "searchCnt": FETCH_COUNT,
    }

    data = fetch_with_retry(params, "기업마당 지원사업")
    if data is None:
        return

    items = data.get("jsonArray") or []
    all_programs = [_simplify(it) for it in items]
    soso_programs = [p for p in all_programs if "소상공인" in p["target"]]

    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "programs": all_programs[:30],
        "soso_programs": soso_programs[:15],
    }

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "support_programs.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(
        f"성공! 정부지원사업 {len(output['programs'])}건"
        f"(그 중 소상공인 대상 {len(output['soso_programs'])}건)이 {file_path}에 저장되었습니다."
    )


def main():
    crawl_support_programs()


if __name__ == "__main__":
    main()
