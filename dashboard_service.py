"""
儀表板視圖模型聚合深模組 (dashboard_service.py)
================================================
職責：依循 Matt Pocock 深模組原則設計，封裝教練主控台儀表板 (Dashboard) 
所需的學員狀態預測、排程分析、流失風險分類、蘋果總裁班摘要與短效快取。
消除原本散落於 routers/coach.py 的程序性迴圈計算，大幅收斂路由控制層。
"""

from __future__ import annotations

import copy
import os
import time
from datetime import datetime, date
from typing import Any, Callable

from apple_ceo_service import extract_session_date, summarize_apple_ceo_program
from prediction_service import predict_student_status


_DASHBOARD_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "payload": None,
}


def clear_dashboard_cache() -> None:
    """清空儀表板聚合資料快取。"""
    _DASHBOARD_CACHE["timestamp"] = 0.0
    _DASHBOARD_CACHE["payload"] = None


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
        student["features"] = features_analyzer(student.get("id", ""))
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

