"""data/dart_filings.json(오늘자 주요사항보고 전체)의 각 항목을
dart_report_classifier로 분류하고, 매칭되는 DART "주요사항보고서
주요정보"(DS005) 상세 API를 호출해서 report_nm만으로는 알 수 없는 실제
수치(금액/비율/이자율/날짜 등)를 확보한다.

- 분류가 안 되는 report_nm(정기공시 등 19개 유형 밖)은 에러가 아니라
  그냥 스킵 대상이다.
- 개별 상세 API 호출이 실패해도(네트워크 오류, status != "000", 빈
  결과 등) 그 항목만 상세정보 없이 건너뛰고 나머지는 계속 진행한다 -
  run_scheduled.py의 다른 모듈들과 동일한 방어적 패턴.
- dart_filings.json 자체가 "오늘 것만" 담고 매일 덮어쓰는 파일이라,
  여기서 만드는 data/dart_filings_detail.json도 날짜별 누적이 아니라
  매 실행마다 오늘자로 새로 쓴다(원본과 생명주기를 맞춤).
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
import requests

import dart_report_classifier

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


def build_details():
    if not DART_API_KEY:
        print("[dart_report_detail] DART_API_KEY 없음 - 상세정보 수집 생략")
        return {}

    filings_data = _load_json("data/dart_filings.json")
    filings = filings_data.get("filings") or []
    if not filings:
        print("[dart_report_detail] 오늘 주요사항보고가 없음 - 상세정보 수집 생략")
        return {}

    today_str = datetime.now(KST).strftime("%Y%m%d")

    details = {}
    matched = 0
    skipped_no_match = 0
    skipped_no_corp_code = 0
    skipped_api_fail = 0

    for item in filings:
        report_nm = item.get("report_nm", "")
        result = dart_report_classifier.classify(report_nm)
        if result is None:
            skipped_no_match += 1
            continue

        category_label, endpoint = result
        corp_code = item.get("corp_code", "")
        rcept_no = item.get("rcept_no", "")
        if not corp_code or not rcept_no:
            skipped_no_corp_code += 1
            continue

        time.sleep(CALL_DELAY_SECONDS)
        raw_detail = fetch_detail(endpoint, corp_code, today_str, today_str)
        if raw_detail is None:
            skipped_api_fail += 1
            continue

        details[rcept_no] = {"category": category_label, "raw_detail": raw_detail}
        matched += 1

    os.makedirs("data", exist_ok=True)
    with open(DETAIL_FILE, "w", encoding="utf-8") as f:
        json.dump(details, f, ensure_ascii=False, indent=2)

    print(
        f"[dart_report_detail] {today_str} 주요사항보고 {len(filings)}건 중 "
        f"상세정보 매칭 {matched}건 (분류 안 됨 {skipped_no_match}, "
        f"corp_code/rcept_no 없음 {skipped_no_corp_code}, API 실패/빈 결과 {skipped_api_fail}) "
        f"-> {DETAIL_FILE}"
    )
    return details


def main():
    build_details()


if __name__ == "__main__":
    main()
