"""Minimal bearer-token protection for private session data."""

import secrets

from fastapi import HTTPException

from backend.app.config import get_api_token


def require_api_token(authorization: str | None) -> None:
    """Require a configured server-side bearer token for session endpoints."""
    configured_token = get_api_token()
    if configured_token is None:
        raise HTTPException(
            status_code=503,
            detail="Session access is not configured.",
        )
    scheme, separator, supplied_token = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not secrets.compare_digest(
            supplied_token.strip().encode("utf-8"), configured_token.encode("utf-8")
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Valid bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
