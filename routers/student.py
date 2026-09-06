"""routers/student.py
學員檔案、課堂筆記閱讀器與數位管理教學領域路由器。
"""

import os
import re
import subprocess
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from schedule_service import get_document_exceptions, get_next_occurrence
from prediction_service import predict_student_status
from student_service import generate_student_renewal_reminder, generate_preclass_briefing
from note_service import resolve_note_detail

from schemas import (
    APIStatusResponse,
    StudentDetailResponse,
    DigitalManagementListResponse,
    DigitalManagementDetailResponse,
)


router = APIRouter(tags=["student"])


def get_student_deps():
    import main
    from hub_service import get_merged_redirects
    return {
        "templates": main.templates,
        "load_students": main.load_students,
        "load_apple_ceo_program": main.load_apple_ceo_program,
        "load_cloud_digital_management_notes": main.load_cloud_digital_management_notes,
        "student_gateway": main.student_gateway,
        "BASE_DIR": main.BASE_DIR,
        "get_merged_redirects": lambda: get_merged_redirects(main.APP_DIR),
        "get_student_metadata": main.get_student_metadata,
        "build_cloud_student_meta": main.build_cloud_student_meta,
        "analyze_student_features": main.analyze_student_features,
        "get_student_teaching_notes": main.get_student_teaching_notes,
        "render_cloud_student_timeline": main.render_cloud_student_timeline,
        "inject_badges": main.inject_badges,
        "build_digital_management_profiles": main.build_digital_management_profiles,
        "use_fallback_pages": main.use_fallback_pages,
        "render_fallback_page": main.render_fallback_page,
        "get_student_by_id": main.get_student_by_id,
    }


@router.get("/student/{student_id}", response_class=HTMLResponse)
async def read_student(request: Request, student_id: str):
    """【學員個人檔案頁面】展示教學時間軸、課前 3 分鐘智慧備課卡與續約文案。"""
    deps = get_student_deps()
    redirects = deps["get_merged_redirects"]()
    if student_id in redirects:
        target_id = redirects[student_id]
        return RedirectResponse(url=f"/student/{target_id}", status_code=301)

    students = deps["load_students"]()
    student = next((s for s in students if s.get('id') == student_id), None)
    if not student:
        return HTMLResponse(content="Student not found", status_code=404)

    base_dir = deps["BASE_DIR"]
    file_value = student.get('file') or ""
    file_path = os.path.join(base_dir, file_value.lstrip('/')) if file_value else ""

    if 'recurring_schedule' in student and not student.get('next_lesson'):
        doc_exceptions = get_document_exceptions(file_path) if file_path else []
        json_exceptions = student.get('schedule_exceptions', [])
        all_exceptions = list(set(json_exceptions + doc_exceptions))

        student['next_lesson'] = get_next_occurrence(
            student['recurring_schedule'],
            all_exceptions
        )

    student_notes = deps["get_student_teaching_notes"](student)
    file_meta = deps["get_student_metadata"](file_path) if file_path and os.path.exists(file_path) else {}
    cloud_meta = deps["build_cloud_student_meta"](student)
    student['meta'] = {**cloud_meta, **file_meta}
    if not student['meta'].get('first_lesson_date') or student['meta']['first_lesson_date'] in ("未記錄", "TBD"):
        student['meta']['first_lesson_date'] = student.get('first_lesson_date') or "未記錄"
    if not student['meta'].get('last_lesson_date') or student['meta']['last_lesson_date'] in ("未記錄", "TBD"):
        student['meta']['last_lesson_date'] = student.get('latest_date') or "未記錄"
    if not student['meta'].get('lessons_count') or student['meta']['lessons_count'] == 0:
        student['meta']['lessons_count'] = student.get('lessons_count') or len(student_notes)
    student['features'] = deps["analyze_student_features"](student_id)
    student['prediction'] = predict_student_status(student['features'], student.get('next_lesson'))
    renewal_message = generate_student_renewal_reminder(student)
    briefing = generate_preclass_briefing(student, student_notes)

    if not file_path or not os.path.exists(file_path):
        teaching_records = deps["student_gateway"].load_teaching_records(student_id)
        return deps["templates"].TemplateResponse(request, "student.html", {
            "request": request,
            "student": student,
            "student_notes": student_notes,
            "timeline_html": deps["render_cloud_student_timeline"](student, teaching_records),
            "student_id": student_id,
            "renewal_message": renewal_message,
            "briefing": briefing,
        })

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parts = re.split(r"## 📅 教學時間軸 \(Lesson Timeline\)", content)
    body = parts[1] if len(parts) > 1 else ""
    body = body.replace("file://", "/open_file?path=")

    import markdown
    html_content = markdown.markdown(body, extensions=['tables'])
    html_content = deps["inject_badges"](html_content)

    return deps["templates"].TemplateResponse(request, "student.html", {
        "request": request,
        "student": student,
        "student_notes": student_notes,
        "timeline_html": html_content,
        "student_id": student_id,
        "renewal_message": renewal_message,
        "briefing": briefing,
    })


