import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


def repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "OpenClaw").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


TABLE_COLUMNS = {
    "students": [
        "id",
        "name",
        "aliases",
        "file",
        "lessons_count",
        "latest_date",
        "next_lesson",
        "tags",
        "recurring_schedule",
        "schedule_exceptions",
        "raw",
    ],
    "teaching_records": [
        "id",
        "student_id",
        "student_name",
        "title",
        "date",
        "lesson_num",
        "lesson_sub",
        "created",
        "edited",
        "raw",
    ],
    "apple_programs": [
        "id",
        "name",
        "url",
        "description",
        "schedule",
        "capacity",
        "round_size",
        "price_per_student",
        "validity_rule",
        "leave_rule",
        "join_rule",
        "raw",
    ],
    "apple_venues": [
        "id",
        "program_id",
        "name",
        "address",
        "parking",
        "metro",
        "cost_per_person",
        "raw",
    ],
    "apple_attendance_records": [
        "id",
        "program_id",
        "date",
        "venue",
        "attendee_count",
        "attendees",
        "note",
        "raw",
    ],
    "apple_venue_ledger": [
        "id",
        "program_id",
        "date",
        "type",
        "amount",
        "payer",
        "headcount",
        "note",
        "balance_after",
        "raw",
    ],
    "apple_student_rounds": [
        "id",
        "program_id",
        "student_name",
        "label",
        "payment_status",
        "sessions",
        "attended_count",
        "sort_order",
        "raw",
    ],
}

COLUMN_DEFAULTS: dict[str, Any] = {
    "aliases": [],
    "tags": [],
    "schedule_exceptions": [],
    "sessions": [],
    "attendees": [],
    "lessons_count": 0,
    "round_size": 8,
    "price_per_student": 0,
    "cost_per_person": 0,
    "attendee_count": 0,
    "amount": 0,
    "balance_after": 0,
    "attended_count": 0,
    "sort_order": 0,
}


def normalize_rows(table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = TABLE_COLUMNS.get(table)
    if not columns:
        return rows
    return [
        {column: row[column] if column in row and row[column] is not None else COLUMN_DEFAULTS.get(column) for column in columns}
        for row in rows
    ]


def supabase_upsert(url: str, key: str, table: str, rows: list[dict[str, Any]], dry_run: bool) -> None:
    rows = normalize_rows(table, rows)
    if dry_run:
        print(f"[DRY-RUN] 會 upsert {len(rows)} 筆至 {table}")
        return

    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    for batch in chunked(rows, 100):
        response = requests.post(endpoint, headers=headers, json=batch, timeout=30)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            print(f"{table} 寫入失敗：{response.status_code} {response.text}", file=sys.stderr)
            raise exc


def supabase_delete(url: str, key: str, table: str, query: str = "") -> None:
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    if query:
        endpoint = f"{endpoint}?{query}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    response = requests.delete(endpoint, headers=headers, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(f"{table} 刪除失敗：{response.status_code} {response.text}", file=sys.stderr)
        raise exc


def supabase_get(url: str, key: str, query_path: str) -> list[dict[str, Any]]:
    endpoint = f"{url.rstrip('/')}/rest/v1/{query_path}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    response = requests.get(endpoint, headers=headers, timeout=30)
    try:
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"Supabase 查詢失敗 ({query_path})：{exc}", file=sys.stderr)
        return []


def supabase_sync_students(url: str, key: str, students_data: list[dict[str, Any]], dry_run: bool) -> None:
    canonical_ids = {s["id"] for s in students_data}
    if not dry_run:
        supa_students = supabase_get(url, key, "students?select=id")
        extra_ids = [s["id"] for s in supa_students if s.get("id") not in canonical_ids]
        if extra_ids:
            print(f"發現 {len(extra_ids)} 位過期/已整併的幽靈學員，正在自 Supabase 清理...")
            for eid in extra_ids:
                supabase_delete(url, key, "students", f"id=eq.{quote(eid)}")
    for s in students_data:
        if not isinstance(s.get("raw"), dict):
            s["raw"] = {}
        if s.get("first_lesson_date"):
            s["raw"]["first_lesson_date"] = s["first_lesson_date"]
        if s.get("file"):
            s["raw"]["file"] = s["file"]
    supabase_upsert(url, key, "students", students_data, dry_run=dry_run)


