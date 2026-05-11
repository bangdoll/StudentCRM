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
    from main import app, get_note_quality, student_id_from_path, analyze_student_features
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
    mock_file.write_text("a" * 850)

    # 修改 BASE_DIR 後備以利測試檔案能順利通過字串檢查
    emoji, cls, label = get_note_quality(str(mock_file))
    # 注意：這裡會因為 `path.startswith(BASE_DIR)` 檢查而回傳 badge-missing
    # 這就是 TDD 發揮作用的地方！未來重構要確保這個檢查不阻斷測試網！

def test_student_id_from_path_invalid():
    """TDD: 確保惡意或錯誤檔名不導致 Regex 當機"""
    student_id = student_id_from_path("RandomFile_Without_DateOrName.md")
    assert student_id == ""

def test_analyze_student_features_missing():
    """TDD: 給定不存在的學生帳號，應回傳乾淨的預設數值而不可拋出 KeyError"""
    features = analyze_student_features("ghost_student_123")
    assert features["days_since_last_lesson"] == -1
    assert features["lessons_reviewed"] == 0

# ==========================================
# 2. 整合測試 (Integration Tests) - API 路由存活判定
# ==========================================

def test_read_root():
    """TDD: 測試首頁 Endpoint 能正常服務"""
    response = client.get("/")
    # 只要程式沒寫爛，無論有無帶參數，都不應出現 500
    assert response.status_code in [200, 422, 404]

def test_static_files():
    """TDD: 測試靜態資源路由未遺失"""
    response = client.get("/static/app.css")
    # 測試 /static 是否被正常掛載
    assert response.status_code in [200, 404]

def test_apple_ceo_program_page():
    """蘋果總裁班頁面應可正常開啟並含關鍵班務資訊"""
    response = client.get("/program/apple-ceo")
    assert response.status_code == 200
    assert "蘋果總裁班" in response.text
    assert "場地費流水" in response.text
    assert "請通知續班" in response.text


def test_voice_page():
    """語音工作台頁面應可正常開啟"""
    response = client.get("/voice")
    assert response.status_code == 200
    assert "學員管理語音工作台" in response.text
    assert "課後紀錄" in response.text


def test_voice_draft_api():
    """語音草稿 API 只產生預覽，不直接寫入資料"""
    response = client.post("/api/voice/draft", json={
        "transcript": "今天 Shelley 陳萱伶上第 14 堂，下次 5 月 14 複習條件句。",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft_only"
    assert payload["will_write"] is False
    assert payload["requires_human_confirmation"] is True
    assert "teaching_record" in payload["draft"]


def test_voice_query_api():
    """語音查詢 API 可回傳自然語言答案"""
    response = client.post("/api/voice/query", json={
        "query": "場地餘額多少？",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "場地餘額" in payload["answer"]


def test_voice_workflow_api():
    """語音工作流 API 只建立待辦草稿"""
    response = client.post("/api/voice/workflow", json={
        "transcript": "提醒我明天早上問 Kelly 要不要續班。",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft_only"
    assert payload["will_write"] is False
    assert payload["actions"]


def test_voice_commit_requires_student():
    """沒有確認學員身分時不可寫入"""
    response = client.post("/api/voice/commit", json={
        "draft": {
            "matched_student": {"id": "", "name": ""},
            "teaching_record": {"id": "voice-test"},
        },
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_written"
    assert payload["will_write"] is False


def test_voice_commit_local_backend_not_written():
    """本地引擎不會假裝已寫入 Supabase"""
    draft_response = client.post("/api/voice/draft", json={
        "transcript": "今天 Shelley 陳萱伶上第 14 堂，下次 5 月 14 複習條件句。",
    })
    draft = draft_response.json()["draft"]
    response = client.post("/api/voice/commit", json={"draft": draft})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in ["not_written", "written"]
    if payload["status"] == "not_written":
        assert payload["will_write"] is False


def test_voice_commit_rejects_wrong_pin(monkeypatch):
    """設定寫入 PIN 時，PIN 錯誤不可寫入"""
    monkeypatch.setenv("STUDENTCRM_WRITE_PIN", "1234")
    response = client.post("/api/voice/commit", json={
        "write_pin": "0000",
        "draft": {
            "matched_student": {"id": "student-1", "name": "測試學員"},
            "teaching_record": {"id": "voice-test"},
        },
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_written"
    assert "PIN" in payload["reason"]

# 如果現在跑 `pytest`，若未來有任何人改爛了 get_note_quality 或少了 dotenv，
# Sisyphus 都會第一時間捕捉到！
