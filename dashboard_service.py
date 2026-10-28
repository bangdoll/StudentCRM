"""
儀表板視圖模型聚合深模組 (dashboard_service.py)
================================================
職責：依循 Matt Pocock 深模組原則設計，封裝教練主控台儀表板 (Dashboard) 
所需的學員狀態預測、排程分析、流失風險分類、蘋果總裁班摘要與短效快取。
消除原本散落於 routers/coach.py 的程序性迴圈計算，大幅收斂路由控制層。
"""

from __future__ import annotations

import copy
import logging
import os
import time
from datetime import datetime, date
from typing import Any, Callable

from apple_ceo_service import extract_session_date, summarize_apple_ceo_program
from prediction_service import predict_student_status
from radar_service import build_full_effectiveness_radar
from schedule_service import (
    get_document_exceptions,
    get_next_lesson_sort_key,
    get_next_occurrence,
)
from student_service import get_global_renewal_radar

logger = logging.getLogger(__name__)


_DASHBOARD_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "payload": None,
}

_HOME_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "payload": None,
}


def clear_dashboard_cache() -> None:
    """清空儀表板與首頁聚合資料快取。"""
    _DASHBOARD_CACHE["timestamp"] = 0.0
    _DASHBOARD_CACHE["payload"] = None
    _HOME_CACHE["timestamp"] = 0.0
    _HOME_CACHE["payload"] = None


def _call_features_analyzer(
    features_analyzer: Callable[..., dict[str, Any]],
    student_id: str,
    student: dict[str, Any],
) -> dict[str, Any]:
    """優先傳入 target_student 避免 N+1 重複查詢，並向下相容單參數測試替身。"""
    try:
        return features_analyzer(student_id, target_student=student)
    except TypeError:
        return features_analyzer(student_id)



def _parse_next_lesson(value: str) -> date | None:
    date_text = extract_session_date(value or "")
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None


def build_dashboard_context(
    students_loader: Callable[[], list[dict[str, Any]]] | None = None,
    apple_program_loader: Callable[[], dict[str, Any]] | None = None,
    sync_status_loader: Callable[[], dict[str, Any]] | None = None,
    metadata_loader: Callable[[str], dict[str, Any]] | None = None,
    features_analyzer: Callable[[str], dict[str, Any]] | None = None,
    status_predictor: Callable[[dict[str, Any], str | None], Any] | None = None,
    base_dir: str = "",
) -> dict[str, Any]:
    """【單一法定入口】建構教練儀表板所需之完整視圖上下文。"""
    now_ts = time.time()
    # 支援短效記憶體快取（15 秒）
    if _DASHBOARD_CACHE["payload"] is not None and (now_ts - _DASHBOARD_CACHE["timestamp"] < 15.0):
        return copy.deepcopy(_DASHBOARD_CACHE["payload"])

    # 依賴解析與懶載入
    if students_loader is None:
        import main
        students_loader = main.load_students
    if apple_program_loader is None:
        import main
        apple_program_loader = main.load_apple_ceo_program
    if sync_status_loader is None:
        import main
        sync_status_loader = main.student_gateway.status
    if metadata_loader is None:
        import main
        metadata_loader = main.get_student_metadata
    if features_analyzer is None:
        import main
        features_analyzer = main.analyze_student_features
    if status_predictor is None:
        status_predictor = predict_student_status
    if not base_dir:
        import main
        base_dir = getattr(main, "BASE_DIR", "")

    raw_students = students_loader()
    # 深拷貝避免就地修改外部快取
    students = copy.deepcopy(raw_students) if isinstance(raw_students, list) else []

    for student in students:
        student_file = os.path.join(base_dir, student.get("file", "").lstrip("/"))
        student["meta"] = metadata_loader(student_file)
        student["features"] = _call_features_analyzer(features_analyzer, student.get("id", ""), student)
        student["prediction"] = status_predictor(student["features"], student.get("next_lesson"))

    apple_program = apple_program_loader()
    apple_summary = summarize_apple_ceo_program(apple_program)
    today = datetime.now().date()

    upcoming_students: list[dict[str, Any]] = []
    unscheduled_students: list[dict[str, Any]] = []
    risk_students: list[dict[str, Any]] = []
    freezing_students: list[dict[str, Any]] = []
    stable_students: list[dict[str, Any]] = []

    for student in students:
        next_date = _parse_next_lesson(student.get("next_lesson") or "")
        if next_date:
            days = (next_date - today).days
            student["next_lesson_days"] = days
            if 0 <= days <= 14:
                upcoming_students.append(student)
        else:
            student["next_lesson_days"] = None
            unscheduled_students.append(student)

        status = student.get("prediction", {}).get("status", "")
        if "高流失" in status:
            risk_students.append(student)
        elif "冰凍期" in status:
            freezing_students.append(student)
        elif "穩定留存" in status:
            stable_students.append(student)

    students.sort(key=lambda item: (
        item.get("next_lesson_days") is None,
        item.get("next_lesson_days") if item.get("next_lesson_days") is not None else 9999,
        item.get("name", ""),
    ))

    sync_status = sync_status_loader()
    program_data = apple_program.get("program", {}) if isinstance(apple_program, dict) else {}

    result = {
        "students": students,
        "student_count": len(students),
        "upcoming_students": upcoming_students,
        "unscheduled_students": unscheduled_students,
        "risk_students": risk_students,
        "freezing_students": freezing_students,
        "stable_students": stable_students,
        "apple_program": program_data,
        "apple_summary": apple_summary,
        "sync_status": sync_status,
    }

    _DASHBOARD_CACHE["timestamp"] = now_ts
    _DASHBOARD_CACHE["payload"] = copy.deepcopy(result)
    return result


