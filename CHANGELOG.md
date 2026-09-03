# 更新日誌 (Changelog)

此專案的所有顯著變更將記錄在此檔案中。
格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)。

## [1.2.0] - 2026-09-03
### 新增 (Added)
- **教學筆記全自動連動入庫管道**：
  - 於 `teaching_sync.py` 實裝 `sync_teaching_records_to_crm()`，全自動將 `01.Docs/teaching` 最新筆記入庫至 StudentCRM。
  - **一對一學員**：精準解析上課日期、堂數，更新 `data/teaching_records.json`，並自動推移 `students.json` 之 `latest_date` 與 `lessons_count`。
  - **蘋果總裁班**：自動萃取課堂標題、日期、全文與預覽，置頂寫入 `apple_ceo_class.json` 的 `teaching_notes`。
  - **專班/團體班**：自動匹配「資深少年 AI 學習團」、「禮品公會」等專班群組並入庫。
  - **定時排程整合**：與每日 20:00 之 Heptabase 同步排程 (`sync_heptabase_teaching.py`) 完全聯動，並推播 Telegram 戰情日報。
  - **獨立 CLI 工具**：新增 `scripts/sync_teaching_to_crm.py`，支援手動隨時觸發全量入庫。
- **PWA 行動端與 iOS 桌面體驗**：
  - 建立專屬高質感 iOS App Icon (`student_crm_ios_icon_*.jpg`)、Web App Manifest 與 Apple Touch Icon 設定。
  - 支援行動裝置全螢幕獨立視窗（Standalone）運行，並實作加入主畫面後自動導向學員專屬空間之流暢體驗。
- **今日刻意練習 · 實戰微行動抽籤小卡**：
  - 於 `hub_service.py` 整合全庫 1,220+ 篇教學資產，提煉五大領域微行動標籤。
  - 新增 `GET /api/practice/random` 端點（支援 GET 與 HEAD 請求），並於首頁增設互動抽籤卡與一鍵複製按鈕。
- **100 篇去識別化學員見證案例牆 (Social Proof Bank)**：
  - 新增 `/cases` 展示牆與 `/api/cases` 介面，依 `AGENTS.md` 嚴格去識別化學員個資。
  - 支援「企業 AI 導入」、「自動化流程」、「提示詞工程」等 6 大維度篩選按鈕與即時文字過濾。
  - 產出 `Social_Proof_Case_Studies_100.md` 與 `social_proof_cases.json` 總帳。
- **蘋果總裁班 2026-09-03 課堂出席與場地流水記帳**：
  - 登錄 2026-09-03 出席紀錄（Roger老師、方醫師，共 2 位）。
  - 場地費流水扣除 $300（玫瑰客廳 150*2），結餘更新為 $1,600。
  - Roger老師夏季梯次 8/8 堂圓滿結訓；方博敦醫師自動開啟 2026 秋季梯次第 1 堂。

### 修正 (Fixed)
- **學員專屬 Magic Link 存取修復**：
  - 修復學生點擊專屬亂碼密鑰網址（如 `/my/adf9958b-a23d-4e9b-a4a2-156b5329b0ed`）時因權限校驗或路徑缺少導致無法查看的問題。
  - 實作教練管理視圖與學員唯讀視圖隔離，落實隱私保護。
- **蘋果總裁班介面導航斷層修復**：
  - 於 `templates/program_apple_ceo.html` 頂部導航與操作工具列增設常駐按鈕 `← 回到學員管理系統`，解決學生或教練進入總裁班後無法點擊返回 CRM 主系統的問題。
- **HEAD 請求 405 Method Not Allowed 缺陷**：
  - 修復瀏覽器預檢、Vercel 探針或快取檢查以 `HEAD` 請求存取 `/api/practice/random` 端點時回傳 405 的錯誤。
- **快取自癒與即時刷新**：
  - 在 `data_gateway.py` 實作 `clear_gateway_memory_cache()`，解決更新 JSON 資料庫後因記憶體快取導致線上頁面未能即時呈現的問題。

### 優化 (Changed)
- **自動化測試體系擴充**：全套單元與整合測試擴充至 **92/92 PASSED (100%)**。
- **Vercel 自動部署管線對齊**：推送 GitHub `main` 分支自動觸發 Vercel Production Build，線上實測 HTTP/2 200 OK。
### 新增 (Added)
- **AI 互動預測系統**：新增學員學習動能預測功能。自動計算「距離上次上課天數」與「近期筆記字數」，產生 🟢 穩定留存、🔴 高流失風險 或 🧊 冰凍期 的視覺化徽章。
- **13 年教學紀錄大一統與日曆倒灌**：新增 `extract_apple_class.py` 腳本，排除 2013 年以前的假陽性關鍵字後，成功將 2013 至 2026 年間的日記教案與 **Google Calendar 上漏網的 234 趟歷史行程**完整萃取，最終建立共 **1,381 堂**的「蘋果總裁班」時間軸。
- **背景日誌紀錄**：`StudentCRM.app` 啟動現在會將後端輸出記錄至 `StudentCRM/backend.log`，方便進行底層除錯。

### 修正 (Fixed)
- **致命的白畫面問題 (Rosetta 2 架構衝突)**：修復 macOS 雙擊啟動 `.app` 會導致白畫面的問題。原因為 App 預設以 x86_64 架構啟動，無法讀取 M2 晶片原生的 `pydantic_core` (arm64) C-extension 模組。目前已透過在啟動腳本中寫入 `/usr/bin/arch -arm64` 強制突破封鎖，解決閃退。
- **YAML 前置內容解析錯誤**：修復 Markdown 解析器在遇到無 `---` 包閉的筆記檔案時引發的 `ScannerError` HTTP 500 系統崩潰。
- **連接超時未顯示問題**：改善 `launcher.py` 中的 `Popen` 機制。

### 移除 (Removed)
- 從介面與文字中全面移除舊版不相關的「OpenClaw」、「龍蝦 (Lobster)」等代號，讓產品更加純粹與專業。

## [1.0.0] - 初始版本
### 新增 (Added)
- 建立基於 FastAPI 與 PyObjC 的 macOS 本地應用程式架構。
- 建立以 `students.json` 與 Markdown 文件為儲存載體的單一真實來源 (SSOT) 系統。
- 實作深色主題的前端儀表板介面。
