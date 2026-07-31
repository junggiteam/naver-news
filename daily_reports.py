"""이미 수집된 데이터(지수/뉴스/공시/거시지표)를 종합해 카테고리별 자체
이슈 리포트를 생성한다. 새로운 크롤링은 하지 않는다.

1단계: 시황/투자/기업 3개 카테고리만 지원.
(IPO/M&A/금융/승계/tax/재테크는 재료 부족·안정성 문제로 보류)

오전판(morning)/저녁판(evening) 두 판을 구분해서 생성한다:
- 오전판: 전일 마감 리캡 + 오늘 오전 이슈 중심. 당일 장중 수치를 마감
  등락률처럼 단정하지 않도록 자료 자체도 "전일 마감"과 "오늘 오전 현재"를
  구분해서 구성한다.
- 저녁판: 당일 마감(또는 마감에 가까운) 수치 중심. 기존 방식 그대로.

data/daily_reports.json은 {"reports": {"morning": {...}, "evening": {...}}}
구조라, 한쪽 판을 생성할 때 다른 쪽 판 데이터를 덮어쓰지 않도록 항상
기존 파일을 먼저 읽고 해당 판 키만 갱신해서 저장한다.
"""

import os
import json
from datetime import datetime, timezone, timedelta

import ai_briefing

KST = timezone(timedelta(hours=9))
CATEGORIES = ["시황", "투자", "기업"]
REPORTS_FILE = os.path.join("data", "daily_reports.json")


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


def _find_previous_close(history):
    """stock_index_history.json 스냅샷 중, 오늘보다 이전 날짜의 가장 마지막
    (=장 마감에 가장 가까운) 스냅샷을 찾아 반환. 없으면 None.
    크롤러가 장 마감 이후에도 계속 도는 덕에, 전일 마지막 스냅샷은 보통
    마감가에서 더 안 바뀐 값(연속 동일값)으로 실제 마감가와 일치한다."""
    if not history:
        return None
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    prev_entries = [h for h in history if h.get("time", "").split(" ")[0] < today_str]
    if not prev_entries:
        return None
    return prev_entries[-1]


# ---------- 저녁판(마감) 자료 구성 - 기존 방식 그대로 ----------

def _build_market_material(stock_data, macro_data):
    """시황(저녁판): 지수 + 거시경제 지표 + 시황·전망 뉴스 제목."""
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
    """투자(저녁판): 급등락 TOP5 + 업종별 등락."""
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
    """기업: DART 주요사항보고(+AI 설명) + 기업·종목분석 뉴스 제목.
    오전판/저녁판 공통 - DART는 항상 "오늘" 날짜로 조회하고, 공시/사건
    중심이라 시점 구분이 가격 데이터만큼 중요하지 않음."""
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


# ---------- 오전판(조간) 자료 구성 - 전일 마감 + 오늘 오전 이슈 ----------

def _build_market_material_morning(stock_data, history):
    """시황(오전판): 전일 마감 지수 + 오늘 오전 관련 뉴스 제목.
    당일 장중 등락률은 싣지 않는다 - 아직 확정된 하루 수치가 아니기 때문."""
    lines = []

    prev_close = _find_previous_close(history)
    if prev_close:
        lines.append(f"[전일 마감 지수] (기준시각: {prev_close.get('time')})")
        for name, value in prev_close.get("values", {}).items():
            lines.append(f"- {name}: {value}")
    else:
        lines.append("[전일 마감 지수] 이력 없음(자료 보관 기간 밖이거나 최초 실행)")

    titles = _stock_category_titles(stock_data, "시황·전망")
    if titles:
        lines.append("\n[오늘 오전 관련 뉴스 제목]")
        lines.extend(f"- {t}" for t in titles)

    return "\n".join(lines)


def _build_investment_material_morning(stock_data):
    """투자(오전판): 오늘 오전 현재 급등락/업종 동향. 데이터 자체는 저녁판과
    같은 소스이지만(현재 스냅샷), 프롬프트가 "오전 기준" 표현을 강제한다."""
    lines = []

    gainers = stock_data.get("top_gainers", [])[:5]
    if gainers:
        lines.append("[오늘 오전 현재 상승 종목]")
        lines.extend(f"- {i.get('name')}: {i.get('change_percent')}" for i in gainers)

    losers = stock_data.get("top_losers", [])[:5]
    if losers:
        lines.append("\n[오늘 오전 현재 하락 종목]")
        lines.extend(f"- {i.get('name')}: {i.get('change_percent')}" for i in losers)

    sectors = stock_data.get("sector_performance", [])[:8]
    if sectors:
        lines.append("\n[오늘 오전 현재 업종별 등락 상위]")
        lines.extend(f"- {s.get('name')}: {s.get('change_value')}" for s in sectors)

    return "\n".join(lines)


