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


def resolve_student_by_name(name: Any, students: Any) -> dict[str, Any] | None:
    """依名稱或別名於學員列表中尋找匹配項目，支援 (name, students) 或 (students, name) 傳參。"""
    if isinstance(name, list) and isinstance(students, str):
        name, students = students, name
    if not isinstance(students, list) or not isinstance(name, str):
        return None
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


def get_student_by_id(sid: Any, students: Any) -> dict[str, Any] | None:
    """依 UUID 取得學員物件，支援 (sid, students) 或 (students, sid) 傳參。"""
    if isinstance(sid, list) and isinstance(students, str):
        sid, students = students, sid
    if not isinstance(students, list):
        return None
    return next((s for s in students if isinstance(s, dict) and s.get("id") == sid), None)


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
    if student.get("renewal_reminder") is False or student.get("disable_renewal_reminder") is True:
        return ""
    if name in ("Calvin", "禮品公會", "禮品公會第二期") or any(k in name for k in ("總裁班", "禮品公會")):
        return ""

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
        if s.get("renewal_reminder") is False or s.get("disable_renewal_reminder") is True:
            continue
        if name in ("Calvin", "禮品公會", "禮品公會第二期") or any(k in name for k in ("總裁班", "禮品公會")):
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


def generate_preclass_briefing(student: dict[str, Any], teaching_notes: list[dict[str, Any]]) -> dict[str, Any]:
    """為蔡教練產生課前 3 分鐘智慧備課卡 (Pre-Class Briefing)。"""
    name = student.get("name", "學員")
    cnt = student.get("lessons_count", 0)
    cycle = student.get("current_cycle_lesson")
    if cycle is None:
        cycle = ((cnt % 8) or 8) if cnt > 0 else 1

    # 1. 技能庫詞典
    SKILL_KEYWORDS = [
        ("Heptabase 白板與雙向連結", ["heptabase", "白板", "雙向連結", "卡片", "card"]),
        ("Apple 跨裝置生態與捷徑", ["捷徑", "shortcut", "備忘錄", "提醒事項", "日曆", "螢幕鏡像", "icloud"]),
        ("AI 提示詞與知識分身", ["ai", "prompt", "chatgpt", "claude", "gemini", "提示詞", "分身", "逐字稿"]),
        ("數位檔案系統與 GTD 管理", ["檔案", "資料夾", "finder", "gtd", "收件匣", "標籤", "檔名"]),
        ("語音筆記與個人輸入流", ["語音", "錄音", "輸入法", "whisper", "逐字", "聽寫"]),
        ("iPad 晨間覆盤與手寫筆記", ["ipad", "pencil", "晨間", "覆盤", "日記", "手寫"]),
    ]

    # 2. 卡點詞典
    CHALLENGE_KEYWORDS = [
        "忘記", "卡住", "不熟練", "待練習", "尚未建立習慣", "找不到", "格式混亂",
        "同步問題", "密碼", "未整理", "時間不夠", "操作生疏", "容易中斷"
    ]

    recent_notes = teaching_notes[:5] if teaching_notes else []
    aggregated_text = ""
    for n in recent_notes:
        preview = n.get("preview") or ""
        title = n.get("title") or ""
        desc = n.get("description") or ""
        aggregated_text += f" {title} {preview} {desc}".lower()

    # 識別已掌握技能
    mastered_skills = []
    for skill_name, triggers in SKILL_KEYWORDS:
        if any(trig in aggregated_text for trig in triggers):
            mastered_skills.append(skill_name)
    if not mastered_skills:
        mastered_skills = ["數位核心工作環境配置", "個人數位資產盤點"]

    # 識別近期卡點
    recent_challenges = []
    for ch in CHALLENGE_KEYWORDS:
        if ch in aggregated_text:
            recent_challenges.append(f"上次課堂反映「{ch}」相關操作，本週需跟進確認")
            if len(recent_challenges) >= 2:
                break
    if not recent_challenges:
        recent_challenges = ["日常操作節奏穩定，引導養成每日使用閉環"]

    # 依週期推薦今日切入目標
    if cycle in (1, 2):
        stage_name = "🌱 第一階段：核心環境與工具配置"
        suggested_goal = "鞏固開機工作流桌面佈局，驗收高頻肌肉記憶快捷鍵，確保各裝置同步順暢。"
    elif cycle in (3, 4):
        stage_name = "🌿 第二階段：數位大腦與知識庫搭建"
        suggested_goal = "實戰 Heptabase 卡片與白板關聯，引導學員建立專屬晨間工作覆盤白板。"
    elif cycle in (5, 6):
        stage_name = "⚡ 第三階段：個人 AI 工作流與自動化"
        suggested_goal = "導入專屬 AI 提示詞模版與語音快速輸入流，帶學員完成 1 項工作場景實戰輸出。"
    else:
        stage_name = "🏆 第四階段：知識分身與系統化總結"
        suggested_goal = "盤點本輪 8 堂核心修煉產出，建立技能樹里程碑，並梳理下一輪進階探索藍圖。"

    briefing_text = (
        f"【蔡教練課前 3 分鐘備課備忘】\n"
        f"學員：{name}（累計 {cnt} 堂 / 本輪第 {cycle}/8 堂）\n"
        f"當前階段：{stage_name}\n"
        f"🎯 已掌握重點：{', '.join(mastered_skills)}\n"
        f"⚠️ 近期觀察與卡點：{'；'.join(recent_challenges)}\n"
        f"💡 今日建議核心目標：{suggested_goal}"
    )

    return {
        "student_name": name,
        "lessons_count": cnt,
        "current_cycle_lesson": cycle,
        "stage_name": stage_name,
        "mastered_skills": mastered_skills,
        "recent_challenges": recent_challenges,
        "suggested_goal": suggested_goal,
        "briefing_text": briefing_text,
        "recent_note_count": len(recent_notes),
    }
