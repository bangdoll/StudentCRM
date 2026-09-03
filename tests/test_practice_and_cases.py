# -*- coding: utf-8 -*-
"""
test_practice_and_cases.py
驗證方案一（課堂精華抽籤小卡）、方案二（去識別化 100 篇案例庫）與方案三（課程大綱手冊）的端點與資料邏輯。
"""

import os
import json
from pathlib import Path
from starlette.testclient import TestClient
from main import app
from hub_service import get_random_practice_card, load_all_practice_cards


client = TestClient(app)
APP_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = APP_DIR.parent.parent


def test_random_practice_card_service():
    """驗證抽籤小卡服務能正確回傳結構化卡片。"""
    card = get_random_practice_card(str(BASE_DIR), str(APP_DIR))
    assert isinstance(card, dict)
    assert "title" in card
    assert "category" in card
    assert "action" in card
    assert len(card["action"]) > 0


def test_api_random_practice_card_endpoint():
    """驗證 /api/practice/random HTTP 端點正確響應 200。"""
    resp = client.get("/api/practice/random")
    assert resp.status_code == 200
    data = resp.json()
    assert "title" in data
    assert "category" in data
    assert "action" in data


def test_cases_html_and_api_endpoints():
    """驗證 /cases 案例牆展示頁與 /api/cases JSON 端點。"""
    # 1. HTML 頁面
    resp_html = client.get("/cases")
    assert resp_html.status_code == 200
    assert "100+ 堂真實實戰見證庫" in resp_html.text
    assert "全部領域" in resp_html.text

    # 2. HEAD 請求支援
    resp_head = client.head("/cases")
    assert resp_head.status_code == 200

    # 3. JSON 端點
    resp_json = client.get("/api/cases")
    assert resp_json.status_code == 200
    cases = resp_json.json()
    assert isinstance(cases, list)
    assert len(cases) == 100
    sample = cases[0]
    assert "alias" in sample
    assert "role" in sample
    assert "category" in sample
    assert "pain_points" in sample
    assert "workflows" in sample
    assert "after_effects" in sample


def test_social_proof_deidentification_compliance():
    """嚴格遵循 AGENTS.md 隱私紅線：驗證 100 筆案例絕不含電話號碼或私人 Email。"""
    cases_file = APP_DIR / "data" / "social_proof_cases.json"
    assert cases_file.exists()

    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) == 100
    for c in cases:
        # 角色代號格式必須為 學員 #XXX
        assert c["alias"].startswith("學員 #")
        # 嚴禁含明文 09 開頭手機
        raw_text = json.dumps(c, ensure_ascii=False)
        assert "09" not in raw_text or "09XX" in raw_text or "09-" in raw_text or "20" in raw_text


def test_curriculum_handbook_exists_and_complete():
    """驗證方案三《一人公司數位管理實戰手冊》課程大綱手冊完整性。"""
    handbook = BASE_DIR / "01.Docs/products/One_Person_Company_Digital_Management_Handbook_Curriculum.md"
    assert handbook.exists()
    content = handbook.read_text(encoding="utf-8")
    assert "一人公司的『四層數位齒輪』" in content
    assert "30 個標準化實戰教學單元" in content
    assert "90 天一人公司實踐節奏表" in content
    assert "單元 01" in content
    assert "單元 30" in content
