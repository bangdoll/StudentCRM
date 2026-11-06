import sys
from unittest.mock import patch
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from main import app, preview_apple_ceo_attendance
from apple_ceo_service import apply_apple_ceo_attendance


class AttendancePreviewTests(unittest.TestCase):
    def test_preview_includes_venue_fee_and_stable_token(self):
        program_data = {
            "venue": {"name": "玫瑰客廳", "cost_per_person": 150},
            "attendance_records": [],
            "venue_ledger": [{"date": "2026-01-01", "balance_after": 1000}],
            "student_rounds": [{
                "student_name": "Roger老師",
                "rounds": [{"label": "最新梯次 (進行中)", "sessions": ["2026-01-01"] + [""] * 7}],
            }],
        }

        preview = preview_apple_ceo_attendance(
            program_data=program_data,
            date="2026-05-14",
            venue="玫瑰客廳",
            attendees=["Roger老師"],
        )

        self.assertEqual(preview["venue_fee"]["amount"], -150)
        self.assertEqual(preview["venue_fee"]["balance_after"], 850)
        self.assertEqual(len(preview["preview_token"]), 64)

    def test_apply_writes_attendance_ledger_round_and_is_idempotent(self):
        program_data = {
            "program": {"id": "apple-ceo"},
            "venue": {"name": "玫瑰客廳", "cost_per_person": 150},
            "attendance_records": [],
            "venue_ledger": [{"date": "2026-01-01", "balance_after": 1000}],
            "student_rounds": [{
                "student_name": "Roger老師",
                "rounds": [{"label": "最新梯次 (進行中)", "sessions": ["2026-01-01"] + [""] * 7}],
            }],
        }
        preview = preview_apple_ceo_attendance(program_data, "2026-05-14", "玫瑰客廳", ["Roger老師"])

        result = apply_apple_ceo_attendance(
            program_data,
            "2026-05-14",
            "玫瑰客廳",
            ["Roger老師"],
            preview_token=preview["preview_token"],
        )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(len(program_data["attendance_records"]), 1)
        self.assertEqual(program_data["venue_ledger"][-1]["balance_after"], 850)
        self.assertEqual(program_data["student_rounds"][0]["rounds"][0]["sessions"][1], "2026-05-14")

        repeat_preview = preview_apple_ceo_attendance(program_data, "2026-05-14", "玫瑰客廳", ["Roger老師"])
        repeat = apply_apple_ceo_attendance(
            program_data,
            "2026-05-14",
            "玫瑰客廳",
            ["Roger老師"],
            preview_token=repeat_preview["preview_token"],
        )
        self.assertEqual(repeat["status"], "idempotent")
        self.assertEqual(len(program_data["attendance_records"]), 1)

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

    def test_preview_attendance_matches_aliases(self):
        program_data = {
            "student_rounds": [{
                "student_name": "方柏敦",
                "aliases": ["方醫師"],
                "rounds": [{
                    "label": "最新梯次 (進行中)",
                    "payment_status": "進度",
                    "sessions": ["2026-05-14", "", "", "", "", "", "", ""],
                }],
            }]
        }

        preview = preview_apple_ceo_attendance(
            program_data=program_data,
            date="2026-05-21",
            venue="玫瑰客廳",
            attendees=["方醫師"],
        )

        self.assertEqual(preview["summary"]["matched_count"], 1)
        self.assertEqual(preview["affected_rounds"][0]["student_name"], "方柏敦")

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
        self.assertEqual(len(payload["preview_token"]), 64)
        self.assertIn("venue_fee", payload)

    def test_apply_endpoint_requires_preview_and_returns_receipt(self):
        program_data = {
            "program": {"id": "apple-ceo"},
            "venue": {"name": "玫瑰客廳", "cost_per_person": 150},
            "attendance_records": [],
            "venue_ledger": [{"date": "2026-01-01", "balance_after": 1000}],
            "student_rounds": [{
                "student_name": "Roger老師",
                "rounds": [{"label": "最新梯次 (進行中)", "sessions": ["2026-01-01"] + [""] * 7}],
            }],
        }

        class FakeGateway:
            backend = "local"

            def persist_apple_ceo_session(self, payload):
                return {"backend": "local", "readback": {"local_data": True, "mirror": True}}

        client = TestClient(app)
        with patch("main.load_apple_ceo_program", return_value=program_data), patch("main.student_gateway", FakeGateway()):
            preview_response = client.post(
                "/api/program/apple-ceo/preview/attendance",
                json={"date": "2026-05-14", "venue": "玫瑰客廳", "attendees": ["Roger老師"], "note": "測試寫入"},
            )
            preview = preview_response.json()
            apply_response = client.post(
                "/api/program/apple-ceo/apply/attendance",
                json={
                    "date": "2026-05-14",
                    "venue": "玫瑰客廳",
                    "attendees": ["Roger老師"],
                    "note": "測試寫入",
                    "preview_token": preview["preview_token"],
                    "confirm": True,
                },
            )

        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(apply_response.json()["status"], "applied")
        self.assertTrue(apply_response.json()["receipt"]["persistence"]["readback"]["local_data"])

    def test_program_page_exposes_attendance_preview_panel(self):
        client = TestClient(app)
        response = client.get("/program/apple-ceo")

        self.assertEqual(response.status_code, 200)
        self.assertIn("預覽新增上課紀錄", response.text)
        self.assertIn("attendancePreviewForm", response.text)


if __name__ == "__main__":
    unittest.main()
