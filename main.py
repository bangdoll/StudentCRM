from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
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
)
from note_service import (
    NoteDetail,
    clean_markdown_frontmatter,
    extract_note_preview,
    get_note_quality,
    get_architect_insight,
    resolve_note_detail,
)

app = FastAPI()

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


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
@app.get("/apple-touch-icon-180x180.png", include_in_schema=False)
async def apple_touch_icon():
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"), media_type="image/png")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    return FileResponse(os.path.join(STATIC_DIR, "favicon-32x32.png"), media_type="image/png")


@app.get("/site.webmanifest", include_in_schema=False)
async def site_webmanifest():
    return FileResponse(os.path.join(STATIC_DIR, "site.webmanifest"), media_type="application/manifest+json")


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


@app.get("/api/students")
async def api_students():
    students = load_students()
    return {
        "count": len(students),
        "students": students,
        "sync": student_gateway.status(),
    }


@app.get("/api/students/{student_id}")
async def api_student_detail(student_id: str):
    students = load_students()
    student = next((s for s in students if s.get("id") == student_id), None)
    if not student:
        return {"status": "not_found", "student_id": student_id}
    features = analyze_student_features(student_id)
    return {
        "status": "ok",
        "student": student,
        "features": features,
        "prediction": predict_student_status(features, student.get("next_lesson")),
        "sync": student_gateway.status(),
    }


@app.get("/api/digital-management/students")
async def api_digital_management_students():
    payload = build_digital_management_profiles(include_heptabase=False)
    return {
        "status": "ok",
        "count": len(payload["students"]),
        **payload,
    }


@app.get("/api/digital-management/students/{student_id}")
async def api_digital_management_student_detail(student_id: str):
    payload = build_digital_management_profiles(include_heptabase=True)
    student = next((item for item in payload["students"] if item.get("id") == student_id), None)
    if not student:
        return {"status": "not_found", "student_id": student_id}
    return {
        "status": "ok",
        "student": student,
        "calendar_cache": payload["calendar_cache"],
        "heptabase_backup_root": payload["heptabase_backup_root"],
    }


@app.get("/api/program/apple-ceo")
async def api_apple_ceo_program():
    program_data = load_apple_ceo_program()
    return {
        **program_data,
        "summary": summarize_apple_ceo_program(program_data),
        "sync": {
            "engine": student_gateway.backend,
            "source": "apple_* Supabase tables" if student_gateway.backend == "supabase" else APPLE_CEO_FILE,
            "checked_at": datetime.now().isoformat(),
        },
    }


@app.post("/api/program/apple-ceo/preview/attendance")
async def api_preview_apple_ceo_attendance(payload: AttendancePreviewRequest):
    program_data = load_apple_ceo_program()
    preview = preview_apple_ceo_attendance(
        program_data=program_data,
        date=payload.date,
        venue=payload.venue,
        attendees=payload.attendees,
        note=payload.note,
    )
    return {
        "status": "preview_only",
        "requires_human_confirmation": True,
        "will_write": False,
        **preview,
    }




def load_students():
    return student_gateway.load_students()


def load_apple_ceo_program():
    return student_gateway.load_apple_ceo_program()


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


def load_local_digital_management_notes() -> list[dict]:
    paths = sorted(glob.glob(os.path.join(TEACHING_DIR, "*.md")))
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
            "source": "本地 teaching 檔案",
            "matched_by": matched_by,
            "matched_to_official_student": True,
        }
        notes.append(parsed)
    return notes


def load_cloud_digital_management_notes() -> list[dict]:
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
    return [note for note in notes if note.get("student_id")]


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
    if not local_notes:
        local_notes = load_cloud_digital_management_notes()
    lessons = calendar_lessons + local_notes
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

        if lesson.get("source") == "本地 teaching 檔案":
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


