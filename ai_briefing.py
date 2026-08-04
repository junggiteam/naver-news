"""Gemini API를 이용한 탭별 '오늘의 브리핑' / 증권 시황 코멘트 생성 모듈.

GEMINI_API_KEY 환경변수가 없거나 API 호출이 실패해도 예외를 던지지 않고
None/빈 리스트를 반환한다. 크롤링 자체(핵심 기능)는 AI 기능과 완전히
분리되어 있어서, 이 모듈이 통째로 실패해도 뉴스 목록 표시에는 영향이 없다.
"""

import os
import re
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Gemini 호출 실패 시 원인을 담아두는 변수. run_scheduled.py에서 필요할 때만
# 데이터 파일에 ai_debug 필드로 잠깐 노출시켜 원인 파악용으로 쓴다
# (마스킹 처리되어 있어 키 유출 위험 없음).
LAST_ERROR = None

# 코스피/코스닥 중 하나라도 이 이상 움직이면 시황 코멘트 생성
STOCK_COMMENTARY_THRESHOLD = 1.5


def _call_gemini(prompt, timeout=60):
    global LAST_ERROR
    if not GEMINI_API_KEY:
        LAST_ERROR = "GEMINI_API_KEY 환경변수 없음"
        print("[ai_briefing] GEMINI_API_KEY 없음 - AI 기능 생략")
        return None
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        body = ""
        try:
            body = resp.text[:300]
        except Exception:
            pass
        raw_error = f"{type(e).__name__}: {e} | body={body}"
        # requests 예외 메시지에는 요청 URL 전체(쿼리스트링의 API 키 포함)가
        # 그대로 들어가는 경우가 있어, 로그/저장 전에 반드시 키를 마스킹한다.
        # (실제로 이걸 안 해서 GitHub Push Protection에 막혀 자동 push가
        # 계속 실패했던 적이 있음 - 키가 실제로 유출되진 않았지만 원인이었음)
        LAST_ERROR = raw_error.replace(GEMINI_API_KEY, "***") if GEMINI_API_KEY else raw_error
        print(f"[ai_briefing] Gemini 호출 실패: {LAST_ERROR}")
        return None


# CLAUDE.md "수치 인용 원칙" - 과거 전체 기록과 비교하는 느낌을 주는
# 최상급 표현은 실제 비교 데이터가 있을 때만 허용. daily_reports.py의
# 카테고리 리포트뿐 아니라 이 파일의 대시보드용 브리핑/코멘트에도 공통
# 적용한다 (record_verification 모듈과 짝을 이룸).
SUPERLATIVE_GUIDE = (
    "과거 전체 기록과 비교하는 느낌을 주는 표현(\"역대\", \"최고\", \"최대\",\n"
    "\"사상 처음\", \"기록적\" 등 이 유형에 속하는 모든 표현, 목록에 없는\n"
    "비슷한 표현도 마찬가지)은 실제로 비교 가능한 과거 데이터가 있어서 그\n"
    "비교가 사실로 확인된 경우에만 써라. 그런 근거가 없으면 이런 유형의\n"
    "표현 자체를 쓰지 마라.\n"
)


def _verified_facts_block(verified_facts):
    """record_verification이 코드로 직접 계산해 확인한 사실을 프롬프트에
    넣을 블록으로 변환. 없으면 빈 문자열(=최상급 표현 여전히 금지)."""
    if not verified_facts:
        return ""
    verified_lines = "\n".join(verified_facts)
    return (
        "\n[검증된 사실 - 코드로 직접 계산해 확인됨]\n"
        f"{verified_lines}\n"
        "위 검증된 사실에 명시된 지표·기간에 한해서만 최상급 표현을 써도\n"
        "된다. 그 외에는 절대 쓰지 마라 - 검증되지 않은 추측성 최상급\n"
        "표현은 금지다.\n"
    )


