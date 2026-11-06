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


def test_renewal_radar_with_30_lesson_cycle():
    from radar_service import evaluate_retention_signal

    # 王敏賢：30 堂專案第 14 堂，不應該進入 7/8 或 8/8 續約雷達
    wang = {
        "id": "65b736c6-06a8-486d-9db5-45ca0aba209e",
        "name": "王敏賢",
        "lessons_count": 22,
        "cycle_size": 30,
        "current_cycle_lesson": 14,
        "latest_date": "2026-04-27",
    }
    # Lucia：30 堂專案第 5 堂，不應該進入續約雷達
    lucia = {
        "id": "9f4dac5a-3229-4dec-9c28-d0554ead4822",
        "name": "Lucia 徐露華",
        "lessons_count": 43,
        "cycle_size": 30,
        "current_cycle_lesson": 5,
        "latest_date": "2026-10-30",
    }
    # 假想即將滿堂的 30 堂學員（第 29 堂）
    student_near_30 = {
        "id": "mock-30-warning",
        "name": "三十堂學員臨近",
        "lessons_count": 29,
        "cycle_size": 30,
        "current_cycle_lesson": 29,
        "latest_date": "2026-11-01",
    }
    # 假想滿 30 堂結業學員（第 30 堂）
    student_full_30 = {
        "id": "mock-30-full",
        "name": "三十堂學員滿額",
        "lessons_count": 30,
        "cycle_size": 30,
        "current_cycle_lesson": 30,
        "latest_date": "2026-11-02",
    }

    radar = get_global_renewal_radar([wang, lucia, student_near_30, student_full_30])
    radar_names = [r["name"] for r in radar]

    # 王敏賢與 Lucia 進行中，不應觸發續約通知
    assert "王敏賢" not in radar_names
    assert "Lucia 徐露華" not in radar_names

    # 臨近與滿額 30 堂者應正確觸發
    assert "三十堂學員臨近" in radar_names
    assert "三十堂學員滿額" in radar_names

    # 檢查文案
    msg_near = generate_student_renewal_reminder(student_near_30)
    assert "29/30 堂" in msg_near
    msg_full = generate_student_renewal_reminder(student_full_30)
    assert "滿 30 堂" in msg_full

    # 檢查 radar_service 的 evaluate_retention_signal
    # 王敏賢第 14 堂，若最近上課天數小於 14，留存訊號應為 stable，絕不是 upgrade_ready
    sig, text, badge = evaluate_retention_signal(days_since_last=5, task_stale=False, cycle_lesson=14, cycle_size=30)
    assert sig == "stable"
    assert sig != "upgrade_ready"

    # 若到了第 29 堂，才應判定為 upgrade_ready
    sig_29, _, _ = evaluate_retention_signal(days_since_last=5, task_stale=False, cycle_lesson=29, cycle_size=30)
    assert sig_29 == "upgrade_ready"

