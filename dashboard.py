"""'오늘 한눈에' 대시보드용 데이터를 만드는 모듈.

새로 크롤링하지 않는다 - 이미 각 탭이 수집·가공해둔 데이터(뉴스, AI 브리핑,
지수, 급등락, 업종별 등락)를 다시 읽어서 한 화면에 뿌릴 수 있게 압축·재조합만 한다.
"""

import json
import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def _signed_percent(index_entry):
    """지수 항목(change_percent, direction)에서 부호 있는 등락률(float)을 추출."""
    if not index_entry:
        return 0.0
    raw = (index_entry.get("change_percent") or "")
    raw = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        value = float(raw) if raw else 0.0
    except ValueError:
        value = 0.0
    return -value if index_entry.get("direction") == "down" else value


def _market_mood(indices):
    """코스피/코스닥 평균 등락률로 오늘의 시장 분위기를 5단계로 판정."""
    kospi = next((i for i in indices if i.get("name") == "코스피"), None)
    kosdaq = next((i for i in indices if i.get("name") == "코스닥"), None)
    kospi_pct = _signed_percent(kospi)
    kosdaq_pct = _signed_percent(kosdaq)
    avg = (kospi_pct + kosdaq_pct) / 2

    if avg <= -3:
        label, emoji = "급락", "\U0001F534"       # 🔴
    elif avg <= -1:
        label, emoji = "하락", "\U0001F7E0"        # 🟠
    elif avg < 1:
        label, emoji = "보합", "\u26AA"             # ⚪
    elif avg < 3:
        label, emoji = "상승", "\U0001F535"        # 🔵
    else:
        label, emoji = "급등", "\U0001F7E2"        # 🟢

    def _numeric_value(entry):
        if not entry:
            return None
        try:
            return float(str(entry.get("value", "")).replace(",", ""))
        except (ValueError, TypeError):
            return None

    return {
        "label": label,
        "emoji": emoji,
        "kospi_change": round(kospi_pct, 2),
        "kosdaq_change": round(kosdaq_pct, 2),
        "kospi_value": _numeric_value(kospi),
        "kosdaq_value": _numeric_value(kosdaq),
    }


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


TAB_SOURCES = [
    ("종합", "data/ranking_news.json"),
    ("경제", "data/economy_news.json"),
    ("부동산", "data/realestate_news.json"),
]


def _collect_headlines():
    """종합/경제/부동산 AI 브리핑 + 증권 시황 코멘트를 하나로 모음."""
    headlines = []
    for label, path in TAB_SOURCES:
        data = _load_json(path)
        for line in (data.get("ai_briefing") or []):
            headlines.append({"category": label, "text": line})

    stock_data = _load_json("data/stock_news.json")
    commentary = stock_data.get("ai_commentary")
    if commentary:
        headlines.append({"category": "증권", "text": commentary})

    return headlines


def _article_counts():
    """카테고리별 오늘 수집된 기사 개수 (기사량 급증 신호용)."""
    counts = {}
    for label, path in TAB_SOURCES:
        data = _load_json(path)
        counts[label] = len(data.get("news") or [])

    stock_data = _load_json("data/stock_news.json")
    stock_count = sum(len(cat.get("items", [])) for cat in (stock_data.get("news_categories") or []))
    counts["증권"] = stock_count
    return counts


ARTICLE_COUNT_HISTORY_FILE = os.path.join("data", "article_count_history.json")
ARTICLE_COUNT_HISTORY_MAX_DAYS = 30

# "급증"으로 표시하려면 전일 대비 증가율(%)과 절대 증가량을 동시에 충족해야 한다.
# 참고: 경제/부동산은 크롤러가 매번 "최신 상위 30개" 스냅샷만 가져오고, 증권
# 뉴스도 카테고리당 상위 5개(6개x5=30)로 고정이라 개수 자체가 날마다 거의
# 안 바뀐다. 실제로 날마다 자연스럽게 변하는 건 종합(랭킹, 언론사별 1~5위
# 집계, 400개 안팎)뿐이라, 이 신호는 사실상 종합 카테고리에서 주로 의미가
# 있을 가능성이 높다.
ARTICLE_COUNT_SURGE_PCT = 0.3
ARTICLE_COUNT_SURGE_MIN_DELTA = 5


