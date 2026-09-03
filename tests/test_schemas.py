"""tests/test_schemas.py
驗證 Pydantic 領域實體與 Schema 契約防護 (Scheme C 驗收測試)。
"""

import unittest
from schemas import StudentProfile, TeachingRecordItem, AppleAttendanceRecord, AppleLedgerItem


class SchemaContractTests(unittest.TestCase):
    def test_student_profile_valid(self):
        profile = StudentProfile(
            id="test-1",
            name="Charlotte",
            first_lesson_date="2023-12-07",
            lessons_count=74,
            current_cycle_lesson=2,
        )
        self.assertEqual(profile.name, "Charlotte")
        self.assertEqual(profile.first_lesson_date, "2023-12-07")

    def test_student_profile_invalid_date_raises(self):
        with self.assertRaises(ValueError):
            StudentProfile(
                id="test-2",
                name="Test Student",
                first_lesson_date="invalid-date-format",
            )

    def test_teaching_record_item(self):
        record = TeachingRecordItem(
            date="2026-09-03",
            title="測試教案",
            filename="Lesson_20260903_Test.md",
            student_name="Test Student",
            word_count=500,
        )
        self.assertEqual(record.date, "2026-09-03")
        self.assertEqual(record.word_count, 500)

    def test_apple_attendance_record(self):
        attendance = AppleAttendanceRecord(
            date="2026-09-03",
            attendees=["Roger老師", "方博敦"],
            cost_per_person=150,
            total_cost=300,
            count=2,
        )
        self.assertEqual(attendance.count, 2)
        self.assertEqual(attendance.total_cost, 300)


if __name__ == "__main__":
    unittest.main()
