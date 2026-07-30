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
from bs4 import BeautifulSoup

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
        change_text = str(row[change_col]).strip() if change_col is not None else ""
        pct_match = re.search(r'([+-]?[\d.]+)', change_text.replace(",", ""))
        items.append({
            "name": name,
            "price": str(row[price_col]).strip() if price_col is not None else "",
            "change_percent": change_text,
            "pct": abs(float(pct_match.group(1))) if pct_match else 0.0,
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
    change_col = _get_col(df, "전일대비")
    if change_col is None:
        if debug_notes is not None:
            debug_notes.append(f"업종별 시세 -> '전일대비' 컬럼을 못 찾음 (컬럼들: {[_flat_col_name(c) for c in df.columns]})")
        return []

    def _as_series(df_or_series):
        """중복된 컬럼 라벨 때문에 df[col]이 DataFrame으로 잡히는 경우를
        첫 번째 컬럼만 남긴 1차원 Series로 강제 변환."""
        if isinstance(df_or_series, pd.DataFrame):
            return df_or_series.iloc[:, 0].reset_index(drop=True)
        return df_or_series.reset_index(drop=True)

    name_series = _as_series(df[name_col])
    change_series = _as_series(df[change_col])

    def parse_pct(v):
        m = re.search(r'([+-]?[\d.]+)', str(v).replace(",", ""))
        return float(m.group(1)) if m else 0.0

    combined = pd.DataFrame({
        "name": name_series,
        "change_value": change_series.astype(str).str.strip(),
    })
    combined["pct"] = combined["change_value"].apply(parse_pct)
    combined = combined.sort_values("pct", ascending=False)

    items = []
    for _, row in combined.iterrows():
        name = str(row["name"]).strip()
        if not name or name.lower() == "nan":
            continue
        items.append({
            "name": name,
            "change_value": row["change_value"],
            "pct": round(float(row["pct"]), 2),
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

    # 1차 시도: <table> 구조로 되어 있는 경우 (pandas)
    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception:
        tables = []

    df, name_col = _find_table_with_column(tables, "종목명")
    if df is not None:
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
        if items:
            return items

    # 2차 시도: <table> 구조가 아닐 수 있으므로, BeautifulSoup으로 "공모/청약"
    # 관련 텍스트 주변 실제 마크업을 진단용으로 남긴다 (다음 조사를 위한 근거 확보).
    if debug_notes is not None:
        soup = BeautifulSoup(html, 'lxml')
        table_summaries = [
            f"table#{i}: shape={t.shape}, cols={[_flat_col_name(c) for c in t.columns]}"
            for i, t in enumerate(tables)
        ]

        keyword_idx = html.find('공모')
        snippet = html[max(0, keyword_idx - 200):keyword_idx + 400] if keyword_idx != -1 else "(응답에 '공모' 텍스트 자체가 없음)"

        list_like = soup.select('ul li a, div.tbl_type1 li')
        list_preview = [el.get_text(strip=True) for el in list_like[:10]]

        debug_notes.append(
            "IPO 일정 -> table 방식 실패. "
            f"발견된 table 개수={len(tables)} [{'; '.join(table_summaries)}], "
            f"'공모' 주변 마크업 스니펫={snippet!r}, "
            f"리스트형 요소 미리보기={list_preview}"
        )

    return []


def crawl_investor_net_buy(debug_notes=None):
    """외국인/기관 순매수 상위 5종목 (코스피+코스닥 합산). pykrx 라이브러리 사용.
    당일 데이터는 보통 장 마감(18시) 이후에나 확정되므로, 비어있으면
    최근 영업일 쪽으로 최대 5일까지 거슬러 올라가며 데이터가 있는 날을 찾는다."""
    result = {"foreign": [], "institution": []}
    try:
        from pykrx import stock as krx_stock
        from datetime import datetime, timezone, timedelta
        KST = timezone(timedelta(hours=9))

        def _fetch(investor_key, market, date_str):
            df = krx_stock.get_market_net_purchases_of_equities(date_str, date_str, market, investor_key)
            return df

        for investor_key, result_key in [("외국인", "foreign"), ("기관합계", "institution")]:
            rows = []
            for market in ["KOSPI", "KOSDAQ"]:
                df = None
                used_date = None
                for days_back in range(0, 6):  # 오늘부터 최대 5영업일 전까지 시도
                    date_str = (datetime.now(KST) - timedelta(days=days_back)).strftime("%Y%m%d")
                    try:
                        candidate = _fetch(investor_key, market, date_str)
                        if candidate is not None and not candidate.empty:
                            df = candidate
                            used_date = date_str
                            break
                    except Exception as e:
                        if debug_notes is not None:
                            debug_notes.append(f"{result_key} {market}({date_str}) 순매수 -> 예외: {e}")

                if df is None:
                    if debug_notes is not None:
                        debug_notes.append(f"{result_key} {market} 순매수 -> 최근 6일 모두 비어있음")
                    continue

                df = df.sort_values("순매수거래대금", ascending=False)
                for ticker, row in df.head(5).iterrows():
                    rows.append({
                        "name": str(row.get("종목명", "")),
                        "net_value": int(row.get("순매수거래대금", 0)),
                        "as_of": used_date,
                    })
            rows.sort(key=lambda r: r["net_value"], reverse=True)
            result[result_key] = rows[:5]
    except Exception as e:
        if debug_notes is not None:
            debug_notes.append(f"투자자별 순매수 -> 전체 예외: {e}")
    return result


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

    try:
        result["investor_net_buy"] = crawl_investor_net_buy(debug_notes)
    except Exception as e:
        debug_notes.append(f"투자자별 순매수 -> 예외: {e}")
        result["investor_net_buy"] = {"foreign": [], "institution": []}

    return result, debug_notes
