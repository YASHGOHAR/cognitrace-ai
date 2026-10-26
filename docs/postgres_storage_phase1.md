# Cognitrace Phase 1 PostgreSQL storage review

## Runtime path

- SQLite remains the default (`COGNITRACE_STORAGE_BACKEND=sqlite`).
- The optional `supabase` setting creates a new `SupabaseSessionStore` per authenticated request.
- The adapter uses the Supabase HTTPS Data API and forwards the access token returned by `get_current_user`; `owner_id` is derived from the same verified token subject.
- It sends a project publishable key as `apikey`, never a service-role key.
- The API query includes an owner filter as defense in depth; the reviewed SQL also enforces ownership using RLS and `auth.uid()`.
- No hosted tables/settings have been accessed or changed, and no session records were read.

## Files in scope

- `ai/storage/session_repository.py`: SQLite wrapper and request-scoped Data API adapter.
- `ai/workflow.py`, `ai/retrieval/keyword_search.py`, `ai/patterns/reasoning_patterns.py`: optional store injection; existing SQLite path remains unchanged.
- `backend/app/security.py`: carries the already-verified bearer token on an identity object with token-hidden repr.
- `backend/app/session_storage.py`, `backend/app/routes/sessions.py`: per-request adapter selection.
- `backend/app/config.py`, `.env.example`: opt-in setting and publishable-key configuration.
- `supabase/migrations/202610240001_reasoning_sessions.sql`: review-only DDL and grants.
- `supabase/tests/reasoning_sessions_rls.sql`: nine pgTAP policy checks; developer-reported as passing 9/9 against the isolated local stack, not a remote database.

## Security boundaries

The API verifies the incoming JWT's signature, issuer, audience, expiry, and role before it constructs the adapter. Supabase Data API receives that same bearer token, not a shared backend token. RLS therefore evaluates the user's verified identity again. The adapter binds `owner_id` from the verified identity and includes it in every retrieval filter and inserted row. PostgreSQL rejects owner-mismatched insertions; RLS filters cross-user reads. The migration grants no `anon` access and grants no update/delete access to authenticated users.

The Data API HTTPS adapter uses Python's standard library, so no extra runtime package is introduced. All storage errors returned to API callers are sanitized. The optional PostgreSQL mode is disabled unless explicitly configured.

## Environment variables

- `COGNITRACE_STORAGE_BACKEND=sqlite` (default); `supabase` is optional and must not be enabled before the migration is approved/applied.
- `SUPABASE_URL` (already required for JWT verification).
- `SUPABASE_PUBLISHABLE_KEY` (publishable Data API project key; never the service-role key).
- `COGNITRACE_DB_PATH` applies only to SQLite.
- Existing `GEMINI_API_KEY`, `GEMINI_MODEL`, `CORS_ALLOWED_ORIGINS`, and `PORT` remain as documented. No Gemini call is made by storage tests.

No database connection string is needed at runtime. A direct PostgreSQL connection / `psycopg` is not used. Supabase project Postgres and Data API must be enabled and the table must be exposed in the `public` schema. The migration should be reviewed/applied through the authorized Supabase migration process only after approval.

## Verification and limits

Offline Python tests verify that separate request adapters forward separate user tokens and owner filters, that pagination and JSON round-trip work, and that invalid/anonymous requests are rejected by the backend verifier. Fake transports are not a substitute for a hosted PostgREST/JWT/RLS integration test. The developer reports the pgTAP script passed 9/9 on an isolated local Supabase stack. This handover task did not independently rerun it. It verifies database grants/RLS, not the complete FastAPI/JWKS/Data API request path. Before a production switch, separately verify the full path on local test users and review backup, migration, and rollback plans.

No SQLite data was inspected, imported, or altered. No remote table/settings were accessed. Data migration, rollback execution, production configuration, and deployment are explicitly outside this phase.