def get_student_teaching_notes(student: dict) -> list[dict]:
    """取得特定學員的所有教學筆記（支援本地 teaching 檔案與雲端快取）。"""
    sid = student.get("id", "")
    sname = student.get("name", "")
    aliases = student.get("aliases", [])
    target_names = {sname.lower()} | {a.lower() for a in aliases}
    is_apple_ceo = "總裁班" in sname or any("總裁班" in a for a in aliases)

    local_notes = load_local_digital_management_notes()
    if not local_notes:
        local_notes = load_cloud_digital_management_notes()

    matched = []
    seen = set()

    if is_apple_ceo:
        apple_program = load_apple_ceo_program()
        for an in apple_program.get("teaching_notes", []):
            key = an.get("path") or f"{an.get('date')}:{an.get('title')}"
            if key not in seen:
                seen.add(key)
                matched.append(an)

    for n in local_notes:
        note_sid = n.get("student_id", "")
        note_name = (n.get("student_name") or "").lower()
        if note_sid == sid or (note_name and note_name in target_names):
            key = n.get("id") or n.get("path") or f"{n.get('date')}:{n.get('title')}"
            if key not in seen:
                seen.add(key)
                matched.append(n)
    return sorted(matched, key=lambda x: x.get("date") or "", reverse=True)


def get_student_lesson_paths(student_id: str) -> list:
    """Get sorted lesson cache and teaching paths for a student."""
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return []
    
    paths = []
    file_path = os.path.join(BASE_DIR, student.get('file', '').lstrip('/'))
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        paths.extend(re.findall(
            r'/open_file\?path=([^\s\)\'">\n]+\.md)',
            content
        ))

    student_notes = get_student_teaching_notes(student)
    for n in student_notes:
        if n.get("path"):
            paths.append(n["path"])

    def date_key(p):
        fname = os.path.basename(p)
        date = parse_date_from_title(fname)
        return date.replace("-", "") if date else fname

    return sorted(set(paths), key=date_key)


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


_FEATURES_CACHE: dict[str, tuple[float, dict]] = {}
_FEATURES_CACHE_TTL = 300  # 5 minutes in-memory cache


def analyze_student_features(student_id: str, use_cache: bool = True) -> dict:
    """Extract features from student's historical data for AI prediction."""
    now_ts = time.time()
    if use_cache and student_id in _FEATURES_CACHE:
        cached_ts, cached_features = _FEATURES_CACHE[student_id]
        if now_ts - cached_ts < _FEATURES_CACHE_TTL:
            return dict(cached_features)

    paths = get_student_lesson_paths(student_id)
    features = {
        'days_since_last_lesson': -1,
        'average_word_count': 0,
        'lessons_reviewed': 0,
    }

    if paths:
        # Parse the latest lesson date
        latest_path = paths[-1]
        date_str = parse_date_from_title(os.path.basename(latest_path))
        if date_str:
            try:
                latest_date = datetime.strptime(date_str, "%Y-%m-%d")
                today = datetime.now()
                features['days_since_last_lesson'] = max(0, (today - latest_date).days)
            except ValueError:
                pass
        else:
            m = re.search(r'Lesson_(\d{4})(\d{2})(\d{2})_', latest_path)
            if m:
                y, mo, d = map(int, m.groups())
                latest_date = datetime(y, mo, d)
                today = datetime.now()
                features['days_since_last_lesson'] = max(0, (today - latest_date).days)

        # Parse average word count from the last 3 lessons
        recent_paths = paths[-3:]
        total_words = 0
        valid_lessons = 0
        for p in recent_paths:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    total_words += len(content)
                    valid_lessons += 1

        if valid_lessons > 0:
            features['average_word_count'] = total_words // valid_lessons
            features['lessons_reviewed'] = valid_lessons

    # Fallback to student metadata and cloud cached notes
    students = load_students()
    student = next((s for s in students if s.get('id') == student_id), None)
    if student:
        latest_str = student.get('latest_date') or student.get('last_lesson_date')
        if latest_str and latest_str != "未記錄":
            try:
                ld = datetime.strptime(latest_str, "%Y-%m-%d")
                meta_days = max(0, (datetime.now() - ld).days)
                if features['days_since_last_lesson'] == -1 or meta_days < features['days_since_last_lesson']:
                    features['days_since_last_lesson'] = meta_days
            except ValueError:
                pass
        if features['average_word_count'] == 0:
            student_notes = get_student_teaching_notes(student)
            total_words = 0
            valid_notes = 0
            for n in student_notes[:3]:
                c = n.get("content") or ""
                if c:
                    total_words += len(c)
                    valid_notes += 1
            if valid_notes > 0:
                features['average_word_count'] = total_words // valid_notes
                features['lessons_reviewed'] = valid_notes

    _FEATURES_CACHE[student_id] = (now_ts, dict(features))
    return features


