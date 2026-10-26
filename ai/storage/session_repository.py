"""Session-store adapters with the same small interface for each backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import base64
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from ai.schemas.reasoning import ReasoningExtraction
from ai.storage.session_store import DuplicateSessionError, StoredSession
from ai.storage.session_store import get_session as sqlite_get_session
from ai.storage.session_store import list_sessions as sqlite_list_sessions
from ai.storage.session_store import save_session as sqlite_save_session


def _is_publishable_key(value: str) -> bool:
    """Accept current publishable keys or legacy anon JWT keys only."""
    if value.startswith("sb_publishable_") and len(value) > len("sb_publishable_"):
        return True
    if value.startswith("sb_secret_"):
        return False
    try:
        parts = value.split(".")
        if len(parts) != 3:
            return False
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return claims.get("role") == "anon"
    except Exception:
        return False


class SessionStoreError(RuntimeError):
    """Sanitized storage failure; provider response bodies are never included."""


class SessionStore:
    """Small adapter interface used by retrieval, patterns, and workflow."""

    def save_session(self, session_text, reasoning, *, session_id=None):
        raise NotImplementedError

    def get_session(self, session_id):
        raise NotImplementedError

    def list_sessions(self, *, limit=20, offset=0):
        raise NotImplementedError


@dataclass(frozen=True)
class SQLiteSessionStore(SessionStore):
    """Owner-bound adapter over the unchanged SQLite storage functions."""

    owner_id: str
    db_path: Any = None

    def save_session(self, session_text, reasoning, *, session_id=None):
        return sqlite_save_session(session_text, reasoning, session_id=session_id,
                                   db_path=self.db_path, owner_id=self.owner_id)

    def get_session(self, session_id):
        return sqlite_get_session(session_id, db_path=self.db_path, owner_id=self.owner_id)

    def list_sessions(self, *, limit=20, offset=0):
        return sqlite_list_sessions(limit=limit, offset=offset,
                                    db_path=self.db_path, owner_id=self.owner_id)


@dataclass(frozen=True)
class SupabaseSessionStore(SessionStore):
    """Request-scoped Supabase Data API adapter forwarding the verified user's JWT.

    Construct one adapter per HTTP request. Supabase validates the forwarded
    bearer token and applies row-level security. The publishable key identifies
    the project; no service credential is accepted by this class.
    """

    project_url: str
    publishable_key: str
    owner_id: str
    access_token: str = field(repr=False)
    transport: Callable[[Request], Any] | None = field(default=None, repr=False, compare=False)

    TABLE = "reasoning_sessions"
    PAGE_SIZE = 1000

    def __post_init__(self):
        parsed_url = urlparse(self.project_url)
        local_http = parsed_url.scheme == "http" and parsed_url.hostname in {
            "localhost", "127.0.0.1", "::1"
        }
        if (parsed_url.scheme != "https" and not local_http) or not parsed_url.netloc:
            raise ValueError("Supabase project URL must use HTTPS, except for local loopback development.")
        if not self.owner_id or not self.access_token:
            raise ValueError("Supabase storage requires a verified user identity and access token.")
        if not _is_publishable_key(self.publishable_key):
            raise ValueError("Supabase storage requires a publishable or legacy anon project key.")

    @property
    def _endpoint(self):
        return f"{self.project_url.rstrip('/')}/rest/v1/{self.TABLE}"

    def _request(self, method, params, body=None):
        url = f"{self._endpoint}?{urlencode(params)}" if params else self._endpoint
        headers = {"apikey": self.publishable_key,
                   "Authorization": f"Bearer {self.access_token}",
                   "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=data, headers=headers, method=method)
        try:
            response = self.transport(request) if self.transport is not None else urlopen(request, timeout=15)
            raw = response.read()
            if not raw:
                return []
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, list) else [parsed]
        except HTTPError as exc:
            if exc.code == 409:
                raise DuplicateSessionError("Session ID already exists.") from None
            if exc.code in (401, 403):
                raise SessionStoreError("Session storage authorization failed.") from None
            raise SessionStoreError("Supabase session storage request failed.") from None
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            raise SessionStoreError("Supabase session storage is unavailable.") from None
        except Exception:
            raise SessionStoreError("Supabase session storage request failed.") from None

    @staticmethod
    def _as_session(row):
        try:
            reasoning = row["reasoning_json"]
            if isinstance(reasoning, str):
                reasoning = json.loads(reasoning)
            return StoredSession(session_id=str(row["session_id"]),
                                 created_at=str(row["created_at"]),
                                 session_text=row["session_text"],
                                 reasoning=ReasoningExtraction.model_validate(reasoning))
        except Exception:
            raise SessionStoreError("Supabase returned an invalid stored session.") from None

    def save_session(self, session_text, reasoning, *, session_id=None):
        if not isinstance(session_text, str) or not session_text.strip():
            raise ValueError("Session text must be a non-empty string.")
        if not isinstance(reasoning, ReasoningExtraction):
            raise TypeError("Reasoning must be a validated ReasoningExtraction instance.")
        items = [*reasoning.decisions, *reasoning.justifications,
                 *reasoning.alternatives_considered, *reasoning.assumptions]
        if reasoning.problem is not None:
            items.append(reasoning.problem)
        if any(not item.evidence or item.evidence not in session_text for item in items):
            raise ValueError("Every evidence quote must appear exactly in the session text.")
        resolved_id = session_id.strip() if isinstance(session_id, str) else str(uuid4())
        if not resolved_id:
            raise ValueError("Session ID must be non-empty.")
        row = {"session_id": resolved_id,
               "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
               "session_text": session_text,
               "reasoning_json": reasoning.model_dump(mode="json"),
               "owner_id": self.owner_id}
        returned = self._request("POST", {"select": "*"}, row)
        return self._as_session(returned[0] if returned else row)

    def get_session(self, session_id):
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Session ID must be a non-empty string.")
        rows = self._request("GET", {"select": "*",
                                     "session_id": f"eq.{session_id.strip()}",
                                     "owner_id": f"eq.{self.owner_id}", "limit": "1"})
        return self._as_session(rows[0]) if rows else None

    def list_sessions(self, *, limit=20, offset=0):
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
            raise ValueError("Limit must be a positive integer or None.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("Offset must be a non-negative integer.")
        rows, page_offset, remaining = [], offset, limit
        while remaining is None or remaining > 0:
            size = self.PAGE_SIZE if remaining is None else min(self.PAGE_SIZE, remaining)
            page = self._request("GET", {"select": "*", "owner_id": f"eq.{self.owner_id}",
                                          "order": "created_at.desc,session_id.desc",
                                          "limit": str(size), "offset": str(page_offset)})
            rows.extend(page)
            page_offset += len(page)
            if remaining is not None:
                remaining -= len(page)
            if len(page) < size:
                break
        return [self._as_session(row) for row in rows]
