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
    assert 'img-has-shimmer' in html_output
    assert 'img-lazy-fade' in html_output
    assert "onload=\"this.classList.add('img-loaded')\"" in html_output
    
    # 測試若原本已有 loading="eager"，不重複破壞
    html_custom = '<img src="/logo.svg" loading="eager">'
    eager_output = resolver.inject_lazy_loading(html_custom)
    assert eager_output.count('loading="eager"') == 1
    assert 'loading="lazy"' not in eager_output
    assert 'src="/logo.svg"' in eager_output
    assert 'onerror=' in eager_output  # main retains the image recovery enhancement.


def test_instant_prefetch_script_integrity():
    js_path = Path("static/instant-prefetch.js")
    assert js_path.exists()
    content = js_path.read_text(encoding="utf-8")
    assert "prefetchUrl" in content
    assert "initLinkPrefetching" in content
    assert "initImageEnhancements" in content
    assert "touchstart" in content
    assert "mouseover" in content


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


def test_static_files_cache_control_headers():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/static/instant-prefetch.js")
    assert resp.status_code == 200
    cache_control = resp.headers.get("Cache-Control", "")
    assert "public" in cache_control
    assert "max-age=" in cache_control


def test_cloud_digital_management_notes_effective_cache_writeback():
    from digital_management_service import load_cloud_digital_management_notes
    mock_gateway = type("MockGateway", (), {
        "backend": "local",
        "load_all_teaching_records": lambda self: [
            {"student_id": "test_sid", "student_name": "測試", "date": "2026-10-28", "title": "測試"}
        ]
    })()
    custom_cache = {"timestamp": 0.0, "notes": []}
    notes = load_cloud_digital_management_notes(data_gateway=mock_gateway, cache_container=custom_cache)
    assert len(notes) == 1
    # 驗證傳入的 custom_cache 有被正確更新寫回
    assert custom_cache["notes"] == notes
    assert custom_cache["timestamp"] > 0


def test_digital_management_profiles_caching():
    from digital_management_service import (
        build_digital_management_profiles,
        clear_digital_management_profiles_cache,
    )
    clear_digital_management_profiles_cache()

    p1 = build_digital_management_profiles(include_heptabase=False)
    assert "students" in p1

    # 第 2 次調用應直接命中短效記憶體快取
    p2 = build_digital_management_profiles(include_heptabase=False)
    assert p1 == p2