def generate_tab_briefing(titles, label, verified_facts=None):
    """탭별 '오늘의 브리핑' 3줄 생성. 실패/데이터없음 시 빈 리스트 반환."""
    if not titles:
        return []

    titles_block = "\n".join(f"- {t}" for t in titles[:20])
    prompt = (
        f"아래는 오늘 수집된 {label} 뉴스 제목 목록이다.\n"
        "이 중 가장 중요한 흐름 3가지를 각각 한 줄(40자 이내)로 요약하라.\n"
        "과장하지 말고 사실 위주로, 기사 제목에 없는 내용은 추측하지 마라.\n"
        f"{SUPERLATIVE_GUIDE}"
        f"{_verified_facts_block(verified_facts)}"
        "출력은 순수 텍스트로 줄바꿈 구분된 3줄만, 번호나 설명, 따옴표 없이.\n\n"
        f"[기사 제목 목록]\n{titles_block}"
    )
    text = _call_gemini(prompt)
    if not text:
        return []
    lines = [line.strip("-•* ").strip() for line in text.splitlines() if line.strip()]
    return lines[:3]


def generate_keyword_tags(titles):
    """오늘 전체 카테고리(종합/경제/부동산/증권) 뉴스 제목에서 핵심 키워드
    5~8개를 추출. 실패/데이터없음 시 빈 리스트 반환."""
    if not titles:
        return []

    titles_block = "\n".join(f"- {t}" for t in titles)
    prompt = (
        "아래는 오늘 수집된 뉴스 제목 목록이다 (종합/경제/부동산/증권 전체를\n"
        "골고루 섞어둠).\n"
        "오늘 가장 핵심적인 키워드를 5~8개 뽑아라.\n"
        "각 키워드는 2~8자 내외의 명사(구)로, 특정 기사 제목을 그대로 베끼지\n"
        "말고 여러 기사를 관통하는 주제어로 뽑아라 (예: 기준금리, 부동산 규제,\n"
        "반도체 수출, AI 투자 등). 특정 인물·기업명 하나만 있는 단독 이슈보다는\n"
        "여러 기사에 걸쳐 반복되는 주제를 우선하라.\n"
        "출력은 키워드만 한 줄에 하나씩, 번호나 설명, 따옴표 없이.\n\n"
        f"[기사 제목 목록]\n{titles_block}"
    )
    text = _call_gemini(prompt)
    if not text:
        return []
    tags = [line.strip("-•* ").strip() for line in text.splitlines() if line.strip()]
    return tags[:8]


def generate_daily_economic_term(titles):
    """오늘 경제 뉴스 제목들에서 가장 이슈된 용어 하나를 뽑아 쉽게 설명.
    실패/데이터없음 시 None 반환."""
    if not titles:
        return None

    titles_block = "\n".join(f"- {t}" for t in titles[:20])
    prompt = (
        "아래는 오늘 수집된 경제 뉴스 제목 목록이다.\n"
        "이 중 오늘 가장 이슈가 된 경제/금융 용어를 딱 하나만 골라라 "
        "(예: 기준금리, 인플레이션, 밸류업, 공매도 등 - 특정 기업명이나 "
        "인명은 고르지 말고 일반적인 경제 개념 용어로 골라라).\n"
        "출력은 아래 형식 정확히 2줄만, 다른 설명이나 번호, 따옴표 없이:\n"
        "용어: (용어 하나)\n"
        "설명: (경제 지식이 없는 일반인도 이해할 수 있게 3문장 이내로 쉽게 설명. "
        "비유를 써도 좋음)\n\n"
        f"[기사 제목 목록]\n{titles_block}"
    )
    text = _call_gemini(prompt)
    if not text:
        return None

    term = ""
    explanation = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("용어:"):
            term = line[len("용어:"):].strip()
        elif line.startswith("설명:"):
            explanation = line[len("설명:"):].strip()

    if not term or not explanation:
        return None
    return {"term": term, "explanation": explanation}


def _extract_signed_percent(index_entry):
    """indices 항목 하나에서 부호 있는 등락률(float)을 추출. 파싱 실패 시 0.0."""
    if not index_entry:
        return 0.0
    raw = (index_entry.get("change_percent") or "")
    raw = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        value = float(raw) if raw else 0.0
    except ValueError:
        value = 0.0
    return -value if index_entry.get("direction") == "down" else value


