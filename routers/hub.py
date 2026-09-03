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
from apple_ceo_service import summarize_apple_ceo_program

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
        "load_apple_ceo_program": main.load_apple_ceo_program,
        "get_merged_redirects": lambda: get_merged_redirects(main.APP_DIR),
        "get_student_teaching_notes": main.get_student_teaching_notes,
        "coach_magic_link": coach_magic_link,
        "BASE_DIR": main.BASE_DIR,
        "APP_DIR": main.APP_DIR,
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
    student = deps["get_student_by_id"](lookup_key, students)
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
        summary = summarize_apple_ceo_program(program_data)
        teaching_notes = program_data.get("teaching_notes", [])
        name_to_student = {}
        for s in students:
            s_name = s.get("name", "")
            if s_name:
                name_to_student[s_name] = s
            for alias in s.get("aliases", []):
                if alias:
                    name_to_student[alias] = s
        response = deps["templates"].TemplateResponse(request, "program_apple_ceo.html", {
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
            "token": lookup_key,
            "is_student_view": True,
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

    student_notes = deps["get_student_teaching_notes"](student)
    for note in student_notes:
        content = note.get("content") or ""
        if not content:
            path = note.get("path") or ""
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError:
                    pass
        if not content:
            content = note.get("preview") or ""
        note["micro_cards"] = extract_micro_action_cards(content, note.get("title") or "")

    cnt = student.get("lessons_count") or len(student_notes)
    cycle = student.get("current_cycle_lesson")
    if cycle is None:
        cycle = ((cnt % 8) or 8) if cnt > 0 else 1

    response = deps["templates"].TemplateResponse(request, "hub.html", {
        "request": request,
        "student": student,
        "student_notes": student_notes,
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
    student = deps["get_student_by_id"](token, students)
    student_name = student.get("name", "學員") if student else "學員"
    if token in ("adf9958b-a23d-4e9b-a4a2-156b5329b0ed", "apple-ceo") or (student and "總裁班" in student.get("name", "")):
        student_name = "蘋果總裁班"
    manifest_data = generate_student_manifest_data(student_name, token)
    return JSONResponse(content=manifest_data, media_type="application/manifest+json")


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
