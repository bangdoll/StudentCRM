"""radar_service.py
成效雷達與 CSM 續約決策領域服務深模組 (Effectiveness Radar & CSM Decision Service)。

職責：
1. 結合課次基準與筆記關鍵字加權，自動判定學員 AI 導入四階段 (AI Import Stage)。
2. 計算距離最後上課天數與微任務卡推進狀態，評估留存與續約訊號 (Retention Signal)。
3. 偵測末次課堂 3 張微行動卡是否停滯 (>14天未開課且未跟進)。
4. 自動對接產品階梯矩陣 (Product Ladder Mapping) 並產出提案建議。
5. 生成客製化「7 天追蹤五問」一鍵複製關懷話術。
6. 彙總全體學員成效雷達並產出統計戰情指標。
"""

from __future__ import annotations

import re
from datetime import datetime, date, timezone
from typing import Any, Optional

from data_gateway import StudentDataGateway
from note_service import extract_micro_action_cards
from schemas.radar import (
    EffectivenessRadarItem,
    ProductRecommendation,
    CSMFollowupRecord,
)


# ── AI 導入四階段特徵關鍵字詞典 ──────────────────────────────────────────
STAGE_KEYWORDS = [
    (
        "AI OS系統",
        "知識分身、團隊流程協同與系統化商業變現",
        ["ai os", "分身", "agent", "架構", "團隊", "自動化工作流", "mcp", "codex", "管造", "系統化"],
        7,
    ),
    (
        "MVP自動化",
        "個人 AI 工作流、快速輸入流與第一項自動化產出",
        ["工作流", "自動化", "輸入流", "語音流", "typeless", "捷徑", "shortcut", "mvp", "輸出閉環", "腳本"],
        5,
    ),
    (
        "核心提示詞",
        "Prompt 結構化框架、逐字稿提煉與知識庫白板",
        ["prompt", "提示詞", "chatgpt", "claude", "gemini", "逐字稿", "heptabase", "白板", "卡片", "雙向連結"],
        3,
    ),
    (
        "數位地基",
        "核心開機環境、檔案命名、GTD 與跨裝置同步基礎",
        ["環境", "桌面", "finder", "資料夾", "檔名", "gtd", "同步", "密碼", "備份", "icloud", "開機"],
        1,
    ),
]


def calculate_days_since(date_str: Optional[str], ref_date: Optional[date] = None) -> int:
    """計算指定日期字串距今（或基準日）的天數。"""
    if not date_str:
        return 999
    date_str = str(date_str).strip()
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", date_str)
    if not match:
        return 999
    try:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        target_d = date(y, m, d)
        today = ref_date or date.today()
        diff = (today - target_d).days
        return max(0, diff)
    except (ValueError, OverflowError):
        return 999


def determine_ai_import_stage(
    lessons_count: int,
    cycle_lesson: int,
    recent_notes_text: str = "",
) -> tuple[str, str]:
    """判定 AI 導入階段與詳細成熟度說明（課次基準 + 關鍵字語意加權）。"""
    lower_text = recent_notes_text.lower()

    # 1. 課次基準判斷
    if cycle_lesson in (1, 2) and lessons_count <= 4:
        base_stage = "數位地基"
        base_detail = "核心開機環境、檔案命名、GTD 與跨裝置同步基礎"
    elif cycle_lesson in (3, 4) or (lessons_count <= 8):
        base_stage = "核心提示詞"
        base_detail = "Prompt 結構化框架、逐字稿提煉與知識庫白板"
    elif cycle_lesson in (5, 6) or (lessons_count <= 16):
        base_stage = "MVP自動化"
        base_detail = "個人 AI 工作流、快速輸入流與第一項自動化產出"
    else:
        base_stage = "AI OS系統"
        base_detail = "知識分身、團隊流程協同與系統化商業變現"

    # 2. 關鍵字加權修正（若近三堂強烈命中高階關鍵字且堂數足夠）
    for stage_name, stage_detail, keywords, min_lesson in STAGE_KEYWORDS:
        hit_count = sum(1 for kw in keywords if kw in lower_text)
        if hit_count >= 2 and lessons_count >= min_lesson:
            return stage_name, stage_detail

    return base_stage, base_detail


def extract_primary_pain(recent_notes_text: str) -> str:
    """從近期筆記中萃取核心痛點或操作卡點。"""
    PAIN_PATTERNS = [
        ("密碼與帳號同步問題", ["密碼", "帳號", "無法登入", "換裝置"]),
        ("檔案混亂與找不到資料", ["找不到", "檔案混亂", "散落", "未整理"]),
        ("快捷鍵操作生疏與依賴滑鼠", ["快捷鍵", "不熟練", "生疏", "滑鼠", "慢"]),
        ("AI 提示詞缺乏背景前情提要", ["提示詞", "回答太籠統", "不精確", "chatgpt 亂答"]),
        ("工作成果散落未建立閉環", ["散落", "沒有存", "中斷", "未能持續"]),
        ("重複繁瑣勞動佔據過多時間", ["重複", "繁瑣", "花太多時間", "手動整理"]),
    ]
    lower_t = recent_notes_text.lower()
    for pain_label, triggers in PAIN_PATTERNS:
        if any(trig in lower_t for trig in triggers):
            return pain_label
    return "日常操作穩定，引導落實每日微習慣與實踐輸出"


