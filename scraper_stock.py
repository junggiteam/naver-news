import os
import re
import json
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.text


def build_change_percent(rate):
    rate = float(rate)
    direction = "up" if rate >= 0 else "down"
    arrow = "▲" if direction == "up" else "▼"
    return f"{arrow}{abs(rate):.2f}%", direction


def crawl_domestic_index(code, name):
    """코스피/코스닥: /sise/sise_index.naver 페이지"""
    html = fetch(f"https://finance.naver.com/sise/sise_index.naver?code={code}")
    soup = BeautifulSoup(html, 'lxml')

    value_elem = soup.select_one('#now_value')
    fluc_elem = soup.select_one('#change_value_and_rate')
    if not value_elem or not fluc_elem:
        return None

    percent_match = re.search(r'([+-][\d.]+)%', fluc_elem.get_text())
    if not percent_match:
        return None
    change_percent, direction = build_change_percent(percent_match.group(1))

    as_of = ""
    iframe = soup.select_one("iframe[name='time']")
    if iframe and iframe.get('src'):
        time_match = re.search(r'thistime=(\d{14})', iframe['src'])
        if time_match:
            ts = time_match.group(1)
            as_of = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"

    return {
        "name": name,
        "value": value_elem.get_text(strip=True),
        "change_percent": change_percent,
        "direction": direction,
        "as_of": as_of
    }


def crawl_world_indices():
    """다우존스, 나스닥, S&P500: /world/ 페이지에 내장된 실시간 데이터(JS 변수)"""
    html = fetch("https://finance.naver.com/world/")
    match = re.search(r"var americaData = jindo\.\$H\((\{.*?\})\);", html)
    if not match:
        return []

    data = json.loads(match.group(1))
    targets = [
        ("DJI@DJI", "다우존스"),
        ("NAS@IXIC", "나스닥"),
        ("SPI@SPX", "S&P500"),
    ]

    results = []
    for symbol, name in targets:
        item = data.get(symbol)
        if not item:
            continue
        change_percent, direction = build_change_percent(item.get('rate', 0))
        results.append({
            "name": name,
            "value": f"{item.get('last', 0):,.2f}",
            "change_percent": change_percent,
            "direction": direction,
            "as_of": item.get('lastUpdTime', '')
        })
    return results


def crawl_detail_price(url, name):
    """국내금, 휘발유 등: marketindex 상세 페이지 공통 구조(.no_today / .no_exday)"""
    html = fetch(url)
    soup = BeautifulSoup(html, 'lxml')

    value_elem = soup.select_one('.today .no_today em')
    exday_ems = soup.select('.today .no_exday em')
    if not value_elem or len(exday_ems) < 2:
        return None

    percent_match = re.search(r'([+-][\d.]+)%', exday_ems[1].get_text())
    if not percent_match:
        return None
    change_percent, direction = build_change_percent(percent_match.group(1))

    as_of = ""
    date_elem = soup.select_one('.exchange_info .date')
    if date_elem:
        as_of = date_elem.get_text(strip=True)

    return {
        "name": name,
        "value": value_elem.get_text(strip=True),
        "change_percent": change_percent,
        "direction": direction,
        "as_of": as_of,
        "_soup": soup
    }


def crawl_domestic_gold():
    """국내금: 위 공통 구조는 원/g 기준이라, 계산기의 1돈(3.75g) 환산값으로 대체"""
    result = crawl_detail_price("https://finance.naver.com/marketindex/goldDetail.naver", "국내금(원/돈)")
    if result is None:
        return None

    soup = result.pop("_soup")
    calc_output = soup.select_one('#calcOutput')
    if calc_output and calc_output.get('value'):
        result["value"] = calc_output['value'].strip()

    return result


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


NEWS_CATEGORIES = [
    ("시황·전망", 401),
    ("기업·종목분석", 402),
    ("해외증시", 403),
    ("채권·선물", 404),
    ("공시·메모", 406),
    ("환율", 429),
]


def crawl_news_category(category_name, section_id3):
    """finance.naver.com/news/ 카테고리별(시황·전망 등) 뉴스 1~5위"""
    url = (
        "https://finance.naver.com/news/news_list.naver"
        f"?mode=LSS3D&section_id=101&section_id2=258&section_id3={section_id3}"
    )
    html = fetch(url)
    soup = BeautifulSoup(html, 'lxml')

    items = []
    top_list = soup.select_one('ul.realtimeNewsList li.newsList.top')
    subjects = top_list.select('.articleSubject') if top_list else []

    for rank, subject in enumerate(subjects[:5], start=1):
        title_elem = subject.select_one('a')
        if not title_elem:
            continue

        title = title_elem.get('title', '').strip() or title_elem.get_text(strip=True)
        link = title_elem.get('href', '')
        if link.startswith('/'):
            link = "https://finance.naver.com" + link

        summary = subject.find_next_sibling(class_='articleSummary')
        press_elem = summary.select_one('.press') if summary else None
        time_elem = summary.select_one('.wdate') if summary else None

        items.append({
            "press_name": press_elem.get_text(strip=True) if press_elem else "",
            "rank": rank,
            "title": title,
            "link": link,
            "upload_time": time_elem.get_text(strip=True) if time_elem else ""
        })

    return {"category": category_name, "items": items}


def crawl_stock_data():
    indices = []

    for code, name in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
        try:
            idx = crawl_domestic_index(code, name)
            if idx:
                indices.append(idx)
            else:
                print(f"{name} 데이터를 찾지 못했습니다.")
        except Exception as e:
            print(f"{name} 수집 실패: {e}")

    try:
        indices.extend(crawl_world_indices())
    except Exception as e:
        print(f"해외 지수(다우존스/나스닥/S&P500) 수집 실패: {e}")

    try:
        gold = crawl_domestic_gold()
        if gold:
            indices.append(gold)
        else:
            print("국내금 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"국내금 수집 실패: {e}")

    try:
        gasoline = crawl_detail_price(
            "https://finance.naver.com/marketindex/oilDetail.naver?marketindexCd=OIL_GSL",
            "휘발유(원/리터)"
        )
        if gasoline:
            gasoline.pop("_soup", None)
            indices.append(gasoline)
        else:
            print("휘발유 데이터를 찾지 못했습니다.")
    except Exception as e:
        print(f"휘발유 수집 실패: {e}")

    try:
        bitcoin = crawl_bitcoin()
        indices.append(bitcoin)
    except Exception as e:
        print(f"비트코인 수집 실패: {e}")

    news_categories = []
    for category_name, section_id3 in NEWS_CATEGORIES:
        try:
            news_categories.append(crawl_news_category(category_name, section_id3))
        except Exception as e:
            print(f"[{category_name}] 뉴스 수집 실패: {e}")
            news_categories.append({"category": category_name, "items": []})

    os.makedirs("data", exist_ok=True)

    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "updated_at": now_kst,
        "indices": indices,
        "news_categories": news_categories
    }

    file_path = os.path.join("data", "stock_news.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    total_news = sum(len(c["items"]) for c in news_categories)
    print(f"성공! 지표 {len(indices)}개, 뉴스 카테고리 {len(news_categories)}개(총 {total_news}건)가 {file_path}에 저장되었습니다.")


if __name__ == "__main__":
    crawl_stock_data()
