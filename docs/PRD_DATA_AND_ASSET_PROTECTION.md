# StudentCRM 產品需求規格書與資料資產保護 PRD (v1.3.0)

> **狀態**：正式生效 (Active)  
> **制定日期**：2026-09-04 00:05 (深夜架構固化版)  
> **系統架構基準**：[OpenClaw 九層塔架構](../../01.Docs/OpenClaw_Nine_Layer_Architecture.md) & [AGENTS.md 全域治理憲法](../../AGENTS.md)  
> **核心宗旨**：終結深夜症狀式修補，確立教學資產絕對零損失、單向流動與回歸測試防護網。

---

## 1. 痛點診斷與根本原因 (Root Cause Analysis)

近期在系統維護中出現多起連鎖異常（總裁班出席記錄未同步、微行動卡空泛脫節、學員首次上課日期變成未記錄），其根本原因為：
1. **缺少權威 PRD 規範**：對「誰是資料的單一真實來源 (SSOT)」、「誰是快取」、「資料流向何處」沒有不可動搖的系統規格。
2. **多端狀態不同步與雙向覆寫風險**：本地 Markdown、本地 JSON (`data/`)、雲端 Supabase PostgreSQL、Vercel 邊緣快取同時存在，若無單向防護，同步時隨時可能發生「以空蓋實」的災難。
3. **缺少資產不變性約束 (Invariance Contracts)**：程式未強制規定「歷史記錄筆數只增不減」、「關鍵欄位不可被洗掉」。
4. **缺少關鍵資產之回歸測試閘門 (Regression Test Gate)**：功能新增時只測新邏輯，未保護全庫 1,220+ 篇筆記與 64 位學員的歷史完整性。

---

## 2. 核心架構原則：四層單向流 (Unidirectional Data Flow)

本系統嚴格執行**單向資料流動**，嚴禁下游逆向修改或覆蓋上游真實資產：

```
[第 1 層：最高物理真實層 (Physical SSOT)]
  📁 01.Docs/teaching/*.md (1,220+ 篇真實教案)
  📁 01.Daily/YYYY/MM/Diary_*.md (4,200+ 天日記資產)
  📁 OpenClaw/Data/students.json (64 位學員基本檔與 Google 日曆對齊之首堂日)
  🛡️ 規範：Append-Only、禁止任何自動化腳本執行破壞性刪除或改名。
       ↓ （只讀解析，增量提取）
[第 2 層：本地核心索引層 (Local Projected Index)]
  📄 07.Projects/StudentCRM/data/teaching_records.json (全庫教學記錄結構化總帳)
  📄 07.Projects/StudentCRM/data/apple_ceo_class.json (總裁班完整班務與出席)
  🛡️ 規範：寫入前自動快照備份 (.bak)；實施斷路器（筆數減少時拒絕寫入）。
       ↓ （安全鏡像同步）
[第 3 層：雲端投射快取層 (Cloud Projected Cache)]
  ☁️ Supabase PostgreSQL (students, teaching_records, apple_*)
  🛡️ 規範：僅作為多租戶與雲端查詢快取，永遠不作為資料唯一孤島。
       ↓ （API 唯讀查詢）
[第 4 層：前端視圖展示層 (Client Presentation View)]
  🌐 Vercel Serverless (FastAPI / Jinja2 / PWA)
  🛡️ 規範：唯讀渲染、教練與學員視野嚴格隔離 (Token Magic Pass)。
```

---

## 3. 資產保護三大不變性契約 (Invariance Contracts)

任何代碼修改、同步腳本或遷移工具，必須無條件滿足以下三大物理約束：

### 契約一：筆數單調不減約束 (Monotonic Non-decreasing Invariant)
* 教學筆記總數（目前 698 條 CRM 記錄 / 1,220+ 篇 Markdown 筆記）在任何更新後，**總筆數只能大於或等於前次狀態**。
* 若同步腳本解析出的筆記數小於現有記錄（例如因解析錯誤只抓到 0 篇或 10 篇），**必須立即觸發熔斷（Circuit Breaker），拋出例外並中止寫入**，嚴禁以空列表覆蓋歷史資料。

