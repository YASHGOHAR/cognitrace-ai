# Cognitrace AI

Cognitrace is a reflection application that helps users think through
decisions and challenges. Gemini responds during a live reflection chat, then
extracts evidence-linked reasoning when the session is completed. Authenticated
sessions are stored per user in PostgreSQL through Supabase.

This README explains how to set up the project from a fresh GitHub clone and
run the complete local website.

## 1. How the application works

The local application has four services/components:

```text
Browser
  React + Vite frontend :5173
          │
          │ Supabase access token + JSON API requests
          ▼
FastAPI backend :8000
          │
          ├── Gemini API          live chat replies and reasoning extraction
          ├── Supabase Auth       account creation, login, JWTs
          └── Supabase REST API   PostgreSQL sessions with RLS
```

The browser does **not** call Gemini directly. The Gemini API key stays in the
backend environment and is never placed in a `VITE_*` variable.

### What happens when you use the website

1. You create an account or sign in through local Supabase Auth.
2. Supabase returns an access token to the browser.
3. The browser sends that token to FastAPI as a bearer token.
4. FastAPI verifies the token and identifies the owner.
5. When you send a chat message, FastAPI sends the conversation to Gemini and
   returns Gemini's reply.
6. When you complete a session, FastAPI sends the transcript to the extraction
   workflow.
7. Gemini returns structured reasoning with exact evidence quotes.
8. The result is saved to PostgreSQL under the authenticated user's ID.

## 2. Repository layout

Important folders and files:

```text
Cognitrace/
├── ai/                         Python AI and storage logic
│   ├── extraction/             Gemini reasoning extraction
│   ├── llm/                    Gemini client
│   ├── patterns/               Cross-session text pattern detection
│   ├── retrieval/              Historical session search
│   ├── schemas/                Validated reasoning models
│   ├── storage/                SQLite and Supabase storage adapters
│   └── workflow.py             Extraction, persistence, retrieval workflow
├── backend/                    FastAPI application
│   └── app/
│       ├── main.py             App, CORS, and health endpoint
│       ├── security.py         Supabase JWT verification
│       ├── schemas.py          API request/response models
│       └── routes/sessions.py  Chat and session endpoints
├── frontend/                   React/Vite website
│   ├── src/App.tsx             Main screens and chat UI
│   ├── src/api/client.ts       Auth and frontend API behavior
│   ├── src/api/backendAdapter.ts  FastAPI request adapter
│   ├── package.json            Frontend scripts and dependencies
│   └── package-lock.json       Locked frontend dependency tree
├── supabase/
│   ├── config.toml             Local Supabase configuration
│   ├── migrations/             PostgreSQL schema and RLS policies
│   └── tests/                  Local pgTAP policy tests
├── tests/                      Python unit and integration-style tests
├── docs/                       Setup, architecture, and evaluation notes
├── .env.example                Safe backend environment template
├── frontend/.env.example      Safe frontend environment template
├── requirements.txt            Locked Python dependencies
├── .python-version             Python version: 3.14
├── .nvmrc                      Node version: 22.12.0
└── .node-version               Node version: 22.12.0
```

## 3. Prerequisites

Install these before cloning or running the application:

- Git
- Python **3.14**
- Node.js **22.12.0** and npm
- Docker Desktop with the Linux engine enabled
- A Gemini API key for live chat and extraction

The project pins the expected versions in `.python-version`, `.nvmrc`, and
`.node-version`. Node version managers such as `nvm` or `fnm` can use the Node
version files automatically.

Check installed tools:

```bash
git --version
python3.14 --version
node --version
npm --version
docker --version
docker info
```

On Windows PowerShell, the Python command may be:

```powershell
py -3.14 --version
```

Docker must be running before starting local Supabase.

## 4. Clone the repository

Choose a folder where you keep development projects, then clone the repository.

### macOS/Linux

