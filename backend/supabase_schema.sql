-- Run this in your Supabase project's SQL Editor before switching
-- AUDIT_BACKEND to "supabase". Creates the audit_log table matching
-- the StepResult schema written by backend/engine/audit.py.

create table if not exists audit_log (
    id                          bigserial primary key,
    event_id                    text not null,
    step_number                 int not null,
    simulated_timestamp         timestamptz not null,
    decline_code                text,
    cause_category               text,
    diagnosis_rationale          text,
    recovery_probability         numeric,
    attempt_count_before         int,
    policy_action                text,
    policy_rationale             text,
    blocked                      boolean,
    block_reason                 text,
    razorpay_success              boolean,
    razorpay_payment_link_id      text,
    razorpay_payment_link_url     text,
    razorpay_mock                 boolean,
    outcome                       text,
    event_status_after            text,
    amount                        numeric,
    inserted_at                   timestamptz default now()
);

-- Useful indexes for the dashboard's queries (Day 6+)
create index if not exists idx_audit_log_event_id on audit_log (event_id);
create index if not exists idx_audit_log_policy_action on audit_log (policy_action);
create index if not exists idx_audit_log_event_status_after on audit_log (event_status_after);

-- Row Level Security: enable and allow the anon/service key used by the
-- app to read/write. Adjust policies before any real public deployment —
-- this is a permissive hackathon-appropriate default, not production-grade.
alter table audit_log enable row level security;

create policy "allow all for authenticated app" on audit_log
    for all
    using (true)
    with check (true);