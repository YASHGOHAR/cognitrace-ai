from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from jwt import PyJWKClientConnectionError

from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import get_session, list_sessions, save_session
from ai.workflow import ReasoningWorkflowError
from backend.app.config import DEFAULT_ALLOWED_ORIGINS, get_allowed_origins, get_port
from backend.app.main import app, health
from backend.app.routes.sessions import chat, create_session, get_session_by_id, get_session_history
from backend.app.schemas import ChatMessage, ChatRequest, CreateSessionRequest
from backend.app.security import get_current_user
from fastapi.security import HTTPAuthorizationCredentials


@pytest.fixture
def database_path(monkeypatch):
    folder = TemporaryDirectory(dir=Path(__file__).parents[1] / "work")
    database = Path(folder.name) / "backend.db"
    monkeypatch.setenv("COGNITRACE_DB_PATH", str(database))
    yield database
    folder.cleanup()



def reasoning(evidence: str) -> ReasoningExtraction:
    return ReasoningExtraction(
        problem=None,
        decisions=[ReasoningItem(text="Use BFS", evidence=evidence)],
        justifications=[],
        alternatives_considered=[],
        assumptions=[],
    )


def save(database_path: Path, session_id: str, text: str, owner: str = "user-a"):
    return save_session(text, reasoning(text), session_id=session_id, db_path=database_path, owner_id=owner)


def test_auth_requires_bearer_and_config(monkeypatch):
    with pytest.raises(HTTPException) as missing:
        get_current_user(None)
    assert missing.value.status_code == 401

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("COGNITRACE_API_TOKEN", "a-test-only-shared-service-token-not-for-users")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-real-token")
    with pytest.raises(HTTPException) as not_configured:
        get_current_user(credentials)
    assert not_configured.value.status_code == 503


def test_local_supabase_url_allows_loopback_http(monkeypatch):
    from backend.app.config import get_supabase_url

    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    assert get_supabase_url() == "http://127.0.0.1:54321"

    monkeypatch.setenv("SUPABASE_URL", "http://example.test")
    assert get_supabase_url() is None


def test_auth_verifies_asymmetric_jwt_claims_and_returns_subject(monkeypatch):
    from backend.app import security

    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    fake_key = SimpleNamespace(key="public-key")
    fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: fake_key)
    monkeypatch.setattr(security, "_jwk_client", lambda url: fake_client)
    with patch("backend.app.security.jwt.decode", return_value={
        "sub": "user-123",
        "iss": "https://project.example/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "exp": 9999999999,
    }) as decode:
        result = get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="opaque-user-jwt")
        )
    assert result == "user-123"
    assert result.access_token == "opaque-user-jwt"
    assert "opaque-user-jwt" not in repr(result)
    assert decode.call_args.kwargs["algorithms"] == ["ES256", "RS256"]
    assert decode.call_args.kwargs["audience"] == "authenticated"
    assert decode.call_args.kwargs["issuer"] == "https://project.example/auth/v1"


def test_real_es256_jwt_is_verified_and_identifies_its_subject(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from cryptography.hazmat.primitives.asymmetric import ec
    from backend.app import security
    import jwt

    project_url = 'https://project.example'
    private_key = ec.generate_private_key(ec.SECP256R1())
    claims = {
        'sub': 'verified-user-42',
        'iss': f'{project_url}/auth/v1',
        'aud': 'authenticated',
        'role': 'authenticated',
        'exp': datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    access_token = jwt.encode(claims, private_key, algorithm='ES256')
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key())
    )
    monkeypatch.setenv('SUPABASE_URL', project_url)
    monkeypatch.setattr(security, '_jwk_client', lambda _: fake_client)

    result = get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=access_token))

    assert result == 'verified-user-42'
    assert result.access_token == access_token
    assert access_token not in repr(result)

def test_invalid_jwt_is_sanitized(monkeypatch):
    from backend.app import security

    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key"))
    monkeypatch.setattr(security, "_jwk_client", lambda url: fake_client)
    with patch("backend.app.security.jwt.decode", side_effect=ValueError("secret provider details")):
        with pytest.raises(HTTPException) as error:
            get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="private-token"))
    assert error.value.status_code == 401
    assert "private-token" not in str(error.value.detail)
    assert "secret provider" not in str(error.value.detail)


def test_jwks_network_failure_is_sanitized_service_unavailable(monkeypatch):
    from backend.app import security

    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: (_ for _ in ()).throw(
            PyJWKClientConnectionError("secret response")
        )
    )
    monkeypatch.setattr(security, "_jwk_client", lambda url: fake_client)
    with pytest.raises(HTTPException) as error:
        get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"))
    assert error.value.status_code == 503
    assert "secret response" not in str(error.value.detail)