def generate_stock_commentary(indices, titles, verified_facts=None):
    """코스피/코스닥 등락률이 임계치 이상일 때만 시황 코멘트를 생성.
    평소(변동 적음)에는 None을 반환해 API 호출 자체를 아낀다."""
    kospi = next((i for i in indices if i.get("name") == "코스피"), None)
    kosdaq = next((i for i in indices if i.get("name") == "코스닥"), None)

    kospi_pct = _extract_signed_percent(kospi)
    kosdaq_pct = _extract_signed_percent(kosdaq)

    if abs(kospi_pct) < STOCK_COMMENTARY_THRESHOLD and abs(kosdaq_pct) < STOCK_COMMENTARY_THRESHOLD:
        return None

    titles_block = "\n".join(f"- {t}" for t in titles[:15])
    prompt = (
        f"오늘 코스피는 {kospi_pct:+.2f}%, 코스닥은 {kosdaq_pct:+.2f}% 움직였다.\n"
        "아래 관련 뉴스 제목을 참고해서, 이 움직임의 배경을 2~3문장으로\n"
        "담백하게 설명하라. 투자 조언이나 전망은 하지 말고 사실 설명만.\n"
        f"{SUPERLATIVE_GUIDE}"
        f"{_verified_facts_block(verified_facts)}"
        "따옴표나 번호 없이 문장만 출력하라.\n\n"
        f"[관련 뉴스 제목]\n{titles_block}"
    )
    return _call_gemini(prompt)


def generate_dart_summary(filings):
    """DART 주요사항보고 공시 목록 각각에 쉬운 설명을 붙여 반환.
    실패하거나 응답 개수가 안 맞으면(매칭을 신뢰할 수 없으므로) 설명 없이
    원본 그대로 반환한다."""
    if not filings:
        return filings

    lines_block = "\n".join(
        f"{i + 1}. {f['corp_name']} | {f['report_nm']}" for i, f in enumerate(filings)
    )
    prompt = (
        "아래는 오늘 등록된 국내 상장사 주요사항보고서(공시) 목록이다.\n"
        "각 공시가 일반적으로 무엇을 의미하는지 한 줄(50자 이내)로 쉽게 설명하라.\n"
        "특정 회사에 대한 투자 조언이나 전망은 하지 말고, 이 공시 유형이\n"
        "통상적으로 뜻하는 바만 사실대로 설명하라.\n"
        "출력은 번호를 그대로 유지해서 아래 형식으로만, 입력된 개수와 순서를\n"
        "정확히 지켜라 (그 외 문장은 쓰지 마라):\n"
        "1. (설명)\n2. (설명)\n...\n\n"
        f"[공시 목록]\n{lines_block}"
    )
    text = _call_gemini(prompt)
    if not text:
        return filings

    explanations = {}
    for line in text.splitlines():
        line = line.strip()
        match = re.match(r'^(\d+)[.)]\s*(.+)$', line)
        if match:
            explanations[int(match.group(1))] = match.group(2).strip()

    if len(explanations) != len(filings):
        return filings

    for i, filing in enumerate(filings):
        filing["ai_explanation"] = explanations.get(i + 1, "")
    return filings


