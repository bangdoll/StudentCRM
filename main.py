"""
StudentCRM 主入口組裝層 (main.py)
==================================
職責：應用程式組裝（FastAPI App、中介層、靜態資源、PWA 路由、全域生命週期與領域路由器掛載）。
所有核心領域邏輯皆已收攏至深模組 (Deep Modules)：
  - auth_service: 密鑰認證、Cookie 與權限防護中介層
  - student_service: 學員統計、特徵提取與換約雷達
  - apple_ceo_service: 蘋果總裁班出席、分組與專案摘要
  - schedule_service: 行程與週次遞迴解析
  - prediction_service: AI 學習狀態與流失風險預測
  - note_service: 筆記詳情解析、微行動卡片與品質診斷
  - radar_service: 成效雷達、成熟度評估與續約推進
  - hub_service: 學員自學門戶與 PWA Manifest
  - digital_management_service: 數位管理日曆、筆記整合與去重
  - student_timeline_service: 學員時光軸、評估標籤與特徵前置
"""

import os
import time
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from data_gateway import StudentDataGateway

# ── 環境路徑與基礎設定 ────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def find_base_dir(start_dir: str) -> str:
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, "OpenClaw")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return start_dir


DEFAULT_BASE_DIR = find_base_dir(APP_DIR)
BASE_DIR = os.getenv("OPEN_CLAW_BASE_DIR", DEFAULT_BASE_DIR)
STATIC_DIR = os.path.join(APP_DIR, "static")
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
STUDENT_DOCS_DIR = os.path.join(BASE_DIR, "01.Docs/Students")
CACHE_DIR = os.getenv("STUDENTCRM_CACHE_DIR", "/tmp/studentcrm-cache" if os.getenv("VERCEL") else os.path.join(APP_DIR, "cache"))
TEACHING_DIR = os.path.join(BASE_DIR, "01.Docs/teaching")
DIGITAL_MANAGEMENT_LABEL = "數位管理教學"

STUDENTS_FILE = os.path.join(BASE_DIR, "OpenClaw/Data/students.json")
if not os.path.exists(STUDENTS_FILE):
    bundled_students = os.path.join(APP_DIR, "data/students.json")
    if os.path.exists(bundled_students):
        STUDENTS_FILE = bundled_students

APPLE_CEO_FILE = os.path.join(BASE_DIR, "OpenClaw/Data/apple_ceo_class.json")
if not os.path.exists(APPLE_CEO_FILE):
    bundled_apple = os.path.join(APP_DIR, "data/apple_ceo_class.json")
    if os.path.exists(bundled_apple):
        APPLE_CEO_FILE = bundled_apple

student_gateway = StudentDataGateway(BASE_DIR)

