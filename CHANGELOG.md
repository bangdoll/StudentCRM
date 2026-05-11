# 更新日誌 (Changelog)

此專案的所有顯著變更將記錄在此檔案中。
格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)。

## [Unreleased]
### 新增 (Added)
- **「蘋果總裁班」完整管理模組**：基於多年 Evernote 散亂資產，透過 Vibe Coding 模式實作課程進度追蹤、場地費紀錄與到期自動提醒功能。
- **Xcode 原生 App 開發探索**：開始嘗試將 StudentCRM 邏輯移植至原生 iOS/macOS 專案，邁向原生系統開發。

## [1.1.0] - 2026-03-19
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
