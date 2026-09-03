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
    # 蘋果總裁班系列
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

    # 一對一核心學員系列
    if "21-6" in lower_t or ("shelley" in lower_t and "20260903" in lower_t):
        return {
            "micro_habit": "「資料不依賴聊天軟體」：重要記事與工作交接不再放 LINE，落實「蒐集 → 工作 → AI 加工 → 人工驗證 → 正式輸出 → 雲端保存」工作閉環，成果責任不外包給工具。",
            "key_action": "「LINE 記事本收攏 SOP」：將 LINE 記事本內容完整拉回轉文字，完成驗證後整理存入公司 Google Drive 正式營運資料夾，建立團隊 Single Source of Truth。",
            "weekly_win": "「公司帳號與權限清冊初版」：完成公司第一份「帳號與權限清冊」初版，盤點常用營運系統與 Google Drive 正式資料夾，建立可交接的數位營運底座。",
        }

    if "charlotte" in lower_t or "陳姐" in lower_t:
        return {
            "micro_habit": "「快速鍵是手段，工作流程才是目的」：在 Mac 桌面落實 Command + Tab 與多視窗平滑切換，減少依賴滑鼠層層點選的零碎摩擦。",
            "key_action": "「掌握五階工作鏈」：熟練「操作熟練 ➔ 資訊流動 ➔ 資料治理 ➔ AI 協作 ➔ 人工驗收」實踐架構，建立一人公司自驅工作流。",
            "weekly_win": "「個人桌面與 AI Work 整合實踐」：在本地資料夾與 ChatGPT Work 中獨立完成一組工作流演練，形成穩定肌肉記憶。",
        }

    if "張素幸" in lower_t or "素幸" in lower_t:
        return {
            "micro_habit": "「界定問題先於尋找解法」：在尋找任何數位工具前，先精確界定現況、目標、障礙與問題範圍，避免在錯誤問題上用力。",
            "key_action": "「數位入口治理收攏」：將分散的網站入口、帳號、裝置與付款方式收斂至單一清晰路徑，不再層層翻找。",
            "weekly_win": "「個人數位資料入口盤點」：完成常用網站、Booking 與付款帳號的跨裝置入口同步，落實高頻 Typeless 語音輸入。",
        }

    if "陳海陸" in lower_t or "海陸" in lower_t:
        return {
            "micro_habit": "「以解決真實生活問題為核心」：AI 不是讓人多學一堆繁雜功能，而是從「遇到問題 ➔ 找資訊 ➔ 判斷選項 ➔ 完成操作 ➔ 確認結果」建立問題解決閉環。",
            "key_action": "「前情提要結構化提煉」：掌握「角色背景 ＋ 具體限制 ＋ 輸出格式」提問結構，將會議或語音摘要一鍵匯出為結構化 Word 文件。",
            "weekly_win": "「完成 1 項生活數位決策」：運用 AI 輔助完成 1 次真實設備選型或流程排查，留下可追溯的驗收紀錄。",
        }

    if "lucia" in lower_t or "徐露華" in lower_t:
        return {
            "micro_habit": "「雲端即時使用，本地真正累積」：清晰劃分雲端對話與本地專案邊界，不讓重要工作成果散落在未整理的聊天室中。",
            "key_action": "「先建前情提要，再開始即時互動」：在 Finder 建立標準專案層級，讓 AI 在明確的背景脈絡下參與工作協作。",
            "weekly_win": "「本地專案工作區建立」：在 Finder 建立標準專案資料夾並連入工作模式，產出首份經過驗收的結構化交付物。",
        }

    if "kelly" in lower_t:
        return {
            "micro_habit": "「專案分工與環境防呆」：建立清晰的專案管理觀念，本地專案落地於實體檔案，雲端專案用於跨裝置輕量溝通。",
            "key_action": "「標準專案建立流程」：熟練「建立新專案 ➔ 建立實體資料夾 ➔ 選擇資料夾 ➔ 建立 Project」之標準動作鏈。",
            "weekly_win": "「AI 工作環境全面梳理」：完成 ChatGPT 電腦版重新配置與專案資料夾建立，獨立跑通 1 次專案建立與輸出。",
        }

    if "julie" in lower_t or "陳怡君" in lower_t:
        return {
            "micro_habit": "「分步推進，不求一次到位」：像專業軟體團隊一樣分步落實：需求訪談 ➔ 規格 ➔ 原型 ➔ 開發 ➔ 測試 ➔ 修正 ➔ 部署。",
            "key_action": "「醫療資料結構化鏈條」：落實「PDF ➔ AI 擷取 ➔ 結構化顯示 ➔ 人工確認／修改 ➔ 正式存檔」專業處理工作鏈。",
            "weekly_win": "「AI 體重管理平台原型實戰」：以臨床減重平台為案例，跑通一次完整的需求拆解與互動原型驗證。",
        }

    if "曾小米" in lower_t:
        return {
            "micro_habit": "「把 AI 當作新進員工」：提供完整的品牌定位、產品規格、風格調性與驗收標準，成果責任不外包給工具。",
            "key_action": "「設計規格嚴格校核」：掌握「輸入 ➔ 產出 ➔ 驗收 ➔ 修正 ➔ 再產出」循環，精確比對禮盒尺寸、刀模與色彩規範。",
            "weekly_win": "「產出一份高質量設計 Brief」：以結構化 Prompt 完成 1 款品牌產品的 AI 協作包裝設計提案。",
        }

    if "邱醫師" in lower_t:
        return {
            "micro_habit": "「自主掌控 AI 工作系統」：即使教練不在身邊，也能自己把真實臨床工作交給 AI：從「AI 幫我做」提升到「我知道該用哪套流程」。",
            "key_action": "「專業閱讀與反思鏈」：掌握「閱讀 ➔ 畫重點 ➔ 提問 ➔ AI 整理 ➔ 自己判斷 ➔ 留存」的高效知識消化鏈條。",
            "weekly_win": "「建立專屬臨床 AI SOP」：在個人專業領域落實「Chat → Project → Work → Skill」的自主工作工作流。",
        }

    if "曹淑鈴" in lower_t or "大腳旅行社" in lower_t or "crystal" in lower_t:
        return {
            "micro_habit": "「從 Chat 邁向 Work」：不要只停留在聊天對話，讓 AI 從聊天夥伴轉化為能夠完成具體交付物的業務實戰幫手。",
            "key_action": "「旅遊業務流程重構」：依照「實際問題 ➔ 現場處理 ➔ 操作流程 ➔ 商業應用 ➔ 後續行動」重塑顧客服務鏈。",
            "weekly_win": "「行程規劃與客服問答 AI 化」：將旅行社高頻客戶諮詢或行程規格整理為一套標準化應答工作流。",
        }

    if "查米" in lower_t:
        return {
            "micro_habit": "「問對問題 ＋ 拆解問題」：先找出真正核心痛點，再拆解成可操作步驟，最後依照現實限制設計最優方案。",
            "key_action": "「限制條件優先盤點」：在專案推進前先列出時間、硬體與成本限制，避免工具過度配置。",
            "weekly_win": "「完成 1 項業務痛點深度拆解」：將目前最卡關的業務梳理出清楚的因果邏輯與執行清單。",
        }

    if "若麟" in lower_t:
        return {
            "micro_habit": "「批判性思考習慣落實」：不盲目追求新工具，先透過 #問對問題 與 #識別假設 釐清任務核心目的。",
            "key_action": "「任務最小可行單元拆解」：運用結構化框架將大型專案拆解為可個別驗收的最小實作步驟。",
            "weekly_win": "「個人專案結構化拆解」：在手頭專案中落實一次無工具干擾的需求定義與驗收指標梳理。",
        }

    if "lala" in lower_t or "湘祺" in lower_t:
        return {
            "micro_habit": "「溝通提供充足前情提要」：不要單純聊天，先提供個人背景、公司資料與目標，讓 AI 一次到位不走彎路。",
            "key_action": "「Typeless 跨裝置語音流」：掌握電腦與手機雙向語音輸入，並在 ChatGPT Work 中以「/」快速叫出 Skill。",
            "weekly_win": "「安裝全自動提示詞改進器」：在電腦版與手機版跑通提示詞優化工作流，提升日常對話產出質量。",
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

    if "資深少年" in lower_t:
        return {
            "micro_habit": "「造 (Build) 的浪漫：建構個人 AI 作業系統」：不再被動等待軟體功能，而是主動運用 AI 打造符合自己生活節奏的微型系統。",
            "key_action": "「專案式學習 (PBL) 閉環」：從日常生活中的真實問題出發，經歷「探索 ➔ 踩坑 ➔ 驗證 ➔ 沉澱為 Skill」的完整過程。",
            "weekly_win": "「跑通 1 個生活自動化專案」：在個人電腦或手機上獨立建立 1 個可重複觸發的生活或學習小幫手。",
        }

    # -------------------------------------------------------------
    # 層級 2：通用深度結構化萃取引擎 (Deep Structural NLP Extraction)
    # -------------------------------------------------------------
    def _is_clean_candidate(s: str) -> bool:
        s_strip = s.strip(" *#「」\"'\t、，。:：")
        if len(s_strip) < 12 or len(s_strip) > 75:
            return False
        if s_strip.endswith(("：", ":")):
            return False
        bad_tokens = [
            "在你的", "你的教學", "你的課程", "代表案例", "思考習慣", "個 HC",
            "個思考", "三句話", "核心定位", "教學內容", "蔡教練", "http",
            ".md", ".pdf", "大綱", "模組", "章節", "授課", "課程名稱",
            "知道很多，但", "尚未形成", "做不出來", "第一階段", "第二階段",
            "工作鏈", "操作熟練 →", "可行性＋", "暫時恢復", "授課日期", "授課時段"
        ]
        if any(b in s_strip for b in bad_tokens):
            return False
        if re.match(r"^[一二三四五六七八九十0-9.、\s（）()第]+", s_strip):
            return False
        return True

    # 1. 優先聚焦學員複習段落或核心總結
    review_match = re.search(
        r"(?:學員複習版|學員課後實作版|課後實作|實作練習|本堂課最重要的三句話|核心原則|優先待辦|今天實際完成|重點摘要).*?(?=\n---|\Z)",
        clean_text,
        re.DOTALL,
    )
    search_text = review_match.group(0) if review_match else clean_text

    # 2. 抽取文章內教練強調之粗體金句 (**...**)
    raw_bolds = re.findall(r"\*\*([^\*\n]{8,85})\*\*", search_text)
    clean_bolds: list[str] = [
        b.strip(" *#「」\"'\t、，。:：")
        for b in raw_bolds
        if _is_clean_candidate(b)
    ]

    # 3. 抽取箭頭式工作流程 (A → B → C)
    arrows = re.findall(r"([^\n]{4,35}(?:→|➔)[^\n]{4,55})", search_text)
    clean_arrows = [
        a.strip(" *#「」\"'\t。")
        for a in arrows
        if not a.strip().startswith(("http", "www")) and len(a.strip()) > 10 and not any(bad in a for bad in ["具體例子", "操作熟練", "把建站任務"])
    ]

    # 4. 抽取鍵盤快捷鍵
    shortcut_match = re.search(r"(?:Command|Cmd|Ctrl|Option)\s*\+\s*[A-Za-z0-9+ ]{1,25}", clean_text)

    # 5. 構建 📱 每日 3 分鐘小習慣 (Micro-Habit)
    habit_candidates = [
        b for b in clean_bolds
        if any(k in b for k in ["習慣", "不要", "先", "才是", "原則", "測試", "驗證", "行事曆", "Calendar", "記錄", "留下", "減法", "責任", "真正", "生活", "晨間", "前情提要"])
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