```bash
mkdir -p ~/Code
cd ~/Code
git clone <your-github-repository-url> Cognitrace
cd Cognitrace
pwd
git status
```

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force "$HOME\Code"
Set-Location "$HOME\Code"
git clone <your-github-repository-url> Cognitrace
Set-Location Cognitrace
Get-Location
git status
```

The command `pwd` on macOS/Linux and `Get-Location` on PowerShell should show
the repository root. You must run backend commands from this root unless a
command explicitly says `cd frontend`.

## 5. Create the Python environment

Create a virtual environment so project packages do not modify your system
Python.

### macOS/Linux

```bash
cd Cognitrace
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The shell prompt normally shows `(.venv)` after activation. Confirm the
environment:

```bash
which python
python --version
```

### Windows PowerShell

```powershell
Set-Location Cognitrace
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, allow it only for the current PowerShell
process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 6. Configure the backend environment

Create a private backend environment file:

### macOS/Linux

```bash
cp .env.example .env
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

Open `.env` and set your own Gemini key:

```dotenv
GEMINI_API_KEY=your_private_gemini_api_key
# Optional: omit this line to use the repository default model.
GEMINI_MODEL=gemini-3.8-flash
```

Do not commit `.env`. Do not put `GEMINI_API_KEY` in the frontend environment
or in any `VITE_*` variable.

The local Supabase values are added in the next step after the local stack
starts.

## 7. Start the local Supabase stack

Local Supabase runs in Docker. It creates local Auth, PostgreSQL, REST, and
related services. It does not modify a hosted Supabase project.

From the repository root, run:

```bash
npx --yes supabase@2.121.0 start
```

The first start may download Docker images and take several minutes. Then read
the local URLs and keys:

```bash
npx --yes supabase@2.121.0 status
```

Use the `API_URL` and `PUBLISHABLE_KEY` from the output. The local values
normally look like:

```text
API_URL=http://127.0.0.1:54321
PUBLISHABLE_KEY=sb_publishable_...
```

Add these values to the backend `.env`:

```dotenv
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_local_key
COGNITRACE_STORAGE_BACKEND=supabase
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
PORT=8000
```

The publishable key is safe for the local frontend, but never use a Supabase
secret key or service-role key in the frontend.

### Apply or reset local migrations

For a disposable local database:

```bash
npx --yes supabase@2.121.0 db reset --no-seed
```

This applies the migration in `supabase/migrations/` and deletes local Auth
users and local session rows. It does not affect a hosted database.

Run the local row-level security tests:

```bash
npx --yes supabase@2.121.0 test db
```

## 8. Start the FastAPI backend

Open **Terminal 1** at the repository root. Activate `.venv` if it is not
already active, then run:

```bash
python -m backend
```

The backend listens on:

```text
http://127.0.0.1:8000
```

Check its public health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Expected output:

```json
{"status":"ok"}
```

You can also open the API documentation at:

```text
http://127.0.0.1:8000/docs
```

Keep this terminal running. The frontend needs FastAPI for authentication,
chat replies, Gemini extraction, session storage, and history.

## 9. Configure and start the frontend

Open **Terminal 2** and enter the frontend folder.

### macOS/Linux

```bash
cd frontend
npm ci
cp .env.example .env.local
```

### Windows PowerShell

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env.local
```

Edit `frontend/.env.local` so it points to the local services:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_USE_MOCK_API=false
VITE_SUPABASE_URL=http://127.0.0.1:54321
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_local_key
```

Start Vite:

```bash
npm run dev -- --host 127.0.0.1
```

Open the URL Vite prints, normally:

```text
http://127.0.0.1:5173/
```

If you change `.env.local`, restart Vite. Vite reads frontend environment
variables when it starts.

## 10. Use the website

### Create an account

1. Open `http://127.0.0.1:5173/`.
2. Select **Create an account**.
3. Enter a synthetic email, name, and password.
4. Select **Create account**.
5. The local Supabase stack returns a local access token.
6. The app loads the authenticated overview.

Local email confirmation is normally disabled for this disposable stack. If
the account does not sign in, check the browser console and the FastAPI
terminal.

### Start a Gemini chat

