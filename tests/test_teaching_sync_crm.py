import json
import shutil
import pytest
from pathlib import Path
from teaching_sync import sync_teaching_records_to_crm


def test_sync_teaching_records_to_crm_basic(tmp_path):
    # 同步流程會寫入多份 CRM 檔案；使用工作區副本，避免測試污染正式資料。
    source_crm_dir = Path(__file__).resolve().parents[1]
    source_workspace_dir = source_crm_dir.parents[1]
    isolated_workspace = tmp_path / "workspace"
    isolated_crm_dir = isolated_workspace / "07.Projects" / "StudentCRM"
    isolated_data_dir = isolated_crm_dir / "data"
    isolated_teaching_dir = isolated_workspace / "01.Docs" / "teaching"

    isolated_data_dir.mkdir(parents=True)
    shutil.copytree(source_workspace_dir / "01.Docs" / "teaching", isolated_teaching_dir)
    shutil.copy2(source_crm_dir / "data" / "students.json", isolated_data_dir / "students.json")
    shutil.copy2(source_crm_dir / "data" / "apple_ceo_class.json", isolated_data_dir / "apple_ceo_class.json")

    res = sync_teaching_records_to_crm(isolated_workspace)
    assert res["success"] is True
    assert res["total_records"] >= 698
    assert res["total_students"] >= 60
    assert res["apple_ceo_notes_count"] >= 80

    data_file = isolated_crm_dir / "data" / "teaching_records.json"
    cache_file = isolated_crm_dir / "cache" / "teaching_records.json"

    assert data_file.exists()
    assert cache_file.exists()

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "records" in data
    assert len(data["records"]) == res["total_records"]
    assert "by_student" in data


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
