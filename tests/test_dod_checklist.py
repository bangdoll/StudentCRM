from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_note_top_dod_action_board():
    # 測試 Lucia 的筆記是否在頂部正確渲染 DoD 看板
    lucia_token = "9f4dac5a-3229-4dec-9c28-d0554ead4822"
    path = "/01.Docs/teaching/20261002 41-3.Lucia數位管理教學.md"
    resp = client.get(f"/note?path={path}&token={lucia_token}")
    assert resp.status_code == 200
    html = resp.text

    assert 'id="topDoDSection"' in html
    assert 'id="topDoDList"' in html
    assert '🥉 銅牌（及格門檻 · 3 分鐘）' in html
    assert '🥈 銀牌（實戰落地 · 15 分鐘）' in html
    assert '🥇 金牌（系統進階 · 週末挑戰）' in html
    assert 'dod-custom-checkbox' in html
    assert 'toggleTopDoDCard' in html

def test_note_peng_dod_action_board():
    # 測試彭老師的筆記是否在頂部正確渲染 DoD 看板
    peng_token = "3405cfa2-be2e-4260-a65b-b6430a3f5c8f"
    path = "/01.Docs/teaching/20261002 39-4.彭老師數位管理教學.md"
    resp = client.get(f"/note?path={path}&token={peng_token}")
    assert resp.status_code == 200
    html = resp.text

    assert 'id="topDoDSection"' in html
    assert '🥉 銅牌（及格門檻 · 3 分鐘）' in html
    assert '🥈 銀牌（實戰落地 · 15 分鐘）' in html
    assert '🥇 金牌（系統進階 · 週末挑戰）' in html
