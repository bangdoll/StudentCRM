"""教學資產與雙向同步深模組 (TeachingSyncPipeline)。

依據 John Ousterhout 深模組原則設計：
將本地 Markdown 掃描、JSON 快取載入、差分比對、雲端孤立記錄清理、批次冪等 Upsert
與讀回校驗完全封裝於單一介面之後。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv


@dataclass
class SyncResult:
    student_id: str
    student_name: str
    records_count: int
    orphans_cleaned: list[str] = field(default_factory=list)
    success: bool = True
    mode: str = "dry-run"
    error_message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "student_name": self.student_name,
            "records_count": self.records_count,
            "orphans_cleaned": self.orphans_cleaned,
            "success": self.success,
            "mode": self.mode,
            "error_message": self.error_message,
            "details": self.details,
        }


class TeachingSyncPipeline:
    def __init__(self, crm_dir: Path | str | None = None) -> None:
        self.crm_dir = Path(crm_dir) if crm_dir else Path(__file__).resolve().parent
        self.students_file = self.crm_dir / "data" / "students.json"
        self.teaching_records_file = self.crm_dir / "data" / "teaching_records.json"
        self.base_url = ""
        self.service_key = ""
        self._load_credentials()

    def _load_credentials(self) -> None:
        repo_root = self.crm_dir.parents[1]
        load_dotenv(self.crm_dir / ".env")
        load_dotenv(repo_root / ".env")
        self.base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    def _headers(self, write: bool = False) -> dict[str, str]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
        }
        if write:
            headers.update({
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            })
        return headers

    def load_student_records(self, student_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """從本地 SSOT 載入指定學員與其所有教學筆記。"""
        if not self.students_file.exists() or not self.teaching_records_file.exists():
            raise FileNotFoundError("找不到本地 students.json 或 teaching_records.json")

        with self.students_file.open("r", encoding="utf-8") as f:
            students = json.load(f)

        student = next((s for s in students if s.get("id") == student_id), None)
        if not student:
            raise ValueError(f"本地學員資料庫中找不到學員 ID={student_id}")

        student_name = student.get("name", "")
        aliases = student.get("aliases", [])
        valid_names = {student_name} | set(aliases)

        with self.teaching_records_file.open("r", encoding="utf-8") as f:
            records_data = json.load(f)

        all_records = records_data.get("records", []) if isinstance(records_data, dict) else records_data
        matched_records = [
            r for r in all_records
            if r.get("student_id") == student_id or r.get("student_name") in valid_names
        ]
        return student, matched_records

    def build_payload_rows(self, student: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """將教學筆記轉換為 Supabase teaching_records 表格規格（保證確定性 UUID）。"""
        rows = []
        student_id = student["id"]
        student_name = student.get("name", "")

        for record in records:
            source_key = (
                record.get("card_id")
                or record.get("id")
                or record.get("path")
                or record.get("title")
            )
            row_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"studentcrm:teaching:{source_key}"))
            rows.append({
                "id": row_id,
                "student_id": student_id,
                "student_name": student_name,
                "title": record.get("title", ""),
                "date": record.get("date", ""),
                "lesson_num": record.get("lesson_num"),
                "lesson_sub": record.get("lesson_sub"),
                "created": record.get("created", ""),
                "edited": record.get("edited", ""),
                "raw": record,
            })
        return rows

    def calculate_diff(
        self, payload_rows: list[dict[str, Any]], remote_rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """差分引擎：計算需 upsert 的 rows 與需清理的孤立 ID。"""
        valid_local_ids = {r["id"] for r in payload_rows}
        stale_orphan_ids = [
            r["id"] for r in remote_rows
            if r.get("id") and r["id"] not in valid_local_ids
        ]
        return payload_rows, stale_orphan_ids

    def _query_remote_student_records(self, student_id: str) -> list[dict[str, Any]]:
        if not self.base_url or not self.service_key:
            return []
        query = quote(f"select=id,date,title&student_id=eq.{student_id}", safe="=&")
        url = f"{self.base_url}/rest/v1/teaching_records?{query}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if not resp.ok:
            raise RuntimeError(f"查詢 Supabase 記錄失敗：HTTP {resp.status_code} {resp.text}")
        return resp.json()

    def _delete_orphan_record(self, record_id: str) -> None:
        url = f"{self.base_url}/rest/v1/teaching_records?id=eq.{quote(record_id)}"
        resp = requests.delete(url, headers=self._headers(), timeout=30)
        if not resp.ok:
            raise RuntimeError(f"刪除孤立記錄 ID={record_id} 失敗：HTTP {resp.status_code}")

    def _upsert_batches(self, rows: list[dict[str, Any]]) -> None:
        url = f"{self.base_url}/rest/v1/teaching_records"
        for i in range(0, len(rows), 100):
            batch = rows[i : i + 100]
            resp = requests.post(url, headers=self._headers(write=True), json=batch, timeout=30)
            if not resp.ok:
                raise RuntimeError(f"批次 upsert 失敗：HTTP {resp.status_code} {resp.text}")

    def _readback_verify(self, student_id: str, expected_count: int) -> dict[str, Any]:
        query = quote(
            f"select=id,date,title,lesson_num&student_id=eq.{student_id}&order=date.asc",
            safe="=&",
        )
        url = f"{self.base_url}/rest/v1/teaching_records?{query}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if not resp.ok:
            raise RuntimeError(f"讀回校驗失敗：HTTP {resp.status_code}")
        records = resp.json()
        if len(records) != expected_count:
            raise RuntimeError(f"讀回數量不符：預期 {expected_count}，實際 {len(records)}")
        return {
            "verified_count": len(records),
            "earliest_date": records[0].get("date") if records else None,
            "latest_date": records[-1].get("date") if records else None,
        }

    def sync_student(self, student_id: str, dry_run: bool = False) -> SyncResult:
        """核心公開介面：單一學員完整同步閉環。"""
        mode = "dry-run" if dry_run else "apply"
        try:
            student, records = self.load_student_records(student_id)
        except Exception as exc:
            return SyncResult(
                student_id=student_id,
                student_name="未知",
                records_count=0,
                success=False,
                mode=mode,
                error_message=str(exc),
            )

        student_name = student.get("name", "")
        payload_rows = self.build_payload_rows(student, records)

        if not self.base_url or not self.service_key:
            return SyncResult(
                student_id=student_id,
                student_name=student_name,
                records_count=len(payload_rows),
                success=False,
                mode=mode,
                error_message="缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY，略過雲端同步",
            )

        try:
            remote_existing = self._query_remote_student_records(student_id)
            to_upsert, orphan_ids = self.calculate_diff(payload_rows, remote_existing)

            if dry_run:
                return SyncResult(
                    student_id=student_id,
                    student_name=student_name,
                    records_count=len(to_upsert),
                    orphans_cleaned=orphan_ids,
                    success=True,
                    mode="dry-run",
                    details={"remote_existing_count": len(remote_existing)},
                )

            # 1. 依序清理孤立 ID
            for oid in orphan_ids:
                self._delete_orphan_record(oid)

            # 2. 批次 Upsert
            self._upsert_batches(to_upsert)

            # 3. 讀回驗收
            verification = self._readback_verify(student_id, len(to_upsert))

            return SyncResult(
                student_id=student_id,
                student_name=student_name,
                records_count=len(to_upsert),
                orphans_cleaned=orphan_ids,
                success=True,
                mode="apply",
                details=verification,
            )
        except Exception as exc:
            return SyncResult(
                student_id=student_id,
                student_name=student_name,
                records_count=len(payload_rows),
                success=False,
                mode=mode,
                error_message=str(exc),
            )

    def sync_all(self, dry_run: bool = False) -> dict[str, Any]:
        """核心公開介面：全量所有學員雙 SSOT 增量差分同步。"""
        if not self.students_file.exists() or not self.teaching_records_file.exists():
            return {"success": False, "error": "本地資料庫不存在"}

        with self.students_file.open("r", encoding="utf-8") as f:
            students = json.load(f)

        results: list[dict[str, Any]] = []
        total_orphans = 0
        total_records = 0
        success_count = 0

        for student in students:
            sid = student.get("id")
            if not sid:
                continue
            res = self.sync_student(sid, dry_run=dry_run)
            results.append(res.to_dict())
            if res.success:
                success_count += 1
                total_records += res.records_count
                total_orphans += len(res.orphans_cleaned)

        return {
            "success": True,
            "mode": "dry-run" if dry_run else "apply",
            "total_students": len(students),
            "synced_students": success_count,
            "total_records": total_records,
            "total_orphans_cleaned": total_orphans,
            "results": results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="TeachingSyncPipeline 雙 SSOT 增量同步工具")
    parser.add_argument("--student", type=str, help="指定學員 ID 或姓名進行同步")
    parser.add_argument("--all", action="store_true", help="全量同步所有學員")
    parser.add_argument("--apply", action="store_true", help="實際寫入 Supabase (預設為 dry-run)")
    args = parser.parse_args()

    pipeline = TeachingSyncPipeline()
    dry_run = not args.apply

    if args.student:
        student_id = args.student
        # 支援傳入學生姓名反查 ID
        if not (len(student_id) == 36 and "-" in student_id):
            with pipeline.students_file.open("r", encoding="utf-8") as f:
                students = json.load(f)
            found = next((s for s in students if s.get("name") == student_id), None)
            if found:
                student_id = found["id"]

        print(f"正在執行學員同步 (mode={'dry-run' if dry_run else 'apply'})...")
        res = pipeline.sync_student(student_id, dry_run=dry_run)
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        return 0 if res.success else 1

    if args.all:
        print(f"正在執行全量同步 (mode={'dry-run' if dry_run else 'apply'})...")
        report = pipeline.sync_all(dry_run=dry_run)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("success") else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
