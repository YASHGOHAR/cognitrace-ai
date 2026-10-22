from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import save_session
from ai.workflow import ReasoningWorkflowError
from backend.app.config import DEFAULT_ALLOWED_ORIGINS, get_allowed_origins, get_port
from backend.app.routes.sessions import (
    create_session,
    get_session_by_id,
    get_session_history,
)
from backend.app.main import health
from backend.app.schemas import CreateSessionRequest
from backend.app.security import require_api_token


TEST_API_TOKEN = "test-only-token-with-at-least-32-characters"


@pytest.fixture(autouse=True)
def configured_api_token(monkeypatch):
    monkeypatch.setenv("COGNITRACE_API_TOKEN", TEST_API_TOKEN)


@pytest.fixture
def database_path(monkeypatch):
    folder = TemporaryDirectory(dir=Path(__file__).parents[1] / "work")
    database = Path(folder.name) / "backend.db"
    monkeypatch.setenv("COGNITRACE_DB_PATH", str(database))
    yield database
    folder.cleanup()


def request(token: str | None = TEST_API_TOKEN):
    authorization = f"Bearer {token}" if token is not None else None
    headers = {"authorization": authorization} if authorization else {}
    return SimpleNamespace(headers=headers)


def reasoning(evidence: str) -> ReasoningExtraction:
    return ReasoningExtraction(
        problem=None,
        decisions=[ReasoningItem(text="Use BFS", evidence=evidence)],
        justifications=[],
        alternatives_considered=[],
        assumptions=[],
    )


def save(database_path: Path, session_id: str, session_text: str) -> None:
    save_session(
        session_text,
        reasoning(session_text),
        session_id=session_id,
        db_path=database_path,
    )


def test_session_access_rejects_missing_and_invalid_bearer_tokens():
    with pytest.raises(HTTPException) as missing:
        require_api_token(None)
    with pytest.raises(HTTPException) as invalid:
        require_api_token("Bearer not-the-configured-token")

    assert missing.value.status_code == 401
    assert invalid.value.status_code == 401
    assert invalid.value.headers == {"WWW-Authenticate": "Bearer"}


def test_unauthorized_post_does_not_call_extraction():
    with patch("backend.app.routes.sessions.process_reasoning_session") as process:
        with pytest.raises(HTTPException) as error:
            create_session(
                CreateSessionRequest(session_text="I chose BFS."), request(token=None)
            )

    assert error.value.status_code == 401
    process.assert_not_called()


def test_health_is_public_and_returns_no_session_data():
    assert health() == {"status": "ok"}


def test_session_routes_fail_closed_when_server_token_is_not_configured(monkeypatch):
    monkeypatch.delenv("COGNITRACE_API_TOKEN", raising=False)

    with patch("backend.app.routes.sessions.list_sessions") as list_saved:
        with pytest.raises(HTTPException) as error:
            get_session_history(request(token=None), limit=20, offset=0)

    assert error.value.status_code == 503
    assert error.value.detail == "Session access is not configured."
    list_saved.assert_not_called()


def test_documentation_placeholder_is_not_accepted_as_an_api_token(monkeypatch):
    monkeypatch.setenv("COGNITRACE_API_TOKEN", "replace_with_a_long_random_secret")

    with pytest.raises(HTTPException) as error:
        require_api_token("Bearer replace_with_a_long_random_secret")

    assert error.value.status_code == 503


def test_short_token_is_not_accepted(monkeypatch):
    monkeypatch.setenv("COGNITRACE_API_TOKEN", "too-short")

    with pytest.raises(HTTPException) as error:
        require_api_token("Bearer too-short")

    assert error.value.status_code == 503


def test_exact_netlify_origin_is_in_default_configurable_cors_origins():
    assert "https://stalwart-chebakia-c6da35.netlify.app" in DEFAULT_ALLOWED_ORIGINS


def test_cors_origins_are_read_from_comma_separated_environment(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " http://localhost:5173 , https://cognitrace-preview.netlify.app/ ",
    )

    assert get_allowed_origins() == [
        "http://localhost:5173",
        "https://cognitrace-preview.netlify.app",
    ]


def test_port_configuration_is_read_and_validated(monkeypatch):
    monkeypatch.setenv("PORT", "9312")
    assert get_port() == 9312

    for invalid_port in ("not-a-port", "0", "65536"):
        monkeypatch.setenv("PORT", invalid_port)
        with pytest.raises(ValueError, match="PORT must be an integer"):
            get_port()


