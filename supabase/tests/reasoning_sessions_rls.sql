begin;
select plan(9);

-- Seed rows as the migration-test owner, then impersonate PostgREST roles.
-- The migration test runs inside a transaction and rolls these synthetic users back.
insert into auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at)
values
  ('00000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'rls-a@example.invalid', '', now(), now(), now()),
  ('00000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'rls-b@example.invalid', '', now(), now(), now())
on conflict (id) do nothing;

insert into public.reasoning_sessions(session_id, created_at, session_text, reasoning_json, owner_id)
values
  ('rls-user-a', now(), 'Synthetic owner A session', '{"problem":null,"decisions":[],"justifications":[],"alternatives_considered":[],"assumptions":[]}', '00000000-0000-0000-0000-00000000000a'),
  ('rls-user-b', now(), 'Synthetic owner B session', '{"problem":null,"decisions":[],"justifications":[],"alternatives_considered":[],"assumptions":[]}', '00000000-0000-0000-0000-00000000000b');

set local role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', true);
select set_config('request.jwt.claims', '{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}', true);
select is((select count(*)::integer from public.reasoning_sessions where session_id = 'rls-user-a'), 1, 'owner can read own row');
select is((select count(*)::integer from public.reasoning_sessions where session_id = 'rls-user-b'), 0, 'owner cannot read another user row');
select lives_ok($$insert into public.reasoning_sessions(session_id, created_at, session_text, reasoning_json, owner_id)
  values ('rls-insert-own', now(), 'Synthetic own row', '{"problem":null,"decisions":[],"justifications":[],"alternatives_considered":[],"assumptions":[]}', '00000000-0000-0000-0000-00000000000a')$$, 'owner can insert own row');
select throws_ok($$insert into public.reasoning_sessions(session_id, created_at, session_text, reasoning_json, owner_id)
  values ('rls-insert-other', now(), 'Synthetic cross-user row', '{"problem":null,"decisions":[],"justifications":[],"alternatives_considered":[],"assumptions":[]}', '00000000-0000-0000-0000-00000000000b')$$,
  '42501', null, 'owner cannot insert for another user');
select throws_ok($$update public.reasoning_sessions set session_text = 'Changed by owner'
  where session_id = 'rls-user-a'$$,
  '42501', null, 'authenticated role cannot update sessions');
select throws_ok($$delete from public.reasoning_sessions where session_id = 'rls-user-a'$$,
  '42501', null, 'authenticated role cannot delete sessions');
select throws_ok($$update public.reasoning_sessions set session_text = 'Changed across users'
  where session_id = 'rls-user-b'$$,
  '42501', null, 'authenticated role cannot update another user session');
select throws_ok($$delete from public.reasoning_sessions where session_id = 'rls-user-b'$$,
  '42501', null, 'authenticated role cannot delete another user session');
reset role;
set local role anon;
select throws_ok($$select * from public.reasoning_sessions$$, '42501', null, 'anonymous role has no table access');
reset role;

select * from finish();
rollback;