1. Select **Start a session**.
2. Enter a session name.
3. Select **Start reflecting**.
4. Type a thought in **Share what you’re thinking…**.
5. Press **Enter** or select **Add note**.
6. Wait for the Cognitrace/Gemini assistant reply.
7. Continue the conversation as needed.

Each chat turn sends the authenticated conversation to:

```text
POST http://127.0.0.1:8000/api/sessions/chat
```

FastAPI calls Gemini and returns the assistant message. Gemini is not called
from browser code.

### Complete and save a session

1. Add at least one user message.
2. Select **Complete session**.
3. FastAPI sends the transcript to Gemini extraction.
4. The structured reasoning is validated.
5. The session is saved to PostgreSQL under your user ID.
6. The app opens the reflection analysis screen.

## 11. Run the tests

From the repository root with `.venv` active:

```bash
python -m pytest
python -m ai.evaluation.evaluate
```

From `frontend/`:

```bash
npm test
npm run build
```

The Python unit tests mock Gemini and do not consume API quota. The live
browser flow uses your Gemini key and local Supabase services.

## 12. Stop the application

Stop FastAPI and Vite with `Ctrl+C` in their respective terminals.

Stop local Supabase:

```bash
npx --yes supabase@2.121.0 stop
```

Reset all disposable local Auth users and database rows:

```bash
npx --yes supabase@2.121.0 db reset --no-seed
```

The reset is destructive to local data only.

## 13. Common problems

### The page shows demo sessions instead of login

Check `frontend/.env.local`:

```dotenv
VITE_USE_MOCK_API=false
```

Restart Vite after changing it.

### “Could not reach the Cognitrace service”

Check that FastAPI is running and responds:

```bash
curl http://127.0.0.1:8000/health
```

Also verify that `VITE_API_BASE_URL` ends with `/api`.

### CORS or preflight errors

The backend must include the exact frontend origin:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Restart FastAPI after changing `.env`.

### “User authentication is not configured”

Check that the backend `.env` contains:

```dotenv
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
COGNITRACE_STORAGE_BACKEND=supabase
```

Restart FastAPI after changing `.env`.

### Gemini replies fail

Check that:

- `GEMINI_API_KEY` is set in the backend `.env`.
- `GEMINI_MODEL` names an available model.
- FastAPI was restarted after editing `.env`.
- The Gemini project has available quota.
- The backend terminal does not report a 401, 403, 404, or 429 provider error.

Never put the Gemini key in `frontend/.env.local`.

### Docker or Supabase does not start

Check Docker Desktop and run:

```bash
docker info
npx --yes supabase@2.121.0 status
```

Do not use `--linked` and do not run commands against a hosted project for
local testing.

## 14. Hosting the frontend and backend separately

The frontend and backend can be hosted on different providers. They connect
over HTTPS using the backend's public API URL:

```text
Browser → hosted frontend → HTTPS request → hosted FastAPI backend
                                             ├── hosted Supabase
                                             └── Gemini API
```

For example:

```text
Frontend: https://cognitrace.example.com
Backend:  https://api.cognitrace.example.com
API base: https://api.cognitrace.example.com/api
```

The frontend does not connect to the backend by folder path, localhost, or a
Docker network. It uses `VITE_API_BASE_URL`, which is compiled into the
frontend during its production build.

### Backend hosting configuration

On the backend host, configure these server-side environment variables:

```dotenv
GEMINI_API_KEY=your_private_gemini_key
GEMINI_MODEL=gemini-3.8-flash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
COGNITRACE_STORAGE_BACKEND=supabase
CORS_ALLOWED_ORIGINS=https://cognitrace.example.com
PORT=8000
```

Use the hosted Supabase project URL, not `http://127.0.0.1:54321`. Apply the
project migration to the intended hosted database before enabling Supabase
storage. The backend host must be able to reach Supabase and Gemini over the
network.

`GEMINI_API_KEY` must remain a backend secret. Never put it in the frontend
host's environment variables or in a `VITE_*` variable. The backend should
also use the provider's secret/server-side environment storage rather than
committing values to GitHub.

### Frontend hosting configuration

