# Security and environment

## Environment variable inventory

Never copy values from private local environment files into docs, chat, frontend bundles, or Git. `.env.example` contains placeholders, not credentials. Configure each developer's own environment independently.

| Variable | Location | Classification / purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Backend only | Secret; authorizes Gemini requests. No key is needed for offline tests. |
| `GEMINI_MODEL` | Backend | Non-secret model selector; default is defined in `ai/core/config.py`. |
| `SUPABASE_URL` | Backend | Project URL used as JWT issuer base and JWKS location; required for session authentication. |
| `SUPABASE_PUBLISHABLE_KEY` | Backend optional storage | Publishable project identifier/key for the Supabase Data API. It is not a service-role key. |
| `COGNITRACE_STORAGE_BACKEND` | Backend | `sqlite` default or explicit opt-in `supabase`. |
| `COGNITRACE_DB_PATH` | Backend SQLite | Local/volume path; not a credential. Use persistent storage when hosted. |
| `CORS_ALLOWED_ORIGINS` | Backend | Comma-separated exact browser origins. |
| `PORT` | Backend | Host-provided listener port. |
| `VITE_API_BASE_URL` | Frontend build | Public backend URL. |
| `VITE_USE_MOCK_API` | Frontend build | Public mode selector; example stays `true`. |
| `VITE_SUPABASE_URL` | Frontend build | Public project URL for Supabase Auth. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Frontend build | Public browser publishable key. Never use `sb_secret_*` or service-role credentials. |

Do not configure `GEMINI_API_KEY`, database passwords, access tokens, JWT signing secrets, Supabase secret/service-role keys, or shared server credentials as `VITE_*`. Vite publishes these variables in browser assets. `SUPABASE_DB_URL` is not used by this runtime; `COGNITRACE_API_TOKEN` is not used by session routes.

## Authentication path

1. The browser's real mode signs in with Supabase Auth. Supabase JS is configured with `persistSession: false`; the user access token is held in memory. The example remains mock mode.
2. Each session HTTP request sends `Authorization: Bearer <user access token>`; fetch uses `credentials: omit`. CORS allows `Authorization` but does not allow cookies.
3. `backend/app/security.py::get_current_user` loads the Supabase JWKS from `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` and validates signature (ES256/RS256), issuer, authenticated audience, role, expiry, and subject. The verified subject is the owner ID.
4. SQLite adapter scopes its queries/writes to the owner ID. In optional Supabase mode, a per-request adapter forwards the same user token and sends the owner ID in query/write data. The publishable key is the Data API `apikey`, never a session-operation credential.
5. PostgreSQL independently enforces owner equality with `auth.uid()` through RLS. The migration grants authenticated only SELECT/INSERT. There is no update/delete permission; anonymous has none.

The API returns sanitized 401 for missing/invalid tokens and 503 if JWT verification is not configured or the key service cannot be reached. Session routes never accept an owner ID from user input. Cross-owner reads return 404.

## Database permissions and privacy

`supabase/migrations/202610240001_reasoning_sessions.sql` creates the table and owner index, enables RLS, revokes broad access, and grants authenticated SELECT/INSERT. Policies check `owner_id = auth.uid()` on select and insert. No policy/grant permits update/delete. The pgTAP file uses synthetic identities and a transaction rollback.

SQLite itself does not enforce row-level security. Backend routes pass the verified owner into the owner-bound store; do not add a user-facing route that calls unscoped functions. Existing SQLite rows with null owner cannot be returned to an authenticated owner query. `data/` and SQLite suffixes are ignored by Git.

## Local files and sharing

The root `.gitignore` ignores `.env`, `.env.*` except `.env.example`, venvs, caches, `data/`, and database files. `supabase/.gitignore` excludes CLI `.temp` and `.branches`. Frontend ignore rules cover `node_modules`, `dist`, and `.env`. The inspected checkout has an ignored root `.env` and ignored Supabase CLI temporary state. Their contents were not inspected. An untracked scratch file, `supabase/snippets/Untitled query 263.sql`, is also present; it is not needed by the runtime or migration and should be reviewed for private SQL/data before sharing (it was not deleted). Git's tracked-path listing showed `.env.example` but not `.env` or database files; no secret values were printed.

Before sharing changes, inspect staged file names and the staged diff; never stage `.env`, databases, generated Supabase state, tokens, or user sessions. Give a teammate access to the repository and ask them to create their own local environment. If a Gemini key is needed, each developer obtains and configures their own key privately. Share only the Supabase project URL and publishable key through an approved configuration channel if real-mode auth is authorized. Never share service-role credentials for session operations.

## Gaps and cautions

- The complete frontend → verified API JWT → Data API → local PostgreSQL RLS flow still needs an end-to-end test with a disposable local Supabase user.
- A JWT test uses a locally generated ES256 key and mocks only the JWKS lookup. It does not test live JWKS rotation/network behavior.
- SQLite on an ephemeral hosted filesystem is not durable. A persistent mounted disk or verified PostgreSQL configuration is required.
- There is no delete/retention API yet; avoid using sensitive real sessions until this is resolved.
- The private local `.env` and generated CLI state were intentionally not read during handover. Their presence is not evidence that a valid credential is configured.

