from __future__ import annotations

import hashlib
import re
from typing import Any


def normalize_digital_name(value: str) -> str:
    """清理文字空白並轉為小寫，作為別名比對基準。"""
    return re.sub(r"\s+", "", value or "").lower()


def digital_student_id(name: str) -> str:
    """以學員名稱產生穩定的數位管理學員 ID。"""
    normalized = normalize_digital_name(name)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    romanized = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"digital-{romanized or digest}"


def resolve_student_by_name(name: str, students: list[dict[str, Any]]) -> dict[str, Any] | None:
    """依名稱或別名精確消歧義查找學員物件。"""
    target = normalize_digital_name(name)
    if not target:
        return None

    # 1. 優先精確比對主要姓名
    for student in students:
        if normalize_digital_name(student.get("name", "")) == target:
            return student

    # 2. 次要比對別名庫
    for student in students:
        for alias in student.get("aliases", []):
            if normalize_digital_name(alias) == target:
                return student

    return None


def get_student_by_id(sid: str, students: list[dict[str, Any]]) -> dict[str, Any] | None:
    """依 UUID 取得學員物件。"""
    return next((s for s in students if s.get("id") == sid), None)


def build_student_features(student: dict[str, Any]) -> dict[str, Any]:
    """計算學員活躍程度、標籤與進度特徵。"""
    lessons_count = student.get("lessons_count", 0)
    latest_date = student.get("latest_date", "")
    tags = list(student.get("tags", []))

    status = "活躍學員"
    if lessons_count >= 50:
        status = "資深長期學員"
    elif lessons_count <= 2:
        status = "新進體驗學員"

    return {
        "status": status,
        "lessons_count": lessons_count,
        "latest_date": latest_date,
        "tags": tags,
    }


def calculate_student_stats(students: list[dict[str, Any]]) -> dict[str, Any]:
    """計算整體學員看板之核心 KPI 指標。"""
    total = len(students)
    total_lessons = sum(s.get("lessons_count", 0) for s in students)
    avg_lessons = round(total_lessons / total, 1) if total else 0

    return {
        "total_students": total,
        "total_lessons": total_lessons,
        "avg_lessons": avg_lessons,
    }
