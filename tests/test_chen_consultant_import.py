from pathlib import Path

from student_timeline_service import get_student_metadata
from teaching_sync import build_teaching_records_from_directory, parse_teaching_file


STUDENT = {"id": "f13107ba-79fb-5bae-8728-99648687ef48", "name": "陳顧問", "aliases": []}


def test_parse_chen_consultant_nested_note(tmp_path: Path):
    source_dir = tmp_path / "陳顧問"
    source_dir.mkdir()
    note = source_dir / "01_2026-05-13_和陳顧問合作課程.md"
    note.write_text(
        "---\n課程日期：2026-05-13\n課程編號：01\n---\n\n# 20260513 01.和陳顧問合作課程\n\n測試內容。\n",
        encoding="utf-8",
    )

    parsed = parse_teaching_file(note)

    assert parsed is not None
    assert parsed["student_name"] == "陳顧問"
    assert parsed["date"] == "2026-05-13"
    assert parsed["lesson_num"] == 1
    assert parsed["title"] == "#20260513 01.和陳顧問合作課程"


def test_chen_consultant_v2_replaces_older_same_lesson(tmp_path: Path):
    source_dir = tmp_path / "陳顧問"
    source_dir.mkdir()
    base = source_dir / "14_2026-09-22_和陳顧問合作課程.md"
    latest = source_dir / "14_2026-09-22_和陳顧問合作課程_v2.md"
    base.write_text("# 舊版本\n", encoding="utf-8")
    latest.write_text("# 最新版本\n", encoding="utf-8")

    payload = build_teaching_records_from_directory(source_dir, [STUDENT])

    assert payload["total_records"] == 1
    assert payload["records"][0]["filename"] == latest.name
    assert "最新版本" in payload["records"][0]["content"]


def test_empty_student_profile_path_does_not_open_workspace_directory(tmp_path: Path):
    assert get_student_metadata(str(tmp_path)) == {}
