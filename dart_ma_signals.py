"""scraper_dart.py가 이미 받아온 data/dart_filings.json(주요사항보고 전체)을
후처리해서 M&A 관련 5개 카테고리로 재분류한다. DART API를 추가로 호출하지
않는다 - 이미 있는 데이터를 report_nm 기준으로 다시 태깅만 한다.

구현 전 조사 결과 (중요 - 처음 요청받은 키워드 중 일부를 실제 DART 공식
보고서명에 맞게 보정함):

1) 합병_분할: "합병결정", "분할결정" 외에 "분할합병결정"(분할과 합병이
   동시에 일어나는 결합 형태)도 실제 존재하는 별도 보고서명이고, 이건
   "분할결정"의 부분문자열이 아니라서(분할-합병-결정 순서) 빠뜨리면 누락된다.
   -> 세 키워드 모두 포함.

2) 지분인수: "타법인주식및출자증권취득결정"은 실제 DART 공식 보고서명이
   아니다. 공식 명칭은 "취득"이 아니라 "양수"를 써서 "타법인 주식 및
   출자증권 양수결정"이다(공공데이터포털에도 이 명칭으로 등록돼 있음,
   data.go.kr/data/15094493). 반대 방향인 "타법인 주식 및 출자증권
   양도결정"(지분 매각)도 별도 보고서로 존재한다.
   -> "양수결정"은 지분인수로, "양도결정"은 지분매각으로 구분해서 태깅.
   -> 혹시 모를 표기 차이에 대비해 "취득결정" 패턴도 폴백으로 남겨둠.

3) 주식교환_이전: 실제 공식 명칭은 "주식의 포괄적 교환·이전 결정"
   하나의 결합된 보고서명이다(두 개의 별도 보고서가 아님). "이전결정"만
   단독으로 매칭하면 무관한 보고서를 오탐할 가능성이 있어, "교환" 또는
   "포괄적"이 함께 있는 경우만 이 카테고리로 인정하도록 가드를 추가했다.

4) 경영권이동_최대주주변경: 조사 결과, 이 공시는 "최대주주 변경을
   수반하는 주식양수도 계약 체결"이라는 이름으로 자본시장법 시행령
   제171조상 주요사항보고서 항목에 이미 포함돼 있다(KRX KIND 공시 사례
   확인: report code 71207). 즉 pblntf_ty=B(주요사항보고) 범위 안에서
   scraper_dart.py가 이미 수집하고 있어 별도 API 조회가 필요 없다.
   (참고: 5% 이상 대량보유 변동 보고인 D001은 이것과 다른 별도 제도라
   여기서는 다루지 않음 - 필요해지면 그때 pblntf_ty=D 조회를 추가할 것.)

5) 자기주식: "자기주식취득결정"/"자기주식처분결정" 그대로 사용, 취득/처분
   여부를 action 필드로 구분.

저장 구조 (날짜별 무기한 누적 - daily_reports_archive.json과 동일한 패턴):
dart_filings.json 자체가 매일 "오늘의 주요사항보고"만 담아 덮어쓰는 파일이라,
여기서 매번 최신 결과만 저장하면 오늘 신규 M&A 공시가 0건인 날엔 위젯의
"최근 공시" 목록이 통째로 비어버리는 문제가 있었다. 그래서
data/dart_ma_signals.json을 {"YYYY-MM-DD": {카테고리: [...]}} 형태의
날짜별 아카이브로 바꾸고, 매 실행마다 오늘 날짜 키만 갱신(다른 날짜는
보존)한다. 용량 제한은 두지 않는다(daily_reports_archive.json과 동일한
방침 - 나중에 커지면 그때 정리).
"""

import os
import json
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

MA_CATEGORIES = ["합병_분할", "지분인수", "주식교환_이전", "경영권이동_최대주주변경", "자기주식"]


def classify_report(report_nm):
    """report_nm 하나를 받아 매칭되는 (category, extra_fields) 목록을 반환."""
    name = (report_nm or "").replace(" ", "")
    matches = []

    if "분할합병결정" in name or "합병결정" in name or "분할결정" in name:
        matches.append(("합병_분할", {}))

    if "타법인주식및출자증권양수결정" in name or "타법인주식및출자증권취득결정" in name:
        matches.append(("지분인수", {"action": "양수"}))
    elif "타법인주식및출자증권양도결정" in name:
        matches.append(("지분인수", {"action": "양도"}))

    if ("주식의포괄적교환" in name or "포괄적교환" in name or "이전결정" in name) and \
       ("교환" in name or "포괄적" in name):
        matches.append(("주식교환_이전", {}))

    if "최대주주변경" in name:
        matches.append(("경영권이동_최대주주변경", {}))

    if "자기주식취득결정" in name:
        matches.append(("자기주식", {"action": "취득"}))
    elif "자기주식처분결정" in name:
        matches.append(("자기주식", {"action": "처분"}))

    return matches


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


MA_ARCHIVE_FILE = os.path.join("data", "dart_ma_signals.json")


def _is_date_key(key):
    try:
        datetime.strptime(key, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def build_ma_signals():
    filings_data = _load_json("data/dart_filings.json")
    filings = filings_data.get("filings") or []

    today_signals = {cat: [] for cat in MA_CATEGORIES}

    for item in filings:
        report_nm = item.get("report_nm", "")
        for category, extra in classify_report(report_nm):
            entry = {
                "corp_name": item.get("corp_name", ""),
                "report_nm": report_nm,
                "rcept_dt": item.get("rcept_dt", ""),
                "source_url": item.get("link", ""),
            }
            entry.update(extra)
            today_signals[category].append(entry)

    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    # 카테고리 키(MA_CATEGORIES)가 아닌 별도 키라서, MA_CATEGORIES만 순회하는
    # 위젯/집계 로직(counts 계산 등)에는 영향 없음. dart_filings.json의
    # updated_at을 참고하던 위젯 메타 텍스트("~ 기준")가 날짜만 있고 시:분이
    # 없어진 문제를 해결하기 위해 추가.
    today_signals["_updated_at"] = now_kst.strftime("%Y-%m-%d %H:%M:%S")

    raw_archive = _load_json(MA_ARCHIVE_FILE)
    # 구버전 평면 스키마({"date":..., "ma_signals":...}) 잔재 제거 - 날짜
    # 형식이 아닌 키는 전부 버린다 (daily_reports.py에서 겪은 것과 동일한
    # 스키마 오염 문제를 여기서도 예방)
    archive = {k: v for k, v in raw_archive.items() if _is_date_key(k)}
    archive[today_str] = today_signals

    os.makedirs("data", exist_ok=True)
    with open(MA_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    counts = {cat: len(today_signals[cat]) for cat in MA_CATEGORIES}
    total = sum(counts.values())
    print(f"[dart_ma] {today_str} 주요사항보고 {len(filings)}건 중 M&A 시그널 {total}건 분류 및 아카이브 저장: {counts}")
    return archive


def main():
    build_ma_signals()


if __name__ == "__main__":
    main()
