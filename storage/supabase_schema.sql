-- Run once in the Supabase SQL editor.
create table if not exists applications (
    id bigint generated always as identity primary key,
    created_at text, company text, job_title text, jd_text text,
    inputs jsonb, original_resume_text text, resume_json jsonb, jd_analysis jsonb,
    photo text,  -- base64
    resume_file text, resume_filename text  -- the uploaded resume, base64
);

create table if not exists versions (
    id bigint generated always as identity primary key,
    application_id bigint references applications(id) on delete cascade,
    version_no int, created_at text, model text, intensity text, feedback text,
    resume_json jsonb, cover_letter text, ats_before int, ats_after int, ats_detail jsonb,
    change_log jsonb, notes jsonb, verification jsonb,
    prompt_tokens int, completion_tokens int, cost_usd double precision, is_final boolean default false
);

create table if not exists usage_log (
    id bigint generated always as identity primary key,
    application_id bigint, version_id bigint, company text, step text, model text,
    prompt_tokens int, completion_tokens int, cost_usd double precision, ts text
);

-- The app connects with the service-role key (kept in Streamlit secrets), so RLS stays enabled
-- with no public policies: nobody can read this data with the anon key.
alter table applications enable row level security;
alter table versions enable row level security;
alter table usage_log enable row level security;

-- Upgrading a project created before uploaded resume files were stored? Run just this line:
-- alter table applications add column if not exists resume_file text, add column if not exists resume_filename text;
