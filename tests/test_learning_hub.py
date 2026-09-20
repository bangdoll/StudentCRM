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


def test_guessable_names_and_slugs_are_strictly_blocked():
    """安全測試：嚴格禁止透過猜測姓名、短網址或公開字眼存取學員空間，僅限不可猜測之私密 UUID。"""
    for bad_slug in ["apple-ceo", "apple", "蘋果總裁班", "senior-ai", "資深少年", "Charlotte", "Amy", "張素幸"]:
        resp = client.get(f"/my/{bad_slug}")
        assert resp.status_code == 404, f"Slug '{bad_slug}' should return 404 but got {resp.status_code}"


def test_coach_magic_link_flow_and_privacy_lock():
    client.cookies.clear()
    # 1. 訪客未授權進入首頁 -> 顯示 403 隱私保護鎖定頁
    unauth_resp = client.get("/", headers={"X-Test-Auth": "true"})
    assert unauth_resp.status_code == 403
    assert "學員隱私安全保護空間" in unauth_resp.text

    # 2. 蔡教練專屬私鑰 /coach/tsai-8f92b7c4-a13e-49b8-9e51-68d1a4c9520b -> 200 安全過渡頁並設定 session cookie
    coach_resp = client.get("/coach/tsai-8f92b7c4-a13e-49b8-9e51-68d1a4c9520b", follow_redirects=False)
    assert coach_resp.status_code == 200
    assert "正在安全解鎖" in coach_resp.text
    assert "coach_session" in coach_resp.cookies
    assert "crm_admin_user" in coach_resp.cookies

    # 3. 師母專屬私鑰 /coach/yumi-7e42d8c1-b39f-4a71-89e5-55c3a1f9482d -> 200 安全過渡頁並設定 session cookie
    from urllib.parse import unquote
    wife_resp = client.get("/coach/yumi-7e42d8c1-b39f-4a71-89e5-55c3a1f9482d", follow_redirects=False)
    assert wife_resp.status_code == 200
    assert "coach_session" in wife_resp.cookies
    assert unquote(wife_resp.cookies["crm_admin_user"]) == "師母 (Yumi)"

    # 4. 任意非法/猜測密鑰 -> 403 門禁鎖
    bad_resp = client.get("/coach/hacker-key-12345", follow_redirects=False)
    assert bad_resp.status_code == 403
    assert "學員隱私安全保護空間" in bad_resp.text

    # 5. 攜帶 session cookie 即可自由進入首頁
    cookie_val = coach_resp.cookies["coach_session"]
    client.cookies.set("coach_session", cookie_val)
    auth_resp = client.get("/", headers={"X-Test-Auth": "true"})
    assert auth_resp.status_code == 200
    assert "學員管理系統" in auth_resp.text

    # 6. 支援 URL Query Parameter 直接存取（解決跨環境遺失 Cookie 問題）
    query_resp = client.get("/?key=yumi-7e42d8c1-b39f-4a71-89e5-55c3a1f9482d", headers={"X-Test-Auth": "true"})
    assert query_resp.status_code == 200
    assert "學員管理系統" in query_resp.text
    assert "coach_session" in query_resp.cookies

    # 7. 支援若誤由 /my/{admin_key} 進入時自動容錯解鎖管理權限
    my_admin_resp = client.get("/my/yumi-7e42d8c1-b39f-4a71-89e5-55c3a1f9482d")
    assert my_admin_resp.status_code == 200
    assert "coach_session" in my_admin_resp.cookies


def test_student_pwa_manifest_and_home_screen_auto_redirect():
    # 1. 存取學員 Hub 時應自動注入 180 天長效憑證 Cookie
    valid_uuid = "78fd9e3f-6a0c-4f92-bd10-2834903478fa"
    hub_resp = client.get(f"/my/{valid_uuid}")
    assert hub_resp.status_code == 200
    assert "last_student_token" in hub_resp.cookies
    assert hub_resp.cookies["last_student_token"] == valid_uuid
    assert f"/my/{valid_uuid}/manifest.webmanifest" in hub_resp.text

    # 2. 學員專屬動態 Manifest 應將 start_url 綁定至個人 URL
    manifest_resp = client.get(f"/my/{valid_uuid}/manifest.webmanifest")
    assert manifest_resp.status_code == 200
    manifest = manifest_resp.json()
    assert manifest["start_url"] == f"/my/{valid_uuid}"
    assert manifest["scope"] == f"/my/{valid_uuid}"
    assert "Charlotte" in manifest["name"]

    # 3. 學員主畫面圖標若因歷史原因開啟了首頁 /，門禁系統自動 303 轉址回其個人空間
    client.cookies.clear()
    client.cookies.set("last_student_token", valid_uuid)
    home_resp = client.get(
        "/",
        headers={"X-Test-Auth": "true"},
        follow_redirects=False,
    )
    assert home_resp.status_code == 303
    assert home_resp.headers["location"] == f"/my/{valid_uuid}"


