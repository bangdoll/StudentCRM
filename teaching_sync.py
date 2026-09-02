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
    "charlotte": "Charlotte",
    "kellywoo": "Kelly Woo",
    "lucia": "Lucia 徐露華",
    "roger": "Roger 黃凱亮",
    "roger黃凱亮": "Roger 黃凱亮",
    "anna蕭": "Anna 蕭",
    "anna": "Anna 蕭",
    "amy": "Amy",
    "annie": "大安妮",
    "蘋果總裁班": "Apple CEO Class",
    "蘋果總裁班休息": "Apple CEO Class",
    "蘋果總裁班休息一次": "Apple CEO Class",
    "蘋果總裁班停課": "Apple CEO Class",
    "蘋果總裁班暫停一次": "Apple CEO Class",
    "楊老師": "楊-捷運台北橋站",
    "楊老師捷運台北橋站": "楊-捷運台北橋站",
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
    is_digital_management = DIGITAL_MANAGEMENT_LABEL in title
    is_lesson_file = bool(re.match(r"Lesson[_\s-]*20\d{6}[_\s-]+", title, re.IGNORECASE))
    if not is_digital_management and not is_lesson_file:
        return None

    date = parse_date_from_title(title)
    title_without_date = re.sub(r"(20\d{2})[-_ ./年]?(\d{2})[-_ ./月]?(\d{2})", "", title, count=1).strip()
    lesson_num, lesson_sub = parse_lesson_parts(title_without_date)
    if lesson_num is None:
        lesson_num, lesson_sub = parse_lesson_parts(title)
    candidate_name = candidate_name_from_title(title)
    if not candidate_name:
        return None

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""

    stat = file_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
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
        unique[(item["key"], item["student"].get("id", ""))] = item
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
