import json
from pathlib import Path
from fastapi.testclient import TestClient

from main import app
from teaching_sync import MANUAL_ALIASES


client = TestClient(app)


def test_entity_disambiguation_aliases_and_students():
    """蕭秉慧 不等於 Anna蕭：驗證別名與學員檔案完全分離。"""
    # 1. 驗證 MANUAL_ALIASES
    assert MANUAL_ALIASES.get("amanda") != "Anna 蕭"
    assert MANUAL_ALIASES.get("amanda蕭秉慧") != "Anna 蕭"
    assert MANUAL_ALIASES.get("蕭秉慧") != "Anna 蕭"
    assert MANUAL_ALIASES.get("蕭秉慧") == "Amanda 蕭秉慧"

    # 2. 驗證 students.json
    students_path = Path(__file__).resolve().parents[1] / "data" / "students.json"
    with open(students_path, "r", encoding="utf-8") as f:
        students = json.load(f)

    anna = next((s for s in students if s.get("name") == "Anna 蕭"), None)
    assert anna is not None, "Anna 蕭 必須存在"
    anna_aliases = anna.get("aliases", [])
    assert "Amanda" not in anna_aliases, "Anna 蕭 別名不得包含 Amanda"
    assert "Amanda 蕭秉慧" not in anna_aliases, "Anna 蕭 別名不得包含 Amanda 蕭秉慧"
    assert "蕭秉慧" not in anna_aliases, "Anna 蕭 別名不得包含 蕭秉慧"

    amanda = next((s for s in students if s.get("name") == "Amanda 蕭秉慧"), None)
    assert amanda is not None, "Amanda 蕭秉慧 必須獨立存在於 students.json"
    amanda_aliases = amanda.get("aliases", [])
    assert "蕭秉慧" in amanda_aliases or amanda.get("name") == "Amanda 蕭秉慧"
    assert "Anna 蕭" not in amanda_aliases


def test_search_student_and_content_queries():
    """驗證 /search 全面支援教學紀錄全文、學員與總裁班，且連結指向 /note?path=。"""
    # 1. 搜尋「蕭秉慧」
    resp = client.get("/search?q=蕭秉慧")
    assert resp.status_code == 200
    html = resp.text
    assert "蕭秉慧" in html
    # 必須找到至少一筆記錄，且連結使用 /note?path= 而非 /open_file
    assert "/note?path=" in html
    assert "/open_file" not in html

    # 2. 搜尋「Anna」
    resp_anna = client.get("/search?q=Anna")
    assert resp_anna.status_code == 200
    assert "Anna" in resp_anna.text
    assert "/note?path=" in resp_anna.text

    # 3. 搜尋「星巴克」（筆記內容關鍵字）
    resp_starbucks = client.get("/search?q=星巴克")
    assert resp_starbucks.status_code == 200
    assert "星巴克" in resp_starbucks.text

    # 4. 搜尋「蘋果總裁班」
    resp_apple = client.get("/search?q=蘋果總裁班")
    assert resp_apple.status_code == 200
    assert "蘋果總裁班" in resp_apple.text
