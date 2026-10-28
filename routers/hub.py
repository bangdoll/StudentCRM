"""routers/hub.py
學員專屬 Learning Hub、微行動卡、實戰案例牆與 PWA 領域路由器。
"""

import os
import json
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth_service import ADMIN_PASSKEYS
from hub_service import generate_student_manifest_data, get_random_practice_card
from note_service import extract_micro_action_cards
from apple_ceo_service import build_apple_ceo_view_context
from student_service import is_valid_student_access_key, resolve_student_access_id
from outcome_service import OutcomeStoreError, StudentActionSubmission, submit_student_action

router = APIRouter(tags=["hub"])


def get_hub_deps():
    """動態延遲取得核心依賴，避免循環導入。"""
    import main
    from hub_service import get_merged_redirects
    from routers.coach import coach_magic_link
    return {
        "templates": main.templates,
        "load_students": main.load_students,
        "get_student_by_id": main.get_student_by_id,
        "resolve_student_access_id": resolve_student_access_id,
        "is_valid_student_access_key": is_valid_student_access_key,
        "load_apple_ceo_program": main.load_apple_ceo_program,
        "get_merged_redirects": lambda: get_merged_redirects(main.APP_DIR),
        "get_student_teaching_notes": main.get_student_teaching_notes,
        "coach_magic_link": coach_magic_link,
        "BASE_DIR": main.BASE_DIR,
        "APP_DIR": main.APP_DIR,
        "student_gateway": main.student_gateway,
    }