### 契約二：核心欄位不可退化約束 (Field Non-Degradation Invariant)
* 學員之 `first_lesson_date`（首次上課日期）、`student_id`、`file`、`lessons_count` 為高價值長期資產。
* 在任何 Local/Supabase 合併、更新或前端組裝過程中，**嚴禁將已存在的具體值覆蓋為 `None`、`""` 或 `"未記錄"`**。
* 雲端載入必須具備本地 SSOT 兜底機制（Local SSOT Fallback）。

### 契約三：寫入前強制快照約束 (Snapshot Before Write Invariant)
* 任何修改 `data/students.json`、`data/teaching_records.json` 或 `data/apple_ceo_class.json` 的自動化流程，寫入前必須將原始版本備份至 `cache/backups/`，保留至少 10 個滾動歷史版本，確保 100% 具備可逆性。

---

## 4. 功能模組規範 (Functional Specifications)

### 4.1 學員檔案與首次上課
* **欄位定義**：`first_lesson_date` 格式為 `YYYY-MM-DD`，資料來源為教練 2018–2026 年 Google Calendar 真實授課行程比對。
* **展示規格**：
  * 首頁卡片：`🌱 首次上課：{first_lesson_date}`
  * 續約預警雷達：`🌱 首次上課：{first_lesson_date}`
  * 學員專屬頁：`🌱 首次授課：{first_lesson_date}`
  * 學員 Learning Hub：`🌱 啟程日期：{first_lesson_date}`
* **降級保護**：若單一來源未載入，閘道器需依序自 `raw.first_lesson_date` ➔ `data/students.json` ➔ `01.Docs/Students/{Name}.md` 取得，嚴禁出現未記錄。

### 4.2 課堂微行動卡 (Actionable Micro-Cards)
* **品質標準**：100% 根據當日真實教學筆記萃取，嚴禁使用「角色設定＋背景目標＋輸出格式」等泛型死模板。
* **內容規格**：
  * 📱 **每日 3 分鐘小習慣**：核心思考原則或反思檢查點（完整句子，非標題碎片）。
  * ⚡ **肌肉記憶 / 核心快捷鍵**：實戰工作流鏈條（`A ➔ B ➔ C`）或鍵盤快捷鍵。
  * 🎯 **本週 1 個小成就**：該堂課明確產出之交付物、專案實作或驗收目標。
* **語意守衛**：嚴禁以「的...」、「→ ...」、「：」開頭或結尾之語病殘片。

### 4.3 蘋果總裁班專班管理
* **資料核心**：`OpenClaw/Data/apple_ceo_class.json` 與 `data/apple_ceo_class.json` 雙向鏡像。
* **班務紀錄**：包含 `teaching_notes`（歷史教案）、`attendance_records`（點名紀錄）、`venue_ledger`（場地流水）、`student_rounds`（學員期別進度）。
* **合併防護**：雲端載入時，四個維度各自進行日期與筆數比對，永遠保留最新、筆數最多的集合。

---

## 5. 獨立回歸測試規格 (Regression Test Specifications)

系統必須常設 `tests/test_zero_loss_regression.py`，作為發布前必經之 Eval Gate，涵蓋：
1. **SSOT 不受損測試**：確認磁碟上真實 Markdown 文件完整性與防刪除。
2. **斷路器防禦測試**：傳入空白或不完整筆記時，驗證系統會堅決拒絕寫入。
3. **首堂日期零遺失測試**：遍歷全體 64 位學員，斷言 `first_lesson_date` 100% 存在且格式合法。
4. **多端合併完整性測試**：模擬 Supabase 缺欄位情境，驗證本地 SSOT 兜底能 100% 修復資料。
5. **總裁班四象限資料不倒退測試**：斷言教案數 >= 103 篇、出席紀錄 >= 50 筆、流水帳 >= 55 筆。

---

## 6. 治理與演進守則
1. **嚴禁無測試提交**：凡修改 `data_gateway.py`、`teaching_sync.py` 或資料讀寫邏輯，必須跑通回歸測試套件。
2. **變更必須留痕**：每次修復與功能演進，同步更新 `CHANGELOG.md` 與 `README.md`。
3. **保護教練數位遺產**：寧可拒絕更新並報警，也絕不能讓一篇筆記、一個學員資料在同步中被洗白。
