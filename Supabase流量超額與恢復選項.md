# Supabase 流量超額、重置時間與恢復選項

查核時間：2026-10-21 07:26–07:41（Asia/Taipei）。範圍：`rdcoach` 組織、Smart Flow 使用的 `ai-trends-daily` 與同組織 `StudentCRM`。使用 Supabase 已驗證管理工具、登入後 Dashboard、限制通知郵件及官方文件；全程唯讀。

## 結論

本次是**組織共用的未快取 Egress 超額**，不是資料庫空間用完，也不是 Vercel 方案不足。組織目前為 Free；5 GB 額度供兩個專案共用，並非每個專案各有 5 GB。

| 同一計費週期 | 未快取 Egress | 占組織用量 |
|---|---:|---:|
| StudentCRM | 7.504 GB | 約 72.1% |
| ai-trends-daily／Smart Flow | 2.905 GB | 約 27.9% |
| 組織合計 | **10.408 GB／5 GB** | **208%** |

StudentCRM 單獨就已超過整個組織的免費額度，因此不能將這次限制全部歸因於 Smart Flow 爬蟲。組織限制會波及兩案；近期紀錄亦出現 StudentCRM `students`／`teaching_records` 與 Smart Flow `news_items` 的 402。Smart Flow 將上游失敗轉成網站端 503。

專案顯示數字四捨五入後合計 10.409 GB，與組織 10.408 GB 差 0.001 GB；不能把這個差異視為第三個來源。Dashboard 註明可能延遲最多 1 小時。

