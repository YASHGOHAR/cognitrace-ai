# Local setup (Windows PowerShell)

These steps use local development resources only. They do not change hosted Render, Netlify, or Supabase settings.

## Prerequisites

- Git and Python **3.14** (the version in `.python-version`).
- Node.js **22.12.0** and npm. `.nvmrc` and `.node-version` select the expected Node version.
- Docker Desktop with Linux engine only for local Supabase.
- A Gemini API key only for real extraction. Unit tests and fixture evaluation do not need one; no paid quota is assumed.

See the [official Vite guide](https://vite.dev/guide/) for its Node compatibility requirement.

## Clone and Python environment

```powershell
git clone https://github.com/YASHGOHAR/cognitrace-ai.git
Set-Location cognitrace-ai
git status --short --branch
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The current developer workspace has uncommitted frontend and Supabase changes; a fresh clone will not contain them unless they are reviewed and shared. Do not copy a developer's private `.env`. Edit your own local `.env`; only set `GEMINI_API_KEY` if you intend to make a real extraction. `SUPABASE_URL` is needed for session-route JWT verification. For a local Supabase stack,
use `http://127.0.0.1:54321`; hosted Supabase URLs must use HTTPS. The example selects SQLite.

If PowerShell blocks venv activation, allow it for this shell only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Run backend from repository root with `python -m backend`. It listens on `0.0.0.0` at `PORT` (default 8000). Health is at `http://127.0.0.1:8000/health`; OpenAPI is at `/docs`. Health is public; session routes require a valid Supabase Auth user bearer JWT.

## Frontend

In a second PowerShell window:

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open Vite's printed URL (normally `http://localhost:5173` or `http://127.0.0.1:5173`). Leave `VITE_USE_MOCK_API=true` while real auth/ownership integration is unverified. Real mode needs the public Supabase project URL and publishable key plus a backend URL. Every `VITE_*` value is bundled into public browser code; never place Gemini credentials, a Supabase secret/service-role key, or a shared backend secret there.

### Second-device checklist

GitHub contains source code, lockfiles, and safe environment templates, but not
private credentials or a running backend/database. On a new device:

1. Install Node `22.12.0`, Python `3.14`, and Docker Desktop.
2. Run `npm ci` from `frontend/`; this uses the committed `frontend/package-lock.json`.
3. Run `python -m pip install -r requirements.txt` in the root virtual environment.
4. Copy `.env.example` to `.env` and set your own Gemini key and Supabase values.
5. Copy `frontend/.env.example` to `frontend/.env.local`, set the same Supabase public values and the backend URL.
6. Start the disposable local stack, backend, and frontend using the commands below.

Do not copy `.env`, `frontend/.env.local`, local databases, or Supabase secret/service-role keys into GitHub.

Frontend commands, from `frontend/`: `npm test` runs Vitest; `npm run build` runs TypeScript and the Vite production build. `netlify.toml` configures base `frontend`, build `npm run build`, publish `dist`, and SPA fallback. These commands do not deploy.

## Environment variables

Backend, in root `.env` or host environment:

| Name | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Secret Gemini key, only for real extraction. |
| `GEMINI_MODEL` | Model name; default is in `ai/core/config.py`. |
| `SUPABASE_URL` | Auth issuer/JWKS source; also required by optional Data API storage. |
| `SUPABASE_PUBLISHABLE_KEY` | Public project key for optional Data API. Never use a secret/service-role key. |
| `COGNITRACE_STORAGE_BACKEND` | `sqlite` by default; `supabase` opts into Data API. |
| `COGNITRACE_DB_PATH` | Optional SQLite path; on hosted service use a persistent mounted disk. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact browser origins. Defaults include localhost and the current Netlify origin. |
| `PORT` | Host-provided backend port; default 8000. |

Frontend, in `frontend/.env.local`: `VITE_API_BASE_URL` (backend URL ending in `/api`), `VITE_USE_MOCK_API` (keep true; real mode only when exactly `false`), `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY`. `SUPABASE_DB_URL` is not used by runtime code. `COGNITRACE_API_TOKEN` is not used by session routes.

## Python tests and offline evaluation

From repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ai.evaluation.evaluate
```

The default evaluator loads saved fixture predictions. Neither command calls Gemini. See [testing and evaluation](TESTING_AND_EVALUATION.md).

## Optional local Supabase

Only use a disposable local stack with Docker running. The pinned CLI is run through transient `npx` and may need npm registry access. Do not authenticate/link the CLI or use a linked/remote target.

```powershell
npx --yes supabase@2.121.0 start
npx --yes supabase@2.121.0 db reset
npx --yes supabase@2.121.0 test db
npx --yes supabase@2.121.0 stop
```

The reset command recreates the local Postgres DB, applies migrations, and can erase existing local DB data. Use it only on a disposable local stack after deciding local data can be discarded. The test command runs local pgTAP checks; the current RLS test's synthetic rows roll back. Do not add `--linked`. See Supabase's [local workflow](https://supabase.com/docs/guides/local-development/cli-workflows) and [database testing guide](https://supabase.com/docs/guides/local-development/cli/testing-and-linting).

## Troubleshooting

- **Venv activation denied:** use the process-scoped command above or call `.venv\Scripts\python.exe` directly.
- **Vite rejects Node:** use Node 20.19+ or 22.12+ for Vite 8.
- **Session route returns 401:** use a valid Supabase Auth user token; the old shared API token is not accepted.
- **Auth config returns 503:** configure backend `SUPABASE_URL` and confirm JWKS availability.
- **Extraction fails:** check your own Gemini key/model and quota; do not repeatedly retry quota errors.
- **Supabase CLI fails:** check Docker Linux engine and local ports; npm registry access may be needed. Do not link the project as a shortcut.
- **Data disappears after host restart:** container storage may be ephemeral. Configure `COGNITRACE_DB_PATH` on a persistent mount or complete PostgreSQL integration first.
