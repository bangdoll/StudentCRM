from __future__ import annotations

import json
from pathlib import Path


def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "OpenClaw").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


ROOT = find_repo_root()
APPLE_FILE_OPENCLAW = ROOT / "OpenClaw/Data/apple_ceo_class.json"
APPLE_FILE_APP = ROOT / "07.Projects/StudentCRM/data/apple_ceo_class.json"


def round_item(label: str, sessions: list[str], payment_status: str = "進度") -> dict:
    padded = (sessions + [""] * 8)[:8]
    return {
        "label": label,
        "payment_status": payment_status,
        "sessions": padded,
    }


def record(date: str, venue: str, count: int, attendees: list[str] | None = None, note: str = "") -> dict:
    return {
        "id": f"apple-ceo-attendance-{date}",
        "date": date,
        "venue": venue,
        "attendee_count": count,
        "attendees": attendees or [],
        "note": note,
    }


def ledger(date: str, tx_type: str, amount: int, balance: int, note: str, payer: str = "", headcount: int | None = None) -> dict:
    safe_type = "income" if amount > 0 else "expense"
    return {
        "id": f"apple-ceo-ledger-{date}-{safe_type}-{abs(amount)}-{len(note)}",
        "date": date,
        "type": tx_type,
        "amount": amount,
        "payer": payer,
        "headcount": headcount,
        "note": note,
        "balance_after": balance,
    }


attendance_records = [
    record("2025-07-30", "玫瑰客廳", 5),
    record("2025-08-07", "玫瑰客廳", 2),
    record("2025-08-14", "玫瑰客廳", 5),
    record("2025-08-28", "玫瑰客廳", 4),
    record("2025-09-04", "玫瑰客廳", 3),
    record("2025-09-11", "玫瑰客廳", 4),
    record("2025-09-18", "玫瑰客廳", 2),
    record("2025-09-25", "玫瑰客廳", 7),
    record("2025-10-02", "小樹屋", 4, note="小樹屋場地費 960，另付，不計入玫瑰客廳儲值餘額"),
    record("2025-10-09", "小樹屋", 3, note="小樹屋場地費 960，另付，不計入玫瑰客廳儲值餘額"),
    record("2025-10-16", "玫瑰客廳", 2),
    record("2025-10-23", "玫瑰客廳", 4),
    record("2025-10-30", "玫瑰客廳", 2),
    record("2025-11-06", "玫瑰客廳", 3),
    record("2025-11-13", "玫瑰客廳", 2),
    record("2025-11-20", "玫瑰客廳", 3),
    record("2025-11-27", "玫瑰客廳", 4),
    record("2025-12-04", "休息", 0, note="休息一次"),
    record("2025-12-11", "玫瑰客廳", 5),
    record("2025-12-18", "玫瑰客廳", 4),
    record("2026-01-08", "玫瑰客廳", 2),
    record("2026-01-15", "玫瑰客廳", 2),
    record("2026-01-29", "玫瑰客廳", 5),
    record("2026-02-05", "玫瑰客廳", 3),
    record("2026-02-26", "玫瑰客廳", 3),
    record("2026-03-05", "玫瑰客廳", 3),
    record("2026-03-12", "玫瑰客廳", 3),
    record("2026-03-19", "玫瑰客廳", 4),
    record("2026-03-26", "玫瑰客廳", 3, ["Roger老師", "邦寧大哥", "方醫師"]),
    record("2026-04-09", "玫瑰客廳", 5, ["Roger老師", "邦寧大哥", "方醫師", "Lucia", "敏穎"]),
    record("2026-04-16", "玫瑰客廳", 3, ["Roger老師", "邦寧大哥", "王太太"]),
    record("2026-04-23", "玫瑰客廳", 2, ["Roger老師", "邦寧大哥"]),
    record("2026-04-30", "玫瑰客廳", 3, ["Roger老師", "邦寧大哥", "方醫師"]),
    record("2026-05-07", "玫瑰客廳", 4, ["Roger老師", "方醫師", "Lucia", "敏穎"]),
    record("2026-05-14", "玫瑰客廳", 3, ["Roger老師", "方醫師", "Lucia"]),
    record("2026-05-21", "玫瑰客廳", 4, ["Roger老師", "方醫師", "Lucia", "王太太"]),
    record("2026-05-28", "小樹屋", 4, ["邦寧大哥", "方醫師", "Lucia", "王太太"], note="小樹屋場地費，另付，不扣抵玫瑰客廳儲值"),
    record("2026-06-04", "玫瑰客廳", 4, ["Roger老師", "方醫師", "邦寧大哥", "王太太"]),
    record("2026-06-11", "玫瑰客廳", 1, ["Roger老師"]),
    record("2026-06-25", "小樹屋", 2, ["方醫師", "邦寧大哥"], note="小樹屋場地費，另付，不扣抵玫瑰客廳儲值"),
    record("2026-07-02", "玫瑰客廳", 3, ["Roger老師", "方醫師", "Lucia"]),
    record("2026-07-09", "玫瑰客廳", 5, ["Roger老師", "方醫師", "Lucia", "王太太", "邦寧大哥"]),
    record("2026-07-16", "玫瑰客廳", 3, ["Roger老師", "方醫師", "Lucia"]),
    record("2026-07-23", "小樹屋", 4, ["邦寧大哥", "方醫師", "Lucia", "王太太"], note="小樹屋場地費，另付，不扣抵玫瑰客廳儲值"),
    record("2026-07-30", "小樹屋", 2, ["方醫師", "王太太"], note="小樹屋場地費，另付，不扣抵玫瑰客廳儲值"),
    record("2026-08-06", "小樹屋", 2, ["方醫師", "王太太"], note="小樹屋場地費，另付，不扣抵玫瑰客廳儲值"),
    record("2026-08-13", "玫瑰客廳", 3, ["Roger老師", "邦寧大哥", "王太太"]),
    record("2026-08-20", "玫瑰客廳", 2, ["Roger老師", "Lucia"]),
    record("2026-08-27", "玫瑰客廳", 3, ["Roger老師", "Lucia", "方醫師"]),
]

