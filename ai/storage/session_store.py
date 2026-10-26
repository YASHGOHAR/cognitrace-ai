"""SQLite storage for source sessions and validated reasoning extractions."""

from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from ai.schemas.reasoning import ReasoningExtraction


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "cognitrace.db"


class DuplicateSessionError(ValueError):
    """Raised when a caller tries to reuse a stored session ID."""


@dataclass(frozen=True)
class StoredSession:
    """A saved source session and its validated reasoning result."""

    session_id: str
    created_at: str
    session_text: str
    reasoning: ReasoningExtraction


def _database_path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DATABASE_PATH


def initialize_database(db_path: str | Path | None = None) -> None:
    """Create the local database directory and sessions table if needed."""
    path = _database_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reasoning_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    session_text TEXT NOT NULL,
                    reasoning_json TEXT NOT NULL,
                    owner_id TEXT
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(reasoning_sessions)")
            }
            if "owner_id" not in columns:
                # Existing records remain unowned and cannot be exposed to any user.
                connection.execute(
                    "ALTER TABLE reasoning_sessions ADD COLUMN owner_id TEXT"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_reasoning_sessions_owner_created "
                "ON reasoning_sessions(owner_id, created_at DESC)"
            )


def _validate_inputs(
    session_text: str,
    reasoning: ReasoningExtraction,
    session_id: str | None,
) -> str:
    if not isinstance(session_text, str) or not session_text.strip():
        raise ValueError("Session text must be a non-empty string.")
    if not isinstance(reasoning, ReasoningExtraction):
        raise TypeError("Reasoning must be a validated ReasoningExtraction instance.")
    if session_id is not None and (not isinstance(session_id, str) or not session_id.strip()):
        raise ValueError("Session ID must be a non-empty string when provided.")

    items = [*reasoning.decisions, *reasoning.justifications,
             *reasoning.alternatives_considered, *reasoning.assumptions]
    if reasoning.problem is not None:
        items.append(reasoning.problem)
    if any(not item.evidence or item.evidence not in session_text for item in items):
        raise ValueError("Every evidence quote must be non-empty and appear exactly in the session text.")
    return session_id.strip() if session_id is not None else str(uuid4())


def save_session(
    session_text: str,
    reasoning: ReasoningExtraction,
    *,
    session_id: str | None = None,
    db_path: str | Path | None = None,
    owner_id: str | None = None,
) -> StoredSession:
    """Save a source session and its already-computed extraction; makes no LLM calls."""
    resolved_id = _validate_inputs(session_text, reasoning, session_id)
    created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    reasoning_json = json.dumps(reasoning.model_dump(mode="json"), ensure_ascii=False)
    path = _database_path(db_path)
    initialize_database(path)
    try:
        with closing(sqlite3.connect(path)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO reasoning_sessions "
                    "(session_id, created_at, session_text, reasoning_json, owner_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (resolved_id, created_at, session_text, reasoning_json, owner_id),
                )
    except sqlite3.IntegrityError as exc:
        raise DuplicateSessionError(f"Session ID already exists: {resolved_id}") from exc
    return StoredSession(resolved_id, created_at, session_text, reasoning)


def get_session(
    session_id: str,
    *,
    db_path: str | Path | None = None,
    owner_id: str | None = None,
) -> StoredSession | None:
    """Retrieve one session, returning None when its ID is unknown."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Session ID must be a non-empty string.")
    path = _database_path(db_path)
    initialize_database(path)
    with closing(sqlite3.connect(path)) as connection:
        if owner_id is None:
            row = connection.execute(
                "SELECT session_id, created_at, session_text, reasoning_json "
                "FROM reasoning_sessions WHERE session_id = ?",
                (session_id.strip(),),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT session_id, created_at, session_text, reasoning_json "
                "FROM reasoning_sessions WHERE session_id = ? AND owner_id = ?",
                (session_id.strip(), owner_id),
            ).fetchone()
    if row is None:
        return None
    return StoredSession(row[0], row[1], row[2], ReasoningExtraction.model_validate(json.loads(row[3])))


def list_sessions(
    *,
    limit: int | None = 20,
    offset: int = 0,
    db_path: str | Path | None = None,
    owner_id: str | None = None,
) -> list[StoredSession]:
    """List recent sessions newest first with optional pagination.

    ``limit=None`` returns every row from ``offset`` onward.
    """
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
    ):
        raise ValueError("Limit must be a positive integer or None.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("Offset must be a non-negative integer.")
    path = _database_path(db_path)
    initialize_database(path)
    with closing(sqlite3.connect(path)) as connection:
        query = "SELECT session_id, created_at, session_text, reasoning_json FROM reasoning_sessions"
        parameters: tuple[object, ...] = ()
        if owner_id is not None:
            query += " WHERE owner_id = ?"
            parameters = (owner_id,)
        query += " ORDER BY created_at DESC, session_id DESC"
        if limit is None:
            rows = connection.execute(
                query + " LIMIT -1 OFFSET ?", (*parameters, offset)
            ).fetchall()
        else:
            rows = connection.execute(
                query + " LIMIT ? OFFSET ?", (*parameters, limit, offset)
            ).fetchall()
    return [
        StoredSession(row[0], row[1], row[2], ReasoningExtraction.model_validate(json.loads(row[3])))
        for row in rows
    ]
