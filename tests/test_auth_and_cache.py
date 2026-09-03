"""tests/test_auth_and_cache.py - 測試 auth_service、hub_service 與 data_gateway 記憶體快取。"""

import os
import time
from data_gateway import StudentDataGateway, _MEMORY_CACHE, clear_gateway_memory_cache
from auth_service import (
    ADMIN_PASSKEYS,
    COACH_PASSKEY,
    WIFE_PASSKEY,
    SESSION_COOKIE_NAME,
    ADMIN_USER_COOKIE_NAME,
    get_session_token,
    VALID_SESSION_TOKENS,
    render_magic_link_page,
)
from hub_service import generate_student_manifest_data, get_merged_redirects


def test_auth_service_passkeys_and_tokens():
    """驗證雙管理員密鑰系統與 Session 雜湊簽名。"""
    assert COACH_PASSKEY in ADMIN_PASSKEYS
    assert WIFE_PASSKEY in ADMIN_PASSKEYS
    assert ADMIN_PASSKEYS[COACH_PASSKEY]["role"] == "coach"
    assert ADMIN_PASSKEYS[WIFE_PASSKEY]["role"] == "admin"

    token = get_session_token()
    assert isinstance(token, str)
    assert len(token) == 32
    assert token in VALID_SESSION_TOKENS


def test_render_magic_link_page():
    """驗證免密碼魔術連結跳轉頁與 Cookie 簽署。"""
    admin_info = {"name": "蔡教練", "role": "coach"}
    resp = render_magic_link_page(admin_info, target_url="/dashboard")
    assert resp.status_code == 200
    assert "正在安全解鎖 蔡教練 專屬管理後台" in resp.body.decode("utf-8")
    assert "/dashboard" in resp.body.decode("utf-8")

    # Check cookies from raw_headers (Starlette sets multiple Set-Cookie headers)
    set_cookies = [val.decode("latin1") for name, val in resp.raw_headers if name.lower() == b"set-cookie"]
    assert any(SESSION_COOKIE_NAME in c for c in set_cookies)
    assert any(ADMIN_USER_COOKIE_NAME in c for c in set_cookies)


def test_hub_service_manifest_generation():
    """驗證 PWA Manifest 配置生成。"""
    manifest = generate_student_manifest_data("劉邦寧", "token-12345")
    assert manifest["name"] == "劉邦寧 的專屬數位學習空間"
    assert manifest["start_url"] == "/my/token-12345"
    assert manifest["display"] == "standalone"
    assert len(manifest["icons"]) >= 3


def test_data_gateway_memory_ttl_cache(tmp_path):
    """驗證 data_gateway 的記憶體短暫快取機制。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gateway = StudentDataGateway(base_dir)

    clear_gateway_memory_cache()
    assert len(_MEMORY_CACHE) == 0

    # 第一次讀取：穿透到本地檔案並寫入快取
    students1 = gateway.load_students()
    assert len(students1) > 0
    assert len(_MEMORY_CACHE) >= 1

    # 第二次讀取：直接從記憶體快取返回
    students2 = gateway.load_students()
    assert len(students2) == len(students1)

    # 清除快取驗證
    clear_gateway_memory_cache()
    assert len(_MEMORY_CACHE) == 0


def test_sw_precache_assets_exist():
    """驗證 Service Worker 的預快取資源在實體目錄中均真實存在（杜絕 404）。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sw_path = os.path.join(base_dir, "static", "sw.js")
    assert os.path.exists(sw_path)

    with open(sw_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 確保不再含有錯誤的路徑
    assert "/static/css/style.css" not in content
    assert "/static/manifest.json" not in content

    # 確保正確路徑存在實體檔案
    assert os.path.exists(os.path.join(base_dir, "static", "style.css"))
    assert os.path.exists(os.path.join(base_dir, "static", "site.webmanifest"))
    assert os.path.exists(os.path.join(base_dir, "static", "apple-touch-icon.png"))
    assert os.path.exists(os.path.join(base_dir, "static", "favicon.svg"))
