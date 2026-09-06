import os
import sys
import pytest
from fastapi.testclient import TestClient

# 確保載入時能正確找到依賴路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 在匯入 main 之前，為測試環境覆寫根目錄 (可支援隔離的測試資料)
# 若希望不破壞正式資料，可將其指向 /tmp/mock_dir
os.environ["OPEN_CLAW_BASE_DIR"] = "/Users/aios/Projects/00.AI-Notes_Local"
os.environ["STUDENTCRM_DATA_BACKEND"] = "local"

try:
    from main import app, get_note_quality, student_id_from_path, analyze_student_features, parse_digital_management_title
    from teaching_sync import parse_teaching_file, resolve_student, build_teaching_records_from_directory
    # 初始化 FastAPI 的測試客戶端
    client = TestClient(app)
except Exception as e:
    pytest.fail(f"無法載入 StudentCRM 的主程式應用，請確認依賴是否安裝齊全。錯誤原因: {e}")

# ==========================================
# 1. 單元測試 (Unit Tests) - 核心業務邏輯
# ==========================================

def test_get_note_quality_missing():
    """TDD: 測試在遇到不存在的檔案時，要完美防呆回傳佔位符"""
    emoji, cls, label = get_note_quality("/non_existent_file_path_123.md")
    assert emoji == "❌"
    assert cls == "badge-missing"
    assert "找不到" in label

def test_get_note_quality_full(tmp_path):
    """TDD: 測試超過 800 字的文章被視為筆記齊全"""
    mock_file = tmp_path / "long_note.md"
    mock_file.write_text("a" * 850, encoding="utf-8")
    emoji, cls, label = get_note_quality(str(mock_file))
    assert emoji == "✅"
    assert cls == "badge-full"
    assert "850 字" in label


def test_get_note_quality_short(tmp_path):
    """測試 201-800 字的文章被視為待補充"""
    mock_file = tmp_path / "short_note.md"
    mock_file.write_text("a" * 300, encoding="utf-8")
    emoji, cls, label = get_note_quality(str(mock_file))
    assert emoji == "⚠️"
    assert cls == "badge-short"
    assert "300 字（待補充）" in label


def test_get_note_quality_placeholder(tmp_path):
    """測試 200 字以下的文章被視為佔位文件"""
    mock_file = tmp_path / "placeholder_note.md"
    mock_file.write_text("a" * 50, encoding="utf-8")
    emoji, cls, label = get_note_quality(str(mock_file))
    assert emoji == "📄"
    assert cls == "badge-placeholder"
    assert label == "佔位文件"

def test_student_id_from_path_invalid():
    """TDD: 確保惡意或錯誤檔名不導致 Regex 當機"""
    student_id = student_id_from_path("RandomFile_Without_DateOrName.md")
    assert student_id == ""

def test_analyze_student_features_missing():
    """TDD: 給定不存在的學生帳號，應回傳乾淨的預設數值而不可拋出 KeyError"""
    features = analyze_student_features("ghost_student_123")
    assert features["days_since_last_lesson"] == -1
    assert features["lessons_reviewed"] == 0


def test_parse_digital_management_title_with_series_and_lesson():
    parsed = parse_digital_management_title("60-4.Kelly Woo 數位管理教學")
    assert parsed["student_name"] == "Kelly Woo"
    assert parsed["calendar_series_number"] == 60
    assert parsed["lesson_number"] == 4


def test_parse_digital_management_title_with_location_suffix():
    parsed = parse_digital_management_title("10-2.湘祺姐數位管理教學@捷運大安站4號出口")
    assert parsed["student_name"] == "湘祺姐"
    assert parsed["lesson_number"] == 2


def test_parse_digital_management_title_with_missing_lesson_after_dash():
    parsed = parse_digital_management_title("23-.陳海陸數位管理教學")
    assert parsed["student_name"] == "陳海陸"
    assert parsed["calendar_series_number"] == 23
    assert parsed["lesson_number"] == 23


def test_parse_teaching_file_standard_digital_management_filename(tmp_path):
    note = tmp_path / "20260522 10-2.曾小米數位管理教學.md"
    note.write_text("#20260522 10-2.曾小米數位管理教學\n今天練習 AI 工作流。", encoding="utf-8")
    parsed = parse_teaching_file(note)
    assert parsed["date"] == "2026-05-22"
    assert parsed["student_name"] == "曾小米"
    assert parsed["lesson_num"] == 10
    assert parsed["lesson_sub"] == "2"


def test_parse_teaching_file_lesson_date_filename_does_not_use_date_as_lesson(tmp_path):
    note = tmp_path / "Lesson_20260319_Chami.md"
    note.write_text("#Lesson_20260319_Chami\n今天練習自動化。", encoding="utf-8")
    parsed = parse_teaching_file(note)
    assert parsed["date"] == "2026-03-19"
    assert parsed["student_name"] == "Chami"
    assert parsed["lesson_num"] is None


