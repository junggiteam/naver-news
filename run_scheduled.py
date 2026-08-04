import os
import json
from datetime import datetime, timezone, timedelta

import scraper_ranking
import scraper_economy_section
import scraper_stock
import scraper_realestate
import scraper_market_movers
import scraper_dart
import scraper_ecos
import scraper_bizinfo
import scraper_calendar
import scraper_tax_calendar
import ai_briefing
import dashboard
import daily_reports
import record_verification
import dart_ma_signals
import dart_report_detail

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
    # DART 공시는 widgets/ma-ticker.html("당일 브리핑" 성격의 티커 위젯)이
    # 참고하므로 체감 신선도를 위해 1시간 주기로 단축(2026-08 변경, 기존
    # 3시간). 무료 API 한도(일 20,000건) 대비 하루 호출량이 24회 x
    # (보통 1페이지) 수준이라 여유가 충분하고, GitHub Actions는 이 저장소가
    # public repo라 표준 러너 무제한이라 실행 빈도 증가도 문제 없음.
    # ECOS 거시지표는 하루 내내 빈번히 바뀌는 데이터가 아니라 여전히
    # 3시간 주기로 충분함.
    "dart": timedelta(hours=1),
    "ecos": timedelta(hours=3),
    "bizinfo": timedelta(hours=3),
    # 경제 캘린더(FOMC/금통위)는 몇 달 전에 이미 확정된 일정이라 자주
    # 확인할 필요가 없음. 매일 한 번이면 충분.
    "calendar": timedelta(hours=24),
    # 세무·노무·공휴일 캘린더도 하루 단위로 바뀌는 성격이 아니라 24시간 주기.
    "tax_calendar": timedelta(hours=24),
}

CRAWLER_FUNCS = {
    "ranking": scraper_ranking.main,
    "economy": scraper_economy_section.main,
    "stock": scraper_stock.main,
    "realestate": scraper_realestate.main,
    "dart": scraper_dart.main,
    "ecos": scraper_ecos.main,
    "bizinfo": scraper_bizinfo.main,
    "calendar": scraper_calendar.main,
    "tax_calendar": scraper_tax_calendar.main,
}


TAB_BRIEFING_TARGETS = {
    # 크롤러 이름: (데이터 파일 경로, 브리핑 프롬프트에 쓸 한글 라벨)
    "ranking": ("data/ranking_news.json", "종합"),
    "economy": ("data/economy_news.json", "경제"),
    "realestate": ("data/realestate_news.json", "부동산"),
}


