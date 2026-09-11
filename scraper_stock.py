import os
import json
import time
import random
from datetime import datetime, timezone, timedelta
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)  # 재시도 사이 대기 시간(초)


def fetch_json(url, label=""):
    """요청 실패(타임아웃/5xx/JSON 아닌 응답 등) 시 최대 MAX_RETRIES회까지 재시도.
    모두 실패하면 None을 반환해 호출부에서 해당 페이지를 건너뛸 수 있게 한다.

    2026-09 finance.naver.com이 stock.naver.com(Next.js) 앱으로 완전히 이전되면서
    예전 페이지들은 전부 이 새 앱으로 리다이렉트되고, 지수/시세/뉴스 데이터는 더 이상
    서버 렌더링된 HTML 안에 없다(React Server Components 스트리밍 방식이라 CSS
    선택자로 읽을 대상 자체가 없어짐). 대신 이 앱이 클라이언트에서 호출하는
    m.stock.naver.com / stock.naver.com JSON API를 직접 호출한다."""
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
            print(f"[{display_label}] {wait_seconds:.1f}초 대기 후 재시도합니다...")
            time.sleep(wait_seconds)

    print(f"[{display_label}] 페이지 3회 재시도 후 실패")
    return None


def _format_as_of(local_traded_at):
    """API가 주는 localTradedAt(ISO 8601, 타임존 포함)을 기존 표시 형식으로 변환."""
    if not local_traded_at:
        return ""
    try:
        return datetime.fromisoformat(local_traded_at).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return local_traded_at


def build_change_percent(rate):
    rate = float(rate)
    direction = "up" if rate >= 0 else "down"
    arrow = "▲" if direction == "up" else "▼"
    return f"{arrow}{abs(rate):.2f}%", direction


def crawl_domestic_index(code, name, debug_notes=None):
    """코스피/코스닥/코스피200: m.stock.naver.com 지수 상세 API(JSON)."""
    url = f"https://m.stock.naver.com/api/index/{code}/basic"
    data = fetch_json(url, label=f"{name} 지수")
    if data is None:
        if debug_notes is not None:
            debug_notes.append(f"{name}({code}) -> fetch 자체가 실패(요청/응답 오류, 3회 재시도 후)")
        return None

    try:
        change_percent, direction = build_change_percent(data["fluctuationsRatio"])
        return {
            "name": name,
            "value": data["closePrice"],
            "change_percent": change_percent,
            "direction": direction,
            "as_of": _format_as_of(data.get("localTradedAt", "")),
        }
    except (KeyError, ValueError, TypeError) as e:
        if debug_notes is not None:
            debug_notes.append(f"{name}({code}) -> 응답 JSON 파싱 실패(원본: {data!r}): {e}")
        return None


WORLD_INDEX_CODES = [
    (".DJI", "다우존스"),
    (".IXIC", "나스닥"),
    (".NDX", "나스닥100"),
    (".INX", "S&P500"),
]


def crawl_world_indices(debug_notes=None):
    """다우존스/나스닥/나스닥100/S&P500: polling.finance.naver.com 실시간 API(JSON).
    reutersCode가 예전 "DJI@DJI" 형식에서 ".DJI" 형식으로 바뀌었다(2026-09 확인)."""
    results = []
    for reuters_code, name in WORLD_INDEX_CODES:
        url = f"https://polling.finance.naver.com/api/realtime/worldstock/index/{reuters_code}"
        data = fetch_json(url, label=f"{name} 지수")
        datas = (data or {}).get("datas") or []
        if not datas:
            if debug_notes is not None:
                debug_notes.append(f"{name}({reuters_code}) -> 데이터 없음(응답: {data!r})")
            continue
        item = datas[0]
        try:
            change_percent, direction = build_change_percent(item["fluctuationsRatio"])
            results.append({
                "name": name,
                "value": item["closePrice"],
                "change_percent": change_percent,
                "direction": direction,
                "as_of": _format_as_of(item.get("localTradedAt", "")),
            })
        except (KeyError, ValueError, TypeError) as e:
            if debug_notes is not None:
                debug_notes.append(f"{name}({reuters_code}) -> 응답 JSON 파싱 실패(원본: {item!r}): {e}")
    return results


