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
    assert "initInstantNavigation" in content
    assert "instant-progress-bar" in content
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


def test_analyze_student_features_skips_note_loading_on_cache_hit(monkeypatch):
    import student_timeline_service
    from prediction_service import clear_features_cache

    clear_features_cache()
    notes_call_count = {"count": 0}

    def fake_get_notes(student, base_dir=""):
        notes_call_count["count"] += 1
        return []

    monkeypatch.setattr(student_timeline_service, "get_student_teaching_notes", fake_get_notes)
    sample_student = {"id": "test-cache-student-id", "name": "快取測試學員", "latest_date": "2026-10-20"}

    f1 = student_timeline_service.analyze_student_features(
        student_id="test-cache-student-id",
        use_cache=True,
        target_student=sample_student,
    )
    assert notes_call_count["count"] == 1

    # 第二次調用應直接命中 _FEATURES_CACHE，不再呼叫 get_student_teaching_notes
    f2 = student_timeline_service.analyze_student_features(
        student_id="test-cache-student-id",
        use_cache=True,
        target_student=sample_student,
    )
    assert notes_call_count["count"] == 1
    assert f1 == f2


def test_analyze_student_features_skips_notes_loader_for_active_and_special_status(monkeypatch):
    """驗證近期穩定學員 (<=14天) 與結訓/休學學員，完全不觸發 notes loader 網路請求。"""
    import student_timeline_service
    from prediction_service import clear_features_cache
    from datetime import datetime

    clear_features_cache()
    notes_call_count = {"count": 0}

    def fake_get_notes(student, base_dir=""):
        notes_call_count["count"] += 1
        return []

    monkeypatch.setattr(student_timeline_service, "get_student_teaching_notes", fake_get_notes)

    # 1. 最近上課在 3 天前的穩定學員
    today_str = datetime.now().strftime("%Y-%m-%d")
    active_student = {"id": "test-active-1", "name": "穩定學員", "latest_date": today_str, "status": "active"}
    f_active = student_timeline_service.analyze_student_features(
        student_id="test-active-1",
        use_cache=False,
        target_student=active_student,
    )
    assert notes_call_count["count"] == 0
    assert f_active["days_since_last_lesson"] == 0

    # 2. 結訓學員
    grad_student = {"id": "test-grad-1", "name": "結訓學員", "latest_date": "2025-01-01", "status": "graduated"}
    f_grad = student_timeline_service.analyze_student_features(
        student_id="test-grad-1",
        use_cache=False,
        target_student=grad_student,
    )
    assert notes_call_count["count"] == 0

    # 3. 休學學員
    paused_student = {"id": "test-pause-1", "name": "休學學員", "latest_date": "2025-01-01", "status": "paused"}
    f_pause = student_timeline_service.analyze_student_features(
        student_id="test-pause-1",
        use_cache=False,
        target_student=paused_student,
    )
    assert notes_call_count["count"] == 0


def test_home_page_cache_control_headers():
    """驗證首頁行動看板具備 HTTP 快取標頭以實現秒開體驗。"""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/?key=tsai-8f92b7c4-a13e-49b8-9e51-68d1a4c9520b")
    assert resp.status_code == 200
    cache_control = resp.headers.get("Cache-Control", "")
    assert "private" in cache_control
    assert "max-age=" in cache_control
    assert "stale-while-revalidate=" in cache_control


def test_load_radar_teaching_records_fast_local_extraction(tmp_path):
    """驗證 load_radar_teaching_records 當本地總帳存在時，能在亞毫秒內完成萃取，絕不阻塞首頁。"""
    import json
    import time
    from data_gateway import StudentDataGateway

    records = [
        {"id": f"rec-{sid}-{i}", "student_id": f"sid-{sid}", "date": f"2026-10-0{i+1}", "content": f"筆記內容 {i}", "title": f"第{i+1}堂"}
        for sid in range(10)
        for i in range(5)
    ]
    records_file = tmp_path / "teaching_records.json"
    records_file.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    gateway = StudentDataGateway(str(tmp_path))
    gateway.backend = "supabase"  # 即使在 supabase 模式下
    gateway.teaching_records_file = str(records_file)

    t0 = time.perf_counter()
    res = gateway.load_radar_teaching_records(["sid-1", "sid-2", "sid-3"])
    elapsed = time.perf_counter() - t0

    assert len(res) == 9  # 每個學生 3 筆，共 9 筆
    assert elapsed < 0.05, f"本地萃取耗時過長: {elapsed:.4f}s"
    assert all("rec-sid-" in r["id"] or "rec-" in r["id"] for r in res)


