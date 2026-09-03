# StudentCRM (學員管理系統)

StudentCRM 是一個專為「數位教練」與「企業 AI 導入顧問」設計的全方位學員管理與教學資產運作系統。它無縫整合了過去 11 年、超過 1,220 篇的教學日記與課堂紀錄，結合 AI 學習動能預測、學員專屬入口（Magic Link Portal）、PWA 行動端桌面體驗、今日刻意練習小卡、100 篇學員實戰見證牆，以及全自動的 Heptabase 教學筆記入庫管道。

* 🌐 **生產環境網址**：[https://student-crm-flax.vercel.app](https://student-crm-flax.vercel.app)
* 🧪 **測試覆蓋率**：92/92 PASSED (100%)

---

## ✨ 核心特色 (Features)

* **原生 macOS 與 PWA 雙棲體驗**：
  * **macOS 桌面 App**：使用 PyObjC 與 WKWebView 將 Web 系統封裝為獨立視窗的 `.app`。
  * **iOS / 行動端 PWA**：提供專屬 App Icon、Web App Manifest 與 Apple Touch Icon，支援「加入主畫面」全螢幕 Standalone 運行，並自動導向至學員專屬空間。
* **學員專屬空間 (Student Magic Link Portal)**：
  * 教練在群組或個別發送專屬亂碼密鑰（`/my/{token}`），學員免註冊、免密碼即可查看個人進度、歷次課堂筆記與專屬練習。
  * 具備嚴格的資料隔離與去識別化安全機制，保障學員個人隱私。
* **今日刻意練習 · 實戰微行動抽籤卡**：
  * 深度提煉全庫教學資產之高頻行動指引，提供「🎲 抽取微行動」互動卡片，支援一鍵複製實踐小卡，促進課後刻意練習。
* **100 篇去識別化學員見證案例牆 (Social Proof Bank)**：
  * 集中展示 100 篇真實教學成果，依 `AGENTS.md` 規範徹底去識別化學員真名與敏感個資。
  * 支援企業 AI 導入、自動化流程、提示詞工程、數位工作流等 6 大領域即時標籤篩選與關鍵字過濾。
* **Heptabase ➔ StudentCRM 教學筆記全自動入庫管道**：
  * 每日 20:00 排程自 Heptabase 拉取最新卡片並寫入 `01.Docs/teaching` 後，**全自動連動入庫至 StudentCRM**。
  * 一對一學員：自動解析日期與堂數，更新 `data/teaching_records.json`，推移 `students.json` 最新上課日期。
  * 蘋果總裁班：自動置頂更新 `apple_ceo_class.json` 之 `teaching_notes` 陣列。
  * 專班/團體班：精準關聯群組並入庫。
* **蘋果總裁班班務與流水帳管理**：
  * 完整追蹤每位學員 8 堂課循環、出席歷史與待續班提醒。
  * 內建玫瑰客廳等場地費流水帳支出與餘額結算。
* **AI 學習狀態預測**：
  * 根據「距離上次上課天數」與「筆記平均字數」，提供 🟢 穩定留存、🔴 高流失風險 或 🧊 冰凍期 之即時動能燈號。

---

## 🛠️ 技術架構 (Tech Stack)

* **後端框架**：Python 3.9+, FastAPI, Uvicorn, Jinja2
* **前端介面**：HTML5, 原生 Vanilla CSS (深色模式體系), Inter / Noto Sans TC
* **部署環境**：Vercel Serverless (Production), 本地 macOS Cocoa App
* **資料層 (SSOT)**：
  * `data/students.json`：76 位學員主要資料庫
  * `data/teaching_records.json`：698 篇結構化教學紀錄全量索引
  * `data/apple_ceo_class.json`：蘋果總裁班班務、出席、流水帳與 103 篇專屬教學筆記
  * `data/social_proof_cases.json`：100 篇去識別化實戰見證庫
  * `data/digital_management_calendar_events.json`：Google 日曆排程歷史快取

---

## 🌐 核心頁面與 API 端點 (Routes & APIs)

### 前端頁面
* `GET /`：教練後台主儀表板（學員總覽、搜尋、KPI、微行動抽籤、日曆連線）
* `GET /my/{student_id_or_token}`：學員專屬個人空間（含個人筆記、出席、進度）
* `GET /program/apple-ceo`：蘋果總裁班專區（常駐導航返回按鈕、出席、場地費流水）
* `GET /cases`：100 篇學員實戰見證牆（多維度篩選與即時搜尋）
* `GET /dashboard`：行動端優化儀表板

### 核心 API
* `GET /api/practice/random`：隨機抽取一張課堂實戰微行動卡片（支援 GET / HEAD）
* `GET /api/cases`：取得 100 篇去識別化實戰見證列表（支援領域篩選）
* `GET /api/students`：取得全體學員列表 JSON
* `GET /api/students/{id}`：取得特定學員詳細特徵與預測動能
* `GET /api/program/apple-ceo`：取得蘋果總裁班全量班務 JSON
* `POST /api/program/apple-ceo/preview/attendance`：預覽新增上課出席對期別之影響差異

---

## 💻 指令工具 (CLI Tools)

### 1. 教學筆記一鍵手動同步入庫
若您剛手動建立或修改了教學筆記，可隨時執行此腳本，全自動更新 StudentCRM 資料庫：
```bash
python3 scripts/sync_teaching_to_crm.py --verbose
```

### 2. 啟動本地開發伺服器
```bash
cd 07.Projects/StudentCRM
python3 main.py
```
伺服器將啟動於 `http://localhost:8888`。

### 3. 執行自動化測試
```bash
cd 07.Projects/StudentCRM
.venv/bin/python -m pytest tests/ -v
```

---

## 📂 檔案目錄結構

```text
07.Projects/StudentCRM/
├── data/                                 # 核心 SSOT 資料庫
│   ├── students.json                     # 學員主檔案
│   ├── teaching_records.json             # 全量教學紀錄索引
│   ├── apple_ceo_class.json              # 蘋果總裁班班務與筆記
│   ├── social_proof_cases.json           # 100 篇去識別化見證庫
│   └── digital_management_calendar_events.json # 日曆事件快取
├── templates/                            # 前端 HTML 視圖
│   ├── index.html                        # 主儀表板
│   ├── hub.html                          # 學員專屬空間 (Magic Link)
│   ├── program_apple_ceo.html            # 蘋果總裁班專區
│   └── cases.html                        # 100 篇實戰見證牆
├── static/                               # 靜態資源與圖示
│   ├── css/                              # 樣式表
│   └── manifest.json                     # PWA 應用程式清單
├── main.py                               # FastAPI 主入口與路由控制器
├── hub_service.py                        # 學員中心與微行動抽籤服務
├── student_service.py                    # 學員特徵與狀態模型
├── teaching_sync.py                      # 教學筆記解析與 CRM 入庫引擎
├── data_gateway.py                       # 快取自癒與資料存取閘道
├── tests/                                # 92 項自動化測試套件
├── README.md                             # 系統說明文檔
└── CHANGELOG.md                          # 版本變更日誌
```
