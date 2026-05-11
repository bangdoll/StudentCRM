alter table public.students enable row level security;
alter table public.teaching_records enable row level security;
alter table public.apple_programs enable row level security;
alter table public.apple_venues enable row level security;
alter table public.apple_attendance_records enable row level security;
alter table public.apple_venue_ledger enable row level security;
alter table public.apple_student_rounds enable row level security;

drop policy if exists "studentcrm_students_read_anon" on public.students;
drop policy if exists "studentcrm_teaching_records_read_anon" on public.teaching_records;
drop policy if exists "studentcrm_students_service_write" on public.students;
drop policy if exists "studentcrm_teaching_records_service_write" on public.teaching_records;
drop policy if exists "studentcrm_apple_programs_read_anon" on public.apple_programs;
drop policy if exists "studentcrm_apple_venues_read_anon" on public.apple_venues;
drop policy if exists "studentcrm_apple_attendance_read_anon" on public.apple_attendance_records;
drop policy if exists "studentcrm_apple_venue_ledger_read_anon" on public.apple_venue_ledger;
drop policy if exists "studentcrm_apple_student_rounds_read_anon" on public.apple_student_rounds;
drop policy if exists "studentcrm_apple_programs_service_write" on public.apple_programs;
drop policy if exists "studentcrm_apple_venues_service_write" on public.apple_venues;
drop policy if exists "studentcrm_apple_attendance_service_write" on public.apple_attendance_records;
drop policy if exists "studentcrm_apple_venue_ledger_service_write" on public.apple_venue_ledger;
drop policy if exists "studentcrm_apple_student_rounds_service_write" on public.apple_student_rounds;

create policy "studentcrm_students_read_anon"
on public.students
for select
to anon, authenticated
using (true);

create policy "studentcrm_teaching_records_read_anon"
on public.teaching_records
for select
to anon, authenticated
using (true);

create policy "studentcrm_students_service_write"
on public.students
for all
to service_role
using (true)
with check (true);

create policy "studentcrm_teaching_records_service_write"
on public.teaching_records
for all
to service_role
using (true)
with check (true);

create policy "studentcrm_apple_programs_read_anon"
on public.apple_programs
for select
to anon, authenticated
using (true);

create policy "studentcrm_apple_venues_read_anon"
on public.apple_venues
for select
to anon, authenticated
using (true);

create policy "studentcrm_apple_attendance_read_anon"
on public.apple_attendance_records
for select
to anon, authenticated
using (true);

create policy "studentcrm_apple_venue_ledger_read_anon"
on public.apple_venue_ledger
for select
to anon, authenticated
using (true);

create policy "studentcrm_apple_student_rounds_read_anon"
on public.apple_student_rounds
for select
to anon, authenticated
using (true);

create policy "studentcrm_apple_programs_service_write"
on public.apple_programs
for all
to service_role
using (true)
with check (true);

create policy "studentcrm_apple_venues_service_write"
on public.apple_venues
for all
to service_role
using (true)
with check (true);

create policy "studentcrm_apple_attendance_service_write"
on public.apple_attendance_records
for all
to service_role
using (true)
with check (true);

create policy "studentcrm_apple_venue_ledger_service_write"
on public.apple_venue_ledger
for all
to service_role
using (true)
with check (true);

create policy "studentcrm_apple_student_rounds_service_write"
on public.apple_student_rounds
for all
to service_role
using (true)
with check (true);
