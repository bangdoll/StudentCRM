"""
搜尋服務深模組 (search_service.py)
==================================
職責：依循 Matt Pocock 深模組原則設計，封裝全站教學紀錄、學員檔案、
別名標籤與總裁班筆記之全文搜尋、內文片斷提取、去重與實體消歧義。
消除原本散落於路由控制器的程序性代碼與 raw 資料解包洩漏。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID


def _is_cloud_uuid(value: Any) -> bool:
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


@dataclass
class SearchResult:
    """搜尋結果不可變視圖模型。"""
    q: str
    results: list[dict[str, Any]] = field(default_factory=list)
    matched_students: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    next_cursor: str | None = None

    def to_template_context(self) -> dict[str, Any]:
        """轉為模板渲染所需之標準鍵值上下文。"""
        return {
            "q": self.q,
            "results": self.results,
            "count": self.count,
            "matched_students": self.matched_students,
            "next_cursor": self.next_cursor,
        }


class SearchService:
    """全站搜尋深模組引擎。"""

    def __init__(
        self,
        students_loader: Callable[[], list[dict[str, Any]]] | None = None,
        teaching_records_loader: Callable[[], list[dict[str, Any]]] | None = None,
        apple_notes_loader: Callable[[], list[dict[str, Any]]] | None = None,
        data_gateway: Any = None,
    ) -> None:
        self._students_loader = students_loader
        self._teaching_records_loader = teaching_records_loader
        self._apple_notes_loader = apple_notes_loader
        self._data_gateway = data_gateway

    def _get_students(self) -> list[dict[str, Any]]:
        if self._students_loader is not None:
            return self._students_loader()
        import main
        return main.load_students()

    def _get_teaching_records(self) -> list[dict[str, Any]]:
        if self._teaching_records_loader is not None:
            return self._teaching_records_loader()
        import main
        return main.student_gateway.load_all_teaching_records()

    def _get_apple_notes(self) -> list[dict[str, Any]]:
        if self._apple_notes_loader is not None:
            return self._apple_notes_loader()
        import main
        apple_ceo = main.load_apple_ceo_program()
        if isinstance(apple_ceo, dict):
            return apple_ceo.get("teaching_notes", [])
        return []

    def search(self, query: str, cursor: str | None = None) -> SearchResult:
        """【單一法定入口】執行全站模糊搜尋。"""
        clean_q = (query or "").strip()
        if not clean_q:
            return SearchResult(q="")

        q_lower = clean_q.lower()
        students = self._get_students()
        name_to_sid: dict[str, str] = {}
        matched_students: list[dict[str, Any]] = []

        for s in students:
            sid = s.get("id", "")
            sname = s.get("name", "")
            if sname:
                name_to_sid[sname.lower()] = sid
            for alias in s.get("aliases", []):
                if alias:
                    name_to_sid[str(alias).lower()] = sid

            # 比對學員姓名、別名、標籤
            student_matched = False
            if q_lower in sname.lower():
                student_matched = True
            elif any(q_lower in str(alias).lower() for alias in s.get("aliases", [])):
                student_matched = True
            elif any(q_lower in str(tag).lower() for tag in s.get("tags", [])):
                student_matched = True

            if student_matched:
                matched_students.append(s)

        gateway = self._data_gateway
        if gateway is None:
            import main
            gateway = getattr(main, "student_gateway", None)

        next_cursor: str | None = None
        is_cloud = bool(gateway and getattr(gateway, "backend", "") == "supabase")

        if is_cloud and hasattr(gateway, "list_teaching_records"):
            target_ids = [s["id"] for s in matched_students if _is_cloud_uuid(s.get("id"))]
            page = gateway.list_teaching_records(query=clean_q, cursor=cursor, student_ids=target_ids)
            teaching_records = page.get("items", [])
            next_cursor = page.get("next_cursor")
        else:
            teaching_records = self._get_teaching_records()

        apple_notes = self._get_apple_notes()
        candidates: list[dict[str, Any]] = []

        # 1. 一對一教學筆記（消化 local JSON 與 Supabase raw 差異）
        for rec in teaching_records:
            if not isinstance(rec, dict):
                continue
            raw_data = rec.get("raw")
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except Exception:
                    raw_data = {}
            elif not isinstance(raw_data, dict):
                raw_data = {}

            t_title = rec.get("title") or raw_data.get("title") or ""
            t_student = rec.get("student_name") or raw_data.get("student_name") or ""
            t_path = rec.get("path") or raw_data.get("path") or rec.get("filename") or raw_data.get("filename") or ""
            if not t_path and t_title:
                t_clean = t_title.lstrip("#").strip()
                t_path = t_clean if t_clean.endswith(".md") else f"{t_clean}.md"

            t_date = rec.get("date") or raw_data.get("date") or ""
            t_preview = rec.get("preview") or raw_data.get("preview") or ""
            t_content = rec.get("content") or raw_data.get("content") or ""
            t_sid = rec.get("student_id") or raw_data.get("student_id") or ""

            candidates.append({
                "cloud_matched": is_cloud,
                "date": t_date,
                "title": t_title,
                "student_name": t_student,
                "student_id": t_sid,
                "path": t_path,
                "preview": t_preview,
                "content": t_content,
            })

        # 2. 蘋果總裁班教學筆記
        for an in apple_notes:
            if not isinstance(an, dict):
                continue
            an_title = an.get("full_title") or an.get("title") or an.get("filename", "")
            an_path = an.get("path") or an.get("filename") or an_title
            candidates.append({
                "cloud_matched": False,
                "date": an.get("date", ""),
                "title": an_title,
                "student_name": "蘋果總裁班",
                "student_id": "",
                "path": an_path,
                "preview": an.get("preview", ""),
                "content": an.get("content", ""),
            })

        results: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str, str]] = set()

        for item in candidates:
            title = str(item.get("title", "")).lstrip("#").strip()
            student_name = str(item.get("student_name", "")).strip()
            content = item.get("content", "")
            preview_raw = item.get("preview", "")
            date_str = item.get("date", "")
            path = item.get("path", "")

            matched = bool(item.get("cloud_matched"))
            if q_lower in student_name.lower():
                matched = True
            elif q_lower in title.lower():
                matched = True
            elif q_lower in preview_raw.lower():
                matched = True
            elif content and q_lower in content.lower():
                matched = True

            if not matched:
                continue

            dedup_key = (date_str, title, student_name, path)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            display_preview = ""
            if content:
                for line in content.splitlines():
                    cleaned = line.strip().lstrip("#-*\t ")
                    if q_lower in cleaned.lower():
                        display_preview = cleaned[:180]
                        break
            if not display_preview:
                display_preview = preview_raw[:180] if preview_raw else (content[:180] if content else "")

            # 確定 student_id 與實體消歧義（Amanda 蕭秉慧 不等於 Anna 蕭）
            sid = item.get("student_id")
            if student_name in ("Amanda 蕭秉慧", "蕭秉慧", "Amanda"):
                amanda_id = name_to_sid.get("amanda 蕭秉慧") or name_to_sid.get("蕭秉慧") or name_to_sid.get("amanda")
                if amanda_id:
                    sid = amanda_id
            if not sid:
                sid = name_to_sid.get(student_name.lower(), "")

            results.append({
                "date": date_str,
                "title": title,
                "student_name": student_name,
                "student_id": sid,
                "path": path,
                "preview": display_preview,
            })

        results.sort(key=lambda r: r.get("date") or "", reverse=True)

        return SearchResult(
            q=clean_q,
            results=results,
            matched_students=matched_students,
            count=len(results),
            next_cursor=next_cursor,
        )


_DEFAULT_SEARCH_SERVICE = SearchService()


def execute_search(
    query: str,
    cursor: str | None = None,
    students_loader: Callable[[], list[dict[str, Any]]] | None = None,
    teaching_records_loader: Callable[[], list[dict[str, Any]]] | None = None,
    apple_notes_loader: Callable[[], list[dict[str, Any]]] | None = None,
    data_gateway: Any = None,
) -> SearchResult:
    """高階函式介面：一鍵執行搜尋。"""
    if any([students_loader, teaching_records_loader, apple_notes_loader, data_gateway]):
        engine = SearchService(
            students_loader=students_loader,
            teaching_records_loader=teaching_records_loader,
            apple_notes_loader=apple_notes_loader,
            data_gateway=data_gateway,
        )
        return engine.search(query, cursor=cursor)
    return _DEFAULT_SEARCH_SERVICE.search(query, cursor=cursor)