def predict_student_status(features: dict, next_lesson: str = None) -> dict:
    """根據最後上課日期與筆記平均字數，回傳三種 AI 學習狀態燈號。"""
    days = features.get('days_since_last_lesson', -1)
    word_count = features.get('average_word_count', 0)

    if days == -1:
        return {"badge": "⚪", "status": "無預測資料", "class": "badge-placeholder", "reason": "系統中尚未找到有效的上課排程或筆記紀錄。"}

    if days <= 14:
        return {"badge": "🟢", "status": "穩定留存", "class": "badge-full", "reason": f"距離上次上課 {days} 天，仍在穩定互動區間。"}
    else:
        if word_count < 200:
            return {"badge": "🔴", "status": "高流失風險", "class": "badge-missing", "reason": f"已超過兩週未上課 ({days} 天)，且近期筆記平均字數偏低，需優先關心。"}
        else:
            return {"badge": "🧊", "status": "冰凍期 (需關心)", "class": "badge-short", "reason": f"已超過兩週未上課 ({days} 天)，但近期筆記內容仍扎實，建議主動回訪。"}


def get_document_exceptions(student_file_path: str) -> list:
    """Scan student .md file for '暫停一次' and return the associated dates."""
    exceptions = []
    if not os.path.exists(student_file_path):
        return exceptions

    try:
        with open(student_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for line in lines:
                if "暫停一次" in line:
                    # Look for date pattern YYYY-MM-DD
                    match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
                    if match:
                        exceptions.append(match.group(1))
    except Exception as e:
        print(f"DEBUG: Error scanning {student_file_path} for exceptions: {e}")

    return list(set(exceptions))


def get_next_occurrence(schedule_str: str, exceptions: list = None) -> str:
    """Calculate the next occurrence of a recurring schedule, skipping exceptions.
    Format: 'weekly:weekday:time' (weekday 0=Mon, 3=Thu)
    """
    if not schedule_str or not schedule_str.startswith("weekly:"):
        return None

    if exceptions is None:
        exceptions = []

    try:
        parts = schedule_str.split(":")
        target_weekday = int(parts[1])
        target_time = datetime.strptime(parts[2] + ":" + parts[3], "%H:%M").time()

        now = datetime.now()
        current_dt = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)

        # Calculate base offset
        days_ahead = target_weekday - current_dt.weekday()
        if days_ahead < 0 or (days_ahead == 0 and current_dt < now):
            days_ahead += 7

        next_dt = current_dt + timedelta(days=days_ahead)

        # Keep jumping 7 days if the date is in exceptions
        while next_dt.strftime("%Y-%m-%d") in exceptions:
            next_dt += timedelta(days=7)

        # Format: 2026-03-24（二）10:00
        weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
        return next_dt.strftime(f"%Y-%m-%d（{weekdays_zh[next_dt.weekday()]}）%H:%M")
    except Exception as e:
        print(f"DEBUG: Error calculating recurring schedule {schedule_str}: {e}")
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    students = load_students()

    for s in students:
        if 'recurring_schedule' in s and not s.get('next_lesson'):
            student_file = os.path.join(BASE_DIR, s['file'].lstrip('/'))
            # Combine JSON exceptions with Doc-based ones
            doc_exceptions = get_document_exceptions(student_file)
            json_exceptions = s.get('schedule_exceptions', [])
            all_exceptions = list(set(json_exceptions + doc_exceptions))

            s['next_lesson'] = get_next_occurrence(
                s['recurring_schedule'],
                all_exceptions
            )

    for s in students:
        file_path = os.path.join(BASE_DIR, s['file'].lstrip('/')) if s.get('file') else ""
        file_meta = get_student_metadata(file_path) if file_path and os.path.exists(file_path) else {}
        cloud_meta = build_cloud_student_meta(s)
        s['meta'] = {**cloud_meta, **file_meta}
        if not s['meta'].get('first_lesson_date') or s['meta']['first_lesson_date'] in ("未記錄", "TBD"):
            s['meta']['first_lesson_date'] = s.get('first_lesson_date') or "未記錄"
        if not s['meta'].get('last_lesson_date') or s['meta']['last_lesson_date'] in ("未記錄", "TBD"):
            s['meta']['last_lesson_date'] = s.get('latest_date') or "未記錄"
        if not s['meta'].get('lessons_count') or s['meta']['lessons_count'] == 0:
            s['meta']['lessons_count'] = s.get('lessons_count') or 0
        s['features'] = analyze_student_features(s['id'])
        s['prediction'] = predict_student_status(s['features'], s.get('next_lesson'))

    def get_next_lesson_sort_key(s):
        nl = s.get('next_lesson')
        name = s.get('name', 'Unknown')
        if not nl or nl == '待定':
            return (2, datetime(9999, 12, 31))

        try:
            ds = nl.split('（')[0].strip()
            ts = "00:00"
            if "）" in nl:
                time_part = nl.split("）")[-1].strip()
                if re.match(r'^\d{2}:\d{2}$', time_part):
                    ts = time_part

            dt = datetime.strptime(f"{ds} {ts}", "%Y-%m-%d %H:%M")
            now = datetime.now()

            if dt >= now:
                res = (0, dt)
            else:
                res = (1, dt)
            return res
        except Exception:
            return (2, datetime(9999, 12, 31))

    # Sort students by next lesson date (Priority: Future > Past > TBD)
    sorted_students = sorted(students, key=get_next_lesson_sort_key)

    apple_program = load_apple_ceo_program()
    apple_summary = summarize_apple_ceo_program(apple_program)

    if use_fallback_pages("index.html"):
        return render_dashboard_fallback(sorted_students, apple_summary, student_gateway.status())

    return templates.TemplateResponse(request, "index.html", {
        "request": request,
        "students": sorted_students,
        "apple_program": apple_program["program"],
        "apple_summary": apple_summary,
    })