def crawl_marketindex_price(category, code, name, debug_notes=None):
    """환율/유가/금속 등: stock.naver.com marketindex 상세 API(JSON) 공통 구조.
    exchange 카테고리만 응답이 {"exchangeInfo": {...}}로 한 겹 감싸져 있고
    energy/metals는 바로 최상위 객체라, 있으면 벗겨내는 방식으로 통일한다."""
    url = f"https://stock.naver.com/api/securityService/marketindex/{category}/{code}"
    data = fetch_json(url, label=name)
    if data is None:
        if debug_notes is not None:
            debug_notes.append(f"{name} -> fetch 자체가 실패(요청/응답 오류, 3회 재시도 후)")
        return None

    item = data.get("exchangeInfo", data) if isinstance(data, dict) else None
    if not item:
        if debug_notes is not None:
            debug_notes.append(f"{name} -> 응답 형식이 예상과 다름(원본: {data!r})")
        return None

    try:
        change_percent, direction = build_change_percent(item["fluctuationsRatio"])
        return {
            "name": name,
            "value": item["closePrice"],
            "change_percent": change_percent,
            "direction": direction,
            "as_of": _format_as_of(item.get("localTradedAt", "")),
        }
    except (KeyError, ValueError, TypeError) as e:
        if debug_notes is not None:
            debug_notes.append(f"{name} -> 응답 JSON 파싱 실패(원본: {item!r}): {e}")
        return None


GOLD_GRAMS_PER_DON = 3.75  # 국내금 API는 원/g 기준이라 1돈 환산이 필요


def crawl_domestic_gold(debug_notes=None):
    """국내금: marketindex API가 원/g 기준으로만 주므로 1돈(3.75g) 환산값으로 저장."""
    result = crawl_marketindex_price("metals", "M04020000", "국내금(원/돈)", debug_notes)
    if result is None:
        return None
    try:
        grams_value = float(str(result["value"]).replace(",", ""))
        result["value"] = f"{grams_value * GOLD_GRAMS_PER_DON:,.2f}"
    except (ValueError, TypeError) as e:
        if debug_notes is not None:
            debug_notes.append(f"국내금(원/돈) -> 원/g -> 원/돈 환산 실패(원본 value: {result.get('value')!r}): {e}")
    return result


DOMESTIC_BOND_TARGETS = [
    ("KR3YT=RR", "국고채(3년)"),
    ("KR10YT=RR", "국고채(10년)"),
]


def crawl_domestic_bonds(debug_notes=None):
    """국고채(3년)/(10년): stock.naver.com 국채 목록 API(JSON).
    marketindexCd(IRR_GOVT03Y 등) 기반 상세 페이지가 사라지고, 국가별 국채
    수익률을 한 번에 내려주는 목록 API(nation=KOR)로 바뀌어 한 번의 호출로 두
    만기를 모두 추출한다."""
    url = "https://stock.naver.com/api/securityService/marketindex/bond/nation/KOR"
    data = fetch_json(url, label="국고채(3년/10년)")
    if data is None:
        if debug_notes is not None:
            debug_notes.append("국고채(3년/10년) -> fetch 자체가 실패(요청/응답 오류, 3회 재시도 후)")
        return []

    by_code = {item.get("reutersCode"): item for item in data} if isinstance(data, list) else {}
    results = []
    for reuters_code, name in DOMESTIC_BOND_TARGETS:
        item = by_code.get(reuters_code)
        if not item:
            if debug_notes is not None:
                debug_notes.append(f"{name}({reuters_code}) -> 목록에서 항목을 찾지 못함")
            continue
        try:
            change_percent, direction = build_change_percent(item["fluctuationsRatio"])
            results.append({
                "name": name,
                "value": item["closePrice"],
                "change_percent": change_percent,
                "direction": direction,
                "as_of": _format_as_of(item.get("localTradedAt", "")),
            })
        except (KeyError, ValueError, TypeError) as e:
            if debug_notes is not None:
                debug_notes.append(f"{name}({reuters_code}) -> 응답 JSON 파싱 실패(원본: {item!r}): {e}")
    return results


def crawl_bitcoin():
    """비트코인(원/코인): 업비트 공개 API"""
    response = requests.get("https://api.upbit.com/v1/ticker?markets=KRW-BTC", timeout=10)
    response.raise_for_status()
    ticker = response.json()[0]

    change_percent, direction = build_change_percent(ticker['signed_change_rate'] * 100)

    date_part = ticker.get('trade_date_kst', '')
    time_part = ticker.get('trade_time_kst', '')
    as_of = ""
    if len(date_part) == 8 and len(time_part) == 6:
        as_of = (f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]} "
                 f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}")

    return {
        "name": "비트코인(원/코인)",
        "value": f"{ticker['trade_price']:,.0f}",
        "change_percent": change_percent,
        "direction": direction,
        "as_of": as_of
    }