def supabase_replace_apple_payload(url: str, key: str, apple_payload: dict[str, list[dict[str, Any]]], dry_run: bool) -> None:
    delete_order = [
        "apple_student_rounds",
        "apple_venue_ledger",
        "apple_attendance_records",
        "apple_venues",
        "apple_programs",
    ]
    upsert_order = [
        "apple_programs",
        "apple_venues",
        "apple_attendance_records",
        "apple_venue_ledger",
        "apple_student_rounds",
    ]

    if dry_run:
        for table in delete_order:
            print(f"[DRY-RUN] 會清除 {table} 中 program_id/id = apple-ceo 的舊資料")
        for table in upsert_order:
            print(f"[DRY-RUN] 會 upsert {len(apple_payload.get(table, []))} 筆至 {table}")
        return

    for table in delete_order:
        query = "id=eq.apple-ceo" if table == "apple_programs" else "program_id=eq.apple-ceo"
        supabase_delete(url, key, table, query)

    for table in upsert_order:
        rows = apple_payload.get(table, [])
        if rows:
            supabase_upsert(url, key, table, rows, dry_run=False)


def supabase_replace_teaching_records(url: str, key: str, rows: list[dict[str, Any]], dry_run: bool) -> None:
    if dry_run:
        print("[DRY-RUN] 會清除 teaching_records 後重建本地 teaching 匯入資料")
        print(f"[DRY-RUN] 會 upsert {len(rows)} 筆至 teaching_records")
        return

    supabase_delete(url, key, "teaching_records", "id=neq.00000000-0000-0000-0000-000000000000")
    if rows:
        supabase_upsert(url, key, "teaching_records", rows, dry_run=False)


def build_teaching_records(root: Path, students_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    app_dir = Path(__file__).resolve().parents[1]
    records_path = app_dir / "cache/teaching_records.json"
    if not records_path.exists():
        records_path = root / "StudentCRM/cache/teaching_records.json"
    if not records_path.exists():
        return []

    records_json = load_json(records_path)
    records_list = records_json.get("records", [])
    name_to_id = {student["name"]: student["id"] for student in students_data}
    for student in students_data:
        for alias in student.get("aliases", []):
            name_to_id[alias] = student["id"]

    formatted_records = []
    for record in records_list:
        source_key = record.get("card_id") or record.get("id") or record.get("path") or record.get("title")
        payload = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"studentcrm:teaching:{source_key}")),
            "student_id": record.get("student_id"),
            "title": record.get("title"),
            "date": record.get("date"),
            "lesson_num": record.get("lesson_num"),
            "lesson_sub": record.get("lesson_sub"),
            "student_name": record.get("student_name"),
            "created": record.get("created"),
            "edited": record.get("edited"),
            "raw": record,
        }
        student_id = record.get("student_id") or name_to_id.get(record.get("student_name"))
        if student_id:
            payload["student_id"] = student_id
        formatted_records.append(payload)
    return formatted_records