@app.get("/program/apple-ceo", response_class=HTMLResponse)
async def read_apple_ceo_program(request: Request):
    program_data = load_apple_ceo_program()
    summary = summarize_apple_ceo_program(program_data)
    teaching_notes = program_data.get("teaching_notes", [])
    if use_fallback_pages("program_apple_ceo.html"):
        rows = "\n".join(
            f"<tr><td>{record.get('date', '')}</td><td>{record.get('venue', '')}</td><td>{record.get('attendee_count', 0)}</td></tr>"
            for record in program_data.get("attendance_records", [])[:80]
        )
        if not rows:
            rows = '<tr><td colspan="3" class="muted">尚未載入班務資料。</td></tr>'
        body = f"""
        <section class="grid">
            <div class="card"><span>活躍學員</span><strong>{summary.get('active_student_count', 0)}</strong></div>
            <div class="card"><span>續班提醒</span><strong>{summary.get('completed_student_count', 0)}</strong></div>
            <div class="card"><span>場地餘額</span><strong>{summary.get('latest_balance_label', '$0')}</strong></div>
        </section>
        <section class="card">
            <h2>{program_data.get('program', {}).get('name', '蘋果總裁班')}</h2>
            <table>
                <thead><tr><th>日期</th><th>場地</th><th>人數</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>
        """
        return render_fallback_page("蘋果總裁班", body)
    return templates.TemplateResponse(request, "program_apple_ceo.html", {
        "request": request,
        "program": program_data["program"],
        "venue": program_data["venue"],
        "active_participants": program_data.get("active_participants", []),
        "attendance_records": program_data.get("attendance_records", []),
        "venue_ledger": program_data.get("venue_ledger", []),
        "student_rounds": program_data.get("student_rounds", []),
        "tuition_records": program_data.get("tuition_records", []),
        "teaching_notes": teaching_notes,
        "summary": summary,
        "legacy_note": program_data.get("legacy_note", ""),
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    students = load_students()
    for student in students:
        student_file = os.path.join(BASE_DIR, student.get('file', '').lstrip('/'))
        student['meta'] = get_student_metadata(student_file)
        student['features'] = analyze_student_features(student['id'])
        student['prediction'] = predict_student_status(student['features'], student.get('next_lesson'))

    apple_program = load_apple_ceo_program()
    apple_summary = summarize_apple_ceo_program(apple_program)

    today = datetime.now().date()

    def parse_next_lesson(value: str):
        date_text = extract_session_date(value or "")
        if not date_text:
            return None
        try:
            return datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            return None

    upcoming_students = []
    unscheduled_students = []
    risk_students = []
    freezing_students = []
    stable_students = []

    for student in students:
        next_date = parse_next_lesson(student.get('next_lesson', ''))
        student['next_lesson_days'] = (next_date - today).days if next_date else None
        if next_date and 0 <= (next_date - today).days <= 14:
            upcoming_students.append(student)
        if not next_date:
            unscheduled_students.append(student)

        status = student.get('prediction', {}).get('status', '')
        if '高流失' in status:
            risk_students.append(student)
        elif '冰凍期' in status:
            freezing_students.append(student)
        elif '穩定留存' in status:
            stable_students.append(student)

    students.sort(key=lambda item: (
        item.get('next_lesson_days') is None,
        item.get('next_lesson_days') if item.get('next_lesson_days') is not None else 9999,
        item.get('name', ''),
    ))

    if use_fallback_pages("dashboard.html"):
        return render_dashboard_fallback(students, apple_summary, student_gateway.status())

    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "students": students,
        "student_count": len(students),
        "upcoming_students": upcoming_students,
        "unscheduled_students": unscheduled_students,
        "risk_students": risk_students,
        "freezing_students": freezing_students,
        "stable_students": stable_students,
        "apple_program": apple_program["program"],
        "apple_summary": apple_summary,
        "sync_status": student_gateway.status(),
    })


