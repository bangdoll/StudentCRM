import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_gateway import StudentDataGateway
from main import parse_frontmatter_metadata


class StudentDataGatewayTests(unittest.TestCase):
    def test_local_engine_reads_students_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "OpenClaw/Data"
            data_dir.mkdir(parents=True)
            (data_dir / "students.json").write_text(
                json.dumps([{"id": "s1", "name": "測試學員"}], ensure_ascii=False),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"STUDENTCRM_DATA_BACKEND": "local"}, clear=False):
                gateway = StudentDataGateway(str(root))
                students = gateway.load_students()

            self.assertEqual(students[0]["name"], "測試學員")
            self.assertEqual(gateway.status()["engine"], "local")

    def test_local_engine_returns_empty_when_local_files_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"STUDENTCRM_DATA_BACKEND": "local"}, clear=False):
                gateway = StudentDataGateway(tmp)
                students = gateway.load_students()
                program = gateway.load_apple_ceo_program()

            self.assertEqual(students, [])
            self.assertEqual(gateway.status()["engine"], "unavailable")
            self.assertEqual(program["program"]["id"], "apple-ceo")
            self.assertEqual(program["student_rounds"], [])

    def test_supabase_engine_falls_back_to_local_when_env_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "OpenClaw/Data"
            data_dir.mkdir(parents=True)
            (data_dir / "students.json").write_text(
                json.dumps([{"id": "s2", "name": "離線學員"}], ensure_ascii=False),
                encoding="utf-8",
            )

            env = {
                "STUDENTCRM_DATA_BACKEND": "supabase",
                "SUPABASE_URL": "",
                "SUPABASE_SERVICE_ROLE_KEY": "",
                "SUPABASE_ANON_KEY": "",
            }
            with patch.dict(os.environ, env, clear=False):
                gateway = StudentDataGateway(str(root))
                students = gateway.load_students()

            status = gateway.status()
            self.assertEqual(students[0]["name"], "離線學員")
            self.assertEqual(status["engine"], "local_fallback")
            self.assertIn("Supabase", status["last_error"])

    def test_local_engine_reads_apple_ceo_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "OpenClaw/Data"
            data_dir.mkdir(parents=True)
            (data_dir / "apple_ceo_class.json").write_text(
                json.dumps({"program": {"id": "apple-ceo", "name": "測試班"}, "venue": {}, "student_rounds": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"STUDENTCRM_DATA_BACKEND": "local"}, clear=False):
                gateway = StudentDataGateway(str(root))
                payload = gateway.load_apple_ceo_program()

            self.assertEqual(payload["program"]["name"], "測試班")

    def test_supabase_engine_composes_apple_ceo_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StudentCRM/cache").mkdir(parents=True)

            table_rows = {
                "apple_programs": [{
                    "id": "apple-ceo",
                    "name": "雲端班",
                    "round_size": 8,
                    "price_per_student": 5000,
                }],
                "apple_venues": [{
                    "name": "玫瑰客廳",
                    "cost_per_person": 150,
                }],
                "apple_attendance_records": [],
                "apple_venue_ledger": [{
                    "id": "ledger-1",
                    "date": "2026-04-09",
                    "type": "收入",
                    "amount": 1000,
                    "balance_after": 1000,
                }],
                "apple_student_rounds": [{
                    "student_name": "Roger老師",
                    "label": "最新梯次 (進行中)",
                    "payment_status": "進度",
                    "sessions": ["2026-03-26", "", "", "", "", "", "", ""],
                }],
            }

            env = {
                "STUDENTCRM_DATA_BACKEND": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": "test-key",
                "SUPABASE_SERVICE_ROLE_KEY": "",
            }
            with patch.dict(os.environ, env, clear=False):
                gateway = StudentDataGateway(str(root))
                with patch.object(gateway, "_load_supabase_table", side_effect=lambda table, query="select=*": table_rows[table]):
                    payload = gateway.load_apple_ceo_program()

            self.assertEqual(payload["program"]["name"], "雲端班")
            self.assertEqual(payload["venue"]["name"], "玫瑰客廳")
            self.assertEqual(payload["venue_ledger"][0]["balance_after"], 1000)
            self.assertEqual(payload["student_rounds"][0]["student_name"], "Roger老師")

    def test_parse_frontmatter_metadata_without_pyyaml(self):
        metadata = parse_frontmatter_metadata(
            """
lessons_count: 12
first_lesson_date: "2026-01-01"
hardware:
  - MacBook
  - iPhone
            """
        )

        self.assertEqual(metadata["lessons_count"], 12)
        self.assertEqual(metadata["first_lesson_date"], "2026-01-01")
        self.assertEqual(metadata["hardware"], ["MacBook", "iPhone"])


if __name__ == "__main__":
    unittest.main()
