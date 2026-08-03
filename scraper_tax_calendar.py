"""세무·노무 일정 캘린더: 공휴일(대체공휴일 포함)은 공공데이터포털
한국천문연구원 특일정보 API로 매번 자동 수집하고, 세무 일정은 국세청이
공공데이터포털에 게시하는 '국세청_세무일정' 원본을 참고해 수동 갱신하는
시드 데이터 + 일반 규정 기반 자동 생성 규칙을 함께 사용한다. 노무 일정은
공식 오픈 API가 없어 전액 규정 기반 자동 생성이다.

TAX_SCHEDULE_SEED을 수동 갱신하는 이유: scraper_calendar.py의 BOK_SCHEDULE와
동일한 이유다. data.go.kr의 '국세청_세무일정' 파일데이터는 로그인 후
활용신청을 거쳐 발급되는 다운로드 링크로 제공되고 고정 REST 엔드포인트가
아니라, 매 배포마다 자동 재검증하기가 마땅치 않다. 반면 이 데이터는 국세청이
연 1회 정도 갱신하는 성격이라, 새로 게시될 때 아래 SEED에 그 달 분량을
새로 추가/교체하는 것으로 충분하다. SEED에 없는 달은 자동으로
build_fallback_tax_events()가 채운다 - 화면이 절대 비지 않는다.

공휴일 API 서비스키 발급 방법 (DATA_GO_KR_SERVICE_KEY):
1. https://www.data.go.kr 회원가입
2. '한국천문연구원_특일 정보' 검색 -> 활용신청 (승인 즉시~1일)
3. 마이페이지에서 발급받은 일반 인증키(Decoding) 값을 환경변수로 등록
"""

import os
import json
import calendar as pycalendar
from datetime import date, datetime, timedelta, timezone
import requests

KST = timezone(timedelta(hours=9))

DATA_GO_KR_SERVICE_KEY = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
HOLIDAY_API_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"

SUPPORTED_YEAR_SPAN = 1  # 오늘 기준 전/후 1년(=holiday API 호출 최소화)


# ---------------------------------------------------------------------------
# 1) 공휴일 (한국천문연구원 특일정보 API, 매번 실시간 조회)
# ---------------------------------------------------------------------------

def fetch_holidays_for_month(year, month):
    """해당 연/월의 관공서 공휴일(대체공휴일·임시공휴일 포함)을
    {'YYYY-MM-DD': '명칭'} 형태로 반환. 실패 시 빈 dict."""
    if not DATA_GO_KR_SERVICE_KEY:
        return {}
    params = {
        "serviceKey": DATA_GO_KR_SERVICE_KEY,
        "solYear": str(year),
        "solMonth": f"{month:02d}",
        "numOfRows": "100",
        "_type": "json",
    }
    try:
        response = requests.get(HOLIDAY_API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"[tax_calendar] 특일정보 API 호출 실패({year}-{month:02d}): {e}")
        return {}

    try:
        items = data["response"]["body"]["items"]
        if not items:
            return {}
        item = items.get("item") if isinstance(items, dict) else None
    except (KeyError, TypeError):
        print(f"[tax_calendar] 특일정보 응답 형식이 예상과 다릅니다({year}-{month:02d}): {data}")
        return {}

    if item is None:
        return {}
    rows = item if isinstance(item, list) else [item]

    holidays = {}
    for row in rows:
        locdate = str(row.get("locdate", ""))
        name = row.get("dateName", "")
        if len(locdate) != 8:
            continue
        key = f"{locdate[0:4]}-{locdate[4:6]}-{locdate[6:8]}"
        holidays[key] = name
    return holidays


def fetch_holidays_around(today):
    """오늘 기준 전/후 1년치 공휴일을 월 단위로 모아 반환."""
    holidays = {}
    start = date(today.year - SUPPORTED_YEAR_SPAN, 1, 1)
    end = date(today.year + SUPPORTED_YEAR_SPAN, 12, 1)
    cursor = start
    while cursor <= end:
        holidays.update(fetch_holidays_for_month(cursor.year, cursor.month))
        cursor = date(cursor.year + (1 if cursor.month == 12 else 0),
                       1 if cursor.month == 12 else cursor.month + 1, 1)
    if not holidays:
        print("[tax_calendar] 공휴일 데이터를 하나도 못 가져왔습니다 "
              "(DATA_GO_KR_SERVICE_KEY 미설정 또는 API 오류) - 영업일 보정 없이 진행")
    return holidays