def evaluate_retention_signal(
    days_since_last: int,
    task_stale: bool,
    cycle_lesson: int,
) -> tuple[str, str, str]:
    """評估學員留存與續約訊號代碼、文字與前端徽章樣式。"""
    if cycle_lesson >= 7:
        return "upgrade_ready", "待續約 / 升級評估 🚀", "badge-primary"
    if days_since_last > 30:
        return "at_risk", "高流失風險 🔴", "badge-danger"
    if days_since_last > 14 or task_stale:
        return "attention", "需要關心 🟡", "badge-warning"
    return "stable", "穩定推進 🟢", "badge-success"


def match_product_ladder(
    ai_stage: str,
    primary_pain: str,
    lessons_count: int,
    cycle_lesson: int,
) -> ProductRecommendation:
    """自動對接產品階梯推薦矩陣。"""
    if ai_stage == "數位地基" or cycle_lesson in (1, 2):
        return ProductRecommendation(
            title="數位基礎救援包",
            slug="digital-foundation",
            pitch_message="針對檔案與環境混亂，一對一協助建立零摩擦開機桌面、GTD 檔案目錄與跨裝置無縫同步底座。",
        )
    if ai_stage == "核心提示詞" or cycle_lesson in (3, 4):
        return ProductRecommendation(
            title="90 分鐘工作流啟動課",
            slug="workflow-starter",
            pitch_message="針對日常重複溝通與撰寫痛點，導入結構化 Prompt 框架與語音快速輸入流，90 分鐘帶出第一個高質量產出。",
        )
    if ai_stage == "MVP自動化" or cycle_lesson in (5, 6):
        return ProductRecommendation(
            title="MVP 工作流建置",
            slug="mvp-workflow",
            pitch_message="針對固定高頻痛點建立專屬 AI Agent 與端到端資料流水線，釋放每週 5~10 小時重複繁重勞動。",
        )
    return ProductRecommendation(
        title="90 天 AI OS 陪跑",
        slug="ai-os-coaching",
        pitch_message="適合有穩定業務或團隊管理需求，進行深度人機協同營運重塑、個人知識分身打造與全流程數位轉型。",
    )


def build_7day_followup_copy(
    student_name: str,
    micro_action_cards: list[dict[str, Any]],
) -> str:
    """產生客製化 7 天追蹤五問關懷文字。"""
    task_bullets = []
    for idx, card in enumerate(micro_action_cards[:3], start=1):
        content = card.get("content") or ""
        card_type = card.get("type", "練習")
        if content:
            task_bullets.append(f"{idx}. 【{card_type}】{content}")

    if not task_bullets:
        tasks_text = "上次課堂討論的各項練習重點與日常習慣"
    else:
        tasks_text = "上次課堂我們整理的落地練習目標：\n" + "\n".join(task_bullets)

    msg = (
        f"{student_name} 你好！我是蔡教練 😊\n"
        f"這週日常操作與工作練習還順利嗎？\n\n"
        f"回顧一下{tasks_text}\n\n"
        f"想了解一下你的落地進度：\n"
        f"1. 上次這幾個練習卡，你目前完成了哪一步？\n"
        f"2. 哪一步最卡或遇到阻礙？\n"
        f"3. 有沒有產出可重複使用的檔案、提示詞或筆記？\n"
        f"4. 這個工作流有沒有幫你省到時間？\n"
        f"5. 下次上課最想優先解決哪一個流程？\n\n"
        f"有任何卡點隨時在 LINE 發訊息給我，我們隨時調整！"
    )
    return msg


