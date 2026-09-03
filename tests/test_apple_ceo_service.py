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

    def test_eight_sessions_completed_triggers_followup_reminder(self):
        """最新梯次已滿 8 堂之學員（如方博敦＝方醫師），應納入續班提醒名單並產出完訓恭賀續班訊息。"""
        fake_program = {
            "attendance_records": [],
            "venue_ledger": [],
            "student_rounds": [
                {
                    "student_name": "方博敦",
                    "aliases": ["方醫師", "方柏敦"],
                    "rounds": [
                        {
                            "label": "2026 夏季梯次 (已結訓)",
                            "payment_date": "2026-06-25",
                            "sessions": [
                                "2026-06-25", "2026-07-02", "2026-07-09", "2026-07-16",
                                "2026-07-23", "2026-07-30", "2026-08-06", "2026-08-27",
                            ],
                        }
                    ],
                }
            ],
            "tuition_records": [],
        }

        summary = summarize_apple_ceo_program(fake_program, today=date(2026, 9, 2))
        followup_names = [s["student_name"] for s in summary["followup_students"]]
        assert "方博敦" in followup_names
        assert summary["followup_student_count"] == 1

        fang = summary["followup_students"][0]
        assert fang["attended_count"] == 8
        assert "圓滿完成本輪 8 堂課程" in fang["reminder_message"]
        assert "續班" in fang["reminder_message"]


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


class TestActiveStudentsSummary:
    def test_active_students_contains_accumulated_counts(self):
        """驗證 active_students 必定包含 active_count（進行中筆數）與 total_attended（累計總堂數）。"""
        program = {
            "attendance_records": [],
            "venue_ledger": [],
            "tuition_records": [],
            "student_rounds": [
                {
                    "student_name": "劉邦寧",
                    "aliases": [],
                    "rounds": [
                        {
                            "label": "最新梯次 (進行中)",
                            "payment_date": "2026-08-01",
                            "sessions": ["2026-08-06", "2026-08-13", "2026-08-20"],
                        },
                        {
                            "label": "2026 春夏梯次 (已結訓)",
                            "payment_date": "2026-03-01",
                            "sessions": ["2026-03-05", "2026-03-12", "2026-03-19", "2026-03-26",
                                         "2026-04-02", "2026-04-09", "2026-04-16", "2026-04-23"],
                        },
                    ],
                }
            ],
        }
        summary = summarize_apple_ceo_program(program)
        active_students = summary["active_students"]
        assert len(active_students) == 1
        student = active_students[0]
        assert student["student_name"] == "劉邦寧"
        assert student["active_count"] == 1
        assert student["total_attended"] == 11  # 3 + 8 = 11 堂
        assert student["attended_count"] == 3   # 當期 3 堂


class TestCanonicalOrderAndLayout:
    def test_canonical_student_order(self):
        from data_gateway import CANONICAL_APPLE_STUDENT_ORDER, sort_apple_student_rounds

        rounds = [
            {"student_name": "Andy哥"},
            {"student_name": "王太太"},
            {"student_name": "方博敦"},
            {"student_name": "Roger老師"},
            {"student_name": "林永青"},
            {"student_name": "Lucia"},
            {"student_name": "劉邦寧"},
            {"student_name": "陳總"},
            {"student_name": "方敏穎"},
        ]
        sorted_rounds = sort_apple_student_rounds(rounds)
        names = [r["student_name"] for r in sorted_rounds]
        expected = [
            "方博敦",
            "劉邦寧",
            "Roger老師",
            "Lucia",
            "王太太",
            "方敏穎",
            "林永青",
            "陳總",
            "Andy哥",
        ]
        assert names == expected
        assert names[0] == "方博敦"
        assert names[1] == "劉邦寧"
        assert names[2] == "Roger老師"
        assert names[3] == "Lucia"
        assert names[4] == "王太太"
        assert names[-1] == "Andy哥"

    def test_program_apple_ceo_page_layout_order(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/program/apple-ceo")
        assert response.status_code == 200
        html = response.text

        # 1. 課堂教學紀錄在最上面
        idx_notes = html.find('id="teachingNotesSection"')
        # 2. 上課日期的記錄在教學筆記下面
        idx_attendance = html.find('id="attendanceSection"')
        # 3. 學員進度在下面
        idx_students = html.find('id="studentsSection"')
        # 4. 歷史/過期學員分隔線
        idx_divider = html.find('class="round-divider-section"')

        assert idx_notes != -1
        assert idx_attendance != -1
        assert idx_students != -1
        assert idx_divider != -1

        assert idx_notes < idx_attendance < idx_students < idx_divider

        # 驗證學員卡片順序：方博敦在前，Andy哥在最後面
        idx_fang = html.find("方博敦")
        idx_andy = html.find("Andy哥")
        assert idx_fang != -1
        assert idx_andy != -1
        assert idx_fang < idx_andy
        assert idx_divider < idx_andy  # Andy哥在分隔線下方
