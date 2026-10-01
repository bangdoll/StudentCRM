"""教學成果閉環服務。

這個模組只新增獨立的 projected outcome store，不回寫原始教學 Markdown、
students.json 或 teaching_records.json。所有學員成果都先經過學員回報，
再由教練確認，才能進入案例草稿。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parent
PRIMARY_STORE = APP_DIR / "data" / "teaching_outcomes.json"
STORE_NAME = "teaching_outcomes.json"
MAX_ACTIONS = 3
ACTION_STATUSES = {"pending", "in_progress", "completed", "blocked"}


class CreateOutcomeRequest(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=120)
    student_name: str = Field(default="", max_length=120)
    note_key: str = Field(default="", max_length=500)
    note_date: str = Field(default="", max_length=40)
    core_judgment: str = Field(..., min_length=1, max_length=1000)
    action_titles: list[str] = Field(..., min_length=1, max_length=MAX_ACTIONS)
    due_dates: list[str] = Field(default_factory=list, max_length=MAX_ACTIONS)
    next_lesson_question: str = Field(default="", max_length=500)


class BootstrapOutcomeRequest(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=120)


class StudentActionSubmission(BaseModel):
    note_key: str = Field(..., min_length=1, max_length=500)
    note_date: str = Field(default="", max_length=40)
    action_index: int = Field(..., ge=0, le=MAX_ACTIONS - 1)
    status: Literal["in_progress", "completed", "blocked"] = "completed"
    evidence: str = Field(default="", max_length=2000)
    student_feedback: str = Field(default="", max_length=2000)


class VerifyOutcomeRequest(BaseModel):
    verified: bool = True
    coach_note: str = Field(default="", max_length=1000)


class CaseDraftRequest(BaseModel):
    problem: str = Field(..., min_length=1, max_length=1000)
    action: str = Field(..., min_length=1, max_length=1500)
    result: str = Field(..., min_length=1, max_length=1500)
    student_quote: str = Field(default="", max_length=1000)
    privacy_checked: bool = False


class ExperimentObservationRequest(BaseModel):
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    verified_outcomes: int | None = Field(default=None, ge=0)
    coach_minutes_saved: int | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=1000)


DEFAULT_FEATURE_GATES = [
    {
        "id": "teaching-outcome-loop",
        "name": "教學成果閉環",
        "window_days": 28,
        "status": "pilot",
        "stop_rule": "28 天後若行動完成率低於 40% 且沒有已驗證成果，停止擴張並人工覆核。",
    },
    {
        "id": "interactive-note-mvp",
        "name": "互動教學筆記 MVP",
        "window_days": 28,
        "status": "pilot",
        "stop_rule": "若學員沒有提交任何回報，或互動頁未降低教練追問成本，停止擴張並人工覆核。",
    },
    {
        "id": "verified-case-pipeline",
        "name": "第一手案例驗證管線",
        "window_days": 28,
        "status": "pilot",
        "stop_rule": "未完成教練確認與隱私檢查前，不得進入公開案例庫。",
    },
    {
        "id": "solo-capacity-dashboard",
        "name": "一人公司容量儀表",
        "window_days": 28,
        "status": "pilot",
        "stop_rule": "容量假設未經教練確認前，只能作為內部觀測，不得自動調整學員狀態。",
    },
    {
        "id": "feature-stop-gate",
        "name": "功能停損閘門",
        "window_days": 28,
        "status": "active",
        "stop_rule": "沒有可核驗成果或時間節省證據的功能，不得直接擴大到全量流程。",
    },
]


class OutcomeStoreError(RuntimeError):
    """成果資料層錯誤；遇到格式或寫入風險時拒絕繼續。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_store() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": "",
        "outcomes": [],
        "case_drafts": [],
        "feature_gates": copy.deepcopy(DEFAULT_FEATURE_GATES),
    }


