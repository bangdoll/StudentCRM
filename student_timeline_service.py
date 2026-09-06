"""
學員時間軸與前綴評估服務 (student_timeline_service.py)
======================================================
專職處理學員時光軸渲染、Markdown Frontmatter 解析、筆記品質標籤（Quality Badge）、
架構師見解（Architect Insight）、課後紀錄路徑對齊與 AI 預測特徵前置處理。
依循深模組 (Deep Module) 原則，提供高內聚且具備向後相容性之純函式介面。
"""

import os
import re
import html as html_lib
from typing import Callable, Any

from teaching_sync import (
    resolve_student,
    parse_teaching_file,
)
from hub_service import (
    get_student_teaching_notes as service_get_student_teaching_notes,
)
from prediction_service import (
    get_student_lesson_paths as service_get_student_lesson_paths,
    analyze_student_features as service_analyze_student_features,
)

# ── 環境路徑與常數配置 ────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def find_base_dir(start_dir: str) -> str:
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, "OpenClaw")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return start_dir


DEFAULT_BASE_DIR = find_base_dir(APP_DIR)
BASE_DIR = os.getenv("OPEN_CLAW_BASE_DIR", DEFAULT_BASE_DIR)


def get_student_metadata(file_path: str) -> dict:
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return parse_frontmatter_metadata(match.group(1))


def parse_frontmatter_metadata(frontmatter: str) -> dict:
    """Parse the small YAML subset used by student profile frontmatter."""
    metadata = {}
    current_list_key = None

    for raw_line in frontmatter.splitlines():
        if not raw_line.strip():
            continue

        stripped = raw_line.strip()
        if stripped.startswith("- ") and current_list_key:
            metadata.setdefault(current_list_key, []).append(
                stripped[2:].strip().strip('"').strip("'")
            )
            continue

        current_list_key = None
        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not value:
            metadata[key] = []
            current_list_key = key
            continue

        value = value.strip('"').strip("'")
        if value.isdigit():
            metadata[key] = int(value)
        else:
            metadata[key] = value

    return metadata


def get_note_quality(path: str) -> tuple[str, str, str]:
    """Return (emoji, css_class, label) for a lesson file."""
    if not path or not os.path.exists(path):
        return "❌", "badge-missing", "找不到文件"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    length = len(content)
    if length > 800:
        return "✅", "badge-full", f"{length} 字"
    elif length > 200:
        return "⚠️", "badge-short", f"{length} 字（待補充）"
    else:
        return "📄", "badge-placeholder", "佔位文件"


def get_architect_insight(path: str) -> dict:
    """Extract cognitive level and assessment from the note."""
    if not os.path.exists(path):
        return {"level": "unknown", "badge": "❓", "class": "badge-unknown", "snippet": ""}

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    structure_words = ["結構", "制度", "系統", "框架", "門戶", "地基", "本質"]
    tool_words = ["按鈕", "工具", "功能", "教學", "操作", "設定", "手機"]

    s_count = sum(content.count(w) for w in structure_words)
    t_count = sum(content.count(w) for w in tool_words)

    level = "structure" if s_count > t_count else "tool"
    badge = "🏗️" if level == "structure" else "🔧"
    cls = "badge-structure" if level == "structure" else "badge-tool"
    label = "架構思維" if level == "structure" else "工具思維"

    diag_match = re.search(r"#### 1. 結構偏移點 (.*?)(?=\n####|$)", content, re.DOTALL)
    snippet = diag_match.group(1).split("\n- ")[1].split("：")[0] if diag_match and "\n- " in diag_match.group(1) else ""

    return {"level": level, "badge": badge, "class": cls, "label": label, "snippet": snippet}


def inject_badges(html: str) -> str:
    """Inject quality AND architect badges after lesson links."""
    def replace_link(m):
        full_tag = m.group(0)
        href = m.group(1)
        if (
            "cache/Lesson_" not in href
            and "teaching/Lesson_" not in href
            and "01.Docs/teaching" not in href
            and "StudentCRM/cache/Lesson_" not in href
        ):
            return full_tag
        path_match = re.search(r'path=([^\s"&]+)', href)
        if not path_match:
            return full_tag
        path = path_match.group(1)

        # 質量標籤
        q_emoji, q_cls, q_label = get_note_quality(path)
        q_html = f'<span class="note-badge {q_cls}" title="{q_label}">{q_emoji}</span>'

        # 架構師見解標籤
        insight = get_architect_insight(path)
        i_html = f'<span class="insight-badge {insight["class"]}" title="{insight["label"]}">{insight["badge"]} {insight["label"]}</span>'

        return f"{full_tag} {q_html} {i_html}"

    return re.sub(r'<a href="([^"]+)">[^<]+</a>', replace_link, html)