# CLAUDE.md "데이터 소스 승인 기준" 4번 원칙(저작권)을 카테고리 리포트
# 프롬프트에 그대로 반영. 모든 카테고리 리포트에 공통 적용.
CATEGORY_REPORT_GUIDE = (
    "너는 여러 언론사·공시·지표 자료의 팩트를 종합해 새로운 관점의 자체\n"
    "리포트를 쓰는 기자다.\n"
    "- 특정 기사 하나의 문장이나 구성을 그대로 따라가지 마라. 여러 자료에서\n"
    "  나온 사실관계만 뽑아 네 방식대로 재구성하라.\n"
    "- 원문 문장을 그대로 옮기지 말고 전부 너의 표현으로 다시 써라.\n"
    "- 숫자(등락률, 가격, 지표값 등)는 반드시 아래 [자료]에 실제로 적혀 있는\n"
    "  값만 그대로 인용하라. 자료에 없는 숫자를 계산하거나 추정하거나\n"
    "  지어내지 마라. 자료의 숫자가 비정상적으로 커 보여도 임의로 줄이거나\n"
    "  보정하지 말고 있는 그대로 인용하라.\n"
    "- 숫자 외의 사건·사실도 자료에 없는 내용은 지어내지 마라. 추측을 사실처럼\n"
    "  단정하지 마라.\n"
    "- 등락률이 절대값 기준 ±5%를 넘는 이례적인 수치가 나오면, 숫자만 던지고\n"
    "  넘어가지 마라. 자료 안에 있는 배경(전일 급락/서킷브레이커, 미국 증시\n"
    "  연동, 특정 기업 실적 등)을 찾아 한 문장 이상으로 반드시 함께 설명하고,\n"
    "  \"이례적\", \"변동성이 큰 장세\" 같은 표현을 써서 독자가 이 수치를\n"
    "  평상시 수준으로 오해하지 않도록 하라. 자료에 배경이 안 보이면\n"
    "  \"배경은 명확히 확인되지 않으나\"처럼 정직하게 밝혀라.\n"
    "- 과거 전체 기록과 비교하는 느낌을 주는 표현은(\"역대\", \"최고\", \"최대\",\n"
    "  \"사상 처음\", \"기록적\" 등 이 유형에 속하는 모든 표현, 목록에 없는\n"
    "  비슷한 표현도 마찬가지) 비교할 과거 기록이 [자료]에 실제로 함께\n"
    "  주어진 경우에만 써라. 오늘 수치가 아무리 크더라도 그것만으로 이런\n"
    "  단정적 표현을 쓰지 마라. 비교 대상 과거 기록이 자료에 없으면 이런\n"
    "  유형의 표현 자체를 쓰지 마라. 다만 아래 [검증된 사실] 섹션이 별도로\n"
    "  주어진 경우에는, 그 안에 명시된 지표·기간에 한해서만 이런 표현을\n"
    "  써도 된다.\n"
)

# 오전판(조간) 전용 추가 지침: 당일 장이 아직 진행 중인 시점에 발행되므로,
# 장중 수치를 마치 하루 최종 등락률처럼 단정하는 문장을 막기 위함.
MORNING_REPORT_GUIDE = (
    "\n[오전판 발행 유의사항]\n"
    "- 이 리포트는 당일 장이 아직 진행 중인 오전에 발행되는 조간판이다.\n"
    "- \"오늘 코스피 OO% 상승 마감\"처럼 당일 장 마감 등락률로 오해될 수 있는\n"
    "  단정적 문장을 쓰지 마라. 그날 마감 결과는 아직 나오지 않았다.\n"
    "- [자료]의 수치가 '전일 마감' 데이터인지 '오늘 오전 현재' 데이터인지\n"
    "  구분해서 명시하라. '오늘 오전 현재' 수치를 언급할 때는 반드시 \"오전\n"
    "  기준\", \"오전 현재\" 같은 시점 한정 표현을 붙여, 그것이 하루 최종\n"
    "  수치가 아니라는 것을 분명히 하라.\n"
    "- 본문 구성은 먼저 전일 마감 상황을 간단히 정리한 뒤, 이어서 오늘 오전에\n"
    "  나온 주요 뉴스·공시 이슈를 정리하는 순서로 써라.\n"
)

# 저녁판(마감) 전용 추가 지침: 당일 장이 끝난 뒤 발행되므로 마감 수치를
# 다뤄도 되지만, 그 시점이 마감 직후라는 걸 분명히 한다.
EVENING_REPORT_GUIDE = (
    "\n[저녁판 발행 유의사항]\n"
    "- 이 리포트는 당일 장 마감 이후 발행되는 마감판이다. [자료]의 수치는\n"
    "  당일 마감(또는 마감에 가까운) 기준 수치로 다뤄도 된다.\n"
)


