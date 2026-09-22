# 2026-09-22｜陳顧問 StudentCRM 匯入任務契約與驗收

## 目標

建立新的「陳顧問」學員資料與專屬 Learning Hub，將 Google Calendar 已核對的第 01–14 堂教學筆記匯入 StudentCRM；第 14 堂採用最新 v2 版本。

## 允許範圍

- 新增一位 StudentCRM 學員：陳顧問。
- 新增 14 筆 `teaching_records`，來源為 `01.Docs/teaching/陳顧問/`。
- 讓同步引擎遞迴讀取教學子資料夾，並優先採用同堂次的 `_v2` 檔案。
- 透過 `StudentDataGateway` 寫入並建立資料快照。

## 禁止事項

- 不歸戶至既有「查米」學員。
- 不刪除或覆寫 Heptabase 既有頁面。
- 不刪除既有 StudentCRM 學員或教學紀錄。
- 不執行全量 Supabase 重建；線上資料只允許對陳顧問做精準 upsert。

## 驗收條件

- `students.json`：67 → 68 位，新增學員名稱為「陳顧問」。
- `teaching_records.json`：723 → 737 筆，新增 14 筆且日期為 2026-05-13～2026-09-22。
- 第 14 堂檔案為 `14_2026-09-22_和陳顧問合作課程_v2.md`，內容含最新 Heptabase MD5 `d83fc494773d6ca68b5f1a2e0feb6b94`。
- 專屬網址：`https://student-crm-flax.vercel.app/my/f13107ba-79fb-5bae-8728-99648687ef48`。
- 同步相關測試通過，且資料鏡像一致。
- Vercel Production 部署狀態為 `READY`，線上專屬頁與 manifest 回傳 HTTP 200。
- Production Supabase 讀回 1 位陳顧問與 14 筆課堂，堂號 1–14，最新 v2 指紋核對通過。

## 停止條件


- 發現既有「陳顧問」或相同筆記檔名時停止，避免重複。
- 學員或教學紀錄基線數量與預期不一致時停止。
- 第 14 堂不是最新 v2 時停止。
