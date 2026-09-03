from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import json
import re
import glob
import hashlib
import html as html_lib
import subprocess
import uuid
from datetime import datetime, timedelta
import calendar
import time
from urllib.parse import quote, unquote
from data_gateway import StudentDataGateway
from teaching_sync import (
    build_student_match_index,
    resolve_student,
    normalize_match_text,
    parse_teaching_file,
    parse_date_from_title,
)
from apple_ceo_service import (
    add_months,
    extract_session_date,
    normalize_attendee_name,
    preview_apple_ceo_attendance,
    summarize_apple_ceo_program,
    load_apple_ceo_teaching_notes,
    generate_renewal_reminder_message,
)
from student_service import (
    normalize_digital_name,
    digital_student_id,
    resolve_student_by_name,
    get_student_by_id,
    build_student_features,
    calculate_student_stats,
    get_global_renewal_radar,
    generate_student_renewal_reminder,
    generate_preclass_briefing,
)
from schedule_service import (
    get_document_exceptions,
    get_next_occurrence,
    get_next_lesson_sort_key,
)
from prediction_service import (
    _FEATURES_CACHE,
    clear_features_cache,
    get_student_lesson_paths as service_get_student_lesson_paths,
    analyze_student_features as service_analyze_student_features,
    predict_student_status,
)
from note_service import (
    NoteDetail,
    clean_markdown_frontmatter,
    extract_note_preview,
    get_note_quality,
    get_architect_insight,
    resolve_note_detail,
    extract_micro_action_cards,
)

app = FastAPI()

# ── 身分認證與安全門禁深模組 (auth_service) ──────────────────────────────────
from auth_service import (
    COACH_PASSKEY,
    WIFE_PASSKEY,
    LEGACY_WIFE_PASSKEY,
    LEGACY_PASSKEY,
    ADMIN_PASSKEYS,
    SESSION_COOKIE_NAME,
    ADMIN_USER_COOKIE_NAME,
    get_session_token,
    VALID_SESSION_TOKENS,
    is_authenticated_admin,
    get_current_admin_name,
    render_magic_link_page,
    handle_coach_auth_middleware,
)


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

