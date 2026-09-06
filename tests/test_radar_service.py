"""tests/test_radar_service.py
成效雷達與 CSM 續約決策系統自動化測試套件。
"""

import os
import json
from datetime import date
import pytest
from starlette.testclient import TestClient

from radar_service import (
    calculate_days_since,
    determine_ai_import_stage,
    extract_primary_pain,
    evaluate_retention_signal,
    match_product_ladder,
    build_7day_followup_copy,
    build_full_effectiveness_radar,
)
from schemas.radar import (
    EffectivenessRadarItem,
    ProductRecommendation,
    CSMFollowupRecord,
    FollowupUpdateRequest,
)
from main import app
from data_gateway import StudentDataGateway


def test_calculate_days_since():
    ref = date(2026, 9, 4)
    assert calculate_days_since("2026-09-04", ref_date=ref) == 0
    assert calculate_days_since("2026-09-01", ref_date=ref) == 3
    assert calculate_days_since("2026-08-20", ref_date=ref) == 15
    assert calculate_days_since(None, ref_date=ref) == 999
    assert calculate_days_since("invalid-date", ref_date=ref) == 999


def test_determine_ai_import_stage():
    # 課次基準
    stage, detail = determine_ai_import_stage(lessons_count=2, cycle_lesson=1, recent_notes_text="")
    assert stage == "數位地基"
    assert "檔案" in detail or "環境" in detail

    stage, detail = determine_ai_import_stage(lessons_count=4, cycle_lesson=3, recent_notes_text="")
    assert stage == "核心提示詞"

    stage, detail = determine_ai_import_stage(lessons_count=10, cycle_lesson=5, recent_notes_text="")
    assert stage == "MVP自動化"

    stage, detail = determine_ai_import_stage(lessons_count=24, cycle_lesson=8, recent_notes_text="")
    assert stage == "AI OS系統"

    # 關鍵字加權提升
    stage_kw, _ = determine_ai_import_stage(
        lessons_count=8,
        cycle_lesson=2,
        recent_notes_text="今天深入學習 AI OS 架構與 Agent 分身協同工作流"
    )
    assert stage_kw == "AI OS系統"


def test_extract_primary_pain():
    pain1 = extract_primary_pain("學員表示常常找不到檔案，資料夾散落且未整理")
    assert "檔案混亂" in pain1

    pain2 = extract_primary_pain("快捷鍵操作生疏，還是習慣依賴滑鼠點選")
    assert "快捷鍵" in pain2

    pain_default = extract_primary_pain("今天上課非常順利，完成一個小專案")
    assert "穩定" in pain_default


def test_evaluate_retention_signal():
    # 待續約 / 升級優先
    sig, text, badge = evaluate_retention_signal(days_since_last=5, task_stale=False, cycle_lesson=7)
    assert sig == "upgrade_ready"
    assert "badge-primary" in badge

    # 高流失風險
    sig, text, badge = evaluate_retention_signal(days_since_last=35, task_stale=False, cycle_lesson=3)
    assert sig == "at_risk"
    assert "badge-danger" in badge

    # 需要關心（停滯或天數 > 14）
    sig, text, badge = evaluate_retention_signal(days_since_last=16, task_stale=False, cycle_lesson=3)
    assert sig == "attention"
    assert "badge-warning" in badge

    sig, text, badge = evaluate_retention_signal(days_since_last=10, task_stale=True, cycle_lesson=3)
    assert sig == "attention"

    # 穩定推進
    sig, text, badge = evaluate_retention_signal(days_since_last=6, task_stale=False, cycle_lesson=2)
    assert sig == "stable"
    assert "badge-success" in badge


def test_match_product_ladder():
    prod1 = match_product_ladder(ai_stage="數位地基", primary_pain="", lessons_count=2, cycle_lesson=1)
    assert prod1.title == "數位基礎救援包"

    prod2 = match_product_ladder(ai_stage="核心提示詞", primary_pain="", lessons_count=4, cycle_lesson=3)
    assert prod2.title == "90 分鐘工作流啟動課"

    prod3 = match_product_ladder(ai_stage="MVP自動化", primary_pain="", lessons_count=10, cycle_lesson=5)
    assert prod3.title == "MVP 工作流建置"

    prod4 = match_product_ladder(ai_stage="AI OS系統", primary_pain="", lessons_count=20, cycle_lesson=7)
    assert prod4.title == "90 天 AI OS 陪跑"


def test_build_7day_followup_copy():
    cards = [
        {"type": "微習慣", "content": "每天晨間在 Heptabase 打開開機白板"},
        {"type": "關鍵動作", "content": "用 Typeless 錄下 3 段日常語音摘要"},
    ]
    copy = build_7day_followup_copy("王大明", cards)
    assert "王大明" in copy
    assert "微習慣" in copy
    assert "1. 上次這幾個練習卡，你目前完成了哪一步？" in copy
    assert "LINE" in copy


