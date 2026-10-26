# Technical architecture

## System flow

```mermaid
flowchart LR
    Browser[React + Vite\nmock mode default]
    Auth[Supabase Auth\nuser JWT]
    API[FastAPI routes]
    Verify[JWT verification\nSupabase JWKS]
    Flow[Reasoning workflow]
    Gemini[Google Gen AI]
    SQLite[(SQLite\ndefault)]
    REST[Supabase Data API\noptional]
    PG[(PostgreSQL + RLS)]
    Browser -->|real-mode sign-in| Auth
    Browser -->|Bearer user JWT| API
    API --> Verify -->|verified subject| Flow
    Flow --> Gemini
    Flow --> SQLite
    Flow --> REST --> PG
    PG -->|auth.uid() RLS| REST
```

The PostgreSQL path is opt-in; the diagram does not imply that production or the frontend is integrated end to end.

## Frontend

- `frontend/src/main.tsx` mounts React; `frontend/src/App.tsx` controls screens/state; `frontend/src/styles.css` holds styling.
- `frontend/src/api/client.ts` selects demo or real behavior and initializes Supabase Auth. Mock mode is on unless `VITE_USE_MOCK_API` is exactly `false`. Demo records use browser local storage. Real-mode auth uses `persistSession: false`; user token and draft are held in memory.
- `frontend/src/api/backendAdapter.ts` maps the authenticated chat-turn, completed-transcript, history, and single-session routes. It sends a bearer user token with `credentials: omit`.
- Real-mode chat turns are sent to Gemini through FastAPI; completing a session submits the full transcript for evidence-grounded extraction and persistence. Drafts are lost on refresh. Pattern results from a new workflow are held in memory; there is no pattern-history route.
- `frontend/package.json` defines `dev`, `test`, and `build` scripts. `netlify.toml` configures the `frontend` base, `npm run build`, `dist`, and SPA fallback.

## Backend

- `backend/app/main.py` builds FastAPI, CORS, sanitized request validation, public `GET /health`, and the session router.
- `backend/__main__.py` starts Uvicorn on `0.0.0.0` using `PORT` (default 8000); run with `python -m backend`.
- `backend/app/routes/sessions.py` implements:
  - `POST /api/sessions`: body `{"session_text":"..."}`; calls the workflow and returns its JSON-ready result.
  - `GET /api/sessions?limit=20&offset=0`: authenticated, newest-first owner history; limit 1–100.
  - `GET /api/sessions/{session_id}`: authenticated owner read; another user's ID is indistinguishable from unknown (404).
- All session routes depend on `get_current_user`. `backend/app/schemas.py` defines request/response models; extra request fields and blank text are rejected.
- `backend/app/config.py` reads environment settings. CORS uses explicit origins, allows GET/POST and Authorization headers, and disables cookies.

## Authentication and ownership

`backend/app/security.py` verifies Supabase Auth JWTs with PyJWT and the project's JWKS at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. It accepts ES256/RS256 signatures and checks issuer, audience `authenticated`, required claims, role, expiry, and non-empty subject. Missing/invalid tokens receive sanitized 401 responses. Missing Supabase URL or unavailable JWKS receives a sanitized 503. JWKS clients are cached; importing the application does not fetch a key.

`AuthenticatedUser` carries the verified `sub` and bearer token; its repr redacts the token. `backend/app/session_storage.py` creates a per-request owner-bound adapter. SQLite receives the verified subject as owner ID. The optional Supabase adapter receives that subject, the same verified token, and a publishable project key.

SQLite queries apply owner filters when invoked by the backend. Supabase requests also filter by owner ID, while PostgreSQL RLS independently checks `auth.uid()`. Direct library calls that omit `owner_id` are not a user-isolation boundary.

## AI extraction and workflow

`ai/workflow.py::process_reasoning_session` validates input, calls `extract_reasoning` once, persists the validated result, retrieves relevant prior sessions, and detects patterns within that history. The new session is excluded from retrieval/pattern evidence. `ReasoningWorkflowError` identifies a stage and whether saving occurred without exposing session text or provider bodies.

`ai/extraction/reasoning_extractor.py` asks Gemini for JSON, removes supported JSON fences, parses it, validates with Pydantic, and requires each evidence quote to occur exactly in the source session. Extraction failure occurs before persistence.

`ai/schemas/reasoning.py` defines a nullable problem and lists for decisions, justifications, alternatives, and assumptions. Extra fields are forbidden; each item contains text and evidence.

`ai/retrieval/keyword_search.py` case-folds/tokenizes text, ignores punctuation, whitespace, and common stop words, weights structured reasoning fields more than source text, and sorts by relevance/time/session ID. It is keyword matching, not semantic search.

`ai/patterns/reasoning_patterns.py` compares statements within the same category, requiring at least two shared meaningful terms, Jaccard >= 0.5, complete-link grouping, and support from two distinct sessions. It returns supporting IDs, exact quotes, possible counterexamples, and neutral questions. Similar text is not proof of behavior.

## Storage

### SQLite (default)

`ai/storage/session_store.py` uses built-in `sqlite3`. The default file is `data/cognitrace.db`; `COGNITRACE_DB_PATH` overrides it. Records include session ID, UTC timestamp, original text, reasoning JSON, and optional owner ID. `COGNITRACE_STORAGE_BACKEND` defaults to `sqlite`. A hosted container needs a mounted persistent disk and a path on that disk; ordinary SQLite files should not be shared across service instances.

### Optional Supabase Data API / PostgreSQL

`ai/storage/session_repository.py::SupabaseSessionStore` uses Python's standard-library HTTP client for PostgREST. The project publishable key is sent as `apikey`; the request's verified user JWT is forwarded as Bearer auth. The adapter rejects service/secret keys. Set `COGNITRACE_STORAGE_BACKEND=supabase` to opt in; SQLite remains default.

`supabase/migrations/202610240001_reasoning_sessions.sql` defines `public.reasoning_sessions` with session ID, timestamp, source text, JSONB reasoning, and `owner_id` referencing `auth.users`. It enables RLS, revokes broad table access, grants authenticated only SELECT/INSERT, and creates owner-only SELECT/INSERT policies (`owner_id = auth.uid()`). No update/delete grants or policies exist.

`supabase/tests/reasoning_sessions_rls.sql` uses two synthetic users/rows in a transaction and rolls them back. Its nine assertions cover owner read/insert, cross-user read/insert denial, update/delete denial for own and other rows, and anonymous denial. The developer reports 9/9 passing locally; not independently rerun during this handover. This is not a hosted migration or a full FastAPI integration test.

## Dependencies and status

Python dependencies are in `requirements.txt`: Google Gen AI SDK, Pydantic, `python-dotenv`, FastAPI, Uvicorn, PyJWT crypto support, and pytest. Supabase REST uses the standard library. Frontend dependencies are isolated in `frontend/package.json` (React, Vite, TypeScript, Vitest, Supabase JS).

**Implemented locally:** components and routes described above. **Partially verified:** offline Python tests and developer-reported local pgTAP. **Not implemented:** delete/retention, feedback, recommendation, and pattern-history routes; embeddings/RAG/vector DB.
