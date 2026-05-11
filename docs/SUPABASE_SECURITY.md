# StudentCRM Supabase 安全策略

## 原則

1. `SUPABASE_SERVICE_ROLE_KEY` 只能存在於後端、遷移工具或受控 Worker。
2. Web Dashboard 與 Native App 不直接持有 service role key。
3. 對外前端若需直連 Supabase，只能使用 anon key，且資料表必須先啟用 RLS。
4. 寫入雲端資料前，先由後端 API 或 Worker 做欄位驗證與審計紀錄。

## 目標專案

- Supabase Dashboard：`https://supabase.com/dashboard/project/vwgbbvodfzsagrtyuybl`
- Supabase API URL：`https://vwgbbvodfzsagrtyuybl.supabase.co`
- 專案 ref：`vwgbbvodfzsagrtyuybl`

## 初始化順序

1. 在 Supabase SQL Editor 執行 `StudentCRM/scripts/supabase_schema.sql`。
2. 再執行 `StudentCRM/scripts/supabase_rls_readonly.sql`。
3. 本機乾跑：
   ```bash
   python3 StudentCRM/scripts/migrate_to_supabase.py
   ```
4. 確認筆數與欄位後，才執行：
   ```bash
   python3 StudentCRM/scripts/migrate_to_supabase.py --apply
   ```

## 前端用 Key 邊界

- 可以公開：`SUPABASE_URL`、`SUPABASE_ANON_KEY`
- 禁止公開：`SUPABASE_SERVICE_ROLE_KEY`

目前 `/dashboard` 仍透過 FastAPI API 閘道讀資料，尚未直接使用 Supabase anon key。這是安全預設；等 RLS 驗證完成後，才考慮讓 Next.js/Vercel 前端直連 Supabase。

## 上線前檢查

- `students` 已啟用 RLS。
- `teaching_records` 已啟用 RLS。
- `apple_programs` / `apple_venues` / `apple_attendance_records` / `apple_venue_ledger` / `apple_student_rounds` 已啟用 RLS。
- anon / authenticated 只有 `select` policy。
- service role 才有寫入 policy。
- `.env` 不被提交。
- Vercel 不設定 `SUPABASE_SERVICE_ROLE_KEY` 給前端 runtime。