# ── 建立 FastAPI 實例與模板掛載 ──────────────────────────────────────────────
app = FastAPI(title="StudentCRM", version="2.5.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ── 身分認證與安全門禁深模組 (auth_service) ──────────────────────────────────
from auth_service import (
    handle_coach_auth_middleware,
    is_authenticated_admin,
    get_current_admin_name,
    render_magic_link_page,
)
from student_service import get_student_by_id

# ── 蘋果總裁班服務委派 (apple_ceo_service) ──────────────────────────────────
from apple_ceo_service import (
    add_months,
    extract_session_date,
    normalize_attendee_name,
    preview_apple_ceo_attendance,
    summarize_apple_ceo_program,
    load_apple_ceo_teaching_notes,
    generate_renewal_reminder_message,
)

def load_students():
    return student_gateway.load_students()


_APPLE_PROGRAM_CACHE = {"timestamp": 0.0, "data": None}


def load_apple_ceo_program():
    now = time.time()
    if _APPLE_PROGRAM_CACHE["data"] is not None and (now - _APPLE_PROGRAM_CACHE["timestamp"] < 30.0):
        return _APPLE_PROGRAM_CACHE["data"]
    data = student_gateway.load_apple_ceo_program()
    _APPLE_PROGRAM_CACHE["timestamp"] = now
    _APPLE_PROGRAM_CACHE["data"] = data
    return data


@app.middleware("http")
async def coach_auth_middleware(request: Request, call_next):
    """【門禁安全防護】攔截所有非授權存取，委託 auth_service 進行深模組驗證。"""
    return await handle_coach_auth_middleware(
        request=request,
        call_next=call_next,
        get_student_by_id_fn=get_student_by_id,
        load_students_fn=load_students,
        render_lock_fn=lambda req: templates.TemplateResponse(req, "lock.html", {"request": req}, status_code=403),
    )


# ── 數位管理教學服務委派 (digital_management_service) ────────────────────────
import digital_management_service as _dm_svc
from digital_management_service import (
    normalize_digital_name,
    digital_student_id,
    parse_datetime,
    parse_digital_management_title,
    load_digital_management_calendar_events,
    parse_digital_management_calendar_events,
    extract_note_preview,
    parse_digital_management_note_file,
    load_local_digital_management_notes,
    load_cloud_digital_management_notes,
    latest_heptabase_backup_dir,
    search_heptabase_backup_notes,
    search_heptabase_cli_notes,
    teaching_note_identity_keys,
    merge_teaching_notes,
    format_digital_lesson_time,
    _LOCAL_NOTES_CACHE,
    _CLOUD_NOTES_CACHE,
    DIGITAL_MANAGEMENT_CALENDAR_CACHE,
    HEPTABASE_BACKUP_ROOT,
)


def build_digital_management_profiles(include_heptabase: bool = False) -> dict:
    import main as current_module
    return _dm_svc.build_digital_management_profiles(
        include_heptabase=include_heptabase,
        students_loader=lambda: current_module.load_students(),
        data_gateway=getattr(current_module, "student_gateway", student_gateway),
        calendar_events_loader=lambda: current_module.load_digital_management_calendar_events(),
        local_notes_loader=lambda: current_module.load_local_digital_management_notes(),
        cloud_notes_loader=lambda: current_module.load_cloud_digital_management_notes(),
    )


# ── 學員時間軸與前綴評估服務委派 (student_timeline_service) ────────────────────
from student_timeline_service import (
    get_student_metadata,
    parse_frontmatter_metadata,
    get_note_quality,
    get_architect_insight,
    inject_badges,
    render_cloud_student_timeline,
    build_cloud_student_meta,
    get_student_teaching_notes as _service_get_student_teaching_notes,
    get_student_lesson_paths as _service_get_student_lesson_paths,
    student_id_from_path as _service_student_id_from_path,
    analyze_student_features as _service_analyze_student_features,
)


def get_student_teaching_notes(student: dict) -> list[dict]:
    return _service_get_student_teaching_notes(
        student,
        base_dir=BASE_DIR,
        app_dir=APP_DIR,
        apple_program_loader=load_apple_ceo_program,
        local_notes_loader=load_local_digital_management_notes,
        cloud_notes_loader=load_cloud_digital_management_notes,
    )


def get_student_lesson_paths(student_id: str) -> list:
    return _service_get_student_lesson_paths(student_id, students=load_students(), base_dir=BASE_DIR)


def student_id_from_path(path: str) -> str:
    return _service_student_id_from_path(path, students=load_students())


def analyze_student_features(student_id: str, use_cache: bool = True, target_student: dict | None = None) -> dict:
    return _service_analyze_student_features(
        student_id=student_id,
        use_cache=use_cache,
        target_student=target_student,
        students=load_students(),
        base_dir=BASE_DIR,
    )


# ── PWA 與靜態圖示路由 ────────────────────────────────────────────────────────
@app.api_route("/apple-touch-icon.png", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/apple-touch-icon-precomposed.png", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/apple-touch-icon-180x180.png", methods=["GET", "HEAD"], include_in_schema=False)
async def apple_touch_icon():
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"), media_type="image/png")


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon_ico():
    return FileResponse(os.path.join(STATIC_DIR, "favicon-32x32.png"), media_type="image/png")


@app.api_route("/site.webmanifest", methods=["GET", "HEAD"], include_in_schema=False)
async def site_webmanifest():
    return FileResponse(os.path.join(STATIC_DIR, "site.webmanifest"), media_type="application/manifest+json")


@app.api_route("/sw.js", methods=["GET", "HEAD"], include_in_schema=False)
async def service_worker():
    sw_file = os.path.join(STATIC_DIR, "sw.js")
    if os.path.exists(sw_file):
        return FileResponse(
            sw_file,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )
    return HTMLResponse(content="// sw not found", status_code=404)


# ── 系統健康與同步狀態端點 ────────────────────────────────────────────────────
@app.get("/__health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/sync/status")
async def api_sync_status():
    return student_gateway.status()


class AttendancePreviewRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    venue: str = "玫瑰客廳"
    attendees: list[str] = []
    note: str = ""


# ── 後備降級頁面渲染委派 (fallback_views) ────────────────────────────────────
from fallback_views import (
    template_exists as _template_exists,
    use_fallback_pages as _use_fallback_pages,
    render_fallback_page,
    render_dashboard_fallback,
)


def template_exists(name: str) -> bool:
    return _template_exists(TEMPLATES_DIR, name)


def use_fallback_pages(name: str) -> bool:
    return _use_fallback_pages(TEMPLATES_DIR, name)


# ── 領域路由器掛載 (Domain Routers: Hub, Apple CEO, Coach, Student) ───────────
from routers import hub_router, apple_ceo_router, coach_router, student_router

app.include_router(hub_router)
app.include_router(apple_ceo_router)
app.include_router(coach_router)
app.include_router(student_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
