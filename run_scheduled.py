import os
import json
from datetime import datetime, timezone, timedelta

import scraper_ranking
import scraper_economy_section
import scraper_stock
import scraper_realestate

KST = timezone(timedelta(hours=9))
MARKER_FILE = os.path.join("data", ".last_run.json")

# 각 크롤러의 최소 재실행 간격.
# GitHub Actions의 schedule 트리거는 선언한 주기(10분)를 지키지 않고
# 실제로는 몇 시간 단위로 불규칙하게 발동된다(공식 문서 기준 "지연"보다 훨씬 심함,
# 2026-07-24~25 실측: 17시간 동안 3번, 4~5시간 간격으로만 발동됨).
# 그래서 "정해진 시각에 맞춰 도는지"가 아니라 "마지막 실행 이후 이만큼
# 지났는지"로 판단해야, 스케줄러가 언제 깨든 밀린 크롤러를 즉시 따라잡는다.
CRAWLER_INTERVALS = {
    "ranking": timedelta(hours=3),
    "economy": timedelta(hours=3),
    "stock": timedelta(hours=3),
    "realestate": timedelta(hours=3),
}

CRAWLER_FUNCS = {
    "ranking": scraper_ranking.main,
    "economy": scraper_economy_section.main,
    "stock": scraper_stock.main,
    "realestate": scraper_realestate.main,
}


def get_now_kst():
    """실제 현재 시각(KST)을 반환. 테스트에서는 SCHEDULED_NOW_OVERRIDE 환경변수
    (ISO 8601, 예: 2026-07-24T07:03:00+09:00)로 임의 시각을 흉내낼 수 있다."""
    override = os.environ.get("SCHEDULED_NOW_OVERRIDE")
    if override:
        return datetime.fromisoformat(override)
    return datetime.now(KST)


def load_marker():
    if not os.path.exists(MARKER_FILE):
        return {}
    with open(MARKER_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_marker(marker):
    os.makedirs("data", exist_ok=True)
    with open(MARKER_FILE, "w", encoding="utf-8") as f:
        json.dump(marker, f, ensure_ascii=False, indent=2)


def find_due_crawlers(now_kst, marker):
    """마지막 실행 이후 CRAWLER_INTERVALS 이상 지난 크롤러 이름 목록을 반환.
    실행 기록이 없으면(최초 실행/마커 유실) 즉시 실행 대상으로 본다."""
    due = []
    for name, interval in CRAWLER_INTERVALS.items():
        last_run_str = marker.get(name)
        if last_run_str is None:
            due.append(name)
            continue
        last_run = datetime.fromisoformat(last_run_str)
        if now_kst - last_run >= interval:
            due.append(name)
    return due


def run_scheduled(now_kst=None):
    if now_kst is None:
        now_kst = get_now_kst()

    marker = load_marker()
    due = find_due_crawlers(now_kst, marker)
    if not due:
        print(f"[{now_kst.isoformat()}] 지금은 실행 대상 없음")
        return

    marker_changed = False

    for name in due:
        last_run_str = marker.get(name, "기록 없음(최초 실행)")
        print(f"[{name}] 마지막 실행: {last_run_str} - 실행 (간격 {CRAWLER_INTERVALS[name]} 경과)")
        try:
            CRAWLER_FUNCS[name]()
            marker[name] = now_kst.isoformat()
            marker_changed = True
            print(f"[{name}] 실행 완료")
        except Exception as e:
            print(f"[{name}] 실행 중 오류 발생, 마커 갱신 안 함 - 다음 주기에 재시도: {e}")

    if marker_changed:
        save_marker(marker)


if __name__ == "__main__":
    run_scheduled()