@router.api_route("/note", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/open_file", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def open_file(request: Request, path: str):
    """【單篇教學筆記閱讀器】安全解析教案內容與課堂 3 張微行動卡。"""
    deps = get_student_deps()
    apple_program = deps["load_apple_ceo_program"]()
    apple_notes = apple_program.get("teaching_notes", [])
    records = deps["load_cloud_digital_management_notes"]()
    students = deps["load_students"]()

    note = resolve_note_detail(
        path_or_filename=path,
        base_dir=deps["BASE_DIR"],
        apple_notes=apple_notes,
        cloud_records=records,
        students=students,
    )

    token = request.query_params.get("token") or request.cookies.get("last_student_token") or ""

    if not note:
        back_url = f"/my/{token}" if token else "/program/apple-ceo"
        return HTMLResponse(content=f"<h3>找不到此筆記或路徑無效 (404)</h3><p><a href='{back_url}'>返回專屬學習空間</a></p>", status_code=404)

    return deps["templates"].TemplateResponse(request, "note.html", {
        "request": request,
        "token": token,
        **note.to_template_context()
    })


@router.get("/trigger_open", response_model=APIStatusResponse)
async def trigger_open(path: str):
    deps = get_student_deps()
    base_dir = deps["BASE_DIR"]
    if os.path.exists(path) and path.startswith(base_dir):
        subprocess.run(["open", path])
        return {"status": "ok"}
    return {"status": "error", "message": "Invalid path"}


@router.get("/digital-management", response_class=HTMLResponse)
async def read_digital_management(request: Request):
    deps = get_student_deps()
    include_heptabase = request.query_params.get("heptabase", "").lower() in {"1", "true", "yes"}
    import html as html_lib
    payload = deps["build_digital_management_profiles"](include_heptabase=include_heptabase)
    if deps["use_fallback_pages"]("digital_management.html"):
        rows = "\n".join(
            "<tr>"
            f"<td><a href='/digital-management/student/{student.get('id')}'>{html_lib.escape(student.get('name', ''))}</a></td>"
            f"<td>{html_lib.escape(str(student.get('current_lesson') or 0))}</td>"
            f"<td>{html_lib.escape(student.get('next_lesson') or '尚未排定')}</td>"
            f"<td>{len(student.get('notes', []))}</td>"
            "</tr>"
            for student in payload.get("students", [])
        )
        body = f"""
        <section class="card">
            <p class="muted">Calendar cache: {html_lib.escape(payload.get('calendar_cache', ''))}</p>
            <table><thead><tr><th>學生</th><th>目前堂數</th><th>下次上課</th><th>筆記</th></tr></thead><tbody>{rows}</tbody></table>
        </section>
        """
        return deps["render_fallback_page"]("數位管理教學", body)
    return deps["templates"].TemplateResponse(request, "digital_management.html", {
        "request": request,
        **payload,
    })


@router.get("/digital-management/student/{student_id}", response_class=HTMLResponse)
async def read_digital_management_student(request: Request, student_id: str):
    deps = get_student_deps()
    import html as html_lib
    payload = deps["build_digital_management_profiles"](include_heptabase=True)
    student = next((item for item in payload.get("students", []) if item.get("id") == student_id), None)
    if not student:
        return HTMLResponse(content="Digital management student not found", status_code=404)
    if deps["use_fallback_pages"]("digital_management_student.html"):
        rows = "\n".join(
            "<tr>"
            f"<td>{html_lib.escape(note.get('date') or '')}</td>"
            f"<td>{html_lib.escape(note.get('title') or '')}</td>"
            f"<td>{html_lib.escape(note.get('source') or '')}</td>"
            "</tr>"
            for note in student.get("notes", [])
        )
        body = f"""
        <section class="card">
            <p>目前上到第 {html_lib.escape(str(student.get('current_lesson') or 0))} 堂；下次上課：{html_lib.escape(student.get('next_lesson') or '尚未排定')}</p>
            <table><thead><tr><th>日期</th><th>筆記</th><th>來源</th></tr></thead><tbody>{rows}</tbody></table>
        </section>
        """
        return deps["render_fallback_page"](student.get("name", "學生檔案"), body)
    return deps["templates"].TemplateResponse(request, "digital_management_student.html", {
        "request": request,
        "student": student,
        "calendar_cache": payload.get("calendar_cache", ""),
        "heptabase_backup_root": payload.get("heptabase_backup_root", ""),
    })


@router.get("/api/students")
async def api_students():
    deps = get_student_deps()
    students = deps["load_students"]()
    return {
        "count": len(students),
        "students": students,
        "sync": deps["student_gateway"].status(),
    }


@router.get("/api/students/{student_id}", response_model=StudentDetailResponse)
async def api_student(student_id: str):
    deps = get_student_deps()
    students = deps["load_students"]()
    student = next((s for s in students if s.get("id") == student_id), None)
    if not student:
        return {"status": "not_found", "student_id": student_id}
    features = deps["analyze_student_features"](student_id)
    return {
        "status": "ok",
        "student_id": student_id,
        "student": student,
        "features": features,
        "prediction": predict_student_status(features, student.get("next_lesson")),
        "sync": deps["student_gateway"].status(),
    }


@router.get("/api/digital-management/students", response_model=DigitalManagementListResponse)
async def api_digital_management_students():
    deps = get_student_deps()
    payload = deps["build_digital_management_profiles"](include_heptabase=False)
    return {
        "status": "ok",
        "count": len(payload.get("students", [])),
        **payload,
    }


@router.get("/api/digital-management/students/{student_id}", response_model=DigitalManagementDetailResponse)
async def api_digital_management_student(student_id: str):
    deps = get_student_deps()
    payload = deps["build_digital_management_profiles"](include_heptabase=True)
    student = next((item for item in payload.get("students", []) if item.get("id") == student_id), None)
    if not student:
        return {"status": "not_found", "student_id": student_id}
    return {
        "status": "ok",
        "student_id": student_id,
        "student": student,
        "calendar_cache": payload.get("calendar_cache", ""),
        "heptabase_backup_root": payload.get("heptabase_backup_root", ""),
    }
