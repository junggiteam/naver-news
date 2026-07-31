"""오늘의 지수 값/등락률이 실제로 최근 며칠간의 기록 대비 최고·최저·최대
변동폭인지 코드로 직접 계산해서 검증하는 공용 모듈.

daily_reports.py의 카테고리 리포트, dashboard AI 브리핑 파이프라인
(ai_briefing.generate_tab_briefing/generate_stock_commentary) 양쪽에서
공통으로 쓴다. CLAUDE.md "수치 인용 원칙" - "역대/최고/최대/사상 처음/
기록적" 같은 최상급 표현은 실제 비교 가능한 과거 데이터가 있을 때만
허용한다는 원칙을, 사람이 검토하는 대신 여기서 직접 계산해 확인한다.

data/daily_close_archive.json에 장 마감 근처(15:37 슬롯) 스냅샷을
날짜별로 무기한 누적한다. 아직 데이터가 며칠치뿐이면 그만큼만("최근
7일 내 최고" 등) 검증하고, 그보다 긴 기간 비교는 데이터가 쌓일 때까지
자동으로 스킵된다(과장해서 "1년" 등을 주장하지 않음).
"""

import os
import json
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
ARCHIVE_FILE = os.path.join("data", "daily_close_archive.json")

# CLAUDE.md 6번 원칙 - 과거 전체 기록과 비교하는 느낌을 주는 미검증 표현
# 목록. 검증되지 않은 채로 쓰이면 후처리 스캔에서 걸러낸다.
BANNED_SUPERLATIVE_WORDS = ["역대", "최고", "최대", "사상 처음", "기록적"]

DEFAULT_VERIFIABLE_INDEX_NAMES = ("코스피", "코스닥", "코스피200")


def contains_banned_expression(text):
    """임의의 텍스트에 미검증 최상급 표현이 있는지 확인."""
    if not text:
        return False
    return any(word in text for word in BANNED_SUPERLATIVE_WORDS)


def _load_archive():
    if not os.path.exists(ARCHIVE_FILE):
        return {}
    try:
        with open(ARCHIVE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def record_daily_close(indices):
    """오늘 종가(장 마감 근처 스냅샷)를 날짜별로 무기한 누적 기록.
    같은 날 여러 번 호출돼도 그날 키를 덮어써서 최신값을 유지한다."""
    if not indices:
        print("[record_verification] 지수 데이터 없음 - 종가 기록 생략")
        return None

    archive = _load_archive()
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    archive[today_str] = {
        "recorded_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
    }

    os.makedirs("data", exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    print(f"[record_verification] {today_str} 종가 {len(indices)}개 지표를 {ARCHIVE_FILE}에 기록했습니다.")
    return archive


def signed_percent_from_index(index_entry):
    """indices 항목 하나(change_percent, direction)에서 부호 있는
    등락률(float)을 추출. 파싱 실패 시 None."""
    if not index_entry:
        return None
    raw = (index_entry.get("change_percent") or "")
    raw = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if index_entry.get("direction") == "down" else value


def verify_superlative(name, today_value, today_change_pct):
    """name 지표가 daily_close_archive.json에 쌓인 과거 기록(오늘 이전
    날짜) 대비 오늘 값이 최고/최저치인지, 오늘 등락폭(절대값)이 최대인지
    판정. 이 지표의 과거 기록이 하나도 없으면 검증 불가(None)를 반환 -
    호출 측은 이 경우 기존처럼 최상급 표현을 금지해야 한다."""
    archive = _load_archive()
    today_str = datetime.now(KST).strftime("%Y-%m-%d")

    past_values = []
    past_abs_changes = []
    covered_days = 0
    for date_str, day in archive.items():
        if date_str >= today_str:
            continue
        entry = next((i for i in day.get("indices", []) if i.get("name") == name), None)
        if not entry:
            continue
        covered_days += 1
        try:
            past_values.append(float(str(entry.get("value", "")).replace(",", "")))
        except (ValueError, TypeError):
            pass
        pct = signed_percent_from_index(entry)
        if pct is not None:
            past_abs_changes.append(abs(pct))

    if covered_days == 0:
        return None

    is_period_high = bool(past_values) and today_value is not None and today_value > max(past_values)
    is_period_low = bool(past_values) and today_value is not None and today_value < min(past_values)
    is_period_max_move = (
        bool(past_abs_changes) and today_change_pct is not None and abs(today_change_pct) > max(past_abs_changes)
    )

    return {
        "name": name,
        "period_days": covered_days,
        "is_period_high": is_period_high,
        "is_period_low": is_period_low,
        "is_period_max_move": is_period_max_move,
        "verified": is_period_high or is_period_low or is_period_max_move,
    }


def build_verified_facts_lines(results):
    """verify_superlative() 결과 목록(None 포함 가능)을 프롬프트에 넣을
    한글 문장으로 변환. 검증 안 된(None 또는 verified=False) 항목은
    자동으로 빠진다."""
    lines = []
    for r in results:
        if not r or not r.get("verified"):
            continue
        period = f"최근 {r['period_days']}일간 데이터 기준"
        if r["is_period_high"]:
            lines.append(f"- {r['name']}: 오늘 수치가 {period}으로 최고치인 것으로 코드 대조 검증됨")
        if r["is_period_low"]:
            lines.append(f"- {r['name']}: 오늘 수치가 {period}으로 최저치인 것으로 코드 대조 검증됨")
        if r["is_period_max_move"]:
            lines.append(f"- {r['name']}: 오늘 등락폭이 {period}으로 최대치인 것으로 코드 대조 검증됨")
    return lines


def build_verified_facts_for_indices(indices, names=DEFAULT_VERIFIABLE_INDEX_NAMES):
    """indices(예: stock_data['indices'])에서 검증 대상 지표를 찾아
    daily_close_archive.json 기준으로 검증하고, 프롬프트에 바로 넣을 수
    있는 문장 리스트로 변환. 검증 가능한 지표가 없거나 전부 미검증이면
    빈 리스트를 반환한다(=기존처럼 최상급 표현 금지)."""
    results = []
    for idx in indices or []:
        if idx.get("name") not in names:
            continue
        try:
            value = float(str(idx.get("value", "")).replace(",", ""))
        except (ValueError, TypeError):
            continue
        change_pct = signed_percent_from_index(idx)
        results.append(verify_superlative(idx["name"], value, change_pct))
    return build_verified_facts_lines(results)
