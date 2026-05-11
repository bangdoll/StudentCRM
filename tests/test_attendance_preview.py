import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from main import app, preview_apple_ceo_attendance


class AttendancePreviewTests(unittest.TestCase):
    def test_preview_attendance_appends_first_empty_session(self):
        program_data = {
            "student_rounds": [{
                "student_name": "Roger老師",
                "rounds": [{
                    "label": "最新梯次 (進行中)",
                    "payment_status": "進度",
                    "sessions": ["2026-03-26", "", "", "", "", "", "", ""],
                }],
            }]
        }

        preview = preview_apple_ceo_attendance(
            program_data=program_data,
            date="2026-05-14",
            venue="玫瑰客廳",
            attendees=["Roger老師"],
        )

        self.assertEqual(preview["summary"]["matched_count"], 1)
        self.assertEqual(preview["affected_rounds"][0]["action"], "append_session")
        self.assertEqual(preview["affected_rounds"][0]["after"]["sessions"][1], "2026-05-14")
        self.assertEqual(program_data["student_rounds"][0]["rounds"][0]["sessions"][1], "")

    def test_preview_attendance_reports_unmatched_attendee(self):
        preview = preview_apple_ceo_attendance(
            program_data={"student_rounds": []},
            date="2026-05-14",
            venue="玫瑰客廳",
            attendees=["不存在的學員"],
        )

        self.assertEqual(preview["summary"]["warning_count"], 1)
        self.assertIn("找不到班務學員", preview["warnings"][0])

    def test_preview_endpoint_is_preview_only(self):
        client = TestClient(app)
        response = client.post(
            "/api/program/apple-ceo/preview/attendance",
            json={
                "date": "2026-05-14",
                "venue": "玫瑰客廳",
                "attendees": ["Roger老師"],
                "note": "預覽測試",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "preview_only")
        self.assertFalse(payload["will_write"])
        self.assertTrue(payload["requires_human_confirmation"])

    def test_program_page_exposes_attendance_preview_panel(self):
        client = TestClient(app)
        response = client.get("/program/apple-ceo")

        self.assertEqual(response.status_code, 200)
        self.assertIn("預覽新增上課紀錄", response.text)
        self.assertIn("attendancePreviewForm", response.text)


if __name__ == "__main__":
    unittest.main()
