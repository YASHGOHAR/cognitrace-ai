-- Cognitrace session store for the Supabase Data API.
-- Review and apply separately; this file has not been applied to a hosted project.
-- Access is restricted to verified authenticated users' own rows.

create table if not exists public.reasoning_sessions (
    session_id text primary key,
    created_at timestamptz not null,
    session_text text not null,
    reasoning_json jsonb not null,
    owner_id uuid not null references auth.users(id) on delete cascade
);

create index if not exists idx_reasoning_sessions_owner_created
    on public.reasoning_sessions (owner_id, created_at desc, session_id desc);

alter table public.reasoning_sessions enable row level security;

revoke all on table public.reasoning_sessions from public, anon, authenticated;
grant select, insert on table public.reasoning_sessions to authenticated;

 drop policy if exists "users_read_own_reasoning_sessions" on public.reasoning_sessions;
create policy "users_read_own_reasoning_sessions"
    on public.reasoning_sessions for select to authenticated
    using (owner_id = (select auth.uid()));

 drop policy if exists "users_insert_own_reasoning_sessions" on public.reasoning_sessions;
create policy "users_insert_own_reasoning_sessions"
    on public.reasoning_sessions for insert to authenticated
    with check (owner_id = (select auth.uid()));

-- There are deliberately no update or delete grants/policies in this phase.
