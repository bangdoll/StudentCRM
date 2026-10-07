import json
import shutil
import pytest
from pathlib import Path
from teaching_sync import ensure_first_lesson_students_from_calendar, sync_teaching_records_to_crm
from digital_management_service import parse_digital_management_title


def test_sync_teaching_records_to_crm_basic(tmp_path):
    # 同步流程會寫入多份 CRM 檔案；使用工作區副本，避免測試污染正式資料。
    source_crm_dir = Path(__file__).resolve().parents[1]
    source_workspace_dir = source_crm_dir.parents[1]
    isolated_workspace = tmp_path / "workspace"
    isolated_crm_dir = isolated_workspace / "07.Projects" / "StudentCRM"
    isolated_data_dir = isolated_crm_dir / "data"
    isolated_teaching_dir = isolated_workspace / "01.Docs" / "teaching"

    isolated_data_dir.mkdir(parents=True)
    shutil.copytree(
        source_workspace_dir / "01.Docs" / "teaching",
        isolated_teaching_dir,
        ignore=shutil.ignore_patterns("assets", "*.png", "*.jpg", "*.jpeg", "*.docx", "*.m4a"),
    )
    shutil.copy2(source_crm_dir / "data" / "students.json", isolated_data_dir / "students.json")
    shutil.copy2(source_crm_dir / "data" / "apple_ceo_class.json", isolated_data_dir / "apple_ceo_class.json")
    shutil.copy2(
        source_crm_dir / "data" / "digital_management_calendar_events.json",
        isolated_data_dir / "digital_management_calendar_events.json",
    )
    baseline_students = json.loads((isolated_data_dir / "students.json").read_text(encoding="utf-8"))
    baseline_students = [
        student
        for student in baseline_students
        if student.get("id") != "806fac9e-6139-54e0-a774-75f87fc0202e"
    ]
    (isolated_data_dir / "students.json").write_text(
        json.dumps(baseline_students, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    res = sync_teaching_records_to_crm(isolated_workspace)
    assert res["success"] is True
    assert res["total_records"] >= 698
    assert res["total_students"] >= 60
    assert res["apple_ceo_notes_count"] >= 80
    assert any(
        item["id"] == "806fac9e-6139-54e0-a774-75f87fc0202e"
        for item in res["first_lesson_students_created"]
    )

    data_file = isolated_crm_dir / "data" / "teaching_records.json"
    cache_file = isolated_crm_dir / "cache" / "teaching_records.json"

    assert data_file.exists()
    assert cache_file.exists()

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "records" in data
    assert len(data["records"]) == res["total_records"]
    assert "by_student" in data


def test_first_lesson_calendar_creates_student_once(tmp_path):
    crm_dir = tmp_path / "StudentCRM"
    (crm_dir / "data").mkdir(parents=True)
    (crm_dir / "data" / "digital_management_calendar_events.json").write_text(
        json.dumps([
            {
                "id": "event-liya-01",
                "date": "2026-10-06",
                "title": "01.Liya數位管理教學",
                "start": "2026-10-06T14:00:00+08:00",
                "end": "2026-10-06T16:00:00+08:00",
            },
            {
                "id": "event-liya-02",
                "date": "2026-10-13",
                "title": "02.Liya數位管理教學",
                "start": "2026-10-13T14:00:00+08:00",
                "end": "2026-10-13T16:00:00+08:00",
            },
        ], ensure_ascii=False),
        encoding="utf-8",
    )

    students = []
    created = ensure_first_lesson_students_from_calendar(students, crm_dir)
    assert len(created) == 1
    assert created[0]["id"] == "806fac9e-6139-54e0-a774-75f87fc0202e"
    assert created[0]["name"] == "Liya"
    assert created[0]["first_lesson_date"] == "2026-10-06"
    assert created[0]["source_event_id"] == "event-liya-01"
    assert students[0]["public_token"].startswith("liya-")
    assert students[0]["lessons_count"] == 1
    assert students[0]["current_cycle_lesson"] == 1

    assert ensure_first_lesson_students_from_calendar(students, crm_dir) == []
    assert len(students) == 1


@pytest.mark.parametrize(
    ("title", "expected_name"),
    [
        ("Liya第一堂數位管理教學", "Liya"),
        ("第一堂數位管理教學：Amy", "Amy"),
        ("20261006 第一堂數位管理教學 Liya", "Liya"),
    ],
)
def test_explicit_first_lesson_title_marker_is_parsed(title, expected_name):
    parsed = parse_digital_management_title(title)
    assert parsed["student_name"] == expected_name
    assert parsed["lesson_number"] == 1
    assert parsed["first_lesson_signal"] == "explicit_title_marker"


def test_explicit_first_lesson_title_without_name_is_ignored():
    assert parse_digital_management_title("第一堂數位管理教學") == {}


def test_explicit_first_lesson_calendar_creates_student(tmp_path):
    crm_dir = tmp_path / "StudentCRM"
    (crm_dir / "data").mkdir(parents=True)
    (crm_dir / "data" / "digital_management_calendar_events.json").write_text(
        json.dumps(
            [
                {
                    "id": "event-amy-first",
                    "date": "2026-10-07",
                    "title": "第一堂數位管理教學：Amy",
                    "start": "2026-10-07T14:00:00+08:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    students = []
    created = ensure_first_lesson_students_from_calendar(students, crm_dir)
    assert len(created) == 1
    assert created[0]["name"] == "Amy"
    assert created[0]["first_lesson_date"] == "2026-10-07"
    assert students[0]["public_token"].startswith("amy-")


def test_sync_apple_ceo_notes_integration():
    crm_dir = Path(__file__).resolve().parents[1]
    apple_ceo_file = crm_dir / "data" / "apple_ceo_class.json"
    assert apple_ceo_file.exists()

    with open(apple_ceo_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    notes = data.get("teaching_notes", [])
    assert len(notes) >= 80

    # 驗證最新蘋果總裁班教學筆記是否在列表中且格式完整
    latest_note = notes[0]
    assert latest_note["date"] >= "2026-09-03"
    assert "蘋果總裁班" in (latest_note.get("title", "") + latest_note.get("full_title", "") + latest_note.get("filename", ""))
    assert "content" in latest_note
    assert "preview" in latest_note
    assert latest_note["word_count"] > 0


def test_sync_one_on_one_and_group_records():
    crm_dir = Path(__file__).resolve().parents[1]
    data_file = crm_dir / "data" / "teaching_records.json"

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. 驗證一對一學員 (Shelley 陳萱玲)
    shelley_records = [r for r in data["records"] if "Shelley" in r.get("student_name", "") or "陳萱玲" in r.get("student_name", "")]
    assert len(shelley_records) >= 15
    assert any(r.get("date") == "2026-09-03" for r in shelley_records)

    # 2. 驗證團體專班 (資深少年 AI 學習團)
    senior_ai_records = [r for r in data["records"] if "資深少年" in r.get("student_name", "")]
    assert len(senior_ai_records) >= 7


def test_remove_liushuhua_online_and_consultation_events():
    """驗證劉淑華線上與諮詢日曆事件不被解析為數位管理學員。"""
    from digital_management_service import parse_digital_management_title, build_digital_management_profiles

    # 1. 驗證標題解析排除諮詢與劉淑華線上
    assert parse_digital_management_title("劉淑華線上數位管理教學諮詢") == {}
    assert parse_digital_management_title("Smart的二兒子數位管理教學諮詢") == {}
    assert parse_digital_management_title("60-4.Kelly Woo 數位管理教學") != {}

    # 2. 驗證 profile 聚合中已徹底無此學員
    payload = build_digital_management_profiles(include_heptabase=False)
    students = payload.get("students", [])
    found_liushuhua = next((s for s in students if s.get("id") == "digital-90b9bc3851" or "劉淑華" in s.get("name", "")), None)
    assert found_liushuhua is None


def test_taoyuan_teaching_notes_completed_and_clean_date():
    """驗證桃園數位管理教學筆記已補齊且無 2025-01-00 畸形日期。"""
    from digital_management_service import build_digital_management_profiles

    payload = build_digital_management_profiles(include_heptabase=False)
    students = payload.get("students", [])
    taoyuan = next((s for s in students if s.get("id") == "36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95"), None)

    assert taoyuan is not None
    assert taoyuan["name"] == "桃園"
    notes = taoyuan.get("notes", [])

    # 1. 筆記總數應從原本的 14 篇擴充至 30 篇以上
    assert len(notes) >= 30

    # 2. 驗證無畸形日期，且 2025-10-07 存在
    dates = [n.get("date") for n in notes]
    assert "2025-01-00" not in dates
    assert "2025-10-07" in dates
    assert "2026-07-03" in dates  # 第 100 堂
    assert "2022-10-21" in dates  # 第 70 堂