def test_user_can_only_list_and_read_owned_sessions(database_path):
    save(database_path, "user-a-session", "User A reasoning.")
    save(database_path, "user-b-session", "User B reasoning.", owner="user-b")

    assert [item.session_id for item in list_sessions(db_path=database_path, owner_id="user-a")] == ["user-a-session"]
    assert get_session("user-b-session", db_path=database_path, owner_id="user-a") is None
    assert get_session("user-a-session", db_path=database_path, owner_id="user-a") is not None


def test_openapi_documents_bearer_authentication():
    schema = app.openapi()
    assert "SupabaseUserBearer" in schema["components"]["securitySchemes"]
    assert schema["paths"]["/api/sessions"]["get"]["security"]


def test_health_is_public():
    assert health() == {"status": "ok"}


def test_private_session_responses_are_not_cached():
    response = TestClient(app).get("/api/sessions")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_chat_generates_reply_from_authenticated_conversation():
    with patch("backend.app.routes.sessions.generate_text", return_value="What evidence would change your mind?") as model:
        response = chat(
            ChatRequest(messages=[ChatMessage(role="user", content="I am unsure.")]),
            _user="user-a",
        )
    assert response.message == "What evidence would change your mind?"
    model.assert_called_once()
    assert "USER: I am unsure." in model.call_args.args[0]


def test_chat_provider_failure_is_sanitized():
    from ai.llm.gemini_client import GeminiClientError

    with patch(
        "backend.app.routes.sessions.generate_text",
        side_effect=GeminiClientError("private provider details"),
    ):
        with pytest.raises(HTTPException) as error:
            chat(ChatRequest(messages=[ChatMessage(role="user", content="Hello.")]), _user="user-a")
    assert error.value.status_code == 502
    assert error.value.detail == "The AI assistant could not respond right now."


def test_unauthorized_and_validation_requests_do_not_reach_workflow():
    with pytest.raises(HTTPException) as error:
        get_current_user(None)
    assert error.value.status_code == 401
    with patch("backend.app.routes.sessions.process_reasoning_session") as process:
        with pytest.raises(ValidationError):
            CreateSessionRequest(session_text=" ")
    process.assert_not_called()

def test_cors_origins_are_configurable_and_include_current_frontend_default():
    assert "https://stalwart-chebakia-c6da35.netlify.app" in DEFAULT_ALLOWED_ORIGINS
    assert "http://127.0.0.1:5173" in DEFAULT_ALLOWED_ORIGINS
    import os

    os.environ["CORS_ALLOWED_ORIGINS"] = " http://localhost:5173 , https://preview.example/ "
    try:
        assert get_allowed_origins() == ["http://localhost:5173", "https://preview.example"]
    finally:
        os.environ.pop("CORS_ALLOWED_ORIGINS", None)


def test_port_configuration_is_read_and_validated(monkeypatch):
    monkeypatch.setenv("PORT", "9312")
    assert get_port() == 9312
    for invalid in ("bad", "0", "65536"):
        monkeypatch.setenv("PORT", invalid)
        with pytest.raises(ValueError, match="PORT must be an integer"):
            get_port()


def test_production_entrypoint_binds_all_interfaces_and_uses_port(monkeypatch):
    from backend import __main__ as entrypoint

    monkeypatch.setenv("PORT", "9010")
    with patch("backend.__main__.uvicorn.run") as run:
        entrypoint.main()
    run.assert_called_once_with("backend.app.main:app", host="0.0.0.0", port=9010)


def test_create_session_passes_verified_owner_to_existing_workflow(database_path):
    expected = {"session_id": "new-session", "reasoning": {"problem": None}}
    result = SimpleNamespace(to_dict=lambda: expected)
    source = "I chose BFS."

    with patch("backend.app.routes.sessions.process_reasoning_session", return_value=result) as process:
        response = create_session(
            CreateSessionRequest(session_text=source), user_id="user-a"
        )
    assert response == expected
    process.assert_called_once_with(source, db_path=database_path, owner_id="user-a")


def test_invalid_schema_rejected():
    with pytest.raises(ValidationError):
        CreateSessionRequest(session_text="   ")


def test_extraction_error_response_is_safe():
    with patch(
        "backend.app.routes.sessions.process_reasoning_session",
        side_effect=ReasoningWorkflowError("private provider text", stage="extraction", session_saved=False),
    ):
        with pytest.raises(HTTPException) as error:
            create_session(CreateSessionRequest(session_text="I chose BFS."), user_id="user-a")
    assert error.value.status_code == 502
    assert error.value.detail == {
        "message": "Reasoning extraction failed; no session was saved.",
        "session_saved": False,
    }
    assert "private provider text" not in str(error.value.detail)



