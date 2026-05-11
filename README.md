# StudentCRM (學員管理系統)

StudentCRM 是一個專為「數位教練」與「企業 AI 導入顧問」設計的本地端 macOS 應用程式。它整合了過去 11 年的教學日記與筆記，並透過 AI 分析提供學員留存率預測與學習狀況追蹤。

## ✨ 核心特色 (Features)

*   **原生 macOS 體驗**：使用 PyObjC 與 WKWebView 將 Web 系統封裝為原生的 macOS `.app` 桌面程式，擁有獨立視窗與 Dock 圖示。
*   **AI 學習狀態預測**：系統會自動抓取每位學員的「最後上課日期」與「筆記平均字數」，給予三種 AI 狀態燈號警示：
    *   🟢 穩定留存
    *   🔴 高流失風險
    *   🧊 冰凍期 (需關心)
*   **11 年時間軸大一統**：完美整合 2013-2026 年的 `.md` 教學日記檔案，建立學員專屬的歷史教學時間軸。
*   **雲端雙引擎資料層**：預設以本地端 `OpenClaw/Data/students.json` 運作；設定 `STUDENTCRM_DATA_BACKEND=supabase` 後，可改由 Supabase REST API 讀取，並保留本地快取作為離線 fallback。

## 🛠️ 技術架構 (Tech Stack)

*   **後端框架**：Python 3.9+, FastAPI, Uvicorn, Jinja2
*   **前端介面**：HTML5, 原生 CSS (純淨深色模式體系), Inter / Noto Sans TC 字體
*   **桌面封裝**：macOS Cocoa API, WebKit, AppBundle
*   **資料庫**：本地 JSON / Markdown、Supabase PostgreSQL（可選雲端 SSOT）

## 🚀 安裝與啟動 (Installation & Launch)

### 啟動應用程式
直接在 Finder 中雙擊 `StudentCRM.app` 即可啟動。

> **注意**：本程式內建已修正 Rosetta 2 架構衝突，將強制使用 M 系列晶片的 `arm64` 原生架構來啟動 Apple Silicon Python 環境。

### 開發者除錯模式
如果您需要查看終端機日誌，可以直接啟動後台：
```bash
cd /Users/aios/Projects/00.AI-Notes_Local/StudentCRM
python3 main.py
```
伺服器將會啟動於 `http://localhost:8888`。

### 雲端雙引擎設定
預設不需要任何雲端設定，系統會讀取本地 JSON。

若要切換到 Supabase 讀取：
```bash
export STUDENTCRM_DATA_BACKEND=supabase
export SUPABASE_URL="https://vwgbbvodfzsagrtyuybl.supabase.co"
export SUPABASE_ANON_KEY="YOUR_SUPABASE_ANON_KEY"
python3 main.py
```

可用 API：
*   `GET /api/sync/status`：查看目前資料引擎與 fallback 狀態
*   `GET /api/students`：提供 Web Dashboard / Native App 共用的學員列表 JSON
*   `GET /api/students/{student_id}`：提供單一學員、特徵與預測狀態
*   `GET /api/program/apple-ceo`：提供蘋果總裁班班務 JSON，含上課紀錄、場地費流水、期別與彙總
*   `POST /api/program/apple-ceo/preview/attendance`：預覽新增上課紀錄將影響哪些期別；只回傳差異，不寫入資料

macOS 原生版已可在「學員總覽」點擊「同步 API」，將 `/api/students` 回傳資料寫入本機 SQLite 快取；也可在「蘋果總裁班」點擊「同步班務 API」，將 `/api/program/apple-ceo` 回傳資料寫入本機 SQLite 快取。這兩個同步都是只讀同步，不會寫回 Supabase 或修改原始 JSON。

在 macOS 原生版「新增上課紀錄」表單內，可先點擊「預覽 API 差異」呼叫 `/api/program/apple-ceo/preview/attendance`，查看每位學員期別 before/after 課次。此預覽不會觸發儲存，也不會寫入 Supabase。

Web Dashboard MVP：
*   `GET /dashboard`：行動友善看板，顯示學員 KPI、14 天內排課、風險狀態篩選與蘋果總裁班提醒。
*   `GET /program/apple-ceo`：班務中心含「預覽新增上課紀錄」面板，可先查看出席名單會影響哪些學員期別；此流程只讀預覽，不會寫入資料。

Supabase 初始化：
1. 先在 Supabase SQL Editor 執行 `StudentCRM/scripts/supabase_schema.sql`。
2. 接著執行 `StudentCRM/scripts/supabase_rls_readonly.sql` 啟用只讀 RLS policy。
3. 乾跑檢查資料量：
   ```bash
   python3 StudentCRM/scripts/migrate_to_supabase.py
   ```
4. 確認後才寫入：
   ```bash
   python3 StudentCRM/scripts/migrate_to_supabase.py --apply
   ```

Supabase 安全邊界請見 `StudentCRM/docs/SUPABASE_SECURITY.md`。

同步 smoke test：
```bash
python3 StudentCRM/scripts/supabase_smoke_test.py --api http://127.0.0.1:8888
```
若已完成 Supabase schema / RLS / migrate，可再加上 `--supabase` 檢查 REST 欄位與筆數；檢查範圍包含 `students` 與蘋果總裁班拆表。網站與 Vercel production 應設定 `SUPABASE_ANON_KEY`；`SUPABASE_SERVICE_ROLE_KEY` 僅供本機遷移工具或受控後端 Worker 使用。

目前 schema 已包含一對一學員、教學紀錄與蘋果總裁班拆表：
*   `students`
*   `teaching_records`
*   `apple_programs`
*   `apple_venues`
*   `apple_attendance_records`
*   `apple_venue_ledger`
*   `apple_student_rounds`

## 📂 目錄結構
*   `StudentCRM.app/` - macOS 原生應用程式套件
*   `main.py` - FastAPI 核心後台程式
*   `templates/` - Jinja2 前端版型
*   `static/` - CSS 樣式表
*   `cache/` - 動態生成的教學快取 Markdown 檔案
*   `backend.log` - 應用程式原生啟動的錯誤與狀態日誌
