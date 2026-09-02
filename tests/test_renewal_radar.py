from student_service import generate_student_renewal_reminder, get_global_renewal_radar


def test_generate_student_renewal_reminder_completed():
    student = {"name": "曾小米", "lessons_count": 16}
    msg = generate_student_renewal_reminder(student)
    assert "曾小米" in msg
    assert "滿 8 堂" in msg
    assert "第 2 輪" in msg
    assert "專屬席位保留通知" in msg


def test_generate_student_renewal_reminder_warning():
    student = {"name": "Yvonne", "lessons_count": 39}
    msg = generate_student_renewal_reminder(student)
    assert "Yvonne" in msg
    assert "7/8 堂" in msg
    assert "專屬時段無縫延續" in msg


def test_get_global_renewal_radar_filters_and_sorts():
    students = [
        {"id": "1", "name": "學員A", "lessons_count": 16, "latest_date": "2026-08-01"},
        {"id": "2", "name": "學員B", "lessons_count": 7, "latest_date": "2026-08-15"},
        {"id": "3", "name": "學員C", "lessons_count": 5, "latest_date": "2026-08-10"},  # not 7 or 8
        {"id": "4", "name": "蘋果總裁班", "lessons_count": 424},  # class group excluded
    ]
    radar = get_global_renewal_radar(students)
    names = [r["name"] for r in radar]
    assert "學員A" in names
    assert "學員B" in names
    assert "學員C" not in names
    assert "蘋果總裁班" not in names
