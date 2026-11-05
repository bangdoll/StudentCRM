from fastapi.testclient import TestClient
import re
import shutil
import subprocess

import pytest

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


def test_furniture_note_dod_script_is_valid_and_initial_progress_matches_content():
    path = "/01.Docs/teaching/20261103 02.家具怡君數位管理教學.md"
    resp = client.get(f"/note?path={path}&token=e27176d0-22eb-4c16-95aa-c55fe2352bcf")
    assert resp.status_code == 200
    html = resp.text

    # 這筆筆記的銅牌子項目是 [x]，首屏不應再顯示錯誤的 0 / 3。
    assert 'id="dodTopBadge">1 / 3 完成 (33%)' in html
    assert 'data-task-id="dod_0"' in html
    assert 'onkeydown="handleTopDoDKeydown(event, this)"' in html

    # 防止再次因括號遺漏，讓整支 DoD 互動腳本在瀏覽器完全失效。
    node = shutil.which("node")
    if not node:
        pytest.skip("環境沒有 Node.js，略過 JavaScript 語法閘門")
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.DOTALL)
    dod_script = next(script for script in scripts if "initTopDoD" in script)
    checked = subprocess.run(
        [node, "--check", "-"],
        input=dod_script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
