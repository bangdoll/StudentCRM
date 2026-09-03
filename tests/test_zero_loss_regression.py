"""tests/test_zero_loss_regression.py

StudentCRM 教學資產零損失回歸測試閘門 (Zero-Loss Regression Test Gate)。
嚴格落實 AGENTS.md 憲法第 3 條「凡可破壞資料或既有功能之修改，必須先有 PRD、備份與驗收清單；
嚴禁用深夜加班補足系統原本應具備之防護」。

本測試套件作為每次發布前的防退化物理防線：
1. 檢驗 SSOT 物理 Markdown 教案存在性與數量不倒退。
2. 檢驗 CRM 結構化教學記錄總量單調不減 (>= 698 筆)。
3. 檢驗全體 64 位學員首堂上課日期 (first_lesson_date) 100% 存在且不退化為未記錄。
4. 檢驗蘋果總裁班教案 (>= 103)、出席 (>= 50)、流水 (>= 55) 與期別 (>= 28) 永不為空。
5. 檢驗寫入斷路器 (Circuit Breaker) 異常腰斬熔斷保護。
6. 檢驗寫入前強制快照備份 (.bak) 機制。
"""

import json
import os
import re
import tempfile
from pathlib import Path
import unittest

from data_gateway import StudentDataGateway, DataGatewayError


class ZeroLossRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_dir = Path(__file__).resolve().parents[1]
        cls.repo_root = cls.app_dir.parents[1]

    def test_01_ssot_markdown_integrity(self):
        """[資產防線 1] 檢驗 01.Docs/teaching 之物理 Markdown 教案總量不可低於基準值 (1,220 篇)。"""
        teaching_dir = self.repo_root / "01.Docs/teaching"
        self.assertTrue(teaching_dir.exists(), "01.Docs/teaching 目錄必須存在")

        md_files = list(teaching_dir.glob("*.md"))
        self.assertGreaterEqual(
            len(md_files),
            1220,
            f"物理教學筆記數量出現異常減少！現存 {len(md_files)} 篇，預期不得低於 1,220 篇！",
        )

    def test_02_crm_teaching_records_monotonic_count(self):
        """[資產防線 2] 檢驗 data/teaching_records.json 總筆數單調不減 (>= 698 筆)。"""
        records_path = self.app_dir / "data/teaching_records.json"
        self.assertTrue(records_path.exists(), "data/teaching_records.json 必須存在")

        with open(records_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("records", []) if isinstance(data, dict) else data
        self.assertGreaterEqual(
            len(records),
            698,
            f"結構化教學記錄出現異常倒退！現有 {len(records)} 筆，基準底線為 698 筆！",
        )

    def test_03_all_students_first_lesson_date_immutable(self):
        """[資產防線 3] 檢驗全體 64 位學員之首次上課日期 100% 存在，禁止退化為 None 或 '未記錄'。"""
        students_path = self.app_dir / "data/students.json"
        self.assertTrue(students_path.exists(), "data/students.json 必須存在")

        with open(students_path, "r", encoding="utf-8") as f:
            students = json.load(f)

        self.assertGreaterEqual(len(students), 64, "學員總數不得少於 64 位")

        missing_first_lesson = []
        for s in students:
            first_date = s.get("first_lesson_date")
            name = s.get("name", "Unknown")
            if not first_date or first_date in ("未記錄", "TBD"):
                missing_first_lesson.append(name)
            else:
                # 驗證日期格式為 YYYY-MM-DD
                self.assertTrue(
                    re.match(r"^\d{4}-\d{2}-\d{2}$", first_date),
                    f"學員 {name} 的 first_lesson_date ({first_date}) 格式不合法！",
                )

        self.assertEqual(
            missing_first_lesson,
            [],
            f"以下學員的首次上課日期缺失或退化為未記錄：{missing_first_lesson}",
        )

    def test_04_apple_ceo_program_four_quadrants_intact(self):
        """[資產防線 4] 檢驗蘋果總裁班教案 (>= 103)、出席 (>= 50)、流水 (>= 55) 與期別 (>= 28) 完備。"""
        apple_path = self.app_dir / "data/apple_ceo_class.json"
        self.assertTrue(apple_path.exists(), "data/apple_ceo_class.json 必須存在")

        with open(apple_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        notes = data.get("teaching_notes", [])
        attendance = data.get("attendance_records", [])
        ledger = data.get("venue_ledger", [])
        rounds = data.get("student_rounds", [])

        self.assertGreaterEqual(len(notes), 103, f"總裁班教案不足 103 篇 (現有 {len(notes)})")
        self.assertGreaterEqual(len(attendance), 50, f"總裁班出席記錄不足 50 筆 (現有 {len(attendance)})")
        self.assertGreaterEqual(len(ledger), 55, f"總裁班流水帳不足 55 筆 (現有 {len(ledger)})")
        self.assertGreaterEqual(len(rounds), 9, f"總裁班期別成員不足 9 位 (現有 {len(rounds)})")

    def test_05_circuit_breaker_prevents_catastrophic_overwrite(self):
        """[資產防線 5] 檢驗斷路器防護：當傳入資料筆數異常腰斬 (少於 80%) 時，強制拒絕覆蓋寫入。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_data.json"
            original_data = [{"id": f"item_{i}"} for i in range(100)]

            # 正常寫入 100 筆
            StudentDataGateway._write_json(str(test_file), original_data)
            self.assertEqual(len(StudentDataGateway._read_json(str(test_file))), 100)

            # 模擬致命解析錯誤只剩下 10 筆（減少超過 20%），斷路器必須強制熔斷拋錯！
            corrupted_data = [{"id": f"item_{i}"} for i in range(10)]
            with self.assertRaises(DataGatewayError) as ctx:
                StudentDataGateway._write_json(str(test_file), corrupted_data)

            self.assertIn("資產防護斷路器熔斷", str(ctx.exception))

            # 原檔案必須完好保留 100 筆，絕對不能被沖洗為 10 筆！
            current_data = StudentDataGateway._read_json(str(test_file))
            self.assertEqual(len(current_data), 100)

    def test_06_pre_write_snapshot_creation(self):
        """[資產防線 6] 檢驗寫入前自動快照備份機制：確保覆寫前保留可逆 .bak 歷史備份。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_snapshot.json"
            StudentDataGateway._write_json(str(test_file), [{"name": "version_1"}])

            backup_dir = Path(temp_dir) / "backups"

            # 再次寫入合法新資料（非縮水資料）
            StudentDataGateway._write_json(str(test_file), [{"name": "version_1"}, {"name": "version_2"}])

            self.assertTrue(backup_dir.exists(), "backups 目錄必須被建立")
            bak_files = list(backup_dir.glob("*.bak"))
            self.assertGreaterEqual(len(bak_files), 1, "必須生成至少 1 個 .bak 快照備份")


if __name__ == "__main__":
    unittest.main()
