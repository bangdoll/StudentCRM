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
    
    1. 📱 1 個小習慣 (One Micro-Habit) - 每日 3 分鐘日常無痛練習
    2. ⚡ 1 個肌肉記憶 (Key Action / Shortcut) - 實戰高頻快捷鍵或核心手勢
    3. 🎯 本週 1 個小成就 (Weekly Win) - 具體可落地的成效驗收
    """
    clean_text = clean_markdown_frontmatter(content)
    lower = clean_text.lower()
    full_title = (title or "").lower()
    clean_title = title.split(".")[-1].replace("#", "").strip() or "數位管理"

    tool_keywords = {
        "raindrop": ["raindrop", "雲端書籤", "書籤分類", "書籤"],
        "typeless": ["typeless", "語音輸入", "字典同步", "vip 歷史", "字典"],
        "heptabase": ["heptabase", "白板", "卡片筆記", "雙向連結"],
        "ai_coding": ["claude code", "skills", "ask matt", "vibe coding", "anygravity", "ai coding", "dgx", "cursor"],
        "chatgpt": ["chatgpt", "prompt", "提示詞", "gpt-4", "gpt-o1", "對話模式"],
        "gdrive": ["google drive", "星號專區", "雲端硬碟", "已加星號", "試算表", "雲端檔案"],
        "shortcuts": ["快速鍵", "快捷鍵", "command +", "cmd +", "視窗管理", "觸控板", "手勢"],
        "ecommerce_security": ["蝦皮", "淘寶", "coupang", "酷澎", "信用卡資安", "debit", "otp 驗證", "網購"],
        "telegram": ["telegram", "檔案過期", "saved messages"],
        "vision_health": ["眼鏡", "雷鳥", "護眼", "視覺負擔", "螢幕疲勞"],
        "automation": ["捷徑", "自動化", "python", "腳本", "computer use"],
        "youtube_learning": ["youtube", "逐字稿", "影片整理", "影片筆記"],
    }

    tool_templates = {
        "raindrop": {
            "habit": "開啟 Chrome 時養成習慣先看第一個分頁的 Raindrop 書籤，不再透過 Google 搜尋重複找網站",
            "action": "點擊網址列右側 Raindrop 雲朵圖示 ➔ 選擇分類資料夾 ➔ 點空白處完成雲端儲存",
            "win": "獨立將常用工作與生活網站分門別類存入 Raindrop，實現手機與電腦跨裝置完全同步",
        },
        "typeless": {
            "habit": "打字遇到常錯人名或專有名詞，順手打開 Typeless 首頁字典「羽毛」圖示新增正確詞彙",
            "action": "日常輸入長按語音鍵流暢口述想法，鬆開後由 AI 自動排版與修正標點",
            "win": "在日常工作與通訊軟體中，以 Typeless 替代手動打字完成 3 篇長文輸入與字典擴充",
        },
        "heptabase": {
            "habit": "晨間開機第一件事：打開 Heptabase 晨間白板，寫下今日核心 3 張執行卡，以雙向連結梳理思路",
            "action": "在白板空白處「雙擊滑鼠」秒開新卡片；按住空白鍵可自由拖曳畫布視野",
            "win": "完成 1 個主題的白板雙向連結整理，產出結構清晰、隨時可調度的個人知識網絡",
        },
        "ai_coding": {
            "habit": "遇到程式重構或自動化需求，先用結構化 Skill / Ask Matt 提煉架構規格，不盲目貼代碼",
            "action": "在終端機或編輯器中運用斜線指令（/）精準調度專案專屬 Skill 與驗收腳本",
            "win": "在本地開發環境成功跑通一次 AI Agent 技能配置，並將輸出產物通過自動化測試",
        },
        "chatgpt": {
            "habit": "遇到複雜分析或長文撰寫，先在 ChatGPT 建立專屬對話並提供明確的 Context 背景資訊",
            "action": "掌握「角色設定 ＋ 背景目標 ＋ 限制條件 ＋ 輸出格式」四步結構化提示詞架構",
            "win": "建立屬於自己的 1 組高頻工作提示詞範本，並在實際業務中成功產出一份高質量交付物",
        },
        "gdrive": {
            "habit": "下班前將重要試算表與檔案按右鍵「新增至已加星號專區」，確保跨裝置 3 秒內秒開",
            "action": "在檔案列表選取常用檔案 ➔ 按右鍵 ➔「整理」➔「新增至已加星號專區」",
            "win": "完成工作雲端硬碟的常用表星號標記與分類清理，徹底告別資料夾層層翻找",
        },
        "shortcuts": {
            "habit": "操作應用程式時多讓雙手停留在鍵盤上，有意識地刻意練習快速鍵，減少使用滑鼠",
            "action": "熟練運用 Command + W (關閉分頁) 與 Command + Tab (快速切換 App) 流暢切換",
            "win": "在工作流程中全程運用課堂快速鍵清單進行視窗切換與複製貼上，工作節奏顯著提升",
        },
        "ecommerce_security": {
            "habit": "電商網購與重要網站登入時堅持「密碼與 OTP 簡訊安全碼手動輸入，不口述給語音工具」",
            "action": "結帳時改用低額度專用網購卡或 Visa 金融卡，並仔細核對簡訊驗證碼金額與平台",
            "win": "完成一次小額電商購物安全流程實測，確保付款卡片風險可控且個資登錄完整",
        },
        "telegram": {
            "habit": "重要教學檔案、大型影片與工作素材優先存入 Telegram 專屬收藏夾，防範過期失效",
            "action": "善用 Telegram「Saved Messages（已儲存訊息）」將手機拍下的靈感秒傳到電腦",
            "win": "建立個人的 Telegram 雲端素材庫，成功完成 3 份重要文件的跨裝置傳遞與永久保存",
        },
        "vision_health": {
            "habit": "使用 AI 語音或輔助設備進行長文聆聽，每專注 30 分鐘讓雙眼離開螢幕進行遠眺深呼吸",
            "action": "善用系統深色模式與文字放大捷徑，主動調整工作視窗至最舒適閱讀比例",
            "win": "建立無螢幕負擔的 AI 語音學習與工作流程，顯著減輕一日工作後的眼睛疲勞感",
        },
        "automation": {
            "habit": "每天在固定情境觸發一次課堂配置之自動化工作流，將重複點擊動作轉化為系統自動執行",
            "action": "設定 iPhone 背面輕點兩下或捷徑小工具，一鍵啟動高頻自動化任務",
            "win": "成功在日常生活中實際觸發並使用 3 次自動化捷徑工作流，節省日常零碎時間",
        },
        "youtube_learning": {
            "habit": "遇到優質教學影片不只被動觀看，習慣取得逐字稿並用 AI 提煉核心骨架存入筆記",
            "action": "利用瀏覽器外掛或捷徑工具，一鍵擷取 YouTube 影片時間軸與關鍵段落筆記",
            "win": "將 1 支長篇教學影片轉化為具備可執行步驟的 Markdown 實戰筆記並完成實作",
        },
    }

    # 工具評分計算
    scores: dict[str, int] = {}
    for tool, kws in tool_keywords.items():
        score = 0
        for kw in kws:
            score += full_title.count(kw) * 15
            score += lower.count(kw)
        if score > 0:
            scores[tool] = score

    sorted_tools = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_tools[0][0] if sorted_tools else "general"
    secondary = sorted_tools[1][0] if len(sorted_tools) > 1 else None

    # 特殊快捷鍵比對
    shortcut_match = re.search(r"(?:Command|Cmd|Ctrl|Option)\s*\+\s*[A-Za-z0-9]+[^\n]{0,35}", clean_text)
    
    # 筆記內文是否有明確的「習慣/每天/原則」具體句子
    habit_match = re.search(r"(?:習慣|每天|每日|原則)[：:、\s]{0,2}([^\n。；]{12,45})", clean_text)
    extracted_habit = habit_match.group(1).strip("*-# ") if habit_match else None
    if extracted_habit and any(bad in extracted_habit for bad in ["不是", "如果", "可能", "以為", "只有", "無法"]):
        extracted_habit = None

    # 筆記內文是否有明確的「下一步/目標/練習」
    win_match = re.search(r"(?:下一步|後續追蹤|目標|實作練習)[：:、\s]{0,2}([^\n。；]{12,50})", clean_text)
    extracted_win = win_match.group(1).strip("*-# ") if win_match else None
    if extracted_win and any(bad in extracted_win for bad in ["不是", "如果", "可能", "以為", "只有", "無法"]):
        extracted_win = None

    tpl = tool_templates.get(primary)
    if tpl:
        habit_text = f"課堂習慣建立：{extracted_habit}" if extracted_habit else tpl["habit"]
        
        if shortcut_match and primary in ["shortcuts", "heptabase", "ai_coding", "gdrive"]:
            shortcut_text = f"掌握實戰快速鍵：{shortcut_match.group(0).strip('*-# ')}"
        else:
            shortcut_text = tpl["action"]
            
        win_text = f"本週實踐目標：{extracted_win}" if extracted_win else tpl["win"]
    else:
        habit_text = f"每日開機複習「{clean_title}」核心觀念，融入日常工作習慣"
        shortcut_text = f"掌握實戰快速鍵：{shortcut_match.group(0).strip('*-# ')}" if shortcut_match else "掌握 Command + Space (Spotlight) 秒開應用程式與搜尋本機檔案"
        win_text = f"獨立完成「{clean_title}」課堂實作演練，向教練回饋 1 個具體效率提升體驗"

    # 若有顯著次要工具且不同，融合到每週成就中增加層次與豐富度
    if secondary and secondary in tool_templates and secondary != primary and scores.get(secondary, 0) >= 8:
        if secondary == "telegram":
            win_text += "；並同步建立 Telegram 雲端素材庫防範過期。"
        elif secondary == "ecommerce_security":
            win_text += "；並手動核對網購付款與 OTP 簡訊安全設定。"
        elif secondary == "typeless":
            win_text += "；並同步以 Typeless 語音輸入擴充常用專有字典。"
        elif secondary == "raindrop":
            win_text += "；並將工作常用網站同步收藏至 Raindrop 雲端書籤。"
        elif secondary == "chatgpt":
            win_text += "；並同步運用 ChatGPT 梳理長文與分析脈絡。"
        elif secondary == "youtube_learning":
            win_text += "；並同步將教學影片轉成 Markdown 實戰筆記。"

    return {
        "micro_habit": habit_text,
        "key_action": shortcut_text,
        "weekly_win": win_text,
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
