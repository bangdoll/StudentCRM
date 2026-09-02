from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from teaching_sync import build_teaching_records_from_directory


def repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "OpenClaw").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="同步本地 teaching 知識庫到 StudentCRM teaching_records cache")
    parser.add_argument(
        "--teaching-dir",
        default="",
        help="教學文件資料夾；預設為 <repo>/01.Docs/teaching",
    )
    parser.add_argument("--dry-run", action="store_true", help="只顯示統計，不寫入 cache")
    args = parser.parse_args()

    root = repo_root()
    app_dir = Path(__file__).resolve().parents[1]
    teaching_dir = Path(args.teaching_dir) if args.teaching_dir else root / "01.Docs/teaching"
    students_path = root / "OpenClaw/Data/students.json"
    cache_dir = app_dir / "cache"
    records_path = cache_dir / "teaching_records.json"
    report_path = cache_dir / "teaching_import_report.json"

    students = load_json(students_path)
    payload = build_teaching_records_from_directory(teaching_dir, students)

    print(f"教學資料夾：{teaching_dir}")
    print(f"正式學生：{len(students)}")
    print(f"已對照紀錄：{payload['total_records']}")
    print(f"已對照學生：{payload['total_students']}")
    print(f"未對照檔案：{len(payload['unmatched'])}")
    print(f"重複紀錄：{payload['duplicate_count']}")

    if payload["unmatched"]:
        print("未對照前 20 筆：")
        for item in payload["unmatched"][:20]:
            print(f"- {item['filename']} -> {item['candidate_name']}")

    if args.dry_run:
        return 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    records_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        key: payload[key]
        for key in ["total_records", "total_students", "unmatched", "duplicate_count", "generated_at"]
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已寫入：{records_path}")
    print(f"已寫入：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
