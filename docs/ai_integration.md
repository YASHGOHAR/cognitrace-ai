# Cognitrace AI backend integration contract

This document describes the direct Python entry point for Person 3's backend. The AI module does not expose an HTTP endpoint. The backend calls the function below and serializes its result for its own response format.

## Public function

```python
process_reasoning_session(
    session_text: str,
    *,
    db_path: str | pathlib.Path | None = None,
    settings: ai.core.config.Settings | None = None,
    retrieval_limit: int = 10,
) -> ai.workflow.ReasoningWorkflowResult
```

- `session_text` is the new problem-solving session and must be a non-empty string.
- `db_path` chooses the SQLite file. By default storage uses `<project-root>/data/cognitrace.db`; the directory and table are created automatically. `.gitignore` excludes `data/` because it contains user session text.
- `settings` is optional. When omitted, the existing Gemini extractor reads its settings from environment variables and `.env` via `python-dotenv`.
- `retrieval_limit` must be a positive integer (default `10`). It limits both the returned keyword matches and the historical sessions considered for pattern detection.

The function calls `extract_reasoning` once, saves the original source text plus validated Pydantic result, retrieves matching prior sessions, then detects patterns within that same historical retrieval scope. The new session ID is excluded from both history and pattern evidence.

## Return structure and JSON serialization

The result has these fields:

- `session_id`: ID assigned to the saved current session.
- `reasoning`: `ReasoningExtraction` Pydantic model.
- `relevant_previous_sessions`: tuple of results with `session_id`, `timestamp`, `relevance_score`, `session_text`, and Pydantic `reasoning`.
- `detected_patterns`: tuple of supported patterns. Each has a description, reasoning category, supporting session IDs and exact evidence, distinct supporting session count, counterexamples when found, and a neutral reflection question.
- `insufficient_evidence`: `true` when no pattern has support from at least two distinct historical sessions.
- `previous_sessions_considered`: number of historical search results analyzed for patterns.

The top-level result is a dataclass. Call `result.to_dict()` for JSON-ready data or `result.to_json()` for a JSON string. Nested reasoning models use Pydantic's `model_dump(mode="json")`. Do not call `json.dumps(result)` directly.

## Synthetic input and output example

Input:

```text
I need to find the shortest path in an unweighted graph. I considered Dijkstra, but I chose BFS because every edge has equal cost. I will use a queue to explore nodes level by level.
```

Output excerpt (all IDs, previous sessions, and pattern evidence below are fabricated documentation examples; this is not a model-output guarantee or actual user behavior):

```json
{
  "session_id": "new-session-example",
  "reasoning": {
    "problem": {"text": "Find the shortest path in an unweighted graph.", "evidence": "find the shortest path in an unweighted graph"},
    "decisions": [{"text": "Use BFS.", "evidence": "I chose BFS"}],
    "justifications": [{"text": "Every edge has equal cost.", "evidence": "every edge has equal cost"}],
    "alternatives_considered": [{"text": "Dijkstra.", "evidence": "I considered Dijkstra"}],
    "assumptions": []
  },
  "relevant_previous_sessions": [
    {
      "session_id": "another-previous-session-example",
      "timestamp": "2025-12-31T12:00:00+00:00",
      "relevance_score": 14,
      "session_text": "I choose a queue to explore the graph level by level.",
      "reasoning": {
        "problem": null,
        "decisions": [{"text": "Use a queue to explore graph level by level", "evidence": "I choose a queue to explore the graph level by level."}],
        "justifications": [], "alternatives_considered": [], "assumptions": []
      }
    },
    {
      "session_id": "previous-session-example",
      "timestamp": "2026-01-01T12:00:00+00:00",
      "relevance_score": 12,
      "session_text": "I use a queue for graph traversal, one level at a time.",
      "reasoning": {
        "problem": null,
        "decisions": [{"text": "Use queue for graph traversal level at a time", "evidence": "I use a queue for graph traversal, one level at a time."}],
        "justifications": [], "alternatives_considered": [], "assumptions": []
      }
    }
  ],
  "detected_patterns": [
    {
      "description": "Possible recurring decision: Use queue for graph traversal level at a time",
      "category": "decisions",
      "supporting_session_ids": ["another-previous-session-example", "previous-session-example"],
      "supporting_evidence": [
        {"session_id": "another-previous-session-example", "category": "decisions", "text": "Use a queue to explore graph level by level", "evidence": "I choose a queue to explore the graph level by level."},
        {"session_id": "previous-session-example", "category": "decisions", "text": "Use queue for graph traversal level at a time", "evidence": "I use a queue for graph traversal, one level at a time."}
      ],
      "distinct_session_count": 2,
      "counterexamples": [],
      "reflection_question": "What factors made this approach useful in these sessions, and when might another option fit better?"
    }
  ],
  "insufficient_evidence": false,
  "previous_sessions_considered": 2
}
```

## Error-handling contract

| Failure | Exception | Saved? | Backend action |
|---|---|---:|---|
| Empty/invalid session or retrieval limit | `ValueError` | No | Return a client input error. |
| Gemini/provider, malformed output, schema, or evidence validation failure | `ReasoningWorkflowError`, `stage="extraction"`, `session_saved=False` | No | Report a generic extraction failure; do not retry automatically. |
| SQLite write failure | `ReasoningWorkflowError`, `stage="storage"`, `session_saved=False` | No | Report a local storage failure. |
| Historical retrieval failure | `ReasoningWorkflowError`, `stage="retrieval"`, `session_saved=True`, with `session_id` | Yes | Retain the ID and report partial success or that history could not be loaded. |
| Pattern-analysis failure | `ReasoningWorkflowError`, `stage="pattern_detection"`, `session_saved=True`, with `session_id` | Yes | Retain the ID and report partial success or that pattern analysis failed. |

Workflow errors omit source text, provider response bodies, and credentials. `ReasoningWorkflowError.stage`, `.session_saved`, and `.session_id` are fields for backend handling. Errors after persistence do not roll back the saved session; use the supplied ID to retrieve it.

## Dependencies and setup

Use the existing `requirements.txt`; no new package is needed. From the project root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configure `GEMINI_API_KEY` in a private local `.env` (copy `.env.example`) or process environment. Never commit or log it. The workflow makes one Gemini request per new session, which may consume available free quota. No paid billing is assumed. Tests mock extraction and do not need a key or contact Gemini.

## Minimal backend-side Python example

```python
import json
from pathlib import Path

from ai.workflow import ReasoningWorkflowError, process_reasoning_session


def analyze_for_backend(session_text: str) -> dict:
    try:
        result = process_reasoning_session(
            session_text,
            db_path=Path("data/backend_sessions.db"),
        )
        return result.to_dict()  # JSON-ready data for the backend response layer
    except ReasoningWorkflowError as exc:
        # Do not return raw tracebacks or provider/database exceptions.
        return {
            "error": str(exc),
            "stage": exc.stage,
            "session_saved": exc.session_saved,
            "session_id": exc.session_id,
        }


payload = analyze_for_backend("I chose BFS because every edge has equal cost.")
json.dumps(payload, ensure_ascii=False)
```

The backend maps failures to its own HTTP status codes. This contract is a direct Python integration, not an API endpoint.
