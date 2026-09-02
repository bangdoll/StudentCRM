import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


REQUIRED_STUDENT_KEYS = {
    "id",
    "name",
    "aliases",
    "file",
    "lessons_count",
    "latest_date",
    "next_lesson",
    "tags",
}

REQUIRED_APPLE_PROGRAM_KEYS = {
    "id",
    "name",
    "round_size",
    "price_per_student",
}


def repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "OpenClaw").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def assert_student_shape(rows: list[dict], label: str) -> None:
    if not isinstance(rows, list):
        raise AssertionError(f"{label} 不是 list")
    if not rows:
        raise AssertionError(f"{label} 沒有資料")

    missing_reports = []
    for index, row in enumerate(rows[:20]):
        missing = REQUIRED_STUDENT_KEYS - set(row.keys())
        if missing:
            missing_reports.append(f"第 {index} 筆缺少 {sorted(missing)}")

    if missing_reports:
        raise AssertionError(f"{label} 欄位不完整：{'；'.join(missing_reports)}")

    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"{label} 有重複 id")


def fetch_json(url: str, headers: dict[str, str] | None = None):
    request = Request(url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def check_local() -> int:
    root = repo_root()
    students = load_json(root / "OpenClaw/Data/students.json")
    assert_student_shape(students, "本地 students.json")
    print(f"本地 students.json：OK ({len(students)} 筆)")
    check_local_apple_ceo(root)
    return len(students)


def check_local_apple_ceo(root: Path) -> None:
    data = load_json(root / "OpenClaw/Data/apple_ceo_class.json")
    missing = REQUIRED_APPLE_PROGRAM_KEYS - set(data.get("program", {}).keys())
    if missing:
        raise AssertionError(f"apple_ceo_class program 缺少 {sorted(missing)}")
    if "venue" not in data or not isinstance(data["venue"], dict):
        raise AssertionError("apple_ceo_class 缺少 venue")
    if not isinstance(data.get("venue_ledger", []), list):
        raise AssertionError("apple_ceo_class venue_ledger 不是 list")
    if not isinstance(data.get("student_rounds", []), list):
        raise AssertionError("apple_ceo_class student_rounds 不是 list")
    for group in data.get("student_rounds", []):
        if "student_name" not in group or not isinstance(group.get("rounds", []), list):
            raise AssertionError("apple_ceo_class student_rounds 欄位不完整")
    print(f"本地 apple_ceo_class.json：OK ({len(data.get('student_rounds', []))} 位班務學員)")


def check_api(base_url: str) -> int:
    payload = fetch_json(f"{base_url.rstrip('/')}/api/students")
    rows = payload.get("students", [])
    assert_student_shape(rows, "FastAPI /api/students")
    print(f"FastAPI /api/students：OK ({len(rows)} 筆)")
    return len(rows)


def check_supabase() -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise AssertionError("缺少 SUPABASE_URL 與 SUPABASE_ANON_KEY")

    rows = fetch_json(
        f"{url}/rest/v1/students?select=*",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    assert_student_shape(rows, "Supabase students")
    print(f"Supabase students：OK ({len(rows)} 筆)")
    check_supabase_apple_ceo(url, key)
    return len(rows)


def fetch_supabase_table(url: str, key: str, table: str):
    return fetch_json(
        f"{url}/rest/v1/{table}?select=*",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )


def check_supabase_apple_ceo(url: str, key: str) -> None:
    expected_tables = {
        "apple_programs": 1,
        "apple_venues": 1,
        "apple_venue_ledger": 1,
        "apple_student_rounds": 1,
    }
    for table, minimum_count in expected_tables.items():
        rows = fetch_supabase_table(url, key, table)
        if len(rows) < minimum_count:
            raise AssertionError(f"Supabase {table} 筆數不足：{len(rows)}")
        print(f"Supabase {table}：OK ({len(rows)} 筆)")

    attendance_rows = fetch_supabase_table(url, key, "apple_attendance_records")
    print(f"Supabase apple_attendance_records：OK ({len(attendance_rows)} 筆)")


def main() -> int:
    app_dir = Path(__file__).resolve().parents[1]
    load_dotenv(app_dir / ".env")
    load_dotenv(repo_root() / ".env")
    parser = argparse.ArgumentParser(description="StudentCRM 雲端同步 smoke test")
    parser.add_argument("--api", default="", help="檢查 FastAPI base URL，例如 http://127.0.0.1:8888")
    parser.add_argument("--supabase", action="store_true", help="檢查 Supabase REST；需要環境變數")
    args = parser.parse_args()

    try:
        local_count = check_local()
        if args.api:
            api_count = check_api(args.api)
            if api_count != local_count:
                raise AssertionError(f"API 筆數 {api_count} 與本地筆數 {local_count} 不一致")
        if args.supabase:
            supabase_count = check_supabase()
            if supabase_count != local_count:
                raise AssertionError(f"Supabase 筆數 {supabase_count} 與本地筆數 {local_count} 不一致")
    except (AssertionError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Smoke test 失敗：{exc}", file=sys.stderr)
        return 1

    print("Smoke test 通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
