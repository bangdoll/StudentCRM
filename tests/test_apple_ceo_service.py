from __future__ import annotations

from datetime import date
import pytest

from apple_ceo_service import (
    add_months,
    extract_session_date,
    normalize_attendee_name,
    preview_apple_ceo_attendance,
    summarize_apple_ceo_program,
    generate_renewal_reminder_message,
)


class TestAddMonths:
    def test_add_months_standard(self):
        d = date(2026, 3, 15)
        assert add_months(d, 4) == date(2026, 7, 15)

    def test_add_months_cross_year(self):
        d = date(2026, 11, 10)
        assert add_months(d, 4) == date(2027, 3, 10)

    def test_add_months_month_end_leap_year(self):
        # 2024 is a leap year
        d = date(2023, 10, 31)
        assert add_months(d, 4) == date(2024, 2, 29)

    def test_add_months_month_end_non_leap_year(self):
        # 2026 is non-leap year
        d = date(2025, 10, 31)
        assert add_months(d, 4) == date(2026, 2, 28)


class TestValidityRules:
    def test_four_month_validity_boundary_not_expired(self):
        """當天剛好在效期當天或效期內，未滿 8 堂不應判定為過期。"""
        fake_program = {
            "attendance_records": [],
            "venue_ledger": [],
            "student_rounds": [
                {
                    "student_name": "測試學員",
                    "aliases": [],
                    "rounds": [
                        {
                            "label": "第 1 輪 (進行中)",
                            "payment_date": "2026-05-01",  # 效期至 2026-09-01
                            "sessions": ["2026-05-05", "2026-05-12", "2026-05-19", "", "", "", "", ""],
                        }
                    ],
                }
            ],
            "tuition_records": [],
        }

        # 模擬今天為 2026-09-01 (效期當天)
        summary = summarize_apple_ceo_program(fake_program, today=date(2026, 9, 1))
        student_round = fake_program["student_rounds"][0]["rounds"][0]
        assert student_round["expiry_date"] == "2026-09-01"
        assert student_round["is_expired"] is False
        assert summary["expired_student_count"] == 0

    def test_four_month_validity_boundary_expired_next_day(self):
        """超過四個月（即使只過期 1 天），未滿 8 堂應判定為過期作廢。"""
        fake_program = {
            "attendance_records": [],
            "venue_ledger": [],
            "student_rounds": [
                {
                    "student_name": "測試學員",
                    "aliases": [],
                    "rounds": [
                        {
                            "label": "第 1 輪 (進行中)",
                            "payment_date": "2026-05-01",  # 效期至 2026-09-01
                            "sessions": ["2026-05-05", "2026-05-12", "2026-05-19", "", "", "", "", ""],
                        }
                    ],
                }
            ],
            "tuition_records": [],
        }

        # 模擬今天為 2026-09-02 (逾期 1 天)
        summary = summarize_apple_ceo_program(fake_program, today=date(2026, 9, 2))
        student_round = fake_program["student_rounds"][0]["rounds"][0]
        assert student_round["expiry_date"] == "2026-09-01"
        assert student_round["is_expired"] is True
        assert summary["expired_student_count"] == 1
        assert student_round["remaining_count"] == 5

    def test_eight_sessions_completed_never_expires(self):
        """若已於四個月內上滿 8 堂圓滿結訓，即使日期超過四個月亦不判定為過期作廢。"""
        fake_program = {
            "attendance_records": [],
            "venue_ledger": [],
            "student_rounds": [
                {
                    "student_name": "圓滿學員",
                    "aliases": [],
                    "rounds": [
                        {
                            "label": "第 1 輪 (結訓)",
                            "payment_date": "2025-01-01",  # 效期至 2025-05-01
                            "sessions": [
                                "2025-01-08", "2025-01-15", "2025-01-22", "2025-02-05",
                                "2025-02-12", "2025-02-19", "2025-02-26", "2025-03-05",
                            ],
                        }
                    ],
                }
            ],
            "tuition_records": [],
        }

        # 模擬今天為 2026-09-02 (遠遠超過 2025-05-01)
        summary = summarize_apple_ceo_program(fake_program, today=date(2026, 9, 2))
        student_round = fake_program["student_rounds"][0]["rounds"][0]
        assert student_round["attended_count"] == 8
        assert student_round["is_expired"] is False
        assert summary["expired_student_count"] == 0

    def test_followup_radar_excludes_expired_students(self):
        """續班雷達（6/8 或 7/8）嚴格排除已過期的歷史學員。"""
        fake_program = {
            "attendance_records": [],
            "venue_ledger": [],
            "student_rounds": [
                {
                    "student_name": "過期學員Andy",
                    "aliases": [],
                    "rounds": [
                        {
                            "label": "歷史梯次",
                            "payment_date": "2024-01-01",  # 效期早已屆滿
                            "sessions": ["2024-01-10", "2024-01-17", "2024-01-24", "2024-01-31",
                                         "2024-02-07", "2024-02-21", "2024-02-28", ""],  # 7 堂
                        }
                    ],
                },
                {
                    "student_name": "活躍學員Roger",
                    "aliases": [],
                    "rounds": [
                        {
                            "label": "第 2 輪 (進行中)",
                            "payment_date": "2026-07-01",  # 效期至 2026-11-01 (未過期)
                            "sessions": ["2026-07-08", "2026-07-15", "2026-07-22", "2026-07-29",
                                         "2026-08-05", "2026-08-12", "2026-08-19", ""],  # 7 堂
                        }
                    ],
                },
            ],
            "tuition_records": [],
        }

        summary = summarize_apple_ceo_program(fake_program, today=date(2026, 9, 2))
        followup_names = [s["student_name"] for s in summary["followup_students"]]
        assert "活躍學員Roger" in followup_names
        assert "過期學員Andy" not in followup_names
        assert summary["followup_student_count"] == 1


class TestAttendancePreview:
    def test_preview_appends_session(self):
        program = {
            "student_rounds": [
                {
                    "student_name": "Lucia",
                    "aliases": ["徐露華"],
                    "rounds": [
                        {
                            "label": "第 1 輪 (進行中)",
                            "sessions": ["2026-08-01", ""],
                        }
                    ],
                }
            ]
        }
        res = preview_apple_ceo_attendance(program, "2026-08-08", "玫瑰客廳", ["徐露華"])
        assert res["summary"]["matched_count"] == 1
        aff = res["affected_rounds"][0]
        assert aff["action"] == "append_session"
        assert aff["after"]["sessions"][1] == "2026-08-08"


class TestReminderMessage:
    def test_generate_renewal_reminder_message(self):
        info = {
            "attended_count": 7,
            "expiry_date": "2026-11-01",
            "days_until_expiry": 60,
        }
        msg = generate_renewal_reminder_message("Roger老師", info)
        assert "Roger老師" in msg
        assert "第 7 堂" in msg
        assert "2026-11-01" in msg
        assert "尚餘 60 天" in msg
        assert "蘋果總裁班・續班預告提醒" in msg
