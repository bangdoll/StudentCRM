"""note_service.py - 筆記解析、檢索、品質評估與分頁導航深模組。

依據 Matt Pocock 深模組架構（Deep Module）：
- 公開極簡乾淨的介面 (resolve_note_detail, clean_markdown_frontmatter, get_note_quality)
- 內部封裝本地實體檔案、雲端 JSON 備份、蘋果總裁班與數位管理教學筆記之消歧義比對與上下篇串接
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
import markdown


@dataclass
class NoteDetail:
    """封裝呈現於 note.html 所需之完整資料物件。"""
    filename: str
    note_title: str
    note_date: str
    lesson_label: str
    content_html: str
    path: str
    student_id: str
    student_name: str
    is_apple_ceo: bool
    prev_path: str | None
    prev_label: str
    next_path: str | None
    next_label: str
    word_count: int
    read_minutes: int

    def to_template_context(self) -> dict:
        """轉換為傳遞至 Jinja2 樣板的字典。"""
        return {
            "filename": self.filename,
            "note_title": self.note_title,
            "note_date": self.note_date,
            "lesson_label": self.lesson_label,
            "content_html": self.content_html,
            "path": self.path,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "is_apple_ceo": self.is_apple_ceo,
            "prev_path": self.prev_path,
            "prev_label": self.prev_label,
            "next_path": self.next_path,
            "next_label": self.next_label,
            "word_count": self.word_count,
            "read_minutes": self.read_minutes,
        }


def clean_markdown_frontmatter(content: str) -> str:
    """移除 Markdown 開頭之 YAML Frontmatter (--- ... ---)。"""
    if not content:
        return ""
    return re.sub(r"^---[\s\S]*?---\s*", "", content)


def extract_note_preview(content: str, limit: int = 280) -> str:
    """從 Markdown 內容中提取乾淨之純文字重點摘要。"""
    if not content:
        return ""
    # 移除 frontmatter
    text = clean_markdown_frontmatter(content)
    # 移除標題行與 code blocks
    text = re.sub(r"^#+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    # 移除連結語法，只保留文字
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # 壓縮空白
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:limit] + "...") if len(text) > limit else text


def get_note_quality(path: str, content: str = "") -> tuple[str, str, str]:
    """依據筆記字數長度評定品質等級，回傳 (emoji, css_class, label)。"""
    if not content:
        if not path or not os.path.exists(path):
            return "❌", "badge-missing", "找不到文件"
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "❌", "badge-missing", "無法讀取"

    length = len(content)
    if length > 800:
        return "✅", "badge-full", f"{length} 字"
    elif length > 200:
        return "⚠️", "badge-short", f"{length} 字（待補充）"
    else:
        return "📄", "badge-placeholder", "佔位文件"


def get_architect_insight(path: str, content: str = "") -> dict:
    """分析筆記之思維層級（架構思維 vs 工具思維）與結構診斷摘要。"""
    if not content:
        if not path or not os.path.exists(path):
            return {"level": "unknown", "badge": "❓", "class": "badge-unknown", "snippet": ""}
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {"level": "unknown", "badge": "❓", "class": "badge-unknown", "snippet": ""}

    structure_words = ["結構", "制度", "系統", "框架", "門戶", "地基", "本質"]
    tool_words = ["按鈕", "工具", "功能", "教學", "操作", "設定", "手機"]

    s_count = sum(content.count(w) for w in structure_words)
    t_count = sum(content.count(w) for w in tool_words)

    level = "structure" if s_count > t_count else "tool"
    badge = "🏗️" if level == "structure" else "🔧"
    cls = "badge-structure" if level == "structure" else "badge-tool"
    label = "架構思維" if level == "structure" else "工具思維"

    diag_match = re.search(r"#### 1. 結構偏移點 (.*?)(?=\n####|$)", content, re.DOTALL)
    snippet = ""
    if diag_match and "\n- " in diag_match.group(1):
        snippet = diag_match.group(1).split("\n- ")[1].split("：")[0]

    return {"level": level, "badge": badge, "class": cls, "label": label, "snippet": snippet}


def resolve_note_detail(
    path_or_filename: str,
    base_dir: str,
    apple_notes: list[dict] | None = None,
    cloud_records: list[dict] | None = None,
    students: list[dict] | None = None,
) -> NoteDetail | None:
    """核心深模組解析器：

    根據傳入之路徑或檔名，統一從：
    1. 蘋果總裁班系列筆記 (apple_notes)
    2. 雲端教學紀錄 (cloud_records)
    3. 本地實體檔案 (base_dir)
    進行多重比對，自動解析上下文、上下篇分頁導航並產出 NoteDetail。
    若完全無法匹配且無實體檔案，回傳 None。
    """
    if not path_or_filename or path_or_filename.startswith(".."):
        return None

    filename = os.path.basename(path_or_filename)
    note_title = filename.replace(".md", "")
    note_date = ""
    lesson_label = ""
    is_apple_ceo = False
    content = ""
    sid = ""
    student_name = ""

    apple_notes = apple_notes or []
    cloud_records = cloud_records or []
    students = students or []

    # 1. 比對「蘋果總裁班」教學筆記 (82 篇)
    apple_match = next((
        n for n in apple_notes
        if n.get("path") == path_or_filename
        or n.get("filename") == filename
        or os.path.basename(n.get("path", "")) == filename
        or (path_or_filename and path_or_filename.endswith(n.get("filename", "---")))
    ), None)

    # 2. 比對數位管理教學筆記
    record_match = next((
        r for r in cloud_records
        if r.get("path") == path_or_filename
        or r.get("filename") == filename
        or os.path.basename(r.get("path", "")) == filename
        or r.get("id") == path_or_filename
    ), None)

    if apple_match:
        is_apple_ceo = True
        note_title = apple_match.get("title", filename.replace(".md", ""))
        note_date = apple_match.get("date", "")
        lesson_label = "蘋果總裁班"
        content = apple_match.get("content") or ""
        student_name = "蘋果總裁班"
    elif record_match:
        note_title = record_match.get("title", "").lstrip("#")
        note_date = record_match.get("date", "")
        if record_match.get("lesson_number"):
            lesson_label = f"第 {record_match.get('lesson_number')}"
            if record_match.get("lesson_sub"):
                lesson_label += f"-{record_match.get('lesson_sub')}"
            lesson_label += " 堂"
        content = record_match.get("content") or ""
        sid = record_match.get("student_id", "")
        student_name = record_match.get("student_name", "")

    # 3. 本地實體檔案優先覆蓋即時內容
    resolved_paths = [
        path_or_filename,
        os.path.join(base_dir, path_or_filename.lstrip('/')),
        os.path.join(base_dir, "01.Docs", "teaching", filename),
    ]
    for p in resolved_paths:
        if p and os.path.exists(p) and os.path.isfile(p):
            try:
                content = Path(p).read_text(encoding="utf-8", errors="ignore")
                break
            except OSError:
                pass

    if not content:
        if apple_match:
            content = f"# {apple_match.get('title')}\n\n**上課日期**：{apple_match.get('date')}\n\n**重點摘要**：\n\n{apple_match.get('preview')}"
        elif record_match:
            content = (
                f"# {record_match.get('title')}\n\n"
                f"**上課日期**：{record_match.get('date')}\n\n"
                f"**堂數**：第 {record_match.get('lesson_number') or '-'} 堂\n\n"
                f"**重點摘要**：\n\n{record_match.get('preview')}"
            )
        else:
            return None

    # 解析學員資訊 (若尚未確認)
    if not student_name and sid:
        matched = next((s for s in students if s.get("id") == sid), None)
        if matched:
            student_name = matched.get("name", "")

    # 解析上下篇筆記導航
    prev_path = next_path = None
    prev_label = next_label = ""

    if is_apple_ceo and apple_notes:
        # 依日期由舊到新排序，確保 idx - 1 恆為上一篇（歷史課堂），idx + 1 恆為下一篇（後續課堂）
        sorted_notes = sorted(apple_notes, key=lambda x: x.get("date", ""))
        note_filenames = [n.get("filename") for n in sorted_notes]
        if filename in note_filenames:
            idx = note_filenames.index(filename)
            if idx > 0:
                prev_path = sorted_notes[idx - 1].get("path")
                prev_label = sorted_notes[idx - 1].get("date") or "上一篇"
            if idx < len(sorted_notes) - 1:
                next_path = sorted_notes[idx + 1].get("path")
                next_label = sorted_notes[idx + 1].get("date") or "下一篇"
    elif record_match:
        # 如果是同一個學員的課堂紀錄，依日期排序串接上一堂與下一堂
        same_student_records = [r for r in cloud_records if r.get("student_id") == sid or (student_name and r.get("student_name") == student_name)]
        if same_student_records:
            same_student_records.sort(key=lambda x: x.get("date", ""))
            paths = [r.get("path") or r.get("filename") for r in same_student_records]
            cur_key = record_match.get("path") or record_match.get("filename")
            if cur_key in paths:
                idx = paths.index(cur_key)
                if idx > 0:
                    prev_path = paths[idx - 1]
                    prev_label = same_student_records[idx - 1].get("date") or "上一堂"
                if idx < len(paths) - 1:
                    next_path = paths[idx + 1]
                    next_label = same_student_records[idx + 1].get("date") or "下一堂"

    clean_content = clean_markdown_frontmatter(content)
    html_content = markdown.markdown(clean_content, extensions=["tables", "fenced_code", "nl2br"])
    word_count = len(content)
    read_minutes = max(1, round(word_count / 500))

    return NoteDetail(
        filename=filename,
        note_title=note_title,
        note_date=note_date,
        lesson_label=lesson_label,
        content_html=html_content,
        path=path_or_filename,
        student_id=sid,
        student_name=student_name,
        is_apple_ceo=is_apple_ceo,
        prev_path=prev_path,
        prev_label=prev_label,
        next_path=next_path,
        next_label=next_label,
        word_count=word_count,
        read_minutes=read_minutes,
    )