# ---------------------------------------------------------------------------
# 2) 세무 일정 - 국세청 게시 시드 + 규정 기반 폴백
# ---------------------------------------------------------------------------

TAX_SCHEDULE_SEED = {
    "2026-07": [
        (10, "취업 후 학자금 상환(ICL) 원천공제 신고 납부", "2026년 6월분"),
        (10, "인지세 납부", "2026년 6월 작성분"),
        (10, "원천세(반기납 포함) 신고 납부기한", "2026년 6월분 및 2026년 1~6월분"),
        (27, "2026년 1기 부가가치세 확정신고 납부", "2026년 1~6월분"),
        (27, "개별소비세 과세유흥장소 신고 납부", "2026년 6월분"),
        (27, "개별소비세 신고 납부", "2026년 4~6월분"),
        (27, "주세 신고 납부", "2026년 4~6월분"),
        (31, "일용근로소득지급명세서 제출", "2026년 6월 지급분"),
        (31, "간이지급명세서(근로소득) 제출", "2026년 1~6월 지급분"),
        (31, "용역제공자 과세자료 제출", "2026년 6월 소득 발생분"),
        (31, "간이지급명세서(기타소득) 제출", "2026년 6월 지급분"),
        (31, "간이지급명세서(사업소득) 제출", "2026년 6월 지급분"),
        (31, "4월말 결산법인 법인세 신고 납부", "2025년 5월~2026년 4월분"),
        (31, "11월말 결산법인 법인세 중간예납", "2025년 12월~2026년 5월분"),
        (31, "개별소비세·교통에너지환경세 신고 납부", "2026년 6월분"),
    ],
}


def next_business_day(d, holidays):
    """주말·공휴일이면 다음 영업일로 이월 (국세기본법 제5조 기한의 특례)."""
    while d.weekday() >= 5 or d.isoformat() in holidays:
        d += timedelta(days=1)
    return d


def deadline(year, month, day, holidays):
    return next_business_day(date(year, month, day), holidays)


def month_end(year, month, holidays):
    last_day = pycalendar.monthrange(year, month)[1]
    return next_business_day(date(year, month, last_day), holidays)


def build_seed_tax_events(year, month, holidays):
    key = f"{year}-{month:02d}"
    rows = TAX_SCHEDULE_SEED.get(key)
    if not rows:
        return None
    events = []
    for day, title, note in rows:
        events.append({
            "date": date(year, month, day).isoformat(),
            "type": "tax",
            "title": title,
            "detail": note,
            "scope": "국세청 게시 세무일정 원본을 반영한 시드 데이터입니다.",
        })
    return events


def build_fallback_tax_events(year, month, holidays):
    """시드가 없는 달을 위한 일반 규정 기반 자동 생성 (예외 케이스 미반영,
    참고용)."""
    events = []

    def add(d, title, detail):
        events.append({
            "date": d.isoformat(), "type": "tax", "title": title,
            "detail": detail,
            "scope": "일반적인 월별 신고 규정을 기준으로 자동 계산된 참고용 일정입니다.",
        })

    add(deadline(year, month, 10, holidays), "원천세 신고·납부",
        "급여·사업소득·기타소득 등에서 원천징수한 세액을 신고하고 납부합니다.")

    submit_date = month_end(year, month, holidays)
    prev_month = date(year, month, 1) - timedelta(days=1)
    prev_label = f"{prev_month.year}년 {prev_month.month}월 지급분"
    add(submit_date, "일용근로소득지급명세서 제출", f"{prev_label} 제출기한입니다.")
    add(submit_date, "간이지급명세서(사업소득) 제출", f"{prev_label} 제출기한입니다.")
    add(submit_date, "간이지급명세서(기타소득) 제출", f"{prev_label} 제출기한입니다.")

    if month in (1, 4, 7, 10):
        label = "예정" if month in (4, 10) else "확정"
        period = {1: "10~12월분", 4: "1~3월분(예정고지 대상 제외)",
                  7: "4~6월분", 10: "7~9월분(예정고지 대상 제외)"}[month]
        add(deadline(year, month, 25, holidays), f"부가가치세 {label} 신고·납부",
            f"{period}. 사업자 유형과 예정고지 여부에 따라 의무가 다를 수 있습니다.")

    if month == 3:
        add(deadline(year, 3, 10, holidays), "지급명세서 제출",
            "전년도 근로·퇴직·사업소득 등 지급명세서 제출 여부를 확인합니다.")
        add(deadline(year, 3, 31, holidays), "법인세 신고·납부",
            "12월 말 결산법인의 법인세 신고·납부 기한입니다.")
    if month == 5:
        add(deadline(year, 5, 31, holidays), "종합소득세 신고·납부",
            "개인의 전년도 종합소득을 신고하고 납부합니다.")
    if month == 6:
        add(deadline(year, 6, 30, holidays), "성실신고확인대상 종합소득세",
            "성실신고확인대상자의 종합소득세 신고·납부 기한입니다.")

    return events


