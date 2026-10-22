import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import (
    DuplicateSessionError,
    get_session,
    initialize_database,
    list_sessions,
    save_session,
)


@pytest.fixture
def database_directory():
    # Keep test databases inside the writable workspace because this Windows
    # sandbox does not allow pytest's default AppData temp directory.
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "work") as folder:
        yield Path(folder)


def extraction(evidence="I chose BFS"):
    return ReasoningExtraction(
        problem=None,
        decisions=[ReasoningItem(text="Use BFS", evidence=evidence)],
        justifications=[],
        alternatives_considered=[],
        assumptions=[],
    )


def test_initialize_database_creates_table(database_directory):
    database = database_directory / "nested" / "sessions.db"

    initialize_database(database)

    assert database.exists()
    with closing(sqlite3.connect(database)) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "reasoning_sessions" in names


def test_save_and_retrieve_session_preserves_schema_and_source(database_directory):
    database = database_directory / "sessions.db"
    saved = save_session(
        "I chose BFS because all edges have equal cost.", extraction(),
        session_id="session-1", db_path=database,
    )

    loaded = get_session("session-1", db_path=database)

    assert loaded == saved
    assert loaded.reasoning.model_dump() == extraction().model_dump()
    assert loaded.created_at.endswith("+00:00")


def test_list_sessions_is_newest_first_and_obeys_limit(database_directory):
    database = database_directory / "sessions.db"
    save_session("I chose BFS", extraction(), session_id="older", db_path=database)
    save_session("I chose BFS", extraction(), session_id="newer", db_path=database)
    # Set deterministic timestamps so the ordering assertion does not depend on clock resolution.
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute("UPDATE reasoning_sessions SET created_at = '2026-01-01T00:00:00+00:00' WHERE session_id = 'older'")
            connection.execute("UPDATE reasoning_sessions SET created_at = '2026-01-02T00:00:00+00:00' WHERE session_id = 'newer'")

    recent = list_sessions(limit=1, db_path=database)

    assert [item.session_id for item in recent] == ["newer"]
    assert [item.session_id for item in list_sessions(db_path=database)] == ["newer", "older"]
    assert [item.session_id for item in list_sessions(limit=1, offset=1, db_path=database)] == ["older"]


def test_unknown_session_id_returns_none(database_directory):
    assert get_session("missing", db_path=database_directory / "sessions.db") is None


def test_duplicate_session_ids_are_rejected(database_directory):
    database = database_directory / "sessions.db"
    save_session("I chose BFS", extraction(), session_id="same", db_path=database)

    with pytest.raises(DuplicateSessionError, match="already exists"):
        save_session("I chose BFS", extraction(), session_id="same", db_path=database)


@pytest.mark.parametrize("session_text", ["", "   ", None])
def test_empty_or_invalid_session_text_is_rejected(database_directory, session_text):
    with pytest.raises(ValueError, match="non-empty string"):
        save_session(session_text, extraction(), db_path=database_directory / "sessions.db")


def test_invalid_reasoning_type_or_unsupported_evidence_is_rejected(database_directory):
    with pytest.raises(TypeError, match="ReasoningExtraction"):
        save_session("I chose BFS", {}, db_path=database_directory / "sessions.db")
    with pytest.raises(ValueError, match="evidence quote"):
        save_session("I chose BFS", extraction("I selected BFS"), db_path=database_directory / "sessions.db")


def test_invalid_ids_and_limits_are_rejected(database_directory):
    with pytest.raises(ValueError, match="Session ID"):
        save_session("I chose BFS", extraction(), session_id=" ", db_path=database_directory / "sessions.db")
    with pytest.raises(ValueError, match="positive integer"):
        list_sessions(limit=0, db_path=database_directory / "sessions.db")
    with pytest.raises(ValueError, match="non-negative integer"):
        list_sessions(offset=-1, db_path=database_directory / "sessions.db")
