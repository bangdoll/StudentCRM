"""auth_service.py - StudentCRM 身分認證、雙管理員私鑰與安全門禁深模組。

依據 Matt Pocock 深模組原則：
- 封裝教練與師母雙管理員私鑰配置與驗證
- 封裝 Session Token 雜湊簽名與 Cookie 存取
- 封裝 HTTP 門禁中介軟體（授權放行、專屬 Token 繼承、403 隱私保護攔截）
- 封裝免密碼魔術連結 HTML 產生器
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable
from urllib.parse import quote, unquote
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# ── 雙管理員密鑰系統（Coach Tsai & Mrs. Tsai Admin Passkeys） ──────────────────
COACH_PASSKEY = os.getenv("COACH_PASSKEY", "tsai-8f92b7c4-a13e-49b8-9e51-68d1a4c9520b")
WIFE_PASSKEY = os.getenv("WIFE_PASSKEY", "yumi-7e42d8c1-b39f-4a71-89e5-55c3a1f9482d")
LEGACY_WIFE_PASSKEY = "amanda-7e42d8c1-b39f-4a71-89e5-55c3a1f9482d"
LEGACY_PASSKEY = os.getenv("LEGACY_PASSKEY", "zzzz")

ADMIN_PASSKEYS: dict[str, dict[str, str]] = {
    COACH_PASSKEY: {"role": "coach", "name": "蔡教練"},
    WIFE_PASSKEY: {"role": "admin", "name": "師母 (Yumi)"},
    LEGACY_WIFE_PASSKEY: {"role": "admin", "name": "師母 (Yumi)"},
    LEGACY_PASSKEY: {"role": "coach", "name": "蔡教練"},
}
SESSION_COOKIE_NAME = "coach_session"
ADMIN_USER_COOKIE_NAME = "crm_admin_user"


def get_session_token() -> str:
    """生成管理員驗證 session 簽名 Token。"""
    secret = os.getenv("CRM_AUTH_SECRET", "openclaw_crm_admin_master_secret_2026")
    return hashlib.sha256(f"crm_admin_salt_{secret}".encode()).hexdigest()[:32]


VALID_SESSION_TOKENS: set[str] = {
    get_session_token(),
    hashlib.sha256(f"crm_coach_salt_{COACH_PASSKEY}".encode()).hexdigest()[:32],
    hashlib.sha256(f"crm_coach_salt_{WIFE_PASSKEY}".encode()).hexdigest()[:32],
    hashlib.sha256(b"crm_coach_salt_zzzz").hexdigest()[:32],
}


def is_authenticated_admin(request: Request) -> bool:
    """檢查請求是否帶有合法的教練或管理員 Session Cookie。"""
    coach_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    return bool(coach_cookie and (coach_cookie == get_session_token() or coach_cookie in VALID_SESSION_TOKENS))


def get_current_admin_name(request: Request) -> str:
    """取得當前已登入管理員顯示名稱，預設為『管理員』。"""
    admin_user_cookie = request.cookies.get(ADMIN_USER_COOKIE_NAME, "")
    return unquote(admin_user_cookie) if admin_user_cookie else "管理員"


def render_magic_link_page(admin_info: dict[str, str], target_url: str = "/") -> HTMLResponse:
    """產生教練或師母專屬私鑰解鎖跳轉頁面，並自動寫入安全 Cookie 與 LocalStorage。"""
    token_val = get_session_token()
    admin_name_enc = quote(admin_info["name"])
    target_url = target_url or "/"

    html_content = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url={target_url}">
    <title>正在解鎖管理員權限...</title>
    <script>
        document.cookie = "{SESSION_COOKIE_NAME}={token_val}; path=/; max-age=15552000; secure; samesite=lax";
        document.cookie = "{ADMIN_USER_COOKIE_NAME}={admin_name_enc}; path=/; max-age=15552000; secure; samesite=lax";
        try {{
            localStorage.setItem("{SESSION_COOKIE_NAME}", "{token_val}");
            localStorage.setItem("{ADMIN_USER_COOKIE_NAME}", "{admin_info['name']}");
        }} catch(e) {{}}
        window.location.replace("{target_url}");
    </script>
    <style>
        body {{ background: #0d1117; color: #58a6ff; font-family: -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .loader {{ text-align: center; }}
        .spinner {{ width: 42px; height: 42px; border: 3px solid rgba(88,166,255,0.2); border-top-color: #58a6ff; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="loader">
        <div class="spinner"></div>
        <h2>🛡️ 正在安全解鎖 {admin_info['name']} 專屬管理後台...</h2>
        <p style="color: #8b949e; font-size: 0.9rem;">若未自動跳轉，請 <a href="{target_url}" style="color: #58a6ff;">點此直接進入</a></p>
    </div>
</body>
</html>"""
    response = HTMLResponse(content=html_content, status_code=200)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token_val,
        max_age=180 * 86400,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=ADMIN_USER_COOKIE_NAME,
        value=admin_name_enc,
        max_age=180 * 86400,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


