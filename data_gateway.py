import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class DataGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewayStatus:
    engine: str
    source: str
    cache_path: str
    last_error: str = ""


class StudentDataGateway:
    """StudentCRM 雙引擎資料讀取閘道。

    預設維持本地 JSON；只有設定 STUDENTCRM_DATA_BACKEND=supabase 時才讀雲端。
    雲端失敗時會退回本地快取，確保桌面版與 Web 版仍可讀取。
    """

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        self.app_dir = os.path.join(base_dir, "StudentCRM") if os.path.isdir(os.path.join(base_dir, "StudentCRM")) else base_dir
        self.students_file = os.path.join(base_dir, "OpenClaw/Data/students.json")
        self.apple_ceo_file = os.path.join(base_dir, "OpenClaw/Data/apple_ceo_class.json")
        default_cache_dir = "/tmp/studentcrm-cache" if os.getenv("VERCEL") else os.path.join(self.app_dir, "cache")
        self.cache_dir = os.getenv("STUDENTCRM_CACHE_DIR", default_cache_dir)
        self.students_cache_file = os.path.join(self.cache_dir, "students_cloud_cache.json")
        self.apple_ceo_cache_file = os.path.join(self.cache_dir, "apple_ceo_cloud_cache.json")
        self.status_file = os.path.join(self.cache_dir, "cloud_gateway_status.json")

        self.backend = os.getenv("STUDENTCRM_DATA_BACKEND", "local").strip().lower()
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.supabase_key = (
            os.getenv("SUPABASE_ANON_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        self.supabase_write_key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or self.supabase_key
        )

    def load_students(self) -> list[dict[str, Any]]:
        if self.backend != "supabase":
            try:
                students = self._load_local_students()
                self._write_status(GatewayStatus("local", self.students_file, self.students_cache_file))
                return students
            except DataGatewayError as exc:
                self._write_status(GatewayStatus("unavailable", self.students_file, self.students_cache_file, str(exc)))
                return []

        try:
            students = self._load_supabase_table("students")
            self._write_json(self.students_cache_file, students)
            self._write_status(GatewayStatus("supabase", "students", self.students_cache_file))
            return students
        except DataGatewayError as exc:
            if os.path.exists(self.students_cache_file):
                cached = self._read_json(self.students_cache_file)
                self._write_status(
                    GatewayStatus("cache", self.students_cache_file, self.students_cache_file, str(exc))
                )
                return cached

            try:
                students = self._load_local_students()
                self._write_status(GatewayStatus("local_fallback", self.students_file, self.students_cache_file, str(exc)))
                return students
            except DataGatewayError as local_exc:
                self._write_status(
                    GatewayStatus("unavailable", self.students_file, self.students_cache_file, f"{exc}; {local_exc}")
                )
                return []

    def load_apple_ceo_program(self) -> dict[str, Any]:
        if self.backend != "supabase":
            try:
                return self._load_local_apple_ceo_program()
            except DataGatewayError:
                return self._empty_apple_ceo_program()

        try:
            payload = self._load_supabase_apple_ceo_program()
            self._write_json(self.apple_ceo_cache_file, payload)
            return payload
        except DataGatewayError:
            if os.path.exists(self.apple_ceo_cache_file):
                return self._read_json(self.apple_ceo_cache_file)
            try:
                return self._load_local_apple_ceo_program()
            except DataGatewayError:
                return self._empty_apple_ceo_program()

    def status(self) -> dict[str, Any]:
        if os.path.exists(self.status_file):
            return self._read_json(self.status_file)
        return {
            "engine": "local",
            "source": self.students_file,
            "cache_path": self.students_cache_file,
            "last_error": "",
            "checked_at": "",
        }

    def _load_local_students(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.students_file):
            raise DataGatewayError(f"找不到本地 students 檔案：{self.students_file}")
        return self._read_json(self.students_file)

    def _load_local_apple_ceo_program(self) -> dict[str, Any]:
        if not os.path.exists(self.apple_ceo_file):
            raise DataGatewayError(f"找不到本地蘋果總裁班檔案：{self.apple_ceo_file}")
        return self._read_json(self.apple_ceo_file)

    @staticmethod
    def _empty_apple_ceo_program() -> dict[str, Any]:
        return {
            "program": {
                "id": "apple-ceo",
                "name": "蘋果總裁班",
                "url": "",
                "description": "",
                "schedule": "",
                "capacity": "",
                "round_size": 8,
                "price_per_student": 0,
                "validity_rule": "",
                "leave_rule": "",
                "join_rule": "",
            },
            "venue": {
                "name": "",
                "address": "",
                "parking": "",
                "metro": "",
                "cost_per_person": 0,
            },
            "attendance_records": [],
            "venue_ledger": [],
            "student_rounds": [],
            "active_participants": [],
            "legacy_note": "",
        }

    def _load_supabase_apple_ceo_program(self) -> dict[str, Any]:
        programs = self._load_supabase_table("apple_programs")
        if not programs:
            raise DataGatewayError("Supabase apple_programs 無資料")

        program = programs[0]
        program_id = program.get("id", "apple-ceo")
        encoded_program_id = quote(program_id, safe="")
        venues = self._load_supabase_table("apple_venues", query=f"select=*&program_id=eq.{encoded_program_id}")
        attendance = self._load_supabase_table("apple_attendance_records", query=f"select=*&program_id=eq.{encoded_program_id}&order=date.asc")
        ledger = self._load_supabase_table("apple_venue_ledger", query=f"select=*&program_id=eq.{encoded_program_id}&order=date.asc")
        rounds = self._load_supabase_table("apple_student_rounds", query=f"select=*&program_id=eq.{encoded_program_id}&order=student_name.asc,sort_order.asc")

        grouped_rounds: dict[str, list[dict[str, Any]]] = {}
        for row in rounds:
            grouped_rounds.setdefault(row.get("student_name", ""), []).append({
                "label": row.get("label", ""),
                "payment_status": row.get("payment_status", ""),
                "sessions": row.get("sessions", []),
            })

        return {
            "program": {
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
            },
            "venue": self._format_apple_venue(venues[0] if venues else {}),
            "attendance_records": [self._format_apple_attendance(row) for row in attendance],
            "venue_ledger": [self._format_apple_ledger(row) for row in ledger],
            "student_rounds": [
                {"student_name": name, "rounds": items}
                for name, items in grouped_rounds.items()
                if name
            ],
        }

    @staticmethod
    def _format_apple_venue(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": row.get("name", ""),
            "address": row.get("address", ""),
            "parking": row.get("parking", ""),
            "metro": row.get("metro", ""),
            "cost_per_person": row.get("cost_per_person", 0),
        }

    @staticmethod
    def _format_apple_attendance(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "date": row.get("date", ""),
            "venue": row.get("venue", ""),
            "attendee_count": row.get("attendee_count", 0),
            "attendees": row.get("attendees", []),
            "note": row.get("note", ""),
        }

    @staticmethod
    def _format_apple_ledger(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "date": row.get("date", ""),
            "type": row.get("type", ""),
            "amount": row.get("amount", 0),
            "payer": row.get("payer", ""),
            "headcount": row.get("headcount"),
            "note": row.get("note", ""),
            "balance_after": row.get("balance_after", 0),
        }

    def _load_supabase_table(self, table: str, query: str = "select=*") -> list[dict[str, Any]]:
        if not self.supabase_url or not self.supabase_key:
            raise DataGatewayError("Supabase 環境變數未設定完整")

        encoded_table = quote(table, safe="")
        url = f"{self.supabase_url}/rest/v1/{encoded_table}?{query}"
        request = Request(
            url,
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=10) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raise DataGatewayError(f"Supabase HTTP {exc.code}") from exc
        except URLError as exc:
            raise DataGatewayError(f"Supabase 連線失敗：{exc.reason}") from exc
        except TimeoutError as exc:
            raise DataGatewayError("Supabase 連線逾時") from exc

        data = json.loads(payload)
        if not isinstance(data, list):
            raise DataGatewayError("Supabase 回傳格式不是列表")
        return data

    def write_voice_crm_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        if self.backend != "supabase":
            return {
                "status": "not_written",
                "reason": "目前資料引擎不是 Supabase，未執行寫入。",
                "engine": self.backend,
            }
        if not self.supabase_url or not self.supabase_write_key:
            return {
                "status": "not_written",
                "reason": "Supabase 寫入環境變數未設定完整。",
                "engine": self.backend,
            }

        teaching_record = draft.get("teaching_record") or {}
        matched_student = draft.get("matched_student") or {}
        student_id = matched_student.get("id") or teaching_record.get("student_id")
        written = []

        if teaching_record.get("id"):
            self._upsert_supabase_row("teaching_records", teaching_record)
            written.append({
                "table": "teaching_records",
                "id": teaching_record.get("id"),
            })

        student_updates = draft.get("student_updates") or []
        if student_id and student_updates:
            patch_payload = {
                item.get("field"): item.get("after")
                for item in student_updates
                if item.get("field")
            }
            patch_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._patch_supabase_row("students", "id", student_id, patch_payload)
            written.append({
                "table": "students",
                "id": student_id,
                "fields": sorted(patch_payload.keys()),
            })

        return {
            "status": "written",
            "engine": self.backend,
            "written": written,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def _upsert_supabase_row(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        encoded_table = quote(table, safe="")
        url = f"{self.supabase_url}/rest/v1/{encoded_table}?on_conflict=id"
        return self._send_supabase_json(
            url=url,
            method="POST",
            payload=payload,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )

    def _patch_supabase_row(self, table: str, field: str, value: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        encoded_table = quote(table, safe="")
        encoded_value = quote(value, safe="")
        url = f"{self.supabase_url}/rest/v1/{encoded_table}?{field}=eq.{encoded_value}"
        return self._send_supabase_json(
            url=url,
            method="PATCH",
            payload=payload,
            extra_headers={"Prefer": "return=representation"},
        )

    def _send_supabase_json(
        self,
        url: str,
        method: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "apikey": self.supabase_write_key,
            "Authorization": f"Bearer {self.supabase_write_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        headers.update(extra_headers or {})
        request = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(request, timeout=10) as response:
                response_payload = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise DataGatewayError(f"Supabase 寫入 HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise DataGatewayError(f"Supabase 寫入連線失敗：{exc.reason}") from exc
        except TimeoutError as exc:
            raise DataGatewayError("Supabase 寫入逾時") from exc

        if not response_payload:
            return []
        data = json.loads(response_payload)
        return data if isinstance(data, list) else [data]

    def _write_status(self, status: GatewayStatus) -> None:
        payload = {
            "engine": status.engine,
            "source": status.source,
            "cache_path": status.cache_path,
            "last_error": status.last_error,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.status_file, payload)

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
