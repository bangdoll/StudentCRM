import pytest
from pathlib import Path

from digital_management_service import (
    build_digital_management_profiles,
    get_digital_management_student_profile,
    parse_digital_management_title,
    digital_student_id,
)


def test_get_digital_management_student_profile_taoyuan():
    # 測試單一學員快速深模組查詢介面
    taoyuan_id = "36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95"
    profile = get_digital_management_student_profile(taoyuan_id, include_heptabase=False)
    assert profile is not None
    assert profile["id"] == taoyuan_id
    assert profile["name"] == "桃園"
    assert len(profile["notes"]) == 31
    assert len(profile["lessons"]) >= 31


def test_get_digital_management_student_profile_not_found():
    profile = get_digital_management_student_profile("non-existent-student-id", include_heptabase=False)
    assert profile is None


def test_get_digital_management_student_profile_matches_bulk_build():
    taoyuan_id = "36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95"
    single = get_digital_management_student_profile(taoyuan_id, include_heptabase=False)
    bulk = build_digital_management_profiles(include_heptabase=False)
    bulk_match = next((s for s in bulk.get("students", []) if s.get("id") == taoyuan_id), None)

    assert single is not None
    assert bulk_match is not None
    assert single["name"] == bulk_match["name"]
    assert len(single["notes"]) == len(bulk_match["notes"])
    assert single["current_lesson"] == bulk_match["current_lesson"]
    assert single["latest_lesson_date"] == bulk_match["latest_lesson_date"]
