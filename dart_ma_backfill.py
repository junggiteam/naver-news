"""dart_ma_signals.json을 2026-01-01부터 오늘까지 소급 백필하는 1회성 스크립트.

평소 운영 중인 scraper_dart.py + dart_ma_signals.py는 "오늘 하루치"만 계속
누적하는 구조라, 이 스크립트를 도입하기 이전 과거 날짜는 데이터가 비어있다.
이 스크립트는 DART Open API list.json을 bgn_de=20260101 ~ end_de=오늘 범위로
직접 조회해서 그 공백을 한 번에 채운다.

- report_nm 분류 로직은 dart_ma_signals.py의 classify_report()를 그대로
  재사용한다(로직 중복 금지 - 두 곳에서 분류 기준이 갈리면 위험).
- DART API는 page_count 최대 100건/페이지라 total_page만큼 순회해야 한다.
  페이지 사이 0.5초 딜레이를 둬서 API를 과도하게 두드리지 않는다(무료 한도
  일 20,000건에 비하면 이 백필 호출량은 넉넉히 여유 있음).
- 실행 중간에 끊겨도 이어서 할 수 있도록, 페이지를 받을 때마다
  data/dart_ma_backfill_checkpoint.json에 지금까지 모은 원본 리스트와
  완료된 페이지 번호를 저장한다. 재실행하면 완료된 페이지는 건너뛰고
  이어서 받는다. 전체 완료 후에는 체크포인트 파일을 지운다.
- 최종 결과는 dart_ma_signals.py와 동일한 날짜별 아카이브 스키마
  ({"YYYY-MM-DD": {카테고리: [...]}})로 변환해서, 백필 대상 기간
  (2026-01-01~오늘) 안의 기존 날짜 키만 교체하고 그 밖의 날짜는 보존한다.
"""

import os
import json
import time
import random
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import requests

import dart_ma_signals as ma

KST = timezone(timedelta(hours=9))

DART_API_KEY = os.environ.get("DART_API_KEY", "")
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"

BACKFILL_BGN_DE = "20260101"

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)
PAGE_DELAY_SECONDS = 0.5

CHECKPOINT_FILE = os.path.join("data", "dart_ma_backfill_checkpoint.json")


def fetch_with_retry(params, label):
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

    print(f"[{label}] 페이지 {MAX_RETRIES}회 재시도 후 실패")
    return None


def load_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return {"collected": [], "done_pages": []}
    try:
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("collected", [])
            data.setdefault("done_pages", [])
            return data
    except json.JSONDecodeError:
        return {"collected": [], "done_pages": []}


def save_checkpoint(collected, done_pages):
    os.makedirs("data", exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"collected": collected, "done_pages": sorted(done_pages)}, f, ensure_ascii=False)


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


def fetch_all_filings(bgn_de, end_de):
    """체크포인트를 활용해 total_page만큼 페이지를 순회, 원본 filing dict 리스트를 반환.
    도중 실패하면 지금까지 모은 것을 체크포인트에 저장하고 None을 반환(다음 실행에서 이어감)."""
    ckpt = load_checkpoint()
    collected = ckpt["collected"]
    done_pages = set(ckpt["done_pages"])

    base_params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "pblntf_ty": "B",
        "page_count": 100,
    }

    first_data = fetch_with_retry({**base_params, "page_no": 1}, "백필 1페이지(전체 건수 확인)")
    if first_data is None:
        print("[백필] 1페이지 조회 실패 - 체크포인트 유지, 다음 실행에서 재시도")
        return None

    status = first_data.get("status")
    if status == "013":
        print("[백필] 조회된 데이터 없음(status=013) - 백필 대상 기간에 주요사항보고가 없습니다")
        clear_checkpoint()
        return []
    if status != "000":
        print(f"[백필] DART API 오류 (status={status}): {first_data.get('message')}")
        return None

    total_count = first_data.get("total_count", 0)
    total_page = first_data.get("total_page", 1)
    print(f"[백필] 대상 기간 {bgn_de}~{end_de}, 전체 {total_count}건, {total_page}페이지")

    if 1 not in done_pages:
        collected.extend(first_data.get("list", []))
        done_pages.add(1)
        save_checkpoint(collected, done_pages)
        print(f"[백필] 1/{total_page}페이지 완료 (누적 {len(collected)}건)")

    for page_no in range(2, total_page + 1):
        if page_no in done_pages:
            print(f"[백필] {page_no}/{total_page}페이지는 체크포인트에 이미 있음 - 건너뜀")
            continue

        time.sleep(PAGE_DELAY_SECONDS)
        page_data = fetch_with_retry({**base_params, "page_no": page_no}, f"백필 {page_no}페이지")
        if page_data is None or page_data.get("status") != "000":
            print(f"[백필] {page_no}페이지 수집 실패 - 지금까지 모은 {len(collected)}건을 체크포인트에 저장하고 중단")
            save_checkpoint(collected, done_pages)
            return None

        collected.extend(page_data.get("list", []))
        done_pages.add(page_no)
        save_checkpoint(collected, done_pages)
        print(f"[백필] {page_no}/{total_page}페이지 완료 (누적 {len(collected)}건)")

    return collected


