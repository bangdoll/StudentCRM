import json
import pytest
from pathlib import Path
from teaching_sync import sync_teaching_records_to_crm


def test_sync_teaching_records_to_crm_basic():
    res = sync_teaching_records_to_crm()
    assert res["success"] is True
    assert res["total_records"] >= 698
    assert res["total_students"] >= 60
    assert res["apple_ceo_notes_count"] >= 80

    crm_dir = Path(__file__).resolve().parents[1]
    data_file = crm_dir / "data" / "teaching_records.json"
    cache_file = crm_dir / "cache" / "teaching_records.json"

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

    # 驗證最新 2026-09-03 1362.蘋果總裁班 是否在筆記列表中
    latest_note = notes[0]
    assert latest_note["date"] == "2026-09-03"
    assert "1362" in latest_note["title"] or "1362" in latest_note["full_title"]
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
