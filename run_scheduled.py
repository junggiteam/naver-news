import os
import json
from datetime import datetime, timezone, timedelta

import scraper_ranking
import scraper_economy_section
import scraper_stock
import scraper_realestate
import scraper_market_movers
import ai_briefing
import dashboard

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
    # 지수(코스피/환율 등)는 체감 실시간성을 위해 훨씬 짧은 주기로 분리.
    # 증권 뉴스도 같은 크롤러가 같이 수집하지만, 더 자주 갱신되는 건
    # 단점이 아니라 오히려 이득이라 굳이 분리하지 않음.
    "stock": timedelta(minutes=15),
    "realestate": timedelta(hours=3),
}

CRAWLER_FUNCS = {
    "ranking": scraper_ranking.main,
    "economy": scraper_economy_section.main,
    "stock": scraper_stock.main,
    "realestate": scraper_realestate.main,
}


TAB_BRIEFING_TARGETS = {
    # 크롤러 이름: (데이터 파일 경로, 브리핑 프롬프트에 쓸 한글 라벨)
    "ranking": ("data/ranking_news.json", "종합"),
    "economy": ("data/economy_news.json", "경제"),
    "realestate": ("data/realestate_news.json", "부동산"),
}


def _augment_with_ai(name):
    """크롤링 직후 해당 카테고리 데이터 파일에 AI 브리핑/코멘트를 추가.
    AI 호출이 실패해도 예외를 밖으로 던지지 않는다 - 크롤링 성공 자체는
    이 단계와 무관하게 보장되어야 하기 때문."""
    try:
        if name in TAB_BRIEFING_TARGETS:
            path, label = TAB_BRIEFING_TARGETS[name]
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            titles = [item["title"] for item in data.get("news", [])]
            data["ai_briefing"] = ai_briefing.generate_tab_briefing(titles, label)
            if name == "economy":
                data["daily_term"] = ai_briefing.generate_daily_economic_term(titles)
                print(f"[economy] 오늘의 경제 용어 {'생성됨: ' + data['daily_term']['term'] if data['daily_term'] else '생략됨(키 없음/호출 실패)'}")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[{name}] AI 브리핑 {'생성됨' if data['ai_briefing'] else '생략됨(키 없음/호출 실패)'}")

        elif name == "stock":
            path = "data/stock_news.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            titles = [
                item["title"]
                for cat in data.get("news_categories", [])
                for item in cat.get("items", [])
            ]
            data["ai_commentary"] = ai_briefing.generate_stock_commentary(
                data.get("indices", []), titles
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[stock] AI 시황 코멘트 {'생성됨' if data['ai_commentary'] else '생략됨(변동폭 작음/키 없음/호출 실패)'}")
    except Exception as e:
        print(f"[{name}] AI 후처리 중 오류(크롤링 결과 자체는 정상 저장됨): {e}")


KEYWORD_TAGS_FILE = os.path.join("data", "keyword_tags.json")
KEYWORD_TAGS_PER_CATEGORY = 15  # 카테고리 하나가(특히 종합 400여개) 편중되지 않도록 상한


def _augment_keyword_tags():
    """종합/경제/부동산/증권 4개 탭의 현재 데이터에서 제목을 골고루 모아
    핵심 키워드 5~8개를 추출해 data/keyword_tags.json에 저장.
    economy 크롤러 주기(3시간)에 맞춰 갱신 - 크롤링 본체와 무관하므로
    실패해도 예외를 밖으로 던지지 않는다."""
    try:
        titles = []
        for path in ("data/ranking_news.json", "data/economy_news.json", "data/realestate_news.json"):
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            titles.extend(item["title"] for item in (data.get("news") or [])[:KEYWORD_TAGS_PER_CATEGORY])

        if os.path.exists("data/stock_news.json"):
            with open("data/stock_news.json", encoding="utf-8") as f:
                stock_data = json.load(f)
            stock_titles = [
                item["title"]
                for cat in (stock_data.get("news_categories") or [])
                for item in cat.get("items", [])
            ]
            titles.extend(stock_titles[:KEYWORD_TAGS_PER_CATEGORY])

        tags = ai_briefing.generate_keyword_tags(titles)
        with open(KEYWORD_TAGS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "tags": tags},
                f, ensure_ascii=False, indent=2
            )
        print(f"[keyword_tags] {'생성됨: ' + ', '.join(tags) if tags else '생략됨(키 없음/호출 실패)'}")
    except Exception as e:
        print(f"[keyword_tags] 생성 중 오류(크롤링 결과 자체는 정상 저장됨): {e}")


