# Cognitrace AI foundation

A small Python module for calling Gemini, extracting structured reasoning, storing sessions locally, retrieving them by keyword, and surfacing tentative cross-session textual patterns.

## Requirements

- Windows 10/11
- Python 3.11 or newer (Python 3.12 is a sensible choice)
- A Gemini API key only when you want to make a real request. Tests use mocks and need no key.

The project uses Google's supported `google-genai` Python SDK. The default model is set in one place and can be changed with `GEMINI_MODEL`; Google's current model list is at [Gemini API models](https://ai.google.dev/gemini-api/docs/models). Gemini API access and free-tier availability depend on Google's current account, region, and quota policies; no paid subscription is assumed.

## Windows setup (PowerShell)

Open PowerShell in the project root and create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation for this terminal, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure the API key safely

1. Copy the example file locally:

   ```powershell
   Copy-Item .env.example .env
   ```
2. Edit `.env` and replace the placeholder with your key from Google AI Studio. Keep `.env` private; Git ignores it. Never paste a real key into source code, README, chat, or a commit.
3. Optionally change `GEMINI_MODEL` in `.env`. The default is `gemini-3.8-flash`; setting the environment variable lets you move models without changing code.

A request is made only when `generate_text(...)` or `extract_reasoning(...)` is called. Importing the module does not create a client or contact Google.

## Reasoning extraction

`extract_reasoning(session_text)` asks Gemini for JSON, validates it against Pydantic schemas, and checks that every evidence quote appears exactly in the source session. The result includes a problem (or `None`), decisions, justifications, alternatives considered, and assumptions. Unstated categories are empty lists; the function does not guess. Invalid model output and provider errors raise `ReasoningExtractionError`.

```python
from ai.extraction.reasoning_extractor import extract_reasoning

result = extract_reasoning(
    "I need to find the shortest path in an unweighted graph. "
    "I considered Dijkstra, but I chose BFS because every edge has equal cost. "
    "I will use a queue to explore nodes level by level."
)

print(result.model_dump())
```

## Local session storage

The extraction and storage steps are separate. After `extract_reasoning(...)` returns a validated result, pass the source text and result to `save_session(...)`. The default SQLite file is `data/cognitrace.db`, which is ignored by Git because it contains user session text. Storage functions accept `db_path=...` so tests or callers can select another database. Saving does not call Gemini.

```python
from ai.extraction.reasoning_extractor import extract_reasoning
from ai.storage.session_store import get_session, list_sessions, save_session

session_text = "I chose BFS because every edge has equal cost."
reasoning = extract_reasoning(session_text)
saved = save_session(session_text, reasoning)
reloaded = get_session(saved.session_id)
recent = list_sessions(limit=10)
```

Call `initialize_database()` to explicitly create the local data directory and table; save and read functions also initialize it when needed. An unknown ID returns `None`.

## Keyword search of past sessions

`search_sessions(query, limit=10)` searches stored source text and extracted reasoning fields without a model or network call. It ignores case, punctuation, repeated whitespace, and a small set of common English stop words. Complete token matches score one point in original session text and two points in each extracted reasoning category, counting a term at most once per field. Results sort by score, then newest timestamp, then session ID. Empty and stop-word-only queries return an empty list; matches are exact-token keyword matches, so this feature does not understand synonyms or semantic similarity.

```python
from ai.retrieval.keyword_search import search_sessions

matches = search_sessions("graph shortest path", limit=5)
for match in matches:
    print(match.session_id, match.relevance_score, match.session_text)
```

## Tentative reasoning-pattern observations

`detect_reasoning_patterns()` compares saved decisions, justifications, alternatives, and assumptions. It returns only clusters supported by at least two distinct sessions, with the exact evidence quotes, session IDs, a neutral reflection question, and related counterexamples when found. Pass an optional keyword query to use `search_sessions(...)` to scope which past sessions are compared:

```python
from ai.patterns.reasoning_patterns import detect_reasoning_patterns

analysis = detect_reasoning_patterns("graph queue")
if analysis.insufficient_evidence:
    print("There is not enough matching evidence to report a pattern yet.")
for pattern in analysis.patterns:
    print(pattern.description, pattern.supporting_session_ids)
    print(pattern.reflection_question)
```

This is deliberately simple textual matching: after removing common stop words, two reasoning statements in the same category must share at least two terms and have Jaccard similarity of at least 0.5. Each cluster uses complete-link matching (every pair must meet the threshold), and each session contributes at most one statement to a cluster. The result is a tentative observation about similar recorded statements, not proof of a behavioral pattern or a fixed personal characteristic. It can miss paraphrases and may group statements that share wording without sharing intent; review the supplied quotes and counterexamples before drawing conclusions. No LLM or network call is made.

## Unified reasoning workflow

`process_reasoning_session(session_text, db_path=...)` coordinates one new session: it validates the input, extracts reasoning once, saves the validated result, searches relevant prior sessions, and analyzes patterns within the same retrieved history. The new session is excluded from historical matches and pattern evidence. If extraction fails, nothing is saved. If a later local step fails, `ReasoningWorkflowError` identifies the stage and tells you whether the session was saved, without echoing the source session or provider response.

```python
from ai.workflow import process_reasoning_session

result = process_reasoning_session(
    "I chose BFS because every edge has equal cost.",
    retrieval_limit=10,
)
print(result.session_id)
print(result.reasoning.model_dump())
print(result.insufficient_evidence)
for pattern in result.detected_patterns:
    print(pattern.description, pattern.supporting_session_ids)
    print(pattern.reflection_question)
```

Pass `db_path` to use a non-default local SQLite file, for example in tests. The extraction step may make one Gemini request; storage, search, and pattern analysis remain local.

The backend-facing function signature, JSON serialization, setup, and error contract are documented in [docs/ai_integration.md](docs/ai_integration.md).

## HTTP backend and deployment

The FastAPI backend wraps the existing workflow and SQLite store. Session endpoints require a bearer token; health remains public. Configure these variables in local `.env` or in the deployment provider's secret/environment settings:

| Variable | Required value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini key, stored as a secret. Needed for `POST /api/sessions`. |
| `GEMINI_MODEL` | Optional; defaults to the model in `ai/core/config.py`. |
| `COGNITRACE_API_TOKEN` | A random secret of at least 32 characters. Required to access session routes; short values and the example placeholder are rejected. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact browser origins (no trailing slash). Example: `https://stalwart-chebakia-c6da35.netlify.app,http://localhost:5173`. |
| `COGNITRACE_DB_PATH` | Path to the SQLite file. Locally, `data/cognitrace.db` is fine. In production, set it inside a mounted persistent volume. |
| `PORT` | Set by most hosting providers. The app defaults to `8000` for local use. |

For local setup, create `.env` from `.env.example` only if one does not already exist, then replace all secret placeholders with private values. Do not commit `.env`. The configured CORS list includes the current frontend origin `https://stalwart-chebakia-c6da35.netlify.app`; override it for preview or other deployments.

Run locally in PowerShell with reload enabled:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload
```

For a production host, use this start command:

```text
python -m backend
```

It binds to `0.0.0.0` and reads the port from `PORT` (defaulting to `8000` locally). It does not enable auto-reload.

### Authentication and session privacy

Send `Authorization: Bearer <COGNITRACE_API_TOKEN>` to `POST /api/sessions`, `GET /api/sessions/{session_id}`, and `GET /api/sessions`. Without a configured server token, these endpoints fail closed with `503`; missing or incorrect credentials receive `401`. `GET /health` does not return session data and remains unauthenticated.

This is a minimal shared service token, not user login or per-user authorization: every authorized caller can access the same SQLite session history. **Do not place this token in a public Netlify/browser JavaScript bundle.** Before allowing browser users to access private sessions, put a trusted server-side component in front of this API or add real user authentication and per-user data ownership. CORS is not authentication.

### Persistent SQLite storage

Hosted container filesystems are often temporary and may be replaced during restarts or deployments. Attach a persistent disk/volume in the hosting provider and set `COGNITRACE_DB_PATH` to a file inside that volume, for example `/mnt/cognitrace-data/cognitrace.db` only when that exact mount point is configured. Do not assume the repository's `data/` directory persists. Keep backups of the volume. SQLite is suitable for a small, single-instance deployment; do not run multiple API instances against an ordinary local SQLite file. Move to a managed database before scaling horizontally.

The endpoints are `GET /health`, `POST /api/sessions`, `GET /api/sessions/{session_id}`, and paginated `GET /api/sessions?limit=20&offset=0` (maximum `limit` is 100). Example local PowerShell calls (after setting `$env:COGNITRACE_API_TOKEN` to the same private value used by the backend):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health

$headers = @{ Authorization = "Bearer $env:COGNITRACE_API_TOKEN" }
$body = @{ session_text = "I chose BFS because all edges have equal cost." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/sessions `
  -Headers $headers -ContentType "application/json" -Body $body

Invoke-RestMethod "http://127.0.0.1:8000/api/sessions?limit=10&offset=0" -Headers $headers
```

Validation and internal errors are sanitized so rejected session text, credentials, provider errors, and stack traces are not returned. Extraction failures are not saved; failures after saving include the saved session ID. No frontend-to-backend integration has been tested.

For the backend-facing function signature, JSON serialization, setup, and error contract, see [docs/ai_integration.md](docs/ai_integration.md).

Example shape (the actual wording is generated from the supplied session):

```json
{
  "problem": {
    "text": "Find the shortest path in an unweighted graph.",
    "evidence": "find the shortest path in an unweighted graph"
  },
  "decisions": [
    {"text": "Use BFS.", "evidence": "I chose BFS"}
  ],
  "justifications": [
    {"text": "Every edge has equal cost.", "evidence": "every edge has equal cost"}
  ],
  "alternatives_considered": [
    {"text": "Dijkstra.", "evidence": "I considered Dijkstra"}
  ],
  "assumptions": []
}
```

## Run tests

```powershell
python -m pytest
```

Tests replace the SDK client with mocks, so they do not make network requests and do not need `GEMINI_API_KEY`.

## Reasoning extraction evaluation

The hand-written dataset in `ai/evaluation/dataset.json` contains 16 sessions from programming, debugging, planning, and everyday problem-solving. Each expected result uses the same Pydantic schema as the extractor. It includes incomplete, ambiguous, and changed-mind examples. Gold evidence quotes are checked against their source session when the dataset loads.

Run the offline evaluation without a Gemini key:

```powershell
.\.venv\Scripts\python.exe -m ai.evaluation.evaluate
```

This uses saved, deterministic fixture predictions in `ai/evaluation/saved_predictions.json`. They are **not** actual Gemini responses: this mode checks the dataset, scoring logic, and report without network access. The fixtures include a few deliberate misses and unsupported outputs so the metrics are not simply a perfect-score example.

To evaluate the configured Gemini model, set `GEMINI_API_KEY` in your local `.env` and run:

```powershell
.\.venv\Scripts\python.exe -m ai.evaluation.evaluate --mode gemini
```

This sends one real request per session (currently 16 requests) and may use quota. It reports failed extractions as prediction errors and as missed expected items, then prints a sanitized error summary for each failed session. The summary can include the SDK error type, HTTP status, and provider message; credentials are redacted.

Metrics are micro-averaged per category across the examples. An item counts as correct only when both its text and evidence match after case and whitespace normalization. Wording, punctuation, and evidence are otherwise kept strict; unsupported or invented items count as false positives. Precision is the share of predicted items that match, recall is the share of expected items found, and F1 balances the two. `N/A` means that category had no expected or predicted items. These exact-match metrics do not judge semantic paraphrases or replace human review. The offline fixture scores do not measure model quality; live scores can vary between runs.

## Existing text-generation example

```python
from ai.llm.gemini_client import generate_text

answer = generate_text("Explain a decision tree in two sentences.")
print(answer)
```

`generate_text` validates the prompt and key, uses the configured model, and returns Gemini's response text. Provider errors become a short `GeminiClientError` without exposing the original exception text or credentials.

## Publish to GitHub

This workspace was created locally. The connected GitHub tools in this environment do not provide repository creation, so no GitHub repository has been made. After creating an empty repository on GitHub (suggested name: `cognitrace-ai`), publish from this folder with:

```powershell
git init
git add .
git commit -m "Create Cognitrace AI foundation"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/cognitrace-ai.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username. Choose public or private on GitHub when creating the repository. Do not use `git add .env` or commit the key.
