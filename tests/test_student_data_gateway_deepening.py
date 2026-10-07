import pytest
from unittest.mock import patch
from data_gateway import StudentDataGateway


def test_normalize_student_promotes_raw_fields():
    gateway = StudentDataGateway(base_dir=".")
    
    raw_student = {
        "id": "test-student-1",
        "name": "陳萱玲",
        "lessons_count": 8,
        "raw": {
            "current_cycle_lesson": 8,
            "cycle_size": 8,
            "completion_status": "completed",
            "completion_note": "第 1 輪 8 堂課圓滿完成",
            "first_lesson_date": "2026-08-01",
        }
    }
    
    normalized = gateway.normalize_student(raw_student)
    
    assert normalized["current_cycle_lesson"] == 8
    assert normalized["cycle_size"] == 8
    assert normalized["completion_status"] == "completed"
    assert normalized["completion_note"] == "第 1 輪 8 堂課圓滿完成"
    assert normalized["first_lesson_date"] == "2026-08-01"


def test_normalize_student_derives_cycle_lesson_from_lessons_count():
    gateway = StudentDataGateway(base_dir=".")
    
    s_16 = {"id": "s-16", "name": "學生A", "lessons_count": 16}
    norm_16 = gateway.normalize_student(s_16)
    assert norm_16["current_cycle_lesson"] == 8
    assert norm_16["cycle_size"] == 8

    s_7 = {"id": "s-7", "name": "學生B", "lessons_count": 7}
    norm_7 = gateway.normalize_student(s_7)
    assert norm_7["current_cycle_lesson"] == 7

    s_0 = {"id": "s-0", "name": "學生C", "lessons_count": 0}
    norm_0 = gateway.normalize_student(s_0)
    assert norm_0["current_cycle_lesson"] == 1


def test_get_student_profile_by_id_and_token():
    gateway = StudentDataGateway(base_dir=".")
    
    mock_students = [
        {
            "id": "uuid-1234",
            "name": "測試學員",
            "public_token": "token-abcd",
            "aliases": ["小測"],
            "lessons_count": 3,
            "raw": {
                "current_cycle_lesson": 3,
                "cycle_size": 8,
            }
        }
    ]
    
    with patch.object(gateway, "load_students", return_value=mock_students):
        # 1. 依 ID 查
        p1 = gateway.get_student_profile("uuid-1234")
        assert p1 is not None
        assert p1["name"] == "測試學員"
        assert p1["current_cycle_lesson"] == 3
        
        # 2. 依 Token 查
        p2 = gateway.get_student_profile("token-abcd")
        assert p2 is not None
        assert p2["id"] == "uuid-1234"
        
        # 3. 查無資料
        p3 = gateway.get_student_profile("non-existent")
        assert p3 is None
