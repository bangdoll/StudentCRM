"""
數位管理教學服務 (digital_management_service.py)
==================================================
專職處理「數位管理教學」體系之日曆事件、本地教學筆記、雲端備份與 Heptabase 搜尋整合。
依循深模組 (Deep Module) 原則，封裝跨來源去重、排程比對與學員檔案建構邏輯。
"""

import os
import json
import re
import glob
import hashlib
import subprocess
import time
from datetime import datetime

from teaching_sync import (
    resolve_student,
    parse_teaching_file,
)
from apple_ceo_service import (
    extract_session_date,
)

# ── 環境路徑與常數配置 ────────────────────────────────────────────────────────
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

# 內部快取容器
_LOCAL_NOTES_CACHE = {"timestamp": 0.0, "notes": []}
_CLOUD_NOTES_CACHE = {"timestamp": 0.0, "notes": []}


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


def load_digital_management_calendar_events(cache_path: str = "") -> list[dict]:
    target_path = cache_path or DIGITAL_MANAGEMENT_CALENDAR_CACHE
    if not os.path.exists(target_path):
        data_cache_path = os.path.join(APP_DIR, "data", "digital_management_calendar_events.json")
        bundled_cache_path = os.path.join(APP_DIR, "cache", "digital_management_calendar_events.json")
        if os.path.exists(data_cache_path):
            target_path = data_cache_path
        elif os.path.exists(bundled_cache_path):
            target_path = bundled_cache_path
    if not os.path.exists(target_path):
        return []
    try:
        with open(target_path, "r", encoding="utf-8") as f:
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


def parse_digital_management_note_file(path: str, base_dir: str = "") -> dict:
    effective_base = base_dir or BASE_DIR
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
        "url": f"/open_file?path={path}" if path.startswith(effective_base) else "",
        "path": path,
        "preview": preview,
        "source": "本地 teaching 檔案",
    }


def load_local_digital_management_notes(
    teaching_dir: str = "",
    base_dir: str = "",
    students_loader=None,
    cache_container: dict | None = None,
) -> list[dict]:
    import sys
    effective_cache = cache_container
    if effective_cache is None:
        main_mod = sys.modules.get("main")
        if main_mod and hasattr(main_mod, "_LOCAL_NOTES_CACHE"):
            effective_cache = getattr(main_mod, "_LOCAL_NOTES_CACHE")
        else:
            effective_cache = _LOCAL_NOTES_CACHE

    now = time.time()
    if effective_cache.get("notes") and (now - effective_cache.get("timestamp", 0.0) < 30.0):
        return effective_cache["notes"]

    effective_teaching_dir = teaching_dir or TEACHING_DIR
    effective_base_dir = base_dir or BASE_DIR
    paths = sorted(glob.glob(os.path.join(effective_teaching_dir, "*.md")))
    if not paths:
        return []

    if students_loader:
        students = students_loader()
    else:
        from data_gateway import StudentDataGateway
        students = StudentDataGateway(effective_base_dir).load_students()

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
            "url": f"/open_file?path={path}" if path.startswith(effective_base_dir) else "",
            "path": path,
            "preview": record.get("preview", ""),
            "content": record.get("content", ""),
            "source": "本地 teaching 檔案",
            "matched_by": matched_by,
            "matched_to_official_student": True,
        }
        notes.append(parsed)
    effective_cache["timestamp"] = now
    effective_cache["notes"] = notes
    return notes


def load_cloud_digital_management_notes(
    data_gateway=None,
    cache_container: dict | None = None,
) -> list[dict]:
    import sys
    effective_cache = cache_container
    if effective_cache is None:
        main_mod = sys.modules.get("main")
        if main_mod and hasattr(main_mod, "_CLOUD_NOTES_CACHE"):
            effective_cache = getattr(main_mod, "_CLOUD_NOTES_CACHE")
        else:
            effective_cache = _CLOUD_NOTES_CACHE

    now = time.time()
    if effective_cache.get("notes") and (now - effective_cache.get("timestamp", 0.0) < 30.0):
        return effective_cache["notes"]

    if data_gateway is not None:
        gateway = data_gateway
    else:
        main_mod = sys.modules.get("main")
        if main_mod and hasattr(main_mod, "student_gateway"):
            gateway = getattr(main_mod, "student_gateway")
        else:
            from data_gateway import StudentDataGateway
            gateway = StudentDataGateway(BASE_DIR)

    rows = gateway.load_all_teaching_records()
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


def format_digital_lesson_time(lesson: dict) -> str:
    start_dt = lesson.get("start_dt") or parse_datetime(lesson.get("start", "")) or parse_datetime(lesson.get("date", ""))
    if not start_dt:
        return lesson.get("date", "") or "未排定"
    date_part = start_dt.strftime("%Y-%m-%d")
    time_part = start_dt.strftime("%H:%M")
    return f"{date_part} {time_part}"


def build_digital_management_profiles(
    include_heptabase: bool = False,
    students_loader=None,
    data_gateway=None,
    calendar_events_loader=None,
    local_notes_loader=None,
    cloud_notes_loader=None,
) -> dict:
    if students_loader:
        official_students = students_loader()
    else:
        from data_gateway import StudentDataGateway
        official_students = StudentDataGateway(BASE_DIR).load_students()

    if calendar_events_loader:
        raw_events = calendar_events_loader()
    else:
        raw_events = load_digital_management_calendar_events()
    calendar_lessons = parse_digital_management_calendar_events(raw_events)
    for lesson in calendar_lessons:
        student, matched_by = resolve_student(lesson.get("student_name", ""), official_students)
        if student:
            lesson["student_id"] = student.get("id", lesson["student_id"])
            lesson["student_name"] = student.get("name", lesson["student_name"])
            lesson["matched_by"] = matched_by
            lesson["matched_to_official_student"] = True
        else:
            lesson["matched_to_official_student"] = False

    if local_notes_loader:
        local_notes = local_notes_loader()
    else:
        local_notes = load_local_digital_management_notes(students_loader=students_loader)

    if cloud_notes_loader:
        cloud_notes = cloud_notes_loader()
    else:
        cloud_notes = load_cloud_digital_management_notes(data_gateway=data_gateway)

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
