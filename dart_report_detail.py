"""data/dart_ma_signals.json(정책·캘린더 M&A 탭이 쓰는, 오늘 날짜 키의
M&A 카테고리별 공시 목록)을 그대로 순회하며 DART "주요사항보고서
주요정보"(DS005) 상세 API를 호출해서 report_nm만으로는 알 수 없는 실제
수치(금액/비율/이자율/날짜 등)를 확보한다.

정책·캘린더(dart_ma_signals.json)를 기준으로 삼는다 - 예전엔
dart_filings.json 전체(오늘의 주요사항보고 19개 유형 전부)를
dart_report_classifier.py로 별도 재분류했지만, 그러면 이 모듈이 확보하는
회사 목록과 정책·캘린더 M&A 탭이 보여주는 목록이 서로 다른 분류 기준을
써서 어긋날 수 있었다. dart_ma_signals.py가 이미 분류해 둔 결과(같은
카테고리, 같은 corp_code/rcept_no)를 그대로 재사용하면 두 화면이 항상
정확히 일치한다 - dart_report_classifier.py는 이제 이 흐름에서 안 쓰인다.

- 카테고리에 대응하는 상세 API가 없는 경우(dart_ma_signals.
  MA_CATEGORY_ENDPOINTS에 없는 카테고리, 예: 경영권이동_최대주주변경 -
  DS005에 대응 API 자체가 없음이 확인됨)는 에러가 아니라 그냥 스킵
  대상이다.
- 개별 상세 API 호출이 실패해도(네트워크 오류, status != "000", 빈
  결과 등) 그 항목만 상세정보 없이 건너뛰고 나머지는 계속 진행한다 -
  run_scheduled.py의 다른 모듈들과 동일한 방어적 패턴.
- dart_ma_signals.json의 오늘 날짜 키 자체가 그날그날의 스냅샷이 아니라
  "지금까지 갱신된 오늘의 최신 상태"이므로, 여기서 만드는
  data/dart_filings_detail.json도 날짜별 누적이 아니라 매 실행마다
  오늘자로 새로 쓴다(원본과 생명주기를 맞춤).
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
import requests

import dart_ma_signals

KST = timezone(timedelta(hours=9))

DART_API_KEY = os.environ.get("DART_API_KEY", "")
DETAIL_API_BASE = "https://opendart.fss.or.kr/api"
DETAIL_FILE = os.path.join("data", "dart_filings_detail.json")

CALL_DELAY_SECONDS = 0.3  # 상세 API 호출 사이 짧은 딜레이(과부하 방지)


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def fetch_detail(endpoint, corp_code, bgn_de, end_de):
    """상세 API 1건 호출. 실패/빈 결과는 None(예외를 밖으로 던지지 않음)."""
    url = f"{DETAIL_API_BASE}/{endpoint}.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"[dart_report_detail] {endpoint} 호출 실패(corp_code={corp_code}): {e}")
        return None

    status = data.get("status")
    if status != "000":
        # 013 = 조회된 데이터 없음(정상 상황 - 이 유형으로 분류는 됐지만
        # 아직 상세 데이터가 안 올라온 경우 등), 그 외는 API 오류
        if status != "013":
            print(f"[dart_report_detail] {endpoint} 응답 오류(corp_code={corp_code}, status={status}): {data.get('message')}")
        return None

    result_list = data.get("list") or []
    if not result_list:
        return None
    return result_list[0]


def _resolve_endpoint(category, action):
    """dart_ma_signals.MA_CATEGORY_ENDPOINTS에서 카테고리(+필요하면 action)에
    맞는 엔드포인트를 찾는다. 매핑 자체가 없는 카테고리(경영권이동_
    최대주주변경 등)는 None - 스킵 대상이지 오류가 아니다."""
    mapping = dart_ma_signals.MA_CATEGORY_ENDPOINTS.get(category)
    if mapping is None:
        return None
    if isinstance(mapping, str):
        return mapping
    return mapping.get(action)


def build_details():
    if not DART_API_KEY:
        print("[dart_report_detail] DART_API_KEY 없음 - 상세정보 수집 생략")
        return {}

    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    today_compact = now_kst.strftime("%Y%m%d")

    archive = _load_json("data/dart_ma_signals.json")
    today_signals = archive.get(today_str) or {}
    total_items = sum(len(today_signals.get(cat) or []) for cat in dart_ma_signals.MA_CATEGORIES)
    if not total_items:
        print("[dart_report_detail] 오늘 M&A 시그널(dart_ma_signals.json)이 없음 - 상세정보 수집 생략")
        return {}

    details = {}
    matched = 0
    skipped_no_endpoint = 0
    skipped_no_corp_code = 0
    skipped_api_fail = 0

    for category in dart_ma_signals.MA_CATEGORIES:
        for item in today_signals.get(category) or []:
            endpoint = _resolve_endpoint(category, item.get("action"))
            if endpoint is None:
                skipped_no_endpoint += 1
                continue

            corp_code = item.get("corp_code", "")
            rcept_no = item.get("rcept_no", "")
            if not corp_code or not rcept_no:
                skipped_no_corp_code += 1
                continue

            time.sleep(CALL_DELAY_SECONDS)
            raw_detail = fetch_detail(endpoint, corp_code, today_compact, today_compact)
            if raw_detail is None:
                skipped_api_fail += 1
                continue

            details[rcept_no] = {"category": category, "raw_detail": raw_detail}
            matched += 1

    os.makedirs("data", exist_ok=True)
    with open(DETAIL_FILE, "w", encoding="utf-8") as f:
        json.dump(details, f, ensure_ascii=False, indent=2)

    print(
        f"[dart_report_detail] {today_str} M&A 시그널 {total_items}건 중 "
        f"상세정보 매칭 {matched}건 (대응 API 없음 {skipped_no_endpoint}, "
        f"corp_code/rcept_no 없음 {skipped_no_corp_code}, API 실패/빈 결과 {skipped_api_fail}) "
        f"-> {DETAIL_FILE}"
    )
    return details


def main():
    build_details()


if __name__ == "__main__":
    main()
