"""routers/coach.py
教練後台、通行門禁、儀表板與全域搜尋領域路由器。
"""

import os
from urllib.parse import unquote
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from auth_service import (
    ADMIN_PASSKEYS,
    SESSION_COOKIE_NAME,
    ADMIN_USER_COOKIE_NAME,
    render_magic_link_page,
)
from schedule_service import (
    get_document_exceptions,
    get_next_occurrence,
    get_next_lesson_sort_key,
)
from student_service import get_global_renewal_radar
from apple_ceo_service import summarize_apple_ceo_program, extract_session_date
from prediction_service import predict_student_status
from radar_service import build_full_effectiveness_radar
from schemas.radar import FollowupUpdateRequest


router = APIRouter(tags=["coach"])


def get_coach_deps():
    import main
    return {
        "templates": main.templates,
        "load_students": main.load_students,
        "load_apple_ceo_program": main.load_apple_ceo_program,
        "student_gateway": main.student_gateway,
        "BASE_DIR": main.BASE_DIR,
        "get_student_metadata": main.get_student_metadata,
        "build_cloud_student_meta": main.build_cloud_student_meta,
        "analyze_student_features": main.analyze_student_features,
        "use_fallback_pages": main.use_fallback_pages,
        "render_dashboard_fallback": main.render_dashboard_fallback,
    }


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_root(request: Request):
    """【教練行動看板首頁】展示 64 位學員進度、續約預警雷達與總裁班摘要。"""
    deps = get_coach_deps()
    students = deps["load_students"]()
    base_dir = deps["BASE_DIR"]

    for s in students:
        if 'recurring_schedule' in s and not s.get('next_lesson'):
            student_file = os.path.join(base_dir, s['file'].lstrip('/')) if s.get('file') else ""
            doc_exceptions = get_document_exceptions(student_file)
            json_exceptions = s.get('schedule_exceptions', [])
            all_exceptions = list(set(json_exceptions + doc_exceptions))

            s['next_lesson'] = get_next_occurrence(
                s['recurring_schedule'],
                all_exceptions
            )

    for s in students:
        file_path = os.path.join(base_dir, s['file'].lstrip('/')) if s.get('file') else ""
        file_meta = deps["get_student_metadata"](file_path) if file_path and os.path.exists(file_path) else {}
        cloud_meta = deps["build_cloud_student_meta"](s)
        s['meta'] = {**cloud_meta, **file_meta}
        if not s['meta'].get('first_lesson_date') or s['meta']['first_lesson_date'] in ("未記錄", "TBD"):
            s['meta']['first_lesson_date'] = s.get('first_lesson_date') or "未記錄"
        if not s['meta'].get('last_lesson_date') or s['meta']['last_lesson_date'] in ("未記錄", "TBD"):
            s['meta']['last_lesson_date'] = s.get('latest_date') or "未記錄"
        if not s['meta'].get('lessons_count') or s['meta']['lessons_count'] == 0:
            s['meta']['lessons_count'] = s.get('lessons_count') or 0
        s['features'] = deps["analyze_student_features"](s['id'], target_student=s)
        s['prediction'] = predict_student_status(s['features'], s.get('next_lesson'))

    sorted_students = sorted(students, key=get_next_lesson_sort_key)
    apple_program = deps["load_apple_ceo_program"]()
    apple_summary = summarize_apple_ceo_program(apple_program)
    renewal_radar = get_global_renewal_radar(sorted_students)

    admin_user_cookie = request.cookies.get(ADMIN_USER_COOKIE_NAME, "")
    admin_user = unquote(admin_user_cookie) if admin_user_cookie else "管理員"

    if deps["use_fallback_pages"]("index.html"):
        return deps["render_dashboard_fallback"](sorted_students, apple_summary, deps["student_gateway"].status())

    return deps["templates"].TemplateResponse(request, "index.html", {
        "request": request,
        "admin_user": admin_user,
        "students": sorted_students,
        "apple_program": apple_program["program"],
        "apple_summary": apple_summary,
        "renewal_radar": renewal_radar,
    })


@router.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    deps = get_coach_deps()
    students = deps["load_students"]()
    base_dir = deps["BASE_DIR"]

    for student in students:
        student_file = os.path.join(base_dir, student.get('file', '').lstrip('/'))
        student['meta'] = deps["get_student_metadata"](student_file)
        student['features'] = deps["analyze_student_features"](student['id'])
        student['prediction'] = predict_student_status(student['features'], student.get('next_lesson'))

    apple_program = deps["load_apple_ceo_program"]()
    apple_summary = summarize_apple_ceo_program(apple_program)
    today = datetime.now().date()

    def parse_next_lesson(value: str):
        date_text = extract_session_date(value or "")
        if not date_text:
            return None
        try:
            return datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            return None

    upcoming_students = []
    unscheduled_students = []
    risk_students = []
    freezing_students = []
    stable_students = []

    for student in students:
        next_date = parse_next_lesson(student.get('next_lesson', ''))
        student['next_lesson_days'] = (next_date - today).days if next_date else None
        if next_date and 0 <= (next_date - today).days <= 14:
            upcoming_students.append(student)
        if not next_date:
            unscheduled_students.append(student)

        status = student.get('prediction', {}).get('status', '')
        if '高流失' in status:
            risk_students.append(student)
        elif '冰凍期' in status:
            freezing_students.append(student)
        elif '穩定留存' in status:
            stable_students.append(student)

    students.sort(key=lambda item: (
        item.get('next_lesson_days') is None,
        item.get('next_lesson_days') if item.get('next_lesson_days') is not None else 9999,
        item.get('name', ''),
    ))

    if deps["use_fallback_pages"]("dashboard.html"):
        return deps["render_dashboard_fallback"](students, apple_summary, deps["student_gateway"].status())

    return deps["templates"].TemplateResponse(request, "dashboard.html", {
        "request": request,
        "students": students,
        "student_count": len(students),
        "upcoming_students": upcoming_students,
        "unscheduled_students": unscheduled_students,
        "risk_students": risk_students,
        "freezing_students": freezing_students,
        "stable_students": stable_students,
        "apple_program": apple_program["program"],
        "apple_summary": apple_summary,
    })