def crawl_ethereum():
    """이더리움(원/코인): 업비트 공개 API - crawl_bitcoin()과 동일한 구조"""
    response = requests.get("https://api.upbit.com/v1/ticker?markets=KRW-ETH", timeout=10)
    response.raise_for_status()
    ticker = response.json()[0]

    change_percent, direction = build_change_percent(ticker['signed_change_rate'] * 100)

    date_part = ticker.get('trade_date_kst', '')
    time_part = ticker.get('trade_time_kst', '')
    as_of = ""
    if len(date_part) == 8 and len(time_part) == 6:
        as_of = (f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]} "
                 f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}")

    return {
        "name": "이더리움(원/코인)",
        "value": f"{ticker['trade_price']:,.0f}",
        "change_percent": change_percent,
        "direction": direction,
        "as_of": as_of
    }


NEWS_CATEGORIES = [
    ("시황·전망", 401),
    ("기업·종목분석", 402),
    ("해외증시", 403),
    ("채권·선물", 404),
    ("공시·메모", 406),
    ("환율", 429),
]


def crawl_news_category(category_name, section_id3, now_kst, debug_notes=None):
    """finance.naver.com/news/ 카테고리별(시황·전망 등) 뉴스.

    2026-09 news_list.naver 페이지가 stock.naver.com/news/section으로 리다이렉트되며
    section_id3 쿼리스트링이 통째로 사라지고 카테고리 구분 없는 랜딩 페이지만 남는다.
    실제 탭별 뉴스는 이 페이지가 클라이언트에서 호출하는 /api/domestic/news/focus
    JSON API로 받아온다. date는 KST 기준 오늘 날짜(YYYYMMDD)를 반드시 넘겨야 하고,
    생략하면 articleTotal이 0인 빈 응답만 온다(실측 확인)."""
    date_str = now_kst.strftime("%Y%m%d")
    url = (
        "https://stock.naver.com/api/domestic/news/focus"
        f"?sid={section_id3}&page=1&pageSize=15&date={date_str}"
    )
    data = fetch_json(url, label=f"{category_name} 뉴스")
    if data is None:
        if debug_notes is not None:
            debug_notes.append(f"{category_name} 뉴스 -> fetch 자체가 실패(요청/응답 오류, 3회 재시도 후)")
        return {"category": category_name, "items": []}

    items = []
    for rank, article in enumerate((data.get("articles") or [])[:15], start=1):
        upload_time = article.get("date", "") or ""
        published_at = ""
        if len(upload_time) == 14:
            try:
                published_at = (
                    datetime.strptime(upload_time, "%Y%m%d%H%M%S")
                    .replace(tzinfo=now_kst.tzinfo)
                    .isoformat()
                )
            except ValueError:
                pass

        items.append({
            "press_name": article.get("officeHName", ""),
            "rank": rank,
            "title": article.get("title", ""),
            "link": article.get("url", ""),
            "upload_time": upload_time,
            "published_at": published_at
        })

    if not items and debug_notes is not None:
        debug_notes.append(f"{category_name} 뉴스 -> 응답은 받았으나 기사 0건(원본 articleTotal: {data.get('articleTotal')!r})")

    return {"category": category_name, "items": items}