def render_cloud_student_timeline(student: dict, teaching_records: list[dict]) -> str:
    rows = []
    for record in teaching_records[:20]:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        focus = raw.get("focus") or raw.get("transcript") or ""
        rows.append(
            "<tr>"
            f"<td>{html_lib.escape(str(record.get('date') or '未記錄'))}</td>"
            f"<td>{html_lib.escape(str(record.get('lesson_num') or ''))}</td>"
            f"<td>{html_lib.escape(str(record.get('title') or '教學紀錄'))}</td>"
            f"<td>{html_lib.escape(str(focus[:80]))}</td>"
            "</tr>"
        )

    table_body = "\n".join(rows)
    if not table_body:
        table_body = '<tr><td colspan="4">尚未在雲端資料庫找到課後紀錄；目前先顯示學員摘要。</td></tr>'

    tags = "、".join(student.get("tags", [])) if isinstance(student.get("tags"), list) else ""
    latest_date = html_lib.escape(str(student.get("latest_date") or "未記錄"))
    next_lesson = html_lib.escape(str(student.get("next_lesson") or "尚未安排"))
    lessons_count = html_lib.escape(str(student.get("lessons_count", 0)))
    recurring_schedule = html_lib.escape(str(student.get("recurring_schedule") or "未設定"))
    tag_label = html_lib.escape(tags or "無")
    return f"""
    <section>
        <p><strong>雲端摘要模式</strong>：雲端部署未包含本地時光軸檔案，目前改由雲端資料庫顯示。</p>
        <table>
            <tbody>
                <tr><th>最近上課</th><td>{latest_date}</td></tr>
                <tr><th>下次上課</th><td>{next_lesson}</td></tr>
                <tr><th>累計堂數</th><td>{lessons_count}</td></tr>
                <tr><th>固定排程</th><td>{recurring_schedule}</td></tr>
                <tr><th>標籤</th><td>{tag_label}</td></tr>
            </tbody>
        </table>
    </section>
    <section>
        <h3>雲端課後紀錄</h3>
        <table>
            <thead>
                <tr><th>日期</th><th>堂數</th><th>標題</th><th>重點</th></tr>
            </thead>
            <tbody>{table_body}</tbody>
        </table>
    </section>
    """


def build_cloud_student_meta(student: dict) -> dict:
    latest = student.get("latest_date") or student.get("last_lesson_date") or "未記錄"
    return {
        "hardware": [],
        "first_lesson_date": student.get("first_lesson_date") or "未記錄",
        "lessons_count": student.get("lessons_count", 0),
        "last_lesson_date": latest,
        "latest_date": latest,
    }


def get_student_teaching_notes(
    student: dict,
    base_dir: str = "",
    app_dir: str = "",
    apple_program_loader: Callable | None = None,
    local_notes_loader: Callable | None = None,
    cloud_notes_loader: Callable | None = None,
) -> list[dict]:
    """取得特定學員的所有教學筆記（委託 hub_service 深模組進行多來源去重合併）。"""
    from digital_management_service import (
        load_local_digital_management_notes,
        load_cloud_digital_management_notes,
    )

    effective_base = base_dir or BASE_DIR
    effective_app = app_dir or APP_DIR

    if apple_program_loader is None:
        from data_gateway import StudentDataGateway
        apple_program_loader = lambda: StudentDataGateway(effective_base).load_apple_ceo_program()

    if local_notes_loader is None:
        local_notes_loader = lambda: load_local_digital_management_notes(base_dir=effective_base)

    if cloud_notes_loader is None:
        cloud_notes_loader = lambda: load_cloud_digital_management_notes()

    return service_get_student_teaching_notes(
        student,
        base_dir=effective_base,
        app_dir=effective_app,
        apple_program_loader=apple_program_loader,
        local_notes_loader=local_notes_loader,
        cloud_notes_loader=cloud_notes_loader,
    )


def get_student_lesson_paths(
    student_id: str,
    students: list[dict] | None = None,
    base_dir: str = "",
) -> list:
    """Get sorted lesson cache and teaching paths for a student."""
    effective_base = base_dir or BASE_DIR
    if students is None:
        from data_gateway import StudentDataGateway
        students = StudentDataGateway(effective_base).load_students()

    student = next((s for s in students if s["id"] == student_id), None)
    if not student:
        return []
    student_notes = get_student_teaching_notes(student, base_dir=effective_base)
    return service_get_student_lesson_paths(student, effective_base, student_notes)


def student_id_from_path(path: str, students: list[dict] | None = None) -> str:
    """Derive student_id from a lesson cache filename or teaching note path."""
    fname = os.path.basename(path)
    m = re.match(r"Lesson_\d{8}_(.+)\.md", fname)
    if students is None:
        from data_gateway import StudentDataGateway
        students = StudentDataGateway(BASE_DIR).load_students()

    if m:
        student_name = m.group(1)
        for s in students:
            if s["name"] == student_name or s["id"] == student_name.lower():
                return s["id"]
            if student_name in s.get("aliases", []):
                return s["id"]
        return student_name.lower()

    rec = parse_teaching_file(path)
    if rec and rec.get("student_name"):
        student, _ = resolve_student(rec["student_name"], students)
        if student:
            return student.get("id", "")
    return ""


def analyze_student_features(
    student_id: str,
    use_cache: bool = True,
    target_student: dict | None = None,
    students: list[dict] | None = None,
    base_dir: str = "",
) -> dict:
    """Extract features from student's historical data for AI prediction."""
    effective_base = base_dir or BASE_DIR
    if target_student is not None:
        student = target_student
    else:
        if students is None:
            from data_gateway import StudentDataGateway
            students = StudentDataGateway(effective_base).load_students()
        student = next((s for s in students if s.get("id") == student_id), None)

    if not student:
        return {
            "days_since_last_lesson": -1,
            "average_word_count": 0,
            "lessons_reviewed": 0,
        }
    student_notes = get_student_teaching_notes(student, base_dir=effective_base)
    return service_analyze_student_features(student, effective_base, student_notes, use_cache=use_cache)