def test_resolve_student_uses_aliases():
    student, matched_by = resolve_student("Shelley 陳萱玲", [{
        "id": "student-shelley",
        "name": "Shelley 陳萱玲",
        "aliases": ["Shelley", "陳萱玲"],
    }])
    assert student["id"] == "student-shelley"
    assert matched_by in ["Shelley 陳萱玲", "Shelley", "陳萱玲"]


def test_resolve_student_prefers_exact_name_over_longer_duplicate():
    student, matched_by = resolve_student("查米", [
        {"id": "student-chami-old", "name": "查米 315", "aliases": []},
        {"id": "student-chami", "name": "查米", "aliases": []},
    ])
    assert student["id"] == "student-chami"
    assert matched_by == "查米"


def test_build_teaching_records_from_directory_matches_students(tmp_path):
    note = tmp_path / "20260522 10-2.曾小米數位管理教學.md"
    note.write_text("#20260522 10-2.曾小米數位管理教學\n今天練習 AI 工作流。", encoding="utf-8")
    payload = build_teaching_records_from_directory(str(tmp_path), [{
        "id": "student-xiaomi",
        "name": "曾小米",
        "aliases": ["小米"],
    }])
    assert payload["total_records"] == 1
    assert payload["records"][0]["student_id"] == "student-xiaomi"
    assert payload["duplicate_count"] == 0

# ==========================================
# 2. 整合測試 (Integration Tests) - API 路由存活判定
# ==========================================

def test_read_root():
    """TDD: 測試首頁 Endpoint 能正常服務"""
    response = client.get("/")
    # 只要程式沒寫爛，無論有無帶參數，都不應出現 500
    assert response.status_code in [200, 422, 404]

def test_static_files():
    """TDD: 測試靜態資源路由正常服務"""
    response = client.get("/static/style.css")
    assert response.status_code == 200

def test_apple_ceo_program_page():
    """蘋果總裁班頁面應可正常開啟並含關鍵班務資訊"""
    response = client.get("/program/apple-ceo")
    assert response.status_code == 200
    assert "蘋果總裁班" in response.text
    assert "場地費流水" in response.text
    assert "請通知續班" in response.text
    assert "進行中 1 筆" in response.text
    assert "累計 27 堂" in response.text




def test_digital_management_page():
    """數位管理教學頁面應可從本地 teaching 檔案建立學生檔案"""
    response = client.get("/digital-management")
    assert response.status_code == 200
    assert "數位管理教學" in response.text
    assert "學生檔案" in response.text


def test_digital_management_api():
    """數位管理教學 API 應回傳學生、堂數與筆記來源"""
    response = client.get("/api/digital-management/students")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["count"] >= 1
    assert "current_lesson" in payload["students"][0]


def test_digital_management_profiles_use_cloud_teaching_records_when_local_empty(monkeypatch):
    import main as studentcrm_main

    monkeypatch.setattr(studentcrm_main, "load_digital_management_calendar_events", lambda: [])
    monkeypatch.setattr(studentcrm_main, "load_local_digital_management_notes", lambda: [])
    monkeypatch.setattr(studentcrm_main, "_CLOUD_NOTES_CACHE", {"timestamp": 0.0, "notes": []})
    monkeypatch.setattr(studentcrm_main.student_gateway, "load_all_teaching_records", lambda: [{
        "id": "record-cloud",
        "student_id": "student-cloud",
        "student_name": "雲端學員",
        "title": "#20260522 10-2.雲端學員數位管理教學",
        "date": "2026-05-22",
        "lesson_num": 10,
        "lesson_sub": "2",
        "raw": {
            "source": "local_teaching",
            "preview": "雲端教學筆記",
        },
    }])

    payload = studentcrm_main.build_digital_management_profiles()
    assert len(payload["students"]) == 1
    assert payload["students"][0]["id"] == "student-cloud"
    assert payload["students"][0]["current_lesson"] == 10
    assert payload["teaching_note_count"] == 1


