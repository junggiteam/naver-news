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

6) 영업양수도(신규, 2026-08 추가): DART DS005 그룹 실제 페이지를 직접 열어
   확인 - "영업양수 결정"(apiId=2020042, endpoint bsnInhDecsn)과 "영업양도
   결정"(apiId=2020043, endpoint bsnTrfDecsn) 둘 다 실존하는 별도
   보고서명이다. 양수/양도 여부를 action 필드로 구분(지분인수와 동일한
   패턴).

7) 경영권이동_최대주주변경 확장(2026-08): "최대주주 변경을 수반하는 주식
   담보제공 계약체결 결정"과 "최대주주 변경을 수반하는 주식 양수도
   계약체결 결정"도 이 카테고리에 포함시킨다 - 새 키워드 분기를 따로
   만들 필요 없이, 기존 "최대주주변경" in name 체크가 두 보고서명 모두
   부분 문자열로 이미 포함하고 있어(직접 문자열 대조로 확인) 자동으로
   매칭된다. 별도 카테고리로 분리하지 않은 이유: DS005 API 그룹 페이지를
   직접 순회해 확인한 결과 이 두 보고서명은 DS005에 대응하는 상세 조회
   API 자체가 없다(일반 공시검색으로만 조회 가능) - 기존
   "경영권이동_최대주주변경"도 애초에 "별도 API 조회가 필요 없다"는
   전제로 만들어진 카테고리라 성격이 정확히 일치한다.

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

MA_CATEGORIES = ["합병_분할", "지분인수", "영업양수도", "주식교환_이전", "경영권이동_최대주주변경", "자기주식"]

# 카테고리(또는 카테고리+action) -> DART DS005 상세 API 엔드포인트 파일명.
# https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=XXXX
# 페이지를 하나씩 직접 열어서 확인한 값(추측 아님, 2026-08 확인).
#
# "합병_분할"/"지분인수"/"영업양수도"/"자기주식"은 카테고리 하나 안에
# 실제로는 서로 다른 DART 상세 API 엔드포인트를 쓰는 하위 유형이 섞여
# 있어서(예: 합병_분할은 분할합병/합병/분할 셋 다 DART 공식 API가
# 별도라 하나로 뭉뚱그려 호출할 수 없다) 카테고리명 하나에 endpoint
# 하나만 매핑하면 틀린 엔드포인트를 부르게 된다. 그래서 이 세 카테고리는
# {action: endpoint} 형태로 한 단계 더 들어간다 - classify_report()가
# 이미 채워주는 extra_fields["action"] 값과 그대로 맞아떨어진다.
# "경영권이동_최대주주변경"은 의도적으로 이 딕셔너리에 없다 - DS005
# API 그룹을 직접 순회해 확인한 결과 이 카테고리에 대응하는 상세 조회
# API 자체가 없다(일반 공시검색으로만 조회 가능). dart_report_detail.py는
# 이 카테고리를 매핑이 없으니 자연스럽게 건너뛴다(에러 아님).
MA_CATEGORY_ENDPOINTS = {
    "합병_분할": {
        "분할합병": "cmpDvmgDecsn",
        "합병": "cmpMgDecsn",
        "분할": "cmpDvDecsn",
    },
    "지분인수": {
        "양수": "otcprStkInvscrInhDecsn",
        "양도": "otcprStkInvscrTrfDecsn",
    },
    "영업양수도": {
        "양수": "bsnInhDecsn",
        "양도": "bsnTrfDecsn",
    },
    "주식교환_이전": "stkExtrDecsn",
    "자기주식": {
        "취득": "tsstkAqDecsn",
        "처분": "tsstkDpDecsn",
    },
}


def classify_report(report_nm):
    """report_nm 하나를 받아 매칭되는 (category, extra_fields) 목록을 반환."""
    name = (report_nm or "").replace(" ", "")
    matches = []

    # "분할합병결정"은 "합병결정"을 부분 문자열로 포함하므로(분할+합병+결정)
    # 반드시 먼저 검사해야 한다 - 순서를 바꾸면 분할합병 공시가 그냥
    # "합병"으로 잘못 분류돼 엉뚱한 엔드포인트(cmpMgDecsn)를 부르게 된다.
    if "분할합병결정" in name:
        matches.append(("합병_분할", {"action": "분할합병"}))
    elif "합병결정" in name:
        matches.append(("합병_분할", {"action": "합병"}))
    elif "분할결정" in name:
        matches.append(("합병_분할", {"action": "분할"}))

    if "타법인주식및출자증권양수결정" in name or "타법인주식및출자증권취득결정" in name:
        matches.append(("지분인수", {"action": "양수"}))
    elif "타법인주식및출자증권양도결정" in name:
        matches.append(("지분인수", {"action": "양도"}))

    if "영업양수결정" in name:
        matches.append(("영업양수도", {"action": "양수"}))
    elif "영업양도결정" in name:
        matches.append(("영업양수도", {"action": "양도"}))

    if ("주식의포괄적교환" in name or "포괄적교환" in name or "이전결정" in name) and \
       ("교환" in name or "포괄적" in name):
        matches.append(("주식교환_이전", {}))

    # "최대주주변경"은 "최대주주 변경을 수반하는 주식 양수도/담보제공
    # 계약체결 결정" 두 보고서명 모두 부분 문자열로 포함하고 있어(직접
    # 문자열 대조로 확인, 2026-08) 별도 키워드 분기 없이 이 체크 하나로
    # 세 가지 보고서명을 전부 커버한다.
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
                "corp_code": item.get("corp_code", ""),
                "report_nm": report_nm,
                "rcept_dt": item.get("rcept_dt", ""),
                "rcept_no": item.get("rcept_no", ""),
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
