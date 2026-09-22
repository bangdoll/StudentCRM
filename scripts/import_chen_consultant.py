"""將陳顧問 14 堂合作課程安全匯入 StudentCRM。

預設只產生 Diff；傳入 --write 才會透過 StudentDataGateway 寫入，
並保留資料閘道的快照與筆數斷路器保護。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
SOURCE_DIR = REPO_ROOT / "01.Docs" / "teaching" / "陳顧問"
STUDENT_ID = "f13107ba-79fb-5bae-8728-99648687ef48"
EXPECTED_LATEST_CONTENT_MD5 = "d83fc494773d6ca68b5f1a2e0feb6b94"

sys.path.insert(0, str(APP_DIR))

from data_gateway import StudentDataGateway  # noqa: E402
from teaching_sync import build_teaching_records_from_directory  # noqa: E402


STUDENT_PROFILE = {
    "id": STUDENT_ID,
    "name": "陳顧問",
    "aliases": [],
    "file": "",
    "lessons_count": 14,
    "latest_date": "2026-09-22",
    "next_lesson": "",
    "tags": ["一般學員"],
    "first_lesson_date": "2026-05-13",
    "current_cycle_lesson": 6,
    "status": "active",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_source_records() -> list[dict]:
    if not SOURCE_DIR.exists():
        raise RuntimeError(f"找不到陳顧問本地教學筆記資料夾：{SOURCE_DIR}")

    result = build_teaching_records_from_directory(SOURCE_DIR, [STUDENT_PROFILE])
    if result["unmatched"]:
        raise RuntimeError(f"存在未對照的陳顧問筆記：{result['unmatched']}")
    if result["total_records"] != 14:
        raise RuntimeError(f"陳顧問筆記數量不是 14 堂，而是 {result['total_records']} 堂")

    records = sorted(result["records"], key=lambda item: (item.get("date", ""), item.get("lesson_num") or 0))
    if {record.get("lesson_num") for record in records} != set(range(1, 15)):
        raise RuntimeError("陳顧問筆記堂數不是完整的第 01–14 堂")

    latest = next((record for record in records if record.get("lesson_num") == 14), None)
    latest_content = (latest or {}).get("content", "")
    if EXPECTED_LATEST_CONTENT_MD5 not in latest_content:
        raise RuntimeError("第 14 堂未使用指定的最新版本內容")

    for record in records:
        if record.get("student_id") != STUDENT_ID or record.get("student_name") != "陳顧問":
            raise RuntimeError(f"筆記學員對照錯誤：{record.get('filename')}")
    return records


def build_merged_payload(current_payload: dict, new_records: list[dict]) -> dict:
    current_records = current_payload.get("records", [])
    if not isinstance(current_records, list):
        raise RuntimeError("現有 teaching_records.json 的 records 不是列表")

    existing_filenames = {record.get("filename") for record in current_records}
    duplicate_files = sorted({record.get("filename") for record in new_records} & existing_filenames)
    if duplicate_files:
        raise RuntimeError(f"CRM 已存在相同筆記檔名，停止避免重複：{duplicate_files}")

    merged_records = [*current_records, *new_records]
    merged_records.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)

    by_student: dict[str, list[dict]] = {}
    for record in merged_records:
        student_id = record.get("student_id") or ""
        by_student.setdefault(student_id, []).append(record)
    for student_records in by_student.values():
        student_records.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)

    payload = dict(current_payload)
    payload.update(
        {
            "records": merged_records,
            "by_student": by_student,
            "total_records": len(merged_records),
            "total_students": len(by_student),
            "generated_at": now_iso(),
        }
    )
    return payload


def prepare_diff() -> tuple[list[dict], dict, list[dict]]:
    students_path = APP_DIR / "data" / "students.json"
    records_path = APP_DIR / "data" / "teaching_records.json"
    students = load_json(students_path)
    root_students = load_json(REPO_ROOT / "OpenClaw" / "Data" / "students.json")
    if students != root_students:
        raise RuntimeError("StudentCRM/data/students.json 與 OpenClaw/Data/students.json 已不一致，停止寫入")
    if any(student.get("name") == "陳顧問" or student.get("id") == STUDENT_ID for student in students):
        raise RuntimeError("已存在陳顧問學員或相同 ID，停止避免重複建立")

    current_payload = load_json(records_path)
    new_records = load_source_records()
    merged_payload = build_merged_payload(current_payload, new_records)
    return students, merged_payload, new_records


def main() -> int:
    parser = argparse.ArgumentParser(description="匯入陳顧問 14 堂教學筆記")
    parser.add_argument("--write", action="store_true", help="確認後寫入 StudentCRM")
    parser.add_argument("--expected-students", type=int, default=None)
    parser.add_argument("--expected-records", type=int, default=None)
    args = parser.parse_args()

    students, merged_payload, new_records = prepare_diff()
    old_record_count = len(merged_payload["records"]) - len(new_records)
    diff = {
        "mode": "write" if args.write else "dry_run",
        "student": {
            "before_count": len(students),
            "after_count": len(students) + 1,
            "added": STUDENT_PROFILE,
            "public_url": f"https://student-crm-flax.vercel.app/my/{STUDENT_ID}",
        },
        "teaching_records": {
            "before_count": old_record_count,
            "after_count": len(merged_payload["records"]),
            "added_count": len(new_records),
            "dates": [record.get("date") for record in sorted(new_records, key=lambda item: item.get("date", ""))],
            "latest_filename": next(record["filename"] for record in new_records if record.get("lesson_num") == 14),
        },
        "backup_required": True,
    }

    if args.expected_students is not None and len(students) != args.expected_students:
        raise RuntimeError(f"學員基線數量變更：預期 {args.expected_students}，實際 {len(students)}")
    if args.expected_records is not None and old_record_count != args.expected_records:
        raise RuntimeError(f"教學紀錄基線數量變更：預期 {args.expected_records}，實際 {old_record_count}")

    if not args.write:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
        return 0

    gateway = StudentDataGateway(str(REPO_ROOT))
    gateway.save_students([*students, STUDENT_PROFILE])
    gateway.save_teaching_records(merged_payload)

    saved_students = load_json(APP_DIR / "data" / "students.json")
    saved_payload = load_json(APP_DIR / "data" / "teaching_records.json")
    saved_student = next((student for student in saved_students if student.get("id") == STUDENT_ID), None)
    saved_records = [record for record in saved_payload.get("records", []) if record.get("student_id") == STUDENT_ID]
    latest_saved = next((record for record in saved_records if record.get("lesson_num") == 14), None)
    if saved_student != STUDENT_PROFILE:
        raise RuntimeError("寫入後陳顧問學員資料與預期不一致")
    if len(saved_records) != 14 or EXPECTED_LATEST_CONTENT_MD5 not in (latest_saved or {}).get("content", ""):
        raise RuntimeError("寫入後陳顧問 14 堂筆記或第 14 堂最新版本驗證失敗")

    diff["verification"] = {
        "student_found": True,
        "records_found": len(saved_records),
        "latest_version_verified": True,
        "studentcrm_url": f"https://student-crm-flax.vercel.app/my/{STUDENT_ID}",
    }
    print(json.dumps(diff, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