@router.api_route("/coach/{key}", methods=["GET", "HEAD"])
@router.api_route("/admin/{key}", methods=["GET", "HEAD"])
async def coach_magic_link(request: Request, key: str, next: str = "/"):
    """【專屬無密碼通行】以專屬私鑰直接解鎖進入教練與管理員後台，零輸入免密碼。"""
    deps = get_coach_deps()
    norm_key = (key or "").strip().lower()
    if norm_key in ADMIN_PASSKEYS:
        return render_magic_link_page(ADMIN_PASSKEYS[norm_key], target_url=next or "/")
    return deps["templates"].TemplateResponse(request, "lock.html", {"request": request}, status_code=403)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(ADMIN_USER_COOKIE_NAME, path="/")
    return response


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = ""):
    deps = get_coach_deps()
    import glob
    import re
    results = []
    if q.strip():
        students = deps["load_students"]()
        name_to_sid = {}
        for s in students:
            name_to_sid[s.get('name', '')] = s.get('id', '')
            for alias in s.get('aliases', []):
                name_to_sid[alias] = s.get('id', '')

        import main
        cache_files = glob.glob(os.path.join(main.CACHE_DIR, "Lesson_*.md"))
        teaching_files = glob.glob(os.path.join(main.TEACHING_DIR, "Lesson_*.md"))
        all_files = sorted(cache_files + teaching_files, reverse=True)

        for fpath in all_files:
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            if q.lower() not in content.lower():
                continue

            fname = os.path.basename(fpath)
            m = re.match(r'Lesson_(\d{8})_(.+)\.md', fname)
            if not m:
                continue
            date_str, student_name = m.group(1), m.group(2)
            sid = name_to_sid.get(student_name, student_name.lower())

            preview = ""
            for line in content.split('\n'):
                if q.lower() in line.lower():
                    preview = line.strip()[:150]
                    break

            title = fname
            for line in content.split('\n'):
                if line.startswith('#'):
                    title = re.sub(r'^#+\s*', '', line).strip()
                    break

            y, mo, d = date_str[:4], date_str[4:6], date_str[6:]
            results.append({
                "date": f"{y}-{mo}-{d}",
                "title": title,
                "student_name": student_name,
                "student_id": sid,
                "path": fpath,
                "preview": preview,
            })

    return deps["templates"].TemplateResponse(request, "search.html", {
        "request": request,
        "q": q,
        "results": results,
        "count": len(results),
    })


@router.get("/radar", response_class=HTMLResponse)
async def get_effectiveness_radar_page(request: Request):
    """【成效與續約雷達戰情頁】展示 AI 導入階段、微行動卡進度、流失預警與 CSM 追蹤。"""
    deps = get_coach_deps()
    gateway = deps["student_gateway"]
    radar_data = build_full_effectiveness_radar(gateway)

    return deps["templates"].TemplateResponse(request, "radar.html", {
        "request": request,
        "radar": radar_data,
        "summary": radar_data.get("summary", {}),
        "items": radar_data.get("items", []),
        "generated_at": radar_data.get("generated_at", ""),
    })


@router.get("/api/radar", response_class=JSONResponse)
async def get_effectiveness_radar_api():
    """【成效雷達資料端點】回傳成效雷達項目與統計數據 JSON。"""
    deps = get_coach_deps()
    gateway = deps["student_gateway"]
    radar_data = gateway.get_effectiveness_radar_data()
    if not radar_data.get("items"):
        radar_data = build_full_effectiveness_radar(gateway)
    return JSONResponse(radar_data)


@router.post("/api/radar/followup", response_class=JSONResponse)
async def update_csm_followup_api(payload: FollowupUpdateRequest):
    """【CSM 跟進狀態更新端點】記錄學員關懷進度、下次回訪日期與私密備忘錄。"""
    deps = get_coach_deps()
    gateway = deps["student_gateway"]
    try:
        updated_item = gateway.update_csm_followup_record(
            student_id=payload.student_id,
            update_data=payload.model_dump(),
        )
        return JSONResponse({"success": True, "item": updated_item})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/radar/refresh", response_class=JSONResponse)
async def refresh_effectiveness_radar_api():
    """【手動重算雷達快取】強制重新掃描學員資料庫與最新教學筆記。"""
    deps = get_coach_deps()
    gateway = deps["student_gateway"]
    radar_data = build_full_effectiveness_radar(gateway)
    return JSONResponse({"success": True, "radar": radar_data})