def _load_json_safe(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def _tab_briefing_with_check(titles, label, verified_facts):
    """금지 표현(record_verification.BANNED_SUPERLATIVE_WORDS) 포함 시
    1회 자동 재생성, 그래도 걸리면 이번 회차는 생략(빈 리스트). verified_facts가
    있으면(코드로 실제 검증된 근거가 있으면) 스캔 자체를 생략한다."""
    lines = ai_briefing.generate_tab_briefing(titles, label, verified_facts=verified_facts)
    if verified_facts:
        return lines
    joined = " ".join(lines)
    if record_verification.contains_banned_expression(joined):
        print(f"[{label}] 브리핑 금지 표현 감지 - 1회 재생성 시도")
        lines = ai_briefing.generate_tab_briefing(titles, label)
        joined = " ".join(lines)
        if record_verification.contains_banned_expression(joined):
            print(f"[{label}] 브리핑 재생성 후에도 금지 표현 감지 - 이번 회차는 생략")
            return []
    return lines


def _stock_commentary_with_check(indices, titles, verified_facts):
    """generate_stock_commentary 버전의 금지 표현 검증/재생성/생략.
    _tab_briefing_with_check와 동일한 정책."""
    commentary = ai_briefing.generate_stock_commentary(indices, titles, verified_facts=verified_facts)
    if verified_facts:
        return commentary
    if commentary and record_verification.contains_banned_expression(commentary):
        print("[stock] 시황 코멘트 금지 표현 감지 - 1회 재생성 시도")
        commentary = ai_briefing.generate_stock_commentary(indices, titles)
        if commentary and record_verification.contains_banned_expression(commentary):
            print("[stock] 시황 코멘트 재생성 후에도 금지 표현 감지 - 이번 회차는 생략")
            return None
    return commentary


def _dart_ma_article_with_check(filings, details):
    """generate_dart_ma_article() 버전의 금지 표현 검증/재생성/생략.
    _tab_briefing_with_check와 동일한 정책이지만 반환 타입이 문자열이라
    별도로 만든다(리스트 대상 함수를 그대로 재사용할 수 없음)."""
    article = ai_briefing.generate_dart_ma_article(filings, details)
    if article and record_verification.contains_banned_expression(article):
        print("[dart_ma_article] 금지 표현 감지 - 1회 재생성 시도")
        article = ai_briefing.generate_dart_ma_article(filings, details)
        if article and record_verification.contains_banned_expression(article):
            print("[dart_ma_article] 재생성 후에도 금지 표현 감지 - 이번 회차는 생략")
            return None
    return article


# DART 브리핑 재생성 체크 시간대/주기. REPORT_SLOTS의 "하루 1번, 날짜
# 단위 중복 방지" 방식과 달리, 이 슬롯은 낮 시간대 안에서 매시간 반복
# 체크한다 - 오후 늦게 올라오는 공시도 그날 안에 반영하기 위함.
DART_MA_ARTICLE_WINDOW_START = "12:00"
DART_MA_ARTICLE_WINDOW_END = "17:10"
DART_MA_ARTICLE_INTERVAL = timedelta(hours=1)


def _dart_ma_article_due(now_kst, marker):
    """평일만, 12:00~17:10 시간대 안에서만, 마지막 "체크"(실제 재생성
    여부와 무관 - 스킵된 체크도 포함) 이후 DART_MA_ARTICLE_INTERVAL 이상
    지났을 때만 True. marker["dart_ma_article_last_run"]에는 날짜만이
    아니라 시:분까지 포함한 전체 ISO 타임스탬프를 저장해 "1시간 경과"를
    정확히 비교한다 - REPORT_SLOTS의 날짜 단위(오늘 이미 실행했는지)
    중복 방지와는 다른 방식이라 별도 로직으로 둔다."""
    if now_kst.weekday() >= 5:
        return False

    start_hour, start_minute = map(int, DART_MA_ARTICLE_WINDOW_START.split(":"))
    end_hour, end_minute = map(int, DART_MA_ARTICLE_WINDOW_END.split(":"))
    start = now_kst.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = now_kst.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if not (start <= now_kst <= end):
        return False

    last_run_str = marker.get("dart_ma_article_last_run")
    if not last_run_str:
        return True
    last_run = datetime.fromisoformat(last_run_str)
    return (now_kst - last_run) >= DART_MA_ARTICLE_INTERVAL


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
            stock_indices = _load_json_safe("data/stock_news.json").get("indices", [])
            verified_facts = record_verification.build_verified_facts_for_indices(stock_indices)
            data["ai_briefing"] = _tab_briefing_with_check(titles, label, verified_facts)
            if name == "economy":
                data["daily_term"] = ai_briefing.generate_daily_economic_term(titles)
                print(f"[economy] 오늘의 경제 용어 {'생성됨: ' + data['daily_term']['term'] if data['daily_term'] else '생략됨(키 없음/호출 실패)'}")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[{name}] AI 브리핑 {'생성됨' if data['ai_briefing'] else '생략됨(키 없음/호출 실패/금지 표현 재생성 실패)'}")

        elif name == "stock":
            path = "data/stock_news.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            titles = [
                item["title"]
                for cat in data.get("news_categories", [])
                for item in cat.get("items", [])
            ]
            verified_facts = record_verification.build_verified_facts_for_indices(data.get("indices", []))
            data["ai_commentary"] = _stock_commentary_with_check(
                data.get("indices", []), titles, verified_facts
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[stock] AI 시황 코멘트 {'생성됨' if data['ai_commentary'] else '생략됨(변동폭 작음/키 없음/호출 실패/금지 표현 재생성 실패)'}")

        elif name == "dart":
            path = "data/dart_filings.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["filings"] = ai_briefing.generate_dart_summary(data.get("filings", []))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            has_explanation = any(f.get("ai_explanation") for f in data["filings"])
            print(f"[dart] 공시 설명 {'생성됨' if has_explanation else '생략됨(공시 없음/키 없음/호출 실패)'}")
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


def _augment_dart_ma_signals():
    """DART 크롤러 성공 직후 dart_filings.json을 M&A 5개 카테고리로 재분류.
    DART API를 추가로 호출하지 않고 이미 저장된 데이터만 재가공하므로
    실패해도 dart_filings.json 저장 자체와는 무관하게 예외를 삼킨다.
    결과(dart_ma_signals.json)는 dashboard.json에 합치지 않고 완전히
    독립된 파일로 유지한다 - 다른 탭 로딩 속도에 영향 없게 하기 위함."""
    try:
        dart_ma_signals.build_ma_signals()
    except Exception as e:
        print(f"[dart_ma] M&A 시그널 분류 중 오류(dart_filings.json 저장 자체엔 영향 없음): {e}")


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


def _record_daily_close_snapshot():
    """장 마감 근처(daily_close_snapshot 슬롯)에 오늘 종가를
    daily_close_archive.json에 무기한 누적 기록 - 최상급 표현("역대",
    "최고" 등) 검증용 장기 데이터. stock_index_history.json(30시간
    롤링 스냅샷)과는 별개 파일이라 서로 영향 없음."""
    with open("data/stock_news.json", encoding="utf-8") as f:
        data = json.load(f)
    record_verification.record_daily_close(data.get("indices", []))


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


def _build_dart_ma_article(marker):
    """평일 12:00~17:10 사이 매시간 체크 시(_dart_ma_article_due() 통과
    시)마다 호출돼, 오늘 M&A 시그널(dart_ma_signals.json - 정책·캘린더
    M&A 탭이 쓰는 것과 동일한 소스)을 취합해 기사 형식으로 정리한다.
    dart_filings.json 전체(오늘의 모든 주요사항보고, M&A 아닌 것도 포함)를
    쓰던 예전 방식은 이미 M&A 기준으로 도는 dart_report_detail.py의
    상세정보 조회와 기준이 어긋나서(상세정보는 M&A만 채워지는데 기사에
    나열되는 회사 목록은 훨씬 넓은 전체 기준) 정책·캘린더 M&A 탭과
    회사/건수가 안 맞는 문제가 있었다(2026-08 발견) - dart_ma_signals.json
    하나로 통일해 이 갭을 닫는다. 오늘 M&A 시그널이 하나도 없으면 생략 -
    쓸 자료가 없다.

    marker 딕셔너리를 직접 받아 그 자리에서 갱신한다("dart_ma_article_
    filing_ids" 키) - 별도로 load_marker()/save_marker()를 호출하지
    않는다. run_scheduled()가 마커 파일 입출력을 단일하게 책임지는 기존
    패턴을 따르는 것으로, 여기서 파일을 따로 읽고 쓰면 run_scheduled()가
    마지막에 자기 사본을 저장하는 시점에 이 함수가 미리 반영해둔 변경이
    덮어써질 위험이 있다."""
    # dart_filings.json 자체는 "dart" 크롤러 주기(1시간)로만 갱신되지만,
    # dart_ma_signals.json은 그 결과를 재분류만 하는 가벼운 로컬 연산이라
    # 여기서 한 번 더 최신화해서 쓴다(추가 네트워크 호출 없음).
    dart_ma_signals.build_ma_signals()

    today_str = get_now_kst().strftime("%Y-%m-%d")
    ma_archive = _load_json_safe("data/dart_ma_signals.json")
    today_signals = ma_archive.get(today_str) or {}
    # dart_ma_signals.json의 entry 자체엔 "category"가 없다 - 어느
    # 카테고리 리스트에 들어있는지로만 구분되므로, 여기서 평탄화하면서
    # 명시적으로 붙여준다(ai_briefing.generate_dart_ma_article()이 회사별
    # 소제목을 더 정확히 묶는 데 참고). 원본 dict를 직접 건드리지 않도록
    # 얕은 복사 후 추가.
    filings = []
    for category in dart_ma_signals.MA_CATEGORIES:
        for item in today_signals.get(category) or []:
            item_with_category = dict(item)
            item_with_category["category"] = category
            filings.append(item_with_category)

    if not filings:
        print("[dart_ma_article] 오늘 M&A 시그널 없음 - 기사 생성 생략")
        return

    # 마지막 생성 이후 새로 올라온 M&A 공시가 없으면(rcept_no 목록이
    # 그대로면) AI 호출 없이 스킵 - M&A 아닌 새 공시가 올라와도 여기엔
    # 안 잡히므로 불필요한 재생성이 없고, M&A 관련 공시가 새로 올라오면
    # 정확히 감지된다.
    current_filing_ids = sorted(f.get("rcept_no", "") for f in filings)
    if current_filing_ids == marker.get("dart_ma_article_filing_ids"):
        print("[dart_ma_article] 새 M&A 공시 없음 - 재생성 스킵")
        return

    details = dart_report_detail.build_details()

    article = _dart_ma_article_with_check(filings, details)
    if not article:
        print("[dart_ma_article] 기사 생성 생략(키 없음/호출 실패/금지 표현 재생성 실패)")
        return

    now_kst = get_now_kst()
    output = {
        "date": now_kst.strftime("%Y-%m-%d"),
        "generated_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
        "article": article,
        "source_filing_count": len(filings),
    }
    os.makedirs("data", exist_ok=True)
    with open("data/dart_ma_daily_article.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[dart_ma_article] 기사 생성 완료({len(filings)}건 반영) -> data/dart_ma_daily_article.json")

    marker["dart_ma_article_filing_ids"] = current_filing_ids


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


# 데일리 브리핑(오전판/저녁판)은 CRAWLER_INTERVALS의 "마지막 실행 후 N시간
# 경과" 방식과 다르게, "하루 중 특정 시각 근처인지"로 판단해야 한다.
# cron-job.org가 15분마다 깨워주므로 목표 시각 ±윈도우 안에 항상 최소 한 번은
# 걸리고, 마커에 "오늘 이미 실행했는지"를 날짜 단위로 기록해 중복 실행을 막는다.
# CRAWLER_INTERVALS/CRAWLER_FUNCS 체계와는 완전히 별도 로직이라 기존
# 크롤러 스케줄에는 영향이 없다.
REPORT_SLOTS = {
    # target은 정시(12:00/18:00)보다 3분 앞당긴 11:57/17:57 - 다른 크롤러/
    # 리포트 슬롯과 정시에 몰려 겹치거나 지연되는 걸 피하려는 의도적인
    # 오프셋이다. 위젯(news-widget.html)에 보이는 "오전판 12:00·저녁판
    # 18:00 업데이트" 문구는 사람이 보기 좋은 반올림 값이고, 실제 실행
    # 시각은 여기 11:57/17:57이라는 점에 유의 - 표시값과 실제 실행값이
    # 다른 게 정상이며 버그가 아니다.
    "daily_report_morning": {
        "target": "11:57", "window_minutes": 15, "func": daily_reports.build_morning_reports,
    },
    "daily_report_evening": {
        "target": "17:57", "window_minutes": 15, "func": daily_reports.build_evening_reports,
    },
    # 장 마감(15:30) 근처 종가를 daily_close_archive.json에 기록. window는
    # 다른 슬롯과 동일하게 ±15분 - cron-job.org가 15분 간격으로만 깨우므로
    # 그보다 좁은 윈도우(예: 5분)를 쓰면 실행 시각과 어긋나 아예 못 걸릴 수 있음.
    "daily_close_snapshot": {
        "target": "15:37", "window_minutes": 15, "func": _record_daily_close_snapshot,
    },
}
# DART 주요사항보고서 취합 기사는 위 REPORT_SLOTS(하루 1번, 날짜 단위
# 중복 방지)와 다른 별도 체계를 쓴다 - 평일 12:00~17:10 사이 매시간
# 반복 체크(_dart_ma_article_due/_build_dart_ma_article, run_scheduled()
# 안에서 REPORT_SLOTS 루프와 별개로 처리). 오후 늦게 올라오는 공시도
# 그날 안에 반영하기 위함.


def _is_in_time_window(now_kst, target_hhmm, window_minutes):
    hour, minute = map(int, target_hhmm.split(":"))
    target_dt = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return abs((now_kst - target_dt).total_seconds()) <= window_minutes * 60


def find_due_report_slots(now_kst, marker):
    """목표 시각(±윈도우) 안에 들어왔고 오늘 아직 실행하지 않은 리포트
    슬롯 이름 목록을 반환. weekdays_only=True인 슬롯은 주말(토=5,일=6)에
    건너뛴다 - 이 키가 없는 기존 슬롯들은 cfg.get(...)이 기본 False라
    영향 없음."""
    today_str = now_kst.strftime("%Y-%m-%d")
    due_slots = []
    for slot_name, cfg in REPORT_SLOTS.items():
        if cfg.get("weekdays_only") and now_kst.weekday() >= 5:
            continue
        last_run_str = marker.get(slot_name)
        last_run_date = last_run_str.split("T")[0] if last_run_str else None
        if last_run_date == today_str:
            continue
        if _is_in_time_window(now_kst, cfg["target"], cfg["window_minutes"]):
            due_slots.append(slot_name)
    return due_slots


def run_scheduled(now_kst=None):
    if now_kst is None:
        now_kst = get_now_kst()

    marker = load_marker()
    due = find_due_crawlers(now_kst, marker)
    due_slots = find_due_report_slots(now_kst, marker)
    dart_ma_article_due = _dart_ma_article_due(now_kst, marker)

    if not due and not due_slots and not dart_ma_article_due:
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
            if name == "dart":
                _augment_dart_ma_signals()
            marker[name] = now_kst.isoformat()
            marker_changed = True
            print(f"[{name}] 실행 완료")
        except Exception as e:
            print(f"[{name}] 실행 중 오류 발생, 마커 갱신 안 함 - 다음 주기에 재시도: {e}")

    for slot_name in due_slots:
        cfg = REPORT_SLOTS[slot_name]
        print(f"[{slot_name}] 목표 시각({cfg['target']}) 윈도우 진입 - 실행")
        try:
            cfg["func"]()
            marker[slot_name] = now_kst.isoformat()
            marker_changed = True
            print(f"[{slot_name}] 실행 완료")
        except Exception as e:
            print(f"[{slot_name}] 실행 중 오류 발생, 마커 갱신 안 함 - 다음 주기에 재시도: {e}")

    if dart_ma_article_due:
        print("[dart_ma_article] 체크 시각 도달(평일 12:00~17:10, 마지막 체크로부터 1시간 경과) - 실행")
        try:
            _build_dart_ma_article(marker)
            # 스킵되든(새 공시 없음) 실제 재생성되든 상관없이 "체크"
            # 자체는 완료된 것으로 보고 last_run을 갱신한다 - 그래야
            # 다음 체크가 1시간 뒤로 정상적으로 넘어가고, 10분마다 계속
            # 재시도하는 낭비가 없다. filing_ids는 _build_dart_ma_article()
            # 안에서 실제 재생성 성공 시에만 별도로 갱신됨(체크 주기
            # 유지 vs 변경 감지, 서로 다른 목적이라 키를 분리).
            marker["dart_ma_article_last_run"] = now_kst.isoformat()
            marker_changed = True
            print("[dart_ma_article] 체크 완료")
        except Exception as e:
            print(f"[dart_ma_article] 실행 중 오류 발생, 마커(dart_ma_article_last_run) 갱신 안 함 - 다음 체크 때 재시도: {e}")

    if marker_changed:
        try:
            dashboard.build_dashboard()
            print("[dashboard] 대시보드 데이터 갱신됨")
        except Exception as e:
            print(f"[dashboard] 대시보드 생성 실패(각 탭 데이터 자체엔 영향 없음): {e}")
        save_marker(marker)


if __name__ == "__main__":
    run_scheduled()
