# Testing and evaluation

## Python test layout

The pytest suite is under `tests/`:

- `test_gemini_client.py`: client/config behavior with mocked SDK calls.
- `test_reasoning_extractor.py`: JSON/schema/evidence validation with mocked Gemini.
- `test_session_store.py`: isolated temporary SQLite storage and ownership.
- `test_keyword_search.py`: local keyword matching and ranking.
- `test_reasoning_patterns.py`: deterministic tentative patterns using synthetic sessions.
- `test_workflow.py`: orchestration with mocks and temporary storage.
- `test_backend.py`: request validation, JWT behavior, API ownership/config, and sanitized errors.
- `test_supabase_session_store.py`: Data API request formation, owner forwarding, JSON round-trip, pagination, and safe storage errors using fake transports.
- `test_evaluation.py`: dataset/schema/evaluator/metric behavior.

From repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/test_backend.py tests/test_supabase_session_store.py
```

The checks are offline. Gemini SDK calls are mocked; the Supabase adapter uses a fake transport in unit tests. Auth tests use local generated JWT/key material or mock the JWKS lookup; no live user or hosted key endpoint is required.

## PostgreSQL / RLS suite

`supabase/tests/reasoning_sessions_rls.sql` is pgTAP coverage for the migration. It uses two synthetic auth users and synthetic rows in a SQL transaction and rolls them back. Its nine assertions check owner read and insert, cross-user read/insert denial, authenticated update/delete denial on own and other-user rows, and anonymous denial. The migration itself revokes broad table access, grants authenticated SELECT/INSERT only, and uses RLS owner policies.

The developer reports `npx --yes supabase@2.121.0 test db` passed all 9 assertions against the local stack before this handover. I did not rerun that database test in this task. pgTAP exercises PostgreSQL grants/RLS, not browser auth or actual FastAPI token forwarding. A local end-to-end test with a real local Supabase Auth user and request token remains outstanding.

## Offline reasoning evaluation

`ai/evaluation/dataset.json` contains 16 hand-written sessions and expected Pydantic outputs. It covers programming, debugging, planning, everyday cases, absent categories, ambiguity, and changing decisions. `ai/evaluation/saved_predictions.json` contains deterministic saved fixture outputs. Run:

```powershell
.\.venv\Scripts\python.exe -m ai.evaluation.evaluate
```

The default is saved-fixture mode and makes no Gemini calls. Optional live mode is an explicit quota-consuming operation:

```powershell
.\.venv\Scripts\python.exe -m ai.evaluation.evaluate --mode gemini
```

It makes one real request per example (16 with the current dataset). Do not use without explicit approval and available quota.

Metrics are micro-averaged per category: precision is matched predictions divided by all predictions; recall is matched expected items divided by all expected items; F1 is their harmonic mean. Matching happens within each session and requires both text and evidence to match after case/whitespace normalization; other wording/evidence differences remain misses. Unsupported predicted items count as false positives. If a category has no expected or predicted items, its score is N/A. These scores test the fixtures and scorer, not actual Gemini quality, semantic paraphrase understanding, or human outcomes.

## Evidence categories to keep separate

- **Unit tests:** code behavior under mocks/temp SQLite.
- **Local pgTAP:** database grants and RLS against local PostgreSQL; historical developer-reported result is 9/9.
- **Offline evaluation:** 16 saved fixtures; not live model scores.
- **Live Gemini quality:** not established by saved fixtures; live calls vary and use quota.
- **Full integration:** real Supabase-issued JWT through browser, FastAPI, Data API, and RLS remains to be verified.


