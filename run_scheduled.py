import os
import json
from datetime import datetime, timezone, timedelta

import scraper_ranking
import scraper_economy_section
import scraper_stock
import scraper_realestate

KST = timezone(timedelta(hours=9))
WINDOW_MINUTES = 5
MARKER_FILE = os.path.join("data", ".last_run.json")

# 기존 4개 워크플로우에 개별로 있던 cron 스케줄과 동일한 목표 시각(KST).
# GitHub Actions의 schedule 트리거는 public 저장소에서 best-effort라 실행이
# 누락되는 경우가 있어, 10분마다 도는 마스터 스케줄러가 이 목표 시각들을
# 직접 확인해서 실행 여부를 판단한다.
CRAWLER_TARGETS = {
    "ranking": ["00:03", "07:03", "12:03", "15:03", "18:03", "21:03"],
    "economy": ["00:06", "07:06", "12:06", "15:06", "18:06", "21:06"],
    "stock": ["00:09", "07:09", "12:09", "15:09", "18:09", "21:09"],
    "realestate": ["00:12", "07:12", "12:12", "15:12", "18:12", "21:12"],
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


def closest_target_dt(now_kst, hhmm):
    """오늘/어제/내일 중 now_kst와 가장 가까운 hhmm(KST) 시각을 반환 (자정 경계 처리용)."""
    hour, minute = map(int, hhmm.split(":"))
    candidates = [
        now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=offset)
        for offset in (-1, 0, 1)
    ]
    return min(candidates, key=lambda c: abs((now_kst - c).total_seconds()))


def load_marker():
    if not os.path.exists(MARKER_FILE):
        return {}
    with open(MARKER_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_marker(marker):
    os.makedirs("data", exist_ok=True)
    with open(MARKER_FILE, "w", encoding="utf-8") as f:
        json.dump(marker, f, ensure_ascii=False, indent=2)


def find_due_crawlers(now_kst):
    """now_kst 기준 ±WINDOW_MINUTES 이내인 크롤러와 그 목표 시각을 반환."""
    due = {}
    for name, hhmm_list in CRAWLER_TARGETS.items():
        closest = min(
            (closest_target_dt(now_kst, hhmm) for hhmm in hhmm_list),
            key=lambda t: abs((now_kst - t).total_seconds()),
        )
        diff_seconds = abs((now_kst - closest).total_seconds())
        if diff_seconds <= WINDOW_MINUTES * 60:
            due[name] = closest
    return due


def run_scheduled(now_kst=None):
    if now_kst is None:
        now_kst = get_now_kst()

    due = find_due_crawlers(now_kst)
    if not due:
        print(f"[{now_kst.isoformat()}] 지금은 실행 대상 없음")
        return

    marker = load_marker()
    marker_changed = False

    for name, target_dt in due.items():
        target_key = target_dt.isoformat()

        if marker.get(name) == target_key:
            print(f"[{name}] {target_key} 윈도우는 이미 실행됨 - 건너뜀")
            continue

        print(f"[{name}] 목표 시각 {target_key} 윈도우 진입 - 실행")
        try:
            CRAWLER_FUNCS[name]()
            marker[name] = target_key
            marker_changed = True
            print(f"[{name}] 실행 완료")
        except Exception as e:
            print(f"[{name}] 실행 중 오류 발생, 다음 주기에 재시도: {e}")

    if marker_changed:
        save_marker(marker)


if __name__ == "__main__":
    run_scheduled()
