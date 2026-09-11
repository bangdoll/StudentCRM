import pytest
from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


def test_red_loop_apple_ceo_student_token_blocked_from_program():
    """【紅燈測試 1】總裁班正式學員 (例如 Roger 黃凱亮) 帶自身合法 Token 訪問 /program/apple-ceo 不應被 403 阻擋。"""
    roger_token = "07815d8c-5d40-4d31-926e-5f74f01818a8"
    response = client.get(
        f"/program/apple-ceo?token={roger_token}",
        headers={"X-Test-Auth": "true"}
    )
    # 目前現況會回傳 403，預期應為 200 通行
    assert response.status_code == 200, f"Expected 200 for class member, got {response.status_code}"


def test_red_loop_student_view_should_not_leak_financial_sections():
    """【紅燈測試 2】學員視圖 (/my/{apple_token}) 不應洩漏教練總營收、場地費流水與學費收款明細。"""
    apple_token = "adf9958b-a23d-4e9b-a4a2-156b5329b0ed"
    response = client.get(f"/my/{apple_token}")
    assert response.status_code == 200
    html = response.text

    # 學員視圖不應包含財務數據與 HITL 管理工具
    assert 'id="financialSection"' not in html, "financialSection leaked in student view!"
    assert 'id="ledgerSection"' not in html, "ledgerSection leaked in student view!"
    assert 'id="tuitionSection"' not in html, "tuitionSection leaked in student view!"
    assert 'id="previewSection"' not in html, "previewSection (HITL) leaked in student view!"
