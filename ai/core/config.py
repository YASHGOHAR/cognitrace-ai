"""Project configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


@dataclass(frozen=True)
class Settings:
    """Settings needed to call the Gemini API."""

    gemini_api_key: str | None
    gemini_model: str


def get_settings() -> Settings:
    """Load local .env values (if present) and return current settings."""
    load_dotenv()
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
        or DEFAULT_GEMINI_MODEL,
    )
