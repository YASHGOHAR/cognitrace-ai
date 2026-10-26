# Cognitrace AI — project handover

## Start here

Cognitrace is a reflection tool for reviewing how a person worked through a problem. It records a session, extracts evidence-linked reasoning, and can show tentative similarities across earlier sessions. It supports reflection; it is not a diagnostic or personality-assessment system.

Read this overview first, then [technical architecture](TECHNICAL_ARCHITECTURE.md), [local setup](LOCAL_SETUP.md), [security and environment](SECURITY_AND_ENVIRONMENT.md), [testing and evaluation](TESTING_AND_EVALUATION.md), [development roadmap](DEVELOPMENT_ROADMAP.md), and [research handover](RESEARCH_HANDOVER.md).

## Current repository state

The checkout is on `main`, tracking `origin/main` at local ref `15b2ba0` (`Add secured FastAPI backend and deployment configuration`). It contains uncommitted modifications and untracked files, including a frontend under `frontend/`, an optional Supabase adapter/migration, and related tests. Git showed no staged files during inspection. Those local changes are not part of the tracked commit; a fresh clone may not include them. Recheck `git status` before sharing or editing.

## Implemented locally

- Gemini text generation and Pydantic-validated extraction of problem, decisions, justifications, alternatives, and assumptions with exact evidence quotes.
- SQLite storage of original text, timestamp, structured JSON, and optional owner ID.
- Deterministic keyword retrieval and tentative cross-session reasoning similarity with evidence, session IDs, counterexamples, and reflection questions.
- A workflow that extracts once, saves, retrieves prior sessions, and detects patterns without including the new session as history.
- FastAPI health, create-session, list-history, and get-session routes. Session routes verify Supabase Auth bearer JWTs and scope data to the verified subject.
- Optional request-scoped Supabase Data API storage; SQL migration and pgTAP RLS tests are present locally.
- Offline evaluation fixtures, Python tests, and a React/TypeScript/Vite frontend.

## Partial or unverified

- SQLite is the default. Supabase storage is opt-in; the full browser → FastAPI → Supabase Auth → Data API/RLS path is not verified end to end.
- The frontend defaults to mock mode. Real mode sends chat turns through the authenticated backend to Gemini; completing a session submits the transcript for persistence and reflection extraction. Drafts are in memory and lost on refresh.
- Delete/retention, feedback, recommendation, and pattern-history API routes are absent. Real-mode UI does not claim those features are connected.
- The developer reports 9 local pgTAP assertions passing. This documentation task does not independently rerun that database suite. Offline saved predictions are fixtures, not Gemini responses or a measure of live model quality.
- No user study or empirical evidence of improved human reasoning was found in the repository.

## Design decisions

Keep extraction, persistence, retrieval, and pattern detection modular. Require exact source evidence; leave absent categories empty and unstated problems null. Pattern results are possibilities backed by at least two distinct sessions, not fixed behavioral claims. SQLite remains default; PostgreSQL uses the verified user token and RLS. Keep `VITE_USE_MOCK_API=true` until the real path is verified. Never put server credentials in Vite variables.

## First-day checklist

1. Clone/open the repository and run `git status --short --branch`; coordinate access to local uncommitted work.
2. Follow [local setup](LOCAL_SETUP.md); create your own `.env` from placeholders. Do not request or copy another developer's private `.env`.
3. Run Python tests and saved-fixture evaluation; run frontend tests/build.
4. Read [technical architecture](TECHNICAL_ARCHITECTURE.md), then inspect `backend/app/routes/sessions.py` and `ai/workflow.py`.
5. Keep mock mode enabled and use only synthetic data until security and persistence decisions are agreed.
6. Choose a P0 task from the [roadmap](DEVELOPMENT_ROADMAP.md) and agree on acceptance criteria before changing code.

## Sharing safely

Share repository access, not a workspace folder containing `.env`, local databases, or Supabase CLI temp state. Ignore rules cover `.env*` except `.env.example`, `data/`, database files, Python environments/caches, frontend `node_modules`/`dist`, and Supabase `.temp`/`.branches`. Inspect the staged list and staged diff before any commit.