def generate_category_report(category_label, material_block, report_type="evening", verified_facts=None):
    """오늘의 카테고리별 자료(material_block)를 종합해 제목+본문 리포트를
    생성. report_type은 "morning"(조간, 전일마감+오늘오전 이슈 중심) 또는
    "evening"(마감판, 당일 마감 수치 중심). verified_facts는
    record_verification이 코드로 직접 계산해 확인한 사실 문장 리스트 -
    있으면 그 근거 안에서만 최상급 표현 사용을 허용한다. 자료가 없거나
    실패하면 None."""
    if not material_block or not material_block.strip():
        return None

    edition_guide = MORNING_REPORT_GUIDE if report_type == "morning" else EVENING_REPORT_GUIDE

    prompt = (
        f"{CATEGORY_REPORT_GUIDE}\n"
        f"{edition_guide}\n"
        f"{_verified_facts_block(verified_facts)}\n"
        f"아래는 오늘의 '{category_label}' 관련 자료다. 이 자료들을 종합해서\n"
        "오늘자 이슈 리포트를 작성하라.\n\n"
        "출력은 정확히 아래 두 줄 형식으로만, 그 외 설명은 쓰지 마라:\n"
        "제목: (25자 이내, 기사 제목처럼)\n"
        "본문: (400~600자, 문단 구분 없이 이어서. 자료에 있는 사실 위주로\n"
        "오늘 흐름을 정리)\n\n"
        f"[자료]\n{material_block}"
    )
    text = _call_gemini(prompt, timeout=90)
    if not text:
        return None

    title = ""
    body = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("제목:"):
            title = stripped[len("제목:"):].strip()
        elif stripped.startswith("본문:"):
            body = stripped[len("본문:"):].strip()
        elif body:
            # 본문이 여러 줄로 나뉘어 온 경우 이어붙임
            body += " " + stripped

    if not title or not body:
        return None
    return {"title": title, "body": body}


# 평일 낮 12시대에 그날 올라온 DART 주요사항보고서 전체를 취합한 기사.
# CATEGORY_REPORT_GUIDE(저작권/숫자 인용/최상급 표현 원칙)를 그대로
# 베이스로 깔고, 이 기사 특유의 구조·톤 규칙을 추가한다.
DART_MA_ARTICLE_GUIDE = (
    "\n[기사 구조]\n"
    "1. 헤드라인: 오늘 공시 중 가장 규모가 크거나 주목도 높은 건을\n"
    "   중심으로, 다른 몇 건을 \"~까지\" 식으로 붙여서 쓴다.\n"
    "2. 부제 2줄: 첫 줄은 \"O월O일 다트 공시 총정리\" 형식, 둘째 줄은\n"
    "   헤드라인에 못 넣은 나머지 회사들을 성격별로 묶은 한 줄.\n"
    "3. 리드 문단: \"[날짜] 금융감독원 전자공시시스템 다트(DART)에는\n"
    "   [오늘 제출된 모든 건을 회사명+핵심내용으로 나열], 모두 N건의\n"
    "   주요사항보고서가 제출됐다\" 형식으로 오늘자 전체를 한 문단에 개관.\n"
    "4. 본문: 회사 단위로(또는 성격이 비슷한 여러 회사를 묶어서) 소제목을\n"
    "   나누고, 그 아래 문단에서 금액·비율·날짜·이자율·방법·목적 등\n"
    "   [자료]에 실제로 있는 값만 나열하라. 한 회사가 같은 날 여러 건\n"
    "   공시했으면 인접한 문단으로 묶어라. 소제목 하나에 여러 회사가\n"
    "   들어가도 된다(예: 자기주식취득 여러 건을 한 소제목으로).\n"
    "5. 마무리 문단: 오늘 공시들을 비교·종합하라(규모가 가장 큰 게\n"
    "   무엇인지, 나머지는 대체로 어떤 성격인지). 단, 이 문단을 포함해\n"
    "   기사 전체에서 \"지켜볼 부분이다\", \"우려된다\", \"주목된다\" 같이\n"
    "   필자의 주관적 평가나 전망을 담은 꼬리표는 절대 쓰지 마라. 사실을\n"
    "   서술하는 것으로 문장을 끝내라 - 예를 들어 \"OO는 조달방법을 아직\n"
    "   확정하지 않았다고 공시에 명시했다\"까지만 쓰고, 그 뒤에 \"이 점은\n"
    "   지켜볼 부분이다\" 같은 해석을 덧붙이지 마라.\n"
    "6. [자료]에 상세정보가 없는(회사명+공시제목만 있는) 건은 리드\n"
    "   문단에 간단히 포함시키는 정도로만 다루고, 별도 소제목 문단을\n"
    "   만들지 마라.\n"
    "7. [자료]에 없는 회사 개요·실적·평판 등은 절대 지어내지 마라. 공시\n"
    "   자체에 없는 배경지식(예: 대표이사 이름, 매출 실적)은 [자료]에\n"
    "   그 값이 명시돼 있을 때만 언급하고, 없으면 그 문장 자체를 쓰지\n"
    "   마라.\n"
    "8. 출력은 헤드라인부터 마무리 문단까지 포함한 완성된 기사 텍스트\n"
    "   하나만 내놓아라 - \"제목:\", \"본문:\" 같은 라벨이나 그 밖의\n"
    "   설명은 붙이지 마라.\n"
)


