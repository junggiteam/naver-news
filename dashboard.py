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


# 뉴스랭킹 탭 정렬에 쓰는 것과 동일한 인지도 우선순위 (대표 기사 선정용)
MAJOR_PRESS = [
    "연합뉴스", "KBS", "MBC", "SBS", "JTBC", "YTN", "MBN",
    "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문", "한국일보",
    "매일경제", "한국경제", "서울경제", "헤럴드경제", "이데일리",
    "아시아경제", "파이낸셜뉴스", "머니투데이", "뉴시스", "뉴스1",
    "채널A", "TV조선", "SBS Biz", "연합뉴스TV", "노컷뉴스",
    "세계일보", "국민일보", "문화일보",
]


def _pick_major_or_first(items):
    """메이저 언론사 기사를 우선순위대로 찾고, 없으면 그냥 첫 기사."""
    for press in MAJOR_PRESS:
        for item in items:
            if item.get("press_name") == press:
                return item
    return items[0] if items else None


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

    dashboard = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "market_mood": _market_mood(indices),
        "heroes": _build_heroes(),
        "headlines": _collect_headlines(),
        "daily_term": economy_data.get("daily_term"),
        "top_gainers": stock_data.get("top_gainers") or [],
        "top_losers": stock_data.get("top_losers") or [],
        "sector_performance": all_sectors[:5],
        "sector_heatmap": sector_heatmap,
        "article_counts": _article_counts(),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/dashboard.json", "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    return dashboard