def build_full_effectiveness_radar(
    gateway: StudentDataGateway,
    ref_date: Optional[date] = None,
) -> dict[str, Any]:
    """全局建構並聚合學員成效雷達總帳與統計指針。"""
    students = gateway.load_students()
    records_list = gateway.load_all_teaching_records()

    # 讀取現有 radar 快取以保留教練歷史跟進狀態
    cached_radar = gateway.get_effectiveness_radar_data()
    followup_map = {}
    for item in cached_radar.get("items", []):
        sid = item.get("student_id")
        if sid and "followup" in item:
            followup_map[sid] = item["followup"]

    student_records_map: dict[str, list[dict[str, Any]]] = {}
    for r in records_list:
        if isinstance(r, dict):
            sid = r.get("student_id")
            if sid:
                student_records_map.setdefault(sid, []).append(r)

    radar_items: list[dict[str, Any]] = []

    # 統計計數器
    total_tracked = 0
    stable_count = 0
    attention_count = 0
    at_risk_count = 0
    upgrade_ready_count = 0
    stale_tasks_count = 0

    for s in students:
        if not isinstance(s, dict):
            continue
        # 僅追蹤 active 活躍學員；典藏 (memorial) 與休學 (paused) 徹底脫鉤靜音
        if s.get("status") in ("memorial", "paused"):
            continue
        sid = s.get("id") or ""
        name = s.get("name") or "未命名學員"
        cnt = s.get("lessons_count", 0)
        cycle = s.get("current_cycle_lesson")
        if cycle is None:
            cycle = ((cnt % 8) or 8) if cnt > 0 else 1

        latest_d = s.get("latest_date") or s.get("last_lesson_date") or ""
        days_since = calculate_days_since(latest_d, ref_date=ref_date)

        # 取得學員筆記
        notes = student_records_map.get(sid, [])
        # 依日期降序
        notes_sorted = sorted(notes, key=lambda x: str(x.get("date", "")), reverse=True)
        recent_notes = notes_sorted[:3]
        recent_text = " ".join([
            f"{n.get('title', '')} {n.get('preview', '')} {n.get('description', '')}"
            for n in recent_notes
        ])

        # 末次筆記與微任務卡
        last_note = notes_sorted[0] if notes_sorted else {}
        last_note_title = last_note.get("title", "")
        last_note_content = f"{last_note_title} {last_note.get('preview', '')} {last_note.get('content', '')}"

        extracted_cards = extract_micro_action_cards(last_note_content if last_note_content.strip() else name)
        cards_list = [
            {"type": "微習慣", "title": "微習慣塑造", "content": extracted_cards.get("micro_habit", "")},
            {"type": "關鍵動作", "title": "落地關鍵動作", "content": extracted_cards.get("key_action", "")},
            {"type": "每週小勝", "title": "每週驗收小勝", "content": extracted_cards.get("weekly_win", "")},
        ]

        # 任務停滯偵測：若距上次上課 > 14 天且非剛開課
        task_is_stale = (days_since > 14) and (cnt > 0)
        if task_is_stale:
            stale_tasks_count += 1

        # 判定 AI 導入階段
        stage_name, stage_detail = determine_ai_import_stage(cnt, cycle, recent_text)
        primary_pain = extract_primary_pain(recent_text)

        # 評估留存訊號
        signal_code, signal_text, badge_class = evaluate_retention_signal(
            days_since_last=days_since,
            task_stale=task_is_stale,
            cycle_lesson=cycle,
        )

        # 累加指標
        total_tracked += 1
        if signal_code == "stable":
            stable_count += 1
        elif signal_code == "attention":
            attention_count += 1
        elif signal_code == "at_risk":
            at_risk_count += 1
        elif signal_code == "upgrade_ready":
            upgrade_ready_count += 1

        # 推薦產品階梯
        prod_rec = match_product_ladder(stage_name, primary_pain, cnt, cycle)

        # 7 天追蹤關懷話術
        followup_copy = build_7day_followup_copy(name, cards_list)

        # CSM 回訪歷史
        cached_followup = followup_map.get(sid, {})
        followup_obj = CSMFollowupRecord(
            status=cached_followup.get("status", "pending"),
            last_contacted_date=cached_followup.get("last_contacted_date"),
            next_followup_date=cached_followup.get("next_followup_date"),
            coach_notes=cached_followup.get("coach_notes", ""),
            updated_at=cached_followup.get("updated_at", ""),
        )

        item = EffectivenessRadarItem(
            student_id=sid,
            name=name,
            lessons_count=cnt,
            current_cycle_lesson=cycle,
            latest_date=latest_d,
            days_since_last=days_since,
            ai_import_stage=stage_name,
            ai_stage_detail=stage_detail,
            primary_pain=primary_pain,
            micro_action_cards=cards_list,
            task_staleness_warning=task_is_stale,
            retention_signal=signal_code,
            retention_signal_text=signal_text,
            retention_badge_class=badge_class,
            product_recommendation=prod_rec,
            followup=followup_obj,
            followup_copy=followup_copy,
        )
        radar_items.append(item.model_dump())

    # 排序規則：待續約與高流失排前，其次為需關心，再依最近上課天數升序
    SIGNAL_PRIORITY = {
        "upgrade_ready": 0,
        "at_risk": 1,
        "attention": 2,
        "stable": 3,
    }

    def _sort_key(it: dict[str, Any]):
        prio = SIGNAL_PRIORITY.get(it.get("retention_signal", "stable"), 99)
        return (prio, it.get("days_since_last", 999))

    radar_items.sort(key=_sort_key)

    now_iso = datetime.now(timezone.utc).isoformat()
    result = {
        "generated_at": now_iso,
        "summary": {
            "total_tracked": total_tracked,
            "stable_count": stable_count,
            "attention_count": attention_count,
            "at_risk_count": at_risk_count,
            "upgrade_ready_count": upgrade_ready_count,
            "stale_tasks_count": stale_tasks_count,
        },
        "items": radar_items,
    }

    # 持久化快取
    gateway.save_effectiveness_radar_data(result)
    return result