def crawl_stock_data():
    indices = []
    debug_notes = []  # 크롤러 실패 시 원인 파악용 - dashboard/위젯에는 노출 안 함(stock_news.json의 _debug 필드로만 저장)

    for code, name in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥"), ("KPI200", "코스피200")]:
        try:
            idx = crawl_domestic_index(code, name, debug_notes)
            if idx:
                indices.append(idx)
            else:
                print(f"{name} 데이터를 찾지 못했습니다.")
        except Exception as e:
            print(f"{name} 수집 실패: {e}")
            debug_notes.append(f"{name}(code={code}) -> 예외: {e}")

    try:
        indices.extend(crawl_world_indices(debug_notes))
    except Exception as e:
        print(f"해외 지수(다우존스/나스닥/S&P500) 수집 실패: {e}")
        debug_notes.append(f"해외 지수 -> 예외: {e}")

    try:
        gold = crawl_domestic_gold(debug_notes)
        if gold:
            indices.append(gold)
        else:
            print("국내금 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"국내금 수집 실패: {e}")
        debug_notes.append(f"국내금 -> 예외: {e}")

    try:
        gasoline = crawl_marketindex_price("energy", "OIL_GSL", "휘발유(원/리터)", debug_notes)
        if gasoline:
            indices.append(gasoline)
        else:
            print("휘발유 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"휘발유 수집 실패: {e}")
        debug_notes.append(f"휘발유(OIL_GSL) -> 예외: {e}")

    try:
        usd_krw = crawl_marketindex_price("exchange", "FX_USDKRW", "원/달러 환율", debug_notes)
        if usd_krw:
            indices.append(usd_krw)
        else:
            print("원/달러 환율 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"원/달러 환율 수집 실패: {e}")
        debug_notes.append(f"원/달러 환율(FX_USDKRW) -> 예외: {e}")

    try:
        jpy_krw = crawl_marketindex_price("exchange", "FX_JPYKRW", "원/엔 환율(100엔)", debug_notes)
        if jpy_krw:
            indices.append(jpy_krw)
        else:
            print("원/엔 환율 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"원/엔 환율 수집 실패: {e}")
        debug_notes.append(f"원/엔 환율(FX_JPYKRW) -> 예외: {e}")

    try:
        eur_krw = crawl_marketindex_price("exchange", "FX_EURKRW", "원/유로 환율", debug_notes)
        if eur_krw:
            indices.append(eur_krw)
        else:
            print("원/유로 환율 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"원/유로 환율 수집 실패: {e}")
        debug_notes.append(f"원/유로 환율(FX_EURKRW) -> 예외: {e}")

    try:
        usd_jpy = crawl_marketindex_price("exchangeWorld", "USDJPY", "USD/JPY", debug_notes)
        if usd_jpy:
            indices.append(usd_jpy)
        else:
            print("USD/JPY 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"USD/JPY 수집 실패: {e}")
        debug_notes.append(f"USD/JPY(exchangeWorld/USDJPY) -> 예외: {e}")

    try:
        eur_usd = crawl_marketindex_price("exchangeWorld", "EURUSD", "EUR/USD", debug_notes)
        if eur_usd:
            indices.append(eur_usd)
        else:
            print("EUR/USD 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"EUR/USD 수집 실패: {e}")
        debug_notes.append(f"EUR/USD(exchangeWorld/EURUSD) -> 예외: {e}")

    try:
        wti = crawl_marketindex_price("energy", "CLcv1", "WTI(국제유가)", debug_notes)
        if wti:
            indices.append(wti)
        else:
            print("WTI 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"WTI 수집 실패: {e}")
        debug_notes.append(f"WTI(energy/CLcv1) -> 예외: {e}")

    try:
        indices.extend(crawl_domestic_bonds(debug_notes))
    except Exception as e:
        print(f"국고채(3년/10년) 수집 실패: {e}")
        debug_notes.append(f"국고채(3년/10년) -> 예외: {e}")

    try:
        bitcoin = crawl_bitcoin()
        indices.append(bitcoin)
    except Exception as e:
        print(f"비트코인 수집 실패: {e}")

    try:
        ethereum = crawl_ethereum()
        indices.append(ethereum)
    except Exception as e:
        print(f"이더리움 수집 실패: {e}")

    kst_timezone = timezone(timedelta(hours=9))
    now_kst_dt = datetime.now(kst_timezone)
    now_kst_minute = now_kst_dt.replace(second=0, microsecond=0)

    news_categories = []
    for category_name, section_id3 in NEWS_CATEGORIES:
        try:
            news_categories.append(crawl_news_category(category_name, section_id3, now_kst_minute, debug_notes))
        except Exception as e:
            print(f"[{category_name}] 뉴스 수집 실패: {e}")
            debug_notes.append(f"{category_name} 뉴스 -> 예외: {e}")
            news_categories.append({"category": category_name, "items": []})

    os.makedirs("data", exist_ok=True)

    output = {
        "updated_at": now_kst_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
        "news_categories": news_categories
    }
    if debug_notes:
        output["_debug"] = debug_notes

    file_path = os.path.join("data", "stock_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    total_news = sum(len(c["items"]) for c in news_categories)
    print(f"성공! 지표 {len(indices)}개, 뉴스 카테고리 {len(news_categories)}개(총 {total_news}건)가 {file_path}에 저장되었습니다.")


def main():
    crawl_stock_data()


if __name__ == "__main__":
    main()
