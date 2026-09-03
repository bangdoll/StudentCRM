"""hub_service.py - StudentCRM 學員專屬空間、教學筆記聚合與數位管理檔案深模組。

依據 Matt Pocock 深模組原則：
- 封裝學員專屬 Hub 網址重導向（get_merged_redirects）
- 封裝多來源課堂筆記聚合去重（本地 teaching 目錄、雲端快取、蘋果總裁班系列）
- 封裝數位管理教學檔案與出席日程解析（build_digital_management_profiles）
- 封裝學員個人 PWA 動態 Manifest 與 Timeline HTML 渲染
"""

from __future__ import annotations

import glob
import html as html_lib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

from student_service import (
    digital_student_id,
    normalize_digital_name,
)
from note_service import (
    extract_micro_action_cards,
    extract_note_preview,
    get_architect_insight,
    get_note_quality,
)

MERGED_REDIRECTS_FILE_DEFAULT = "data/merged_redirects.json"


def get_merged_redirects(app_dir: str) -> dict[str, str]:
    """取得歷史舊學員 ID 至標準學員 ID 之對照重導向字典。"""
    redirects = {
        "d892570c-70d2-4fba-9f2e-614ba775232b": "d06bb300-4b9e-44b5-8cd3-1b47695cdee4",  # 查米 315 -> 查米
        "0e6b6b92-ebe9-4252-a6cf-3907b78700f7": "d06bb300-4b9e-44b5-8cd3-1b47695cdee4",  # Chami BNI Management 38 6 -> 查米
    }
    redirects_file = os.path.join(app_dir, MERGED_REDIRECTS_FILE_DEFAULT)
    if os.path.exists(redirects_file):
        try:
            with open(redirects_file, "r", encoding="utf-8") as f:
                redirects.update(json.load(f))
        except Exception:
            pass
    return redirects


def parse_datetime(value: str) -> datetime | None:
    """解析各類標準 ISO 或日期字串為帶 UTC 時區的 datetime。"""
    if not value:
        return None
    for pattern in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(value, pattern)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def parse_digital_management_title(summary: str) -> dict[str, Any]:
    """解析 Google 日曆或筆記標題中的堂數、副堂數與學生名稱。"""
    clean_summary = (summary or "").strip()
    match = re.search(r"(\d+)(?:[-_](\d+))?\s*[.、\s]\s*數位管理教學(?:[-_](\S+))?", clean_summary)
    if not match:
        match = re.search(r"(\d+)(?:[-_](\d+))?\s*[.、\s]\s*(\S+?)(?:教學|課)?$", clean_summary)

    if match:
        lesson_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else None
        student_raw = match.group(3) or ""
        return {
            "lesson_number": lesson_num,
            "lesson_sub": sub_num,
            "student_name": normalize_digital_name(student_raw),
            "raw_title": clean_summary,
        }

    return {
        "lesson_number": None,
        "lesson_sub": None,
        "student_name": normalize_digital_name(clean_summary),
        "raw_title": clean_summary,
    }


def teaching_note_identity_keys(note: dict) -> list[tuple]:
    """生成教學筆記之唯一去重鑑別金鑰。"""
    keys = []
    path = note.get("path") or ""
    filename = note.get("filename") or os.path.basename(path)
    if filename:
        keys.append(("file", filename.lower()))

    date = note.get("date") or ""
    student_id = note.get("student_id") or ""
    student_name = (note.get("student_name") or "").lower()
    lesson_num = note.get("lesson_number")

    if date and student_id:
        keys.append(("date_sid", date, student_id))
    if date and student_name:
        keys.append(("date_name", date, student_name))
    if student_id and lesson_num:
        keys.append(("sid_lesson", student_id, lesson_num))
    if student_name and lesson_num:
        keys.append(("name_lesson", student_name, lesson_num))

    return keys


def merge_teaching_notes(*note_groups: list[dict]) -> list[dict]:
    """將來自本地實體檔案、雲端快取等多個來源的教學筆記安全去重並依日期倒序排列。"""
    seen: set[tuple] = set()
    merged: list[dict] = []

    for group in note_groups:
        for note in group or []:
            identities = teaching_note_identity_keys(note)
            if any(identity in seen for identity in identities):
                continue
            seen.update(identities)
            merged.append(note)

    return sorted(merged, key=lambda item: item.get("date") or "", reverse=True)


def load_local_digital_management_notes(base_dir: str) -> list[dict]:
    """讀取本地 01.Docs/teaching 目錄下的實體 Markdown 教學筆記。"""
    teaching_dir = os.path.join(base_dir, "01.Docs", "teaching")
    if not os.path.exists(teaching_dir):
        return []

    notes = []
    for filepath in glob.glob(os.path.join(teaching_dir, "*.md")):
        filename = os.path.basename(filepath)
        filename_no_ext = filename.replace(".md", "")

        date_match = re.search(r"(\d{4}[-_]?\d{2}[-_]?\d{2})", filename)
        date_str = ""
        if date_match:
            raw_d = date_match.group(1).replace("-", "").replace("_", "")
            if len(raw_d) == 8:
                date_str = f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:]}"

        info = parse_digital_management_title(filename_no_ext)
        preview_text = ""
        word_count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                preview_text = extract_note_preview(content)
                word_count = len(content)
        except OSError:
            pass

        notes.append({
            "source": "local_teaching",
            "path": f"/01.Docs/teaching/{filename}",
            "filename": filename,
            "title": filename_no_ext,
            "date": date_str,
            "student_name": info["student_name"],
            "student_id": digital_student_id(info["student_name"]) if info["student_name"] else "",
            "lesson_number": info["lesson_number"],
            "lesson_sub": info["lesson_sub"],
            "preview": preview_text,
            "word_count": word_count,
        })
    return sorted(notes, key=lambda item: item.get("date") or "", reverse=True)


