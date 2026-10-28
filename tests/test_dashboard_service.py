import pytest
from datetime import datetime, timedelta
from dashboard_service import build_dashboard_context, clear_dashboard_cache


def test_dashboard_service_empty_students():
    clear_dashboard_cache()
    ctx = build_dashboard_context(
        students_loader=lambda: [],
        apple_program_loader=lambda: {"program": {}},
        sync_status_loader=lambda: {"status": "ok"},
    )
    assert ctx["student_count"] == 0
    assert len(ctx["students"]) == 0
    assert len(ctx["upcoming_students"]) == 0
    assert len(ctx["risk_students"]) == 0
    assert ctx["sync_status"]["status"] == "ok"


def test_dashboard_service_groups_and_sorting():
    clear_dashboard_cache()
    today = datetime.now().date()
    d3 = (today + timedelta(days=3)).strftime("%Y-%m-%d")
    d20 = (today + timedelta(days=20)).strftime("%Y-%m-%d")

    mock_students = [
        {
            "id": "s1",
            "name": "即將上課學員",
            "next_lesson": d3,
        },
        {
            "id": "s2",
            "name": "遠期上課學員",
            "next_lesson": d20,
        },
        {
            "id": "s3",
            "name": "未排課學員",
            "next_lesson": "",
        },
    ]

    mock_meta_loader = lambda path: {}
    mock_features_loader = lambda sid: {}
    def mock_predictor(features, next_lesson):
        if next_lesson == d3:
            return {"status": "穩定留存", "risk_level": "low"}
        elif next_lesson == d20:
            return {"status": "冰凍期觀察", "risk_level": "medium"}
        return {"status": "高流失預警", "risk_level": "high"}

    ctx = build_dashboard_context(
        students_loader=lambda: mock_students,
        apple_program_loader=lambda: {"program": {}},
        sync_status_loader=lambda: {"status": "ok"},
        metadata_loader=mock_meta_loader,
        features_analyzer=mock_features_loader,
        status_predictor=mock_predictor,
    )

    assert ctx["student_count"] == 3
    assert len(ctx["upcoming_students"]) == 1
    assert ctx["upcoming_students"][0]["name"] == "即將上課學員"

    assert len(ctx["unscheduled_students"]) == 1
    assert ctx["unscheduled_students"][0]["name"] == "未排課學員"

    assert len(ctx["stable_students"]) == 1
    assert ctx["stable_students"][0]["name"] == "即將上課學員"

    assert len(ctx["freezing_students"]) == 1
    assert ctx["freezing_students"][0]["name"] == "遠期上課學員"

    assert len(ctx["risk_students"]) == 1
    assert ctx["risk_students"][0]["name"] == "未排課學員"


def test_dashboard_service_caching():
    clear_dashboard_cache()
    call_counter = {"count": 0}

    def counter_loader():
        call_counter["count"] += 1
        return [{"id": "s1", "name": "測試學員", "next_lesson": ""}]

    ctx1 = build_dashboard_context(
        students_loader=counter_loader,
        apple_program_loader=lambda: {"program": {}},
        sync_status_loader=lambda: {"status": "ok"},
        metadata_loader=lambda p: {},
        features_analyzer=lambda sid: {},
        status_predictor=lambda f, n: {"status": "穩定留存"},
    )
    assert call_counter["count"] == 1

    # 第 2 次呼叫命中快取，不應重複執行 counter_loader
    ctx2 = build_dashboard_context(
        students_loader=counter_loader,
        apple_program_loader=lambda: {"program": {}},
        sync_status_loader=lambda: {"status": "ok"},
        metadata_loader=lambda p: {},
        features_analyzer=lambda sid: {},
        status_predictor=lambda f, n: {"status": "穩定留存"},
    )
    assert call_counter["count"] == 1
    assert ctx1 == ctx2

