"""
test_supabase_egress_guard.py
==============================
Matt Pocock 紀律除錯迴圈 - 紅燈回饋測試 (Red Loop)
針對 Supabase Egress 超額 (10.4 GB / 5 GB) 與 StudentCRM 全量 select=* 的防禦測試。
"""
import time
from unittest.mock import MagicMock, patch
import pytest

from data_gateway import (
    StudentDataGateway,
    GATEWAY_CACHE_TTL_SECONDS,
    clear_gateway_memory_cache,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_gateway_memory_cache()
    yield
    clear_gateway_memory_cache()


def test_load_all_teaching_records_uses_memory_cache(tmp_path):
    """驗證 load_all_teaching_records 在 TTL 內必須命中記憶體快取，不可重複發起後端查詢。"""
    gateway = StudentDataGateway(base_dir=".")
    gateway.backend = "supabase"
    gateway.supabase_url = "https://mock.supabase.co"
    gateway.supabase_key = "mock-key"
    gateway.teaching_records_cache_file = str(tmp_path / "teaching_records_cloud_cache.json")

    mock_records = [
        {"id": "1", "student_id": "s1", "title": "Lesson 1", "date": "2026-10-01"},
        {"id": "2", "student_id": "s2", "title": "Lesson 2", "date": "2026-10-02"},
    ]

    with patch.object(gateway, "_load_supabase_table", return_value=mock_records) as mock_load:
        # 第一次呼叫，發起查詢
        res1 = gateway.load_all_teaching_records()
        assert len(res1) == 2

        # 第二次呼叫，必須命中記憶體快取，不可再度呼叫 _load_supabase_table
        res2 = gateway.load_all_teaching_records()
        assert len(res2) == 2
        assert mock_load.call_count == 1, f"未命中快取！呼叫次數為 {mock_load.call_count}，造成 Egress 浪費！"


def test_load_all_teaching_records_query_projection_excludes_heavy_content(tmp_path):
    """驗證 load_all_teaching_records 在向 Supabase 查詢時，絕對不可使用 select=*，必須精簡欄位排除 content/raw。"""
    gateway = StudentDataGateway(base_dir=".")
    gateway.backend = "supabase"
    gateway.supabase_url = "https://mock.supabase.co"
    gateway.supabase_key = "mock-key"
    gateway.teaching_records_cache_file = str(tmp_path / "teaching_records_cloud_cache.json")

    captured_queries = []

    def fake_load_table(table_name, query=None):
        captured_queries.append(query or "")
        return [{"id": "1", "title": "Lesson 1", "date": "2026-10-01"}]

    with patch.object(gateway, "_load_supabase_table", side_effect=fake_load_table):
        gateway.load_all_teaching_records()

    assert len(captured_queries) == 1
    query = captured_queries[0]
    # 必須不能包含 select=*
    assert "select=*" not in query, f"發現全欄位抓取 select=*！Query: {query}"
    # 必須包含投影欄位
    assert "select=" in query
    # 投影不可包含 content 與 raw
    assert "content" not in query
    assert "raw" not in query


def test_load_teaching_record_detail_for_single_note():
    """驗證當需要讀取特定單筆筆記正文時，必須透過專用的窄介面依 id/path 精準查詢單筆。"""
    gateway = StudentDataGateway(base_dir=".")
    gateway.backend = "supabase"
    gateway.supabase_url = "https://mock.supabase.co"
    gateway.supabase_key = "mock-key"

    def fake_load_table(table_name, query=None):
        if "id=eq.test-id" in (query or ""):
            return [{"id": "test-id", "title": "Note 1", "content": "Full Markdown Body"}]
        return []

    with patch.object(gateway, "_load_supabase_table", side_effect=fake_load_table):
        # 必須具備 load_teaching_record_detail 方法
        record = gateway.load_teaching_record_detail("test-id")
        assert record is not None
        assert record.get("content") == "Full Markdown Body"
