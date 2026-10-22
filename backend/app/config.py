"""Environment-backed settings for the HTTP application."""

import os
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173,https://stalwart-chebakia-c6da35.netlify.app"
)


def get_database_path() -> Path | None:
    """Return an optional DB path; None preserves the AI module default."""
    load_dotenv()
    configured_path = os.getenv("COGNITRACE_DB_PATH", "").strip()
    return Path(configured_path).expanduser() if configured_path else None


def get_allowed_origins() -> list[str]:
    """Read comma-separated browser origins from the local environment."""
    load_dotenv()
    configured = os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


def get_api_token() -> str | None:
    """Return the server-side bearer token, if configured."""
    load_dotenv()
    token = os.getenv("COGNITRACE_API_TOKEN", "").strip()
    if (
        not token
        or len(token) < 32
        or token.casefold().startswith("replace_with_")
    ):
        return None
    return token


def get_port() -> int:
    """Read and validate the port expected by most hosting platforms."""
    load_dotenv()
    raw_port = os.getenv("PORT", "8000").strip()
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError("PORT must be an integer between 1 and 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535.")
    return port