def _load_article_count_history():
    if not os.path.exists(ARTICLE_COUNT_HISTORY_FILE):
        return []
    try:
        with open(ARTICLE_COUNT_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _save_article_count_history(history):
    os.makedirs("data", exist_ok=True)
    with open(ARTICLE_COUNT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _article_count_trend(today_str, counts):
    """전일(이력상 가장 최근 과거 날짜) 대비 카테고리별 기사량 변화/급증 여부를
    계산하고, 오늘자 스냅샷을 이력에 기록(같은 날 재실행 시 덮어씀)."""
    history = _load_article_count_history()
    past_entries = [h for h in history if h.get("date") != today_str]

    yesterday_counts = past_entries[-1]["counts"] if past_entries else {}

    trend = {}
    for label, today_count in counts.items():
        yesterday_count = yesterday_counts.get(label)
        if not yesterday_count:
            trend[label] = {"today": today_count, "yesterday": yesterday_count, "change_pct": None, "surge": False}
            continue
        change_pct = round((today_count - yesterday_count) / yesterday_count * 100, 1)
        delta = today_count - yesterday_count
        surge = change_pct >= ARTICLE_COUNT_SURGE_PCT * 100 and delta >= ARTICLE_COUNT_SURGE_MIN_DELTA
        trend[label] = {"today": today_count, "yesterday": yesterday_count, "change_pct": change_pct, "surge": surge}

    new_history = past_entries + [{"date": today_str, "counts": counts}]
    _save_article_count_history(new_history[-ARTICLE_COUNT_HISTORY_MAX_DAYS:])

    return trend


# 뉴스랭킹 탭 정렬에 쓰는 것과 동일한 인지도 우선순위 (대표 기사 선정용)
MAJOR_PRESS = [
    "연합뉴스", "KBS", "MBC", "SBS", "JTBC", "YTN", "MBN",
    "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문", "한국일보",
    "매일경제", "한국경제", "서울경제", "헤럴드경제", "이데일리",
    "아시아경제", "파이낸셜뉴스", "머니투데이", "뉴시스", "뉴스1",
    "채널A", "TV조선", "SBS Biz", "연합뉴스TV", "노컷뉴스",
    "세계일보", "국민일보", "문화일보",
]


# "오늘의 이슈" 대표 카드 선정 시 배제할 일반 부고성 기사 키워드. 대기업
# 총수급 부고조차 아닌 일반 부고(예: 지역 언론사 임직원 모친상 등)가 대표
# 이슈로 뽑히는 사고가 있어(2026-08) 아예 후보군에서 제외한다 - 뉴스랭킹
# 탭 등 다른 목록에는 영향 없음(대표 카드 선정 함수에만 적용).
OBITUARY_KEYWORDS = ["부고", "별세", "타계", "모친상", "부친상", "빈소", "발인", "장례식장"]


def _is_obituary(title):
    return any(kw in title for kw in OBITUARY_KEYWORDS)


def _pick_major_or_first(items):
    """메이저 언론사 기사를 우선순위대로 찾고, 없으면 그냥 첫 기사(부고성 기사는 후보에서 제외)."""
    candidates = [item for item in items if not _is_obituary(item.get("title", ""))]
    for press in MAJOR_PRESS:
        for item in candidates:
            if item.get("press_name") == press:
                return item
    return candidates[0] if candidates else None


def _build_hero_for_category(path):
    data = _load_json(path)
    news_list = data.get("news") or []
    top = _pick_major_or_first(news_list)
    if not top:
        return None
    return {
        "title": top.get("title", ""),
        "thumbnail": top.get("thumbnail", ""),
        "link": top.get("link", ""),
        "press_name": top.get("press_name", ""),
    }


def _build_heroes():
    """종합/경제/부동산 각각의 대표(메이저 언론사 우선) 이슈 카드."""
    return {
        "종합": _build_hero_for_category("data/ranking_news.json"),
        "경제": _build_hero_for_category("data/economy_news.json"),
        "부동산": _build_hero_for_category("data/realestate_news.json"),
    }


def build_dashboard():
    stock_data = _load_json("data/stock_news.json")
    indices = stock_data.get("indices") or []

    all_sectors = stock_data.get("sector_performance") or []
    # 히트맵은 상승/하락 양쪽 스펙트럼이 다 보여야 의미가 있으므로,
    # 상위 6개 + 하위 6개를 뽑아 색 대비를 확보한다.
    sector_heatmap = (all_sectors[:6] + all_sectors[-6:]) if len(all_sectors) > 12 else all_sectors

    economy_data = _load_json("data/economy_news.json")
    keyword_data = _load_json("data/keyword_tags.json")
    dart_data = _load_json("data/dart_filings.json")
    macro_data = _load_json("data/macro_indicators.json")
    support_data = _load_json("data/support_programs.json")
    calendar_data = _load_json("data/economic_calendar.json")
    tax_labor_data = _load_json("data/tax_labor_calendar.json")

    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    counts = _article_counts()

    # scraper_dart.py는 오늘자 주요사항보고 공시가 하나도 없으면 파일을
    # 덮어쓰지 않고 가장 최근 영업일 데이터를 그대로 남겨둔다(2026-08).
    # filing_date가 오늘과 다르면 "며칠 전(주말/공휴일이 껴서 하루 이상
    # 차이날 수도 있음) 데이터"라는 뜻이므로, 위젯이 그대로 보여줄 안내
    # 라벨을 여기서 만들어 둔다 - "전일"로 고정 문구를 쓰면 연휴 다음날
    # 아침처럼 실제로는 2~3일 전 데이터인 경우 부정확해지므로 "최근
    # 영업일"이라는 항상-정확한 표현을 쓴다.
    dart_filing_date = dart_data.get("filing_date") or ""
    dart_filing_label = (
        f"최근 영업일({dart_filing_date}) 공시"
        if dart_filing_date and dart_filing_date != today_str
        else None
    )

    dashboard = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "market_mood": _market_mood(indices),
        "heroes": _build_heroes(),
        "headlines": _collect_headlines(),
        "daily_term": economy_data.get("daily_term"),
        "keyword_tags": keyword_data.get("tags") or [],
        "dart_filings": dart_data.get("filings") or [],
        "dart_filing_label": dart_filing_label,
        "macro_indicators": macro_data.get("indicators") or [],
        "support_programs": support_data.get("programs") or [],
        "soso_support_programs": support_data.get("soso_programs") or [],
        "economic_calendar": calendar_data.get("events") or [],
        "tax_labor_events": tax_labor_data.get("events") or [],
        "tax_labor_source_status": tax_labor_data.get("source_status") or {},
        "top_gainers": stock_data.get("top_gainers") or [],
        "top_losers": stock_data.get("top_losers") or [],
        "sector_performance": all_sectors[:5],
        "sector_heatmap": sector_heatmap,
        "article_counts": counts,
        "article_count_trend": _article_count_trend(today_str, counts),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/dashboard.json", "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    return dashboard
