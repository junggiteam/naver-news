"""(임시 검증용) 과장된 '역대/최고' 표현 금지 지침 반영 확인. 확인 후 삭제."""
import daily_reports
import ai_briefing

stock_data = daily_reports._load_json("data/stock_news.json")
macro_data = daily_reports._load_json("data/macro_indicators.json")
material = daily_reports._build_market_material(stock_data, macro_data)

report = ai_briefing.generate_category_report("시황", material)
print("=== 생성된 리포트 ===")
if report:
    print("제목:", report["title"])
    print("본문:", report["body"])
    banned = ["역대", "최고", "최대", "사상 처음"]
    found = [w for w in banned if w in report["title"] or w in report["body"]]
    print()
    print("금지 표현 발견 여부:", found if found else "없음 (통과)")
else:
    print("(생성 실패)")
