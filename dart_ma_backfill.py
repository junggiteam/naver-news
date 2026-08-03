"""dart_ma_signals.json을 2026-01-01부터 오늘까지 소급 백필하는 1회성 스크립트.

평소 운영 중인 scraper_dart.py + dart_ma_signals.py는 "오늘 하루치"만 계속
누적하는 구조라, 이 스크립트를 도입하기 이전 과거 날짜는 데이터가 비어있다.
이 스크립트는 DART Open API list.json을 bgn_de=20260101 ~ end_de=오늘 범위로
직접 조회해서 그 공백을 한 번에 채운다.

- report_nm 분류 로직은 dart_ma_signals.py의 classify_report()를 그대로
  재사용한다(로직 중복 금지 - 두 곳에서 분류 기준이 갈리면 위험).
- DART API는 corp_code 없이 조회할 경우 bgn_de~end_de 구간이 3개월을
  넘으면 "status=100 (검색기간은 3개월만 가능합니다)" 오류를 낸다(실제
  운영 중 확인된 제약 - 최초 설계 시에는 이 제한을 몰랐음). 그래서
  전체 기간을 달력 기준 3개월 단위 구간(generate_chunks)으로 쪼개서
  구간별로 따로 조회한다.
- 한 구간 안에서는 DART API page_count 최대 100건/페이지라 total_page만큼
  순회해야 한다. 페이지 사이 0.5초 딜레이를 둬서 API를 과도하게 두드리지
  않는다(무료 한도 일 20,000건에 비하면 이 백필 호출량은 넉넉히 여유 있음).
- 실행 중간에 끊겨도 이어서 할 수 있도록 체크포인트
  (data/dart_ma_backfill_checkpoint.json)에 "완료된 구간 목록"과 "현재
  진행 중인 구간에서 지금까지 모은 원본 리스트/완료된 페이지 번호"를
  저장한다. 재실행하면 완료된 구간은 통째로 건너뛰고, 진행 중이던
  구간은 이어받은 페이지부터 계속한다. 구간 하나가 끝날 때마다 그
  구간만큼 바로 아카이브에 병합해서 저장한다(전체가 다 끝나야만 저장하는
  방식이 아님 - 중간에 계속 끊겨도 이미 끝난 구간은 유실되지 않음).
  전체 구간이 다 끝나면 체크포인트 파일을 지운다.
- 최종 결과는 dart_ma_signals.py와 동일한 날짜별 아카이브 스키마
  ({"YYYY-MM-DD": {카테고리: [...]}})로 변환해서, 구간에 해당하는 기존
  날짜 키만 교체하고 그 밖의 날짜는 보존한다.
"""

import os
import json
import time
import random
import calendar
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

DEFAULT_CHECKPOINT = {
    "completed_chunks": [],
    "current_chunk": None,
    "collected": [],
    "done_pages": [],
}


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
        return dict(DEFAULT_CHECKPOINT)
    try:
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_CHECKPOINT.items():
            data.setdefault(k, v)
        return data
    except json.JSONDecodeError:
        return dict(DEFAULT_CHECKPOINT)


def save_checkpoint(completed_chunks, current_chunk, collected, done_pages):
    os.makedirs("data", exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "completed_chunks": completed_chunks,
            "current_chunk": current_chunk,
            "collected": collected,
            "done_pages": sorted(done_pages),
        }, f, ensure_ascii=False)


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


