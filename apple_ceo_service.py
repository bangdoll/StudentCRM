from __future__ import annotations

import calendar
import glob
import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5


APPLE_CEO_ACCESS_TOKEN = "adf9958b-a23d-4e9b-a4a2-156b5329b0ed"


def extract_apple_note_id(note: dict[str, Any]) -> str:
    """取得課堂筆記的穩定 ASCII 識別碼，避免將中文檔名暴露在網址中。"""
    explicit_id = str(note.get("id") or "").strip()
    try:
        return str(UUID(explicit_id))
    except (ValueError, AttributeError):
        pass

    content = str(note.get("content") or "")
    frontmatter_match = re.search(
        r"(?m)^id:\s*[\"']?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})[\"']?\s*$",
        content,
    )
    if frontmatter_match:
        return str(UUID(frontmatter_match.group(1)))

    identity_source = (
        note.get("path")
        or note.get("filename")
        or note.get("full_title")
        or note.get("title")
        or "apple-ceo-note"
    )
    return str(uuid5(NAMESPACE_URL, f"studentcrm:apple-ceo-note:{identity_source}"))


def normalize_apple_ceo_notes(notes: list[dict] | None) -> list[dict]:
    """補齊總裁班筆記的 ASCII URL key；不改寫原始資料或中文顯示名稱。"""
    normalized: list[dict] = []
    for note in notes or []:
        if not isinstance(note, dict):
            continue
        item = dict(note)
        note_id = extract_apple_note_id(item)
        item["id"] = note_id
        item["url_key"] = note_id
        normalized.append(item)
    return normalized