def build_apple_ceo_payload(root: Path) -> dict[str, list[dict[str, Any]]]:
    apple_path = root / "OpenClaw/Data/apple_ceo_class.json"
    if not apple_path.exists():
        return {}

    data = load_json(apple_path)
    program = data.get("program", {})
    program_id = program.get("id", "apple-ceo")
    venue = data.get("venue", {})

    program_rows = [{
        "id": program_id,
        "name": program.get("name", ""),
        "url": program.get("url", ""),
        "description": program.get("description", ""),
        "schedule": program.get("schedule", ""),
        "capacity": program.get("capacity", ""),
        "round_size": program.get("round_size", 8),
        "price_per_student": program.get("price_per_student", 0),
        "validity_rule": program.get("validity_rule", ""),
        "leave_rule": program.get("leave_rule", ""),
        "join_rule": program.get("join_rule", ""),
        "raw": {
            **program,
            "active_participants": data.get("active_participants", []),
            "tuition_records": data.get("tuition_records", []),
            "duplicate_report": data.get("duplicate_report", {}),
            "teaching_notes": data.get("teaching_notes", []),
            "legacy_note": data.get("legacy_note", ""),
        },
    }]

    venue_rows = [{
        "id": f"{program_id}-venue-primary",
        "program_id": program_id,
        "name": venue.get("name", ""),
        "address": venue.get("address", ""),
        "parking": venue.get("parking", ""),
        "metro": venue.get("metro", ""),
        "cost_per_person": venue.get("cost_per_person", 0),
        "raw": venue,
    }]

    attendance_rows = []
    for index, record in enumerate(data.get("attendance_records", [])):
        date = record.get("date", "")
        attendance_rows.append({
            "id": record.get("id") or f"{program_id}-attendance-{date}-{index}",
            "program_id": program_id,
            "date": date,
            "venue": record.get("venue", ""),
            "attendee_count": record.get("attendee_count", 0),
            "attendees": record.get("attendees", []),
            "note": record.get("note", ""),
            "raw": record,
        })

    ledger_rows = []
    for index, record in enumerate(data.get("venue_ledger", [])):
        date = record.get("date", "")
        ledger_rows.append({
            "id": record.get("id") or f"{program_id}-ledger-{date}-{index}",
            "program_id": program_id,
            "date": date,
            "type": record.get("type", ""),
            "amount": record.get("amount", 0),
            "payer": record.get("payer", ""),
            "headcount": record.get("headcount"),
            "note": record.get("note", ""),
            "balance_after": record.get("balance_after", 0),
            "raw": record,
        })

    round_rows = []
    for group in data.get("student_rounds", []):
        student_name = group.get("student_name", "")
        aliases = group.get("aliases", [])
        for index, round_item in enumerate(group.get("rounds", [])):
            sessions = round_item.get("sessions", [])
            raw = {**round_item, "aliases": aliases}
            round_rows.append({
                "id": f"{program_id}-round-{student_name}-{index}",
                "program_id": program_id,
                "student_name": student_name,
                "label": round_item.get("label", ""),
                "payment_status": round_item.get("payment_status", ""),
                "sessions": sessions,
                "attended_count": len([session for session in sessions if session]),
                "sort_order": index,
                "raw": raw,
            })

    return {
        "apple_programs": program_rows,
        "apple_venues": venue_rows,
        "apple_attendance_records": attendance_rows,
        "apple_venue_ledger": ledger_rows,
        "apple_student_rounds": round_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="StudentCRM Supabase 遷移工具")
    parser.add_argument("--apply", action="store_true", help="實際寫入 Supabase；預設只乾跑")
    parser.add_argument("--apple-only", action="store_true", help="只同步蘋果總裁班資料，並清除 Supabase 舊班務資料後重建")
    parser.add_argument("--replace-teaching", action="store_true", help="清除 Supabase teaching_records 後用本地 teaching cache 重建")
    args = parser.parse_args()

    root = repo_root()
    app_dir = Path(__file__).resolve().parents[1]
    load_dotenv(app_dir / ".env")
    load_dotenv(root / "StudentCRM/.env")
    load_dotenv(root / ".env")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    dry_run = not args.apply

    students_path = root / "OpenClaw/Data/students.json"
    students_data = [] if args.apple_only else load_json(students_path)
    teaching_records = [] if args.apple_only else build_teaching_records(root, students_data)
    apple_payload = build_apple_ceo_payload(root)

    print(f"資料根目錄：{root}")
    if not args.apple_only:
        print(f"學員資料：{students_path} ({len(students_data)} 筆)")
        print(f"教學紀錄：{len(teaching_records)} 筆")
    for table, rows in apple_payload.items():
        print(f"蘋果總裁班 {table}：{len(rows)} 筆")
    print(f"執行模式：{'實際寫入' if args.apply else '乾跑'}")

    if dry_run:
        if args.replace_teaching and teaching_records:
            supabase_replace_teaching_records("", "", teaching_records, dry_run=True)
        if args.apple_only:
            supabase_replace_apple_payload("", "", apple_payload, dry_run=True)
        print("乾跑完成；確認 schema 後加上 --apply 才會寫入 Supabase。")
        return 0

    if not url or not key:
        print("錯誤：缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2

    if args.apple_only:
        supabase_replace_apple_payload(url, key, apple_payload, dry_run=False)
        print("Supabase 蘋果總裁班同步完成")
        return 0

    supabase_sync_students(url, key, students_data, dry_run=False)
    if teaching_records:
        if args.replace_teaching:
            supabase_replace_teaching_records(url, key, teaching_records, dry_run=False)
        else:
            supabase_upsert(url, key, "teaching_records", teaching_records, dry_run=False)
    for table, rows in apple_payload.items():
        if rows:
            supabase_upsert(url, key, table, rows, dry_run=False)
    print("Supabase 遷移完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
