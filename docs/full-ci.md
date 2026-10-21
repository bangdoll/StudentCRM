# 完整 CI 與套件驗收

PR #1 修正後，原 `CI Test Pipeline` 在 Python 3.11、3.12 執行完整 `tests/`，不設定 ignore、skip、xfail 或縮小測試集合。JUnit 檢查額外要求 tests > 0、skipped = failures = errors = 0。

## 已釐清的原因

| 原問題 | 修正與驗證 |
| --- | --- |
| editable 安裝發現多個頂層目錄，setuptools 拒絕自動探索 | 宣告 build backend、全部頂層 Python 模組、routers/schemas 與資源 namespace，排除 NativeApp、cache、tests；保留 `uvicorn main:app`。 |
| requirements 缺少已在 pyproject 宣告的 Pillow | 兩個安裝入口補齊相同執行依賴。 |
| Gateway 的 `.` 與絕對路徑比較不一致，雷達讀到空學員 | 入口正規化絕對路徑，新增兩種路徑等價的回歸測試。 |
| 指定暫存 app 的 Gateway 卻寫回程式目錄 | 辨識明確的 data 目錄，測試驗證寫入位置。 |
| 測試匯入未提交的外部 merge_students 腳本 | 納入無資料庫預設值的身分查找、候選判斷與唯讀計畫介面；保護名單、歧義拒絕與禁止寫入均測試。不提供實際學員合併工具。 |
| test_main 匯入時覆寫成原作者電腦路徑，造成服務全域設定與快取互相污染 | conftest 在匯入應用前建隔離工作區，複製已提交的 JSON；空白服務憑證，逐項清快取並禁止外部 socket 連線。 |
| 同步 dry-run 測試未設定假憑證，提早走缺憑證分支 | 明確提供 example.invalid 與假金鑰，遠端查詢仍為 stub；缺憑證失敗測試保留。 |
| 教案、圖片、手冊的測試依賴 repo 外私人檔案 | 用明確的隔離資料重播功能；實體私人資產盤點保留為下述獨立唯讀命令。 |

## 測試強度與私人資產的邊界

- 匯入測試使用 62 位匿名學員各 10 課、80 份班級教材與 1 位新學員，共 701 份。原本 >= 698 筆、>= 60 位、>= 80 份門檻保留，另要求精確 701 筆／64 位、每份檔名完整保留、正文非空、data/cache 相同。
- 圖片測試使用兩份匿名正文及真實可解碼的小圖片，保留兩處實體存在、frontmatter、渲染去重檢查；另刪除一份圖片驗證盤點必須失敗。
- 1,220 篇閘門測試實際驗證缺目錄、1,219 篇失敗與 1,220 篇通過，沒有降低原門檻。這些是驗證門檻的臨時檔案，**不是私人教案庫，也不能證明正式庫有 1,220 篇**。
- 手冊驗收增加到全部 30 個單元，缺檔或刪除中間單元必須失敗。CI 的匿名教材不能證明正式手冊存在。
- 正式私人工作區另以 `asset_audit` 讀回：最低 1,220 篇、原指定 10/12 兩篇筆記與兩份圖片副本、巢狀 frontmatter、手冊三大區塊及全部 30 單元。缺檔會回傳非零退出碼，不會略過。此次本機實測 1,357 篇、無缺口；本機報告與完整 CI 結果分開保存，私人正文不新增至公開 repo。
- 已提交 JSON 的原有學員數、首次上課日期、教學紀錄數與總裁班四象限資產斷言全部保留。完整測試前後已提交 data 檔案應無差異。

## 重跑

```sh
python -m pip install -e '.[dev]'
python -m pip check
python -m pytest tests/ -v --junitxml=full-suite.xml
python scripts/check_test_report.py full-suite.xml
python -m build
```

CI 會由 sdist 建立 wheel，再於 checkout 外的全新 venv 安裝，使用 `python -I scripts/check_installed_package.py` 的絕對路徑執行。驗證匯入來自 venv、HTML 模板、靜態資產、已提交 JSON、未授權筆記 403 與授權後舊連結 200；不只驗證 editable 能安裝。

私人資產盤點需明確指定工作區與 CRM，不能讓 CI 自動探索使用者目錄：

```sh
python -m asset_audit /path/to/workspace --crm-dir /path/to/StudentCRM
```

這些驗收不包含正式 Supabase／Vercel 端到端、服務恢復或計費 Egress 實測；PR 分支仍關閉自動部署，未合併、部署或修改帳務。