venue_ledger = [
    ledger("2025-07-30", "收入", 3000, 3000, "儲值在 Roger 老師", "Roger老師"),
    ledger("2025-07-30", "支出", -750, 2250, "玫瑰客廳 150*5", headcount=5),
    ledger("2025-08-07", "支出", -300, 1950, "玫瑰客廳 150*2", headcount=2),
    ledger("2025-08-14", "支出", -750, 1200, "玫瑰客廳 150*5", headcount=5),
    ledger("2025-08-28", "支出", -600, 600, "玫瑰客廳 150*4", headcount=4),
    ledger("2025-09-04", "支出", -450, 150, "玫瑰客廳 150*3", headcount=3),
    ledger("2025-09-11", "收入", 3000, 3150, "場地費儲值", "Roger老師"),
    ledger("2025-09-11", "支出", -600, 2550, "玫瑰客廳 150*4", headcount=4),
    ledger("2025-09-18", "支出", -300, 2250, "玫瑰客廳 150*2", headcount=2),
    ledger("2025-09-25", "支出", -1050, 1200, "玫瑰客廳 150*7", headcount=7),
    ledger("2025-10-02", "另付", -960, 1200, "小樹屋場地費 960，另付，不計入玫瑰客廳餘額", headcount=4),
    ledger("2025-10-09", "另付", -960, 1200, "小樹屋場地費 960，另付，不計入玫瑰客廳餘額", headcount=3),
    ledger("2025-10-16", "支出", -300, 900, "玫瑰客廳 150*2", headcount=2),
    ledger("2025-10-23", "支出", -600, 300, "玫瑰客廳 150*4", headcount=4),
    ledger("2025-10-30", "支出", -300, 0, "玫瑰客廳 150*2", headcount=2),
    ledger("2025-11-06", "支出", -450, -450, "玫瑰客廳 150*3", headcount=3),
    ledger("2025-11-13", "收入", 3000, 2550, "11/13 場地費儲值", "Roger老師"),
    ledger("2025-11-13", "支出", -300, 2250, "玫瑰客廳 150*2", headcount=2),
    ledger("2025-11-20", "支出", -450, 1800, "玫瑰客廳 150*3", headcount=3),
    ledger("2025-11-27", "支出", -600, 1200, "玫瑰客廳 150*4", headcount=4),
    ledger("2025-12-11", "支出", -750, 450, "玫瑰客廳 150*5", headcount=5),
    ledger("2025-12-18", "支出", -600, -150, "玫瑰客廳 150*4", headcount=4),
    ledger("2026-01-08", "支出", -300, -450, "玫瑰客廳 150*2", headcount=2),
    ledger("2026-01-15", "支出", -300, -750, "玫瑰客廳 150*2", headcount=2),
    ledger("2026-01-29", "收入", 3000, 2250, "1/29 場地費儲值", "Roger老師"),
    ledger("2026-01-29", "支出", -750, 1500, "玫瑰客廳 150*5", headcount=5),
    ledger("2026-02-05", "支出", -450, 1050, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-02-26", "支出", -450, 600, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-03-05", "支出", -450, 150, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-03-12", "支出", -450, -300, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-03-19", "支出", -600, -900, "玫瑰客廳 150*4", headcount=4),
    ledger("2026-03-26", "支出", -450, -1350, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-04-09", "收入", 2000, 650, "場地費儲值", "Roger老師、邦寧大哥、方醫師"),
    ledger("2026-04-09", "支出", -750, -100, "玫瑰客廳 150*5", headcount=5),
    ledger("2026-04-16", "支出", -450, -550, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-04-23", "支出", -300, -850, "玫瑰客廳 150*2", headcount=2),
    ledger("2026-04-30", "支出", -450, -1300, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-05-07", "支出", -600, -1900, "玫瑰客廳 150*4", headcount=4),
    ledger("2026-05-14", "支出", -450, -2350, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-05-21", "支出", -600, -2950, "玫瑰客廳 150*4", headcount=4),
    ledger("2026-05-28", "另付", 0, -2950, "小樹屋場地費，另付，不扣抵玫瑰客廳儲值", headcount=4),
    ledger("2026-06-04", "支出", -600, -3550, "玫瑰客廳 150*4", headcount=4),
    ledger("2026-06-11", "支出", -150, -3700, "玫瑰客廳 150*1", headcount=1),
    ledger("2026-06-11", "收入", 8000, 4300, "20260611 場地費儲值 $8000 (-3550-150+8000=4300)", "Roger老師"),
    ledger("2026-06-25", "另付", 0, 4300, "小樹屋場地費，另付，不扣抵玫瑰客廳儲值", headcount=2),
    ledger("2026-07-02", "支出", -450, 3850, "玫瑰客廳 150*3", headcount=3),
    ledger("2026-07-09", "支出", -750, 3550, "玫瑰客廳 150*5 (依筆記標註結餘 3550)", headcount=5),
    ledger("2026-07-16", "支出", -450, 3100, "玫瑰客廳 150*3 (3550-450=3100)", headcount=3),
    ledger("2026-07-23", "另付", 0, 3100, "小樹屋場地費，另付，不扣抵玫瑰客廳儲值", headcount=4),
    ledger("2026-07-30", "另付", 0, 3100, "小樹屋場地費，另付，不扣抵玫瑰客廳儲值", headcount=2),
    ledger("2026-08-06", "另付", 0, 3100, "小樹屋場地費，另付，不扣抵玫瑰客廳儲值", headcount=2),
    ledger("2026-08-13", "支出", -450, 2650, "玫瑰客廳 150*3 (3100-450=2650)", headcount=3),
    ledger("2026-08-20", "支出", -300, 2350, "玫瑰客廳 150*2 (2650-300=2350)", headcount=2),
    ledger("2026-08-27", "支出", -450, 1900, "玫瑰客廳 150*3 (2350-450=1900)", headcount=3),
]

student_rounds = [
    {
        "student_name": "方柏敦",
        "aliases": ["方醫師"],
        "rounds": [
            round_item("2026 夏季梯次 (已結訓)", ["2026-06-25", "2026-07-02", "2026-07-09", "2026-07-16", "2026-07-23", "2026-07-30", "2026-08-06", "2026-08-27"], "6/25 收到方醫師學費 $8000 (滿 8 堂結訓)"),
            round_item("2026 春季梯次 (已結訓)", ["2026-03-26", "2026-04-09", "2026-04-30", "2026-05-07", "2026-05-14", "2026-05-21", "2026-05-28", "2026-06-04"], "滿 8 堂結訓"),
            round_item("2025 冬季梯次", ["2025-11-27", "2025-12-11", "2025-12-18", "2026-01-29"]),
            round_item("2025 秋季梯次", ["2025-09-25", "2025-10-02", "2025-10-09", "2025-10-23", "2025-10-30", "2025-11-06", "2025-11-13", "2025-11-20"]),
            round_item("2025 夏季梯次", ["2025-06-12", "2025-06-19", "2025-07-03", "2025-07-10", "2025-07-24", "2025-07-31", "2025-08-07", "2025-07-14"]),
        ],
    },
    {
        "student_name": "劉邦寧",
        "aliases": ["邦寧大哥"],
        "rounds": [
            round_item("最新梯次 (進行中)", ["2026-07-09", "2026-07-23", "2026-08-13"], "8/13 收到邦寧大哥學費 $8000"),
            round_item("2026 春夏梯次 (已結訓)", ["2026-03-27", "2026-04-09", "2026-04-16", "2026-04-23", "2026-04-30", "2026-05-28", "2026-06-04", "2026-06-25"], "4/12 收到學費 $8000 (滿 8 堂結訓)"),
            round_item("2025 冬季梯次", ["2025-11-27", "2025-12-11", "2025-12-18", "2026-01-29", "2026-02-05", "2026-02-26", "2026-03-12", "2026-03-19"]),
            round_item("2025 夏秋梯次", ["2025-07-31", "2025-07-14", "2025-08-28", "2025-09-25", "2025-10-02", "2025-10-09", "2025-10-23", "2025-11-20"]),
        ],
    },
    {
        "student_name": "Roger老師",
        "aliases": ["Roger"],
        "rounds": [
            round_item("最新梯次 (進行中)", ["2026-06-11", "2026-07-02", "2026-07-09", "2026-07-16", "2026-08-13", "2026-08-20", "2026-08-27"], "6/11 收到學費 $8000 (進行至第 7 堂，即將結訓)"),
            round_item("2026 春季梯次 (已結訓)", ["2026-04-09", "2026-04-16", "2026-04-23", "2026-04-30", "2026-05-07", "2026-05-14", "2026-05-21", "2026-06-04"], "4/9 收到學費 $8000 (滿 8 堂結訓)"),
            round_item("2026 冬春梯次", ["2026-01-15", "2026-01-29", "2026-02-05", "2026-02-26", "2026-03-05", "2026-03-12", "2026-03-19", "2026-03-26"]),
            round_item("2025 冬季梯次", ["2025-10-30", "2025-11-06", "2025-11-13", "2025-11-20", "2025-11-27", "2025-12-11", "2025-12-18", "2026-01-08"]),
            round_item("2025 秋季梯次", ["2025-07-24", "2025-07-31", "2025-08-28", "2025-09-11", "2025-09-18", "2025-09-25", "2025-10-16", "2025-10-23"]),
        ],
    },
    {
        "student_name": "Lucia",
        "aliases": ["Lucia 徐露華"],
        "rounds": [
            round_item("最新梯次 (進行中)", ["2026-05-28", "2026-07-02", "2026-07-09", "2026-07-16", "2026-07-23", "2026-08-20", "2026-08-27"], "5/23 收到學費 $8000 (進行至第 7 堂，即將結訓)"),
            round_item("2026 春季梯次 (已結訓)", ["2026-01-29", "2026-03-05", "2026-03-12", "2026-03-19", "2026-04-09", "2026-05-07", "2026-05-14", "2026-05-21"], "滿 8 堂結訓"),
            round_item("2025 冬季梯次", ["2025-10-09", "2025-10-16", "2025-10-23", "2025-11-27", "2025-12-11", "2025-12-18", "2026-01-08", "2026-01-15"]),
        ],
    },
    {
        "student_name": "王太太",
        "rounds": [
            round_item("最新梯次 (進行中)", ["2026-06-04", "2026-07-09", "2026-07-23", "2026-07-30", "2026-08-06", "2026-08-13"], "7/9 收到學費 $8000 (進行至第 6 堂)"),
            round_item("2026 春季梯次 (已結訓)", ["2025-09-11", "2026-01-29", "2026-02-05", "2026-02-26", "2026-03-05", "2026-04-16", "2026-05-21", "2026-05-28"], "滿 8 堂結訓"),
            round_item("2025 夏季梯次", ["2025-05-22", "2025-05-29", "2025-07-03", "2025-07-10", "2025-07-24", "2025-07-31", "2025-08-28", "2025-09-04"]),
            round_item("2024 冬季梯次", ["2024-10-24", "2024-11-07", "2024-11-14", "2024-11-21", "2024-11-28", "2024-12-05", "2024-12-12", "2025-01-02"]),
            round_item("2025 春季梯次", ["2025-01-09", "2025-01-16", "2025-01-23", "2025-02-06", "2025-02-13", "2025-04-24", "2025-05-08", "2025-05-15"]),
        ],
    },
    {
        "student_name": "方敏穎",
        "aliases": ["敏穎"],
        "rounds": [
            round_item("最新梯次 (進行中)", ["2026-03-19", "2026-04-09", "2026-05-07"]),
            round_item("2025 梯次", ["2025-03-21", "2025-04-18", "2025-05-09", "2025-06-13", "2025-08-01", "2025-09-26"]),
        ],
    },
    {
        "student_name": "Andy哥",
        "rounds": [
            round_item("歷史梯次", ["2025-06-27", "2025-08-08", "2025-08-22", "2025-10-17", "2025-11-14", "2026-01-09", "2026-01-23"]),
        ],
    },
    {
        "student_name": "林永青",
        "rounds": [
            round_item("歷史梯次", ["2025-07-24", "2025-07-31", "2025-07-14", "2025-09-11", "2025-09-18", "2025-09-25", "2025-10-02"]),
        ],
    },
    {
        "student_name": "陳總",
        "rounds": [
            round_item("歷史梯次", ["2025-07-14", "2025-09-04", "2025-09-11", "2025-09-25", "2025-12-11"], "原來的一對一 $12000 轉為總裁班"),
        ],
    },
]

tuition_records = [
    {"date": "2026-04-09", "student_name": "Roger老師", "amount": 8000, "note": "收到 Roger 學費 $8000"},
    {"date": "2026-04-12", "student_name": "劉邦寧", "amount": 8000, "note": "收到邦寧大哥學費 $8000"},
    {"date": "2026-05-23", "student_name": "Lucia", "amount": 8000, "note": "收到 Lucia 學費 $8000"},
    {"date": "2026-06-11", "student_name": "Roger老師", "amount": 8000, "note": "收到 Roger 學費 $8000"},
    {"date": "2026-06-25", "student_name": "方柏敦", "amount": 8000, "note": "收到方醫師學費 $8000"},
    {"date": "2026-07-09", "student_name": "王太太", "amount": 8000, "note": "收到王太太學費 $8000"},
    {"date": "2026-08-13", "student_name": "劉邦寧", "amount": 8000, "note": "收到邦寧大哥學費 $8000"},
]


def duplicate_report(payload: dict) -> dict:
    duplicate_attendance_dates = []
    seen_dates = set()
    for item in payload["attendance_records"]:
        date = item["date"]
        if date in seen_dates:
            duplicate_attendance_dates.append(date)
        seen_dates.add(date)

    duplicate_ledger_ids = []
    seen_ids = set()
    for item in payload["venue_ledger"]:
        item_id = item["id"]
        if item_id in seen_ids:
            duplicate_ledger_ids.append(item_id)
        seen_ids.add(item_id)

    duplicate_sessions_by_student = {}
    for group in payload["student_rounds"]:
        dates = []
        for item in group["rounds"]:
            dates.extend([session for session in item["sessions"] if session])
        duplicates = sorted({date for date in dates if dates.count(date) > 1})
        if duplicates:
            duplicate_sessions_by_student[group["student_name"]] = duplicates

    return {
        "duplicate_attendance_dates": duplicate_attendance_dates,
        "duplicate_ledger_ids": duplicate_ledger_ids,
        "duplicate_sessions_by_student": duplicate_sessions_by_student,
    }


def main() -> None:
    payload = {
        "program": {
            "id": "apple-ceo",
            "name": "蘋果總裁班",
            "url": "https://rd.coach/apple-ceo/",
            "description": "小班制教學，4-10 人，一輪共 8 堂課，一次 3 小時。",
            "schedule": "每週四 14:00-17:00",
            "capacity": "4-10",
            "round_size": 8,
            "price_per_student": 8000,
            "validity_rule": "從第一堂課起算 4 個月內有效",
            "leave_rule": "如需請假，請提前告知蔡教練",
            "join_rule": "可插班上課",
            "session_duration_hours": 3,
        },
        "venue": {
            "name": "玫瑰客廳",
            "address": "台北市民族東路767號2樓之1",
            "parking": "開車停松山機場第一停車場，步行 3-5 分鐘。",
            "metro": "文湖線松山機場站 2 號出口，步行 3-5 分鐘。",
            "cost_per_person": 150,
        },
        "active_participants": ["劉邦寧", "方柏敦", "Roger老師", "Lucia", "王太太", "方敏穎"],
        "attendance_records": attendance_records,
        "venue_ledger": venue_ledger,
        "student_rounds": student_rounds,
        "tuition_records": tuition_records,
        "legacy_note": "2026-09-02 依教練提供完整上課與學費紀錄更新至 2026-08-27。場地費結餘 $1900；學費完整登記 7 筆各 $8000。",
    }
    payload["duplicate_report"] = duplicate_report(payload)

    for target_path in [APPLE_FILE_OPENCLAW, APPLE_FILE_APP]:
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"✅ 已更新：{target_path}")

    print("場地費最新餘額：", venue_ledger[-1]["balance_after"])
    print("出席紀錄總數：", len(attendance_records))
    print("學費入帳總筆數：", len(tuition_records))


if __name__ == "__main__":
    main()
