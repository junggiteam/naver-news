"""급등/급락 종목 TOP5, 업종별 등락 TOP, IPO 일정을 네이버 금융에서 수집.

전용 CSS 선택자를 추측하는 대신, 페이지 안의 HTML <table>을 pandas가
구조적으로 파싱하게 하고 컬럼 이름으로 원하는 테이블/값을 찾는 방식을 쓴다.
Naver가 클래스명을 바꿔도(자주 있는 일) 테이블 자체 구조만 유지되면
계속 동작할 가능성이 높아, 개별 선택자 방식보다 이 페이지들에는 더 안정적이다.
"""

import io
import re
import time
import random
import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MAX_RETRIES = 3
RETRY_WAIT_RANGE = (15, 20)


def fetch(url, label=""):
    display_label = label or url
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                response.encoding = response.apparent_encoding or "euc-kr"
                return response.text
            print(f"[{display_label}] 응답이 비정상입니다 (상태 코드 {response.status_code}) - {attempt}/{MAX_RETRIES}회 시도")
        except requests.exceptions.RequestException as e:
            print(f"[{display_label}] 요청 중 오류가 발생했습니다: {e} - {attempt}/{MAX_RETRIES}회 시도")

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(*RETRY_WAIT_RANGE)
            time.sleep(wait_seconds)

    print(f"[{display_label}] 페이지 3회 재시도 후 실패")
    return None


def _flat_col_name(col):
    """MultiIndex 컬럼(병합된 헤더 등)도 하나의 문자열로 평탄화."""
    if isinstance(col, tuple):
        return " ".join(str(c) for c in col if "Unnamed" not in str(c))
    return str(col)


def _find_table_with_column(tables, keyword):
    """읽어들인 테이블 목록 중, 컬럼 이름에 keyword가 포함된 첫 테이블과
    그 실제 컬럼명(원본, 평탄화 전)을 함께 반환. 못 찾으면 (None, None)."""
    for df in tables:
        for col in df.columns:
            if keyword in _flat_col_name(col):
                return df, col
    return None, None


def _get_col(df, keyword, default=""):
    """평탄화한 컬럼명에 keyword가 포함된 첫 컬럼을 찾아 그 컬럼 객체를 반환."""
    for col in df.columns:
        if keyword in _flat_col_name(col):
            return col
    return None


def crawl_top_movers(direction, sosok, market_label, debug_notes=None):
    """direction: 'rise'(급등) 또는 'fall'(급락). sosok: 0=코스피, 1=코스닥."""
    page = "sise_rise" if direction == "rise" else "sise_fall"
    label = f"{market_label} {'급등' if direction == 'rise' else '급락'} TOP5"
    url = f"https://finance.naver.com/sise/{page}.naver?sosok={sosok}"

    html = fetch(url, label=label)
    if html is None:
        if debug_notes is not None:
            debug_notes.append(f"{label} -> fetch 실패")
        return []

    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception as e:
        if debug_notes is not None:
            debug_notes.append(f"{label} -> pandas 테이블 파싱 실패: {e}")
        return []

    df, name_col = _find_table_with_column(tables, "종목명")
    if df is None:
        if debug_notes is not None:
            debug_notes.append(f"{label} -> 테이블 {len(tables)}개 중 '종목명' 컬럼을 가진 테이블 없음")
        return []

    df = df.dropna(subset=[name_col])
    price_col = _get_col(df, "현재가")
    change_col = _get_col(df, "등락률")

    items = []
    for _, row in df.head(5).iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        items.append({
            "name": name,
            "price": str(row[price_col]).strip() if price_col is not None else "",
            "change_percent": str(row[change_col]).strip() if change_col is not None else "",
        })

    if not items and debug_notes is not None:
        debug_notes.append(f"{label} -> 테이블은 찾았으나 유효한 행이 0개")

    return items