def build_home_context(
    students_loader: Callable[[], list[dict[str, Any]]] | None = None,
    apple_program_loader: Callable[[], dict[str, Any]] | None = None,
    data_gateway: Any | None = None,
    metadata_loader: Callable[[str], dict[str, Any]] | None = None,
    cloud_meta_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    features_analyzer: Callable[..., dict[str, Any]] | None = None,
    status_predictor: Callable[[dict[str, Any], str | None], Any] | None = None,
    base_dir: str = "",
) -> dict[str, Any]:
    """【單一法定入口】建構教練首頁行動看板 (index.html) 所需之完整視圖上下文。"""
    now_ts = time.time()
    if _HOME_CACHE["payload"] is not None and (now_ts - _HOME_CACHE["timestamp"] < 15.0):
        return copy.deepcopy(_HOME_CACHE["payload"])

    if students_loader is None:
        import main
        students_loader = main.load_students
    if apple_program_loader is None:
        import main
        apple_program_loader = main.load_apple_ceo_program
    if data_gateway is None:
        import main
        data_gateway = main.student_gateway
    if metadata_loader is None:
        import main
        metadata_loader = main.get_student_metadata
    if cloud_meta_builder is None:
        import main
        cloud_meta_builder = main.build_cloud_student_meta
    if features_analyzer is None:
        import main
        features_analyzer = main.analyze_student_features
    if status_predictor is None:
        status_predictor = predict_student_status
    if not base_dir:
        import main
        base_dir = getattr(main, "BASE_DIR", "")

    raw_students = students_loader()
    students = copy.deepcopy(raw_students) if isinstance(raw_students, list) else []

    for s in students:
        if "recurring_schedule" in s and not s.get("next_lesson"):
            student_file = os.path.join(base_dir, s["file"].lstrip("/")) if s.get("file") else ""
            doc_exceptions = get_document_exceptions(student_file)
            json_exceptions = s.get("schedule_exceptions", [])
            all_exceptions = list(set(json_exceptions + doc_exceptions))
            s["next_lesson"] = get_next_occurrence(s["recurring_schedule"], all_exceptions)

        file_path = os.path.join(base_dir, s["file"].lstrip("/")) if s.get("file") else ""
        file_meta = metadata_loader(file_path) if file_path and os.path.exists(file_path) else {}
        cloud_meta = cloud_meta_builder(s)
        s["meta"] = {**cloud_meta, **file_meta}
        if not s["meta"].get("first_lesson_date") or s["meta"]["first_lesson_date"] in ("未記錄", "TBD"):
            s["meta"]["first_lesson_date"] = s.get("first_lesson_date") or "未記錄"
        if not s["meta"].get("last_lesson_date") or s["meta"]["last_lesson_date"] in ("未記錄", "TBD"):
            s["meta"]["last_lesson_date"] = s.get("latest_date") or "未記錄"
        if not s["meta"].get("lessons_count") or s["meta"]["lessons_count"] == 0:
            s["meta"]["lessons_count"] = s.get("lessons_count") or 0

        s["features"] = _call_features_analyzer(features_analyzer, s.get("id", ""), s)
        s["prediction"] = status_predictor(s["features"], s.get("next_lesson"))

    sorted_students = sorted(students, key=get_next_lesson_sort_key)
    apple_program = apple_program_loader()
    apple_summary = summarize_apple_ceo_program(apple_program)
    renewal_radar = get_global_renewal_radar(sorted_students)

    effectiveness_radar = data_gateway.get_effectiveness_radar_data() if data_gateway else {}
    if not effectiveness_radar.get("items") and data_gateway is not None:
        try:
            effectiveness_radar = build_full_effectiveness_radar(data_gateway)
        except Exception as exc:
            logger.warning(f"首頁建構完整成效雷達失敗，使用預設快取: {exc}")

    program_data = apple_program.get("program", {}) if isinstance(apple_program, dict) else {}
    result = {
        "students": sorted_students,
        "apple_program": program_data,
        "apple_summary": apple_summary,
        "renewal_radar": renewal_radar,
        "effectiveness_radar": effectiveness_radar,
    }

    _HOME_CACHE["timestamp"] = now_ts
    _HOME_CACHE["payload"] = copy.deepcopy(result)
    return result