def test_apple_ceo_group_token_access_and_head_support():
    """驗證蘋果總裁班群組專屬亂碼金鑰 URL (/my/{token})、HEAD 支援與筆記存取。"""
    apple_token = "adf9958b-a23d-4e9b-a4a2-156b5329b0ed"

    # 1. 學生點擊私密亂碼網址，直接呈現蘋果總裁班完整班務與置頂教學筆記
    resp = client.get(f"/my/{apple_token}")
    assert resp.status_code == 200
    assert "蘋果總裁班" in resp.text
    assert "teachingNotesSection" in resp.text
    assert "attendanceSection" in resp.text
    assert "last_student_token" in resp.cookies
    assert resp.cookies["last_student_token"] == apple_token

    # 2. 支援 HEAD 請求，防止 LINE 或 Safari 預檢時報 405 Method Not Allowed
    head_resp = client.head(f"/my/{apple_token}")
    assert head_resp.status_code == 200

    # 3. 動態 PWA Manifest 支援總裁班
    manifest_resp = client.get(f"/my/{apple_token}/manifest.webmanifest")
    assert manifest_resp.status_code == 200
    assert "蘋果總裁班" in manifest_resp.json()["name"]

    # 4. 學生透過總裁班 token 開啟教學筆記全文
    note_path = "/01.Docs/teaching/20260827 1361.蘋果總裁班.md"
    note_resp = client.get(f"/note?path={note_path}&token={apple_token}")
    assert note_resp.status_code == 200
    assert "蘋果總裁班" in note_resp.text
    assert f"/my/{apple_token}" in note_resp.text

    # 5. 學生透過帶有 token 或 cookie 瀏覽 /program/apple-ceo，門禁直接通行
    prog_resp = client.get(f"/program/apple-ceo?token={apple_token}", headers={"X-Test-Auth": "true"})
    assert prog_resp.status_code == 200


def test_same_date_multiple_notes_and_image_resolution():
    """驗證同日多篇筆記去重不誤殺，且圖片路徑正確轉譯為 /static/teaching_assets/。"""
    kelly_id = "28ef42b0-8fc9-496f-a804-56b57b4011db"
    hub_resp = client.get(f"/my/{kelly_id}")
    assert hub_resp.status_code == 200
    # 兩篇同在 2026-09-20 的筆記皆必須在 Hub 頁面出現
    assert "20260920 70-1.Kelly Woo 數位管理教學" in hub_resp.text
    assert "Kelly 法國旅行 AI Reels 行動指南" in hub_resp.text

    # 點擊閱讀筆記，驗證圖片標籤已正確替換為 /static/teaching_assets/
    note_resp = client.get(
        f"/note?path=01.Docs/teaching/20260920%2070-1.Kelly%20Woo%20%E6%95%B8%E4%BD%8D%E7%AE%A1%E7%90%86%E6%95%99%E5%AD%B8.md&token={kelly_id}"
    )
    assert note_resp.status_code == 200
    assert "/static/teaching_assets/D2FA4D4E-0C6B-4EB9-B94F-81E2094CA963-14f348ae-069f-4563-9c47-1528e6a1a3f3.png" in note_resp.text


def test_student_note_back_link_not_polluted_by_apple_ceo_cookie():
    """驗證當瀏覽器殘留蘋果總裁班 cookie 時，一般學員（如 Kelly Woo）筆記的返回按鈕絕不會跳轉至蘋果總裁班。"""
    kelly_id = "28ef42b0-8fc9-496f-a804-56b57b4011db"
    apple_token = "adf9958b-a23d-4e9b-a4a2-156b5329b0ed"
    note_path = "01.Docs/teaching/20260920 70-1.Kelly Woo 數位管理教學.md"

    # 情境 1: 教練在後台開啟 Kelly 筆記（無 query token），但瀏覽器存有蘋果總裁班的 last_student_token cookie
    client.cookies.set("last_student_token", apple_token)
    resp = client.get(f"/note?path={note_path}")
    assert resp.status_code == 200
    # 「返回學員檔案」連結必須是 Kelly 的學員檔案，絕對不能是蘋果總裁班
    assert f"/student/{kelly_id}" in resp.text
    assert f"/my/{apple_token}" not in resp.text
    assert "/program/apple-ceo" not in resp.text

    # 情境 2: 學員在自己的 Hub 點擊筆記（帶有自己的 token）
    resp_with_token = client.get(f"/note?path={note_path}&token={kelly_id}")
    assert resp_with_token.status_code == 200
    assert f"/my/{kelly_id}" in resp_with_token.text
    assert f"/my/{apple_token}" not in resp_with_token.text

    # 情境 3: URL 誤帶總裁班 token 時，必須自動校正，不應跳往總裁班
    resp_tampered = client.get(f"/note?path={note_path}&token={apple_token}")
    assert resp_tampered.status_code == 200
    assert f"/my/{apple_token}" not in resp_tampered.text