# Paths - 支援大倉庫本機開發與 Vercel 獨立 repo 部署
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
STUDENT_DOCS_DIR = os.path.join(BASE_DIR, "01.Docs/Students")
CACHE_DIR = os.getenv("STUDENTCRM_CACHE_DIR", "/tmp/studentcrm-cache" if os.getenv("VERCEL") else os.path.join(APP_DIR, "cache"))
TEACHING_DIR = os.path.join(BASE_DIR, "01.Docs/teaching")
DIGITAL_MANAGEMENT_LABEL = "數位管理教學"
DIGITAL_MANAGEMENT_CALENDAR_CACHE = os.getenv(
    "STUDENTCRM_DIGITAL_MANAGEMENT_CALENDAR_CACHE",
    os.path.join(CACHE_DIR, "digital_management_calendar_events.json"),
)
HEPTABASE_BACKUP_ROOT = os.getenv(
    "STUDENTCRM_HEPTABASE_BACKUP_ROOT",
    os.path.expanduser("~/Documents/文件 - bangdoll’s MacBook Air - 1/Heptabase-auto-backup"),
)
student_gateway = StudentDataGateway(BASE_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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


def template_exists(name: str) -> bool:
    return os.path.exists(os.path.join(TEMPLATES_DIR, name))


def use_fallback_pages(name: str) -> bool:
    return not template_exists(name)


def render_fallback_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Noto Sans TC", sans-serif; background: #f6f7f9; color: #18202a; }}
        header {{ padding: 28px 24px; background: #111827; color: white; }}
        main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
        a {{ color: #155eef; text-decoration: none; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
        .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
        .card strong {{ display: block; font-size: 28px; margin-top: 8px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
        th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #eef0f3; }}
        th {{ color: #5b6472; font-size: 13px; }}
        .muted {{ color: #6b7280; }}
        .nav {{ display: flex; gap: 16px; margin-top: 12px; }}
    </style>
</head>
<body>
    <header>
        <h1>{title}</h1>
        <nav class="nav">
            <a href="/dashboard">學員看板</a>
            <a href="/digital-management">數位管理教學</a>
            <a href="/program/apple-ceo">蘋果總裁班</a>
            <a href="/api/students">API</a>
        </nav>
    </header>
    <main>{body}</main>
</body>
</html>""")


def render_dashboard_fallback(students: list[dict], apple_summary: dict, sync_status: dict) -> HTMLResponse:
    rows = "\n".join(
        f"<tr><td>{student.get('name', '')}</td><td>{student.get('next_lesson') or '安排中'}</td><td>{student.get('lessons_count', 0)}</td><td>{student.get('latest_date') or '未記錄'}</td></tr>"
        for student in students[:80]
    )
    if not rows:
        rows = '<tr><td colspan="4" class="muted">尚未載入學員資料。請確認 Vercel 環境變數與 Supabase 匯入狀態。</td></tr>'

    body = f"""
    <section class="grid">
        <div class="card"><span>全部學員</span><strong>{len(students)}</strong></div>
        <div class="card"><span>續班提醒</span><strong>{apple_summary.get('completed_student_count', 0)}</strong></div>
        <div class="card"><span>場地餘額</span><strong>{apple_summary.get('latest_balance_label', '$0')}</strong></div>
        <div class="card"><span>同步引擎</span><strong style="font-size:20px">{sync_status.get('engine', 'unknown')}</strong></div>
    </section>
    <section class="card">
        <p class="muted">來源：{sync_status.get('source', '')}</p>
        <table>
            <thead><tr><th>學員</th><th>下次上課</th><th>累計堂數</th><th>最近上課</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </section>
    """
    return render_fallback_page("StudentCRM 學員行動看板", body)


class AttendancePreviewRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    venue: str = "玫瑰客廳"
    attendees: list[str] = []
    note: str = ""




@app.get("/__health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/sync/status")
async def api_sync_status():
    return student_gateway.status()


# ── 學生與專班 API 路由已委託至 routers/student.py 與 routers/apple_ceo.py ──




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


def normalize_digital_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def digital_student_id(name: str) -> str:
    normalized = normalize_digital_name(name)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    romanized = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"digital-{romanized or digest}"


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    date_text = extract_session_date(value)
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return None


def parse_digital_management_title(summary: str) -> dict:
    """Parse titles like `60-4.Kelly Woo 數位管理教學` into profile fields."""
    title = (summary or "").strip()
    if any(ex in title for ex in ["看診", "中醫看診", "中醫", "門診", "回診", "就診", "牙醫"]):
        return {}
    if DIGITAL_MANAGEMENT_LABEL not in title:
        return {}

    head = title.split(DIGITAL_MANAGEMENT_LABEL, 1)[0]
    head = head.split("@", 1)[0].strip()
    head = re.sub(r"\s+", " ", head)
    match = re.match(
        r"^(?:(?P<series>\d+)(?:\s*[-－]\s*(?P<lesson>\d*))?\s*[.．、]?\s*)?(?P<name>.+?)\s*$",
        head,
    )
    if not match:
        return {}

    name = re.sub(r"^[\s.．、-]+|[\s.．、-]+$", "", match.group("name") or "")
    if not name:
        return {}

    series_number = int(match.group("series")) if match.group("series") else None
    lesson_number = int(match.group("lesson")) if match.group("lesson") else series_number
    return {
        "student_name": name,
        "student_id": digital_student_id(name),
        "calendar_series_number": series_number,
        "lesson_number": lesson_number,
        "title": title,
    }


def load_digital_management_calendar_events() -> list[dict]:
    cache_path = DIGITAL_MANAGEMENT_CALENDAR_CACHE
    if not os.path.exists(cache_path):
        data_cache_path = os.path.join(APP_DIR, "data", "digital_management_calendar_events.json")
        bundled_cache_path = os.path.join(APP_DIR, "cache", "digital_management_calendar_events.json")
        if os.path.exists(data_cache_path):
            cache_path = data_cache_path
        elif os.path.exists(bundled_cache_path):
            cache_path = bundled_cache_path
    if not os.path.exists(cache_path):
        return []
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        events = payload.get("events", [])
    else:
        events = payload
    return [event for event in events if isinstance(event, dict)]


def parse_digital_management_calendar_events(events: list[dict]) -> list[dict]:
    lessons = []
    for event in events:
        summary = event.get("summary") or event.get("title") or event.get("display_title") or ""
        parsed = parse_digital_management_title(summary)
        if not parsed:
            continue

        start = event.get("start") or event.get("start_time") or event.get("date") or ""
        end = event.get("end") or event.get("end_time") or ""
        start_dt = parse_datetime(start)
        date_text = start_dt.strftime("%Y-%m-%d") if start_dt else extract_session_date(start)
        lessons.append({
            "id": event.get("id") or hashlib.sha1(f"{summary}:{start}".encode("utf-8")).hexdigest(),
            "student_id": parsed["student_id"],
            "student_name": parsed["student_name"],
            "date": date_text,
            "start": start,
            "end": end,
            "start_dt": start_dt,
            "title": parsed["title"],
            "lesson_number": parsed["lesson_number"],
            "calendar_series_number": parsed["calendar_series_number"],
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "url": event.get("url") or event.get("htmlLink") or event.get("display_url") or "",
            "source": "Google Calendar 快取",
        })
    return lessons


def extract_note_preview(content: str, limit: int = 280) -> str:
    if not content:
        return ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        texts = []

        def walk(node):
            if isinstance(node, dict):
                text = node.get("text")
                if isinstance(text, str):
                    texts.append(text)
                for child in node.get("content", []):
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(payload)
        preview = " ".join(texts)
    else:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        preview = " ".join(line for line in lines[:8] if not line.startswith("---"))

    return re.sub(r"\s+", " ", preview).strip()[:limit]


def parse_digital_management_note_file(path: str) -> dict:
    filename = os.path.basename(path)
    title = filename[:-3] if filename.endswith(".md") else filename
    if DIGITAL_MANAGEMENT_LABEL not in title:
        return {}

    date_match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", title)
    date_text = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else ""

    compact_title = title
    if date_match:
        compact_title = title[date_match.end():].strip(" #._-")

    parsed = parse_digital_management_title(compact_title)
    if not parsed:
        return {}

    preview = ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        preview = extract_note_preview(content)
    except OSError:
        content = ""

    return {
        "id": hashlib.sha1(path.encode("utf-8")).hexdigest(),
        "student_id": parsed["student_id"],
        "student_name": parsed["student_name"],
        "date": date_text,
        "start": date_text,
        "end": "",
        "start_dt": parse_datetime(date_text),
        "title": parsed["title"],
        "lesson_number": parsed["lesson_number"],
        "calendar_series_number": parsed["calendar_series_number"],
        "location": "",
        "description": "",
        "url": f"/open_file?path={path}" if path.startswith(BASE_DIR) else "",
        "path": path,
        "preview": preview,
        "source": "本地 teaching 檔案",
    }


_LOCAL_NOTES_CACHE = {"timestamp": 0.0, "notes": []}
_CLOUD_NOTES_CACHE = {"timestamp": 0.0, "notes": []}


def load_local_digital_management_notes() -> list[dict]:
    now = time.time()
    if _LOCAL_NOTES_CACHE["notes"] and (now - _LOCAL_NOTES_CACHE["timestamp"] < 30.0):
        return _LOCAL_NOTES_CACHE["notes"]

    paths = sorted(glob.glob(os.path.join(TEACHING_DIR, "*.md")))
    if not paths:
        return []
    students = load_students()
    notes = []
    for path in paths:
        record = parse_teaching_file(path)
        if not record:
            continue
        student, matched_by = resolve_student(record.get("student_name", ""), students)
        if not student:
            continue
        lesson_sub = record.get("lesson_sub")
        parsed = {
            "id": record.get("card_id", hashlib.sha1(path.encode("utf-8")).hexdigest()),
            "student_id": student.get("id", ""),
            "student_name": student.get("name", record.get("student_name", "")),
            "date": record.get("date", ""),
            "start": record.get("date", ""),
            "end": "",
            "start_dt": parse_datetime(record.get("date", "")),
            "title": record.get("title", "").lstrip("#"),
            "lesson_number": record.get("lesson_num"),
            "calendar_series_number": record.get("lesson_num"),
            "lesson_sub": lesson_sub,
            "location": "",
            "description": "",
            "url": f"/open_file?path={path}" if path.startswith(BASE_DIR) else "",
            "path": path,
            "preview": record.get("preview", ""),
            "content": record.get("content", ""),
            "source": "本地 teaching 檔案",
            "matched_by": matched_by,
            "matched_to_official_student": True,
        }
        notes.append(parsed)
    _LOCAL_NOTES_CACHE["timestamp"] = now
    _LOCAL_NOTES_CACHE["notes"] = notes
    return notes


def load_cloud_digital_management_notes() -> list[dict]:
    now = time.time()
    if _CLOUD_NOTES_CACHE["notes"] and (now - _CLOUD_NOTES_CACHE["timestamp"] < 30.0):
        return _CLOUD_NOTES_CACHE["notes"]

    rows = student_gateway.load_all_teaching_records()
    if isinstance(rows, dict) and "records" in rows:
        rows = rows["records"]
    if not isinstance(rows, list):
        rows = []
    notes = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        source = row.get("source") or raw.get("source") or "Supabase teaching_records"
        if source == "local_teaching":
            source = "本地 teaching 檔案"
        preview = row.get("preview") or raw.get("preview", "")
        content_text = row.get("content") or raw.get("content", "")
        path = row.get("path") or raw.get("path", "")
        date_text = row.get("date", "") or raw.get("date", "")
        title = row.get("title", "") or raw.get("title", "")
        notes.append({
            "id": row.get("id", "") or row.get("card_id", ""),
            "student_id": row.get("student_id", ""),
            "student_name": row.get("student_name", ""),
            "date": date_text,
            "start": date_text,
            "end": "",
            "start_dt": parse_datetime(date_text),
            "title": title.lstrip("#"),
            "lesson_number": row.get("lesson_num") or raw.get("lesson_num"),
            "calendar_series_number": row.get("lesson_num") or raw.get("lesson_num"),
            "lesson_sub": row.get("lesson_sub") or raw.get("lesson_sub"),
            "location": "",
            "description": "",
            "url": row.get("url", "") or raw.get("url", ""),
            "path": path,
            "preview": preview,
            "content": content_text,
            "source": source,
            "matched_by": row.get("matched_by") or raw.get("matched_by", ""),
            "matched_to_official_student": bool(row.get("student_id")),
        })
    result = [note for note in notes if note.get("student_id")]
    _CLOUD_NOTES_CACHE["timestamp"] = now
    _CLOUD_NOTES_CACHE["notes"] = result
    return result


def latest_heptabase_backup_dir() -> str:
    if not os.path.isdir(HEPTABASE_BACKUP_ROOT):
        return ""
    candidates = [
        os.path.join(HEPTABASE_BACKUP_ROOT, item)
        for item in os.listdir(HEPTABASE_BACKUP_ROOT)
        if item.startswith("Heptabase-Data-Backup-")
    ]
    dirs = [path for path in candidates if os.path.isdir(path)]
    return max(dirs, key=os.path.getmtime) if dirs else ""


def search_heptabase_backup_notes(student_name: str, limit: int = 12) -> list[dict]:
    target_dir = latest_heptabase_backup_dir()
    if not target_dir:
        return []

    candidate_dirs = [
        os.path.join(target_dir, "Card Library"),
        os.path.join(target_dir, "Journal"),
    ]
    normalized_name = normalize_digital_name(student_name)
    matches = []
    for root_dir in candidate_dirs:
        if not os.path.isdir(root_dir):
            continue
        for root, _, files in os.walk(root_dir):
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                path = os.path.join(root, filename)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError:
                    continue
                normalized_content = normalize_digital_name(content + " " + filename)
                if DIGITAL_MANAGEMENT_LABEL not in content and DIGITAL_MANAGEMENT_LABEL not in filename:
                    continue
                if normalized_name not in normalized_content:
                    continue
                parsed = parse_digital_management_note_file(path)
                if not parsed:
                    parsed = {
                        "id": hashlib.sha1(path.encode("utf-8")).hexdigest(),
                        "student_id": digital_student_id(student_name),
                        "student_name": student_name,
                        "date": extract_session_date(filename),
                        "title": filename[:-3],
                        "lesson_number": None,
                        "path": path,
                        "url": f"/open_file?path={path}",
                        "preview": " ".join(content.splitlines()[:6])[:280],
                        "source": "Heptabase 本地備份",
                    }
                parsed["source"] = "Heptabase 本地備份"
                matches.append(parsed)

    return sorted(matches, key=lambda item: item.get("date") or "", reverse=True)[:limit]


def search_heptabase_cli_notes(student_name: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    bun_path = os.getenv("STUDENTCRM_BUN_PATH", "/Users/aios/.bun/bin/bun")
    cli_path = os.getenv(
        "STUDENTCRM_HEPTABASE_CLI_PATH",
        "/Users/aios/.bun/install/global/node_modules/heptabase-cli/heptabase-cli.ts",
    )
    if not os.path.exists(bun_path) or not os.path.exists(cli_path):
        return [], ["找不到 heptabase-cli 或 bun，已改用本地檔案/備份。"]

    query = f"{student_name} {DIGITAL_MANAGEMENT_LABEL}"
    try:
        completed = subprocess.run(
            [
                bun_path,
                cli_path,
                "semantic-search-objects",
                "--queries", query,
                "--result-object-types", "card,journal",
                "--output", "json",
            ],
            capture_output=True,
            text=True,
            timeout=18,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], [f"heptabase-cli 查詢失敗：{exc}"]

    if completed.returncode != 0 or not completed.stdout.strip():
        detail = (completed.stderr or completed.stdout or "沒有回傳資料").strip()[:240]
        return [], [f"heptabase-cli 沒有可用結果：{detail}"]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [], ["heptabase-cli 回傳不是 JSON，已略過即時結果。"]

    candidates = payload if isinstance(payload, list) else payload.get("results", [])
    notes = []
    for item in candidates[:limit]:
        title = item.get("title") or item.get("name") or ""
        object_id = item.get("id") or item.get("object_id") or ""
        object_type = item.get("type") or item.get("object_type") or "card"
        if not object_id:
            continue
        notes.append({
            "id": f"heptabase-{object_id}",
            "student_id": digital_student_id(student_name),
            "student_name": student_name,
            "date": extract_session_date(title),
            "title": title or "Heptabase 教學筆記",
            "lesson_number": None,
            "path": f"heptabase://{object_type}/{object_id}",
            "url": "",
            "preview": item.get("preview") or item.get("content") or "",
            "source": "heptabase-cli",
        })
    return notes, [f"heptabase-cli query: {query}"]


def teaching_note_identity_keys(note: dict) -> list[tuple]:
    """建立跨本地／雲端來源可共用的教學筆記去重鍵。"""
    keys = []
    student_id = str(note.get("student_id") or "")
    note_id = str(note.get("id") or note.get("card_id") or "")
    path = str(note.get("path") or "")
    if note_id:
        keys.append(("id", note_id))
    if path:
        keys.append(("path", path))
    keys.append((
        "fields",
        student_id,
        str(note.get("date") or ""),
        str(note.get("lesson_number") or note.get("lesson_num") or ""),
        str(note.get("lesson_sub") or ""),
        normalize_digital_name(note.get("title", "")),
    ))
    return keys


def merge_teaching_notes(*note_groups: list[dict]) -> list[dict]:
    """合併各來源教學筆記，保留第一個來源的完整內容並去除重複。"""
    merged = []
    seen = set()
    for notes in note_groups:
        for note in notes or []:
            if not isinstance(note, dict):
                continue
            identity_keys = teaching_note_identity_keys(note)
            if any(key in seen for key in identity_keys):
                continue
            seen.update(identity_keys)
            merged.append(note)
    return merged


def build_digital_management_profiles(include_heptabase: bool = False) -> dict:
    official_students = load_students()
    calendar_lessons = parse_digital_management_calendar_events(load_digital_management_calendar_events())
    for lesson in calendar_lessons:
        student, matched_by = resolve_student(lesson.get("student_name", ""), official_students)
        if student:
            lesson["student_id"] = student.get("id", lesson["student_id"])
            lesson["student_name"] = student.get("name", lesson["student_name"])
            lesson["matched_by"] = matched_by
            lesson["matched_to_official_student"] = True
        else:
            lesson["matched_to_official_student"] = False
    local_notes = load_local_digital_management_notes()
    cloud_notes = load_cloud_digital_management_notes()
    teaching_notes = merge_teaching_notes(local_notes, cloud_notes)
    lessons = calendar_lessons + teaching_notes
    teaching_note_object_ids = {id(note) for note in teaching_notes}
    now = datetime.now()
    profiles: dict[str, dict] = {}

    for lesson in lessons:
        student_id = lesson["student_id"]
        profile = profiles.setdefault(student_id, {
            "id": student_id,
            "name": lesson["student_name"],
            "tags": [DIGITAL_MANAGEMENT_LABEL],
            "lessons": [],
            "notes": [],
            "current_lesson": 0,
            "next_lesson": "",
            "next_lesson_dt": None,
            "latest_lesson_date": "",
            "source_summary": [],
        })

        if id(lesson) in teaching_note_object_ids:
            profile["notes"].append(lesson)
        else:
            profile["lessons"].append(lesson)

        source = lesson.get("source", "")
        if source and source not in profile["source_summary"]:
            profile["source_summary"].append(source)

    for profile in profiles.values():
        timeline_items = []
        seen_lesson_keys = set()
        for item in profile["lessons"] + profile["notes"]:
            key = item.get("id") or item.get("path") or f"{item.get('date')}:{item.get('title')}"
            if key in seen_lesson_keys:
                continue
            seen_lesson_keys.add(key)
            timeline_items.append(item)

        lessons_sorted = sorted(
            timeline_items,
            key=lambda item: item.get("start_dt") or parse_datetime(item.get("date", "")) or datetime.min,
        )
        notes_sorted = sorted(profile["notes"], key=lambda item: item.get("date") or "", reverse=True)
        past_lessons = [
            item for item in lessons_sorted
            if (item.get("start_dt") or parse_datetime(item.get("date", "")) or datetime.min) <= now
        ]
        future_lessons = [
            item for item in lessons_sorted
            if (item.get("start_dt") or parse_datetime(item.get("date", "")) or datetime.min) >= now
        ]
        numbered_past = [item.get("lesson_number") or 0 for item in past_lessons]
        profile["current_lesson"] = max(numbered_past) if numbered_past else 0
        profile["latest_lesson_date"] = past_lessons[-1].get("date", "") if past_lessons else ""
        if future_lessons:
            next_item = future_lessons[0]
            profile["next_lesson"] = format_digital_lesson_time(next_item)
            profile["next_lesson_dt"] = next_item.get("start_dt")

        note_keys = {(item.get("date"), normalize_digital_name(item.get("title", ""))) for item in notes_sorted}
        for lesson in lessons_sorted:
            key = (lesson.get("date"), normalize_digital_name(lesson.get("title", "")))
            if lesson.get("source") != "本地 teaching 檔案" and key not in note_keys:
                matching_note = next(
                    (
                        note for note in notes_sorted
                        if note.get("date") == lesson.get("date")
                        and normalize_digital_name(profile["name"]) in normalize_digital_name(note.get("title", ""))
                    ),
                    None,
                )
                if matching_note:
                    lesson["note"] = matching_note

        profile["lessons"] = sorted(lessons_sorted, key=lambda item: item.get("date") or "", reverse=True)
        profile["notes"] = notes_sorted

        if include_heptabase and os.getenv("STUDENTCRM_ENABLE_HEPTABASE_LOOKUP", "").strip() == "1":
            cli_notes, cli_diagnostics = search_heptabase_cli_notes(profile["name"])
            backup_notes = search_heptabase_backup_notes(profile["name"])
            merged = cli_notes + backup_notes + profile["notes"]
            seen = set()
            deduped = []
            for note in merged:
                key = note.get("path") or note.get("id")
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(note)
            profile["notes"] = sorted(deduped, key=lambda item: item.get("date") or "", reverse=True)
            profile["heptabase_diagnostics"] = cli_diagnostics
        elif include_heptabase:
            profile["heptabase_diagnostics"] = [
                "Heptabase 深度查詢預設關閉；設定 STUDENTCRM_ENABLE_HEPTABASE_LOOKUP=1 後會嘗試 heptabase-cli 與本地備份。"
            ]

    sorted_profiles = sorted(
        profiles.values(),
        key=lambda item: (
            item.get("next_lesson_dt") is None,
            item.get("next_lesson_dt") or datetime.max,
            item.get("name", ""),
        ),
    )
    for profile in sorted_profiles:
        profile.pop("next_lesson_dt", None)
    return {
        "students": sorted_profiles,
        "calendar_event_count": len(calendar_lessons),
        "local_note_count": len(local_notes),
        "teaching_note_count": len(teaching_notes),
        "calendar_cache": DIGITAL_MANAGEMENT_CALENDAR_CACHE,
        "heptabase_backup_root": HEPTABASE_BACKUP_ROOT,
    }


def format_digital_lesson_time(lesson: dict) -> str:
    start_dt = lesson.get("start_dt") or parse_datetime(lesson.get("start", "")) or parse_datetime(lesson.get("date", ""))
    if not start_dt:
        return lesson.get("date", "") or "未排定"
    date_part = start_dt.strftime("%Y-%m-%d")
    time_part = start_dt.strftime("%H:%M")
    return f"{date_part} {time_part}"





# 蘋果總裁班業務邏輯已統一收攏至 apple_ceo_service.py 深模組


def get_student_metadata(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r"---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return parse_frontmatter_metadata(match.group(1))


def parse_frontmatter_metadata(frontmatter: str) -> dict:
    """Parse the small YAML subset used by student profile frontmatter."""
    metadata = {}
    current_list_key = None

    for raw_line in frontmatter.splitlines():
        if not raw_line.strip():
            continue

        stripped = raw_line.strip()
        if stripped.startswith("- ") and current_list_key:
            metadata.setdefault(current_list_key, []).append(
                stripped[2:].strip().strip('"').strip("'")
            )
            continue

        current_list_key = None
        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not value:
            metadata[key] = []
            current_list_key = key
            continue

        value = value.strip('"').strip("'")
        if value.isdigit():
            metadata[key] = int(value)
        else:
            metadata[key] = value

    return metadata


def get_note_quality(path: str) -> tuple:
    """Return (emoji, css_class, label) for a lesson file."""
    if not path or not os.path.exists(path):
        return "❌", "badge-missing", "找不到文件"
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    length = len(content)
    if length > 800:
        return "✅", "badge-full", f"{length} 字"
    elif length > 200:
        return "⚠️", "badge-short", f"{length} 字（待補充）"
    else:
        return "📄", "badge-placeholder", "佔位文件"


def get_architect_insight(path: str) -> dict:
    """Extract cognitive level and assessment from the note."""
    if not os.path.exists(path):
        return {"level": "unknown", "badge": "❓", "class": "badge-unknown", "snippet": ""}

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 簡單分析邏輯 (與 knowledge_syncer 同步)
    structure_words = ["結構", "制度", "系統", "框架", "門戶", "地基", "本質"]
    tool_words = ["按鈕", "工具", "功能", "教學", "操作", "設定", "手機"]

    s_count = sum(content.count(w) for w in structure_words)
    t_count = sum(content.count(w) for w in tool_words)

    level = "structure" if s_count > t_count else "tool"
    badge = "🏗️" if level == "structure" else "🔧"
    cls = "badge-structure" if level == "structure" else "badge-tool"
    label = "架構思維" if level == "structure" else "工具思維"

    # 提取診斷摘要 (如果有)
    diag_match = re.search(r"#### 1. 結構偏移點 (.*?)(?=\n####|$)", content, re.DOTALL)
    snippet = diag_match.group(1).split("\n- ")[1].split("：")[0] if diag_match and "\n- " in diag_match.group(1) else ""

    return {"level": level, "badge": badge, "class": cls, "label": label, "snippet": snippet}


def inject_badges(html: str) -> str:
    """Inject quality AND architect badges after lesson links."""
    def replace_link(m):
        full_tag = m.group(0)
        href = m.group(1)
        if (
            "cache/Lesson_" not in href
            and "teaching/Lesson_" not in href
            and "01.Docs/teaching" not in href
            and "StudentCRM/cache/Lesson_" not in href
        ):
            return full_tag
        path_match = re.search(r'path=([^\s"&]+)', href)
        if not path_match:
            return full_tag
        path = path_match.group(1)

        # 質量標籤
        q_emoji, q_cls, q_label = get_note_quality(path)
        q_html = f'<span class="note-badge {q_cls}" title="{q_label}">{q_emoji}</span>'

        # 架構師見解標籤
        insight = get_architect_insight(path)
        i_html = f'<span class="insight-badge {insight["class"]}" title="{insight["label"]}">{insight["badge"]} {insight["label"]}</span>'

        return f'{full_tag} {q_html} {i_html}'

    return re.sub(r'<a href="([^"]+)">[^<]+</a>', replace_link, html)


def render_cloud_student_timeline(student: dict, teaching_records: list[dict]) -> str:
    rows = []
    for record in teaching_records[:20]:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        focus = raw.get("focus") or raw.get("transcript") or ""
        rows.append(
            "<tr>"
            f"<td>{html_lib.escape(str(record.get('date') or '未記錄'))}</td>"
            f"<td>{html_lib.escape(str(record.get('lesson_num') or ''))}</td>"
            f"<td>{html_lib.escape(str(record.get('title') or '教學紀錄'))}</td>"
            f"<td>{html_lib.escape(str(focus[:80]))}</td>"
            "</tr>"
        )

    table_body = "\n".join(rows)
    if not table_body:
        table_body = '<tr><td colspan="4">尚未在雲端資料庫找到課後紀錄；目前先顯示學員摘要。</td></tr>'

    tags = "、".join(student.get("tags", [])) if isinstance(student.get("tags"), list) else ""
    latest_date = html_lib.escape(str(student.get('latest_date') or '未記錄'))
    next_lesson = html_lib.escape(str(student.get('next_lesson') or '尚未安排'))
    lessons_count = html_lib.escape(str(student.get('lessons_count', 0)))
    recurring_schedule = html_lib.escape(str(student.get('recurring_schedule') or '未設定'))
    tag_label = html_lib.escape(tags or '無')
    return f"""
    <section>
        <p><strong>雲端摘要模式</strong>：雲端部署未包含本地時光軸檔案，目前改由雲端資料庫顯示。</p>
        <table>
            <tbody>
                <tr><th>最近上課</th><td>{latest_date}</td></tr>
                <tr><th>下次上課</th><td>{next_lesson}</td></tr>
                <tr><th>累計堂數</th><td>{lessons_count}</td></tr>
                <tr><th>固定排程</th><td>{recurring_schedule}</td></tr>
                <tr><th>標籤</th><td>{tag_label}</td></tr>
            </tbody>
        </table>
    </section>
    <section>
        <h3>雲端課後紀錄</h3>
        <table>
            <thead>
                <tr><th>日期</th><th>堂數</th><th>標題</th><th>重點</th></tr>
            </thead>
            <tbody>{table_body}</tbody>
        </table>
    </section>
    """


def build_cloud_student_meta(student: dict) -> dict:
    latest = student.get("latest_date") or student.get("last_lesson_date") or "未記錄"
    return {
        "hardware": [],
        "first_lesson_date": student.get("first_lesson_date") or "未記錄",
        "lessons_count": student.get("lessons_count", 0),
        "last_lesson_date": latest,
        "latest_date": latest,
    }


from hub_service import (
    get_merged_redirects as service_get_merged_redirects,
    get_student_teaching_notes as service_get_student_teaching_notes,
    generate_student_manifest_data,
    load_all_practice_cards,
    get_random_practice_card,
)


def get_student_teaching_notes(student: dict) -> list[dict]:
    """取得特定學員的所有教學筆記（委託 hub_service 深模組進行多來源去重合併）。"""
    return service_get_student_teaching_notes(
        student,
        base_dir=BASE_DIR,
        app_dir=APP_DIR,
        apple_program_loader=load_apple_ceo_program,
        local_notes_loader=lambda: load_local_digital_management_notes(),
        cloud_notes_loader=lambda: load_cloud_digital_management_notes(),
    )


def get_student_lesson_paths(student_id: str) -> list:
    """Get sorted lesson cache and teaching paths for a student."""
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return []
    student_notes = get_student_teaching_notes(student)
    return service_get_student_lesson_paths(student, BASE_DIR, student_notes)


def student_id_from_path(path: str) -> str:
    """Derive student_id from a lesson cache filename or teaching note path."""
    fname = os.path.basename(path)
    m = re.match(r'Lesson_\d{8}_(.+)\.md', fname)
    students = load_students()
    if m:
        student_name = m.group(1)
        for s in students:
            if s['name'] == student_name or s['id'] == student_name.lower():
                return s['id']
            if student_name in s.get('aliases', []):
                return s['id']
        return student_name.lower()

    rec = parse_teaching_file(path)
    if rec and rec.get("student_name"):
        student, _ = resolve_student(rec["student_name"], students)
        if student:
            return student.get("id", "")
    return ""


def analyze_student_features(student_id: str, use_cache: bool = True, target_student: dict | None = None) -> dict:
    """Extract features from student's historical data for AI prediction."""
    if target_student is not None:
        student = target_student
    else:
        students = load_students()
        student = next((s for s in students if s.get('id') == student_id), None)
    if not student:
        return {
            'days_since_last_lesson': -1,
            'average_word_count': 0,
            'lessons_reviewed': 0,
        }
    student_notes = get_student_teaching_notes(student)
    return service_analyze_student_features(student, BASE_DIR, student_notes, use_cache=use_cache)


# ── 領域路由器掛載 (Domain Routers: Coach, Student, Apple CEO, Learning Hub) ──
from routers import hub_router, apple_ceo_router, coach_router, student_router

app.include_router(hub_router)
app.include_router(apple_ceo_router)
app.include_router(coach_router)
app.include_router(student_router)




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
