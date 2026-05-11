create table if not exists public.students (
  id text primary key,
  name text not null,
  aliases jsonb not null default '[]'::jsonb,
  file text,
  lessons_count integer not null default 0,
  latest_date text,
  next_lesson text,
  tags jsonb not null default '[]'::jsonb,
  recurring_schedule text,
  schedule_exceptions jsonb not null default '[]'::jsonb,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.teaching_records (
  id text primary key,
  student_id text references public.students(id) on delete set null,
  student_name text,
  title text,
  date text,
  lesson_num integer,
  lesson_sub text,
  created text,
  edited text,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_students_latest_date on public.students(latest_date);
create index if not exists idx_students_next_lesson on public.students(next_lesson);
create index if not exists idx_teaching_records_student_id on public.teaching_records(student_id);
create index if not exists idx_teaching_records_date on public.teaching_records(date);

create table if not exists public.apple_programs (
  id text primary key,
  name text not null,
  url text,
  description text,
  schedule text,
  capacity text,
  round_size integer not null default 8,
  price_per_student integer not null default 0,
  validity_rule text,
  leave_rule text,
  join_rule text,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.apple_venues (
  id text primary key,
  program_id text references public.apple_programs(id) on delete cascade,
  name text not null,
  address text,
  parking text,
  metro text,
  cost_per_person integer not null default 0,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.apple_attendance_records (
  id text primary key,
  program_id text references public.apple_programs(id) on delete cascade,
  date text not null,
  venue text,
  attendee_count integer not null default 0,
  attendees jsonb not null default '[]'::jsonb,
  note text,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.apple_venue_ledger (
  id text primary key,
  program_id text references public.apple_programs(id) on delete cascade,
  date text not null,
  type text not null,
  amount integer not null default 0,
  payer text,
  headcount integer,
  note text,
  balance_after integer not null default 0,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.apple_student_rounds (
  id text primary key,
  program_id text references public.apple_programs(id) on delete cascade,
  student_name text not null,
  label text not null,
  payment_status text,
  sessions jsonb not null default '[]'::jsonb,
  attended_count integer not null default 0,
  sort_order integer not null default 0,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_apple_attendance_program_date on public.apple_attendance_records(program_id, date);
create index if not exists idx_apple_venue_ledger_program_date on public.apple_venue_ledger(program_id, date);
create index if not exists idx_apple_student_rounds_program_student on public.apple_student_rounds(program_id, student_name);