def generate_dart_ma_article(filings, details):
    """오늘 M&A 시그널(filings - dart_ma_signals.json에서 이미 분류된
    것만. "오늘 전체 주요사항보고서"가 아니라 정책·캘린더 M&A 탭이 보여
    주는 것과 정확히 같은 좁은 기준 - run_scheduled.py의
    _build_dart_ma_article() 참고) + dart_filings_detail.json
    (rcept_no -> {"category", "raw_detail"})을 합쳐서 회사별 소제목이
    있는 기사 하나를 생성. 자료가 없거나 호출 실패 시 None.

    filings의 각 항목엔 dart_ma_signals.json 원본 필드(corp_name/
    corp_code/report_nm/rcept_dt/rcept_no/source_url) 외에 호출부에서
    붙여준 "category"(합병_분할/지분인수/영업양수도/주식교환_이전/
    경영권이동_최대주주변경/자기주식)와, 카테고리에 따라 "action"(양수/
    양도/취득/처분 등)이 있을 수 있다 - 둘 다 material_lines에 넣어
    Gemini가 회사별로 소제목을 묶을 때 참고하게 한다."""
    if not filings:
        return None

    material_lines = [f"오늘 제출된 M&A 관련 주요사항보고서 총 {len(filings)}건.\n"]
    for f in filings:
        rcept_no = f.get("rcept_no", "")
        entry = (details or {}).get(rcept_no)
        category = f.get("category", "")
        action = f.get("action", "")
        tag = f"{category}·{action}" if action else category
        material_lines.append(f"[{f.get('corp_name', '')}] {f.get('report_nm', '')} (M&A 유형: {tag})")
        if entry:
            raw = entry.get("raw_detail") or {}
            for key, value in raw.items():
                if not value or key in ("rcept_no",):
                    continue
                material_lines.append(f"  - {key}: {value}")
        else:
            material_lines.append("  (상세정보 없음 - 공시제목만 확인됨)")
        material_lines.append("")

    material_block = "\n".join(material_lines)

    prompt = (
        f"{CATEGORY_REPORT_GUIDE}\n"
        f"{DART_MA_ARTICLE_GUIDE}\n"
        "아래는 오늘 DART(금융감독원 전자공시시스템)에 제출된 M&A 관련\n"
        "(합병·분할, 지분인수, 영업양수도, 주식교환·이전, 경영권이동,\n"
        "자기주식) 주요사항보고서 자료다 - 오늘 제출된 주요사항보고서\n"
        "전체가 아니라 이 M&A 관련 항목만 추린 자료이니, 기사에서 오늘\n"
        "DART 공시 전체를 다루는 것처럼 쓰지 말 것. [기사 구조] 지침에\n"
        "따라 기사를 작성하라. 일부 항목의 필드명이 무엇을 뜻하는지\n"
        "애매하면 그 필드는 기사에 쓰지 말고 넘어가라 - 확실히 이해되는\n"
        "금액·비율·날짜 등만 반영하라.\n\n"
        f"[자료]\n{material_block}"
    )
    return _call_gemini(prompt, timeout=120)
