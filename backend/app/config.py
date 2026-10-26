"""Environment-backed settings for the HTTP application."""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,https://stalwart-chebakia-c6da35.netlify.app"
)


def get_database_path() -> Path | None:
    load_dotenv()
    configured_path = os.getenv("COGNITRACE_DB_PATH", "").strip()
    return Path(configured_path).expanduser() if configured_path else None


def get_storage_backend() -> str:
    """Return sqlite (the default) or the optional Supabase Data API backend."""
    load_dotenv()
    backend = os.getenv("COGNITRACE_STORAGE_BACKEND", "sqlite").strip().casefold()
    if backend not in {"sqlite", "supabase"}:
        raise ValueError("COGNITRACE_STORAGE_BACKEND must be sqlite or supabase.")
    return backend


def get_supabase_publishable_key() -> str | None:
    load_dotenv()
    value = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    return value or None


def get_allowed_origins() -> list[str]:
    load_dotenv()
    configured = os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


def get_port() -> int:
    load_dotenv()
    raw_port = os.getenv("PORT", "8000").strip()
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError("PORT must be an integer between 1 and 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535.")
    return port


def get_supabase_url() -> str | None:
    load_dotenv()
    value = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not value:
        return None
    parsed = urlparse(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parsed.scheme != "https" and not local_http) or not parsed.netloc or parsed.path not in ("", "/"):
        return None
    return value