def add_months(base_date: date, months: int) -> date:
    """以自然月增加月份，自動處理月底天數溢位（如 1/31 + 1個月 -> 2/28 或 2/29）。"""
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def extract_session_date(value: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
    return match.group(0) if match else ""


def normalize_attendee_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _normalize_attendees(attendees: list[str]) -> tuple[list[str], list[str]]:
    """正規化並去除同一堂課重複輸入的學員姓名。"""
    normalized: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for raw_name in attendees or []:
        name = str(raw_name or "").strip()
        if not name:
            continue
        key = normalize_attendee_name(name)
        if key in seen:
            duplicates.append(name)
            continue
        seen.add(key)
        normalized.append(name)
    return normalized, duplicates


def attendance_preview_fingerprint(
    program_data: dict,
    date: str,
    venue: str,
    attendees: list[str],
    note: str = "",
) -> str:
    """產生與目前資料狀態綁定的預覽指紋，防止確認時套用過期差異。"""
    normalized_attendees, _ = _normalize_attendees(attendees)
    state = {
        "attendance_records": program_data.get("attendance_records", []),
        "venue_ledger": program_data.get("venue_ledger", []),
        "student_rounds": program_data.get("student_rounds", []),
        "request": {
            "date": date,
            "venue": venue,
            "attendees": normalized_attendees,
            "note": note,
        },
    }
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


CANONICAL_APPLE_STUDENT_ORDER: list[str] = [
    "方博敦",
    "劉邦寧",
    "Roger老師",
    "Lucia",
    "王太太",
    "方敏穎",
    "林永青",
    "陳總",
    "Andy哥",
]


def sort_apple_student_rounds(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """依據教練指示強制排序：在學在前面（方博敦、劉邦寧、Roger老師、Lucia、王太太、方敏穎），已過期在下面（林永青、陳總、Andy哥在最底）。"""
    def _key(item: dict[str, Any]) -> int:
        name = item.get("student_name", "")
        if name in CANONICAL_APPLE_STUDENT_ORDER:
            return CANONICAL_APPLE_STUDENT_ORDER.index(name)
        return 999

    return sorted(rounds, key=_key)


def clean_note_preview(content: str, limit: int = 150) -> str:
    """清理 Frontmatter 與開頭標題，萃取前 limit 個字作為精選摘要。"""
    text = re.sub(r"^---[\s\S]*?---\s*", "", content)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = []
    for line in lines:
        if line.startswith("#") or re.match(r"^\*?\*?20\d{2}", line):
            continue
        cleaned.append(line)
        if len(" ".join(cleaned)) >= limit:
            break
    preview = " ".join(cleaned)
    preview = re.sub(r"[*_#`]", "", preview)
    return re.sub(r"\s+", " ", preview).strip()[:limit]


def load_apple_ceo_teaching_notes(
    teaching_dir: str | None = None,
    fallback_notes: list[dict] | None = None,
) -> list[dict]:
    """讀取本地 01.Docs/teaching 中所有「蘋果總裁班」的教學紀錄檔案，若無則使用 fallback_notes。"""
    if not teaching_dir or not os.path.exists(teaching_dir):
        return fallback_notes or []

    patterns = ["*蘋果總裁*.md", "*Apple_CEO*.md", "*Apple CEO*.md"]
    files: set[str] = set()
    for p in patterns:
        files.update(glob.glob(os.path.join(teaching_dir, p)))

    notes: list[dict] = []
    for file_path in files:
        stem = Path(file_path).stem
        if "我的工作是數位教練" in stem or "eDM" in stem or stem.startswith("Pre_Class_Card"):
            continue
        
        # 解析日期
        date_match = re.search(r"(20\d{2})[-_ ./年]?(\d{2})[-_ ./月]?(\d{2})", stem)
        date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else "無日期"

        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        preview = clean_note_preview(content)
        display_title = re.sub(r"^(20\d{2})[-_ ./年]?(\d{2})[-_ ./月]?(\d{2})[_\s-]*", "", stem).strip()
        if not display_title:
            display_title = stem

        notes.append({
            "date": date_str,
            "title": display_title,
            "full_title": stem,
            "filename": os.path.basename(file_path),
            "path": f"/01.Docs/teaching/{os.path.basename(file_path)}",
            "preview": preview or "點擊查看課堂筆記全文",
            "word_count": len(content),
            "content": content,
        })

    notes.sort(key=lambda x: x["date"], reverse=True)
    return notes if notes else (fallback_notes or [])


def generate_renewal_reminder_message(student_name: str, round_info: dict) -> str:
    """生成繁體中文續班提醒預告訊息（適合 LINE / 簡訊一鍵複製）。"""
    attended = round_info.get("attended_count", 0)
    expiry = round_info.get("expiry_date", "")
    days = round_info.get("days_until_expiry")
    expiry_desc = f"，四個月效期至 {expiry}" if expiry else ""
    days_desc = f"（尚餘 {days} 天）" if days is not None and days >= 0 else ""

    if attended >= 8:
        return (
            f"【蘋果總裁班・續班提醒】\n"
            f"親愛的 {student_name} 您好！\n"
            f"恭喜您在蘋果總裁班已圓滿完成本輪 8 堂課程！🎉\n"
            f"感謝您這段期間的專注投入與扎實實作。\n"
            f"為確保後續 AI 實戰與數位管理進度持續推進，特別為您保留下期專屬席位。\n"
            f"若希望繼續續班下一輪（8 堂），歡迎隨時與教練聯繫確認最新時段安排！"
        )

    return (
        f"【蘋果總裁班・續班預告提醒】\n"
        f"親愛的 {student_name} 您好！\n"
        f"您目前在蘋果總裁班已順利上至第 {attended} 堂（每輪共 8 堂）{expiry_desc}{days_desc}。\n"
        f"因本輪進度已接近圓滿結訓，特別提前為您預告下期課程安排以保留專屬席位。\n"
        f"若希望繼續深入 AI 實戰與數位管理，歡迎隨時與教練聯繫確認下一輪時段！"
    )


def preview_apple_ceo_attendance(
    program_data: dict,
    date: str,
    venue: str,
    attendees: list[str],
    note: str = "",
) -> dict:
    """預覽單次點名對學員梯次與剩餘堂數的影響（純運算，不修改原始資料）。"""
    normalized_attendees, duplicate_attendees = _normalize_attendees(attendees)
    student_rounds = program_data.get("student_rounds", [])
    name_to_group = {
        normalize_attendee_name(group.get("student_name", "")): group
        for group in student_rounds
    }

    warnings = [f"同一堂課重複輸入，已合併：{name}" for name in duplicate_attendees]
    affected_rounds = []

    existing_records = [
        record for record in program_data.get("attendance_records", [])
        if extract_session_date(record.get("date", "")) == date
    ]
    if existing_records:
        warnings.append(f"{date} 已有上課紀錄，請改用補單或修正流程，避免重複記帳。")

    for attendee in normalized_attendees:
        normalized_attendee = normalize_attendee_name(attendee)
        group = name_to_group.get(normalized_attendee)
        if not group:
            group = next(
                (
                    item for item in student_rounds
                    if normalized_attendee in {
                        normalize_attendee_name(alias)
                        for alias in item.get("aliases", [])
                    }
                ),
                None,
            )
        if not group:
            warnings.append(f"找不到班務學員：{attendee}")
            continue

        rounds = group.get("rounds", [])
        latest_round = rounds[0] if rounds else None
        if not latest_round:
            new_sessions = [date] + [""] * 7
            affected_rounds.append({
                "student_name": group.get("student_name", attendee),
                "action": "create_round",
                "before": None,
                "after": {
                    "label": "新一輪 (預覽建立)",
                    "payment_status": "未收",
                    "sessions": new_sessions,
                    "attended_count": 1,
                    "remaining_count": 7,
                },
            })
            continue

        sessions = list(latest_round.get("sessions", []))
        if len(sessions) < 8:
            sessions.extend([""] * (8 - len(sessions)))
        sessions = sessions[:8]

        # 若已滿 8 堂且是歷史已過期梯次，提示需另建新梯次
        if latest_round.get("is_expired") and "" not in sessions:
            action = "create_next_round"
            new_sessions = [date] + [""] * 7
            affected_rounds.append({
                "student_name": group.get("student_name", attendee),
                "action": action,
                "before": {
                    "label": latest_round.get("label", ""),
                    "sessions": list(sessions),
                    "attended_count": len([s for s in sessions if s]),
                    "remaining_count": max(0, 8 - len([s for s in sessions if s])),
                },
                "after": {
                    "label": "新一輪 (預覽建立)",
                    "sessions": new_sessions,
                    "attended_count": 1,
                    "remaining_count": 7,
                },
            })
            continue

        before_sessions = list(sessions)
        action = "append_session"
        if "" in sessions:
            sessions[sessions.index("")] = date
        else:
            action = "create_next_round"
            sessions = [date] + [""] * 7

        affected_rounds.append({
            "student_name": group.get("student_name", attendee),
            "action": action,
            "before": {
                "label": latest_round.get("label", ""),
                "sessions": before_sessions,
                "attended_count": len([item for item in before_sessions if item]),
                "remaining_count": max(0, 8 - len([item for item in before_sessions if item])),
            },
            "after": {
                "label": latest_round.get("label", "") if action == "append_session" else "新一輪 (預覽建立)",
                "sessions": sessions,
                "attended_count": len([item for item in sessions if item]),
                "remaining_count": max(0, 8 - len([item for item in sessions if item])),
            },
        })

    proposed_record = {
        "id": f"apple-ceo-attendance-{date}",
        "date": date,
        "venue": venue,
        "attendee_count": len(normalized_attendees),
        "attendees": normalized_attendees,
        "note": note,
    }

    venue_config = program_data.get("venue", {}) if isinstance(program_data.get("venue", {}), dict) else {}
    primary_venue = venue_config.get("name") or "玫瑰客廳"
    cost_per_person = int(venue_config.get("cost_per_person") or 150)
    primary_venue_match = normalize_attendee_name(venue) == normalize_attendee_name(primary_venue)
    latest_ledger = (program_data.get("venue_ledger") or [{}])[-1]
    balance_before = int(latest_ledger.get("balance_after") or 0)
    venue_amount = -(cost_per_person * len(normalized_attendees)) if primary_venue_match else 0
    venue_fee = {
        "venue": venue,
        "primary_venue": primary_venue,
        "charged_to_primary_balance": primary_venue_match,
        "cost_per_person": cost_per_person,
        "headcount": len(normalized_attendees),
        "amount": venue_amount,
        "balance_before": balance_before,
        "balance_after": balance_before + venue_amount,
        "type": "支出" if primary_venue_match else "另付",
    }
    preview_token = attendance_preview_fingerprint(program_data, date, venue, normalized_attendees, note)

    return {
        "proposed_record": proposed_record,
        "affected_rounds": affected_rounds,
        "warnings": warnings,
        "venue_fee": venue_fee,
        "preview_token": preview_token,
        "summary": {
            "attendee_count": len(normalized_attendees),
            "matched_count": len(affected_rounds),
            "warning_count": len(warnings),
            "duplicate_count": len(existing_records),
        },
    }


def apply_apple_ceo_attendance(
    program_data: dict,
    date: str,
    venue: str,
    attendees: list[str],
    note: str = "",
    preview_token: str = "",
) -> dict:
    """套用單堂出席與場地費，並回傳可讀的寫入收據；不接受過期或有警告的預覽。"""
    preview = preview_apple_ceo_attendance(program_data, date, venue, attendees, note)
    if preview_token and preview_token != preview["preview_token"]:
        raise ValueError("預覽已過期，請重新產生最新差異後再確認寫入。")

    normalized_attendees = preview["proposed_record"]["attendees"]
    existing_records = [
        record for record in program_data.get("attendance_records", [])
        if extract_session_date(record.get("date", "")) == date
    ]
    if existing_records:
        existing = existing_records[0]
        same_attendance = (
            existing.get("venue") == venue
            and [normalize_attendee_name(name) for name in existing.get("attendees", [])]
            == [normalize_attendee_name(name) for name in normalized_attendees]
        )
        if same_attendance:
            return {
                "status": "idempotent",
                "message": "同一堂課已存在相同紀錄，未重複寫入。",
                "attendance_record": existing,
                "venue_ledger": next(
                    (item for item in program_data.get("venue_ledger", []) if item.get("date") == date),
                    None,
                ),
                "preview": preview,
            }
        raise ValueError(f"{date} 已有不同出席紀錄，為避免覆蓋既有資料，請走人工修正流程。")

    if preview["warnings"]:
        raise ValueError("；".join(preview["warnings"]))

    primary_venue = preview["venue_fee"]["primary_venue"]
    record_note = note or f"{date} 蘋果總裁班"
    attendance_record = {
        **preview["proposed_record"],
        "note": record_note,
    }
    program_data.setdefault("attendance_records", []).append(attendance_record)
    program_data["attendance_records"].sort(key=lambda item: item.get("date", ""))

    fee = preview["venue_fee"]
    if fee["charged_to_primary_balance"]:
        ledger_note = f"{primary_venue} {fee['cost_per_person']}*{fee['headcount']}"
        ledger_amount = fee["amount"]
    else:
        ledger_note = f"{venue}場地費另付，不扣抵{primary_venue}儲值"
        ledger_amount = 0
    if note:
        ledger_note = f"{ledger_note}；{note}"
    venue_ledger = {
        "id": f"apple-ceo-ledger-{date}-expense-{abs(ledger_amount)}",
        "date": date,
        "type": fee["type"],
        "amount": ledger_amount,
        "payer": "",
        "headcount": fee["headcount"],
        "note": ledger_note,
        "balance_after": fee["balance_after"],
    }
    program_data.setdefault("venue_ledger", []).append(venue_ledger)
    program_data["venue_ledger"].sort(key=lambda item: item.get("date", ""))

    sync_attendance_to_student_rounds(program_data)
    return {
        "status": "applied",
        "message": "出席、場地費與學員堂數已完成寫入。",
        "attendance_record": attendance_record,
        "venue_ledger": venue_ledger,
        "preview": preview,
    }


def sync_attendance_to_student_rounds(program_data: dict) -> bool:
    """自動將出席紀錄 (attendance_records) 中有到課但尚未排入學員梯次 (student_rounds) 的日期，
    自動追加至該學員的進行中輪次（若滿 8 堂則自動建立新一輪）。
    確保教練只要記錄出席與繳費，學員各自的 8 堂課進度與後續統計永遠保持最新。
    """
    student_rounds = program_data.get("student_rounds", [])
    attendance_records = program_data.get("attendance_records", [])
    if not student_rounds or not attendance_records:
        return False

    alias_to_student = {}
    for s in student_rounds:
        canon = s.get("student_name", "")
        if canon:
            alias_to_student[canon] = s
            alias_to_student[normalize_attendee_name(canon)] = s
        for a in s.get("aliases", []):
            if a:
                alias_to_student[a] = s
                alias_to_student[normalize_attendee_name(a)] = s

    all_recorded_sessions = {}
    for s in student_rounds:
        canon = s.get("student_name", "")
        recorded = set()
        for r in s.get("rounds", []):
            for sess in r.get("sessions", []):
                if sess:
                    recorded.add(extract_session_date(sess))
        all_recorded_sessions[canon] = recorded

    has_changes = False
    for att in sorted(attendance_records, key=lambda x: x.get("date", "")):
        att_date = extract_session_date(att.get("date", ""))
        if not att_date:
            continue
        for attendee in att.get("attendees", []):
            target = alias_to_student.get(attendee) or alias_to_student.get(normalize_attendee_name(attendee))
            if not target:
                continue
            canon = target.get("student_name", "")
            if att_date not in all_recorded_sessions.get(canon, set()):
                rounds = target.get("rounds", [])
                if not rounds:
                    rounds.append({
                        "label": "最新梯次 (進行中)",
                        "payment_status": "未收 (待補單)",
                        "payment_date": None,
                        "sessions": [att_date] + [""] * 7,
                    })
                    has_changes = True
                    all_recorded_sessions.setdefault(canon, set()).add(att_date)
                    continue

                latest_round = rounds[0]
                first_session = next((extract_session_date(s) for s in latest_round.get("sessions", []) if s), "")
                # 若出席日期比最新輪次的首堂上課日還要早，表示屬於歷史紀錄，不排入最新進行中梯次
                if first_session and att_date < first_session:
                    continue

                sessions = list(latest_round.get("sessions", []))
                if len(sessions) < 8:
                    sessions.extend([""] * (8 - len(sessions)))
                sessions = sessions[:8]

                if "" in sessions:
                    empty_idx = sessions.index("")
                    sessions[empty_idx] = att_date
                    latest_round["sessions"] = sessions
                    has_changes = True
                    all_recorded_sessions.setdefault(canon, set()).add(att_date)
                else:
                    # 前一輪已滿 8 堂，標記完成並開新一輪
                    if "進行中" in latest_round.get("label", ""):
                        latest_round["label"] = latest_round["label"].replace("進行中", "滿 8 堂結訓")
                    new_round = {
                        "label": "最新梯次 (進行中)",
                        "payment_status": "未收 (待補單)",
                        "payment_date": None,
                        "sessions": [att_date] + [""] * 7,
                    }
                    rounds.insert(0, new_round)
                    has_changes = True
                    all_recorded_sessions.setdefault(canon, set()).add(att_date)

    return has_changes


def summarize_apple_ceo_program(program_data: dict, today: date | None = None) -> dict:
    """計算蘋果總裁班的核心財務、出勤、效期與學員狀態指標。"""
    if today is None:
        today = date.today()

    # 自動對齊出席紀錄至學員各輪次
    sync_attendance_to_student_rounds(program_data)

    attendance_records = program_data.get("attendance_records", [])
    ledger = program_data.get("venue_ledger", [])
    student_rounds = program_data.get("student_rounds", [])
    active_participants = program_data.get("active_participants", [])
    tuition_records = program_data.get("tuition_records", [])

    total_tuition = sum(item.get("amount", 0) for item in tuition_records)
    tuition_count = len(tuition_records)

    latest_attendance = attendance_records[-1] if attendance_records else {}
    latest_ledger = ledger[-1] if ledger else {}
    latest_balance = latest_ledger.get("balance_after", 0)
    total_headcount = sum(item.get("attendee_count", 0) for item in attendance_records)
    total_sessions = len(attendance_records)
    avg_headcount = round(total_headcount / total_sessions, 1) if total_sessions else 0

    active_rounds = []
    completed_rounds = []
    followup_rounds = []
    expired_rounds = []
    expiring_soon_rounds = []
    student_statuses = []

    for student in student_rounds:
        student_active_count = 0
        student_priority_count = 0
        student_total_attended = 0
        latest_session = ""
        rounds = student.get("rounds", [])
        for round_item in rounds:
            sessions = round_item.get("sessions", [])
            actual_sessions = [s for s in sessions if s]
            normalized_sessions = [extract_session_date(s) for s in actual_sessions]
            normalized_sessions = [s for s in normalized_sessions if s]
            attended_count = len(actual_sessions)
            student_total_attended += attended_count
            round_item["attended_count"] = attended_count
            round_item["remaining_count"] = max(0, 8 - attended_count)
            round_item["progress_percent"] = int((attended_count / 8) * 100) if sessions else 0
            round_item["is_expired"] = False
            round_item["expiry_date"] = ""
            round_item["validity_base"] = ""

            # 規則：繳學費起四個月上完八堂課，超過就是過期
            payment_date_str = round_item.get("payment_date")
            base_date: date | None = None
            validity_base_desc = ""

            # 1. 優先使用 round 內記錄的 payment_date
            if payment_date_str:
                try:
                    base_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
                    validity_base_desc = f"繳學費日 {payment_date_str}"
                except ValueError:
                    base_date = None

            # 2. 若無，比對 tuition_records 該學員之繳費日（排除未收狀態與已過期舊輪次的學費）
            if not base_date and not ("未收" in round_item.get("payment_status", "")):
                student_name = student.get("student_name", "")
                aliases = student.get("aliases", [])
                matched_tuitions = [
                    t for t in tuition_records
                    if t.get("student_name") == student_name or t.get("student_name") in aliases
                ]
                if "進行中" in round_item.get("label", "") and matched_tuitions and normalized_sessions:
                    try:
                        latest_t_date = matched_tuitions[-1].get("date")
                        t_dt = datetime.strptime(latest_t_date, "%Y-%m-%d").date()
                        first_session_dt = datetime.strptime(normalized_sessions[0], "%Y-%m-%d").date()
                        # 僅當繳費日在首堂課前後 60 天內或在首堂課之後，才視為本輪繳費
                        if (first_session_dt - t_dt).days <= 60 and (t_dt <= first_session_dt or (t_dt - first_session_dt).days <= 120):
                            base_date = t_dt
                            validity_base_desc = f"繳學費日 {latest_t_date}"
                    except ValueError:
                        base_date = None

            # 3. 若仍無繳費紀錄，fallback 至首堂課日期
            if not base_date and normalized_sessions:
                base_date = datetime.strptime(normalized_sessions[0], "%Y-%m-%d").date()
                validity_base_desc = f"首堂上課日 {normalized_sessions[0]}"

            round_item["validity_base"] = validity_base_desc

            if base_date:
                expiry_date = add_months(base_date, 4)
                round_item["expiry_date"] = expiry_date.strftime("%Y-%m-%d")
                days_until_expiry = (expiry_date - today).days
                round_item["days_until_expiry"] = days_until_expiry

                # 規則核心：四個月內須上完八堂課。若未滿八堂且超過四個月，即為過期作廢
                if attended_count < 8 and today > expiry_date:
                    round_item["is_expired"] = True
                    round_item["is_expiring_soon"] = False
                elif attended_count < 8 and 0 <= days_until_expiry <= 14:
                    round_item["is_expired"] = False
                    round_item["is_expiring_soon"] = True
                else:
                    round_item["is_expired"] = False
                    round_item["is_expiring_soon"] = False

                if normalized_sessions:
                    latest_session = max([latest_session] + normalized_sessions)
            else:
                round_item["days_until_expiry"] = None
                round_item["is_expiring_soon"] = False

            # 生成 Phase B 一鍵複製通知文字
            round_item["reminder_message"] = generate_renewal_reminder_message(
                student.get("student_name", ""), round_item
            )

            if round_item["is_expired"]:
                student_priority_count += 1
                expired_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })
            elif round_item["is_expiring_soon"]:
                student_priority_count += 1
                expiring_soon_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })

            # 判斷是否為學員之最新一期（rounds[0]）
            is_latest_round = bool(rounds and round_item is rounds[0])
            is_active_label = "進行中" in round_item.get("label", "") or (is_latest_round and "待續班" in round_item.get("label", ""))

            # 若為最新一輪且已滿 8 堂（如方博敦/方醫師），亦視為活躍與待續班對象
            if is_latest_round and attended_count >= 8 and not round_item.get("is_expired"):
                is_active = True
            else:
                is_active = is_active_label and not round_item.get("is_expired")

            if is_active:
                student_active_count += 1
                active_rounds.append({
                    "student_name": student.get("student_name", ""),
                    **round_item,
                })
                # 續班提醒：包含 6/8, 7/8 接近完成，或最新一輪已滿 8 堂（8/8）待續約之學員
                if (attended_count in (6, 7) or (is_latest_round and attended_count >= 8)) and not round_item.get("is_expired"):
                    student_priority_count += 1
                    followup_rounds.append({
                        "student_name": student.get("student_name", ""),
                        **round_item,
                    })
                if attended_count >= 8:
                    student_priority_count += 1
                    completed_rounds.append({
                        "student_name": student.get("student_name", ""),
                        **round_item,
                    })

        student_statuses.append({
            "student_name": student.get("student_name", ""),
            "active_count": student_active_count,
            "priority_count": student_priority_count,
            "total_attended": student_total_attended,
            "latest_session": latest_session,
        })

    status_by_name = {s["student_name"]: s for s in student_statuses}

    def unique_students(records: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for r in records:
            name = r.get("student_name")
            if name and name not in seen:
                seen.add(name)
                st = status_by_name.get(name, {})
                enriched = {
                    **r,
                    "active_count": st.get("active_count", 1 if "進行中" in r.get("label", "") else 0),
                    "total_attended": st.get("total_attended", r.get("attended_count", 0)),
                    "priority_count": st.get("priority_count", 0),
                    "latest_session": st.get("latest_session", ""),
                }
                result.append(enriched)
        return result

    unique_active = unique_students(active_rounds)
    unique_completed = unique_students(completed_rounds)
    unique_followup = unique_students(followup_rounds)
    unique_expired = unique_students(expired_rounds)
    unique_expiring_soon = unique_students(expiring_soon_rounds)

    balance_status = "餘額正常"
    balance_note = f"目前場地結餘款 ${latest_balance}，可支應後續場地扣款。"
    if latest_balance < 0:
        balance_status = "場地費透支"
        balance_note = f"目前場地費已墊付 ${abs(latest_balance)}，請儘速向 Roger 老師儲值 ${abs(latest_balance)}。"
    elif latest_balance <= 600:
        balance_status = "餘額偏低"
        balance_note = f"目前場地結餘款僅剩 ${latest_balance}，即將不足支付下一場場地費，建議安排儲值。"

    return {
        "active_participant_count": len(active_participants),
        "total_sessions": total_sessions,
        "total_headcount": total_headcount,
        "avg_headcount": avg_headcount,
        "latest_attendance": latest_attendance,
        "latest_balance": latest_balance,
        "latest_balance_label": f"${latest_balance:,}",
        "latest_session_date": latest_attendance.get("date", "無紀錄"),
        "latest_session_venue": latest_attendance.get("venue", "無紀錄"),
        "active_rounds": active_rounds,
        "active_round_count": len(active_rounds),
        "followup_rounds": followup_rounds,
        "followup_round_count": len(followup_rounds),
        "followup_students": unique_followup,
        "followup_student_count": len(unique_followup),
        "completed_rounds": completed_rounds,
        "completed_round_count": len(completed_rounds),
        "completed_students": unique_completed,
        "completed_student_count": len(unique_completed),
        "expiring_soon_rounds": expiring_soon_rounds,
        "expiring_soon_round_count": len(expiring_soon_rounds),
        "expiring_soon_students": unique_expiring_soon,
        "expiring_soon_student_count": len(unique_expiring_soon),
        "expired_rounds": expired_rounds,
        "expired_round_count": len(expired_rounds),
        "expired_students": unique_expired,
        "expired_student_count": len(unique_expired),
        "active_students": unique_active,
        "active_student_count": len(unique_active),
        "inactive_students": [],
        "student_statuses": student_statuses,
        "balance_status": balance_status,
        "balance_note": balance_note,
        "total_tuition": total_tuition,
        "total_tuition_label": f"${total_tuition:,}",
        "tuition_count": tuition_count,
    }


def build_apple_ceo_view_context(
    program_data: dict[str, Any],
    students: list[dict[str, Any]],
    token: str = "adf9958b-a23d-4e9b-a4a2-156b5329b0ed",
    is_student_view: bool = False,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """【深模組聚合入口】統一組裝 program_apple_ceo.html 模板所需之視圖模型與學員名稱映射。"""
    effective_summary = summary if summary is not None else summarize_apple_ceo_program(program_data)
    name_to_student: dict[str, dict[str, Any]] = {}
    for s in students or []:
        s_name = s.get("name", "")
        if s_name:
            name_to_student[s_name] = s
        for alias in s.get("aliases", []):
            if alias:
                name_to_student[alias] = s

    teaching_notes = normalize_apple_ceo_notes(program_data.get("teaching_notes", []))

    return {
        "program": program_data.get("program", {}),
        "venue": program_data.get("venue", {}),
        "active_participants": program_data.get("active_participants", []),
        "attendance_records": program_data.get("attendance_records", []),
        "venue_ledger": program_data.get("venue_ledger", []),
        "student_rounds": program_data.get("student_rounds", []),
        "tuition_records": program_data.get("tuition_records", []),
        "teaching_notes": teaching_notes,
        "summary": effective_summary,
        "legacy_note": program_data.get("legacy_note", ""),
        "name_to_student": name_to_student,
        "token": token,
        # 課堂筆記屬於班級空間，不能沿用可能來自其他學員頁面的 token。
        "apple_note_token": APPLE_CEO_ACCESS_TOKEN,
        "is_student_view": is_student_view,
    }

