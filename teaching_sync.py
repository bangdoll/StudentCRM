from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DIGITAL_MANAGEMENT_LABEL = "數位管理教學"

MANUAL_ALIASES = {
    "chami": "查米",
    "chamibnimanagement": "查米",
    "chami 315": "查米",
    "查米 315": "查米",
    "查米315": "查米",
    "315.查米": "查米",
    "charlotte": "Charlotte",
    "陳姐": "Charlotte",
    "陳姐charlotte": "Charlotte",
    "kellywoo": "Kelly Woo",
    "lucia": "Lucia 徐露華",
    "roger": "Roger 黃凱亮",
    "roger黃凱亮": "Roger 黃凱亮",
    "anna蕭": "Anna 蕭",
    "anna蕭zoom": "Anna 蕭",
    "anna蕭-zoom": "Anna 蕭",
    "anna": "Anna 蕭",
    "amanda": "Anna 蕭",
    "amanda蕭秉慧": "Anna 蕭",
    "蕭秉慧": "Anna 蕭",
    "amy": "Amy",
    "annie": "Annie",
    "annie老師": "Annie",
    "安妮": "Annie",
    "安妮老師": "Annie",
    "腦波annie": "Annie",
    "大安妮": "大安妮",
    "大安妮老師": "大安妮",
    "大乘旅運": "大腳旅行社曹淑鈴Crystal",
    "大腳旅行社曹淑鈴crystal": "大腳旅行社曹淑鈴Crystal",
    "大腳旅行社曹淑鈴crystal曹姐": "大腳旅行社曹淑鈴Crystal",
    "曹淑鈴crystal": "大腳旅行社曹淑鈴Crystal",
    "曹淑鈴crystal曹姐": "大腳旅行社曹淑鈴Crystal",
    "曹淑鈴": "大腳旅行社曹淑鈴Crystal",
    "曹姐": "大腳旅行社曹淑鈴Crystal",
    "蘋果總裁班": "蘋果總裁班",
    "蘋果總裁班休息": "蘋果總裁班",
    "蘋果總裁班休息一次": "蘋果總裁班",
    "蘋果總裁班停課": "蘋果總裁班",
    "蘋果總裁班暫停一次": "蘋果總裁班",
    "Apple CEO Class": "蘋果總裁班",
    "Apple CEO": "蘋果總裁班",
    "楊老師": "楊-捷運台北橋站",
    "楊老師捷運台北橋站": "楊-捷運台北橋站",
    "shelley": "Shelley 陳萱玲",
    "shelley陳萱玲": "Shelley 陳萱玲",
    "shelley陳萱伶": "Shelley 陳萱玲",
    "陳萱玲": "Shelley 陳萱玲",
    "陳萱伶": "Shelley 陳萱玲",
    "julie陳怡君醫師": "Julie 陳怡君",
    "julie陳怡君": "Julie 陳怡君",
    "陳怡君": "Julie 陳怡君",
    "bill楊文祥": "Bill 楊文祥",
    "楊文祥": "Bill 楊文祥",
    "邱頂溪捷運站2號出口": "邱醫師",
    "邱311208": "邱醫師",
    "邱311": "邱醫師",
    "邱醫師": "邱醫師",
    "邱": "邱醫師",
    "陳姐": "Charlotte",
    "陳姐charlotte": "Charlotte",
    "charlotte陳姐": "Charlotte",
    "charlotte": "Charlotte",
    "國英": "國英老師",
    "國英老師": "國英老師",
    "國英（買電子書閱讀器）": "國英老師",
    "國英買電子書閱讀器": "國英老師",
    "和國英老師": "國英老師",
    "資深少年": "資深少年 AI 學習團",
    "資深少年ai學習團": "資深少年 AI 學習團",
    "資深少年ai領導力專班": "資深少年 AI 學習團",
    "禮品公會": "禮品公會",
    "禮品公會手機班": "禮品公會",
    "禮品公會手機班第二期": "禮品公會",
}


def normalize_match_text(value: str) -> str:
    return re.sub(r"[\s#._,，、:：()（）@\-－/\\\\]+", "", value or "").lower()


def extract_note_preview(content: str, limit: int = 280) -> str:
    if not content:
        return ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        texts: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                text = node.get("text")
                if isinstance(text, str):
                    texts.append(text)
                for child in node.get("content", []):
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(payload)
        preview = " ".join(texts)
    else:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        preview = " ".join(line for line in lines[:8] if not line.startswith("---"))

    return re.sub(r"\s+", " ", preview).strip()[:limit]


