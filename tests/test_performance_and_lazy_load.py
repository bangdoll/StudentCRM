import os
import time
from pathlib import Path
from media_asset_resolver import get_media_resolver
from student_profile_assembler import StudentProfileAssembler, clear_timeline_cache


def test_media_asset_resolver_injects_lazy_loading():
    resolver = get_media_resolver()
    html_input = '<p>課堂截圖：<img src="/static/teaching_assets/board.png" alt="板書"></p>'
    html_output = resolver.inject_lazy_loading(html_input)
    
    assert 'loading="lazy"' in html_output
    assert 'decoding="async"' in html_output
    assert 'alt="板書"' in html_output
    
    # 測試若原本已有 loading="eager"，不重複破壞
    html_custom = '<img src="/logo.svg" loading="eager">'
    assert resolver.inject_lazy_loading(html_custom) == html_custom


def test_student_profile_assembler_timeline_caching(tmp_path):
    clear_timeline_cache()
    mock_file = tmp_path / "student_notes.md"
    mock_file.write_text("## 📅 教學時間軸 (Lesson Timeline)\n\n### 2026-10-01 第1堂\n內容文字", encoding="utf-8")
    
    mock_gateway = type("MockGateway", (), {
        "get_student_profile": lambda self, sid: {
            "id": sid, "name": "測試學員", "file": str(mock_file),
            "current_cycle_lesson": 1, "cycle_size": 8
        },
        "load_students": lambda self: [{"id": "s1", "name": "測試學員"}],
        "load_teaching_records": lambda self, sid: [],
    })()
    
    assembler = StudentProfileAssembler(
        data_gateway=mock_gateway,
        base_dir=str(tmp_path),
        teaching_notes_loader=lambda s: [],
    )
    
    # 第 1 次組裝：冷啟動
    ctx1 = assembler.assemble_student_view_context("s1")
    assert ctx1 is not None
    assert "2026-10-01" in ctx1["timeline_html"]
    
    # 第 2 次組裝：快取命中
    ctx2 = assembler.assemble_student_view_context("s1")
    assert ctx2 is not None
    assert ctx2["timeline_html"] == ctx1["timeline_html"]
    
    # 修改檔案 mtime，快取自動失效重建
    time.sleep(0.01)
    mock_file.write_text("## 📅 教學時間軸 (Lesson Timeline)\n\n### 2026-10-02 第2堂\n新內容", encoding="utf-8")
    ctx3 = assembler.assemble_student_view_context("s1")
    assert ctx3 is not None
    assert "2026-10-02" in ctx3["timeline_html"]


def test_html_templates_contain_font_preconnect():
    templates_dir = Path("templates")
    targets = ["student.html", "hub.html", "note.html"]
    
    for tpl_name in targets:
        tpl_path = templates_dir / tpl_name
        if tpl_path.exists():
            content = tpl_path.read_text(encoding="utf-8")
            assert 'rel="preconnect" href="https://fonts.googleapis.com"' in content, f"{tpl_name} 缺少 fonts.googleapis.com preconnect"
            assert 'rel="preconnect" href="https://fonts.gstatic.com"' in content, f"{tpl_name} 缺少 fonts.gstatic.com preconnect"


def test_note_service_detail_caching(tmp_path):
    from note_service import resolve_note_detail, clear_note_detail_cache
    clear_note_detail_cache()

    note_file = tmp_path / "test_note.md"
    note_file.write_text("# 課堂重點\n第一版內容", encoding="utf-8")

    detail1 = resolve_note_detail(str(note_file), base_dir=str(tmp_path))
    assert detail1 is not None
    assert "第一版內容" in detail1.content_html

    # 第 2 次解析命中快取
    detail2 = resolve_note_detail(str(note_file), base_dir=str(tmp_path))
    assert detail2 is not None
    assert detail1 is detail2

    # 檔案更新時自動失效
    time.sleep(0.01)
    note_file.write_text("# 課堂重點\n第二版更新內容", encoding="utf-8")
    detail3 = resolve_note_detail(str(note_file), base_dir=str(tmp_path))
    assert detail3 is not None
    assert "第二版更新內容" in detail3.content_html
