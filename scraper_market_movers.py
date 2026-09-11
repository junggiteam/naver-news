"""급등/급락 종목 TOP5, 업종별 등락 TOP, IPO 일정을 네이버 금융(모바일 API)에서 수집.

2026-09 finance.naver.com이 stock.naver.com(Next.js) 앱으로 완전히 이전되면서
sise_rise.naver/sise_group.naver/ipo.naver 같은 <table> 기반 페이지가 전부 사라졌다
(html5lib 설치 여부와 무관하게 pd.read_html()이 애초에 읽을 테이블 자체가 없음).
이 새 앱이 클라이언트에서 호출하는 m.stock.naver.com JSON API를 직접 호출하는
방식으로 바꾼다.

다만 이 API(m.stock.naver.com/api/stocks/up·down)는 코스피 상위 20개만 내려주고
코스닥을 포함하는 별도 파라미터/엔드포인트가 없다(2026-09 실측 확인) - 그래서
top_gainers/top_losers는 코스피 기준으로만 채워진다. 코스닥까지 포함하는 대체
엔드포인트를 찾으면 이 부분만 넓히면 된다.
"""

import time
import random
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)


def fetch_json(url, label=""):
    display_label = label or url
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                return response.json()
            print(f"[{display_label}] 응답이 비정상입니다 (상태 코드 {response.status_code}) - {attempt}/{MAX_RETRIES}회 시도")
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"[{display_label}] 요청 중 오류가 발생했습니다: {e} - {attempt}/{MAX_RETRIES}회 시도")

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(*RETRY_WAIT_RANGE)
            time.sleep(wait_seconds)

    print(f"[{display_label}] 페이지 3회 재시도 후 실패")
    return None


def crawl_top_movers(direction, debug_notes=None):
    """direction: 'up'(급등) 또는 'down'(급락). 코스피 기준 상위 20개 중 5개만 사용."""
    label = f"{'급등' if direction == 'up' else '급락'} TOP5(코스피)"
    url = f"https://m.stock.naver.com/api/stocks/{direction}"

    data = fetch_json(url, label=label)
    if data is None:
        if debug_notes is not None:
            debug_notes.append(f"{label} -> fetch 실패")
        return []

    items = []
    for stock in (data.get("stocks") or [])[:5]:
        try:
            rate = float(stock["fluctuationsRatio"])
            items.append({
                "name": stock["stockName"],
                "price": stock["closePrice"],
                "change_percent": f"{rate:+.2f}%",
                "pct": abs(rate),
            })
        except (KeyError, ValueError, TypeError) as e:
            if debug_notes is not None:
                debug_notes.append(f"{label} -> 종목 파싱 실패(원본: {stock!r}): {e}")

    if not items and debug_notes is not None:
        debug_notes.append(f"{label} -> 응답은 받았으나 유효한 종목 0개")

    return items


def crawl_sector_performance(debug_notes=None):
    """업종별 등락 (등락률 기준 내림차순 정렬, 전체 업종).

    dashboard.py의 build_dashboard()가 이 전체 목록을 받아 상위 5개(sector_performance)와
    상/하위 6개씩(sector_heatmap)으로 직접 슬라이싱하므로, 여기서 미리 5개로 자르면 안 된다."""
    # 기본 pageSize=20이라 전체 업종(실측 79개) 중 상승률 상위 20개만 오고
    # 하락 업종이 통째로 빠진다 - 히트맵이 상/하위 대비를 보여줘야 하므로 이
    # API가 허용하는 최대치(100, 그 이상은 400 에러 - 실측 확인)로 전체를 받아온다.
    url = "https://m.stock.naver.com/api/stocks/industry?pageSize=100"
    data = fetch_json(url, label="업종별 시세")
    if data is None:
        if debug_notes is not None:
            debug_notes.append("업종별 시세 -> fetch 실패")
        return []

    groups = data.get("groups") or []
    items = []
    for group in groups:
        try:
            rate = float(group["changeRate"])
            items.append({
                "name": group["name"],
                "change_value": f"{rate:+.2f}%",
                "pct": round(rate, 2),
            })
        except (KeyError, ValueError, TypeError) as e:
            if debug_notes is not None:
                debug_notes.append(f"업종별 시세 -> 항목 파싱 실패(원본: {group!r}): {e}")

    items.sort(key=lambda item: item["pct"], reverse=True)

    if not items and debug_notes is not None:
        debug_notes.append("업종별 시세 -> 응답은 받았으나 유효한 업종 0개")

    return items


def crawl_ipo_calendar(debug_notes=None):
    """공모주 청약 일정."""
    url = "https://m.stock.naver.com/api/stocks/ipo"
    data = fetch_json(url, label="IPO 일정")
    if data is None:
        if debug_notes is not None:
            debug_notes.append("IPO 일정 -> fetch 실패")
        return []

    items = []
    for ipo in (data.get("ipoCoInfos") or [])[:10]:
        try:
            start = ipo.get("poStartDate", "")
            end = ipo.get("poEndDate", "")
            schedule = f"{start}~{end}" if start and end else (start or end)
            items.append({
                "name": ipo["itemName"],
                "schedule": schedule,
                "offer_price": ipo.get("poPrice", ""),
            })
        except (KeyError, TypeError) as e:
            if debug_notes is not None:
                debug_notes.append(f"IPO 일정 -> 항목 파싱 실패(원본: {ipo!r}): {e}")

    if not items and debug_notes is not None:
        debug_notes.append(f"IPO 일정 -> 응답은 받았으나 유효한 일정 0개(원본 개수: {len(data.get('ipoCoInfos') or [])})")

    return items


def crawl_market_movers():
    """지금은 stock_news.json에 필드를 덧붙이는 용도로만 쓰이므로,
    결과 dict와 디버그 노트를 함께 반환한다 (저장은 호출부에서)."""
    debug_notes = []
    result = {}

    try:
        result["top_gainers"] = crawl_top_movers("up", debug_notes)
    except Exception as e:
        debug_notes.append(f"급등 TOP5 -> 예외: {e}")
        result["top_gainers"] = []

    try:
        result["top_losers"] = crawl_top_movers("down", debug_notes)
    except Exception as e:
        debug_notes.append(f"급락 TOP5 -> 예외: {e}")
        result["top_losers"] = []

    try:
        result["sector_performance"] = crawl_sector_performance(debug_notes)
    except Exception as e:
        debug_notes.append(f"업종별 시세 -> 예외: {e}")
        result["sector_performance"] = []

    try:
        result["ipo_calendar"] = crawl_ipo_calendar(debug_notes)
    except Exception as e:
        debug_notes.append(f"IPO 일정 -> 예외: {e}")
        result["ipo_calendar"] = []

    return result, debug_notes