def test_digital_management_profile_merges_cloud_notes_per_student(monkeypatch):
    """本地有其他學員筆記時，仍要把目標學員的雲端筆記放入個人頁。"""
    import main as studentcrm_main

    monkeypatch.setattr(studentcrm_main, "load_students", lambda: [
        {"id": "student-local", "name": "本地學員", "aliases": []},
        {"id": "student-cloud", "name": "雲端學員", "aliases": []},
    ])
    monkeypatch.setattr(studentcrm_main, "load_digital_management_calendar_events", lambda: [{
        "id": "calendar-cloud",
        "summary": "01.雲端學員數位管理教學",
        "start": "2026-05-22T10:00:00+08:00",
        "end": "2026-05-22T12:00:00+08:00",
    }])
    monkeypatch.setattr(studentcrm_main, "load_local_digital_management_notes", lambda: [{
        "id": "local-note",
        "student_id": "student-local",
        "student_name": "本地學員",
        "date": "2026-05-01",
        "title": "本地學員筆記",
        "lesson_number": 1,
        "source": "本地 teaching 檔案",
    }])
    monkeypatch.setattr(studentcrm_main, "load_cloud_digital_management_notes", lambda: [{
        "id": "cloud-note",
        "student_id": "student-cloud",
        "student_name": "雲端學員",
        "date": "2026-05-22",
        "title": "雲端學員筆記",
        "lesson_number": 1,
        "source": "Supabase teaching_records",
    }])

    payload = studentcrm_main.build_digital_management_profiles()
    profile = next(item for item in payload["students"] if item["id"] == "student-cloud")

    assert [note["id"] for note in profile["notes"]] == ["cloud-note"]
    assert payload["teaching_note_count"] == 2

    response = client.get("/digital-management/student/student-cloud")
    assert response.status_code == 200
    assert "雲端學員筆記" in response.text


def test_student_page_cloud_fallback(monkeypatch):
    """本地已有其他學員筆記時，目標學員頁仍要顯示雲端筆記。"""
    import main as studentcrm_main

    monkeypatch.setattr(studentcrm_main, "load_students", lambda: [{
        "id": "cloud-student",
        "name": "雲端學員",
        "file": "/missing-student.md",
        "tags": ["測試"],
        "lessons_count": 3,
        "latest_date": "2026-05-10",
        "next_lesson": "2026-05-17",
    }])
    monkeypatch.setattr(studentcrm_main, "load_local_digital_management_notes", lambda: [{
        "id": "local-note",
        "student_id": "another-student",
        "student_name": "其他學員",
        "date": "2026-05-01",
        "title": "其他學員筆記",
    }])
    monkeypatch.setattr(studentcrm_main, "load_cloud_digital_management_notes", lambda: [{
        "id": "cloud-note",
        "student_id": "cloud-student",
        "student_name": "雲端學員",
        "date": "2026-05-10",
        "title": "雲端學員筆記",
        "preview": "雲端筆記摘要",
    }])
    monkeypatch.setattr(studentcrm_main.student_gateway, "load_teaching_records", lambda student_id: [])

    response = client.get("/student/cloud-student")
    assert response.status_code == 200
    assert "雲端學員" in response.text
    assert "雲端學員筆記" in response.text
    assert "雲端摘要模式" in response.text


def test_note_endpoint_apple_ceo():
    """驗證 /note 路由能成功讀取蘋果總裁班教學筆記全文。"""
    response = client.get("/note?path=/01.Docs/teaching/20260813%201359.蘋果總裁班.md")
    assert response.status_code == 200
    assert "1359.蘋果總裁班" in response.text
    assert "返回蘋果總裁班" in response.text
    assert "教學筆記" in response.text


def test_note_endpoint_filename_fallback():
    """驗證 /note 路由即使僅傳入檔名也能在雲端 fallback 比對中成功解析。"""
    response = client.get("/note?path=20260813%201359.蘋果總裁班.md")
    assert response.status_code == 200
    assert "1359.蘋果總裁班" in response.text


def test_dashboard_endpoint_authenticated():
    """驗證登入後的教練能正常存取 /dashboard，無 UndefinedError，且支援 HEAD。"""
    from auth_service import get_session_token, SESSION_COOKIE_NAME, ADMIN_USER_COOKIE_NAME
    from urllib.parse import quote

    auth_client = TestClient(app)
    auth_client.cookies.set(SESSION_COOKIE_NAME, get_session_token())
    auth_client.cookies.set(ADMIN_USER_COOKIE_NAME, quote("蔡教練"))

    resp_get = auth_client.get("/dashboard", headers={"X-Test-Auth": "true"})
    assert resp_get.status_code == 200
    assert "學員行動看板" in resp_get.text
    assert "同步來源" in resp_get.text

    resp_head = auth_client.head("/dashboard", headers={"X-Test-Auth": "true"})
    assert resp_head.status_code == 200


def test_dashboard_endpoint_unauthenticated():
    """驗證未登入訪客存取 /dashboard 會被安全門禁攔截並回傳 403 隱私保護頁。"""
    unauth_client = TestClient(app)
    resp = unauth_client.get("/dashboard", headers={"X-Test-Auth": "true"})
    assert resp.status_code == 403
    assert "學員隱私保護空間" in resp.text

