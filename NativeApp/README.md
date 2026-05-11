# StudentCRM 原生版

這是 `StudentCRM` 的真正 macOS 原生版本第一版骨架，採用：

- `SwiftUI`
- `SQLite`
- 以 `OpenClaw/Data/students.json`
- 與 `OpenClaw/Data/apple_ceo_class.json`

作為正式匯入來源。

## 目前已完成

- 原生 `NavigationSplitView` 側欄
- `學員總覽`
- `蘋果總裁班`
- SQLite 本地資料庫
- 首次啟動自動匯入 JSON
- 可手動重新匯入
- `新增上課紀錄` 視窗
- `新增場地費紀錄` 視窗
- 新增後自動回寫 `apple_ceo_class.json`
- 依出席者自動補學員最新一輪堂次
- 本機通知：8 堂完成提醒 / 14 天內到期提醒

## 如何開啟

### 方式 A：Xcode 專案

1. 用 Xcode 開啟：

```text
StudentCRM/NativeApp/StudentCRMNative.xcodeproj
```

2. 選擇 `StudentCRMNative`
3. 直接執行

### 方式 B：Swift Package

如果你只想先看原始碼結構，也可以開：

1. 用 Xcode 開啟這個檔案：

```text
StudentCRM/NativeApp/Package.swift
```

2. 選擇 `StudentCRMNative`
3. 直接執行

## 目前資料表

- `students`
- `app_meta`
- `apple_attendance`
- `apple_venue_ledger`
- `apple_rounds`

## 下一步建議

- 新增「新增上課紀錄」原生表單
- 新增「新增場地費紀錄」原生表單
- 加入本機通知：8 堂完成提醒 / 4 個月到期提醒
- 把學生頁也改成原生詳細頁

## Heptabase 整合規劃

目前原生版的教學紀錄查詢仍在過渡期。

- 正式規劃文件：
  - `StudentCRM/NativeApp/HEPTABASE_MCP_MIGRATION.md`
- 原則：
  - `Heptabase MCP` 為主
  - `01.Docs/teaching` 為 fallback
  - `heptabase-cli` 降級為 debug 工具