@app.get("/digital-management", response_class=HTMLResponse)
async def read_digital_management(request: Request):
    payload = build_digital_management_profiles(include_heptabase=False)
    if use_fallback_pages("digital_management.html"):
        rows = "\n".join(
            "<tr>"
            f"<td><a href='/digital-management/student/{student.get('id')}'>{html_lib.escape(student.get('name', ''))}</a></td>"
            f"<td>{html_lib.escape(str(student.get('current_lesson') or 0))}</td>"
            f"<td>{html_lib.escape(student.get('next_lesson') or '尚未排定')}</td>"
            f"<td>{len(student.get('notes', []))}</td>"
            "</tr>"
            for student in payload["students"]
        )
        body = f"""
        <section class="card">
            <p class="muted">Calendar cache: {html_lib.escape(payload['calendar_cache'])}</p>
            <table><thead><tr><th>學生</th><th>目前堂數</th><th>下次上課</th><th>筆記</th></tr></thead><tbody>{rows}</tbody></table>
        </section>
        """
        return render_fallback_page("數位管理教學", body)
    return templates.TemplateResponse(request, "digital_management.html", {
        "request": request,
        **payload,
    })


@app.get("/digital-management/student/{student_id}", response_class=HTMLResponse)
async def read_digital_management_student(request: Request, student_id: str):
    payload = build_digital_management_profiles(include_heptabase=True)
    student = next((item for item in payload["students"] if item.get("id") == student_id), None)
    if not student:
        return HTMLResponse(content="Digital management student not found", status_code=404)
    if use_fallback_pages("digital_management_student.html"):
        rows = "\n".join(
            "<tr>"
            f"<td>{html_lib.escape(note.get('date') or '')}</td>"
            f"<td>{html_lib.escape(note.get('title') or '')}</td>"
            f"<td>{html_lib.escape(note.get('source') or '')}</td>"
            "</tr>"
            for note in student.get("notes", [])
        )
        body = f"""
        <section class="card">
            <p>目前上到第 {html_lib.escape(str(student.get('current_lesson') or 0))} 堂；下次上課：{html_lib.escape(student.get('next_lesson') or '尚未排定')}</p>
            <table><thead><tr><th>日期</th><th>筆記</th><th>來源</th></tr></thead><tbody>{rows}</tbody></table>
        </section>
        """
        return render_fallback_page(student.get("name", "學生檔案"), body)
    return templates.TemplateResponse(request, "digital_management_student.html", {
        "request": request,
        "student": student,
        "calendar_cache": payload["calendar_cache"],
        "heptabase_backup_root": payload["heptabase_backup_root"],
    })





