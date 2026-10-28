import pytest
from search_service import SearchService, SearchResult


def test_search_service_empty_query():
    service = SearchService()
    res = service.search("")
    assert isinstance(res, SearchResult)
    assert res.q == ""
    assert res.count == 0
    assert len(res.results) == 0
    assert len(res.matched_students) == 0


def test_search_service_matches_student_and_aliases():
    mock_students = [
        {"id": "sid-1", "name": "Anna 蕭", "aliases": ["Anna", "小安妮"], "tags": ["總裁班"]},
        {"id": "sid-2", "name": "Amanda 蕭秉慧", "aliases": ["Amanda", "蕭秉慧"], "tags": ["數位管理"]},
    ]
    service = SearchService(
        students_loader=lambda: mock_students,
        teaching_records_loader=lambda: [],
        apple_notes_loader=lambda: [],
    )

    # 搜尋別名「小安妮」
    res = service.search("小安妮")
    assert res.count == 0  # 無筆記
    assert len(res.matched_students) == 1
    assert res.matched_students[0]["name"] == "Anna 蕭"

    # 搜尋別名「蕭秉慧」
    res2 = service.search("蕭秉慧")
    assert len(res2.matched_students) == 1
    assert res2.matched_students[0]["name"] == "Amanda 蕭秉慧"


def test_search_service_matches_content_and_extracts_snippet():
    mock_students = [
        {"id": "sid-1", "name": "張素幸", "aliases": []},
    ]
    mock_records = [
        {
            "title": "20261019 20-4.張素幸數位管理教學",
            "student_name": "張素幸",
            "student_id": "sid-1",
            "date": "2026-10-19",
            "content": "# 課堂標題\n今天教了星巴克隨行卡在手機上的綁定技巧。\n其他備註文字",
            "path": "01.Docs/teaching/20261019 20-4.張素幸數位管理教學.md",
        }
    ]
    service = SearchService(
        students_loader=lambda: mock_students,
        teaching_records_loader=lambda: mock_records,
        apple_notes_loader=lambda: [],
    )

    res = service.search("星巴克")
    assert res.count == 1
    hit = res.results[0]
    assert hit["student_name"] == "張素幸"
    assert hit["student_id"] == "sid-1"
    assert "今天教了星巴克隨行卡" in hit["preview"]


def test_search_service_disambiguates_amanda_and_anna():
    mock_students = [
        {"id": "anna-id", "name": "Anna 蕭", "aliases": ["Anna"]},
        {"id": "amanda-id", "name": "Amanda 蕭秉慧", "aliases": ["Amanda", "蕭秉慧"]},
    ]
    # 模擬以前歷史遺留的錯誤 id (誤植為 Anna 的 id)
    mock_records = [
        {
            "title": "Amanda 蕭秉慧數位管理教學",
            "student_name": "Amanda 蕭秉慧",
            "student_id": "anna-id",  # 誤植
            "date": "2026-10-01",
            "content": "數位工作流教案",
            "path": "teaching/amanda.md",
        }
    ]
    service = SearchService(
        students_loader=lambda: mock_students,
        teaching_records_loader=lambda: mock_records,
        apple_notes_loader=lambda: [],
    )

    res = service.search("數位工作流")
    assert res.count == 1
    # 必須精準消歧義校正回 amanda-id
    assert res.results[0]["student_id"] == "amanda-id"

