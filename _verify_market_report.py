"""(임시 검증용) 시황 카테고리 리포트만 다시 생성해서 확인. 확인 후 삭제."""
import daily_reports
import ai_briefing

stock_data = daily_reports._load_json("data/stock_news.json")
macro_data = daily_reports._load_json("data/macro_indicators.json")
material = daily_reports._build_market_material(stock_data, macro_data)

report = ai_briefing.generate_category_report("시황", material)
print("=== 원본 코스피/코스닥 change_percent ===")
for idx in stock_data.get("indices", []):
    if idx["name"] in ("코스피", "코스닥", "코스피200"):
        print(idx["name"], idx["change_percent"])

print()
print("=== 생성된 리포트 ===")
if report:
    print("제목:", report["title"])
    print("본문:", report["body"])
else:
    print("(생성 실패)")
