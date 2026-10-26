# Cognitrace AI

Cognitrace is a reflection system for reviewing how people solve problems over time. It extracts evidence-linked reasoning from a completed session, stores it, retrieves relevant history, and can surface tentative text-based patterns. It is not a diagnostic tool, and current test fixtures do not establish improved human reasoning.

## Current development status

The Python AI module and FastAPI session API are implemented. SQLite remains the default store. Optional Supabase Data API/PostgreSQL storage, an RLS migration, and a React + Vite frontend exist in this local working tree. The frontend defaults to mock/demo mode. The complete browser-to-Supabase-authenticated-storage path is not yet verified end to end.

**Workspace note:** At handover, the local `main` checkout had many modified and untracked files not included in its tracked `origin/main` commit. A fresh GitHub clone may not include the frontend, optional Supabase adapter/migration, and latest local tests/docs. Review `git status --short --branch` before relying on this code.

## Architecture at a glance

```text
React/Vite (mock by default) → FastAPI bearer-auth session routes → AI workflow
                                                 ├─ Gemini extraction
                                                 ├─ SQLite (default)
                                                 └─ Supabase Data API + PostgreSQL RLS (opt-in)
```

The workflow validates an extraction, saves source text and structured JSON, retrieves prior sessions by keywords, and finds tentative cross-session textual similarities with exact evidence. Details: [technical architecture](docs/TECHNICAL_ARCHITECTURE.md).

## Get started

The repository pins Python dependencies in `requirements.txt`, frontend dependencies in
`frontend/package-lock.json`, Node in `.nvmrc`/`.node-version`, and Python in
`.python-version`. A second device still needs its own environment files and running
services; credentials and local databases are intentionally not committed.

Windows PowerShell, from the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m backend
```

Session routes require a valid Supabase Auth user JWT. `GEMINI_API_KEY` is needed only for a real extraction request. Keep secrets in local backend environment, never Vite `VITE_*` variables. Full setup and frontend instructions are in [local setup](docs/LOCAL_SETUP.md).

## Verify locally

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ai.evaluation.evaluate
Set-Location frontend
npm ci
npm test
npm run build
```

Python tests mock model calls. Offline evaluation uses saved fixtures, not live Gemini outputs or model-quality measurements. The developer reports the isolated local pgTAP RLS suite passed 9 assertions; this is separate from end-to-end frontend/auth/API verification. See [testing and evaluation](docs/TESTING_AND_EVALUATION.md).

## Handover documents

- [Project overview and onboarding](docs/PROJECT_HANDOVER.md)
- [Technical architecture](docs/TECHNICAL_ARCHITECTURE.md)
- [Local setup](docs/LOCAL_SETUP.md)
- [Security and environment](docs/SECURITY_AND_ENVIRONMENT.md)
- [Testing and evaluation](docs/TESTING_AND_EVALUATION.md)
- [Development roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Research handover](docs/RESEARCH_HANDOVER.md)
- [AI integration contract](docs/ai_integration.md)
- [PostgreSQL storage phase review](docs/postgres_storage_phase1.md)

## Important limits

- Leave `VITE_USE_MOCK_API=true` until real auth, per-user ownership, CORS, and persistence have been verified together.
- Real-mode frontend sends each chat turn to Gemini through the authenticated FastAPI `/api/sessions/chat` route; completing a session saves the transcript and generates the evidence-grounded reflection.
- Delete/retention, feedback, recommendation, and pattern-history routes are not implemented.
- Hosted SQLite needs a persistent mounted disk and is not suitable as a shared multi-instance file store.
- No live-model or human-outcome claim follows from passing unit tests or fixture scores.