On the frontend host, configure only public browser variables:

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://api.cognitrace.example.com/api
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
```

Then build and publish the `frontend/dist` directory:

```bash
cd frontend
npm ci
npm run build
```

For Netlify, this repository already contains `netlify.toml`, which sets:

```text
Base directory: frontend
Build command: npm run build
Publish directory: dist
```

Set the same `VITE_*` variables in the Netlify site settings and trigger a new
deploy after changing them. Do not expect changing a local `.env.local` file
to update an already deployed frontend.

### CORS must match the deployed frontend exactly

If the frontend URL is `https://cognitrace.example.com`, the backend must use:

```dotenv
CORS_ALLOWED_ORIGINS=https://cognitrace.example.com
```

Do not add a trailing slash. If both a custom domain and the provider domain
are used, list both comma-separated:

```dotenv
CORS_ALLOWED_ORIGINS=https://cognitrace.example.com,https://your-site.netlify.app
```

After changing backend environment variables, restart or redeploy FastAPI.
After changing frontend environment variables, rebuild and redeploy the
frontend.

### Production connection checklist

1. Create or select one hosted Supabase project for Auth and PostgreSQL.
2. Apply the Cognitrace migration to that project and verify its RLS policies.
3. Deploy FastAPI with the hosted Supabase URL, Gemini key, and production
   CORS origin.
4. Open the deployed backend health URL:
   `https://api.cognitrace.example.com/health`.
5. Confirm it returns `{"status":"ok"}`.
6. Configure the frontend's `VITE_API_BASE_URL` to end in `/api`.
7. Configure the frontend with the same hosted Supabase URL and publishable
   key.
8. Build and deploy the frontend.
9. Create a test account from the deployed site.
10. Send a chat message and complete a session.
11. Confirm the session appears after refreshing and belongs only to that user.

### Common split-hosting mistakes

- `VITE_API_BASE_URL` still points to `http://127.0.0.1:8000/api`.
- The frontend was not rebuilt after changing a `VITE_*` variable.
- `CORS_ALLOWED_ORIGINS` contains the wrong domain or a trailing slash.
- FastAPI is using local Supabase values instead of hosted Supabase values.
- `COGNITRACE_STORAGE_BACKEND` is still `sqlite` on an ephemeral host.
- A Gemini key or Supabase secret key was accidentally exposed in frontend
  variables.

## 15. GitHub and second-device setup

Pushing the repository to GitHub transfers source code, migrations, tests,
dependency lockfiles, and setup templates. It does **not** transfer:

- `.env` or `frontend/.env.local`
- Gemini API keys
- Supabase secret/service-role keys
- local Auth accounts
- local PostgreSQL data
- Docker containers
- running FastAPI or Vite processes

On a second device:

1. Install Python 3.14, Node 22.12.0, npm, and Docker Desktop.
2. Clone the repository.
3. Create and activate `.venv`.
4. Install `requirements.txt`.
5. Run `npx --yes supabase@2.121.0 start`.
6. Create that device's `.env` and `frontend/.env.local`.
7. Add that device's own Gemini key.
8. Start FastAPI in one terminal.
9. Start Vite from `frontend/` in another terminal.
10. Create a new local account and use the website.

## 16. Important limitations

- The local Supabase stack is disposable unless you configure persistent
  storage.
- Draft chat messages are held in browser memory until the session is
  completed.
- Delete/retention, feedback persistence, recommendation generation, and
  pattern-history routes are not implemented in real mode.
- Retrieval currently uses keyword matching rather than embeddings or a vector
  database.
- Passing tests does not establish that the system improves human reasoning.

## 17. More documentation

- [Local setup](docs/LOCAL_SETUP.md)
- [Technical architecture](docs/TECHNICAL_ARCHITECTURE.md)
- [Security and environment](docs/SECURITY_AND_ENVIRONMENT.md)
- [Testing and evaluation](docs/TESTING_AND_EVALUATION.md)
- [Development roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [AI integration contract](docs/ai_integration.md)
- [PostgreSQL storage review](docs/postgres_storage_phase1.md)
