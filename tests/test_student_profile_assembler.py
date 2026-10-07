import pytest
from unittest.mock import MagicMock, patch
from student_profile_assembler import StudentProfileAssembler


def test_assembler_returns_none_for_missing_student():
    mock_gateway = MagicMock()
    mock_gateway.get_student_profile.return_value = None
    
    assembler = StudentProfileAssembler(data_gateway=mock_gateway, base_dir=".")
    context = assembler.assemble_student_view_context("non-existent-id")
    assert context is None


def test_assembler_assembles_complete_context():
    mock_gateway = MagicMock()
    mock_gateway.get_student_profile.return_value = {
        "id": "stu-1",
        "name": "陳萱玲",
        "current_cycle_lesson": 8,
        "cycle_size": 8,
        "file": "",
    }
    mock_gateway.load_students.return_value = [
        {"id": "stu-1", "name": "陳萱玲", "public_token": "shelley-token"}
    ]
    mock_gateway.load_teaching_records.return_value = []
    
    assembler = StudentProfileAssembler(
        data_gateway=mock_gateway,
        base_dir=".",
        teaching_notes_loader=lambda s: [],
        features_analyzer=lambda sid: {},
        status_predictor=lambda feat, nxt: "良好",
        renewal_generator=lambda s: "提醒續約",
        briefing_generator=lambda s, notes: "備課簡報",
        timeline_renderer=lambda s, recs: "<p>雲端時間軸</p>",
    )
    
    ctx = assembler.assemble_student_view_context("stu-1")
    assert ctx is not None
    assert ctx["student_id"] == "stu-1"
    assert ctx["student"]["name"] == "陳萱玲"
    assert ctx["hub_token"] == "shelley-token"
    assert ctx["renewal_message"] == "提醒續約"
    assert ctx["briefing"] == "備課簡報"
    assert "timeline_html" in ctx
    assert ctx["timeline_html"] == "<p>雲端時間軸</p>"
