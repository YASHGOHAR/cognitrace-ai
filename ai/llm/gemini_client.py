"""Small Gemini text-generation wrapper."""

import re

from google import genai
from google.genai import types

from ai.core.config import Settings, get_settings


class GeminiClientError(RuntimeError):
    """A safe, user-readable error raised when text generation fails."""


def sanitize_error_detail(detail: str, api_key: str = "") -> str:
    """Remove credentials and flatten provider text before showing diagnostics."""
    if api_key:
        detail = detail.replace(api_key, "[REDACTED]")
    detail = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", detail)
    detail = re.sub(
        r"(?i)(api[_ -]?key|authorization|bearer|token|secret)\s*[:=]\s*[^\s,;&]+",
        r"\1=[REDACTED]",
        detail,
    )
    detail = re.sub(r"(?i)([?&]key=)[^&\s]+", r"\1[REDACTED]", detail)
    return " ".join(detail.split())[:240]


def _provider_error_summary(error: Exception, api_key: str) -> str:
    """Summarize an SDK exception without exposing its raw response or secrets."""
    status_code = getattr(error, "code", None)
    status_name = getattr(error, "status", None)
    status = ""
    if isinstance(status_code, int):
        status = f", HTTP {status_code}"
    if isinstance(status_name, str) and status_name:
        status += f" {status_name}"
    # Do not echo provider response bodies: they can contain submitted content.
    # Stable status-based hints are useful while keeping diagnostics content-free.
    if status_code == 429:
        status += ": quota or rate limit exceeded; no retry attempted"
    elif status_code == 404:
        status += ": configured model or endpoint was not found"
    elif status_code in (401, 403):
        status += ": API access was denied; check key and project access"
    elif isinstance(status_code, int) and status_code >= 500:
        status += ": Gemini service error"
    else:
        status += ": provider request failed"
    return f"{type(error).__name__}{status}"


def generate_text(prompt: str, *, settings: Settings | None = None) -> str:
    """Generate text for a prompt using Gemini.

    The SDK client is created only when this function is called. SDK/network
    exceptions include a short, sanitized diagnostic so credentials are not
    accidentally included in logs or UI errors.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a non-empty string.")

    active_settings = settings or get_settings()
    if not active_settings.gemini_api_key:
        raise GeminiClientError(
            "Gemini API key is missing. Set GEMINI_API_KEY in your environment or .env file."
        )

    try:
        # The SDK otherwise retries transient errors (including 429) by
        # default. One attempt keeps free-tier quota failures predictable.
        client = genai.Client(
            api_key=active_settings.gemini_api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        response = client.models.generate_content(
            model=active_settings.gemini_model,
            contents=prompt,
        )
        text = response.text
        if not text:
            raise GeminiClientError("Gemini returned an empty response.")
        return text
    except GeminiClientError:
        raise
    except Exception as exc:
        summary = _provider_error_summary(exc, active_settings.gemini_api_key)
        raise GeminiClientError(
            "Gemini text generation failed "
            f"({summary}). Check the configured model, API access, network connection, and quota."
        ) from None
