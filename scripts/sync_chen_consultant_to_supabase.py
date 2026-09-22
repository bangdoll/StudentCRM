"""只同步陳顧問到 Production Supabase，不重建或刪除其他資料。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv


APP_DIR = Path(__file__).resolve().parents[1]
STUDENT_ID = "f13107ba-79fb-5bae-8728-99648687ef48"
EXPECTED_RECORD_COUNT = 14
LATEST_FILENAME = "14_2026-09-22_和陳顧問合作課程_v2.md"
LATEST_SOURCE_MD5 = "d83fc494773d6ca68b5f1a2e0feb6b94"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_local_credentials() -> None:
    """沿用專案既有的本機秘密載入位置，不把秘密寫入程式或輸出。"""
    repo_root = APP_DIR.parent.parent
    load_dotenv(APP_DIR / ".env")
    load_dotenv(repo_root / ".env")


def source_records() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    students = load_json(APP_DIR / "data" / "students.json")
    records_payload = load_json(APP_DIR / "data" / "teaching_records.json")
    student = next((item for item in students if item.get("id") == STUDENT_ID), None)
    if not student or student.get("name") != "陳顧問":
        raise RuntimeError("本地資料找不到預期的陳顧問學員")

    records = [
        item
        for item in records_payload.get("records", [])
        if item.get("student_id") == STUDENT_ID
    ]
    lesson_numbers = sorted(item.get("lesson_num") for item in records)
    if len(records) != EXPECTED_RECORD_COUNT or lesson_numbers != list(range(1, 15)):
        raise RuntimeError(
            f"陳顧問課堂數或堂號不符：count={len(records)}, lessons={lesson_numbers}"
        )
    latest = next((item for item in records if item.get("filename") == LATEST_FILENAME), None)
    if not latest or LATEST_SOURCE_MD5 not in (latest.get("preview") or ""):
        raise RuntimeError("第 14 堂不是預期的 Heptabase v2 最新版本")
    return student, records


def student_row(student: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": student["id"],
        "name": student.get("name", ""),
        "aliases": student.get("aliases", []),
        "file": student.get("file", ""),
        "lessons_count": student.get("lessons_count", 0),
        "latest_date": student.get("latest_date", ""),
        "next_lesson": student.get("next_lesson", ""),
        "tags": student.get("tags", []),
        "recurring_schedule": student.get("recurring_schedule", ""),
        "schedule_exceptions": student.get("schedule_exceptions", []),
        "raw": student,
    }


def teaching_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        source_key = (
            record.get("card_id")
            or record.get("id")
            or record.get("path")
            or record.get("title")
        )
        rows.append(
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"studentcrm:teaching:{source_key}")),
                "student_id": STUDENT_ID,
                "student_name": record.get("student_name", "陳顧問"),
                "title": record.get("title", ""),
                "date": record.get("date", ""),
                "lesson_num": record.get("lesson_num"),
                "lesson_sub": record.get("lesson_sub"),
                "created": record.get("created", ""),
                "edited": record.get("edited", ""),
                "raw": record,
            }
        )
    return rows


def request_headers(key: str, *, write: bool = False) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if write:
        headers.update(
            {
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }
        )
    return headers


def api_url(base_url: str, table: str) -> str:
    return f"{base_url.rstrip('/')}/rest/v1/{table}"


def upsert(base_url: str, key: str, table: str, rows: list[dict[str, Any]]) -> None:
    response = requests.post(
        api_url(base_url, table),
        headers=request_headers(key, write=True),
        json=rows,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase {table} upsert 失敗：HTTP {response.status_code}")


def readback(base_url: str, key: str) -> dict[str, Any]:
    student_query = quote(f"select=id,name,lessons_count,latest_date&id=eq.{STUDENT_ID}", safe="=&")
    records_query = quote(
        f"select=id,student_id,lesson_num,raw&student_id=eq.{STUDENT_ID}&order=lesson_num.asc",
        safe="=&",
    )
    student_response = requests.get(
        f"{api_url(base_url, 'students')}?{student_query}",
        headers=request_headers(key),
        timeout=30,
    )
    records_response = requests.get(
        f"{api_url(base_url, 'teaching_records')}?{records_query}",
        headers=request_headers(key),
        timeout=30,
    )
    if not student_response.ok or not records_response.ok:
        raise RuntimeError(
            "Supabase 讀回失敗："
            f"students={student_response.status_code}, teaching_records={records_response.status_code}"
        )

    students = student_response.json()
    records = records_response.json()
    lesson_numbers = sorted(item.get("lesson_num") for item in records)
    latest_md5_found = any(
        LATEST_SOURCE_MD5 in json.dumps(item.get("raw"), ensure_ascii=False)
        for item in records
    )
    if len(students) != 1 or students[0].get("name") != "陳顧問":
        raise RuntimeError("Supabase 讀回的陳顧問學員不符合預期")
    if len(records) != EXPECTED_RECORD_COUNT or lesson_numbers != list(range(1, 15)):
        raise RuntimeError(
            f"Supabase 讀回課堂數或堂號不符：count={len(records)}, lessons={lesson_numbers}"
        )
    if not latest_md5_found:
        raise RuntimeError("Supabase 讀回未找到第 14 堂 v2 來源指紋")

    return {
        "student_count": len(students),
        "record_count": len(records),
        "lesson_numbers": lesson_numbers,
        "latest_v2_verified": latest_md5_found,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="只同步陳顧問到 StudentCRM Production Supabase")
    parser.add_argument("--apply", action="store_true", help="實際 upsert；預設只乾跑")
    args = parser.parse_args()

    student, records = source_records()
    student_payload = student_row(student)
    records_payload = teaching_rows(records)
    mode = "apply" if args.apply else "dry-run"
    print(f"mode={mode} student=1 teaching_records={len(records_payload)}")
    print(f"latest_filename={LATEST_FILENAME} source_md5={LATEST_SOURCE_MD5}")
    if not args.apply:
        print("dry-run 完成；未修改 Supabase")
        return 0

    load_local_credentials()
    base_url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not base_url or not key:
        print("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2

    upsert(base_url, key, "students", [student_payload])
    upsert(base_url, key, "teaching_records", records_payload)
    verification = readback(base_url, key)
    print(json.dumps(verification, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