MERGED_STUDENT_REDIRECTS = {
    "d892570c-70d2-4fba-9f2e-614ba775232b": "d06bb300-4b9e-44b5-8cd3-1b47695cdee4",  # 查米 315 -> 查米
    "0e6b6b92-ebe9-4252-a6cf-3907b78700f7": "d06bb300-4b9e-44b5-8cd3-1b47695cdee4",  # Chami BNI Management 38 6 -> 查米
}


@app.get("/student/{student_id}", response_class=HTMLResponse)
async def read_student(request: Request, student_id: str):
    if student_id in MERGED_STUDENT_REDIRECTS:
        target_id = MERGED_STUDENT_REDIRECTS[student_id]
        return RedirectResponse(url=f"/student/{target_id}", status_code=301)

    students = load_students()
    student = next((s for s in students if s.get('id') == student_id), None)
    if not student:
        return HTMLResponse(content="Student not found", status_code=404)

    file_value = student.get('file') or ""
    file_path = os.path.join(BASE_DIR, file_value.lstrip('/')) if file_value else ""

    # Dynamic calculation for detail page
    if 'recurring_schedule' in student and not student.get('next_lesson'):
        doc_exceptions = get_document_exceptions(file_path) if file_path else []
        json_exceptions = student.get('schedule_exceptions', [])
        all_exceptions = list(set(json_exceptions + doc_exceptions))

        student['next_lesson'] = get_next_occurrence(
            student['recurring_schedule'],
            all_exceptions
        )

    student_notes = get_student_teaching_notes(student)

    file_meta = get_student_metadata(file_path) if file_path and os.path.exists(file_path) else {}
    cloud_meta = build_cloud_student_meta(student)
    student['meta'] = {**cloud_meta, **file_meta}
    if not student['meta'].get('first_lesson_date') or student['meta']['first_lesson_date'] in ("未記錄", "TBD"):
        student['meta']['first_lesson_date'] = student.get('first_lesson_date') or "未記錄"
    if not student['meta'].get('last_lesson_date') or student['meta']['last_lesson_date'] in ("未記錄", "TBD"):
        student['meta']['last_lesson_date'] = student.get('latest_date') or "未記錄"
    if not student['meta'].get('lessons_count') or student['meta']['lessons_count'] == 0:
        student['meta']['lessons_count'] = student.get('lessons_count') or len(student_notes)
    student['features'] = analyze_student_features(student_id)
    student['prediction'] = predict_student_status(student['features'], student.get('next_lesson'))

    if not file_path or not os.path.exists(file_path):
        teaching_records = student_gateway.load_teaching_records(student_id)
        return templates.TemplateResponse(request, "student.html", {
            "request": request,
            "student": student,
            "student_notes": student_notes,
            "timeline_html": render_cloud_student_timeline(student, teaching_records),
            "student_id": student_id,
        })

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parts = re.split(r"## 📅 教學時間軸 \(Lesson Timeline\)", content)
    body = parts[1] if len(parts) > 1 else ""
    body = body.replace("file://", "/open_file?path=")

    import markdown
    html_content = markdown.markdown(body, extensions=['tables'])
    html_content = inject_badges(html_content)

    return templates.TemplateResponse(request, "student.html", {
        "request": request,
        "student": student,
        "student_notes": student_notes,
        "timeline_html": html_content,
        "student_id": student_id,
    })