STOCK_HISTORY_FILE = os.path.join("data", "stock_index_history.json")
STOCK_HISTORY_MAX_POINTS = 120  # 15분 간격 기준 대략 30시간치, 여유있게 보관


def _record_stock_history():
    """지수 스냅샷을 이력 파일에 누적 기록 (나중에 위젯에서 미니 추이 그래프용).
    실패해도 크롤링/저장 본체와는 무관하므로 예외를 삼킨다."""
    try:
        with open("data/stock_news.json", encoding="utf-8") as f:
            data = json.load(f)
        indices = data.get("indices", [])
        if not indices:
            return

        values = {}
        for idx in indices:
            try:
                values[idx["name"]] = float(str(idx["value"]).replace(",", ""))
            except (ValueError, TypeError):
                continue
        if not values:
            return

        snapshot = {"time": data.get("updated_at"), "values": values}

        if os.path.exists(STOCK_HISTORY_FILE):
            with open(STOCK_HISTORY_FILE, encoding="utf-8") as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = []
        else:
            history = []

        history.append(snapshot)
        history = history[-STOCK_HISTORY_MAX_POINTS:]

        with open(STOCK_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"[stock] 지수 이력 기록됨 (누적 {len(history)}개)")
    except Exception as e:
        print(f"[stock] 지수 이력 기록 실패(스파크라인용, 본체 크롤링엔 영향 없음): {e}")


def _augment_with_market_movers():
    """급등락 TOP5, 업종별 등락, IPO 일정을 stock_news.json에 덧붙임.
    실패해도 예외를 밖으로 던지지 않음 - 크롤링 본체와 무관해야 함."""
    try:
        result, debug_notes = scraper_market_movers.crawl_market_movers()
        with open("data/stock_news.json", encoding="utf-8") as f:
            data = json.load(f)
        data.update(result)
        if debug_notes:
            data["_movers_debug"] = debug_notes  # 원인 확인용, 검증되면 제거 예정
        with open("data/stock_news.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        counts = {k: len(v) for k, v in result.items()}
        print(f"[market_movers] 저장 완료: {counts}")
    except Exception as e:
        print(f"[market_movers] 후처리 중 오류(본체 크롤링엔 영향 없음): {e}")


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
    try:
        with open(MARKER_FILE, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # 마커 파일이 손상돼도(예: 동시 push 충돌 잔재) 전체 실행이 죽지 않고
        # "기록 없음"으로 간주해 모든 크롤러를 다시 실행하도록 한다.
        print(f"[load_marker] 마커 파일 손상, 초기화하고 계속 진행: {e}")
        return {}


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
            _augment_with_ai(name)
            if name == "stock":
                _record_stock_history()
                _augment_with_market_movers()
            if name == "economy":
                _augment_keyword_tags()
            marker[name] = now_kst.isoformat()
            marker_changed = True
            print(f"[{name}] 실행 완료")
        except Exception as e:
            print(f"[{name}] 실행 중 오류 발생, 마커 갱신 안 함 - 다음 주기에 재시도: {e}")

    if marker_changed:
        try:
            dashboard.build_dashboard()
            print("[dashboard] 대시보드 데이터 갱신됨")
        except Exception as e:
            print(f"[dashboard] 대시보드 생성 실패(각 탭 데이터 자체엔 영향 없음): {e}")
        save_marker(marker)


if __name__ == "__main__":
    run_scheduled()