def test_radar_data_gateway_and_csm_update(tmp_path):
    # 測試 Gateway 寫入與回訪更新
    app_dir = str(tmp_path)
    os.makedirs(os.path.join(app_dir, "data"), exist_ok=True)
    gateway = StudentDataGateway(base_dir=app_dir)

    initial_radar = {
        "generated_at": "2026-09-04T00:00:00Z",
        "summary": {"total_tracked": 1},
        "items": [
            {
                "student_id": "std-test-1",
                "name": "測試學員",
                "followup": {
                    "status": "pending",
                    "coach_notes": "初始備忘"
                }
            }
        ]
    }
    gateway.save_effectiveness_radar_data(initial_radar)

    loaded = gateway.get_effectiveness_radar_data()
    assert loaded["summary"]["total_tracked"] == 1

    # 執行 CSM 回訪狀態更新
    updated = gateway.update_csm_followup_record(
        student_id="std-test-1",
        update_data={
            "status": "contacted",
            "next_followup_date": "2026-09-15",
            "coach_notes": "已於 LINE 關心，學員表示捷徑正常運作"
        }
    )
    assert updated["followup"]["status"] == "contacted"
    assert updated["followup"]["next_followup_date"] == "2026-09-15"
    assert "已於 LINE 關心" in updated["followup"]["coach_notes"]


from urllib.parse import quote
from auth_service import SESSION_COOKIE_NAME, get_session_token


def test_radar_endpoints_auth_and_responses():
    client = TestClient(app)

    # 1. 未認證訪問 /radar 應遭攔截 (403)
    resp_unauth = client.get("/radar", headers={"X-Test-Auth": "true"})
    assert resp_unauth.status_code == 403

    # 2. 模擬教練 Passkey 認證通過
    token = get_session_token()
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.cookies.set("admin_user", quote("蔡教練"))

    resp_auth = client.get("/radar", headers={"X-Test-Auth": "true"})
    assert resp_auth.status_code == 200
    assert "成效雷達與 CSM 續約決策戰情室" in resp_auth.text
    assert "AI 導入階段" in resp_auth.text

    # 3. GET /api/radar JSON 端點
    resp_api = client.get("/api/radar", headers={"X-Test-Auth": "true"})
    assert resp_api.status_code == 200
    data = resp_api.json()
    assert "summary" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) > 0

    first_student = data["items"][0]
    target_sid = first_student["student_id"]

    # 4. POST /api/radar/followup 更新回訪
    followup_payload = {
        "student_id": target_sid,
        "status": "contacted",
        "next_followup_date": "2026-09-20",
        "coach_notes": "自動化測試更新回訪紀錄"
    }
    resp_post = client.post("/api/radar/followup", json=followup_payload, headers={"X-Test-Auth": "true"})
    assert resp_post.status_code == 200
    post_json = resp_post.json()
    assert post_json["success"] is True
    assert post_json["item"]["followup"]["status"] == "contacted"

    # 5. POST /api/radar/refresh 手動重算快取
    resp_refresh = client.post("/api/radar/refresh", headers={"X-Test-Auth": "true"})
    assert resp_refresh.status_code == 200
    refresh_json = resp_refresh.json()
    assert refresh_json["success"] is True
    assert "radar" in refresh_json


def test_radar_and_homepage_readonly_fs_resilience(monkeypatch):
    """回歸測試：模擬 Vercel Serverless Function 唯讀檔案系統環境，確保 /radar 與首頁永不崩潰。"""
    client = TestClient(app)
    token = get_session_token()
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.cookies.set("admin_user", quote("蔡教練"))

    orig_write = StudentDataGateway._write_json

    def mock_readonly_write(path: str, payload):
        if not path.startswith("/tmp"):
            raise OSError(30, f"Read-only file system: {path}")
        return orig_write(path, payload)

    monkeypatch.setattr(StudentDataGateway, "_write_json", staticmethod(mock_readonly_write))

    # 1. 唯讀環境下 GET /radar
    resp_radar = client.get("/radar", headers={"X-Test-Auth": "true"})
    assert resp_radar.status_code == 200
    assert "成效雷達與 CSM 續約決策戰情室" in resp_radar.text

    # 2. 唯讀環境下 HEAD /radar
    resp_head = client.head("/radar", headers={"X-Test-Auth": "true"})
    assert resp_head.status_code == 200

    # 3. 唯讀環境下 GET / 首頁，驗證包含成效雷達即時指針
    resp_root = client.get("/", headers={"X-Test-Auth": "true"})
    assert resp_root.status_code == 200
    assert "成效雷達與 CSM 續約決策戰情室" in resp_root.text
    assert "全域追蹤" in resp_root.text


def test_radar_excludes_memorial_and_paused_students(monkeypatch):
    """驗證成效雷達徹底排除 memorial (已故典藏) 與 paused (休學暫停) 學員，守護教練情感與營運雜訊零打擾。"""
    gateway = StudentDataGateway(base_dir=".")

    mock_students = [
        {"id": "s1", "name": "現役學員", "status": "active", "lessons_count": 8, "latest_date": "2026-09-01"},
        {"id": "s2", "name": "彭澤江", "status": "memorial", "lessons_count": 5, "latest_date": "2024-04-15"},
        {"id": "s3", "name": "大安妮", "status": "memorial", "lessons_count": 3, "latest_date": "2024-02-20"},
        {"id": "s4", "name": "腦波Annie", "status": "paused", "lessons_count": 1, "latest_date": "2022-06-02"},
    ]
    monkeypatch.setattr(gateway, "load_students", lambda: mock_students)
    monkeypatch.setattr(gateway, "save_effectiveness_radar_data", lambda x: None)

    radar = build_full_effectiveness_radar(gateway)
    items = radar.get("items", [])
    tracked_names = [it["name"] for it in items]

    assert "現役學員" in tracked_names
    assert "彭澤江" not in tracked_names
    assert "大安妮" not in tracked_names
    assert "腦波Annie" not in tracked_names
    assert radar["summary"]["total_tracked"] == 1


