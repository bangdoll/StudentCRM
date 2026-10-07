import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from image_sync_engine import ImageSyncEngine


@pytest.fixture
def temp_workspace(tmp_path):
    ws = tmp_path / "workspace"
    crm = ws / "07.Projects" / "StudentCRM"
    docs_assets = ws / "01.Docs" / "teaching" / "assets"
    crm_assets = crm / "static" / "teaching_assets"
    
    docs_assets.mkdir(parents=True, exist_ok=True)
    crm_assets.mkdir(parents=True, exist_ok=True)
    
    return {
        "workspace": ws,
        "crm": crm,
        "docs_assets": docs_assets,
        "crm_assets": crm_assets,
    }


def test_image_sync_engine_syncs_and_compresses_image(temp_workspace):
    docs_assets = temp_workspace["docs_assets"]
    crm_assets = temp_workspace["crm_assets"]
    
    # 建立一張假圖片 (小於 300KB)
    test_img = docs_assets / "lesson_flow.png"
    test_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    
    engine = ImageSyncEngine(crm_dir=temp_workspace["crm"], workspace_dir=temp_workspace["workspace"])
    
    records = [
        {
            "id": "rec-1",
            "content": "今天上課內容請參考流程圖：![流程圖](assets/lesson_flow.png)"
        }
    ]
    
    result = engine.sync_records_images(records)
    
    assert result["synced"] >= 1
    target_img = crm_assets / "lesson_flow.png"
    assert target_img.exists()
    assert target_img.read_bytes() == test_img.read_bytes()


def test_image_sync_engine_skips_up_to_date(temp_workspace):
    docs_assets = temp_workspace["docs_assets"]
    crm_assets = temp_workspace["crm_assets"]
    
    test_img = docs_assets / "cached.png"
    test_img.write_bytes(b"content-12345")
    
    target_img = crm_assets / "cached.png"
    target_img.write_bytes(b"content-12345")
    
    # 確保 mtime 一致或更新
    os.utime(target_img, (test_img.stat().st_atime, test_img.stat().st_mtime + 10))
    
    engine = ImageSyncEngine(crm_dir=temp_workspace["crm"], workspace_dir=temp_workspace["workspace"])
    result = engine.sync_records_images([{"content": "![demo](assets/cached.png)"}])
    
    assert result["skipped"] == 1
    assert result["synced"] == 0


def test_image_sync_engine_heals_missing_uuid(temp_workspace):
    docs_assets = temp_workspace["docs_assets"]
    crm_assets = temp_workspace["crm_assets"]
    
    uuid_str = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    img_name = f"whiteboard_{uuid_str}.png"
    
    engine = ImageSyncEngine(crm_dir=temp_workspace["crm"], workspace_dir=temp_workspace["workspace"])
    
    # 模擬 Heptabase CLI 成功匯出
    def mock_heal(name, target_dir):
        fake_file = target_dir / name
        fake_file.write_bytes(b"healed_content")
        return fake_file
        
    with patch.object(engine, "heal_missing_image", side_effect=mock_heal):
        result = engine.sync_records_images([{"content": f"![板書](assets/{img_name})"}])
        assert result["synced"] == 1
        assert (crm_assets / img_name).exists()