@router.api_route("/my/{token}", methods=["GET", "HEAD"])
@router.api_route("/hub/{student_id}", methods=["GET", "HEAD"])
async def read_student_hub(request: Request, token: Optional[str] = None, student_id: Optional[str] = None):
    """【方案 A】專屬無感 Token 學習空間 (My Learning Hub)。

    提供學員專屬視圖：八堂修煉技能樹、歷次筆記與微行動卡片。
    100% 隱私與視野隔離，無需帳號密碼，支援 PWA 加入 iPhone 主畫面秒開。
    針對「蘋果總裁班」班級型空間，直接呈現完整班務、置頂教學筆記與出席紀錄。
    """
    deps = get_hub_deps()
    lookup_key = (token or student_id or "").strip()
    if not lookup_key:
        raise HTTPException(status_code=404, detail="請提供學員專屬 Token 或 ID")

    # 若持有人是教練或管理員私鑰（誤輸入至 /my/ 或 /hub/），自動引導登入管理員後台
    if lookup_key.lower() in ADMIN_PASSKEYS:
        return await deps["coach_magic_link"](request, lookup_key)

    redirects = deps["get_merged_redirects"]()
    if lookup_key in redirects:
        target_id = redirects[lookup_key]
        return RedirectResponse(url=f"/my/{target_id}", status_code=301)

    students = deps["load_students"]()
    student = deps["get_student_by_id"](deps["resolve_student_access_id"](lookup_key, students), students)
    if student and not deps["is_valid_student_access_key"](lookup_key, student):
        student = None
    if not student:
        raise HTTPException(status_code=404, detail="找不到此專屬學員空間，請確認連結是否正確")

    # 【重要核心路由】：若此 Token 是「蘋果總裁班」（班級型學習空間），直接呈現完整蘋果總裁班專屬頁面
    is_apple_ceo = (
        lookup_key in ("adf9958b-a23d-4e9b-a4a2-156b5329b0ed", "apple-ceo")
        or student.get("name") == "蘋果總裁班"
        or "總裁班" in student.get("name", "")
    )
    if is_apple_ceo:
        program_data = deps["load_apple_ceo_program"]()
        view_ctx = build_apple_ceo_view_context(
            program_data=program_data,
            students=students,
            token=lookup_key,
            is_student_view=True,
        )
        response = deps["templates"].TemplateResponse(request, "program_apple_ceo.html", {
            "request": request,
            **view_ctx,
        })
        response.set_cookie(
            key="last_student_token",
            value=lookup_key,
            max_age=180 * 86400,
            httponly=False,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response

    gateway = deps["student_gateway"]
    next_cursor = None
    if gateway.backend == "supabase":
        page = gateway.list_teaching_records(student["id"], cursor=request.query_params.get("cursor"))
        student_notes, next_cursor = page["items"], page["next_cursor"]
        # Latest card only; historical cards remain available in each note reader.
        recent = gateway.load_recent_teaching_records(student["id"], limit=1)
        latest = recent[0] if recent else None
        for note in student_notes:
            note["micro_cards"] = extract_micro_action_cards(latest["content"], latest.get("title") or "") if latest and note["id"] == latest["id"] else None
    else:
        student_notes = deps["get_student_teaching_notes"](student)
        for note in student_notes:
            content = note.get("content") or ""
            path = note.get("path") or ""
            if not content and path and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError:
                    pass
            note["micro_cards"] = extract_micro_action_cards(content or note.get("preview") or "", note.get("title") or "")

    cnt = student.get("lessons_count") or len(student_notes)
    cycle = student.get("current_cycle_lesson")
    if cycle is None:
        cycle = ((cnt % 8) or 8) if cnt > 0 else 1

    response = deps["templates"].TemplateResponse(request, "hub.html", {
        "request": request,
        "student": student,
        "student_notes": student_notes,
        "next_cursor": next_cursor,
        "cycle_lesson": cycle,
        "token": lookup_key,
    })
    response.set_cookie(
        key="last_student_token",
        value=lookup_key,
        max_age=180 * 86400,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


@router.api_route("/my/{token}/manifest.webmanifest", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/hub/{token}/manifest.webmanifest", methods=["GET", "HEAD"], include_in_schema=False)
async def student_hub_manifest(token: str):
    """【學員專屬 PWA 清單】將 start_url 綁定至學員個人 URL，委託 hub_service 產生標準配置。"""
    deps = get_hub_deps()
    students = deps["load_students"]()
    student = deps["get_student_by_id"](deps["resolve_student_access_id"](token, students), students)
    if student and not is_valid_student_access_key(token, student):
        student = None
    student_name = student.get("name", "學員") if student else "學員"
    if token in ("adf9958b-a23d-4e9b-a4a2-156b5329b0ed", "apple-ceo") or (student and "總裁班" in student.get("name", "")):
        student_name = "蘋果總裁班"
    manifest_data = generate_student_manifest_data(student_name, token)
    return JSONResponse(content=manifest_data, media_type="application/manifest+json")


@router.post("/my/{token}/outcomes/submit", response_class=JSONResponse)
async def submit_student_outcome(token: str, payload: StudentActionSubmission):
    """學員在專屬連結回報課後行動；只修改獨立成果層，不修改原始教學筆記。"""
    deps = get_hub_deps()
    students = deps["load_students"]()
    student = deps["get_student_by_id"](deps["resolve_student_access_id"](token, students), students)
    if student and not is_valid_student_access_key(token, student):
        student = None
    if not student:
        raise HTTPException(status_code=404, detail="找不到學員專屬空間")
    try:
        outcome = submit_student_action(student.get("id", ""), payload)
        return JSONResponse({"success": True, "outcome_id": outcome.get("id"), "outcome": outcome})
    except OutcomeStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.api_route("/api/practice/random", methods=["GET", "HEAD"])
async def api_random_practice_card():
    """【今日實戰微行動】隨機抽取一張課堂實踐微行動小卡。"""
    deps = get_hub_deps()
    card = get_random_practice_card(deps["BASE_DIR"], deps["APP_DIR"])
    return JSONResponse(content=card)


@router.api_route("/cases", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_cases(request: Request):
    """【去識別化 100+ 堂實戰見證案例庫】展示醫師、企業高階經理人與超級個體的真實轉化成果。"""
    deps = get_hub_deps()
    cases_file = os.path.join(deps["APP_DIR"], "data", "social_proof_cases.json")
    cases = []
    if os.path.exists(cases_file):
        try:
            with open(cases_file, "r", encoding="utf-8") as f:
                cases = json.load(f)
        except Exception:
            pass
    return deps["templates"].TemplateResponse(request, "cases.html", {"request": request, "cases": cases})


@router.api_route("/api/cases", methods=["GET", "HEAD"])
async def api_cases():
    """取得去識別化實戰案例清單 JSON。"""
    deps = get_hub_deps()
    cases_file = os.path.join(deps["APP_DIR"], "data", "social_proof_cases.json")
    if os.path.exists(cases_file):
        try:
            with open(cases_file, "r", encoding="utf-8") as f:
                return JSONResponse(content=json.load(f))
        except Exception:
            pass
    return JSONResponse(content=[])
