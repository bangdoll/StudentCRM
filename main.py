from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import json
import re
import subprocess
import glob
from datetime import datetime, timedelta
import calendar
from data_gateway import StudentDataGateway

app = FastAPI()

# Paths - 支援大倉庫本機開發與 Vercel 獨立 repo 部署
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASE_DIR = os.path.dirname(APP_DIR) if os.path.isdir(os.path.join(os.path.dirname(APP_DIR), "OpenClaw")) else APP_DIR
BASE_DIR = os.getenv("OPEN_CLAW_BASE_DIR", DEFAULT_BASE_DIR)
STATIC_DIR = os.path.join(APP_DIR, "static")
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
STUDENTS_FILE = os.path.join(BASE_DIR, "OpenClaw/Data/students.json")
APPLE_CEO_FILE = os.path.join(BASE_DIR, "OpenClaw/Data/apple_ceo_class.json")
STUDENT_DOCS_DIR = os.path.join(BASE_DIR, "01.Docs/Students")
CACHE_DIR = os.getenv("STUDENTCRM_CACHE_DIR", "/tmp/studentcrm-cache" if os.getenv("VERCEL") else os.path.join(APP_DIR, "cache"))
TEACHING_DIR = os.path.join(BASE_DIR, "01.Docs/teaching")
student_gateway = StudentDataGateway(BASE_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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


def add_months(base_date: datetime, months: int) -> datetime:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


def extract_session_date(value: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
    return match.group(0) if match else ""


def normalize_attendee_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def preview_apple_ceo_attendance(program_data: dict, date: str, venue: str, attendees: list[str], note: str = "") -> dict:
    normalized_attendees = [name.strip() for name in attendees if name and name.strip()]
    student_rounds = program_data.get("student_rounds", [])
    name_to_group = {
        normalize_attendee_name(group.get("student_name", "")): group
        for group in student_rounds
    }

    warnings = []
    affected_rounds = []

    for attendee in normalized_attendees:
        group = name_to_group.get(normalize_attendee_name(attendee))
        if not group:
            warnings.append(f"找不到班務學員：{attendee}")
            continue

        rounds = group.get("rounds", [])
        latest_round = rounds[0] if rounds else None
        if not latest_round:
            new_sessions = [date] + [""] * 7
            affected_rounds.append({
                "student_name": group.get("student_name", attendee),
                "action": "create_round",
                "before": None,
                "after": {
                    "label": "新一輪 (預覽建立)",
                    "payment_status": "未收",
                    "sessions": new_sessions,
                    "attended_count": 1,
                    "remaining_count": 7,
                },
            })
            continue

        sessions = list(latest_round.get("sessions", []))
        if date in sessions:
            warnings.append(f"{group.get('student_name', attendee)} 已存在 {date} 上課紀錄")
            continue

        before_sessions = list(sessions)
        action = "append_session"
        if "" in sessions:
            sessions[sessions.index("")] = date
        else:
            action = "create_next_round"
            sessions = [date] + [""] * 7

        affected_rounds.append({
            "student_name": group.get("student_name", attendee),
            "action": action,
            "before": {
                "label": latest_round.get("label", ""),
                "sessions": before_sessions,
                "attended_count": len([item for item in before_sessions if item]),
                "remaining_count": max(0, 8 - len([item for item in before_sessions if item])),
            },
            "after": {
                "label": latest_round.get("label", "") if action == "append_session" else "新一輪 (預覽建立)",
                "sessions": sessions,
                "attended_count": len([item for item in sessions if item]),
                "remaining_count": max(0, 8 - len([item for item in sessions if item])),
            },
        })

    proposed_record = {
        "date": date,
        "venue": venue,
        "attendee_count": len(normalized_attendees),
        "attendees": normalized_attendees,
        "note": note,
    }

    return {
        "proposed_record": proposed_record,
        "affected_rounds": affected_rounds,
        "warnings": warnings,
        "summary": {
            "attendee_count": len(normalized_attendees),
            "matched_count": len(affected_rounds),
            "warning_count": len(warnings),
        },
    }


def summarize_apple_ceo_program(program_data: dict) -> dict:
    attendance_records = program_data.get("attendance_records", [])
    ledger = program_data.get("venue_ledger", [])
    student_rounds = program_data.get("student_rounds", [])
    active_participants = program_data.get("active_participants", [])

    latest_attendance = attendance_records[-1] if attendance_records else {}
    latest_ledger = ledger[-1] if ledger else {}
    latest_balance = latest_ledger.get("balance_after", 0)
    total_headcount = sum(item.get("attendee_count", 0) for item in attendance_records)
    total_sessions = len(attendance_records)
    avg_headcount = round(total_headcount / total_sessions, 1) if total_sessions else 0

    active_rounds = []
    completed_rounds = []
    followup_rounds = []
    expired_rounds = []
    expiring_soon_rounds = []
    student_statuses = []
    today = datetime.now().date()
    for student in student_rounds:
        student_active_count = 0
        student_priority_count = 0
        student_total_attended = 0
        latest_session = ""
        for round_item in student.get("rounds", []):
            sessions = round_item.get("sessions", [])
            actual_sessions = [session for session in sessions if session]
            normalized_sessions = [extract_session_date(session) for session in actual_sessions]
            normalized_sessions = [session for session in normalized_sessions if session]
            attended_count = len(actual_sessions)
            student_total_attended += attended_count
            round_item["attended_count"] = attended_count
            round_item["remaining_count"] = max(0, 8 - attended_count)
            round_item["progress_percent"] = int((attended_count / 8) * 100) if sessions else 0
            round_item["is_expired"] = False
            round_item["expiry_date"] = ""

            if normalized_sessions:
                first_session_date = datetime.strptime(normalized_sessions[0], "%Y-%m-%d").date()
                expiry_date = add_months(datetime.combine(first_session_date, datetime.min.time()), 4).date()
                round_item["expiry_date"] = expiry_date.strftime("%Y-%m-%d")
                round_item["is_expired"] = today > expiry_date
                days_until_expiry = (expiry_date - today).days
                round_item["days_until_expiry"] = days_until_expiry
                round_item["is_expiring_soon"] = 0 <= days_until_expiry <= 14
                latest_session = max([latest_session] + normalized_sessions)
            else:
                round_item["days_until_expiry"] = None
                round_item["is_expiring_soon"] = False

            if round_item["is_expired"]:
                student_priority_count += 1
                expired_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })
            elif round_item["is_expiring_soon"]:
                student_priority_count += 1
                expiring_soon_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })
            if "進行中" in round_item.get("label", ""):
                student_active_count += 1
                active_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })
            if attended_count in (6, 7):
                student_priority_count += 1
                followup_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })
            if attended_count >= 8:
                student_priority_count += 1
                completed_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })

        student_statuses.append({
            "student_name": student.get("student_name", ""),
            "active_count": student_active_count,
            "priority_count": student_priority_count,
            "total_attended": student_total_attended,
            "latest_session": latest_session,
        })

    def unique_students(records: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for item in records:
            name = item.get("student_name", "")
            if name in seen:
                continue
            seen.add(name)
            result.append(item)
        return result

    completed_students = unique_students(completed_rounds)
    followup_students = unique_students(followup_rounds)
    expiring_soon_students = unique_students(expiring_soon_rounds)
    expired_students = unique_students(expired_rounds)
    active_student_names = {item["student_name"] for item in active_rounds}
    active_students = [item for item in student_statuses if item["student_name"] in active_student_names]
    inactive_students = [item for item in student_statuses if item["student_name"] not in active_student_names]

    if latest_balance < 0:
        balance_status = "待補場地費"
        balance_note = "場地餘額已為負數，建議優先補值。"
    elif latest_balance == 0:
        balance_status = "餘額用盡"
        balance_note = "下一堂課前建議先儲值。"
    else:
        balance_status = "場地正常"
        balance_note = "場地費目前仍有可用餘額。"

    return {
        "active_participant_count": len(active_participants),
        "total_sessions": total_sessions,
        "avg_headcount": avg_headcount,
        "latest_attendance": latest_attendance,
        "latest_balance": latest_balance,
        "latest_balance_label": f"${latest_balance:,.0f}",
        "latest_session_date": latest_attendance.get("date", "尚無資料"),
        "active_rounds": active_rounds,
        "active_round_count": len(active_rounds),
        "followup_rounds": followup_rounds,
        "followup_round_count": len(followup_rounds),
        "followup_students": followup_students,
        "followup_student_count": len(followup_students),
        "completed_rounds": completed_rounds,
        "completed_round_count": len(completed_rounds),
        "completed_students": completed_students,
        "completed_student_count": len(completed_students),
        "expiring_soon_rounds": expiring_soon_rounds,
        "expiring_soon_round_count": len(expiring_soon_rounds),
        "expiring_soon_students": expiring_soon_students,
        "expiring_soon_student_count": len(expiring_soon_students),
        "expired_rounds": expired_rounds,
        "expired_round_count": len(expired_rounds),
        "expired_students": expired_students,
        "expired_student_count": len(expired_students),
        "active_students": active_students,
        "active_student_count": len(active_students),
        "inactive_students": inactive_students,
        "student_statuses": student_statuses,
        "balance_status": balance_status,
        "balance_note": balance_note,
    }


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
    if not path.startswith(BASE_DIR) or not os.path.exists(path):
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
        if "StudentCRM/cache/Lesson_" not in href and "01.Docs/teaching/Lesson_" not in href:
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


def get_student_lesson_paths(student_id: str) -> list:
    """Get sorted lesson cache paths for a student from their .md timeline."""
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return []
    file_path = os.path.join(BASE_DIR, student['file'].lstrip('/'))
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    paths = re.findall(
        r'/open_file\?path=([^\s\)\'">\n]+Lesson_\d{8}_[^\s\)\'">\n]+\.md)',
        content
    )

    def date_key(p):
        m = re.search(r'Lesson_(\d{8})_', p)
        return m.group(1) if m else ''

    return sorted(set(paths), key=date_key)


def student_id_from_path(path: str) -> str:
    """Derive student_id from a lesson cache filename."""
    fname = os.path.basename(path)
    m = re.match(r'Lesson_\d{8}_(.+)\.md', fname)
    if not m:
        return ""
    student_name = m.group(1)
    students = load_students()
    for s in students:
        if s['name'] == student_name or s['id'] == student_name.lower():
            return s['id']
        if student_name in s.get('aliases', []):
            return s['id']
    return student_name.lower()


def analyze_student_features(student_id: str) -> dict:
    """Extract features from student's historical data for AI prediction."""
    paths = get_student_lesson_paths(student_id)
    features = {
        'days_since_last_lesson': -1,
        'average_word_count': 0,
        'lessons_reviewed': 0,
    }

    if not paths:
        return features

    # Parse the latest lesson date
    latest_path = paths[-1]
    m = re.search(r'Lesson_(\d{4})(\d{2})(\d{2})_', latest_path)
    if m:
        y, mo, d = map(int, m.groups())
        latest_date = datetime(y, mo, d)
        today = datetime.now()
        features['days_since_last_lesson'] = (today - latest_date).days

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
        s['meta'] = get_student_metadata(os.path.join(BASE_DIR, s['file'].lstrip('/')))
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

    return templates.TemplateResponse("index.html", {
        "request": request,
        "students": sorted_students,
        "apple_program": apple_program["program"],
        "apple_summary": apple_summary,
    })


@app.get("/program/apple-ceo", response_class=HTMLResponse)
async def read_apple_ceo_program(request: Request):
    program_data = load_apple_ceo_program()
    summary = summarize_apple_ceo_program(program_data)
    return templates.TemplateResponse("program_apple_ceo.html", {
        "request": request,
        "program": program_data["program"],
        "venue": program_data["venue"],
        "active_participants": program_data.get("active_participants", []),
        "attendance_records": program_data.get("attendance_records", []),
        "venue_ledger": program_data.get("venue_ledger", []),
        "student_rounds": program_data.get("student_rounds", []),
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

    return templates.TemplateResponse("dashboard.html", {
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


@app.get("/student/{student_id}", response_class=HTMLResponse)
async def read_student(request: Request, student_id: str):
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return HTMLResponse(content="Student not found", status_code=404)

    file_path = os.path.join(BASE_DIR, student['file'].lstrip('/'))

    # NEW: Dynamic calculation for detail page
    if 'recurring_schedule' in student and not student.get('next_lesson'):
        doc_exceptions = get_document_exceptions(file_path)
        json_exceptions = student.get('schedule_exceptions', [])
        all_exceptions = list(set(json_exceptions + doc_exceptions))

        student['next_lesson'] = get_next_occurrence(
            student['recurring_schedule'],
            all_exceptions
        )

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parts = re.split(r"## 📅 教學時間軸 \(Lesson Timeline\)", content)
    body = parts[1] if len(parts) > 1 else ""
    body = body.replace("file://", "/open_file?path=")

    import markdown
    html_content = markdown.markdown(body, extensions=['tables'])
    html_content = inject_badges(html_content)

    student['meta'] = get_student_metadata(file_path)
    student['features'] = analyze_student_features(student_id)
    student['prediction'] = predict_student_status(student['features'], student.get('next_lesson'))
    return templates.TemplateResponse("student.html", {
        "request": request,
        "student": student,
        "timeline_html": html_content,
        "student_id": student_id,
    })


@app.get("/open_file", response_class=HTMLResponse)
async def open_file(request: Request, path: str):
    if not (os.path.exists(path) and path.startswith(BASE_DIR)):
        return HTMLResponse(content="Insecure or missing path", status_code=403)

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    import markdown
    html_content = markdown.markdown(content, extensions=['tables'])
    filename = os.path.basename(path)

    # Derive student_id from filename for prev/next
    sid = student_id_from_path(path)
    lesson_paths = get_student_lesson_paths(sid) if sid else []

    prev_path = next_path = None
    prev_label = next_label = ""

    if path in lesson_paths:
        idx = lesson_paths.index(path)
        if idx > 0:
            prev_path = lesson_paths[idx - 1]
            m = re.search(r'Lesson_(\d{4})(\d{2})(\d{2})_', prev_path)
            prev_label = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "上一堂"
        if idx < len(lesson_paths) - 1:
            next_path = lesson_paths[idx + 1]
            m = re.search(r'Lesson_(\d{4})(\d{2})(\d{2})_', next_path)
            next_label = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "下一堂"

    word_count = len(content)
    read_minutes = max(1, round(word_count / 500))

    return templates.TemplateResponse("note.html", {
        "request": request,
        "filename": filename,
        "content_html": html_content,
        "path": path,
        "student_id": sid,
        "prev_path": prev_path,
        "prev_label": prev_label,
        "next_path": next_path,
        "next_label": next_label,
        "word_count": word_count,
        "read_minutes": read_minutes,
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

    return templates.TemplateResponse("search.html", {
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