def test_production_entrypoint_binds_all_interfaces_and_uses_port(monkeypatch):
    from backend import __main__ as entrypoint

    monkeypatch.setenv("PORT", "9010")
    with patch("backend.__main__.uvicorn.run") as run:
        entrypoint.main()

    run.assert_called_once_with(
        "backend.app.main:app", host="0.0.0.0", port=9010
    )


def test_create_session_calls_existing_workflow_and_returns_json_ready_result(database_path):
    expected = {
        "session_id": "new-session",
        "reasoning": {"problem": None},
        "relevant_previous_sessions": [],
        "detected_patterns": [],
        "insufficient_evidence": True,
        "previous_sessions_considered": 0,
    }
    workflow_result = SimpleNamespace(to_dict=lambda: expected)
    source = "I chose BFS because all edges have equal cost."

    with (
        patch(
            "backend.app.routes.sessions.process_reasoning_session",
            return_value=workflow_result,
        ) as process,
        patch("ai.llm.gemini_client.genai.Client") as gemini_client,
    ):
        result = create_session(CreateSessionRequest(session_text=source), request())

    assert result == expected
    process.assert_called_once_with(source, db_path=database_path)
    gemini_client.assert_not_called()


def test_invalid_session_body_is_rejected_without_calling_workflow():
    with patch("backend.app.routes.sessions.process_reasoning_session") as process:
        with pytest.raises(ValidationError):
            CreateSessionRequest(session_text="   ")

    process.assert_not_called()


def test_extraction_error_is_safe_and_reports_that_nothing_was_saved():
    with patch(
        "backend.app.routes.sessions.process_reasoning_session",
        side_effect=ReasoningWorkflowError(
            "provider secret and private session", stage="extraction", session_saved=False
        ),
    ):
        with pytest.raises(HTTPException) as error:
            create_session(
                CreateSessionRequest(session_text="I chose BFS."), request()
            )

    assert error.value.status_code == 502
    assert error.value.detail == {
        "message": "Reasoning extraction failed; no session was saved.",
        "session_saved": False,
    }
    assert "provider secret" not in str(error.value.detail)
    assert "I chose BFS" not in str(error.value.detail)


def test_post_save_failure_includes_only_saved_status_and_session_id():
    with patch(
        "backend.app.routes.sessions.process_reasoning_session",
        side_effect=ReasoningWorkflowError(
            "private text", stage="retrieval", session_saved=True, session_id="saved-123"
        ),
    ):
        with pytest.raises(HTTPException) as error:
            create_session(
                CreateSessionRequest(session_text="I chose BFS."), request()
            )

    assert error.value.status_code == 500
    assert error.value.detail == {
        "message": "The session was saved, but a later processing step failed.",
        "session_saved": True,
        "session_id": "saved-123",
    }
    assert "private text" not in str(error.value.detail)


def test_unexpected_processing_error_does_not_expose_exception_text():
    with patch(
        "backend.app.routes.sessions.process_reasoning_session",
        side_effect=RuntimeError("private session text and provider details"),
    ):
        with pytest.raises(HTTPException) as error:
            create_session(
                CreateSessionRequest(session_text="I chose BFS."), request()
            )

    assert error.value.status_code == 500
    assert error.value.detail == "The session could not be processed."
    assert "private session text" not in str(error.value.detail)


def test_get_session_returns_saved_reasoning(database_path):
    source = "I chose BFS because all edges have equal cost."
    save(database_path, "saved-1", source)

    result = get_session_by_id("saved-1", request())

    assert result.session_id == "saved-1"
    assert result.session_text == source
    assert result.reasoning.decisions[0].text == "Use BFS"


def test_unknown_session_returns_404(database_path):
    with pytest.raises(HTTPException) as error:
        get_session_by_id("missing", request())

    assert error.value.status_code == 404
    assert error.value.detail == "Session not found."


def test_history_is_paginated_and_newest_first(database_path):
    save(database_path, "older", "I chose BFS yesterday.")
    save(database_path, "middle", "I chose BFS this morning.")
    save(database_path, "newest", "I chose BFS just now.")

    result = get_session_history(request(), limit=1, offset=1)

    assert result.limit == 1
    assert result.offset == 1
    assert [item.session_id for item in result.items] == ["middle"]
