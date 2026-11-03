import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import ai_briefing
import daily_reports
import run_scheduled


class DailyReportsRecoveryTests(unittest.TestCase):
    def test_empty_edition_does_not_replace_published_report(self):
        with tempfile.TemporaryDirectory() as temp:
            reports_path = Path(temp) / "daily_reports.json"
            archive_path = Path(temp) / "archive.json"
            previous = {"reports": {"evening": {"generated_at": "2026-11-02 17:46:17"}}}
            reports_path.write_text(json.dumps(previous), encoding="utf-8")
            with patch.object(daily_reports, "REPORTS_FILE", str(reports_path)), patch.object(
                daily_reports, "ARCHIVE_FILE", str(archive_path)
            ):
                with self.assertRaisesRegex(RuntimeError, "정상 카테고리 0/6개"):
                    daily_reports._save_edition("morning", "test", {c: None for c in daily_reports.CATEGORIES})
            self.assertEqual(json.loads(reports_path.read_text(encoding="utf-8")), previous)
            self.assertFalse(archive_path.exists())

    def test_blank_marked_edition_is_retried_after_cooldown(self):
        now = datetime(2026, 11, 3, 14, 0, tzinfo=run_scheduled.KST)
        marker = {"daily_report_morning": now.isoformat()}
        with patch.object(daily_reports, "has_valid_published_edition", return_value=False):
            self.assertIn("daily_report_morning", run_scheduled.find_due_report_slots(now, marker))
            marker["daily_report_morning_last_failure"] = (now - timedelta(minutes=15)).isoformat()
            self.assertNotIn("daily_report_morning", run_scheduled.find_due_report_slots(now, marker))
            self.assertIn(
                "daily_report_morning",
                run_scheduled.find_due_report_slots(now + timedelta(minutes=16), marker),
            )

    def test_gemini_503_is_retried_and_success_clears_error(self):
        unavailable = Mock(status_code=503, text='{"error":"UNAVAILABLE"}')
        unavailable.raise_for_status.side_effect = requests.HTTPError("503")
        available = Mock(status_code=200)
        available.raise_for_status.return_value = None
        available.json.return_value = {"candidates": [{"content": {"parts": [{"text": "  완료  "}]}}]}
        with patch.object(ai_briefing, "GEMINI_API_KEY", "test-key"), patch.object(
            ai_briefing.requests, "post", side_effect=[unavailable, available]
        ) as post, patch.object(ai_briefing.time, "sleep") as sleep:
            self.assertEqual(ai_briefing._call_gemini("test"), "완료")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(2)
        self.assertIsNone(ai_briefing.LAST_ERROR)


if __name__ == "__main__":
    unittest.main()
