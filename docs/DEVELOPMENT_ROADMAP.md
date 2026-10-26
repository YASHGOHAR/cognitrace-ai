# Development roadmap

Status describes this checkout as inspected for handover; it does not mean a task is approved or deployed. Priority: P0 blocks safe real-user/public use, P1 needed for coherent integration, P2 important quality/maintenance, P3 future scope.

## 1. Critical security and correctness

### P0 — Verify real local auth-to-storage path
- **Why:** Current tests separately verify JWT logic, adapter behavior, and PostgreSQL RLS; none proves the complete request path.
- **Files:** `backend/app/security.py`, `backend/app/session_storage.py`, `backend/app/routes/sessions.py`, `ai/storage/session_repository.py`, `supabase/migrations/202610240001_reasoning_sessions.sql`.
- **Depends on:** Disposable local Supabase stack and local Auth user; no hosted link.
- **Status:** Unit/mocked coverage exists; pgTAP 9/9 reported by developer; end-to-end pending.
- **Acceptance:** Create/read a session with a local Supabase user JWT; cross-user and anonymous requests are denied by API and RLS; no service key is used; errors/logs reveal no token or source text.

### P0 — Choose production persistence and verify durability
- **Why:** SQLite is default and a container filesystem may be ephemeral; Supabase adapter remains opt-in.
- **Files:** `backend/app/config.py`, `backend/app/session_storage.py`, `ai/storage/session_repository.py`, `ai/storage/session_store.py`, deployment docs.
- **Depends on:** Persistent Render disk decision or separately approved PostgreSQL production configuration/migration.
- **Status:** SQLite default preserved; hosted persistence configuration not verified in this checkout.
- **Acceptance:** Documented backend setting and persistence path are tested across restart; no data migration occurs without backup/rollback approval.

### P0 — Define deletion, retention, and account lifecycle
- **Why:** The API stores user session text but has no delete or retention route.
- **Files:** `backend/app/routes/sessions.py`, storage adapters, migration/RLS tests, frontend settings.
- **Depends on:** Product/privacy decision and permission design.
- **Status:** Not implemented.
- **Acceptance:** Owner-only deletion/retention policy is specified and tested; cascade/account deletion behavior is clear before real sensitive use.

## 2. Local end-to-end verification

### P1 — Automate disposable local-stack integration
- **Why:** Reduce manual confidence gaps between mocks and PostgREST behavior.
- **Files:** `supabase/tests/reasoning_sessions_rls.sql`, `tests/test_supabase_session_store.py`, CI workflow (not present/verified).
- **Depends on:** Docker and pinned Supabase CLI.
- **Status:** pgTAP local pass reported; Python adapter transport remains mocked.
- **Acceptance:** Reproducible local-only command verifies migration, JWT forwarding, create/list/get, pagination, RLS, and safe errors; never links hosted Supabase.

### P1 — Confirm JWT signing-key policy and rotation behavior
- **Why:** Backend currently accepts ES256 and RS256 and obtains signing keys from JWKS; tests mock key lookup.
- **Files:** `backend/app/security.py`, `tests/test_backend.py`.
- **Depends on:** Confirm project signing algorithms and Supabase key-rotation expectations.
- **Status:** Local ES256 validation covered; live/JWKS integration and rotation unverified.
- **Acceptance:** Explicit algorithm policy matches project; rotation/unknown-kid/network failure are tested locally or with controlled fixtures.

## 3. Frontend-backend integration

### P1 — Keep mock mode until approved real-mode verification
- **Why:** The current example is intentionally demo-first and browser output must not be mistaken for real AI.
- **Files:** `frontend/src/api/client.ts`, `frontend/src/api/backendAdapter.ts`, `frontend/.env.example`, `backend/app/main.py`.
- **Depends on:** Local auth-to-storage verification, environment configuration, CORS review.
- **Status:** Adapter for Gemini chat turns, completed transcript/history/get exists; mock remains default.
- **Acceptance:** Test account can sign in, submit one synthetic transcript, view own history, and cannot view another user; all routes and CORS are confirmed. Only then consider changing a deployment variable.

