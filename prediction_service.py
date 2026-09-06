import os
import re
import time
from datetime import datetime
from teaching_sync import parse_date_from_title

_FEATURES_CACHE: dict[str, tuple[float, dict]] = {}
_FEATURES_CACHE_TTL = 300  # 5 minutes in-memory cache


def clear_features_cache():
    """Clear in-memory features cache."""
    _FEATURES_CACHE.clear()


def get_student_lesson_paths(student: dict, base_dir: str, student_notes: list = None) -> list[str]:
    """Get sorted lesson cache and teaching paths for a student."""
    if not student:
        return []

    paths = []
    file_path = os.path.join(base_dir, (student.get("file") or "").lstrip("/"))
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            paths.extend(re.findall(r"/open_file\?path=([^\s\)\'\">\n]+\.md)", content))
        except Exception:
            pass

    for n in student_notes or []:
        if n.get("path"):
            paths.append(n["path"])

    def date_key(p):
        fname = os.path.basename(p)
        date = parse_date_from_title(fname)
        return date.replace("-", "") if date else fname

    return sorted(set(paths), key=date_key)


def analyze_student_features(
    student: dict,
    base_dir: str,
    student_notes: list = None,
    use_cache: bool = True,
    now: datetime = None,
) -> dict:
    """Extract features from student's historical data for AI prediction."""
    if not student:
        return {
            "days_since_last_lesson": -1,
            "average_word_count": 0,
            "lessons_reviewed": 0,
        }

    student_id = student.get("id", "")
    now_ts = time.time()
    if use_cache and student_id in _FEATURES_CACHE:
        cached_ts, cached_features = _FEATURES_CACHE[student_id]
        if now_ts - cached_ts < _FEATURES_CACHE_TTL:
            return dict(cached_features)

    now_dt = now or datetime.now()
    paths = get_student_lesson_paths(student, base_dir, student_notes)
    features = {
        "days_since_last_lesson": -1,
        "average_word_count": 0,
        "lessons_reviewed": 0,
        "status": student.get("status", "active"),
    }

    if paths:
        # Parse the latest lesson date
        latest_path = paths[-1]
        date_str = parse_date_from_title(os.path.basename(latest_path))
        if date_str:
            try:
                latest_date = datetime.strptime(date_str, "%Y-%m-%d")
                features["days_since_last_lesson"] = max(0, (now_dt - latest_date).days)
            except ValueError:
                pass
        else:
            m = re.search(r"Lesson_(\d{4})(\d{2})(\d{2})_", latest_path)
            if m:
                y, mo, d = map(int, m.groups())
                latest_date = datetime(y, mo, d)
                features["days_since_last_lesson"] = max(0, (now_dt - latest_date).days)

        # Parse average word count from the last 3 lessons
        recent_paths = paths[-3:]
        total_words = 0
        valid_lessons = 0
        for p in recent_paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        total_words += len(content)
                        valid_lessons += 1
                except Exception:
                    pass

        if valid_lessons > 0:
            features["average_word_count"] = total_words // valid_lessons
            features["lessons_reviewed"] = valid_lessons

    # Align with student metadata (SSOT of latest attendance date)
    latest_str = student.get("latest_date") or student.get("last_lesson_date")
    if latest_str and latest_str != "未記錄":
        try:
            ld = datetime.strptime(latest_str, "%Y-%m-%d")
            meta_days = max(0, (now_dt - ld).days)
            if features["days_since_last_lesson"] == -1 or meta_days < features["days_since_last_lesson"]:
                features["days_since_last_lesson"] = meta_days
        except ValueError:
            pass

    # Fallback word count from notes
    if features["average_word_count"] == 0 and student_notes:
        total_words = 0
        valid_notes = 0
        for n in student_notes[:3]:
            c = n.get("content") or ""
            if c:
                total_words += len(c)
                valid_notes += 1
        if valid_notes > 0:
            features["average_word_count"] = total_words // valid_notes
            features["lessons_reviewed"] = valid_notes

    if student_id:
        _FEATURES_CACHE[student_id] = (now_ts, dict(features))
    return features


def predict_student_status(features: dict, next_lesson: str = None) -> dict:
    """根據最後上課日期與筆記平均字數，回傳學員 AI 學習狀態燈號。"""
    raw_status = features.get("status")
    if raw_status == "memorial":
        return {
            "badge": "🎗️",
            "status": "歷史典藏",
            "class": "badge-placeholder",
            "reason": "學員教學資產永久典藏，不再進行日常營運追蹤。",
        }
    if raw_status == "paused":
        return {
            "badge": "⏸️",
            "status": "休學暫停",
            "class": "badge-placeholder",
            "reason": "學員目前為休學或暫停狀態，暫緩關懷追蹤。",
        }

    days = features.get("days_since_last_lesson", -1)
    word_count = features.get("average_word_count", 0)

    if days == -1:
        return {
            "badge": "⚪",
            "status": "無預測資料",
            "class": "badge-placeholder",
            "reason": "系統中尚未找到有效的上課排程或筆記紀錄。",
        }

    if days <= 14:
        return {
            "badge": "🟢",
            "status": "穩定留存",
            "class": "badge-full",
            "reason": f"距離上次上課 {days} 天，仍在穩定互動區間。",
        }
    else:
        if word_count < 200:
            return {
                "badge": "🔴",
                "status": "高流失風險",
                "class": "badge-missing",
                "reason": f"已超過兩週未上課 ({days} 天)，且近期筆記平均字數偏低，需優先關心。",
            }
        else:
            return {
                "badge": "🧊",
                "status": "冰凍期 (需關心)",
                "class": "badge-short",
                "reason": f"已超過兩週未上課 ({days} 天)，但近期筆記內容仍扎實，建議主動回訪。",
            }
