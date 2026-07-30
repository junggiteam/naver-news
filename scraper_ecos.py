"""한국은행 ECOS Open API에서 거시경제 지표(100대 통계지표)를 가져와
일반 사용자에게 의미 있는 지표만 선별해 저장.
"""

import os
import json
from datetime import datetime, timezone, timedelta
import requests

ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "")
KEY_STATISTIC_URL = "https://ecos.bok.or.kr/api/KeyStatisticList/{key}/json/kr/1/110"

# ECOS "100대 통계지표"(KeyStatisticList) 전체(101개) 중, 대시보드에
# 노출할 만한 핵심 지표만 선별. 지표명은 API가 내려주는 KEYSTAT_NAME과
# 정확히 일치해야 매칭된다.
SELECTED_INDICATORS = [
    "한국은행 기준금리",
    "국고채수익률(3년)",
    "원/달러 환율(종가)",
    "소비자물가지수",
    "실업률",
    "경제성장률(실질, 계절조정 전기대비)",
    "주택매매가격지수",
    "소비자심리지수",
]


def crawl_macro_indicators():
    if not ECOS_API_KEY:
        print("ECOS_API_KEY 없음 - 거시경제 지표 수집 생략")
        return

    url = KEY_STATISTIC_URL.format(key=ECOS_API_KEY)
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"ECOS API 호출 실패: {e}")
        return

    result = data.get("KeyStatisticList")
    if not result:
        print(f"ECOS 응답 형식이 예상과 다릅니다: {data}")
        return

    rows = result.get("row") or []
    by_name = {row.get("KEYSTAT_NAME"): row for row in rows}

    indicators = []
    for name in SELECTED_INDICATORS:
        row = by_name.get(name)
        if not row:
            print(f"[ecos] '{name}' 지표를 응답에서 찾지 못했습니다 (지표명이 바뀌었을 수 있음)")
            continue
        indicators.append({
            "class": row.get("CLASS_NAME", ""),
            "name": row.get("KEYSTAT_NAME", ""),
            "value": row.get("DATA_VALUE", ""),
            "unit": row.get("UNIT_NAME", ""),
            "cycle": row.get("CYCLE", ""),
        })

    kst_timezone = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    output = {"updated_at": now_kst, "indicators": indicators}

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "macro_indicators.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"성공! 거시경제 지표 {len(indicators)}개가 {file_path}에 저장되었습니다.")


def main():
    crawl_macro_indicators()


if __name__ == "__main__":
    main()