# ---------------------------------------------------------------------------
# 3) 노무 일정 - 공식 API 없음, 규정 기반 자동 생성
# ---------------------------------------------------------------------------

def build_labor_events(year, holidays):
    events = []

    def add(d, title, detail):
        events.append({
            "date": d.isoformat(), "type": "labor", "title": title,
            "detail": detail,
            "scope": "일반 규정 기준 참고용 안내입니다 (공식 오픈 API 없음).",
        })

    for m in range(1, 13):
        add(deadline(year, m, 10, holidays), "4대보험료 납부",
            "국민연금·건강보험·고용보험·산재보험의 고지 보험료 납부일을 확인하세요.")
        add(deadline(year, m, 15, holidays), "고용보험 취득·상실 신고 점검",
            "입사·퇴사 등 피보험자격 변동이 있는 경우 신고 여부를 점검합니다.")

    add(deadline(year, 3, 10, holidays), "건강보험 보수총액 통보",
        "직장가입자의 전년도 보수총액을 국민건강보험공단에 통보합니다.")
    add(deadline(year, 3, 15, holidays), "고용·산재보험 보수총액 신고",
        "전년도 실제 지급 보수를 기준으로 보험료 정산을 위한 신고를 진행합니다.")
    add(date(year, 12, 31), "연간 노무관리 마감 점검",
        "근로계약서, 연차, 취업규칙, 법정의무교육과 인사자료를 연말에 점검하세요.")

    return events


# ---------------------------------------------------------------------------
# 4) 종합
# ---------------------------------------------------------------------------

def shifted_month(year, month, delta):
    total = (year * 12 + (month - 1)) + delta
    return total // 12, total % 12 + 1


def build_calendar():
    now_kst = datetime.now(KST)
    today = now_kst.date()

    holidays = fetch_holidays_around(today)

    events = []
    seen = set()

    def dedupe_add(ev_list):
        for ev in ev_list:
            uid = (ev["date"], ev["type"], ev["title"])
            if uid in seen:
                continue
            seen.add(uid)
            events.append(ev)

    for delta in (-1, 0, 1):
        y, m = shifted_month(today.year, today.month, delta)
        seed = build_seed_tax_events(y, m, holidays)
        dedupe_add(seed if seed is not None else build_fallback_tax_events(y, m, holidays))

    for y in {today.year - 1, today.year, today.year + 1}:
        dedupe_add(build_labor_events(y, holidays))

    for d, name in holidays.items():
        dedupe_add([{
            "date": d, "type": "holiday", "title": name, "detail": "",
            "scope": "관공서 공휴일 또는 대체공휴일입니다.",
        }])

    events.sort(key=lambda e: (e["date"], e["type"]))

    source_status = {
        "tax": "국세청 게시 세무일정 원본 반영(시드) + 일반 규정 기반 자동 보완"
               if DATA_GO_KR_SERVICE_KEY else "일반 규정 기반 자동 계산(공휴일 API 키 미설정)",
        "holiday": "한국천문연구원 특일정보 API 실시간 연동" if holidays
                   else "공휴일 API 미연동(주말만 반영, 영업일 보정 부정확할 수 있음)",
        "labor": "일반 규정 기준 안내 (공식 오픈 API 없음)",
    }

    output = {
        "updated_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
        "source_status": source_status,
        "events": events,
    }

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "tax_labor_calendar.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"성공! 세무·노무·공휴일 일정 {len(events)}건이 {file_path}에 저장되었습니다.")


def main():
    build_calendar()


if __name__ == "__main__":
    main()
