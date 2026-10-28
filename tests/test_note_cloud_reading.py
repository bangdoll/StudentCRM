"""Cloud-index -> real Hub link -> note body; all data is synthetic/offline."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

import digital_management_service
from digital_management_service import load_cloud_digital_management_notes
from hub_service import get_student_teaching_notes
from routers import hub, student

RECORD_ID = "11111111-1111-4111-8111-111111111111"
STUDENT = {"id": "sample-student", "name": "驗收學員", "lessons_count": 1}
FILENAME = "20261028 01.驗收學員數位管理教學.md"
BODY = "# 本機測試課堂\n\n這是必須讀回的完整正文，不是清單標題或摘要。"

class NoteLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href", "")
        if tag == "a" and href.startswith("/note?"):
            self.links.append(href)

@pytest.fixture
def cloud_reader(monkeypatch, tmp_path):
    # Existing normalizer writes the module cache even with an injected container.
    # Keep synthetic notes isolated from the rest of the regression suite.
    monkeypatch.setattr(digital_management_service, "_CLOUD_NOTES_CACHE", {"timestamp": 0.0, "notes": []})
    row = {"id": RECORD_ID, "student_id": STUDENT["id"], "student_name": STUDENT["name"],
           "title": FILENAME[:-3], "date": "2026-10-28", "lesson_num": 1}
    detail = {**row, "raw": {"path": "/01.Docs/teaching/" + FILENAME,
                             "filename": FILENAME, "content": BODY}}
    gateway = Mock()
    gateway.load_all_teaching_records.return_value = [row]
    gateway.load_teaching_record_detail.side_effect = lambda identifier: detail if identifier == RECORD_ID else None
    notes = load_cloud_digital_management_notes(data_gateway=gateway, cache_container={})
    templates = Jinja2Templates(directory=str(Path(__file__).parents[1] / "templates"))
    deps = {"templates": templates, "load_students": lambda: [STUDENT],
            "get_student_by_id": lambda identifier, students: STUDENT if identifier == STUDENT["id"] else None,
            "resolve_student_access_id": lambda token, students: token,
            "is_valid_student_access_key": lambda token, student: token == STUDENT["id"],
            "get_merged_redirects": lambda: {}, "load_apple_ceo_program": lambda: {},
            "get_student_teaching_notes": lambda student: get_student_teaching_notes(
                student, local_notes_loader=lambda: [], cloud_notes_loader=lambda: notes),
            "load_cloud_digital_management_notes": lambda: notes,
            "student_gateway": gateway, "BASE_DIR": str(tmp_path), "APP_DIR": str(tmp_path)}
    monkeypatch.setattr(hub, "get_hub_deps", lambda: deps)
    monkeypatch.setattr(student, "get_student_deps", lambda: deps)
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parents[1] / "static")), name="static")
    app.include_router(hub.router)
    app.include_router(student.router)
    return TestClient(app), gateway, notes


def test_hub_cloud_index_link_reads_full_note(cloud_reader):
    client, gateway, notes = cloud_reader
    hub_page = client.get("/hub/" + STUDENT["id"])
    assert hub_page.status_code == 200
    parser = NoteLinks()
    parser.feed(hub_page.text)
    assert parser.links, "Hub must expose an existing lesson link"
    gateway.load_teaching_record_detail.assert_not_called()
    response = client.get(parser.links[0])
    assert response.status_code == 200, "Existing Hub lesson must not return 404"
    assert "這是必須讀回的完整正文" in response.text
    gateway.load_teaching_record_detail.assert_called_once_with(RECORD_ID)


def test_cloud_profile_note_url_uses_stable_id(cloud_reader):
    client, gateway, notes = cloud_reader
    assert parse_qs(urlsplit(notes[0]["url"]).query)["path"] == [RECORD_ID]
    response = client.get(notes[0]["url"])
    assert response.status_code == 200
    assert "這是必須讀回的完整正文" in response.text
    gateway.load_teaching_record_detail.assert_called_once_with(RECORD_ID)


@pytest.mark.parametrize("route", ["/note", "/open_file"])
@pytest.mark.parametrize("identifier", [FILENAME, "/01.Docs/teaching/" + FILENAME])
def test_legacy_note_links_still_read_only_the_selected_body(cloud_reader, route, identifier):
    client, gateway, notes = cloud_reader
    notes[0].update(path="/01.Docs/teaching/" + FILENAME, filename=FILENAME)
    response = client.get(route, params={"path": identifier})
    assert response.status_code == 200
    assert "這是必須讀回的完整正文" in response.text
    gateway.load_teaching_record_detail.assert_called_once_with(RECORD_ID)


@pytest.mark.parametrize("identifier", ["", "missing.md", "../missing.md"])
def test_invalid_note_references_keep_404_without_detail_reads(cloud_reader, identifier):
    client, gateway, notes = cloud_reader
    response = client.get("/note", params={"path": identifier})
    assert response.status_code == 404
    gateway.load_teaching_record_detail.assert_not_called()


def test_local_note_keeps_zero_cloud_detail_reads(tmp_path):
    from note_service import resolve_note_detail
    path = tmp_path / FILENAME
    path.write_text(BODY)
    loader = Mock(side_effect=AssertionError("Local notes must not fetch cloud detail"))
    note = resolve_note_detail(str(path), str(tmp_path),
                               cloud_records=[{"id": RECORD_ID, "path": str(path)}],
                               record_detail_loader=loader)
    assert note is not None
    assert "這是必須讀回的完整正文" in note.content_html
    loader.assert_not_called()


def test_cloud_note_navigation_keeps_stable_refs_without_loading_other_bodies(tmp_path):
    from note_service import resolve_note_detail
    rows = [{"id": RECORD_ID, "student_id": STUDENT["id"], "date": "2026-10-28"},
            {"id": "22222222-2222-4222-8222-222222222222", "student_id": STUDENT["id"], "date": "2026-10-29"}]
    loader = Mock(return_value={"id": RECORD_ID, "raw": {"content": BODY, "path": "/old/path.md"}})
    note = resolve_note_detail(RECORD_ID, str(tmp_path), cloud_records=rows, record_detail_loader=loader)
    assert note is not None
    assert note.prev_path is None
    assert note.next_path == rows[1]["id"]
    assert note.student_id == STUDENT["id"]
    loader.assert_called_once_with(RECORD_ID)
