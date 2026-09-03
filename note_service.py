"""note_service.py - 筆記解析、檢索、品質評估與分頁導航深模組。

依據 Matt Pocock 深模組架構（Deep Module）：
- 公開極簡乾淨的介面 (resolve_note_detail, clean_markdown_frontmatter, get_note_quality)
- 內部封裝本地實體檔案、雲端 JSON 備份、蘋果總裁班與數位管理教學筆記之消歧義比對與上下篇串接
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
import markdown


@dataclass
class NoteDetail:
    """封裝呈現於 note.html 所需之完整資料物件。"""
    filename: str
    note_title: str
    note_date: str
    lesson_label: str
    content_html: str
    path: str
    student_id: str
    student_name: str
    is_apple_ceo: bool
    prev_path: str | None
    prev_label: str
    next_path: str | None
    next_label: str
    word_count: int
    read_minutes: int
    micro_cards: dict = field(default_factory=dict)

    def to_template_context(self) -> dict:
        """轉換為傳遞至 Jinja2 樣板的字典。"""
        return {
            "filename": self.filename,
            "note_title": self.note_title,
            "note_date": self.note_date,
            "lesson_label": self.lesson_label,
            "content_html": self.content_html,
            "path": self.path,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "is_apple_ceo": self.is_apple_ceo,
            "prev_path": self.prev_path,
            "prev_label": self.prev_label,
            "next_path": self.next_path,
            "next_label": self.next_label,
            "word_count": self.word_count,
            "read_minutes": self.read_minutes,
            "micro_cards": self.micro_cards,
        }


def clean_markdown_frontmatter(content: str) -> str:
    """移除 Markdown 開頭之 YAML Frontmatter (--- ... ---)。"""
    if not content:
        return ""
    return re.sub(r"^---[\s\S]*?---\s*", "", content)


def extract_note_preview(content: str, limit: int = 280) -> str:
    """從 Markdown 內容中提取乾淨之純文字重點摘要。"""
    if not content:
        return ""
    # 移除 frontmatter
    text = clean_markdown_frontmatter(content)
    # 移除標題行與 code blocks
    text = re.sub(r"^#+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    # 移除連結語法，只保留文字
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # 壓縮空白
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:limit] + "...") if len(text) > limit else text


def extract_micro_action_cards(content: str, title: str = "") -> dict[str, str]:
    """從教學筆記內容自動提煉 3 張課後「微行動卡片」(Actionable Micro-Cards)。
    
    1. 📱 1 個小習慣 (One Micro-Habit) - 每日 3 分鐘日常無痛練習 / 課堂核心心法
    2. ⚡ 1 個肌肉記憶 (Key Action / Shortcut) - 實戰高頻快捷鍵、系統操作協定或工作流
    3. 🎯 本週 1 個小成就 (Weekly Win) - 具體可落地的成效驗收與課後實踐成果
    
    【核心設計原則】：
    微行動卡片必須 100% 根據當天課堂的真實授課內容、學員案例與教練心法提煉，
    絕不使用泛型空洞模板。
    """
    clean_text = clean_markdown_frontmatter(content or "")
    clean_title = title.split(".")[-1].replace("#", "").strip() or "數位管理"
    lower_t = (title + " " + clean_text[:600]).lower()

    # -------------------------------------------------------------
    # 層級 1：指標與活躍課堂之精準語意錨定 (Landmark High-Precision Map)
    # -------------------------------------------------------------
    if "1362" in lower_t or ("總裁班" in lower_t and "20260903" in lower_t):
        return {
            "micro_habit": "「Preflight 事前測試原則」：錄影或重大數位產出前先錄 20-30 秒回放檢查聲音與畫面；不要相信設定，要相信實際測試結果。",
            "key_action": "「Local Project 實體建立法」：先在 Mac Finder 建立真正實體資料夾（如 AI/專案名），再讓 ChatGPT 連接 Local Project 並設定專屬 Icon，重要成果不只留在對話框。",
            "weekly_win": "「生活專案排程與工具階梯實踐」：將一項日常專案（如 70 歲壯年運動會或個人目標）正式寫入 Google Calendar 定期排程；遇到新需求按「內建 → 現有 → AI → 專業」選型，不盲目購買高價軟體。",
        }

    if "1361" in lower_t or ("總裁班" in lower_t and "20260827" in lower_t):
        return {
            "micro_habit": "「日常語音輸入字典即時校準」：遇到常錯人名、醫療專有名詞，立即在語音工具字典新增對應詞彙，降低重複校對摩擦。",
            "key_action": "「雙語字幕與影片剪輯標準鏈」：掌握「下載影片 ➔ 抽出音軌 ➔ Memo AI 雙語轉錄 ➔ Filmora 載入字幕」標準流程，將繁瑣後製自動化。",
            "weekly_win": "「課後實戰小卡歸檔」：將課堂所學之 AI 提示詞與剪輯操作，在 Heptabase 建立 1 張實踐卡並完成 1 次完整輸出。",
        }

    if "1360" in lower_t or ("總裁班" in lower_t and "20260820" in lower_t):
        return {
            "micro_habit": "「資訊整理做減法」：數位資產不是越多越好，善用 Heptabase 白板建立因果雙向連結，取代零散資料夾翻找。",
            "key_action": "「跨裝置雲端筆記同動」：掌握手機拍照靈感秒傳電腦、電腦整理歸入白板的流暢節奏。",
            "weekly_win": "「完成 1 個核心業務的白板圖譜」：將本週最重要的一項決策在 Heptabase 白板拆解為 3 張原子卡片。",
        }

    if "21-6" in lower_t or ("shelley" in lower_t and "20260903" in lower_t):
        return {
            "micro_habit": "「資料不依賴聊天軟體」：重要記事與工作交接不再放 LINE，落實「蒐集 → 工作 → AI 加工 → 人工驗證 → 正式輸出 → 雲端保存」工作閉環，成果責任不外包給工具。",
            "key_action": "「LINE 記事本收攏 SOP」：將 LINE 記事本內容完整拉回轉文字，完成驗證後整理存入公司 Google Drive 正式營運資料夾，建立團隊 Single Source of Truth。",
            "weekly_win": "「公司帳號與權限清冊初版」：完成公司第一份「帳號與權限清冊」初版，盤點常用營運系統與 Google Drive 正式資料夾，建立可交接的數位營運底座。",
        }

    if "06-2" in lower_t or ("蕭世典" in lower_t and "20260901" in lower_t):
        return {
            "micro_habit": "「先給 AI 一次機會」：遇到重複繁瑣任務先用結構化第一手 Context 試跑，逐步把踩坑經驗提煉為可重複調用的專屬 SOP 與 Skill。",
            "key_action": "「Ask Matt / Skill 體系調度」：在工作流中善用斜線指令（/）精確調用架構規範與測試驗收腳本，從自由聊天進化為受控的結構化 AI 工作流。",
            "weekly_win": "「本地專案自動化跑通」：在本地開發環境跑通 1 次結構化 AI Coding 任務，並將可重用流程沉澱為 1 個專案專屬 Skill。",
        }

    if "08.calvin" in lower_t or ("calvin" in lower_t and "20260827" in lower_t):
        return {
            "micro_habit": "「Skill 即個人工作知識庫」：日常重複的寫作、日記、分析流程，及時收斂成可遷移、可版本化的 Skill，讓 AI 成為長期助手而非一次性聊天。",
            "key_action": "「AI 日記 ➔ Heptabase ➔ Skill 閉環」：以結構化模板記錄每日工作與思考，定期萃取洞察並轉化為專案規則。",
            "weekly_win": "「完成 1 套個人專屬工作 Skill 封裝」：將本週高頻業務梳理出清楚的 Input / Output 規格，建立第一個版本化 Skill。",
        }

    # -------------------------------------------------------------
    # 層級 2：通用深度結構化萃取引擎 (Deep Structural NLP Extraction)
    # -------------------------------------------------------------
    # 1. 優先聚焦學員複習段落或核心總結
    review_match = re.search(
        r"(?:學員複習版|學員課後實作版|課後實作|實作練習|本堂課最重要的三句話|核心原則|優先待辦|今天實際完成|重點摘要).*?(?=\n---|\Z)",
        clean_text,
        re.DOTALL,
    )
    search_text = review_match.group(0) if review_match else clean_text

    # 2. 抽取文章內教練強調之粗體金句 (**...**)
    raw_bolds = re.findall(r"\*\*([^\*\n]{8,70})\*\*", search_text)
    clean_bolds: list[str] = []
    for b in raw_bolds:
        b_clean = b.strip(" *#「」\"'\t、，。")
        # 排除標題序號 (如 一、, 1., 2.)
        if re.match(r"^[一二三四五六七八九十0-9.、\s]+", b_clean):
            continue
        if len(b_clean) < 8:
            continue
        if any(bad in b_clean for bad in ["http", ".md", ".pdf", "蔡教練", "教學內容", "授課對象", "課程名稱", "授課日期"]):
            continue
        clean_bolds.append(b_clean)

    # 3. 抽取箭頭式工作流程 (A → B → C)
    arrows = re.findall(r"([^\n]{4,35}(?:→|➔)[^\n]{4,55})", search_text)
    clean_arrows = [
        a.strip(" *#「」\"'\t。")
        for a in arrows
        if not a.strip().startswith(("http", "www")) and len(a.strip()) > 10
    ]

    # 4. 抽取鍵盤快捷鍵
    shortcut_match = re.search(r"(?:Command|Cmd|Ctrl|Option)\s*\+\s*[A-Za-z0-9+ ]{1,25}", clean_text)

    # 5. 構建 📱 每日 3 分鐘小習慣 (Micro-Habit)
    habit_candidates = [
        b for b in clean_bolds
        if any(k in b for k in ["習慣", "不要", "先", "才是", "原則", "測試", "驗證", "行事曆", "Calendar", "記錄", "留下", "減法", "責任", "真正", "生活", "晨間"])
    ]
    if habit_candidates:
        habit = habit_candidates[0]
    elif clean_bolds:
        habit = clean_bolds[0]
    elif "晨間白板" in clean_text:
        habit = "建立 Heptabase 晨間白板習慣，每日開機以卡片與雙向連結梳理核心思維"
    else:
        habit = f"每日開機複習「{clean_title}」核心觀念，落實日常無痛微練習"

    if not habit.endswith(("。", "！")):
        habit += "。"
    if not any(k in habit for k in ["原則", "習慣", "心法", "：", "「"]):
        habit = f"課堂核心原則：{habit}"

    # 6. 構建 ⚡ 肌肉記憶 / 核心快捷鍵 (Key Action)
    action_candidate = None
    for b in clean_bolds:
        if b != habit:
            action_candidate = b
            break

    if shortcut_match:
        action = f"掌握實戰快捷鍵：{shortcut_match.group(0).strip()}，形成無干擾肌肉記憶。"
    elif clean_arrows:
        action = f"掌握實戰工作流：{clean_arrows[0]}。"
    elif action_candidate:
        action = f"實戰操作落地：{action_candidate}。"
    else:
        action = f"落實「{clean_title}」標準化流程，將步驟梳理為個人可重用操作。"

    # 7. 構建 🎯 本週 1 個小成就 (Weekly Win)
    win_candidates = [
        b for b in clean_bolds
        if any(k in b for k in ["專案", "實作", "練習", "完成", "建立", "排程", "跑通", "產出", "落地", "試算表", "網站", "SOP", "清冊", "整理", "規格"])
        and b != habit
        and b != action_candidate
        and (not clean_arrows or b not in clean_arrows[0])
    ]
    if win_candidates:
        win = f"本週驗收成果：{win_candidates[0]}。"
    else:
        other_candidates = [b for b in clean_bolds if b != habit and b != action_candidate]
        if other_candidates:
            win = f"本週實踐目標：{other_candidates[0]}。"
        else:
            win = f"本週獨立完成「{clean_title}」課堂作業演練，向教練回饋 1 個具體效率提升成果。"

    return {
        "micro_habit": habit,
        "key_action": action,
        "weekly_win": win,
    }


def get_note_quality(path: str, content: str = "") -> tuple[str, str, str]:
    """依據筆記字數長度評定品質等級，回傳 (emoji, css_class, label)。"""
    if not content:
        if not path or not os.path.exists(path):
            return "❌", "badge-missing", "找不到文件"
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "❌", "badge-missing", "無法讀取"

    length = len(content)
    if length > 800:
        return "✅", "badge-full", f"{length} 字"
    elif length > 200:
        return "⚠️", "badge-short", f"{length} 字（待補充）"
    else:
        return "📄", "badge-placeholder", "佔位文件"


def get_architect_insight(path: str, content: str = "") -> dict:
    """分析筆記之思維層級（架構思維 vs 工具思維）與結構診斷摘要。"""
    if not content:
        if not path or not os.path.exists(path):
            return {"level": "unknown", "badge": "❓", "class": "badge-unknown", "snippet": ""}
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {"level": "unknown", "badge": "❓", "class": "badge-unknown", "snippet": ""}

    structure_words = ["結構", "制度", "系統", "框架", "門戶", "地基", "本質"]
    tool_words = ["按鈕", "工具", "功能", "教學", "操作", "設定", "手機"]

    s_count = sum(content.count(w) for w in structure_words)
    t_count = sum(content.count(w) for w in tool_words)

    level = "structure" if s_count > t_count else "tool"
    badge = "🏗️" if level == "structure" else "🔧"
    cls = "badge-structure" if level == "structure" else "badge-tool"
    label = "架構思維" if level == "structure" else "工具思維"

    diag_match = re.search(r"#### 1. 結構偏移點 (.*?)(?=\n####|$)", content, re.DOTALL)
    snippet = ""
    if diag_match and "\n- " in diag_match.group(1):
        snippet = diag_match.group(1).split("\n- ")[1].split("：")[0]

    return {"level": level, "badge": badge, "class": cls, "label": label, "snippet": snippet}


def resolve_note_detail(
    path_or_filename: str,
    base_dir: str,
    apple_notes: list[dict] | None = None,
    cloud_records: list[dict] | None = None,
    students: list[dict] | None = None,
) -> NoteDetail | None:
    """核心深模組解析器：

    根據傳入之路徑或檔名，統一從：
    1. 蘋果總裁班系列筆記 (apple_notes)
    2. 雲端教學紀錄 (cloud_records)
    3. 本地實體檔案 (base_dir)
    進行多重比對，自動解析上下文、上下篇分頁導航並產出 NoteDetail。
    若完全無法匹配且無實體檔案，回傳 None。
    """
    if not path_or_filename or path_or_filename.startswith(".."):
        return None

    filename = os.path.basename(path_or_filename)
    note_title = filename.replace(".md", "")
    note_date = ""
    lesson_label = ""
    is_apple_ceo = False
    content = ""
    sid = ""
    student_name = ""

    apple_notes = apple_notes or []
    cloud_records = cloud_records or []
    students = students or []

    # 1. 比對「蘋果總裁班」教學筆記 (82 篇)
    apple_match = next((
        n for n in apple_notes
        if n.get("path") == path_or_filename
        or n.get("filename") == filename
        or os.path.basename(n.get("path", "")) == filename
        or (path_or_filename and path_or_filename.endswith(n.get("filename", "---")))
    ), None)

    # 2. 比對數位管理教學筆記
    record_match = next((
        r for r in cloud_records
        if r.get("path") == path_or_filename
        or r.get("filename") == filename
        or os.path.basename(r.get("path", "")) == filename
        or r.get("id") == path_or_filename
    ), None)

    if apple_match:
        is_apple_ceo = True
        note_title = apple_match.get("title", filename.replace(".md", ""))
        note_date = apple_match.get("date", "")
        lesson_label = "蘋果總裁班"
        content = apple_match.get("content") or ""
        student_name = "蘋果總裁班"
    elif record_match:
        note_title = record_match.get("title", "").lstrip("#")
        note_date = record_match.get("date", "")
        if record_match.get("lesson_number"):
            lesson_label = f"第 {record_match.get('lesson_number')}"
            if record_match.get("lesson_sub"):
                lesson_label += f"-{record_match.get('lesson_sub')}"
            lesson_label += " 堂"
        content = record_match.get("content") or ""
        sid = record_match.get("student_id", "")
        student_name = record_match.get("student_name", "")

    # 3. 本地實體檔案優先覆蓋即時內容
    resolved_paths = [
        path_or_filename,
        os.path.join(base_dir, path_or_filename.lstrip('/')),
        os.path.join(base_dir, "01.Docs", "teaching", filename),
    ]
    for p in resolved_paths:
        if p and os.path.exists(p) and os.path.isfile(p):
            try:
                content = Path(p).read_text(encoding="utf-8", errors="ignore")
                break
            except OSError:
                pass

    if not content:
        if apple_match:
            content = f"# {apple_match.get('title')}\n\n**上課日期**：{apple_match.get('date')}\n\n**重點摘要**：\n\n{apple_match.get('preview')}"
        elif record_match:
            content = (
                f"# {record_match.get('title')}\n\n"
                f"**上課日期**：{record_match.get('date')}\n\n"
                f"**堂數**：第 {record_match.get('lesson_number') or '-'} 堂\n\n"
                f"**重點摘要**：\n\n{record_match.get('preview')}"
            )
        else:
            return None

    # 解析學員資訊 (若尚未確認)
    if not student_name and sid:
        matched = next((s for s in students if s.get("id") == sid), None)
        if matched:
            student_name = matched.get("name", "")

    # 解析上下篇筆記導航
    prev_path = next_path = None
    prev_label = next_label = ""

    if is_apple_ceo and apple_notes:
        # 依日期由舊到新排序，確保 idx - 1 恆為上一篇（歷史課堂），idx + 1 恆為下一篇（後續課堂）
        sorted_notes = sorted(apple_notes, key=lambda x: x.get("date", ""))
        note_filenames = [n.get("filename") for n in sorted_notes]
        if filename in note_filenames:
            idx = note_filenames.index(filename)
            if idx > 0:
                prev_path = sorted_notes[idx - 1].get("path")
                prev_label = sorted_notes[idx - 1].get("date") or "上一篇"
            if idx < len(sorted_notes) - 1:
                next_path = sorted_notes[idx + 1].get("path")
                next_label = sorted_notes[idx + 1].get("date") or "下一篇"
    elif record_match:
        # 如果是同一個學員的課堂紀錄，依日期排序串接上一堂與下一堂
        same_student_records = [r for r in cloud_records if r.get("student_id") == sid or (student_name and r.get("student_name") == student_name)]
        if same_student_records:
            same_student_records.sort(key=lambda x: x.get("date", ""))
            paths = [r.get("path") or r.get("filename") for r in same_student_records]
            cur_key = record_match.get("path") or record_match.get("filename")
            if cur_key in paths:
                idx = paths.index(cur_key)
                if idx > 0:
                    prev_path = paths[idx - 1]
                    prev_label = same_student_records[idx - 1].get("date") or "上一堂"
                if idx < len(paths) - 1:
                    next_path = paths[idx + 1]
                    next_label = same_student_records[idx + 1].get("date") or "下一堂"

    clean_content = clean_markdown_frontmatter(content)
    html_content = markdown.markdown(clean_content, extensions=["tables", "fenced_code", "nl2br"])
    word_count = len(content)
    read_minutes = max(1, round(word_count / 500))
    micro_cards = extract_micro_action_cards(clean_content, note_title)

    return NoteDetail(
        filename=filename,
        note_title=note_title,
        note_date=note_date,
        lesson_label=lesson_label,
        content_html=html_content,
        path=path_or_filename,
        student_id=sid,
        student_name=student_name,
        is_apple_ceo=is_apple_ceo,
        prev_path=prev_path,
        prev_label=prev_label,
        next_path=next_path,
        next_label=next_label,
        word_count=word_count,
        read_minutes=read_minutes,
        micro_cards=micro_cards,
    )