def classify_and_group_by_date(filings_raw):
    """dart_ma_signals.classify_report()로 분류해서 {날짜: {카테고리: [...]}} 형태로 묶는다."""
    by_date = defaultdict(lambda: {cat: [] for cat in ma.MA_CATEGORIES})

    for item in filings_raw:
        rcept_dt = item.get("rcept_dt", "")
        if len(rcept_dt) != 8:
            continue
        date_key = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
        report_nm = (item.get("report_nm") or "").strip()
        rcept_no = item.get("rcept_no", "")

        for category, extra in ma.classify_report(report_nm):
            entry = {
                "corp_name": item.get("corp_name", ""),
                "report_nm": report_nm,
                "rcept_dt": rcept_dt,
                "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else "",
            }
            entry.update(extra)
            by_date[date_key][category].append(entry)

    return dict(by_date)


def merge_into_archive(by_date, bgn_date_key, end_date_key):
    raw_archive = ma._load_json(ma.MA_ARCHIVE_FILE)
    archive = {k: v for k, v in raw_archive.items() if ma._is_date_key(k)}
    # 백필 범위 안의 기존 날짜 키는 이번 백필 결과로 완전히 교체(중복 방지),
    # 범위 밖 날짜(백필 이후 실시간 크롤러가 이미 쌓은 데이터 등)는 그대로 보존
    archive = {k: v for k, v in archive.items() if not (bgn_date_key <= k <= end_date_key)}
    archive.update(by_date)

    os.makedirs("data", exist_ok=True)
    with open(ma.MA_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    return archive


def run_backfill():
    if not DART_API_KEY:
        print("DART_API_KEY 없음 - 백필 생략")
        return

    today_str = datetime.now(KST).strftime("%Y%m%d")
    bgn_date_key = f"{BACKFILL_BGN_DE[:4]}-{BACKFILL_BGN_DE[4:6]}-{BACKFILL_BGN_DE[6:8]}"
    end_date_key = f"{today_str[:4]}-{today_str[4:6]}-{today_str[6:8]}"

    filings_raw = fetch_all_filings(BACKFILL_BGN_DE, today_str)
    if filings_raw is None:
        print("[백필] 이번 실행에서 전체 페이지를 다 받지 못했습니다. 워크플로우를 다시 실행하면 체크포인트에서 이어집니다.")
        return

    by_date = classify_and_group_by_date(filings_raw)
    archive = merge_into_archive(by_date, bgn_date_key, end_date_key)
    clear_checkpoint()

    totals = {cat: 0 for cat in ma.MA_CATEGORIES}
    for day in by_date.values():
        for cat in ma.MA_CATEGORIES:
            totals[cat] += len(day[cat])
    grand_total = sum(totals.values())

    print(f"[백필 완료] {bgn_date_key} ~ {end_date_key} 기간, 원본 주요사항보고 {len(filings_raw)}건 중 "
          f"M&A 시그널 {grand_total}건 분류, {len(by_date)}개 날짜에 매핑, "
          f"아카이브 전체 날짜 수={len(archive)}")
    print(f"[백필 완료] 카테고리별 건수: {totals}")


def main():
    run_backfill()


if __name__ == "__main__":
    main()
