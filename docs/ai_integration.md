# Cognitrace AI integration contract

The AI workflow is a Python function called by the FastAPI backend. It is not itself an HTTP endpoint.

## Current public workflow

```python
process_reasoning_session(
    session_text: str,
    *,
    db_path: str | pathlib.Path | None = None,
    settings: ai.core.config.Settings | None = None,
    retrieval_limit: int = 10,
    owner_id: str | None = None,
    store=None,
) -> ai.workflow.ReasoningWorkflowResult
```

- `session_text`: non-empty source transcript.
- `db_path`: SQLite path; defaults to `<repo>/data/cognitrace.db`.
- `settings`: optional Gemini settings. Otherwise the extractor reads backend environment and `.env`.
- `retrieval_limit`: positive integer; defaults to 10.
- `owner_id`: optional for direct library callers. The backend must pass only the verified JWT subject so SQLite save and retrieval are owner-scoped.
- `store`: optional adapter implementing the session-store interface. The backend creates this per request; for Supabase mode it forwards the verified user's token and owner. Do not accept caller-supplied owner IDs or adapters from HTTP input.

The workflow calls extraction once, persists the validated result, searches historical sessions, then detects patterns only within retrieved history. It excludes the newly saved session from history and pattern evidence. Extraction failure happens before saving; later failures can happen after saving.

## Result and serialization

`ReasoningWorkflowResult` contains `session_id`, Pydantic `reasoning`, `relevant_previous_sessions`, `detected_patterns`, `insufficient_evidence`, and `previous_sessions_considered`. Use `result.to_dict()` for JSON-ready primitives or `result.to_json()` for a JSON string. Do not call `json.dumps(result)` directly.

Each reasoning item has `text` and exact source `evidence`; `problem` may be null, and missing categories are empty lists. Patterns include category, supporting session IDs/evidence, distinct session count, counterexamples, and a neutral reflection question.

## Error contract

| Failure | Raised by workflow | Saved? |
| --- | --- | --- |
| Blank input or invalid retrieval limit | `ValueError` | No |
| Provider/JSON/schema/evidence extraction failure | `ReasoningWorkflowError`, stage `extraction` | No |
| Storage failure | `ReasoningWorkflowError`, stage `storage` | No |
| Retrieval or pattern-analysis failure | `ReasoningWorkflowError`, stage `retrieval` or `pattern_detection`; may include `session_id` | Yes, inspect `session_saved` |

Messages omit user session text, provider response bodies, and credentials. The API maps these to sanitized HTTP errors. Do not return tracebacks or raw provider errors to clients.

## Minimal backend example

```python
from ai.workflow import process_reasoning_session

result = process_reasoning_session(
    "I chose BFS because every edge has equal cost.",
    owner_id=verified_user_id,
)
json_ready_response = result.to_dict()
```

For optional Supabase storage, the backend must pass the request-scoped store built from the verified user's bearer token. Do not put service-role credentials in the adapter.

## Setup

Install `requirements.txt`, configure `SUPABASE_URL` for authenticated backend routes, and configure `GEMINI_API_KEY` only for real extraction. SQLite is the default. Tests mock Gemini; they do not need a real key. See [local setup](LOCAL_SETUP.md) and [security/environment](SECURITY_AND_ENVIRONMENT.md). A real workflow request can consume Gemini quota; no live call is made by this example document.
