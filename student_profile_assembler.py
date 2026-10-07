"""學員個人檔案視圖模型聚合深模組 (StudentProfileAssembler)。

依據 Matt Pocock 代碼庫設計與 John Ousterhout 深模組原則設計：
將原本散落於 routers/student.py 的排程計算、檔案/雲端元資料合併、
AI 狀態預測、課前備課簡報生成、續約提醒與 Markdown 時間軸轉譯完全封裝於單一深模組。
HTTP 路由控制器只需調用單一方法即可獲得完全組裝好的視圖模型上下文。
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)


_TIMELINE_CACHE: dict[str, tuple[float, str]] = {}


def clear_timeline_cache() -> None:
    """清除時間軸渲染 HTML 記憶體快取。"""
    _TIMELINE_CACHE.clear()


class StudentProfileAssembler:
    """學員個人檔案視圖模型聚合器。"""

    def __init__(
        self,
        data_gateway: Any,
        base_dir: str,
        teaching_notes_loader: Callable[[dict], list[dict]] | None = None,
        features_analyzer: Callable[[str], dict] | None = None,
        status_predictor: Callable[[dict, str | None], Any] | None = None,
        renewal_generator: Callable[[dict], str] | None = None,
        briefing_generator: Callable[[dict, list[dict]], str] | None = None,
        timeline_renderer: Callable[[dict, list[dict]], str] | None = None,
        metadata_loader: Callable[[str], dict] | None = None,
        cloud_meta_builder: Callable[[dict], dict] | None = None,
        badges_injector: Callable[[str], str] | None = None,
    ) -> None:
        self.gateway = data_gateway
        self.base_dir = base_dir
        self.teaching_notes_loader = teaching_notes_loader
        self.features_analyzer = features_analyzer
        self.status_predictor = status_predictor
        self.renewal_generator = renewal_generator
        self.briefing_generator = briefing_generator
        self.timeline_renderer = timeline_renderer
        self.metadata_loader = metadata_loader
        self.cloud_meta_builder = cloud_meta_builder
        self.badges_injector = badges_injector

    def _resolve_deps(self) -> None:
        """懶加載未注入之默認服務函數，避免循環引用。"""
        if self.teaching_notes_loader is None:
            import main
            self.teaching_notes_loader = main.get_student_teaching_notes
        if self.features_analyzer is None:
            import main
            self.features_analyzer = main.analyze_student_features
        if self.status_predictor is None:
            from prediction_service import predict_student_status
            self.status_predictor = predict_student_status
        if self.renewal_generator is None:
            from student_service import generate_student_renewal_reminder
            self.renewal_generator = generate_student_renewal_reminder
        if self.briefing_generator is None:
            from student_service import generate_preclass_briefing
            self.briefing_generator = generate_preclass_briefing
        if self.timeline_renderer is None:
            import main
            self.timeline_renderer = main.render_cloud_student_timeline
        if self.metadata_loader is None:
            import main
            self.metadata_loader = main.get_student_metadata
        if self.cloud_meta_builder is None:
            import main
            self.cloud_meta_builder = main.build_cloud_student_meta
        if self.badges_injector is None:
            import main
            self.badges_injector = main.inject_badges

    def assemble_student_view_context(self, student_id: str) -> dict[str, Any] | None:
        """【單一法定入口】組裝單一學員主頁所需的完整渲染 Context。"""
        self._resolve_deps()

        student = self.gateway.get_student_profile(student_id)
        if not student:
            return None

        students = self.gateway.load_students()

        # 1. 檔案路徑與排程計算
        file_value = student.get("file") or ""
        if file_value and os.path.isabs(file_value) and os.path.exists(file_value):
            file_path = file_value
        else:
            file_path = os.path.join(self.base_dir, file_value.lstrip("/")) if file_value else ""

        if "recurring_schedule" in student and not student.get("next_lesson"):
            from schedule_service import get_document_exceptions, get_next_occurrence
            doc_exceptions = get_document_exceptions(file_path) if file_path else []
            json_exceptions = student.get("schedule_exceptions", [])
            all_exceptions = list(set(json_exceptions + doc_exceptions))

            student["next_lesson"] = get_next_occurrence(
                student["recurring_schedule"],
                all_exceptions,
            )

        # 2. 教學筆記與公開 Token
        student_notes = self.teaching_notes_loader(student) if self.teaching_notes_loader else []
        
        from student_service import get_public_student_slug
        hub_token = get_public_student_slug(student_id, students) or student_id

        # 3. 欄位補全與元資料合併
        file_meta = self.metadata_loader(file_path) if (self.metadata_loader and file_path and os.path.exists(file_path)) else {}
        cloud_meta = self.cloud_meta_builder(student) if self.cloud_meta_builder else {}
        student["meta"] = {**cloud_meta, **file_meta}

        if not student.get("current_cycle_lesson") and student["meta"].get("current_cycle_lesson"):
            student["current_cycle_lesson"] = student["meta"]["current_cycle_lesson"]
        if not student.get("cycle_size") and student["meta"].get("cycle_size"):
            student["cycle_size"] = student["meta"]["cycle_size"]

        if not student["meta"].get("first_lesson_date") or student["meta"]["first_lesson_date"] in ("未記錄", "TBD"):
            student["meta"]["first_lesson_date"] = student.get("first_lesson_date") or "未記錄"
        if not student["meta"].get("last_lesson_date") or student["meta"]["last_lesson_date"] in ("未記錄", "TBD"):
            student["meta"]["last_lesson_date"] = student.get("latest_date") or "未記錄"
        if not student["meta"].get("lessons_count") or student["meta"]["lessons_count"] == 0:
            student["meta"]["lessons_count"] = student.get("lessons_count") or len(student_notes)

        # 4. AI 診斷、預測與簡報生成
        student["features"] = self.features_analyzer(student_id) if self.features_analyzer else {}
        student["prediction"] = self.status_predictor(student["features"], student.get("next_lesson")) if self.status_predictor else None
        renewal_message = self.renewal_generator(student) if self.renewal_generator else ""
        briefing = self.briefing_generator(student, student_notes) if self.briefing_generator else ""

        # 5. 時間軸 HTML 渲染 (Markdown 轉譯或雲端紀錄渲染)
        timeline_html = ""
        if not file_path or not os.path.isfile(file_path):
            teaching_records = self.gateway.load_teaching_records(student_id)
            if self.timeline_renderer:
                timeline_html = self.timeline_renderer(student, teaching_records)
        else:
            try:
                mtime = os.path.getmtime(file_path)
                cached = _TIMELINE_CACHE.get(file_path)
                if cached and cached[0] == mtime:
                    timeline_html = cached[1]
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    parts = re.split(r"## 📅 教學時間軸 \(Lesson Timeline\)", content)
                    body = parts[1] if len(parts) > 1 else ""
                    body = body.replace("file://", "/open_file?path=")

                    from media_asset_resolver import get_media_resolver
                    resolver = get_media_resolver()
                    body = resolver.transform_markdown_media(body)

                    import markdown
                    raw_html = markdown.markdown(body, extensions=["tables"])
                    if self.badges_injector:
                        raw_html = self.badges_injector(raw_html)
                    
                    timeline_html = resolver.inject_lazy_loading(raw_html)
                    _TIMELINE_CACHE[file_path] = (mtime, timeline_html)
            except Exception as read_err:
                logger.warning("讀取學員時間軸 Markdown 失敗: %s", read_err)
                timeline_html = "<p class='muted'>時間軸讀取失敗</p>"

        return {
            "student": student,
            "student_notes": student_notes,
            "timeline_html": timeline_html,
            "student_id": student_id,
            "hub_token": hub_token,
            "renewal_message": renewal_message,
            "briefing": briefing,
        }
