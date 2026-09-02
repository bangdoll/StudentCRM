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


def generate_student_renewal_reminder(student: dict[str, Any]) -> str:
    """為個別學員產生客製化 LINE 續課席位保留提醒文案。"""
    name = student.get("name", "同學")
    total_lessons = student.get("lessons_count", 0)
    cycle_lesson = student.get("current_cycle_lesson")
    if cycle_lesson is None:
        cycle_lesson = (total_lessons % 8) or (8 if total_lessons > 0 else 0)

    cycle_num = ((total_lessons - 1) // 8) + 1 if total_lessons > 0 else 1

    if cycle_lesson == 8 and total_lessons > 0:
        headline = f"已圓滿完成第 {cycle_num} 輪（滿 8 堂，累計達 {total_lessons} 堂課）！🎉"
        subtext = f"感謝您一路以來的實作投入與專注學習！為確保您每週專屬輔導時段不受影響，教練已優先為您保留下期（第 {cycle_num + 1} 期・8 堂）上課名額。"
    elif cycle_lesson == 7:
        headline = f"即將完成本輪第 7/8 堂課（累計已達 {total_lessons} 堂）！🎉"
        subtext = f"下週即將迎來本輪最後一堂總結課。為確保下階段專屬時段無縫延續，教練已優先為您預留續班名額。"
    else:
        headline = f"目前已完成 {total_lessons} 堂課（本期第 {cycle_lesson}/8 堂）！"
        subtext = "感謝您的持續學習與實踐，為確保專屬時段不中斷，教練已為您預留後續名額。"

    return (
        f"【數位管理實戰・專屬席位保留通知】\n\n"
        f"親愛的 {name} 您好！\n\n"
        f"您在數位管理一對一實戰教學中，{headline}\n\n"
        f"{subtext}\n\n"
        f"若您想延續目前的進度或安排下梯次主題，歡迎隨時與教練確認續約時間與時段安排！😊\n"
        f"—— 蔡教練 敬上"
    )


def get_global_renewal_radar(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """篩選出全域 7/8（即將滿堂）與 8/8（滿 8 堂結訓）之個別學員名單，依最近上課日期與堂數排序。"""
    radar = []
    for s in students:
        name = s.get("name", "")
        if "總裁班" in name:
            continue
        cnt = s.get("lessons_count", 0)
        if cnt <= 0:
            continue

        # 優先以 Google 日曆標題精準解析之當期堂數為主，未登錄時 fallback 至 cnt % 8
        cycle_lesson = s.get("current_cycle_lesson")
        if cycle_lesson is None:
            cycle_lesson = (cnt % 8) or (8 if cnt > 0 else 0)

        if cycle_lesson == 8:
            status_code = "completed"
            status_text = "已滿 8/8 堂 (圓滿結訓)"
            badge_class = "badge-full"
            action_text = "📋 複製續班提醒"
        elif cycle_lesson == 7:
            status_code = "warning"
            status_text = "即將滿 7/8 堂 (請提前預留)"
            badge_class = "badge-short"
            action_text = "📋 複製預約提醒"
        else:
            continue

        reminder_msg = generate_student_renewal_reminder(s)
        latest_date = s.get("latest_date") or s.get("last_lesson_date") or ""

        radar.append({
            "id": s.get("id"),
            "name": name,
            "lessons_count": cnt,
            "current_cycle_lesson": cycle_lesson,
            "progress_ratio": f"{cycle_lesson}/8",
            "status_code": status_code,
            "status_text": status_text,
            "badge_class": badge_class,
            "action_text": action_text,
            "latest_date": latest_date,
            "first_lesson_date": s.get("first_lesson_date") or "未記錄",
            "next_lesson": s.get("next_lesson") or "安排中",
            "reminder_message": reminder_msg,
        })

    def radar_sort_key(item):
        ld = item.get("latest_date") or "0000-00-00"
        is_completed = 0 if item["status_code"] == "completed" else 1
        return (ld < "2026-01-01", is_completed, -item["lessons_count"])

    return sorted(radar, key=radar_sort_key)