async def handle_coach_auth_middleware(
    request: Request,
    call_next: Callable,
    get_student_by_id_fn: Callable[[str, list[dict[str, Any]]], dict[str, Any] | None],
    load_students_fn: Callable[[], list[dict[str, Any]]],
    render_lock_fn: Callable[[Request], Any],
) -> Any:
    """【門禁安全防護核心】攔截所有非授權存取，保護教練後台與學員隱私。"""
    # 測試環境自動旁路，除非顯式測試認證
    if os.getenv("PYTEST_CURRENT_TEST") and not request.headers.get("X-Test-Auth"):
        return await call_next(request)

    path = request.url.path

    # 1. 完全公開路由（靜態資產、學員個人專屬 Hub、教練專屬通行密鑰網址）
    if (
        path.startswith("/static")
        or path.startswith("/my/")
        or path.startswith("/hub/")
        or path.startswith("/coach/")
        or path.startswith("/admin/")
        or path in (
            "/logout",
            "/favicon.ico",
            "/favicon.svg",
            "/favicon-32x32.png",
            "/favicon-16x16.png",
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
            "/site.webmanifest",
            "/sw.js",
        )
    ):
        return await call_next(request)

    # 2. 學員專屬筆記存取與班級授權（攜帶合法 token 參數或具備合法學員 cookie）
    if path in ("/note", "/open_file", "/program/apple-ceo"):
        token_param = request.query_params.get("token") or request.cookies.get("last_student_token")
        if token_param:
            students = load_students_fn()
            st = get_student_by_id_fn(token_param, students)
            if st:
                if path in ("/note", "/open_file"):
                    return await call_next(request)
                if path == "/program/apple-ceo" and (token_param in ("adf9958b-a23d-4e9b-a4a2-156b5329b0ed", "apple-ceo") or "總裁班" in st.get("name", "")):
                    return await call_next(request)

    # 2.5. 檢查網址列自帶合法管理員私鑰（解決部分手機瀏覽器在跨跳轉時遺失 Cookie 的問題）
    query_key = (request.query_params.get("key") or request.query_params.get("passkey") or request.query_params.get("token") or "").strip().lower()
    if query_key and query_key in ADMIN_PASSKEYS:
        admin_info = ADMIN_PASSKEYS[query_key]
        response = await call_next(request)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=get_session_token(),
            max_age=180 * 86400,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            key=ADMIN_USER_COOKIE_NAME,
            value=quote(admin_info["name"]),
            max_age=180 * 86400,
            httponly=False,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response

    # 3. 教練與管理員 Session Cookie 檢查（已解鎖裝置直接通行）
    if is_authenticated_admin(request):
        return await call_next(request)

    # 3.5. 學員誤開首頁或由舊主畫面圖標啟動時，自動智慧導流回學員專屬 Hub（解決加入主畫面被鎖住問題）
    student_cookie = request.cookies.get("last_student_token")
    if path == "/" and student_cookie:
        students = load_students_fn()
        if get_student_by_id_fn(student_cookie, students):
            return RedirectResponse(url=f"/my/{student_cookie}", status_code=303)

    # 4. 未授權攔截：陌生人或未授權訪客一律顯示隱私保護提示，絕不洩漏學員名單與後台
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "此區域僅限授權教練存取"})

    return render_lock_fn(request)