### P1 — Make current product limits explicit in UI
- **Why:** Delete, feedback, recommendation, and pattern-history routes remain unsupported in real mode.
- **Files:** `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/api/backendAdapter.ts`.
- **Depends on:** Product scope decision.
- **Status:** Demo flows exist; real mode sends chat turns through Gemini and hides/labels unsupported operations.
- **Acceptance:** No real-mode feature implies a backend capability that is absent; error and empty states are user-understandable.

## 4. Persistence and retrieval

### P1 — Decide one production storage target
- **Why:** Two adapters add configuration and migration complexity; SQLite durability depends on host volume.
- **Files:** `ai/storage/session_store.py`, `ai/storage/session_repository.py`, `backend/app/session_storage.py`, `.env.example`.
- **Depends on:** Deployment plan and a tested rollback.
- **Status:** SQLite remains default; Supabase is optional and local migration is present.
- **Acceptance:** Target, backup, migration, rollback, and RLS verification are documented and exercised before switching.

### P2 — Review keyword retrieval and pattern thresholds with users
- **Why:** Exact token overlap and Jaccard similarity miss paraphrases and may group wording rather than intent.
- **Files:** `ai/retrieval/keyword_search.py`, `ai/patterns/reasoning_patterns.py`, evaluation fixtures.
- **Depends on:** Consent-based representative evaluation data.
- **Status:** Deterministic heuristic only.
- **Acceptance:** Error analysis documents false matches/misses; output remains tentative and quote-backed.

## 5. Testing and evaluation

### P1 — Add full request integration tests
- **Why:** Current API tests call route functions or mock dependencies; browser-to-backend contract still needs verification.
- **Files:** `tests/test_backend.py`, `frontend/src/api/backendAdapter.test.ts`, possible local integration harness.
- **Depends on:** Local Auth/Data API fixture.
- **Status:** Offline tests exist; full end-to-end test missing.
- **Acceptance:** Input validation, authorization, owner separation, JSON response, CORS, and persistence tested without hosted services.

### P2 — Expand evaluation evidence
- **Why:** Sixteen authored examples and saved predictions are a small hand-built regression set.
- **Files:** `ai/evaluation/dataset.json`, `ai/evaluation/saved_predictions.json`, `ai/evaluation/evaluate.py`.
- **Depends on:** Human-reviewed, consented and de-identified examples.
- **Status:** Offline fixtures run; not live model-quality evidence.
- **Acceptance:** Dataset is versioned with provenance/annotation guidance; agreement and error categories are reported; no claim about user outcomes without a study.

## 6. Documentation and maintainability

### P2 — Reconcile local handover work with GitHub main
- **Why:** This checkout has substantial uncommitted/untracked work absent from the tracked commit.
- **Files:** `README.md`, `docs/`, `frontend/`, `supabase/`, backend/AI files.
- **Depends on:** Review staged file list and security scan with repository owner.
- **Status:** Handover docs are prepared in this local worktree; no commit/push authorized.
- **Acceptance:** Reviewer approves exact files and tests before any commit or push.

### P2 — Establish a simple CI workflow
- **Why:** The repository needs repeatable Python/frontend checks on reviewed changes.
- **Files:** CI configuration to be proposed.
- **Depends on:** Team agreement and secret-free offline jobs.
- **Status:** No verified CI workflow found.
- **Acceptance:** CI runs pytest, offline evaluation, frontend test/build, and local SQL/RLS tests without Gemini secrets or hosted credentials.

## 7. Future features

### P3 — Consider semantic retrieval or incremental chat
- **Why:** These could broaden recall or support conversational interaction but add cost, complexity, and privacy surface.
- **Files:** Not selected.
- **Depends on:** Product evidence, architecture review, budget, and privacy review.
- **Status:** Proposed only; no embeddings, RAG, vector store, or incremental chat is implemented.
- **Acceptance:** A separate design and approval precedes implementation.
