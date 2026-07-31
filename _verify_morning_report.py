"""(임시 검증용) 오전판(조간) 리포트 생성 확인. 확인 후 삭제."""
import daily_reports
import ai_briefing

stock_data = daily_reports._load_json("data/stock_news.json")
history = daily_reports._load_json("data/stock_index_history.json")
dart_data = daily_reports._load_json("data/dart_filings.json")

for category, material in [
    ("시황", daily_reports._build_market_material_morning(stock_data, history)),
    ("투자", daily_reports._build_investment_material_morning(stock_data)),
    ("기업", daily_reports._build_corporate_material(stock_data, dart_data)),
]:
    report = ai_briefing.generate_category_report(category, material, report_type="morning")
    print(f"=== {category} (오전판) ===")
    if report:
        print("제목:", report["title"])
        print("본문:", report["body"])
    else:
        print("(생성 실패)")
    print()
