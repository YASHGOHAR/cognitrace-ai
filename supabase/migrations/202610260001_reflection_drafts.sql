-- Durable in-progress reflections, owned and readable only by their signed-in user.

create table if not exists public.reflection_drafts (
    session_id text primary key,
    owner_id uuid not null references auth.users(id) on delete cascade,
    title text not null check (length(trim(title)) > 0),
    messages jsonb not null default '[]'::jsonb check (jsonb_typeof(messages) = 'array'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_reflection_drafts_owner_updated
    on public.reflection_drafts (owner_id, updated_at desc);

alter table public.reflection_drafts enable row level security;
revoke all on table public.reflection_drafts from public, anon, authenticated;
grant select, insert, update, delete on table public.reflection_drafts to authenticated;

drop policy if exists "users_read_own_reflection_drafts" on public.reflection_drafts;
create policy "users_read_own_reflection_drafts"
    on public.reflection_drafts for select to authenticated
    using (owner_id = (select auth.uid()));

drop policy if exists "users_insert_own_reflection_drafts" on public.reflection_drafts;
create policy "users_insert_own_reflection_drafts"
    on public.reflection_drafts for insert to authenticated
    with check (owner_id = (select auth.uid()));

drop policy if exists "users_update_own_reflection_drafts" on public.reflection_drafts;
create policy "users_update_own_reflection_drafts"
    on public.reflection_drafts for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

drop policy if exists "users_delete_own_reflection_drafts" on public.reflection_drafts;
create policy "users_delete_own_reflection_drafts"
    on public.reflection_drafts for delete to authenticated
    using (owner_id = (select auth.uid()));
