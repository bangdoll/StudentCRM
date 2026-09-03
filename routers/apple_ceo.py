"""routers/apple_ceo.py
蘋果總裁班專區領域路由器。
管理班務、出席預覽、場地費流水與專班看板。
"""

from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from apple_ceo_service import (
    summarize_apple_ceo_program,
    preview_apple_ceo_attendance,
)

router = APIRouter(tags=["apple_ceo"])


class AttendancePreviewRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    venue: str = "玫瑰客廳"
    attendees: list[str] = []
    note: str = ""


def get_apple_deps():
    import main
    return {
        "templates": main.templates,
        "student_gateway": main.student_gateway,
        "load_apple_ceo_program": main.load_apple_ceo_program,
        "load_students": main.load_students,
        "APPLE_CEO_FILE": main.APPLE_CEO_FILE,
        "use_fallback_pages": main.use_fallback_pages,
        "render_fallback_page": main.render_fallback_page,
    }


@router.get("/api/program/apple-ceo")
async def api_apple_ceo_program():
    deps = get_apple_deps()
    program_data = deps["load_apple_ceo_program"]()
    gateway = deps["student_gateway"]
    return {
        **program_data,
        "summary": summarize_apple_ceo_program(program_data),
        "sync": {
            "engine": gateway.backend,
            "source": "apple_* Supabase tables" if gateway.backend == "supabase" else deps["APPLE_CEO_FILE"],
            "checked_at": datetime.now().isoformat(),
        },
    }


@router.post("/api/program/apple-ceo/preview/attendance")
async def api_preview_apple_ceo_attendance(payload: AttendancePreviewRequest):
    deps = get_apple_deps()
    program_data = deps["load_apple_ceo_program"]()
    preview = preview_apple_ceo_attendance(
        program_data=program_data,
        date=payload.date,
        venue=payload.venue,
        attendees=payload.attendees,
        note=payload.note,
    )
    return {
        "status": "preview_only",
        "requires_human_confirmation": True,
        "will_write": False,
        **preview,
    }


@router.api_route("/program/apple-ceo", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_apple_ceo_program(request: Request):
    deps = get_apple_deps()
    program_data = deps["load_apple_ceo_program"]()
    summary = summarize_apple_ceo_program(program_data)
    teaching_notes = program_data.get("teaching_notes", [])
    token = request.query_params.get("token") or request.cookies.get("last_student_token") or "adf9958b-a23d-4e9b-a4a2-156b5329b0ed"

    if deps["use_fallback_pages"]("program_apple_ceo.html"):
        rows = "\n".join(
            f"<tr><td>{record.get('date', '')}</td><td>{record.get('venue', '')}</td><td>{record.get('attendee_count', 0)}</td></tr>"
            for record in program_data.get("attendance_records", [])[:80]
        )
        if not rows:
            rows = '<tr><td colspan="3" class="muted">尚未載入班務資料。</td></tr>'
        body = f"""
        <section class="grid">
            <div class="card"><span>活躍學員</span><strong>{summary.get('active_student_count', 0)}</strong></div>
            <div class="card"><span>續班提醒</span><strong>{summary.get('completed_student_count', 0)}</strong></div>
            <div class="card"><span>場地餘額</span><strong>{summary.get('latest_balance_label', '$0')}</strong></div>
        </section>
        <section class="card">
            <h2>{program_data.get('program', {}).get('name', '蘋果總裁班')}</h2>
            <table>
                <thead><tr><th>日期</th><th>場地</th><th>人數</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>
        """
        return deps["render_fallback_page"]("蘋果總裁班", body)

    students = deps["load_students"]()
    name_to_student = {}
    for s in students:
        s_name = s.get("name", "")
        if s_name:
            name_to_student[s_name] = s
        for alias in s.get("aliases", []):
            if alias:
                name_to_student[alias] = s

    return deps["templates"].TemplateResponse(request, "program_apple_ceo.html", {
        "request": request,
        "program": program_data["program"],
        "venue": program_data["venue"],
        "active_participants": program_data.get("active_participants", []),
        "attendance_records": program_data.get("attendance_records", []),
        "venue_ledger": program_data.get("venue_ledger", []),
        "student_rounds": program_data.get("student_rounds", []),
        "tuition_records": program_data.get("tuition_records", []),
        "teaching_notes": teaching_notes,
        "summary": summary,
        "legacy_note": program_data.get("legacy_note", ""),
        "name_to_student": name_to_student,
        "token": token,
        "is_student_view": False,
    })
