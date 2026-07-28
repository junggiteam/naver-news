"""Gemini API를 이용한 탭별 '오늘의 브리핑' / 증권 시황 코멘트 생성 모듈.

GEMINI_API_KEY 환경변수가 없거나 API 호출이 실패해도 예외를 던지지 않고
None/빈 리스트를 반환한다. 크롤링 자체(핵심 기능)는 AI 기능과 완전히
분리되어 있어서, 이 모듈이 통째로 실패해도 뉴스 목록 표시에는 영향이 없다.
"""

import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# 코스피/코스닥 중 하나라도 이 이상 움직이면 시황 코멘트 생성
STOCK_COMMENTARY_THRESHOLD = 1.5


def _call_gemini(prompt, timeout=30):
    if not GEMINI_API_KEY:
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
        print(f"[ai_briefing] Gemini 호출 실패: {e}")
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
