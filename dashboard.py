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

    return {
        "label": label,
        "emoji": emoji,
        "kospi_change": round(kospi_pct, 2),
        "kosdaq_change": round(kosdaq_pct, 2),
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


def build_dashboard():
    stock_data = _load_json("data/stock_news.json")
    indices = stock_data.get("indices") or []

    dashboard = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "market_mood": _market_mood(indices),
        "headlines": _collect_headlines(),
        "top_gainers": stock_data.get("top_gainers") or [],
        "top_losers": stock_data.get("top_losers") or [],
        "sector_performance": stock_data.get("sector_performance") or [],
        "article_counts": _article_counts(),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/dashboard.json", "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    return dashboard
