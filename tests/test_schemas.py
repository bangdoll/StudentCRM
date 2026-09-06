"""tests/test_schemas.py
驗證 Pydantic 領域實體與 Schema 契約防護 (Scheme C 驗收測試)。
"""

import unittest
from schemas import (
    StudentProfile,
    TeachingRecordItem,
    AppleAttendanceRecord,
    AppleLedgerItem,
    APIStatusResponse,
    SyncStatusResponse,
    StudentDetailResponse,
    DigitalManagementListResponse,
    DigitalManagementDetailResponse,
    RadarRefreshResponse,
    CSMFollowupUpdateResponse,
)


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

    def test_api_status_response_valid(self):
        resp = APIStatusResponse(status="ok", message="Operation successful")
        self.assertEqual(resp.status, "ok")
        self.assertEqual(resp.message, "Operation successful")

    def test_sync_status_response_valid(self):
        resp = SyncStatusResponse(
            engine="supabase",
            source="students",
            cache_path="/tmp/cache.json",
            last_error="",
            checked_at="2026-09-06T12:00:00Z",
        )
        self.assertEqual(resp.engine, "supabase")
        self.assertEqual(resp.source, "students")

    def test_student_detail_response_valid(self):
        resp = StudentDetailResponse(
            status="ok",
            student_id="student-1",
            student={"name": "Charlotte"},
            features={"days_since_last_lesson": 5},
            prediction={"status": "active"},
            sync={"engine": "local"},
        )
        self.assertEqual(resp.status, "ok")
        self.assertEqual(resp.student_id, "student-1")
        self.assertEqual(resp.student["name"], "Charlotte")

    def test_digital_management_list_response_valid(self):
        resp = DigitalManagementListResponse(
            status="ok",
            count=1,
            students=[
                {
                    "id": "digital-kelly",
                    "name": "Kelly Woo",
                    "current_lesson": 4,
                    "lessons": [],
                    "notes": [],
                }
            ],
            calendar_event_count=10,
            local_note_count=5,
            teaching_note_count=15,
        )
        self.assertEqual(resp.count, 1)
        self.assertEqual(len(resp.students), 1)
        self.assertEqual(resp.students[0].name, "Kelly Woo")

    def test_radar_refresh_and_followup_schemas(self):
        refresh = RadarRefreshResponse(
            success=True,
            generated_at="2026-09-06T12:00:00Z",
            items_count=64,
        )
        self.assertTrue(refresh.success)
        self.assertEqual(refresh.items_count, 64)

        followup = CSMFollowupUpdateResponse(
            success=True,
            student_id="student-1",
            followup={"status": "contacted", "coach_notes": "已電聯關懷"},
        )
        self.assertTrue(followup.success)
        self.assertEqual(followup.student_id, "student-1")


if __name__ == "__main__":
    unittest.main()