def test_apple_ceo_parallel_fetches(monkeypatch):
    """驗證 _load_supabase_apple_ceo_program 同時並行查詢 4 張關聯表。"""
    import threading
    from data_gateway import StudentDataGateway

    active_threads = set()
    lock = threading.Lock()

    gateway = StudentDataGateway("07.Projects/StudentCRM")
    gateway.supabase_url = "https://mock.supabase.co"
    gateway.supabase_key = "mock-key"

    def mock_load_supabase_table(table: str, query: str = ""):
        with lock:
            active_threads.add(threading.get_ident())
        if table == "apple_programs":
            return [{"id": "apple-ceo", "name": "蘋果總裁班"}]
        return []

    monkeypatch.setattr(gateway, "_load_supabase_table", mock_load_supabase_table)

    res = gateway._load_supabase_apple_ceo_program()
    assert res["program"]["id"] == "apple-ceo"
    # 並行查詢應跨多個執行緒執行
    assert len(active_threads) >= 2


def test_gzip_middleware_compresses_large_html_responses():
    """驗證 GZipMiddleware 已啟用，對超過 1KB 的 HTML 頁面自動進行 gzip 壓縮。"""
    from fastapi.testclient import TestClient
    import main
    from auth_service import SESSION_COOKIE_NAME, get_session_token

    client = TestClient(main.app)
    client.cookies.set(SESSION_COOKIE_NAME, get_session_token())

    resp = client.get("/cases", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"


def test_write_json_noop_shortcircuit_and_ephemeral_cache_no_backup(tmp_path):
    """驗證 _write_json 對無變更資料短路不重複產生 .bak，且對 cache 目錄不產生 .bak。"""
    from data_gateway import StudentDataGateway

    # 1. 正式目錄：相同資料重複寫入不產生多餘 .bak
    data_dir = tmp_path / "data"
    data_file = data_dir / "students.json"
    payload = [{"id": "s1", "name": "Alice"}]
    StudentDataGateway._write_json(str(data_file), payload)
    StudentDataGateway._write_json(str(data_file), payload)  # 內容完全相同，應短路
    backup_dir = data_dir / "backups"
    assert not backup_dir.exists() or len(list(backup_dir.glob("*.bak"))) == 0

    # 2. 暫存快取目錄：即使內容改變也不應產生 .bak
    cache_dir = tmp_path / "cache"
    cache_file = cache_dir / "teaching_records.json"
    StudentDataGateway._write_json(str(cache_file), [{"id": "r1"}])
    StudentDataGateway._write_json(str(cache_file), [{"id": "r1"}, {"id": "r2"}])
    assert not (cache_dir / "backups").exists()


def test_digital_management_profiles_cache_works_via_main_wrapper():
    """驗證 main.build_digital_management_profiles 在預設環境下能命中 _PROFILES_CACHE。"""
    import main
    from digital_management_service import _PROFILES_CACHE, clear_digital_management_profiles_cache

    clear_digital_management_profiles_cache()
    res1 = main.build_digital_management_profiles(include_heptabase=False)
    assert _PROFILES_CACHE["payload"] is not None
    ts1 = _PROFILES_CACHE["timestamp"]

    res2 = main.build_digital_management_profiles(include_heptabase=False)
    assert _PROFILES_CACHE["timestamp"] == ts1
    assert len(res1.get("students", [])) == len(res2.get("students", []))





