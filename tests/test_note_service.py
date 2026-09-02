import pytest
from note_service import (
    clean_markdown_frontmatter,
    extract_note_preview,
    get_note_quality,
    get_architect_insight,
    resolve_note_detail,
    NoteDetail,
)


class TestNoteServiceUtils:
    def test_clean_markdown_frontmatter(self):
        raw = "---\ntitle: test\ndate: 2026-08-01\n---\n# Main Content\nHello World"
        cleaned = clean_markdown_frontmatter(raw)
        assert cleaned.strip() == "# Main Content\nHello World"

    def test_clean_markdown_no_frontmatter(self):
        raw = "# Just Content\nParagraph"
        assert clean_markdown_frontmatter(raw) == raw

    def test_extract_note_preview(self):
        raw = "---\nmeta: val\n---\n# Title\nThis is a teaching note discussing AI workflows and prompt engineering."
        preview = extract_note_preview(raw, limit=50)
        assert "This is a teaching note" in preview
        assert "---" not in preview
        assert "# Title" not in preview

    def test_get_note_quality_from_content(self):
        short = "a" * 100
        emoji, cls, label = get_note_quality("", content=short)
        assert emoji == "📄"
        assert cls == "badge-placeholder"

        medium = "a" * 300
        emoji, cls, label = get_note_quality("", content=medium)
        assert emoji == "⚠️"
        assert cls == "badge-short"

        long_content = "a" * 1000
        emoji, cls, label = get_note_quality("", content=long_content)
        assert emoji == "✅"
        assert cls == "badge-full"


class TestNoteDetailResolver:
    def test_resolve_apple_ceo_note(self):
        apple_notes = [
            {
                "date": "2026-08-06",
                "title": "1358.蘋果總裁班@小樹屋",
                "filename": "20260806 1358.蘋果總裁班@小樹屋.md",
                "path": "/01.Docs/teaching/20260806 1358.蘋果總裁班@小樹屋.md",
                "content": "# 1358.蘋果總裁班\n上課記錄內容",
            },
            {
                "date": "2026-08-13",
                "title": "1359.蘋果總裁班",
                "filename": "20260813 1359.蘋果總裁班.md",
                "path": "/01.Docs/teaching/20260813 1359.蘋果總裁班.md",
                "content": "# 1359.蘋果總裁班\n最新課堂內容",
            },
        ]

        note = resolve_note_detail(
            path_or_filename="/01.Docs/teaching/20260813 1359.蘋果總裁班.md",
            base_dir="/tmp/test",
            apple_notes=apple_notes,
            cloud_records=[],
        )

        assert isinstance(note, NoteDetail)
        assert note.note_title == "1359.蘋果總裁班"
        assert note.is_apple_ceo is True
        assert note.lesson_label == "蘋果總裁班"
        assert "最新課堂內容" in note.content_html
        # 驗證上一篇自動串接 (2026-08-06)
        assert note.prev_path == "/01.Docs/teaching/20260806 1358.蘋果總裁班@小樹屋.md"
        assert note.prev_label == "2026-08-06"
        assert note.next_path is None

    def test_resolve_cloud_teaching_record(self):
        cloud_records = [
            {
                "path": "/01.Docs/teaching/20260501 01-1.測試學員數位管理教學.md",
                "filename": "20260501 01-1.測試學員數位管理教學.md",
                "title": "測試學員第一堂",
                "date": "2026-05-01",
                "lesson_number": 1,
                "lesson_sub": 1,
                "student_name": "測試學員",
                "student_id": "test-student-id",
                "content": "# 測試第一堂筆記\n學員進度順暢",
            }
        ]

        note = resolve_note_detail(
            path_or_filename="20260501 01-1.測試學員數位管理教學.md",
            base_dir="/tmp/test",
            apple_notes=[],
            cloud_records=cloud_records,
        )

        assert isinstance(note, NoteDetail)
        assert note.student_name == "測試學員"
        assert note.lesson_label == "第 1-1 堂"
        assert "學員進度順暢" in note.content_html
        assert note.is_apple_ceo is False

    def test_resolve_non_existent_note_returns_none(self):
        note = resolve_note_detail(
            path_or_filename="non_existent_file.md",
            base_dir="/tmp/test",
            apple_notes=[],
            cloud_records=[],
        )
        assert note is None