def crawl_sector_performance(debug_notes=None):
    """업종별 등락 TOP (상승률 기준 정렬 상위 5개)."""
    url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
    html = fetch(url, label="업종별 시세")
    if html is None:
        if debug_notes is not None:
            debug_notes.append("업종별 시세 -> fetch 실패")
        return []

    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception as e:
        if debug_notes is not None:
            debug_notes.append(f"업종별 시세 -> pandas 테이블 파싱 실패: {e}")
        return []

    df, name_col = _find_table_with_column(tables, "업종명")
    if df is None:
        if debug_notes is not None:
            debug_notes.append(f"업종별 시세 -> 테이블 {len(tables)}개 중 '업종명' 컬럼을 가진 테이블 없음")
        return []

    df = df.dropna(subset=[name_col])
    change_col = _get_col(df, "등락률")
    if change_col is None:
        if debug_notes is not None:
            debug_notes.append(f"업종별 시세 -> '등락률' 컬럼을 못 찾음 (컬럼들: {[_flat_col_name(c) for c in df.columns]})")
        return []

    def parse_pct(v):
        m = re.search(r'([+-]?[\d.]+)', str(v).replace(",", ""))
        return float(m.group(1)) if m else 0.0

    df = df.copy()
    df["_pct"] = df[change_col].apply(parse_pct)
    df = df.sort_values("_pct", ascending=False)

    items = []
    for _, row in df.head(5).iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        items.append({
            "name": name,
            "change_percent": str(row[change_col]).strip(),
        })

    if not items and debug_notes is not None:
        debug_notes.append("업종별 시세 -> 테이블은 찾았으나 유효한 행이 0개")

    return items


def crawl_ipo_calendar(debug_notes=None):
    """공모주 청약 일정."""
    url = "https://finance.naver.com/sise/ipo.naver"
    html = fetch(url, label="IPO 일정")
    if html is None:
        if debug_notes is not None:
            debug_notes.append("IPO 일정 -> fetch 실패")
        return []

    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception as e:
        if debug_notes is not None:
            debug_notes.append(f"IPO 일정 -> pandas 테이블 파싱 실패: {e}")
        return []

    df, name_col = _find_table_with_column(tables, "종목명")
    if df is None:
        if debug_notes is not None:
            debug_notes.append(f"IPO 일정 -> 테이블 {len(tables)}개 중 '종목명' 컬럼을 가진 테이블 없음")
        return []

    df = df.dropna(subset=[name_col])
    date_col = _get_col(df, "청약일") or _get_col(df, "일정")
    price_col = _get_col(df, "공모가")

    items = []
    for _, row in df.head(10).iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        items.append({
            "name": name,
            "schedule": str(row[date_col]).strip() if date_col is not None else "",
            "offer_price": str(row[price_col]).strip() if price_col is not None else "",
        })

    if not items and debug_notes is not None:
        debug_notes.append("IPO 일정 -> 테이블은 찾았으나 유효한 행이 0개")

    return items


def crawl_market_movers():
    """지금은 stock_news.json에 필드를 덧붙이는 용도로만 쓰이므로,
    결과 dict와 디버그 노트를 함께 반환한다 (저장은 호출부에서)."""
    debug_notes = []
    result = {}

    try:
        kospi_gainers = crawl_top_movers("rise", 0, "코스피", debug_notes)
        kosdaq_gainers = crawl_top_movers("rise", 1, "코스닥", debug_notes)
        result["top_gainers"] = (kospi_gainers + kosdaq_gainers)[:5]
    except Exception as e:
        debug_notes.append(f"급등 TOP5 -> 예외: {e}")
        result["top_gainers"] = []

    try:
        kospi_losers = crawl_top_movers("fall", 0, "코스피", debug_notes)
        kosdaq_losers = crawl_top_movers("fall", 1, "코스닥", debug_notes)
        result["top_losers"] = (kospi_losers + kosdaq_losers)[:5]
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
