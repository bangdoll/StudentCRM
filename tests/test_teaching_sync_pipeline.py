import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from teaching_sync_pipeline import TeachingSyncPipeline, SyncResult


@pytest.fixture
def crm_dir():
    return Path(__file__).resolve().parents[1]


def test_pipeline_init(crm_dir):
    pipeline = TeachingSyncPipeline(crm_dir)
    assert pipeline.crm_dir == crm_dir
    assert pipeline.students_file.exists()
    assert pipeline.teaching_records_file.exists()


def test_pipeline_load_student_records(crm_dir):
    pipeline = TeachingSyncPipeline(crm_dir)
    student, records = pipeline.load_student_records("36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95")
    assert student is not None
    assert student["name"] == "桃園"
    assert len(records) == 31


def test_pipeline_detects_orphans_in_diff(crm_dir):
    pipeline = TeachingSyncPipeline(crm_dir)
    student, records = pipeline.load_student_records("36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95")
    payload_rows = pipeline.build_payload_rows(student, records)
    assert len(payload_rows) == 31

    # 模擬 Supabase 雲端回傳：包含 1 筆孤立舊記錄 + 30 筆有效記錄
    legacy_orphan_id = "7bb4ceeb-4449-5b0e-a980-19307db4986e"
    mock_existing_remote = [{"id": r["id"]} for r in payload_rows[:30]] + [{"id": legacy_orphan_id}]

    to_upsert, stale_ids = pipeline.calculate_diff(payload_rows, mock_existing_remote)
    assert len(to_upsert) == 31
    assert stale_ids == [legacy_orphan_id]


def test_pipeline_dry_run_mode(crm_dir):
    pipeline = TeachingSyncPipeline(crm_dir)
    with patch.object(pipeline, "_query_remote_student_records", return_value=[{"id": "mock-orphan-1"}]):
        res = pipeline.sync_student("36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95", dry_run=True)
        assert res.success is True
        assert res.mode == "dry-run"
        assert res.student_name == "桃園"
        assert res.records_count == 31
        assert "mock-orphan-1" in res.orphans_cleaned


def test_pipeline_skips_when_no_credentials(crm_dir, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    pipeline = TeachingSyncPipeline(crm_dir)
    pipeline.base_url = ""
    pipeline.service_key = ""
    res = pipeline.sync_student("36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95", dry_run=False)
    assert res.success is False
    assert "缺少 SUPABASE_URL" in res.error_message
