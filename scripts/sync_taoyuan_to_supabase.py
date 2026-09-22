"""只同步桃園教學筆記到 Production Supabase，不重建或刪除其他資料。"""

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
STUDENT_ID = "36e24a4e-b1b0-4c03-9a6f-dd5d3f52cd95"
EXPECTED_RECORD_COUNT = 31
INVALID_LEGACY_ID = "7bb4ceeb-4449-5b0e-a980-19307db4986e"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_local_credentials() -> None:
    repo_root = APP_DIR.parent.parent
    load_dotenv(APP_DIR / ".env")
    load_dotenv(repo_root / ".env")


def source_records() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    students = load_json(APP_DIR / "data" / "students.json")
    records_payload = load_json(APP_DIR / "data" / "teaching_records.json")
    student = next((item for item in students if item.get("id") == STUDENT_ID), None)
    if not student or student.get("name") != "桃園":
        raise RuntimeError("本地資料找不到預期的桃園學員")

    records = [
        item
        for item in records_payload.get("records", [])
        if item.get("student_id") == STUDENT_ID or item.get("student_name") == "桃園"
    ]
    if len(records) != EXPECTED_RECORD_COUNT:
        raise RuntimeError(f"桃園教學記錄數不符：預期 {EXPECTED_RECORD_COUNT}，實際 {len(records)}")

    # 驗證無 2025-01-00 畸形日期
    for r in records:
        if r.get("date") == "2025-01-00" or "202501007" in (r.get("filename") or ""):
            raise RuntimeError(f"發現畸形日期或檔名：{r}")

    # 驗證 94-2 正確記錄存在
    rec_94 = next((r for r in records if r.get("lesson_num") == 94 and str(r.get("lesson_sub")) == "2"), None)
    if not rec_94 or rec_94.get("date") != "2025-10-07":
        raise RuntimeError(f"未找到正確的 94-2 (2025-10-07) 記錄：{rec_94}")

    return student, records


def teaching_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        source_key = (
            record.get("card_id")
            or record.get("id")
            or record.get("path")
            or record.get("title")
        )
        row_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"studentcrm:teaching:{source_key}"))
        rows.append(
            {
                "id": row_id,
                "student_id": STUDENT_ID,
                "student_name": "桃園",
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
    for i in range(0, len(rows), 100):
        batch = rows[i : i + 100]
        response = requests.post(
            api_url(base_url, table),
            headers=request_headers(key, write=True),
            json=batch,
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase {table} upsert 失敗：HTTP {response.status_code} {response.text}")


def delete_record(base_url: str, key: str, table: str, record_id: str) -> None:
    response = requests.delete(
        f"{api_url(base_url, table)}?id=eq.{quote(record_id)}",
        headers=request_headers(key),
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase {table} delete {record_id} 失敗：HTTP {response.status_code} {response.text}")


def readback(base_url: str, key: str) -> dict[str, Any]:
    records_query = quote(
        f"select=id,student_id,lesson_num,lesson_sub,date,title,raw&student_id=eq.{STUDENT_ID}&order=date.asc",
        safe="=&",
    )
    records_response = requests.get(
        f"{api_url(base_url, 'teaching_records')}?{records_query}",
        headers=request_headers(key),
        timeout=30,
    )
    if not records_response.ok:
        raise RuntimeError(f"Supabase 讀回失敗：HTTP {records_response.status_code} {records_response.text}")

    records = records_response.json()
    dates = [r.get("date") for r in records]
    if "2025-01-00" in dates:
        raise RuntimeError("Supabase 讀回仍存在 2025-01-00 畸形日期！")

    if len(records) != EXPECTED_RECORD_COUNT:
        raise RuntimeError(f"Supabase 讀回記錄數不符：預期 {EXPECTED_RECORD_COUNT}，實際 {len(records)}")

    lesson_pairs = [(r.get("lesson_num"), r.get("lesson_sub")) for r in records if r.get("lesson_num")]

    return {
        "student_id": STUDENT_ID,
        "record_count": len(records),
        "earliest_date": records[0].get("date") if records else None,
        "latest_date": records[-1].get("date") if records else None,
        "lesson_pairs_count": len(lesson_pairs),
        "sample_titles": [r.get("title") for r in records[:3]] + [r.get("title") for r in records[-3:]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="只同步桃園教學筆記到 StudentCRM Production Supabase")
    parser.add_argument("--apply", action="store_true", help="實際 upsert；預設只乾跑")
    args = parser.parse_args()

    student, records = source_records()
    records_payload = teaching_rows(records)
    valid_ids = {r["id"] for r in records_payload}

    mode = "apply" if args.apply else "dry-run"
    print(f"mode={mode} student=桃園({STUDENT_ID}) teaching_records={len(records_payload)}")
    print(f"預計寫入筆數：{len(records_payload)} 篇")

    load_local_credentials()
    base_url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not base_url or not key:
        print("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2

    # 先查詢雲端現況
    query = quote(f"select=id,date,title&student_id=eq.{STUDENT_ID}", safe="=&")
    existing_resp = requests.get(
        f"{api_url(base_url, 'teaching_records')}?{query}",
        headers=request_headers(key),
        timeout=30,
    )
    if not existing_resp.ok:
        print(f"查詢雲端現況失敗：HTTP {existing_resp.status_code}", file=sys.stderr)
        return 3

    existing_rows = existing_resp.json()
    stale_ids = [r["id"] for r in existing_rows if r["id"] not in valid_ids]
    print(f"雲端目前筆數：{len(existing_rows)}，其中過期/無效孤立 ID：{stale_ids}")

    if not args.apply:
        print("dry-run 完成；未修改 Supabase")
        return 0

    # 1. 刪除過期孤立 ID（例如筆誤產生的 7bb4ceeb-4449-5b0e-a980-19307db4986e）
    for sid in stale_ids:
        print(f"正在清理過期/無效記錄 ID={sid} ...")
        delete_record(base_url, key, "teaching_records", sid)

    # 2. Upsert 31 筆有效記錄
    print(f"正在 upsert {len(records_payload)} 筆桃園教學筆記 ...")
    upsert(base_url, key, "teaching_records", records_payload)

    # 3. 讀回驗證
    print("正在進行讀回嚴格驗證 ...")
    verification = readback(base_url, key)
    print("=== Supabase 同步驗證成功 ===")
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