@app.get("/note", response_class=HTMLResponse)
@app.get("/open_file", response_class=HTMLResponse)
async def open_file(request: Request, path: str):
    apple_program = load_apple_ceo_program()
    apple_notes = apple_program.get("teaching_notes", [])
    records = load_cloud_digital_management_notes()
    students = load_students()

    note = resolve_note_detail(
        path_or_filename=path,
        base_dir=BASE_DIR,
        apple_notes=apple_notes,
        cloud_records=records,
        students=students,
    )

    if not note:
        return HTMLResponse(content="<h3>找不到此筆記或路徑無效 (404)</h3><p><a href='/'>返回首頁</a></p>", status_code=404)

    return templates.TemplateResponse(request, "note.html", {
        "request": request,
        **note.to_template_context()
    })



@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = ""):
    results = []
    if q.strip():
        students = load_students()
        # Build name → student_id map
        name_to_sid = {}
        for s in students:
            name_to_sid[s['name']] = s['id']
            for alias in s.get('aliases', []):
                name_to_sid[alias] = s['id']

        cache_files = glob.glob(os.path.join(CACHE_DIR, "Lesson_*.md"))
        teaching_files = glob.glob(os.path.join(TEACHING_DIR, "Lesson_*.md"))
        all_files = sorted(cache_files + teaching_files, reverse=True)

        for fpath in all_files:
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            if q.lower() not in content.lower():
                continue

            fname = os.path.basename(fpath)
            m = re.match(r'Lesson_(\d{8})_(.+)\.md', fname)
            if not m:
                continue
            date_str, student_name = m.group(1), m.group(2)
            sid = name_to_sid.get(student_name, student_name.lower())

            # First matching line as preview
            preview = ""
            for line in content.split('\n'):
                if q.lower() in line.lower():
                    preview = line.strip()[:150]
                    break

            # Title = first # heading
            title = fname
            for line in content.split('\n'):
                if line.startswith('#'):
                    title = re.sub(r'^#+\s*', '', line).strip()
                    break

            y, mo, d = date_str[:4], date_str[4:6], date_str[6:]
            results.append({
                "date": f"{y}-{mo}-{d}",
                "title": title,
                "student_name": student_name,
                "student_id": sid,
                "path": fpath,
                "preview": preview,
            })

    return templates.TemplateResponse(request, "search.html", {
        "request": request,
        "q": q,
        "results": results,
        "count": len(results),
    })


@app.get("/trigger_open")
async def trigger_open(path: str):
    if os.path.exists(path) and path.startswith(BASE_DIR):
        subprocess.run(["open", path])
        return HTMLResponse(content="<script>window.history.back();</script>")
    return {"status": "error", "message": "Insecure or missing path"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