def load_cloud_digital_management_notes(app_dir: str) -> list[dict]:
    """讀取本地快取或 Supabase 備份之 teaching_records.json。"""
    cache_path = os.path.join(app_dir, "data", "teaching_records.json")
    if not os.path.exists(cache_path):
        cache_path = os.path.join(app_dir, "cache", "teaching_records.json")
    if not os.path.exists(cache_path):
        return []

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    records = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    notes = []
    for r in records:
        title = r.get("title") or r.get("filename") or ""
        sname = normalize_digital_name(r.get("student_name") or "")
        sid = r.get("student_id") or (digital_student_id(sname) if sname else "")
        preview_text = r.get("preview") or extract_note_preview(r.get("content") or "")
        notes.append({
            "source": "cloud_records",
            "path": r.get("path") or f"/01.Docs/teaching/{r.get('filename', '')}",
            "filename": r.get("filename") or os.path.basename(r.get("path") or ""),
            "title": title,
            "date": r.get("date") or "",
            "student_name": sname,
            "student_id": sid,
            "lesson_number": r.get("lesson_number"),
            "lesson_sub": r.get("lesson_sub"),
            "content": r.get("content") or "",
            "preview": preview_text,
            "word_count": r.get("word_count") or len(r.get("content") or ""),
        })
    return notes


def get_student_teaching_notes(
    student: dict,
    base_dir: str = "",
    app_dir: str = "",
    apple_program_loader: Callable[[], dict[str, Any]] | None = None,
    local_notes_loader: Callable[[], list[dict]] | None = None,
    cloud_notes_loader: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    """取得特定學員的所有教學筆記（支援本地 teaching 檔案、雲端快取與蘋果總裁班，支援注入自訂 loader）。"""
    sid = student.get("id", "")
    sname = student.get("name", "")
    aliases = student.get("aliases", [])
    target_names = {sname.lower()} | {a.lower() for a in aliases}
    is_apple_ceo = "總裁班" in sname or any("總裁班" in a for a in aliases)

    local_notes = local_notes_loader() if local_notes_loader is not None else load_local_digital_management_notes(base_dir)
    cloud_notes = cloud_notes_loader() if cloud_notes_loader is not None else load_cloud_digital_management_notes(app_dir)
    teaching_notes = merge_teaching_notes(local_notes, cloud_notes)

    matched = []
    seen = set()

    def append_unique(note: dict) -> None:
        identity_keys = teaching_note_identity_keys(note)
        if any(key in seen for key in identity_keys):
            return
        seen.update(identity_keys)
        matched.append(note)

    if is_apple_ceo and apple_program_loader:
        apple_program = apple_program_loader()
        for an in apple_program.get("teaching_notes", []):
            append_unique(an)

    for n in teaching_notes:
        note_sid = n.get("student_id", "")
        note_name = (n.get("student_name") or "").lower()
        if note_sid == sid or (note_name and note_name in target_names):
            append_unique(n)

    return sorted(matched, key=lambda x: x.get("date") or "", reverse=True)


def parse_frontmatter_metadata(frontmatter: str) -> dict[str, Any]:
    """解析筆記 YAML Frontmatter。"""
    metadata: dict[str, Any] = {}
    lines = frontmatter.strip().split("\n")
    for line in lines:
        if ":" in line:
            key, val = line.split(":", 1)
            metadata[key.strip()] = val.strip()
    return metadata


def get_student_metadata(file_path: str) -> dict[str, Any]:
    """從 Markdown 檔案中提取 Frontmatter 與標題元資料。"""
    if not file_path or not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return {}

    frontmatter_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    metadata = {}
    if frontmatter_match:
        metadata = parse_frontmatter_metadata(frontmatter_match.group(1))

    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match and "name" not in metadata:
        metadata["name"] = title_match.group(1).strip()

    return metadata


def build_cloud_student_meta(student: dict) -> dict[str, Any]:
    """建立純雲端無本地檔案環境下的學員元資料。"""
    first_date = student.get("first_lesson_date") or "未記錄"
    last_date = student.get("latest_date") or "未記錄"
    lessons_count = student.get("lessons_count", 0)

    tags = list(student.get("tags") or ["一般學員"])
    status = "穩定留存"
    if lessons_count >= 8:
        tags.append("需注意續費")
        status = "需注意續費"
    elif lessons_count > 0:
        status = "正常上課中"

    return {
        "name": student.get("name"),
        "status": status,
        "first_lesson_date": first_date,
        "last_lesson_date": last_date,
        "lessons_count": lessons_count,
        "next_lesson": student.get("next_lesson") or "尚未排定",
        "tags": tags,
        "frequency": "每週固定" if student.get("recurring_schedule") else "彈性預約",
        "cycle_lesson": student.get("current_cycle_lesson", 1),
    }


def generate_student_manifest_data(student_name: str, token: str) -> dict[str, Any]:
    """產生學員專屬之 PWA Web Manifest 配置物件。"""
    return {
        "name": f"{student_name} 的專屬數位學習空間",
        "short_name": f"{student_name} Hub",
        "description": f"{student_name} 的專屬數位管理學習空間",
        "start_url": f"/my/{token}",
        "scope": f"/my/{token}",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#0d1117",
        "icons": [
            {
                "src": "/static/apple-touch-icon.png",
                "sizes": "180x180",
                "type": "image/png",
            },
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
