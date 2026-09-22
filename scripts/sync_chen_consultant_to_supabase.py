"""只同步陳顧問教學筆記到 Production Supabase (Thin Wrapper 封裝版)。

底層已委由 TeachingSyncPipeline 深模組統一處理，保證邏輯內聚與安全差分。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 將專案根目錄加入路徑
APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from teaching_sync_pipeline import TeachingSyncPipeline

STUDENT_ID = "f13107ba-79fb-5bae-8728-99648687ef48"


def main() -> int:
    parser = argparse.ArgumentParser(description="只同步陳顧問教學筆記到 StudentCRM Production Supabase")
    parser.add_argument("--apply", action="store_true", help="實際 upsert；預設只乾跑")
    args = parser.parse_args()

    pipeline = TeachingSyncPipeline(APP_DIR)
    dry_run = not args.apply

    print(f"正在執行陳顧問教學筆記同步 (mode={'apply' if args.apply else 'dry-run'})...")
    res = pipeline.sync_student(STUDENT_ID, dry_run=dry_run)

    print("=== Supabase 同步報告 ===")
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    return 0 if res.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
