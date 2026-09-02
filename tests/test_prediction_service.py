from datetime import datetime
from prediction_service import predict_student_status, analyze_student_features


def test_predict_student_status_active():
    features = {"days_since_last_lesson": 5, "average_word_count": 1200}
    pred = predict_student_status(features)
    assert pred["badge"] == "🟢"
    assert "穩定留存" in pred["status"]


def test_predict_student_status_freezing():
    features = {"days_since_last_lesson": 25, "average_word_count": 1200}
    pred = predict_student_status(features)
    assert pred["badge"] == "🧊"
    assert "冰凍期" in pred["status"]


def test_predict_student_status_high_risk():
    features = {"days_since_last_lesson": 30, "average_word_count": 80}
    pred = predict_student_status(features)
    assert pred["badge"] == "🔴"
    assert "高流失風險" in pred["status"]


def test_analyze_student_features_uses_metadata_latest_date():
    student = {
        "id": "test-student-1",
        "name": "測試學員",
        "latest_date": "2026-08-27",
    }
    fixed_now = datetime(2026, 9, 2, 12, 0, 0)
    features = analyze_student_features(student, base_dir="/nonexistent", student_notes=[], use_cache=False, now=fixed_now)
    assert features["days_since_last_lesson"] == 6
