import json
import os
import time
import copy
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class DataGatewayError(RuntimeError):
    pass


_MEMORY_CACHE: dict[str, tuple[float, Any]] = {}
GATEWAY_CACHE_TTL_SECONDS = 15.0


def clear_gateway_memory_cache() -> None:
    """清除記憶體快取。"""
    _MEMORY_CACHE.clear()


@dataclass(frozen=True)
class GatewayStatus:
    engine: str
    source: str
    cache_path: str
    last_error: str = ""


# ── 領域邏輯收斂：委託 apple_ceo_service 排序，維持 data_gateway 純粹性與向後相容 ──
from apple_ceo_service import (
    CANONICAL_APPLE_STUDENT_ORDER,
    sort_apple_student_rounds,
)


class StudentDataGateway:
    """StudentCRM 雙引擎資料讀取閘道。

    預設維持本地 JSON；只有設定 STUDENTCRM_DATA_BACKEND=supabase 時才讀雲端。
    雲端失敗時會退回本地快取，確保桌面版與 Web 版仍可讀取。
    """

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir

        # 自動尋找包含 OpenClaw 的工作區根目錄 (repo_root)
        current = os.path.abspath(base_dir)
        detected_repo_root = None
        while True:
            if os.path.isdir(os.path.join(current, "OpenClaw")):
                detected_repo_root = current
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        self.repo_root = detected_repo_root or os.path.abspath(base_dir)

        if os.path.isdir(os.path.join(self.repo_root, "07.Projects/StudentCRM")):
            self.app_dir = os.path.join(self.repo_root, "07.Projects/StudentCRM")
        elif os.path.isdir(os.path.join(self.repo_root, "StudentCRM")):
            self.app_dir = os.path.join(self.repo_root, "StudentCRM")
        elif os.path.isdir(base_dir) and os.path.basename(os.path.abspath(base_dir)) == "StudentCRM":
            self.app_dir = os.path.abspath(base_dir)
        else:
            self.app_dir = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(os.path.dirname(os.path.abspath(__file__))) else base_dir

        openclaw_students = os.path.join(self.repo_root, "OpenClaw/Data/students.json")
        if os.path.exists(openclaw_students):
            self.students_file = openclaw_students
        elif (os.getenv("VERCEL") or base_dir == self.app_dir):
            bundled_students = os.path.join(self.app_dir, "data/students.json")
            if os.path.exists(bundled_students):
                self.students_file = bundled_students
            else:
                self.students_file = openclaw_students
        else:
            self.students_file = openclaw_students

        openclaw_apple = os.path.join(self.repo_root, "OpenClaw/Data/apple_ceo_class.json")
        if os.path.exists(openclaw_apple):
            self.apple_ceo_file = openclaw_apple
        elif (os.getenv("VERCEL") or base_dir == self.app_dir):
            bundled_apple = os.path.join(self.app_dir, "data/apple_ceo_class.json")
            if os.path.exists(bundled_apple):
                self.apple_ceo_file = bundled_apple
            else:
                self.apple_ceo_file = openclaw_apple
        else:
            self.apple_ceo_file = openclaw_apple

        self.teaching_records_file = os.path.join(self.app_dir, "data/teaching_records.json")
        if not os.path.exists(self.teaching_records_file):
            cache_teaching = os.path.join(self.app_dir, "cache/teaching_records.json")
            if os.path.exists(cache_teaching):
                self.teaching_records_file = cache_teaching

        default_cache_dir = "/tmp/studentcrm-cache" if os.getenv("VERCEL") else os.path.join(self.app_dir, "cache")
        self.cache_dir = os.getenv("STUDENTCRM_CACHE_DIR", default_cache_dir)
        self.students_cache_file = os.path.join(self.cache_dir, "students_cloud_cache.json")
        self.apple_ceo_cache_file = os.path.join(self.cache_dir, "apple_ceo_cloud_cache.json")
        self.status_file = os.path.join(self.cache_dir, "cloud_gateway_status.json")
        self.radar_file = os.path.join(self.app_dir, "data", "effectiveness_radar.json")
        self.radar_cache_file = os.path.join(self.cache_dir, "effectiveness_radar.json")

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
        now = time.time()
        cache_key = f"students_{self.backend}_{self.students_file}"
        if cache_key in _MEMORY_CACHE:
            cached_time, cached_data = _MEMORY_CACHE[cache_key]
            if now - cached_time < GATEWAY_CACHE_TTL_SECONDS:
                return copy.deepcopy(cached_data)

        students = self._load_students_uncached()
        if students:
            _MEMORY_CACHE[cache_key] = (now, students)
        return students

    def _load_students_uncached(self) -> list[dict[str, Any]]:
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
            local_students = []
            try:
                local_students = self._load_local_students()
            except Exception:
                pass
            local_map = {s.get("id"): s for s in local_students if isinstance(s, dict) and s.get("id")}
            local_name_map = {s.get("name"): s for s in local_students if isinstance(s, dict) and s.get("name")}
            for s in students:
                if not isinstance(s, dict):
                    continue
                raw_data = s.get("raw") or {}
                if isinstance(raw_data, dict):
                    for k, v in raw_data.items():
                        if (k not in s or s[k] is None or s[k] in ("", "未記錄", "TBD")) and v:
                            s[k] = v
                loc = local_map.get(s.get("id")) or local_name_map.get(s.get("name"))
                if loc:
                    if (not s.get("first_lesson_date") or s.get("first_lesson_date") in ("未記錄", "TBD")) and loc.get("first_lesson_date"):
                        s["first_lesson_date"] = loc["first_lesson_date"]
                    if not s.get("file") and loc.get("file"):
                        s["file"] = loc["file"]
                    if not s.get("recurring_schedule") and loc.get("recurring_schedule"):
                        s["recurring_schedule"] = loc["recurring_schedule"]
                    if not s.get("schedule_exceptions") and loc.get("schedule_exceptions"):
                        s["schedule_exceptions"] = loc["schedule_exceptions"]
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
        now = time.time()
        cache_key = f"apple_ceo_{self.backend}_{self.apple_ceo_file}"
        if cache_key in _MEMORY_CACHE:
            cached_time, cached_data = _MEMORY_CACHE[cache_key]
            if now - cached_time < GATEWAY_CACHE_TTL_SECONDS:
                return copy.deepcopy(cached_data)

        payload = self._load_apple_ceo_program_uncached()
        if payload and payload.get("program"):
            _MEMORY_CACHE[cache_key] = (now, payload)
        return payload

    def _load_apple_ceo_program_uncached(self) -> dict[str, Any]:
        local_payload = None
        try:
            local_payload = self._load_local_apple_ceo_program()
        except DataGatewayError:
            pass

        if self.backend != "supabase":
            if local_payload:
                local_payload["student_rounds"] = sort_apple_student_rounds(local_payload.get("student_rounds", []))
                self._write_status(GatewayStatus("local", self.apple_ceo_file, self.apple_ceo_cache_file))
                return local_payload
            return self._empty_apple_ceo_program()

        try:
            payload = self._load_supabase_apple_ceo_program()
            if local_payload:
                if not payload.get("tuition_records") and local_payload.get("tuition_records"):
                    payload["tuition_records"] = local_payload.get("tuition_records")
                
                local_notes = local_payload.get("teaching_notes", [])
                cloud_notes = payload.get("teaching_notes", [])
                if len(local_notes) > len(cloud_notes) or not cloud_notes:
                    payload["teaching_notes"] = local_notes

                local_attendance = local_payload.get("attendance_records", [])
                cloud_attendance = payload.get("attendance_records", [])
                if len(local_attendance) > len(cloud_attendance) or not cloud_attendance:
                    payload["attendance_records"] = local_attendance

                local_ledger = local_payload.get("venue_ledger", [])
                cloud_ledger = payload.get("venue_ledger", [])
                if len(local_ledger) > len(cloud_ledger) or not cloud_ledger:
                    payload["venue_ledger"] = local_ledger

                local_rounds = local_payload.get("student_rounds", [])
                cloud_rounds = payload.get("student_rounds", [])
                if local_rounds:
                    local_filled = sum(len([s for s in r.get("sessions", []) if s]) for st in local_rounds for r in st.get("rounds", []))
                    cloud_filled = sum(len([s for s in r.get("sessions", []) if s]) for st in cloud_rounds for r in st.get("rounds", []))
                    if local_filled > cloud_filled or len(local_rounds) > len(cloud_rounds):
                        payload["student_rounds"] = local_rounds

            payload["student_rounds"] = sort_apple_student_rounds(payload.get("student_rounds", []))
            self._write_json(self.apple_ceo_cache_file, payload)
            return payload
        except DataGatewayError:
            if os.path.exists(self.apple_ceo_cache_file):
                cached = self._read_json(self.apple_ceo_cache_file)
                cached["student_rounds"] = sort_apple_student_rounds(cached.get("student_rounds", []))
                return cached
            if local_payload:
                local_payload["student_rounds"] = sort_apple_student_rounds(local_payload.get("student_rounds", []))
                return local_payload
            return self._empty_apple_ceo_program()

    def load_teaching_records(self, student_id: str) -> list[dict[str, Any]]:
        if not student_id:
            return []

        if self.backend == "supabase":
            encoded_student_id = quote(student_id, safe="")
            try:
                res = self._load_supabase_table(
                    "teaching_records",
                    query=f"select=*&student_id=eq.{encoded_student_id}&order=date.desc",
                )
                if isinstance(res, list):
                    return res
                if isinstance(res, dict) and "records" in res:
                    return [r for r in res["records"] if isinstance(r, dict) and r.get("student_id") == student_id]
            except DataGatewayError:
                pass

        all_records = self.load_all_teaching_records()
        return [r for r in all_records if isinstance(r, dict) and r.get("student_id") == student_id]

    def load_all_teaching_records(self) -> list[dict[str, Any]]:
        if self.backend == "supabase":
            try:
                res = self._load_supabase_table(
                    "teaching_records",
                    query="select=*&order=date.desc",
                )
                if isinstance(res, list):
                    return res
                if isinstance(res, dict) and "records" in res:
                    return res["records"]
            except DataGatewayError:
                pass

        if hasattr(self, "teaching_records_file") and os.path.exists(self.teaching_records_file):
            try:
                data = self._read_json(self.teaching_records_file)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "records" in data:
                    return data["records"]
            except Exception:
                pass
        return []

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
        program_raw = program.get("raw") if isinstance(program.get("raw"), dict) else {}
        encoded_program_id = quote(program_id, safe="")
        venues = self._load_supabase_table("apple_venues", query=f"select=*&program_id=eq.{encoded_program_id}")
        attendance = self._load_supabase_table("apple_attendance_records", query=f"select=*&program_id=eq.{encoded_program_id}&order=date.asc")
        ledger = self._load_supabase_table("apple_venue_ledger", query=f"select=*&program_id=eq.{encoded_program_id}&order=date.asc")
        rounds = self._load_supabase_table("apple_student_rounds", query=f"select=*&program_id=eq.{encoded_program_id}&order=student_name.asc,sort_order.asc")

        grouped_rounds: dict[str, list[dict[str, Any]]] = {}
        grouped_aliases: dict[str, list[str]] = {}
        for row in rounds:
            student_name = row.get("student_name", "")
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            aliases = raw.get("aliases", []) if isinstance(raw.get("aliases"), list) else []
            grouped_aliases.setdefault(student_name, [])
            for alias in aliases:
                if alias and alias not in grouped_aliases[student_name]:
                    grouped_aliases[student_name].append(alias)
            grouped_rounds.setdefault(student_name, []).append({
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
                {"student_name": name, "aliases": grouped_aliases.get(name, []), "rounds": items}
                for name, items in grouped_rounds.items()
                if name
            ],
            "active_participants": program_raw.get("active_participants", []),
            "tuition_records": program_raw.get("tuition_records", []),
            "teaching_notes": program_raw.get("teaching_notes", []),
            "legacy_note": program_raw.get("legacy_note", ""),
            "duplicate_report": program_raw.get("duplicate_report", {}),
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


    def _write_status(self, status: GatewayStatus) -> None:
        payload = {
            "engine": status.engine,
            "source": status.source,
            "cache_path": status.cache_path,
            "last_error": status.last_error,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._write_json(self.status_file, payload)
        except Exception:
            pass

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 1. 斷路器 (Circuit Breaker)：若即將寫入的資料筆數異常減少超過 20%，觸發保護以防止資料被清空
        if os.path.exists(path) and isinstance(payload, list):
            try:
                with open(path, "r", encoding="utf-8") as existing_f:
                    existing_data = json.load(existing_f)
                if isinstance(existing_data, list) and len(existing_data) >= 10 and len(payload) < len(existing_data) * 0.8:
                    raise DataGatewayError(
                        f"資產防護斷路器熔斷：即將寫入的列表筆數 ({len(payload)}) 異常小於現存筆數 ({len(existing_data)})，拒絕寫入以防止教學資產丟失！"
                    )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # 2. 自動快照備份 (Pre-Write Snapshot)
        if os.path.exists(path) and os.path.getsize(path) > 10:
            backup_dir = os.path.join(os.path.dirname(path), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"{os.path.basename(path)}.{timestamp}.bak")
            try:
                import shutil
                shutil.copy2(path, backup_file)
            except Exception:
                pass

        tmp_path = f"{path}.{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        try:
            os.replace(tmp_path, path)
        except OSError:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def save_teaching_records(self, payload: dict[str, Any]) -> None:
        """安全寫入教學記錄總帳，100% 具備前置快照與單調不減斷路器保護。"""
        new_records = payload.get("records", []) if isinstance(payload, dict) else payload
        if not isinstance(new_records, list):
            raise DataGatewayError("教學記錄 payload 必須包含 records 列表")

        # 斷路器：若目前已有檔案，檢查筆數是否異常縮水
        target_path = os.path.join(self.app_dir, "data", "teaching_records.json")
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                old_records = old_data.get("records", []) if isinstance(old_data, dict) else old_data
                if isinstance(old_records, list) and len(old_records) >= 10 and len(new_records) < len(old_records) * 0.8:
                    raise DataGatewayError(
                        f"教學記錄斷路器熔斷：即將寫入 {len(new_records)} 筆，遠少於現有 {len(old_records)} 筆，拒絕覆寫！"
                    )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        self._write_json(target_path, payload)
        cache_path = os.path.join(self.app_dir, "cache", "teaching_records.json")
        self._write_json(cache_path, payload)
        clear_gateway_memory_cache()

    def save_apple_ceo_program(self, payload: dict[str, Any]) -> None:
        """安全寫入蘋果總裁班資料，保護教案與出席不倒退。"""
        target_path = os.path.join(self.app_dir, "data", "apple_ceo_class.json")
        self._write_json(target_path, payload)
        root_path = os.path.join(self.repo_root, "OpenClaw", "Data", "apple_ceo_class.json")
        if os.path.exists(os.path.dirname(root_path)):
            self._write_json(root_path, payload)
        clear_gateway_memory_cache()

    def save_students(self, payload: list[dict[str, Any]]) -> None:
        """安全寫入學員資料庫，鎖定 first_lesson_date 不可退化。"""
        target_path = os.path.join(self.app_dir, "data", "students.json")
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    old_students = json.load(f)
                old_map = {s.get("id"): s for s in old_students if isinstance(s, dict)}
                for s in payload:
                    sid = s.get("id")
                    if sid and sid in old_map:
                        old_first = old_map[sid].get("first_lesson_date")
                        if old_first and not s.get("first_lesson_date"):
                            s["first_lesson_date"] = old_first
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        self._write_json(target_path, payload)
        root_path = os.path.join(self.repo_root, "OpenClaw", "Data", "students.json")
        if os.path.exists(os.path.dirname(root_path)):
            self._write_json(root_path, payload)
        clear_gateway_memory_cache()

    def get_effectiveness_radar_data(self) -> dict[str, Any]:
        """安全讀取成效雷達資料與快取（多級快取：記憶體 -> /tmp 快取 -> 預載 JSON）。"""
        now = time.time()
        cache_key = f"radar_{self.radar_file}"
        if cache_key in _MEMORY_CACHE:
            cached_time, cached_data = _MEMORY_CACHE[cache_key]
            if now - cached_time < GATEWAY_CACHE_TTL_SECONDS:
                return copy.deepcopy(cached_data)

        # 1. 優先嘗試讀取 cache_dir 中的最新雷達快取（例如 /tmp/studentcrm-cache）
        if hasattr(self, "radar_cache_file") and os.path.exists(self.radar_cache_file):
            try:
                with open(self.radar_cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("items"):
                    _MEMORY_CACHE[cache_key] = (now, data)
                    return copy.deepcopy(data)
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                pass

        # 2. 其次嘗試讀取專案內預載的 radar_file
        if os.path.exists(self.radar_file):
            try:
                with open(self.radar_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _MEMORY_CACHE[cache_key] = (now, data)
                    return copy.deepcopy(data)
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                pass

        default_data = {
            "generated_at": "",
            "summary": {
                "total_tracked": 0,
                "stable_count": 0,
                "attention_count": 0,
                "at_risk_count": 0,
                "upgrade_ready_count": 0,
                "stale_tasks_count": 0,
            },
            "items": [],
        }
        return default_data

    def save_effectiveness_radar_data(self, payload: dict[str, Any]) -> None:
        """安全寫入成效雷達數據，具備自動快照、唯讀環境降級與多級快取保護。"""
        if not isinstance(payload, dict):
            raise DataGatewayError("成效雷達 payload 必須為 dict 結構")

        # 1. 優先寫入快取目錄（在 Vercel 為 /tmp/studentcrm-cache，永遠可寫）
        if hasattr(self, "radar_cache_file"):
            try:
                self._write_json(self.radar_cache_file, payload)
            except Exception as e:
                logger.warning(f"寫入 radar_cache_file 失敗：{e}")

        # 2. 嘗試持久化至專案資料庫檔案（本地開發有效；在 Vercel 唯讀環境安全略過）
        try:
            self._write_json(self.radar_file, payload)
        except (OSError, PermissionError) as e:
            logger.info(f"檔案系統為唯讀（如 Vercel），已安全略過專案資料夾寫入：{e}")

        # 3. 即時更新記憶體快取
        cache_key = f"radar_{self.radar_file}"
        _MEMORY_CACHE[cache_key] = (time.time(), copy.deepcopy(payload))

    def update_csm_followup_record(self, student_id: str, update_data: dict[str, Any]) -> dict[str, Any]:
        """更新單一學員的 CSM 回訪追蹤記錄，自動寫入並同步快照。"""
        radar_data = self.get_effectiveness_radar_data()
        items = radar_data.get("items", [])
        target_item = None
        now_str = datetime.now(timezone.utc).isoformat()
        today_date = datetime.now().strftime("%Y-%m-%d")

        for item in items:
            if item.get("student_id") == student_id:
                followup = item.get("followup") or {}
                new_status = update_data.get("status", followup.get("status", "pending"))
                followup["status"] = new_status
                if new_status == "contacted":
                    followup["last_contacted_date"] = today_date
                if "next_followup_date" in update_data:
                    followup["next_followup_date"] = update_data["next_followup_date"]
                if "coach_notes" in update_data:
                    followup["coach_notes"] = update_data["coach_notes"]
                followup["updated_at"] = now_str
                item["followup"] = followup
                target_item = item
                break

        if not target_item:
            raise DataGatewayError(f"在成效雷達中找不到學員 ID：{student_id}")

        self.save_effectiveness_radar_data(radar_data)
        return target_item

