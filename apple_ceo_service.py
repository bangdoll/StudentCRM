from __future__ import annotations

import calendar
import glob
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


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
        if "我的工作是數位教練" in stem or "eDM" in stem:
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
    normalized_attendees = [name.strip() for name in attendees if name and name.strip()]
    student_rounds = program_data.get("student_rounds", [])
    name_to_group = {
        normalize_attendee_name(group.get("student_name", "")): group
        for group in student_rounds
    }

    warnings = []
    affected_rounds = []

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
        "date": date,
        "venue": venue,
        "attendee_count": len(normalized_attendees),
        "attendees": normalized_attendees,
        "note": note,
    }

    return {
        "proposed_record": proposed_record,
        "affected_rounds": affected_rounds,
        "warnings": warnings,
        "summary": {
            "attendee_count": len(normalized_attendees),
            "matched_count": len(affected_rounds),
            "warning_count": len(warnings),
        },
    }


def summarize_apple_ceo_program(program_data: dict, today: date | None = None) -> dict:
    """計算蘋果總裁班的核心財務、出勤、效期與學員狀態指標。"""
    if today is None:
        today = date.today()

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

            # 2. 若無，比對 tuition_records 該學員之繳費日
            if not base_date:
                student_name = student.get("student_name", "")
                aliases = student.get("aliases", [])
                matched_tuitions = [
                    t for t in tuition_records
                    if t.get("student_name") == student_name or t.get("student_name") in aliases
                ]
                if "進行中" in round_item.get("label", "") and matched_tuitions:
                    try:
                        latest_t_date = matched_tuitions[-1].get("date")
                        base_date = datetime.strptime(latest_t_date, "%Y-%m-%d").date()
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
                is_active = is_active_label

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