快取 Egress 另為 **0.025 GB／5 GB**，與未快取額度獨立，不能互抵。Vercel 的網頁 HIT 與 Supabase 的 Cached Egress 也是不同層；網頁快取可減少未來 DB 讀取，不能回收已用流量。[官方 Egress 說明](https://supabase.com/docs/guides/platform/manage-your-usage/egress)

## 為什麼傳輸量大

### StudentCRM：完整教學紀錄的重複讀取是明確線索

- Dashboard 高峰日 **2026-10-02：738.158 MB，100.0% 為 PostgREST Egress**，即資料 API 傳輸。這是單日分類證據，並非全月逐筆歸因。
- `pg_stat_statements` 可見未依學員篩選的 `teaching_records.*`、按日期排序查詢，累計 **1,700 次**。統計起點為 **2026-09-03 07:19 台灣時間**，早於本期 9 月 27 日，**不能稱為本月 1,700 次**。
- 最近完整 24 小時的可讀日誌窗為 **2026-10-20 07:32:53–2026-10-21 07:32:53（台灣時間）**。其中 6 次成功請求使用 `select=*`，沒有明示 limit、沒有學員條件，User-Agent 為 `Python-urllib/3.12`。另見 `python-requests`。這與腳本／維護程式讀取相符，但 UA 無法驗證真正身分，也不能據此指認某個人或特定自動化。
- 以資料庫端聚合估算，目前 **948 筆教學紀錄的完整 JSON 約 23,921,516 bytes（23.92 MB）**；其中正文約 9.51 MB、原始 JSON 約 13.65 MB。沒有讀回任何一筆學員內容或姓名。
- 同樣 948 筆，若列表只含 id、標題、日期、學員關聯、課次／科目等資訊，估算 JSON 約 **237,210 bytes（0.237 MB）**，比完整快照少約 **99.0%**。這只是欄位投影的資料量比較，**未修改 StudentCRM，也不是實際網路或帳單降幅保證**。

已證明的是：反覆全欄讀取會把大量正文與 raw 一起搬出資料庫。建議後續優先評估列表分頁、明確欄位、開啟紀錄才取正文、增量同步及快取，並查明哪些腳本需要整份資料。

### Smart Flow：高頻新聞查詢仍是第二個來源

- Dashboard **2026-10-20：114.659 MB，100.0% 為 PostgREST Egress**。
- 同一 24 小時日誌窗內，`news_items` 的 `node` 請求有 **27,906 次 200、1,134 次 402**；這是 DB API 請求數，不是 Vercel Function Invocations，也不能據此還原原始訪客／爬蟲身分。
- 長期查詢統計中可見標籤查詢及舊 slug 全欄查詢等歷史模式；統計自 2025 年 12 月開始，不能當本月呼叫量。PR #8 已補 ISR、失效、有限重試與縮減部分讀取欄位，但仍未部署；不能把尚未上線的修復當成已降低流量的證據。

日誌中多個大回應未提供 Content-Length。例如 6 次完整教學紀錄讀取皆無此欄位，因此**日誌的 bytes=0 不是零流量**；不能用可見 Content-Length 加總替代帳務 Egress，也不能拿現有 JSON 大小乘長期呼叫數冒充本月帳單。

## 何時重置、何時開始限制

- Dashboard 本期為 **2026-09-27 至 2026-10-27**，不是每月 1 日重置。
- Supabase 在 **2026-10-21 06:43:40（台灣時間）**寄出「Restrictions are applied to your org rdcoach」，明確通知本期額度耗盡、於 **October 27, 2026** 補回。這證明通知時間，不是首次超過 5 GB 的精確時刻。[查看限制通知](https://mail.google.com/mail/u/?authuser=bangdoll2k%40gmail.com#all/1a15b7c128aae52f)
- 平台頁面與郵件只提供日期，未提供精確時分與時區，因此不能承諾**台灣時間 10 月 27 日 00:00**立即恢復。官方亦說明週期刷新後解除限制可能稍有延遲。[官方 Fair Use／恢復規則](https://supabase.com/docs/guides/platform/billing-faq#fair-use-policy)
- 通知信當時記載 **10.14 GB of 5.5 GB**；目前 Dashboard 與公開方案則是 **10.408／5 GB**。這個口徑差異未獲官方解釋，不把 5.5 GB 當成新的方案額度。若需要精確解除時刻或釐清門檻，應由 Supabase 支援確認；本次未發送支援單或郵件。

## 恢復選項與費用

以下為美元、未稅估算；首次結帳金額、稅額與當期按時數費用，需以正式確認頁為準。本次只查看方案列表，沒有按 Upgrade、提交付款或更動支出上限。

| 選項 | 費用 | 恢復與限制 |
|---|---:|---|
| 維持 Free，等待 10 月 27 日週期刷新 | US$0 | 額度刷新後按官方規則解除，可能略延；目前服務限制仍在。若讀取模式不改善，下期仍有再次超額風險 |
| 將目前 rdcoach 組織升為 Pro，保留兩個活躍專案 | **常態整月約 US$35 起** | 官方表示升級可立即解除額度限制；不需為此部署網站。之後仍應實測兩案 API 與頁面恢復 |
| 請 Supabase 支援確認用量／重置時間或是否誤判 | 詢問本身不需升級 | 不能保證提前解鎖；本次未送出任何請求 |

### 為什麼約 US$35，而非只有 US$25

官方是以組織訂閱搭配每個活躍專案的 compute 計費。以兩個最低計費規格、都運行整月估算：

`US$25 Pro + 約 US$10 × 2 個專案 − US$10 組織 compute credit = 約 US$35／月`

Nano 在付費組織亦按 Micro 價格計算；compute 按小時計費，實際月份長度、升級時間與額外服務會影響帳單。這不是已取得或已接受的首次付款報價。[官方計價](https://supabase.com/pricing)、[Compute 計費與 Nano 規則](https://supabase.com/docs/guides/platform/manage-your-usage/compute)

Pro 包含**組織共用**的 250 GB 未快取 Egress 與獨立 250 GB 快取 Egress；不是每案各 250 GB。以目前 10.408 GB 而言，尚未超過 Pro 額度，不會就這筆用量產生額外 Egress 超額費。超過 Pro 額度後，未快取為 **US$0.09／GB**、快取為 **US$0.03／GB**。[官方額度與單價](https://supabase.com/docs/guides/platform/manage-your-usage/egress)

**不能把目前超出的 5.408 GB 直接乘 US$0.09，付約 US$0.49 就解鎖。**Free 不是按 GB 補購的付費方案；關閉 Spend Cap 是 Pro 的超額計費選項，並非免費解鎖方式。本次用量也不需要為了恢復而在 Pro 關閉 Spend Cap。Spend Cap 僅涵蓋部分項目，亦非整張帳單的硬上限。[官方成本控制](https://supabase.com/docs/guides/platform/cost-control)

### 後續架構與改善

1. 若兩個服務都需要持續可用，整個組織 Pro 約 US$35／月是目前較直接的付費選項；仍應先優化 StudentCRM 的大資料讀取。
2. 若願意等待，先維持 Free 至平台週期刷新，再驗收恢復；程式改善需另外確認實作／部署範圍。
3. 額度問題依規則處理後，長期可評估組織隔離：例如 StudentCRM 放單獨 Pro、Smart Flow 留 Free，基本費可能約 US$25／月起。這涉及專案轉移、權限與整合檢查，**不是本期立即解鎖捷徑**；轉移前已產生的用量仍歸來源組織，且不能藉搬移消除歷史超額。本次未轉移、建立、暫停或刪除專案。[官方轉移規則](https://supabase.com/docs/guides/platform/project-transfer)
4. 清理資料、停用專案或部署快取只能降低未來用量，不能扣回已產生的本期 Egress。未依此採取任何處置。

## 其他核對與驗收邊界

- 資料庫與 Storage 容量仍在免費額度內；本次限制明確是 Egress Exceeded。Log Ingestion 雖顯示 157%，但目前標為 UPCOMING／2027 年初前寬限，不是這次限制的原因。
- Dashboard 另有平台事件橫幅；官方事件為 us-east-2 專案卡在 restarting。兩案分別在 ap-south-1、ap-northeast-1，且回報明確 quota 錯誤，不能把本次問題混作該重啟事件。[官方事件](https://status.supabase.com/incidents/01M5DN6V02FJHZTE9390XJM9YY)
- 沒有完整全月逐請求 response bytes、原始呼叫者認證身分或精確重置時刻，故未聲稱已逐 byte 歸因、確認爬蟲身分或保證某分鐘恢復。
- 結束前管理 API 與 Dashboard 均再次確認仍為 **Free**。未升級、未更動帳務／付款／Spend Cap、未變更流量或部署，也沒有資料寫入或發送訊息。

## 證據檔

- `evidence.json`：同週期用量、限制郵件摘要、日期、聚合日誌與費用假設。
- `sql-aggregate-evidence.json`：正規化查詢統計及聚合資料大小，不含學員內容或個人 IP 清單。
- `usage-all-ax.txt`、`usage-overview-final-ax.txt`、`usage-smartflow-ax.txt`、`usage-studentcrm-ax.txt`：實際畫面讀回。
- `billing-redacted-ax.txt`、`plan-options-readonly.txt`：已排除帳務地址與付款資訊的方案／週期摘要。
- `usage-overview.png`、`studentcrm-peak-tooltip.png`、`smartflow-egress-tooltip.png`：用量與單日服務分類畫面。

查看：[組織用量](https://supabase.com/dashboard/org/qozguxdjtrggvwimorch/usage)、[組織帳務](https://supabase.com/dashboard/org/qozguxdjtrggvwimorch/billing)。
