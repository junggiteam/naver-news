"""이미 수집된 데이터(지수/뉴스/공시/거시지표)를 종합해 카테고리별 자체
이슈 리포트를 생성한다. 새로운 크롤링은 하지 않는다.

1단계: 시황/투자/기업 3개 카테고리만 지원.
(IPO/M&A/금융/승계/tax/재테크는 재료 부족·안정성 문제로 보류)
"""

import os
import json
from datetime import datetime, timezone, timedelta

import ai_briefing

KST = timezone(timedelta(hours=9))
CATEGORIES = ["시황", "투자", "기업"]


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def _stock_category_titles(stock_data, category_name, limit=5):
    for cat in stock_data.get("news_categories", []):
        if cat.get("category") == category_name:
            return [item["title"] for item in cat.get("items", [])[:limit]]
    return []


def _build_market_material(stock_data, macro_data):
    """시황: 지수 + 거시경제 지표 + 시황·전망 뉴스 제목."""
    lines = ["[주요 지수]"]
    for idx in stock_data.get("indices", []):
        lines.append(f"- {idx.get('name')}: {idx.get('value')} ({idx.get('change_percent')})")

    indicators = macro_data.get("indicators", [])
    if indicators:
        lines.append("\n[거시경제 지표]")
        for ind in indicators:
            unit = ind.get("unit") or ""
            value_str = f"{ind.get('value')}{unit}" if unit and len(unit) <= 2 else f"{ind.get('value')} ({unit})" if unit else str(ind.get("value"))
            lines.append(f"- {ind.get('name')}: {value_str} ({ind.get('cycle', '')})")

    titles = _stock_category_titles(stock_data, "시황·전망")
    if titles:
        lines.append("\n[관련 뉴스 제목]")
        lines.extend(f"- {t}" for t in titles)

    return "\n".join(lines)


def _build_investment_material(stock_data):
    """투자: 급등락 TOP5 + 업종별 등락."""
    lines = []

    gainers = stock_data.get("top_gainers", [])[:5]
    if gainers:
        lines.append("[오늘의 급등 종목]")
        lines.extend(f"- {i.get('name')}: {i.get('change_percent')}" for i in gainers)

    losers = stock_data.get("top_losers", [])[:5]
    if losers:
        lines.append("\n[오늘의 급락 종목]")
        lines.extend(f"- {i.get('name')}: {i.get('change_percent')}" for i in losers)

    sectors = stock_data.get("sector_performance", [])[:8]
    if sectors:
        lines.append("\n[업종별 등락 상위]")
        lines.extend(f"- {s.get('name')}: {s.get('change_value')}" for s in sectors)

    return "\n".join(lines)


def _build_corporate_material(stock_data, dart_data):
    """기업: DART 주요사항보고(+AI 설명) + 기업·종목분석 뉴스 제목."""
    lines = []

    filings = dart_data.get("filings", [])[:10]
    if filings:
        lines.append("[오늘의 주요 공시]")
        for f in filings:
            desc = f.get("ai_explanation", "")
            entry = f"- {f.get('corp_name')} | {f.get('report_nm')}"
            if desc:
                entry += f" -> {desc}"
            lines.append(entry)

    titles = _stock_category_titles(stock_data, "기업·종목분석")
    if titles:
        lines.append("\n[관련 뉴스 제목]")
        lines.extend(f"- {t}" for t in titles)

    return "\n".join(lines)


def build_daily_reports():
    stock_data = _load_json("data/stock_news.json")
    macro_data = _load_json("data/macro_indicators.json")
    dart_data = _load_json("data/dart_filings.json")

    materials = {
        "시황": _build_market_material(stock_data, macro_data),
        "투자": _build_investment_material(stock_data),
        "기업": _build_corporate_material(stock_data, dart_data),
    }

    reports = {}
    for category in CATEGORIES:
        material = materials[category]
        report = ai_briefing.generate_category_report(category, material)
        reports[category] = report
        status = "생성됨" if report else "생략됨(재료 없음/키 없음/호출 실패)"
        print(f"[daily_reports] {category} {status}")

    output = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "reports": reports,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/daily_reports.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"성공! 카테고리 {len(CATEGORIES)}개 리포트가 data/daily_reports.json에 저장되었습니다.")
    return output


def main():
    build_daily_reports()


if __name__ == "__main__":
    main()