def _add_months(dt, n):
    month = dt.month - 1 + n
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def generate_chunks(bgn_de, end_de):
    """bgn_de~end_de(YYYYMMDD)를 DART API 제약(corp_code 없이는 3개월 이내)에
    맞춰 달력 기준 3개월 단위 구간 리스트로 쪼갠다. 각 구간은 (bgn, end) 튜플."""
    start = datetime.strptime(bgn_de, "%Y%m%d")
    end = datetime.strptime(end_de, "%Y%m%d")
    chunks = []
    cur = start
    while cur <= end:
        chunk_end = _add_months(cur, 3) - timedelta(days=1)
        if chunk_end > end:
            chunk_end = end
        chunks.append((cur.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        cur = chunk_end + timedelta(days=1)
    return chunks


def fetch_chunk_filings(bgn_de, end_de, collected, done_pages, chunk_key, completed_chunks):
    """한 구간(bgn_de~end_de)에 대해 체크포인트를 이어받아 total_page만큼 페이지를
    순회, 원본 filing dict 리스트를 반환. 도중 실패하면 체크포인트에 저장 후 None."""
    base_params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "pblntf_ty": "B",
        "page_count": 100,
    }

    first_data = fetch_with_retry({**base_params, "page_no": 1}, f"백필 {chunk_key} 1페이지")
    if first_data is None:
        print(f"[백필] {chunk_key} 1페이지 조회 실패 - 체크포인트 유지, 다음 실행에서 재시도")
        return None

    status = first_data.get("status")
    if status == "013":
        print(f"[백필] {chunk_key} 구간에는 조회된 데이터 없음(status=013)")
        return []
    if status != "000":
        print(f"[백필] {chunk_key} DART API 오류 (status={status}): {first_data.get('message')}")
        return None

    total_count = first_data.get("total_count", 0)
    total_page = first_data.get("total_page", 1)
    print(f"[백필] {chunk_key} 구간 전체 {total_count}건, {total_page}페이지")

    if 1 not in done_pages:
        collected.extend(first_data.get("list", []))
        done_pages.add(1)
        save_checkpoint(completed_chunks, chunk_key, collected, sorted(done_pages))
        print(f"[백필] {chunk_key} 1/{total_page}페이지 완료 (누적 {len(collected)}건)")

    for page_no in range(2, total_page + 1):
        if page_no in done_pages:
            print(f"[백필] {chunk_key} {page_no}/{total_page}페이지는 체크포인트에 이미 있음 - 건너뜀")
            continue

        time.sleep(PAGE_DELAY_SECONDS)
        page_data = fetch_with_retry({**base_params, "page_no": page_no}, f"백필 {chunk_key} {page_no}페이지")
        if page_data is None or page_data.get("status") != "000":
            print(f"[백필] {chunk_key} {page_no}페이지 수집 실패 - 지금까지 모은 {len(collected)}건을 체크포인트에 저장하고 중단")
            save_checkpoint(completed_chunks, chunk_key, collected, sorted(done_pages))
            return None

        collected.extend(page_data.get("list", []))
        done_pages.add(page_no)
        save_checkpoint(completed_chunks, chunk_key, collected, sorted(done_pages))
        print(f"[백필] {chunk_key} {page_no}/{total_page}페이지 완료 (누적 {len(collected)}건)")

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
    # 이 구간 안의 기존 날짜 키는 이번 백필 결과로 완전히 교체(중복 방지),
    # 구간 밖 날짜(다른 구간, 백필 이후 실시간 크롤러가 이미 쌓은 데이터 등)는 보존
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
    chunks = generate_chunks(BACKFILL_BGN_DE, today_str)
    print(f"[백필] 총 {len(chunks)}개 구간(3개월 단위)으로 분할: {chunks}")

    ckpt = load_checkpoint()
    completed_chunks = list(ckpt["completed_chunks"])

    grand_totals = {cat: 0 for cat in ma.MA_CATEGORIES}
    grand_filings = 0

    for bgn_de, end_de in chunks:
        chunk_key = f"{bgn_de}-{end_de}"
        if chunk_key in completed_chunks:
            print(f"[백필] {chunk_key} 구간은 이미 완료됨 - 건너뜀")
            continue

        if ckpt.get("current_chunk") == chunk_key:
            collected = list(ckpt["collected"])
            done_pages = set(ckpt["done_pages"])
        else:
            collected, done_pages = [], set()

        filings_raw = fetch_chunk_filings(bgn_de, end_de, collected, done_pages, chunk_key, completed_chunks)
        if filings_raw is None:
            print(f"[백필] {chunk_key} 구간을 이번 실행에서 다 못 받았습니다. 워크플로우를 다시 실행하면 이어집니다.")
            return

        bgn_date_key = f"{bgn_de[:4]}-{bgn_de[4:6]}-{bgn_de[6:8]}"
        end_date_key = f"{end_de[:4]}-{end_de[4:6]}-{end_de[6:8]}"
        by_date = classify_and_group_by_date(filings_raw)
        merge_into_archive(by_date, bgn_date_key, end_date_key)

        totals = {cat: 0 for cat in ma.MA_CATEGORIES}
        for day in by_date.values():
            for cat in ma.MA_CATEGORIES:
                totals[cat] += len(day[cat])
                grand_totals[cat] += len(day[cat])
        grand_filings += len(filings_raw)

        completed_chunks.append(chunk_key)
        save_checkpoint(completed_chunks, None, [], [])
        print(f"[백필] {chunk_key} 구간 완료 및 아카이브 병합: 원본 {len(filings_raw)}건 중 M&A {sum(totals.values())}건 {totals} "
              f"({len(completed_chunks)}/{len(chunks)}개 구간 완료)")

        ckpt = load_checkpoint()

    clear_checkpoint()
    print(f"[백필 전체 완료] {BACKFILL_BGN_DE} ~ {today_str}, 원본 주요사항보고 총 {grand_filings}건 중 "
          f"M&A 시그널 총 {sum(grand_totals.values())}건 분류: {grand_totals}")


def main():
    run_backfill()


if __name__ == "__main__":
    main()
