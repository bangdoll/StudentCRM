# 教學紀錄雲端讀取契約

## 問題與結果

舊搜尋、筆記閱讀器、學員頁及雷達共用全欄位歷史下載。這次拆為有上限的 metadata 列表、精準單篇、伺服器端全文篩選及雷達最近三篇批次讀取。未採用本機未提交的欄位投影草稿；其 cycle/lesson/path/filename/preview/topics 並非 teaching_records 頂層欄位。

- `TeachingReads` 由既有 `StudentDataGateway` 提供；所有雲端讀取沿用現有 HTTP 邊界與憑證，不新增公開資料庫權限或 schema。
- `GET /api/teaching-records?student_id=…&cursor=…&limit=50&q=…` 沿用教練門禁，回傳 `items,next_cursor,has_more`。預設 50，最大 100；沒有正文或完整 raw。
- 列表先在 PostgREST 篩選，按 `date DESC NULLS LAST,id DESC` 穩定排序，再取頁。cursor 綁定學生和查詢；空日期與 NULL 有確定順序。以小型 ID probe 處理平台 max_rows 小於請求頁數，不能因平台截斷而漏掉後續頁。
- path/filename/preview 從 raw 子欄位投影，不把整份 raw 搬出資料庫。preview 回應最多 280 字。日期欄位目前仍為 text，採資料庫文字排序；不在本 PR 修改歷史日期。
- `/my`、`/student`、數位管理個人頁及搜尋提供較早紀錄連結。數位管理 API 保留總統計，筆記清單有上限，提供完整索引端點。頁面數字不冒充全部紀錄數。
- 數位管理總覽、課程統計及雷達會分頁掃描 metadata，以維持全量統計完整性；這是小欄位索引掃描，不是下載歷史正文。
- `/note?path=…` 與 `/open_file?path=…` 保留 UUID、中文原始路徑、檔名連結；先查原路徑，再查檔名，歧義拒絕。前後篇僅讀同一學員的兩筆 metadata。學員 token 限制到其學員／已授權班級；新 API 不開放匿名或學員任意查詢。
- 雲端閱讀器不再讀取本地筆記來覆蓋正文，避免舊快照掩蓋錯誤；桌面 local 模式保留既有檔案閱讀行為。雲端正文只取 content；只有該欄空白時才讀同筆 raw.content，避免同時傳輸兩份正文。
- 全文搜尋在資料庫篩選 title/student_name/content/raw.content/raw.preview，再回傳 metadata。保留姓名別名及班級搜尋；中文、英文大小寫與特殊字元依字面子字串搜尋，沒有改成英文斷詞。結果使用既有短摘要，不額外下載全文來產生片段。
- 雷達先以 metadata 選每位有效學員最近三篇，再批次讀取其正文；保留原分析與人工 followup。Bootstrap 僅取最新一篇。Hub 顯示最新篇微行動卡，歷史篇完整卡片仍在單篇閱讀器，避免為展開列表下載全部正文。
- 動態個人頁／搜尋／雷達不再因 hover 預載；靜態資產原功能保留。

## 更新、失敗與一致性

不新增持久雲端正文／索引快取；每個 HTTP 請求重新讀取，筆記及新列表 API 使用 `private,no-store`。不依賴沒有更新觸發器的 updated_at，新增、修改、刪除、重新歸屬於下一次讀取可見。班務 apple_programs 既有 30 秒快取不在本 PR 重構範圍。

402/403/5xx、逾時或無效 JSON 明確回 503，不自動重試、不擴大成全表、不以本地舊資料冒充成功。沒有新資料表、RPC、migration 或額外付費快取服務。

Keyset 解決同日排序與新資料插入的 offset 位移，但不是資料庫快照：在翻頁中修改既有紀錄日期，應回最新紀錄重新整理。統計 metadata 與後續正文亦非同一交易；並行刪除會略過已不存在的紀錄。

## 驗證

執行：

```sh
PYTHONPATH=. python -m pytest tests/test_cloud_teaching_reads.py tests/test_note_service.py tests/test_performance_and_lazy_load.py -q
```

新增 27 個雲端測試使用合成學員／筆記與 HTTP 邊界的 PostgREST 模擬器，驗證欄位、UUID 型別、篩選與筆數上限；不 mock gateway、路由或搜尋／雷達演算法。教學資料和快取檔皆不存在，沒有正式憑證，無須讀取實際學員資料。

範圍包含：1,201 筆完整翻頁、空／同日／NULL 日期、max_rows=1/7、scope cursor、舊路徑、raw-only 正文、正文詞搜尋、特殊字元、班級舊連結、跨學員隔離、API 門禁、正文更新／刪除／重新歸屬、無效 JSON／402／403／500，以及正文極大時列表仍小於 100 KiB。

這是雲端契約與 ASGI 路由測試，不是已部署正式 Supabase/Vercel 的端到端驗收；沒有聲稱已恢復正式服務或實測計費 Egress 節省 99%。

初次診斷快照：main `21021a9` 與當時修正版曾排除無法匯入的外部 `merge_students` 以比較失敗集合，分別 174／200 項通過、相同 10 項失敗；這只是定位用的局部結果，不能當完整驗收。後續已修正套件探索、外部腳本依賴、資料路徑、測試隔離與假憑證；原有 CI 現在執行全部 `tests/` 並檢查零 skip。私人實體教案盤點和可攜功能回歸明確分開，原門檻保留，詳見 [完整 CI 說明](full-ci.md)。

## PR 與發布邊界

`vercel.json` 只對 `codex/studentcrm-paged-cloud-reads` 關閉 Git 自動部署，以便依使用者指示提交 PR 而不產生 preview deployment。其他分支未指定，維持 Vercel 預設行為。開 PR 不代表批准合併或部署。

未合併、未部署、未升級或變更帳務／正式流量設定。正式測試與實際用量比較需等使用者另行授權；現有額度限制不會因 PR 自動解除。
