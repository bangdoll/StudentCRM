import os
import re
from datetime import datetime, timedelta

WEEKDAYS_ZH = ["（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（日）"]


def get_document_exceptions(student_file_path: str) -> list[str]:
    """Scan student .md file for '暫停一次' and return the associated dates."""
    exceptions = []
    if not student_file_path or not os.path.exists(student_file_path):
        return exceptions

    try:
        with open(student_file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "暫停一次" in line:
                    match = re.search(r"(\d{4}-\d{2}-\d{2})", line)
                    if match:
                        exceptions.append(match.group(1))
    except Exception as e:
        print(f"DEBUG: Error scanning {student_file_path} for exceptions: {e}")

    return list(set(exceptions))


def get_next_occurrence(schedule_str: str, exceptions: list[str] = None, now: datetime = None) -> str | None:
    """Calculate the next occurrence of a recurring schedule, skipping exceptions.
    Format: 'weekly:weekday:time' (weekday 0=Mon, 3=Thu)
    """
    if not schedule_str or not schedule_str.startswith("weekly:"):
        return None

    if exceptions is None:
        exceptions = []

    try:
        parts = schedule_str.split(":")
        target_weekday = int(parts[1])
        target_time = datetime.strptime(parts[2] + ":" + parts[3], "%H:%M").time()

        now = now or datetime.now()
        current_dt = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)

        # Calculate base offset
        days_ahead = target_weekday - current_dt.weekday()
        if days_ahead < 0 or (days_ahead == 0 and current_dt < now):
            days_ahead += 7

        next_dt = current_dt + timedelta(days=days_ahead)

        # Keep jumping 7 days if the date is in exceptions
        while next_dt.strftime("%Y-%m-%d") in exceptions:
            next_dt += timedelta(days=7)

        # Format: 2026-03-24（二）10:00
        weekday_str = WEEKDAYS_ZH[next_dt.weekday()]
        return next_dt.strftime(f"%Y-%m-%d{weekday_str}%H:%M")

    except Exception as e:
        print(f"DEBUG: Error parsing schedule_str '{schedule_str}': {e}")
        return None


def get_next_lesson_sort_key(s: dict, now: datetime = None) -> tuple:
    """Sort key for students based on their upcoming next lesson."""
    nl = s.get("next_lesson")
    if not nl or nl in ("待定", "安排中"):
        return (2, datetime(9999, 12, 31))

    try:
        ds = nl.split("（")[0].strip()
        ts = "00:00"
        if "）" in nl:
            time_part = nl.split("）")[-1].strip()
            if re.match(r"^\d{2}:\d{2}$", time_part):
                ts = time_part

        dt = datetime.strptime(f"{ds} {ts}", "%Y-%m-%d %H:%M")
        now = now or datetime.now()

        if dt >= now:
            return (0, dt)
        return (1, dt)
    except Exception:
        return (2, datetime(9999, 12, 31))
