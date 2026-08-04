"""DART 주요사항보고서(report_nm)를 "주요사항보고서 주요정보"(DS005 API
그룹) 19개 세부 유형 중 하나로 분류하고, 상세정보 조회에 필요한 API
엔드포인트 파일명을 함께 반환한다.

dart_ma_signals.py의 classify_report()(M&A 관점 5개 카테고리만 다룸)보다
훨씬 넓은 범위를 다루는 별개 분류기다 - 이 모듈은 "오늘 올라온 주요사항
보고서 전체를 기사로 정리"하는 용도라 report_nm이 매핑하는 모든 유형을
다뤄야 한다.

매핑값은 https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=XXXX
페이지를 하나씩 직접 열어서 확인한 값이다(추측 아님, 2026-08 확인).

키워드 우선순위: 문자열 길이가 긴(더 구체적인) 키워드부터 검사한다.
실제로 "무상증자결정"이 "유무상증자결정"의 뒷부분과 완전히 겹치는 경우가
있어서("유무상증자결정"[1:] == "무상증자결정"), 짧은 키워드를 먼저
검사하면 "유무상증자결정" 공시가 "무상증자결정"으로 잘못 분류된다. 길이
내림차순 정렬로 이런 부분 문자열 겹침을 전부 안전하게 처리한다
(dart_ma_signals.py의 "분할합병결정을 분할/합병보다 먼저 검사"하던
관례와 같은 원리).

report_nm 안의 "[기재정정]", "[정정명령부과]" 같은 접두어는 따로 벗기지
않는다 - 부분 문자열(in) 검사라 앞에 뭐가 붙어 있어도 정상적으로
매칭된다(예: "[기재정정]주요사항보고서(회사합병결정)"도 "회사합병결정"을
그대로 포함하고 있음). 접두어 제거는 화면 표시용(ma-ticker.html의
shortenReportName())에만 필요하고 분류에는 필요 없다.

주의: "주식교환ㆍ이전결정"의 가운뎃점은 일반 middle dot(·, U+00B7)이
아니라 한글 호환 자모 아래아(ㆍ, U+318D)다 - 실제 dart_ma_signals.json에
쌓인 원본 데이터로 직접 확인함. 다른 문자를 쓰면 이 카테고리만 조용히
매칭 실패한다.
"""

# (report_nm에 포함될 키워드, 카테고리 라벨, DART API 엔드포인트 파일명)
# 길이 내림차순으로 미리 정렬돼 있음 - 새 항목을 추가할 때도 이 순서
# 원칙을 지킬 것 (아래 _RULES 생성 시 자동으로 길이순 재정렬하니 순서를
# 꼭 손으로 맞출 필요는 없지만, 표를 훑어볼 때 헷갈리지 않도록 유지한다).
_RAW_RULES = [
    ("상각형조건부자본증권발행결정", "상각형조건부자본증권발행결정", "wdCocobdIsDecsn"),
    ("자기주식취득신탁계약체결결정", "자기주식취득신탁계약체결결정", "tsstkAqTrctrCnsDecsn"),
    ("자기주식취득신탁계약해지결정", "자기주식취득신탁계약해지결정", "tsstkAqTrctrCcDecsn"),
    ("타법인주식및출자증권양수결정", "타법인주식및출자증권양수결정", "otcprStkInvscrInhDecsn"),
    ("타법인주식및출자증권양도결정", "타법인주식및출자증권양도결정", "otcprStkInvscrTrfDecsn"),
    ("신주인수권부사채권발행결정", "신주인수권부사채권발행결정", "bdwtIsDecsn"),
    ("주권관련사채권양수결정", "주권관련사채권양수결정", "stkrtbdInhDecsn"),
    ("주권관련사채권양도결정", "주권관련사채권양도결정", "stkrtbdTrfDecsn"),
    ("교환사채권발행결정", "교환사채권발행결정", "exbdIsDecsn"),
    ("전환사채권발행결정", "전환사채권발행결정", "cvbdIsDecsn"),
    ("주식교환ㆍ이전결정", "주식교환·이전결정", "stkExtrDecsn"),  # 원본은 ㆍ(U+318D), 라벨 표시는 · 그대로 둠
    ("회사분할합병결정", "회사분할합병결정", "cmpDvmgDecsn"),
    ("자기주식취득결정", "자기주식취득결정", "tsstkAqDecsn"),
    ("자기주식처분결정", "자기주식처분결정", "tsstkDpDecsn"),
    ("유무상증자결정", "유무상증자결정", "pifricDecsn"),
    ("회사합병결정", "회사합병결정", "cmpMgDecsn"),
    ("회사분할결정", "회사분할결정", "cmpDvDecsn"),
    ("유상증자결정", "유상증자결정", "piicDecsn"),
    ("무상증자결정", "무상증자결정", "fricDecsn"),
]

# 혹시 위 리스트 순서가 흐트러져도 항상 길이 내림차순으로 검사하도록
# 런타임에 재정렬해서 고정한다.
_RULES = sorted(_RAW_RULES, key=lambda r: len(r[0]), reverse=True)


def classify(report_nm):
    """report_nm 문자열을 받아 (category_label, api_endpoint_filename)
    튜플을 반환. 19개 유형 중 아무것도 안 걸리면 None(에러 아님 - 정기
    공시 등 이 분류 대상이 아닌 보고서가 훨씬 많다)."""
    name = (report_nm or "").replace(" ", "")
    if not name:
        return None
    for keyword, label, endpoint in _RULES:
        if keyword in name:
            return (label, endpoint)
    return None
