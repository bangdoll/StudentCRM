"""routers/coach.py
教練後台、通行門禁、儀表板與全域搜尋領域路由器。
"""

import os
import logging
from urllib.parse import unquote
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

logger = logging.getLogger(__name__)

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
from note_service import extract_micro_action_cards
from outcome_service import (
    BootstrapOutcomeRequest,
    CaseDraftRequest,
    CreateOutcomeRequest,
    ExperimentObservationRequest,
    OutcomeStoreError,
    VerifyOutcomeRequest,
    bootstrap_outcome,
    create_case_draft,
    create_outcome,
    outcome_summary,
    record_experiment_observation,
    list_outcomes,
    verify_outcome,
)


def _is_cloud_uuid(value):
    from uuid import UUID
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


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

    # 載入成效雷達數據，供首頁戰情儀表板展示
    gateway = deps["student_gateway"]
    effectiveness_radar = gateway.get_effectiveness_radar_data()
    if not effectiveness_radar.get("items"):
        try:
            effectiveness_radar = build_full_effectiveness_radar(gateway)
        except Exception as exc:
            logger.warning(f"首頁建構完整成效雷達失敗，使用預設快取: {exc}")

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
        "effectiveness_radar": effectiveness_radar,
    })


@router.api_route("/dashboard", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_dashboard(request: Request):
    deps = get_coach_deps()
    from dashboard_service import build_dashboard_context

    context = build_dashboard_context(
        students_loader=deps.get("load_students"),
        apple_program_loader=deps.get("load_apple_ceo_program"),
        sync_status_loader=lambda: deps["student_gateway"].status(),
        metadata_loader=deps.get("get_student_metadata"),
        features_analyzer=deps.get("analyze_student_features"),
        base_dir=deps.get("BASE_DIR", ""),
    )

    if deps["use_fallback_pages"]("dashboard.html"):
        return deps["render_dashboard_fallback"](
            context["students"],
            context["apple_summary"],
            context["sync_status"],
        )

    return deps["templates"].TemplateResponse(request, "dashboard.html", {
        "request": request,
        **context,
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
async def search(request: Request, q: str = "", cursor: str | None = None):
    deps = get_coach_deps()
    from search_service import execute_search

    search_result = execute_search(
        query=q,
        cursor=cursor,
        data_gateway=deps.get("student_gateway"),
        students_loader=deps.get("load_students"),
        teaching_records_loader=lambda: deps["student_gateway"].load_all_teaching_records(),
        apple_notes_loader=lambda: deps["load_apple_ceo_program"]().get("teaching_notes", []) if isinstance(deps["load_apple_ceo_program"](), dict) else [],
    )

    return deps["templates"].TemplateResponse(request, "search.html", {
        "request": request,
        **search_result.to_template_context(),
    })


@router.api_route("/radar", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def get_effectiveness_radar_page(request: Request):
    """【成效與續約雷達戰情頁】展示 AI 導入階段、微行動卡進度、流失預警與 CSM 追蹤。"""
    deps = get_coach_deps()
    gateway = deps["student_gateway"]
    try:
        radar_data = build_full_effectiveness_radar(gateway)
    except Exception as exc:
        logger.warning(f"即時計算成效雷達異常，降級至快取資料: {exc}")
        radar_data = gateway.get_effectiveness_radar_data()
    outcome_data = outcome_summary(deps["load_students"](), radar_data.get("items", []))

    return deps["templates"].TemplateResponse(request, "radar.html", {
        "request": request,
        "radar": radar_data,
        "summary": radar_data.get("summary", {}),
        "items": radar_data.get("items", []),
        "generated_at": radar_data.get("generated_at", ""),
        "outcome_summary": outcome_data,
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


@router.get("/api/outcomes/summary", response_class=JSONResponse)
async def get_outcome_summary_api():
    """回傳教學成果閉環、容量與功能停損閘門摘要。"""
    deps = get_coach_deps()
    radar_data = deps["student_gateway"].get_effectiveness_radar_data()
    return JSONResponse(outcome_summary(deps["load_students"](), radar_data.get("items", [])))


@router.get("/api/outcomes", response_class=JSONResponse)
async def get_outcomes_api():
    """回傳教練端可讀的成果閉環紀錄；不對外暴露此端點。"""
    return JSONResponse({"items": list_outcomes()})


@router.post("/api/outcomes", response_class=JSONResponse)
async def create_outcome_api(payload: CreateOutcomeRequest):
    """由教練建立一堂課的核心判斷、下一步行動與回看問題。"""
    try:
        return JSONResponse({"success": True, "outcome": create_outcome(payload)})
    except OutcomeStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/outcomes/bootstrap", response_class=JSONResponse)
async def bootstrap_outcome_api(payload: BootstrapOutcomeRequest):
    """以學員最新一堂既有筆記建立待教練覆核的閉環草稿。"""
    deps = get_coach_deps()
    students = deps["load_students"]()
    student = next((item for item in students if item.get("id") == payload.student_id), None)
    if not student:
        raise HTTPException(status_code=404, detail="找不到學員")
    records = deps["student_gateway"].load_recent_teaching_records(payload.student_id, limit=1)
    if not records:
        raise HTTPException(status_code=400, detail="此學員尚無可建立閉環的教學筆記")
    note = sorted(records, key=lambda item: str(item.get("date") or ""), reverse=True)[0]
    content = str(note.get("content") or note.get("preview") or "")
    cards = extract_micro_action_cards(content, str(note.get("title") or ""))
    try:
        outcome = bootstrap_outcome(student, note, cards)
        return JSONResponse({"success": True, "outcome": outcome})
    except OutcomeStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/outcomes/{outcome_id}/verify", response_class=JSONResponse)
async def verify_outcome_api(outcome_id: str, payload: VerifyOutcomeRequest):
    """教練確認成果，作為案例草稿的必要閘門。"""
    try:
        return JSONResponse({"success": True, "outcome": verify_outcome(outcome_id, payload)})
    except OutcomeStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/outcomes/{outcome_id}/case-draft", response_class=JSONResponse)
async def create_case_draft_api(outcome_id: str, payload: CaseDraftRequest):
    """只允許已驗證且有證據的成果進入內部案例草稿。"""
    try:
        draft = create_case_draft(outcome_id, payload)
        return JSONResponse({"success": True, "case_draft": draft})
    except OutcomeStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/feature-gates/{gate_id}/observations", response_class=JSONResponse)
async def record_feature_gate_observation_api(gate_id: str, payload: ExperimentObservationRequest):
    """記錄 2–4 週試點訊號，沒有足夠證據時維持 human_review。"""
    try:
        return JSONResponse({"success": True, **record_experiment_observation(gate_id, payload)})
    except OutcomeStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
