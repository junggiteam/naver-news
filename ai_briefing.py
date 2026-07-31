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


def generate_tab_briefing(titles, label):
    """탭별 '오늘의 브리핑' 3줄 생성. 실패/데이터없음 시 빈 리스트 반환."""
    if not titles:
        return []

    titles_block = "\n".join(f"- {t}" for t in titles[:20])
    prompt = (
        f"아래는 오늘 수집된 {label} 뉴스 제목 목록이다.\n"
        "이 중 가장 중요한 흐름 3가지를 각각 한 줄(40자 이내)로 요약하라.\n"
        "과장하지 말고 사실 위주로, 기사 제목에 없는 내용은 추측하지 마라.\n"
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


def generate_stock_commentary(indices, titles):
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
)


def generate_category_report(category_label, material_block):
    """오늘의 카테고리별 자료(material_block)를 종합해 제목+본문 리포트를
    생성. 자료가 없거나 실패하면 None."""
    if not material_block or not material_block.strip():
        return None

    prompt = (
        f"{CATEGORY_REPORT_GUIDE}\n"
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
