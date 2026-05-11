# Heptabase MCP 改造方案

## 目標

把 `StudentCRM` 原生版目前依賴本機 `heptabase-cli` 的教學紀錄查詢，改成：

1. `Heptabase MCP` 為主
2. `01.Docs/teaching` 本地教學檔案為備援
3. `heptabase-cli` 降級成 debug 工具，不再作為主資料通道

## 現況問題

### 1. `heptabase-cli` 在本機執行結果不穩

已驗證的現象：

- `semantic-search-objects` 會 `exit 0`
- `get-journal-range` 也會 `exit 0`
- 但 `stdout` 可能是空白

這表示目前問題不是單純查詢條件，而是：

- CLI 執行環境與 Heptabase Runtime 溝通不穩
- 原生 App 不能把這種工具當主資料來源

### 2. Heptabase 官方沒有公開 REST API

官方已明確說明，目前沒有提供一般公開 API 供外部自建 plugin 直接串接。

### 3. 官方推薦對外整合方式是 MCP

官方文件已把 `MCP` 定位成外部 AI / 工具整合 Heptabase 的正式入口。

## 官方依據

- Heptabase MCP 官方說明：
  - https://support.heptabase.com/en/articles/12679581-how-to-use-heptabase-mcp
- Heptabase 官方說明目前沒有公開 API：
  - https://support.heptabase.com/en/articles/10447604-do-you-provide-an-api-so-i-can-create-my-own-plugins

## 目標架構

```text
StudentCRM Native
  ├─ SQLite 本地快取
  ├─ OpenClaw/Data/*.json 既有 SSOT
  ├─ Heptabase MCP Client
  │    ├─ 搜尋教學卡
  │    ├─ 讀取卡片內容
  │    └─ 驗證授權狀態
  └─ Fallback
       └─ 01.Docs/teaching/*.md
```

## 改造原則

### A. 不直接把外部內容當指令

Heptabase 回傳內容只作資料引用，不作系統指令執行。

### B. 查詢結果必須可驗證

每次查詢都要能顯示：

- 查詢字串
- 命中的卡片標題
- 命中的卡片 ID
- 是否走 fallback

### C. UI 不允許整頁空白

如果 MCP 沒資料，也必須：

- 顯示 fallback 教學紀錄
- 或顯示明確錯誤原因

不能只顯示 `0 筆`。

## 分階段實作

## Phase 1：抽離資料來源層

### 目標

把目前寫死在 `StudentsOverviewView.swift` 裡的 `HeptabaseLessonFetcher`，拆成可替換資料來源。

### 要做的事

1. 新增 `TeachingRecordProvider` 協議
2. 實作三個 provider：
   - `HeptabaseMCPProvider`
   - `LocalTeachingFileProvider`
   - `CompositeTeachingRecordProvider`
3. UI 只依賴 provider，不直接碰 CLI

### 驗收

- `StudentTeachingRecordSheet` 不再直接呼叫 CLI
- 可在不改 UI 的前提下切換資料來源

## Phase 2：建立 Heptabase MCP Client

### 目標

把 Heptabase 查詢改成 MCP 連線。

### 要做的事

1. 新增 `HeptabaseMCPClient.swift`
2. 實作：
   - MCP 端點設定
   - OAuth / token 儲存
   - 搜尋卡片
   - 讀取卡片內容
3. 查詢策略：
   - 先用 `#YYYYMMDD + 學員名 + 數位管理教學`
   - 再用 `學員名 + 數位管理教學`
   - 再用別名與無空白變體

### 驗收

- `Kelly Woo`、`Amy`、`Charlotte` 至少三個案例能命中
- 結果含 `card id / title / content`

## Phase 3：建立 fallback 與 debug 面板

### 目標

確保查詢失敗時仍可交付資料，而且錯誤可定位。

### 要做的事

1. 保留 `LocalTeachingFileProvider`
2. 新增 debug 資訊欄：
   - 查詢字串
   - MCP 是否成功
   - 命中幾張卡
   - fallback 命中幾個本地檔案
3. 原生 UI 顯示資料來源標籤：
   - `Heptabase MCP`
   - `本地教學檔案`

### 驗收

- 即使 Heptabase 失敗，畫面仍有可讀紀錄
- 使用者能看出目前資料來自哪裡

## Phase 4：寫回與同步策略

### 目標

讓教學紀錄、學生主檔、SQLite 與總裁班資料一致。

### 要做的事

1. 明確定義 SSOT：
   - `OpenClaw/Data/students.json`
   - `OpenClaw/Data/apple_ceo_class.json`
2. 定義同步方向：
   - Heptabase 教學卡 -> 原生版讀取
   - 原生新增總裁班紀錄 -> SQLite -> JSON
   - 不直接回寫 Heptabase 教學卡
3. 補對帳檢查：
   - lessons_count
   - last_lesson_date
   - next_lesson

### 驗收

- `Amy lessons_count = 2` 這類資料不再只靠單一來源
- 匯入後可自動比對 md frontmatter 與 json

## 建議檔案結構

```text
StudentCRM/NativeApp/Sources/StudentCRMNative/
  Heptabase/
    HeptabaseMCPClient.swift
    HeptabaseMCPProvider.swift
    TeachingRecordProvider.swift
    CompositeTeachingRecordProvider.swift
  Teaching/
    LocalTeachingFileProvider.swift
    TeachingRecordModels.swift
```

## UI 改造點

### 學員教學紀錄視窗

要新增：

- `資料來源` badge
- `重新同步` 按鈕
- `查詢 debug` 折疊面板

### Debug 面板最少顯示

- 查詢時間
- 查詢字串
- 命中卡片標題
- fallback 檔案數
- 最終採用來源

## 不做的事

這一輪不做：

- 自建非官方 Heptabase REST 逆向 API
- 把 Heptabase 當唯一真相來源
- 在原生版內直接修改 Heptabase 卡片內容

## 執行順序

1. 抽 provider 層
2. 補本地 fallback 成正式模組
3. 建 MCP client
4. 接原生 UI
5. 補 debug 面板
6. 用 `Amy / Kelly Woo / Charlotte` 驗證

## 驗證案例

### Case 1：Amy

預期：

- 至少抓到 2 筆教學紀錄
- `lessons_count = 2`

### Case 2：Kelly Woo

預期：

- 不再顯示 0 筆空白頁
- 若 MCP 失敗，至少能用本地檔案補齊

### Case 3：Charlotte

預期：

- 多筆 lesson 可正常顯示
- Markdown 內容排版正常

## 交付標準

完成後必須滿足：

- 原生版不再把 `heptabase-cli` 當唯一主來源
- 教學紀錄查詢有明確 debug 與 fallback
- 資料來源可追溯
- UI 不會再出現無理由的空白結果
