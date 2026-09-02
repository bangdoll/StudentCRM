import pytest
from starlette.testclient import TestClient

from main import app
from student_service import generate_preclass_briefing
from note_service import extract_micro_action_cards


client = TestClient(app)


def test_generate_preclass_briefing_extracts_skills_and_challenges():
    student = {
        "name": "測試學員",
        "lessons_count": 3,
        "current_cycle_lesson": 3,
    }
    notes = [
        {
            "title": "Heptabase 白板與雙向連結實戰",
            "preview": "在練習卡片分類與雙向連結時，遇到格式混亂卡住，下次需複習快捷鍵",
        }
    ]
    briefing = generate_preclass_briefing(student, notes)
    assert briefing["student_name"] == "測試學員"
    assert briefing["current_cycle_lesson"] == 3
    assert "Heptabase 白板與雙向連結" in briefing["mastered_skills"]
    assert any("卡住" in ch or "格式混亂" in ch for ch in briefing["recent_challenges"])
    assert "第二階段" in briefing["stage_name"]
    assert "【蔡教練課前 3 分鐘備課備忘】" in briefing["briefing_text"]


def test_extract_micro_action_cards_fallback_and_patterns():
    # 包含快捷鍵的文字
    content_with_shortcut = """
# 課堂紀錄
今日重點練習快捷鍵：Cmd + Shift + K 快速置頂卡片
建立 Heptabase 晨間白板習慣
"""
    cards = extract_micro_action_cards(content_with_shortcut, "Heptabase 實戰")
    assert "Cmd" in cards["key_action"] or "shortcut" in cards["key_action"].lower()
    assert "晨間白板" in cards["micro_habit"]
    assert len(cards["weekly_win"]) > 0


def test_read_student_hub_endpoint_valid_student():
    # 測試現有學員 (以 Charlotte 為例: 78fd9e3f-6a0c-4f92-bd10-2834903478fa)
    response = client.get("/my/78fd9e3f-6a0c-4f92-bd10-2834903478fa")
    assert response.status_code == 200
    assert "Charlotte" in response.text
    assert "數位管理八堂修煉技能樹" in response.text
    assert "專屬學員修煉空間" in response.text


def test_read_student_hub_alias_endpoint():
    response = client.get("/hub/78fd9e3f-6a0c-4f92-bd10-2834903478fa")
    assert response.status_code == 200
    assert "Charlotte" in response.text


def test_read_student_hub_redirect_merged_student():
    # 測試已合併學員之 301 轉址 (例如古金桃之被合併 ID)
    response = client.get("/my/7071583c-13d4-4a2b-bf91-a52c9e968322", follow_redirects=False)
    assert response.status_code == 301
    assert "/my/6e3b718a-3f8e-46dc-ad79-53d4ef41c74e" in response.headers["location"]


def test_read_student_hub_not_found():
    response = client.get("/my/invalid-token-12345")
    assert response.status_code == 404


def test_coach_magic_link_flow_and_privacy_lock():
    # 1. 訪客未授權進入首頁 -> 顯示 403 隱私保護鎖定頁
    unauth_resp = client.get("/", headers={"X-Test-Auth": "true"})
    assert unauth_resp.status_code == 403
    assert "學員隱私安全保護空間" in unauth_resp.text

    # 2. 教練點擊專屬通行連結 /coach/zzzz -> 303 轉址並設定 session cookie
    login_resp = client.get("/coach/zzzz", follow_redirects=False)
    assert login_resp.status_code == 303
    assert "coach_session" in login_resp.cookies

    # 3. 攜帶 session cookie 即可自由進入首頁
    cookie_val = login_resp.cookies["coach_session"]
    auth_resp = client.get("/", cookies={"coach_session": cookie_val}, headers={"X-Test-Auth": "true"})
    assert auth_resp.status_code == 200