# CLAUDE.md 6번 원칙 - 과거 전체 기록과 비교하는 느낌을 주는 미검증 표현
# 목록. 프롬프트 지침만으로는 100% 지켜지지 않는 경우가 실제로 확인돼서
# (예: "기록적인 반등"), 생성 후 후처리 검증으로 한 번 더 걸러낸다.
BANNED_SUPERLATIVE_WORDS = ["역대", "최고", "최대", "사상 처음", "기록적"]


def _contains_banned_expression(report):
    if not report:
        return False
    text = f"{report.get('title', '')} {report.get('body', '')}"
    return any(word in text for word in BANNED_SUPERLATIVE_WORDS)


def _generate_checked_report(category, material, report_type):
    """금지 표현(BANNED_SUPERLATIVE_WORDS) 포함 시 1회 자동 재생성.
    재생성해도 또 걸리면 해당 카테고리는 이번 판에서 생략(None) - 전체
    발행을 막지 않고 그 카테고리만 스킵한다."""
    report = ai_briefing.generate_category_report(category, material, report_type=report_type)
    if _contains_banned_expression(report):
        print(f"[daily_reports:{report_type}] {category} 금지 표현 감지 - 1회 재생성 시도")
        report = ai_briefing.generate_category_report(category, material, report_type=report_type)
        if _contains_banned_expression(report):
            print(f"[daily_reports:{report_type}] {category} 재생성 후에도 금지 표현 감지 - 이번 판에서 생략")
            return None
    return report


def _generate_reports(materials, report_type):
    reports = {}
    for category in CATEGORIES:
        material = materials[category]
        report = _generate_checked_report(category, material, report_type)
        reports[category] = report
        status = "생성됨" if report else "생략됨(재료 없음/키 없음/호출 실패/금지 표현 재생성 실패)"
        print(f"[daily_reports:{report_type}] {category} {status}")
    return reports


VALID_REPORT_TYPES = ("morning", "evening")


def _save_edition(report_type, basis, reports):
    """daily_reports.json에서 report_type 판(오전/저녁)만 갱신하고 다른 판은
    보존한다. morning/evening 구조 도입 이전의 평면 스키마(카테고리명이
    reports 바로 아래 있던 구버전) 잔재가 있으면 함께 정리한다."""
    output = _load_json(REPORTS_FILE)
    existing_reports = output.get("reports", {})
    # 구버전 스키마 잔재 제거: morning/evening이 아닌 키(예: 예전 "시황" 등)는 버림
    cleaned_reports = {k: v for k, v in existing_reports.items() if k in VALID_REPORT_TYPES}

    cleaned_reports[report_type] = {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "basis": basis,
        **reports,
    }
    output["reports"] = cleaned_reports
    output["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    os.makedirs("data", exist_ok=True)
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"성공! {report_type}판 카테고리 {len(CATEGORIES)}개 리포트가 {REPORTS_FILE}에 저장되었습니다.")
    return output


def build_morning_reports():
    """오전판(조간): 전일 마감 리캡 + 오늘 오전 이슈."""
    stock_data = _load_json("data/stock_news.json")
    history = _load_json("data/stock_index_history.json")
    dart_data = _load_json("data/dart_filings.json")
    if not isinstance(history, list):
        history = []

    materials = {
        "시황": _build_market_material_morning(stock_data, history),
        "투자": _build_investment_material_morning(stock_data),
        "기업": _build_corporate_material(stock_data, dart_data),
    }
    reports = _generate_reports(materials, "morning")
    return _save_edition("morning", "전일 마감 + 오늘 오전 이슈", reports)


def build_evening_reports():
    """저녁판(마감): 당일 마감(또는 마감에 가까운) 수치 중심."""
    stock_data = _load_json("data/stock_news.json")
    macro_data = _load_json("data/macro_indicators.json")
    dart_data = _load_json("data/dart_filings.json")

    materials = {
        "시황": _build_market_material(stock_data, macro_data),
        "투자": _build_investment_material(stock_data),
        "기업": _build_corporate_material(stock_data, dart_data),
    }
    reports = _generate_reports(materials, "evening")
    return _save_edition("evening", "당일 마감", reports)


def main():
    """단독 실행 시(python daily_reports.py)에는 저녁판을 생성한다.
    오전판은 build_morning_reports()를 별도로 호출해서 쓴다."""
    build_evening_reports()


if __name__ == "__main__":
    main()