def parse_date_from_title(title: str) -> str:
    for match in re.finditer(r"(20\d{2})[-_ ./年]?(\d{2})[-_ ./月]?(\d{2})", title or ""):
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def parse_lesson_parts(value: str) -> tuple[int | None, str | None]:
    text = value or ""
    patterns = [
        r"(?:^|[\s#._-])Lesson[_\s-]*(?!20\d{6})(\d+)(?:[_\s-]+(\d+))?",
        r"^\s*(\d+)\s*[-－]\s*(\d*)\s*[.．、]?",
        r"^\s*(\d+)\s*[.．、]",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        lesson_num = int(match.group(1)) if match.group(1) else None
        lesson_sub = match.group(2) if len(match.groups()) > 1 and match.group(2) else None
        return lesson_num, lesson_sub
    return None, None


def candidate_name_from_title(title: str) -> str:
    stem = title[:-3] if title.endswith(".md") else title

    if "蘋果總裁班" in stem or "Apple_CEO" in stem or "Apple CEO" in stem:
        return "蘋果總裁班"

    if "資深少年" in stem or "Senior_AI" in stem or "Senior AI" in stem:
        return "資深少年 AI 學習團"

    if "禮品公會" in stem:
        return "禮品公會"

    lesson_match = re.match(r"Lesson[_\s-]*(20\d{6})[_\s-]+(.+)$", stem, re.IGNORECASE)
    if lesson_match:
        return re.sub(r"[_-]+", " ", lesson_match.group(2)).strip()

    text = re.sub(r"(20\d{2})[-_ ./年]?(\d{2})[-_ ./月]?(\d{2})", "", stem, count=1).strip()
    text = text.strip(" #._-")

    if DIGITAL_MANAGEMENT_LABEL in text:
        text = text.split(DIGITAL_MANAGEMENT_LABEL, 1)[0]

    text = text.split("@", 1)[0]
    text = re.sub(r"\bLesson[_\s-]*\d+(?:[_\s-]+\d+)?\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d+\s*[-－]\s*\d*\s*[.．、]?\s*", "", text)
    text = re.sub(r"^\s*\d+\s*[.．、]\s*", "", text)
    text = text.strip(" #._-，,、")
    return re.sub(r"\s+", " ", text)


def parse_teaching_file(path: str | Path) -> dict[str, Any] | None:
    file_path = Path(path)
    title = file_path.stem
    if "我的工作是數位教練" in title or "eDM" in title:
        return None
    is_digital_management = DIGITAL_MANAGEMENT_LABEL in title
    is_lesson_file = bool(re.match(r"Lesson[_\s-]*20\d{6}[_\s-]+", title, re.IGNORECASE))
    is_apple_ceo = "蘋果總裁班" in title or "Apple_CEO" in title or "Apple CEO" in title
    is_group_class = any(k in title for k in ["資深少年", "AI學習團", "AI 學習團", "Senior_AI", "禮品公會"])
    if not is_digital_management and not is_lesson_file and not is_apple_ceo and not is_group_class:
        return None

    date = parse_date_from_title(title)
    title_without_date = re.sub(r"(20\d{2})[-_ ./年]?(\d{2})[-_ ./月]?(\d{2})", "", title, count=1).strip()
    title_without_date = title_without_date.lstrip(" .-_#")
    lesson_num, lesson_sub = parse_lesson_parts(title_without_date)
    if lesson_num is None and not date:
        lesson_num, lesson_sub = parse_lesson_parts(title)
    candidate_name = candidate_name_from_title(title)
    if not candidate_name:
        return None

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""

    try:
        stat = file_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except OSError:
        mtime = ""
    return {
        "card_id": hashlib.sha1(str(file_path).encode("utf-8")).hexdigest(),
        "title": f"#{title}",
        "date": date,
        "lesson_num": lesson_num,
        "lesson_sub": lesson_sub,
        "student_name": candidate_name,
        "created": mtime,
        "edited": mtime,
        "path": str(file_path),
        "filename": file_path.name,
        "preview": extract_note_preview(content),
        "content": content,
        "source": "local_teaching",
    }


def build_student_match_index(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    by_normalized_name = {normalize_match_text(student.get("name", "")): student for student in students}

    for student in students:
        names = [student.get("name", ""), *student.get("aliases", [])]
        for name in names:
            key = normalize_match_text(name)
            if key:
                candidates.append({"key": key, "label": name, "student": student})

    for alias_key, target_name in MANUAL_ALIASES.items():
        target = by_normalized_name.get(normalize_match_text(target_name))
        if target:
            candidates.append({"key": normalize_match_text(alias_key), "label": alias_key, "student": target})

    unique = {}
    for item in candidates:
        candidate_key = (item["key"], item["student"].get("id", ""))
        if candidate_key not in unique:
            unique[candidate_key] = item
    return sorted(unique.values(), key=lambda item: len(item["key"]), reverse=True)


def resolve_student(candidate_name: str, students: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    candidate_key = normalize_match_text(candidate_name)
    if not candidate_key:
        return None, ""
    index = build_student_match_index(students)
    for item in index:
        if item["key"] == candidate_key:
            return item["student"], item["label"]
    for item in index:
        key = item["key"]
        if key and key in candidate_key:
            return item["student"], item["label"]
    for item in index:
        key = item["key"]
        if key and candidate_key in key:
            return item["student"], item["label"]
    return None, ""


def build_teaching_records_from_directory(teaching_dir: str | Path, students: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    unmatched: list[dict[str, str]] = []
    by_student: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(Path(teaching_dir).glob("*.md")):
        parsed = parse_teaching_file(path)
        if not parsed:
            continue
        student, matched_by = resolve_student(parsed["student_name"], students)
        if not student:
            unmatched.append({
                "filename": parsed["filename"],
                "candidate_name": parsed["student_name"],
                "date": parsed["date"],
            })
            continue

        record = {
            **parsed,
            "student_id": student.get("id", ""),
            "student_name": student.get("name", parsed["student_name"]),
            "matched_by": matched_by,
        }
        records.append(record)
        by_student.setdefault(record["student_id"], []).append(record)

    records.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)
    for items in by_student.values():
        items.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)

    duplicate_keys = set()
    seen = set()
    for record in records:
        key = (record.get("student_id"), record.get("date"), record.get("lesson_num"), record.get("lesson_sub"), record.get("title"))
        if key in seen:
            duplicate_keys.add(key)
        seen.add(key)

    return {
        "total_records": len(records),
        "total_students": len(by_student),
        "records": records,
        "by_student": by_student,
        "unmatched": unmatched,
        "duplicate_count": len(duplicate_keys),
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def sync_teaching_records_to_crm(workspace_dir: str | Path | None = None) -> dict[str, Any]:
    """將 01.Docs/teaching 的所有教學筆記完整同步至 StudentCRM 系統。
    涵蓋：
    1. 一對一教學：更新 data/teaching_records.json，並自動推移 students.json 之最新上課日期與堂數。
    2. 蘋果總裁班：更新 data/apple_ceo_class.json 的 teaching_notes 陣列。
    3. 專班/團體班（如資深少年 AI 學習團、禮品公會等）：同步入庫並精確關聯。
    4. 自動清理 data_gateway 記憶體快取。
    """
    if workspace_dir is None:
        workspace_dir = Path(__file__).resolve().parents[2]
    else:
        workspace_dir = Path(workspace_dir)

    crm_dir = workspace_dir / "07.Projects" / "StudentCRM"
    teaching_dir = workspace_dir / "01.Docs" / "teaching"
    students_file = crm_dir / "data" / "students.json"
    root_students_file = workspace_dir / "OpenClaw" / "Data" / "students.json"
    apple_ceo_file = crm_dir / "data" / "apple_ceo_class.json"
    cache_teaching_file = crm_dir / "data" / "teaching_records.json"
    backup_cache_file = crm_dir / "cache" / "teaching_records.json"

    if not students_file.exists() and root_students_file.exists():
        students_file = root_students_file

    if not students_file.exists():
        raise FileNotFoundError(f"找不到學員資料庫: {students_file}")

    with open(students_file, "r", encoding="utf-8") as f:
        students = json.load(f)

    # 1. 產生全量教學紀錄
    result = build_teaching_records_from_directory(teaching_dir, students)

    # 2. 寫入 data/teaching_records.json 與 cache/teaching_records.json
    cache_teaching_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_teaching_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    backup_cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(backup_cache_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 3. 同步至 apple_ceo_class.json (蘋果總裁班教學紀錄)
    apple_ceo_synced_count = 0
    if apple_ceo_file.exists():
        try:
            with open(apple_ceo_file, "r", encoding="utf-8") as f:
                apple_ceo_data = json.load(f)

            current_notes = apple_ceo_data.get("teaching_notes", [])
            existing_note_keys = {
                (n.get("date"), n.get("filename") or n.get("title")): idx
                for idx, n in enumerate(current_notes)
            }

            for r in result["records"]:
                if r.get("student_name") == "蘋果總裁班" or "蘋果總裁班" in r.get("filename", ""):
                    date = r.get("date", "")
                    filename = r.get("filename", "")
                    title = re.sub(r"^#?(?:20\d{2}[-_ ./年]?\d{2}[-_ ./月]?\d{2}\s*)?", "", filename[:-3]).strip()
                    full_title = filename[:-3]
                    content = r.get("content", "")
                    preview = r.get("preview", "")[:280]
                    word_count = len(content)

                    note_obj = {
                        "date": date,
                        "title": title or full_title,
                        "full_title": full_title,
                        "filename": filename,
                        "path": f"/01.Docs/teaching/{filename}",
                        "preview": preview,
                        "word_count": word_count,
                        "content": content,
                    }

                    key = (date, filename)
                    alt_key = (date, title)
                    if key in existing_note_keys:
                        idx = existing_note_keys[key]
                        current_notes[idx] = note_obj
                    elif alt_key in existing_note_keys:
                        idx = existing_note_keys[alt_key]
                        current_notes[idx] = note_obj
                    else:
                        current_notes.append(note_obj)
                        existing_note_keys[key] = len(current_notes) - 1
                    apple_ceo_synced_count += 1

            current_notes.sort(key=lambda n: (n.get("date") or "", n.get("title") or ""), reverse=True)
            with open(apple_ceo_file, "w", encoding="utf-8") as f:
                json.dump(apple_ceo_data, f, ensure_ascii=False, indent=2)
            root_apple = workspace_dir / "OpenClaw" / "Data" / "apple_ceo_class.json"
            if root_apple.exists() and root_apple.resolve() != apple_ceo_file.resolve():
                with open(root_apple, "w", encoding="utf-8") as f:
                    json.dump(apple_ceo_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 同步 apple_ceo_class.json 失敗: {e}")

    # 4. 更新學員進度 (一對一與專班學員之 latest_date 與 lessons_count)
    students_updated = []
    for s in students:
        sid = s.get("id")
        if not sid or sid not in result["by_student"]:
            continue
        student_records = result["by_student"][sid]
        dates = [r.get("date") for r in student_records if r.get("date")]
        if not dates:
            continue
        max_date = max(dates)
        lesson_nums = [r.get("lesson_num") for r in student_records if isinstance(r.get("lesson_num"), int)]
        max_lesson = max(lesson_nums) if lesson_nums else None

        changed = False
        old_latest = s.get("latest_date", "")
        if max_date > old_latest:
            s["latest_date"] = max_date
            changed = True

        if max_lesson is not None and max_lesson > s.get("lessons_count", 0):
            s["lessons_count"] = max_lesson
            s["current_cycle_lesson"] = ((max_lesson % 8) or 8) if max_lesson > 0 else 0
            changed = True

        if changed:
            students_updated.append({
                "id": sid,
                "name": s.get("name"),
                "latest_date": s.get("latest_date"),
                "lessons_count": s.get("lessons_count"),
            })

    if students_updated:
        with open(students_file, "w", encoding="utf-8") as f:
            json.dump(students, f, ensure_ascii=False, indent=2)
        if root_students_file.exists() and root_students_file.resolve() != students_file.resolve():
            with open(root_students_file, "w", encoding="utf-8") as f:
                json.dump(students, f, ensure_ascii=False, indent=2)

    # 5. 清理記憶體快取
    try:
        from data_gateway import clear_gateway_memory_cache
        clear_gateway_memory_cache()
    except Exception:
        pass

    return {
        "success": True,
        "total_records": result["total_records"],
        "total_students": result["total_students"],
        "apple_ceo_notes_count": apple_ceo_synced_count,
        "students_updated_count": len(students_updated),
        "students_updated": students_updated,
        "generated_at": result["generated_at"],
    }

