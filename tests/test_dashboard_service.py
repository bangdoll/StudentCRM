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


def test_build_home_context_enriches_and_caches():
    from dashboard_service import build_home_context, clear_dashboard_cache

    clear_dashboard_cache()
    call_counter = {"count": 0}

    def mock_students_loader():
        call_counter["count"] += 1
        return [
            {
                "id": "s1",
                "name": "測試首頁學員",
                "first_lesson_date": "2026-09-01",
                "latest_date": "2026-10-20",
                "lessons_count": 5,
                "next_lesson": "2026-11-01",
            }
        ]

    class DummyGateway:
        def get_effectiveness_radar_data(self):
            return {"items": [{"student_id": "s1"}], "summary": {}}

    ctx1 = build_home_context(
        students_loader=mock_students_loader,
        apple_program_loader=lambda: {"program": {"name": "蘋果總裁班"}},
        data_gateway=DummyGateway(),
        metadata_loader=lambda p: {},
        cloud_meta_builder=lambda s: {"first_lesson_date": "未記錄", "last_lesson_date": "未記錄", "lessons_count": 0},
        features_analyzer=lambda sid, target_student=None: {"days_since_last_lesson": 5},
        status_predictor=lambda f, n: {"status": "穩定留存", "risk_level": "low"},
    )
    assert call_counter["count"] == 1
    assert len(ctx1["students"]) == 1
    assert ctx1["students"][0]["meta"]["first_lesson_date"] == "2026-09-01"
    assert ctx1["students"][0]["meta"]["last_lesson_date"] == "2026-10-20"
    assert ctx1["students"][0]["meta"]["lessons_count"] == 5
    assert ctx1["apple_program"]["name"] == "蘋果總裁班"
    assert "renewal_radar" in ctx1
    assert "effectiveness_radar" in ctx1

    # 第二次呼叫應命中快取
    ctx2 = build_home_context(
        students_loader=mock_students_loader,
        apple_program_loader=lambda: {"program": {"name": "蘋果總裁班"}},
        data_gateway=DummyGateway(),
        metadata_loader=lambda p: {},
        cloud_meta_builder=lambda s: {},
        features_analyzer=lambda sid, target_student=None: {},
        status_predictor=lambda f, n: {"status": "穩定留存"},
    )
    assert call_counter["count"] == 1
    assert ctx1 == ctx2


def test_build_apple_ceo_view_context():
    from apple_ceo_service import build_apple_ceo_view_context

    program_data = {
        "program": {"name": "蘋果總裁班"},
        "venue": {"name": "玫瑰客廳"},
        "active_participants": ["Roger老師"],
        "attendance_records": [],
        "venue_ledger": [],
        "student_rounds": [],
        "tuition_records": [],
        "teaching_notes": [{"title": "測試筆記"}],
        "legacy_note": "備註",
    }
    students = [
        {"id": "roger-1", "name": "Roger 黃凱亮", "aliases": ["Roger老師"]},
    ]
    ctx = build_apple_ceo_view_context(
        program_data=program_data,
        students=students,
        token="apple-ceo",
        is_student_view=True,
    )
    assert ctx["program"]["name"] == "蘋果總裁班"
    assert ctx["token"] == "apple-ceo"
    assert ctx["is_student_view"] is True
    assert "Roger老師" in ctx["name_to_student"]
    assert ctx["name_to_student"]["Roger老師"]["id"] == "roger-1"
    assert "summary" in ctx


