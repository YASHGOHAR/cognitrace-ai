import base64
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_repository import SessionStoreError, SupabaseSessionStore
from backend.app.security import get_current_user


SOURCE = "I choose BFS because each edge has equal cost."
REASONING = ReasoningExtraction(
    problem=None,
    decisions=[ReasoningItem(text="Use BFS", evidence="I choose BFS")],
    justifications=[], alternatives_considered=[], assumptions=[],
)


def row(session_id, owner):
    return {
        "session_id": session_id,
        "created_at": "2026-10-24T00:00:00+00:00",
        "session_text": SOURCE,
        "reasoning_json": REASONING.model_dump(mode="json"),
        "owner_id": owner,
    }


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()


def test_storage_forwards_user_bearer_and_owner_filter_without_leaking_token():
    captured = []

    def transport(request):
        captured.append(request)
        return Response([row("owned", "user-a")])

    store = SupabaseSessionStore(
        "https://project.example", "sb_publishable_test-placeholder", "user-a", "user-jwt-placeholder", transport
    )
    result = store.get_session("owned")

    assert result.session_id == "owned"
    request = captured[0]
    assert request.get_header("Authorization") == "Bearer user-jwt-placeholder"
    assert request.get_header("Apikey") == "sb_publishable_test-placeholder"
    query = parse_qs(urlparse(request.full_url).query)
    assert query["owner_id"] == ["eq.user-a"]
    assert "user-jwt-placeholder" not in repr(store)


def test_cross_user_reads_are_isolated_by_request_token_and_owner_filter():
    seen = []

    def transport(request):
        query = parse_qs(urlparse(request.full_url).query)
        token = request.get_header("Authorization").removeprefix("Bearer ")
        requested_owner = query["owner_id"][0].removeprefix("eq.")
        seen.append((token, requested_owner))
        # This fake Data API applies the same owner predicate as the reviewed RLS policy.
        session_owner = "user-a" if token == "jwt-a" else "user-b"
        return Response([row(f"session-{session_owner}", session_owner)] if requested_owner == session_owner else [])

    stores = [
        SupabaseSessionStore("https://project.example", "sb_publishable_test", "user-a", "jwt-a", transport),
        SupabaseSessionStore("https://project.example", "sb_publishable_test", "user-b", "jwt-b", transport),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda s: s.list_sessions(limit=10), stores))

    assert [[item.session_id for item in result] for result in results] == [["session-user-a"], ["session-user-b"]]
    assert set(seen) == {("jwt-a", "user-a"), ("jwt-b", "user-b")}


def test_json_round_trip_preserves_reasoning_schema():
    captured = []

    def transport(request):
        captured.append(request)
        payload = json.loads(request.data)
        return Response([payload])

    store = SupabaseSessionStore("https://project.example", "sb_publishable_test", "user-a", "jwt", transport)
    saved = store.save_session(SOURCE, REASONING, session_id="json-session")
    sent = json.loads(captured[0].data)
    assert sent["reasoning_json"] == REASONING.model_dump(mode="json")
    assert sent['owner_id'] == 'user-a'
    assert saved.reasoning == REASONING


def test_pagination_sends_limit_offset_and_newest_first_order():
    captured = []
    rows = [row(f"s-{n}", "user-a") for n in range(5)]

    def transport(request):
        query = parse_qs(urlparse(request.full_url).query)
        captured.append(query)
        start = int(query["offset"][0])
        end = start + int(query["limit"][0])
        return Response(rows[start:end])

    store = SupabaseSessionStore("https://project.example", "sb_publishable_test", "user-a", "jwt", transport)
    result = store.list_sessions(limit=2, offset=1)

    assert [item.session_id for item in result] == ["s-1", "s-2"]
    assert captured[0]["offset"] == ["1"]
    assert captured[0]["limit"] == ["2"]
    assert captured[0]["order"] == ["created_at.desc,session_id.desc"]


def test_anonymous_and_invalid_jwt_are_denied_before_data_api(monkeypatch):
    with pytest.raises(HTTPException) as anonymous:
        get_current_user(None)
    assert anonymous.value.status_code == 401

    from backend.app import security
    from types import SimpleNamespace
    from unittest.mock import patch
    from fastapi.security import HTTPAuthorizationCredentials

    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setattr(security, "_jwk_client", lambda _: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key="public-key")
    ))
    with patch("backend.app.security.jwt.decode", side_effect=ValueError("private response")):
        with pytest.raises(HTTPException) as invalid:
            get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-jwt"))
    assert invalid.value.status_code == 401
    assert "private response" not in str(invalid.value.detail)


def test_supabase_storage_errors_are_sanitized():
    def transport(_):
        raise OSError("token and private response body")

    store = SupabaseSessionStore("https://project.example", "sb_publishable_test", "user-a", "jwt-secret", transport)
    with pytest.raises(SessionStoreError) as error:
        store.list_sessions()
    assert "token" not in str(error.value)
    assert "private response" not in str(error.value)


def test_migration_enables_owner_rls_and_grants_only_read_insert():
    migration = Path(__file__).parents[1] / "supabase" / "migrations" / "202610240001_reasoning_sessions.sql"
    sql = migration.read_text(encoding="utf-8").casefold()
    assert "enable row level security" in sql
    assert "grant select, insert" in sql
    assert "using (owner_id = (select auth.uid()))" in sql
    assert "with check (owner_id = (select auth.uid()))" in sql
    assert "revoke all on table public.reasoning_sessions from public, anon, authenticated" in sql
    assert "grant all" not in sql
    assert "service_role" not in sql


def test_service_role_keys_are_rejected_before_any_data_request():
    from ai.storage.session_repository import SupabaseSessionStore

    payload = base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
    service_role_token = f"header.{payload}.signature"
    for key in ("sb_secret_placeholder", service_role_token):
        with pytest.raises(ValueError, match="publishable or legacy anon"):
            SupabaseSessionStore("https://project.example", key, "user-a", "user-jwt")


def test_local_loopback_supabase_url_is_allowed():
    store = SupabaseSessionStore(
        "http://127.0.0.1:54321", "sb_publishable_test", "user-a", "user-jwt"
    )
    assert store._endpoint == "http://127.0.0.1:54321/rest/v1/reasoning_sessions"
