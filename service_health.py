"""대시보드용 공개 사이트 상태 점검.

실패해도 예외로 끝내지 않고 data/service_health.json에 오류 상태를 기록한다.
이 파일에는 사이트 주소, HTTP 상태, 응답 시간, 정상/오류 여부만 저장한다.
계정·본문·비밀값 등 민감 정보는 저장하지 않는다.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests


KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "service_health.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CeonoteServiceMonitor/1.0; +https://ceonote.co.kr/)"
}
TARGETS = [
    {
        "id": "sowhat-site",
        "title": "쏘왓레터 사이트",
        "url": "https://ceonote.co.kr/sowhat-auto",
        "marker": "swl-widget",
    },
    {
        "id": "newsbot-site",
        "title": "뉴스봇 사이트",
        "url": "https://ceonote.co.kr/newsbot",
        "marker": "news-widget",
    },
]


def check_target(target):
    started = time.monotonic()
    result = {
        "id": target["id"],
        "title": target["title"],
        "url": target["url"],
        "status": "error",
        "http_status": None,
        "response_ms": None,
        "message": "점검을 시작하지 못했습니다.",
    }
    try:
        response = requests.get(target["url"], headers=HEADERS, timeout=20, allow_redirects=True)
        result["http_status"] = response.status_code
        result["response_ms"] = round((time.monotonic() - started) * 1000)
        if not 200 <= response.status_code < 300:
            result["message"] = f"HTTP {response.status_code} 응답"
        elif target["marker"] not in response.text:
            result["message"] = "페이지 식별 문구를 찾지 못했습니다. 배포 또는 위젯 로딩 상태를 확인하세요."
        else:
            result["status"] = "ok"
            result["message"] = "정상 응답"
    except requests.RequestException as error:
        result["response_ms"] = round((time.monotonic() - started) * 1000)
        result["message"] = f"접속 오류: {error.__class__.__name__}"
    return result


def main():
    checked_at = datetime.now(KST).isoformat()
    services = [check_target(target) for target in TARGETS]
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump({"checked_at": checked_at, "services": services}, file, ensure_ascii=False, indent=2)
    for service in services:
        print(f"[{service['id']}] {service['status']} · {service['message']}")


if __name__ == "__main__":
    main()