def _cache_path() -> Path:
    cache_root = os.getenv("STUDENTCRM_CACHE_DIR")
    if cache_root:
        return Path(cache_root) / STORE_NAME
    if os.getenv("VERCEL"):
        return Path("/tmp/studentcrm-cache") / STORE_NAME
    return APP_DIR / "cache" / STORE_NAME


def _candidate_paths() -> list[Path]:
    cache_path = _cache_path()
    return [cache_path, PRIMARY_STORE] if cache_path != PRIMARY_STORE else [PRIMARY_STORE]


def _normalise_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OutcomeStoreError("教學成果資料格式不是 object，已拒絕讀取")
    store = empty_store()
    for key in ("schema_version", "updated_at", "outcomes", "case_drafts", "feature_gates"):
        if key in raw:
            store[key] = raw[key]
    if not isinstance(store["outcomes"], list) or not isinstance(store["case_drafts"], list):
        raise OutcomeStoreError("教學成果資料的 records 結構不合法，已拒絕讀取")
    if not isinstance(store["feature_gates"], list):
        raise OutcomeStoreError("功能閘門資料結構不合法，已拒絕讀取")
    return store


def load_store(path: str | Path | None = None) -> dict[str, Any]:
    paths = [Path(path)] if path else _candidate_paths()
    for candidate in paths:
        if not candidate.exists():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            return _normalise_store(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OutcomeStoreError(f"讀取教學成果資料失敗：{candidate}：{exc}") from exc
    return empty_store()


def _write_store(store: dict[str, Any], target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup_dir = target.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_name = f"{target.stem}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.json"
        shutil.copy2(target, backup_dir / backup_name)
    temp = target.with_name(f".{target.name}.tmp")
    temp.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def save_store(store: dict[str, Any], path: str | Path | None = None) -> Path:
    normalised = _normalise_store(store)
    normalised["updated_at"] = _now()
    target = Path(path) if path else PRIMARY_STORE
    try:
        return _write_store(normalised, target)
    except (OSError, PermissionError):
        if path:
            raise
        return _write_store(normalised, _cache_path())


def _clean_note_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()


def _find_outcome(store: dict[str, Any], student_id: str, note_key: str) -> dict[str, Any] | None:
    key = _clean_note_key(note_key)
    for outcome in reversed(store.get("outcomes", [])):
        if outcome.get("student_id") != student_id:
            continue
        if _clean_note_key(outcome.get("note_key", "")) == key:
            return outcome
    return None


def _assert_action_titles(action_titles: list[str]) -> list[str]:
    titles = [str(value or "").strip() for value in action_titles[:MAX_ACTIONS]]
    titles = [value for value in titles if value]
    if not titles:
        raise OutcomeStoreError("至少需要一個可執行的下一步行動")
    return titles


def create_outcome(payload: CreateOutcomeRequest, path: str | Path | None = None) -> dict[str, Any]:
    store = load_store(path)
    existing = _find_outcome(store, payload.student_id, payload.note_key)
    if existing:
        return existing
    titles = _assert_action_titles(payload.action_titles)
    due_dates = list(payload.due_dates[:MAX_ACTIONS])
    actions = [
        {
            "id": f"action-{uuid.uuid4().hex[:12]}",
            "title": title,
            "due_date": due_dates[idx] if idx < len(due_dates) else "",
            "status": "pending",
            "evidence": "",
            "student_feedback": "",
            "completed_at": "",
            "last_submitted_at": "",
        }
        for idx, title in enumerate(titles)
    ]
    now = _now()
    outcome = {
        "id": f"outcome-{uuid.uuid4().hex}",
        "student_id": payload.student_id,
        "student_name": payload.student_name,
        "note_key": payload.note_key,
        "note_date": payload.note_date,
        "core_judgment": payload.core_judgment.strip(),
        "next_actions": actions,
        "next_lesson_question": payload.next_lesson_question.strip(),
        "coach_verified": False,
        "coach_note": "",
        "created_at": now,
        "updated_at": now,
    }
    store["outcomes"].append(outcome)
    save_store(store, path)
    return outcome


def bootstrap_outcome(
    student: dict[str, Any],
    note: dict[str, Any],
    micro_cards: dict[str, str],
    path: str | Path | None = None,
) -> dict[str, Any]:
    titles = [
        micro_cards.get("micro_habit", ""),
        micro_cards.get("key_action", ""),
        micro_cards.get("weekly_win", ""),
    ]
    payload = CreateOutcomeRequest(
        student_id=str(student.get("id") or ""),
        student_name=str(student.get("name") or ""),
        note_key=str(note.get("path") or note.get("filename") or note.get("title") or ""),
        note_date=str(note.get("date") or ""),
        core_judgment="待教練覆核：請補上本堂課最重要的判斷與學員要解決的問題。",
        action_titles=titles,
        next_lesson_question="下次上課先回看哪一個行動的實作證據？",
    )
    return create_outcome(payload, path=path)


def submit_student_action(
    student_id: str,
    payload: StudentActionSubmission,
    path: str | Path | None = None,
) -> dict[str, Any]:
    store = load_store(path)
    outcome = _find_outcome(store, student_id, payload.note_key)
    if not outcome:
        raise OutcomeStoreError("這堂課尚未建立教學成果閉環，請先由教練建立課後行動")
    actions = outcome.get("next_actions") or []
    if payload.action_index >= len(actions):
        raise OutcomeStoreError("找不到指定的課後行動")
    action = actions[payload.action_index]
    action["status"] = payload.status
    action["evidence"] = payload.evidence.strip()
    action["student_feedback"] = payload.student_feedback.strip()
    action["last_submitted_at"] = _now()
    if payload.status == "completed":
        action["completed_at"] = action["last_submitted_at"]
    outcome["updated_at"] = _now()
    save_store(store, path)
    return outcome


def verify_outcome(
    outcome_id: str,
    payload: VerifyOutcomeRequest,
    path: str | Path | None = None,
) -> dict[str, Any]:
    store = load_store(path)
    for outcome in store["outcomes"]:
        if outcome.get("id") != outcome_id:
            continue
        outcome["coach_verified"] = bool(payload.verified)
        outcome["coach_note"] = payload.coach_note.strip()
        outcome["updated_at"] = _now()
        save_store(store, path)
        return outcome
    raise OutcomeStoreError(f"找不到教學成果：{outcome_id}")


def create_case_draft(
    outcome_id: str,
    payload: CaseDraftRequest,
    path: str | Path | None = None,
) -> dict[str, Any]:
    store = load_store(path)
    outcome = next((item for item in store["outcomes"] if item.get("id") == outcome_id), None)
    if not outcome:
        raise OutcomeStoreError(f"找不到教學成果：{outcome_id}")
    has_evidence = any(
        action.get("status") == "completed" and str(action.get("evidence") or "").strip()
        for action in outcome.get("next_actions", [])
    )
    if not outcome.get("coach_verified") or not has_evidence or not payload.privacy_checked:
        raise OutcomeStoreError("案例草稿需要教練確認、已完成行動證據與隱私檢查")
    existing = next((item for item in store["case_drafts"] if item.get("outcome_id") == outcome_id), None)
    if existing:
        return existing
    draft = {
        "id": f"case-{uuid.uuid4().hex}",
        "outcome_id": outcome_id,
        "student_id": outcome.get("student_id", ""),
        "problem": payload.problem.strip(),
        "action": payload.action.strip(),
        "result": payload.result.strip(),
        "student_quote": payload.student_quote.strip(),
        "privacy_checked": True,
        "status": "internal_review",
        "created_at": _now(),
    }
    store["case_drafts"].append(draft)
    save_store(store, path)
    return draft


def _capacity_summary(students: list[dict[str, Any]], store: dict[str, Any]) -> dict[str, Any]:
    active_students = [s for s in students if s.get("status") not in ("memorial", "paused")]
    outcomes = store.get("outcomes", [])
    actions = [action for outcome in outcomes for action in outcome.get("next_actions", [])]
    completed = [action for action in actions if action.get("status") == "completed"]
    today = datetime.now().date().isoformat()
    overdue = [
        action for action in actions
        if action.get("status") != "completed" and action.get("due_date") and action["due_date"] < today
    ]
    target = int(os.getenv("STUDENTCRM_ACTIVE_STUDENT_TARGET", "20"))
    completion_rate = round(len(completed) / len(actions), 3) if actions else None
    return {
        "active_student_count": len(active_students),
        "active_student_target": target,
        "capacity_ratio": round(len(active_students) / target, 3) if target else None,
        "tracked_outcome_count": len(outcomes),
        "pending_action_count": len([a for a in actions if a.get("status") in ("pending", "in_progress")]),
        "overdue_action_count": len(overdue),
        "completed_action_count": len(completed),
        "total_action_count": len(actions),
        "action_completion_rate": completion_rate,
        "capacity_assumption_label": "暫定學員容量，請教練確認",
    }


def _gate_decision(gate: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "human_review"
    latest = observations[-1]
    completion = latest.get("completion_rate")
    verified = latest.get("verified_outcomes")
    if completion is not None and completion < 0.4 and (verified or 0) == 0:
        return "stop"
    if completion is not None and (completion >= 0.4 or (verified or 0) > 0):
        return "continue"
    return "human_review"


def feature_gate_summary(store: dict[str, Any]) -> list[dict[str, Any]]:
    observations_by_gate = {}
    for item in store.get("feature_gates", []):
        observations_by_gate[item.get("id")] = item.get("observations", [])
    result = []
    for default in DEFAULT_FEATURE_GATES:
        gate = next((item for item in store.get("feature_gates", []) if item.get("id") == default["id"]), default)
        observations = observations_by_gate.get(default["id"], [])
        result.append({**default, **gate, "observations": observations, "decision": _gate_decision(gate, observations)})
    return result


def record_experiment_observation(
    gate_id: str,
    payload: ExperimentObservationRequest,
    path: str | Path | None = None,
) -> dict[str, Any]:
    store = load_store(path)
    gate = next((item for item in store["feature_gates"] if item.get("id") == gate_id), None)
    if not gate:
        gate = next((item for item in DEFAULT_FEATURE_GATES if item["id"] == gate_id), None)
        if not gate:
            raise OutcomeStoreError(f"找不到功能閘門：{gate_id}")
        gate = copy.deepcopy(gate)
        store["feature_gates"].append(gate)
    gate.setdefault("observations", []).append({
        "recorded_at": _now(),
        "completion_rate": payload.completion_rate,
        "verified_outcomes": payload.verified_outcomes,
        "coach_minutes_saved": payload.coach_minutes_saved,
        "note": payload.note.strip(),
    })
    save_store(store, path)
    return {"gate": gate, "decision": _gate_decision(gate, gate["observations"])}


def outcome_summary(students: list[dict[str, Any]], radar_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    store = load_store()
    outcomes = store.get("outcomes", [])
    verified = [item for item in outcomes if item.get("coach_verified")]
    cases = store.get("case_drafts", [])
    capacity = _capacity_summary(students, store)
    return {
        "outcome_count": len(outcomes),
        "verified_outcome_count": len(verified),
        "case_draft_count": len(cases),
        "capacity": capacity,
        "risk_student_count": len([item for item in (radar_items or []) if item.get("retention_signal") == "at_risk"]),
        "feature_gates": feature_gate_summary(store),
        "storage": "獨立教學成果資料層；原始教學筆記唯讀",
    }


def list_outcomes(path: str | Path | None = None) -> list[dict[str, Any]]:
    return load_store(path).get("outcomes", [])
