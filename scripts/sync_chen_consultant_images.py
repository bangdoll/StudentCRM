"""將陳顧問 8 張 Heptabase 圖片引用同步到 StudentCRM 教學紀錄鏡像。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent.parent
STUDENT_ID = "f13107ba-79fb-5bae-8728-99648687ef48"

IMAGE_REFS = {
    6: "assets/chen-consultant-06.png",
    8: "assets/chen-consultant-08.png",
    9: "assets/chen-consultant-09.png",
    10: "assets/chen-consultant-10.png",
    11: "assets/chen-consultant-11.png",
    12: "assets/chen-consultant-12.png",
    13: "assets/chen-consultant-13.png",
    14: "assets/chen-consultant-14.png",
}

SOURCE_FILES = {
    6: "06_2026-06-17_和陳顧問合作課程.md",
    8: "08_2026-07-01_和陳顧問合作課程.md",
    9: "09_2026-07-08_和陳顧問合作課程.md",
    10: "10_2026-07-15_和陳顧問合作課程.md",
    11: "11_2026-08-05_和陳顧問合作課程.md",
    12: "12_2026-08-12_和陳顧問合作課程.md",
    13: "13_2026-08-26_和陳顧問合作課程.md",
    14: "14_2026-09-22_和陳顧問合作課程_v2.md",
}


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise RuntimeError(f"教學紀錄格式不符：{path}")
    return payload


def expected_contents() -> dict[int, str]:
    source_dir = REPO_ROOT / "01.Docs" / "teaching" / "陳顧問"
    contents: dict[int, str] = {}
    for lesson, filename in SOURCE_FILES.items():
        path = source_dir / filename
        content = path.read_text(encoding="utf-8")
        ref = IMAGE_REFS[lesson]
        if ref not in content:
            raise RuntimeError(f"第 {lesson:02d} 堂缺少圖片引用：{ref}")
        asset_path = APP_DIR / "static" / "teaching_assets" / Path(ref).name
        if not asset_path.is_file():
            raise RuntimeError(f"找不到圖片資產：{asset_path}")
        contents[lesson] = content
    return contents


def update_payload(payload: dict[str, Any], contents: dict[int, str]) -> int:
    records = payload["records"]
    target_records = [record for record in records if record.get("student_id") == STUDENT_ID]
    if len(target_records) != 14:
        raise RuntimeError(f"陳顧問紀錄數不符：{len(target_records)}")

    updated = 0
    for record in target_records:
        lesson = record.get("lesson_num")
        if lesson in contents and record.get("content") != contents[lesson]:
            record["content"] = contents[lesson]
            updated += 1
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="精準同步陳顧問教學圖片引用")
    parser.add_argument("--write", action="store_true", help="實際寫入 data 與 cache 鏡像")
    args = parser.parse_args()

    contents = expected_contents()
    paths = [
        APP_DIR / "data" / "teaching_records.json",
        APP_DIR / "cache" / "teaching_records.json",
    ]
    payloads = [load_payload(path) for path in paths]
    before_counts = [len(payload["records"]) for payload in payloads]
    if before_counts != [743, 743]:
        raise RuntimeError(f"教學紀錄基線不符：{before_counts}")
    if payloads[0] != payloads[1]:
        raise RuntimeError("data 與 cache 教學紀錄鏡像已不一致，停止寫入")

    updated_counts = [update_payload(payload, contents) for payload in payloads]
    print(f"mode={'write' if args.write else 'dry-run'} updated_records={updated_counts[0]}")
    print(f"image_refs={len(IMAGE_REFS)} records={before_counts[0]}")
    if not args.write:
        print("dry-run 完成；未修改資料鏡像")
        return 0

    serialized = json.dumps(payloads[0], ensure_ascii=False, indent=2) + "\n"
    for path in paths:
        path.write_text(serialized, encoding="utf-8")
    print("已寫入 data/teaching_records.json 與 cache/teaching_records.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