def test_authenticated_post_persists_only_for_verified_owner(database_path, monkeypatch):
    monkeypatch.setenv("COGNITRACE_DB_PATH", str(database_path))
    source = "I will use BFS because each edge has equal cost."
    with patch("ai.workflow.extract_reasoning", return_value=reasoning(source)):
        response = create_session(CreateSessionRequest(session_text=source), user_id="user-a")
    session_id = response["session_id"]
    assert get_session(session_id, db_path=database_path, owner_id="user-a") is not None
    assert get_session(session_id, db_path=database_path, owner_id="user-b") is None

def test_post_retrieval_never_includes_another_users_sessions(database_path, monkeypatch):
    monkeypatch.setenv("COGNITRACE_DB_PATH", str(database_path))
    source = "I will use BFS because each edge has equal cost."
    save(database_path, "other-users-match", source, owner="user-b")
    with patch("ai.workflow.extract_reasoning", return_value=reasoning(source)):
        response = create_session(CreateSessionRequest(session_text=source), user_id="user-a")
    assert response["relevant_previous_sessions"] == []
    assert response["previous_sessions_considered"] == 0

def test_other_user_session_is_404_not_disclosed(database_path, monkeypatch):
    monkeypatch.setenv("COGNITRACE_DB_PATH", str(database_path))
    save(database_path, "private-session", "A private decision.", owner="user-b")
    with pytest.raises(HTTPException) as error:
        get_session_by_id("private-session", user_id="user-a")
    assert error.value.status_code == 404
    assert error.value.detail == "Session not found."

def test_authenticated_history_only_contains_current_user(database_path, monkeypatch):
    monkeypatch.setenv("COGNITRACE_DB_PATH", str(database_path))
    save(database_path, "mine", "My decision.", owner="user-a")
    save(database_path, "not-mine", "Someone else's decision.", owner="user-b")
    response = get_session_history(user_id="user-a", limit=20, offset=0)
    assert [item.session_id for item in response.items] == ["mine"]


def test_storage_backend_configuration_keeps_sqlite_as_default(monkeypatch):
    from backend.app.config import get_storage_backend, get_supabase_publishable_key

    monkeypatch.delenv("COGNITRACE_STORAGE_BACKEND", raising=False)
    assert get_storage_backend() == "sqlite"
    monkeypatch.setenv("COGNITRACE_STORAGE_BACKEND", "supabase")
    assert get_storage_backend() == "supabase"
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test-placeholder")
    assert get_supabase_publishable_key() == "sb_publishable_test-placeholder"
    monkeypatch.setenv("COGNITRACE_STORAGE_BACKEND", "service_role")
    with pytest.raises(ValueError):
        get_storage_backend()


def test_request_store_rejects_secret_and_service_role_project_keys(monkeypatch):
    from backend.app.security import AuthenticatedUser
    from backend.app.session_storage import get_request_session_store

    monkeypatch.setenv('COGNITRACE_STORAGE_BACKEND', 'supabase')
    monkeypatch.setenv('SUPABASE_URL', 'https://project.example')
    user = AuthenticatedUser('verified-user', 'user-access-token')
    service_role_payload = 'eyJyb2xlIjoic2VydmljZV9yb2xlIn0'
    service_role_jwt = f'header.{service_role_payload}.signature'
    for key in ('sb_secret_test-placeholder', service_role_jwt):
        monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', key)
        with pytest.raises(ValueError, match='publishable or legacy anon'):
            get_request_session_store(user)

def test_request_store_uses_verified_owner_and_access_token_only_in_supabase_mode(monkeypatch):
    from backend.app.security import AuthenticatedUser
    from backend.app.session_storage import get_request_session_store
    from ai.storage.session_repository import SupabaseSessionStore, SQLiteSessionStore

    user = AuthenticatedUser("verified-user", "verified-access-token")
    monkeypatch.setenv("COGNITRACE_STORAGE_BACKEND", "sqlite")
    assert isinstance(get_request_session_store(user), SQLiteSessionStore)
    monkeypatch.setenv("COGNITRACE_STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test-placeholder")
    store = get_request_session_store(user)
    assert isinstance(store, SupabaseSessionStore)
    assert store.owner_id == "verified-user"
    assert store.access_token == "verified-access-token"
    assert "verified-access-token" not in repr(store)
