from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from google.genai.errors import ClientError

from ai.core.config import Settings
from ai.llm.gemini_client import GeminiClientError, generate_text


def test_generate_text_uses_configured_model_and_returns_text():
    fake_client = Mock()
    fake_client.models.generate_content.return_value = SimpleNamespace(text="Generated answer")
    settings = Settings(gemini_api_key="test-key", gemini_model="test-model")

    with patch("ai.llm.gemini_client.genai.Client", return_value=fake_client) as client_factory:
        result = generate_text("A useful prompt", settings=settings)

    assert result == "Generated answer"
    kwargs = client_factory.call_args.kwargs
    assert kwargs["api_key"] == "test-key"
    assert kwargs["http_options"].retry_options.attempts == 1
    fake_client.models.generate_content.assert_called_once_with(
        model="test-model", contents="A useful prompt"
    )


@pytest.mark.parametrize("prompt", ["", "   ", None])
def test_generate_text_rejects_empty_prompt(prompt):
    with pytest.raises(ValueError, match="non-empty"):
        generate_text(prompt, settings=Settings("test-key", "test-model"))


def test_generate_text_rejects_missing_api_key():
    with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
        generate_text("prompt", settings=Settings(None, "test-model"))


def test_generate_text_hides_provider_exception_details():
    fake_client = Mock()
    fake_client.models.generate_content.side_effect = RuntimeError("secret=do-not-leak")
    settings = Settings(gemini_api_key="test-key", gemini_model="test-model")

    with patch("ai.llm.gemini_client.genai.Client", return_value=fake_client):
        with pytest.raises(GeminiClientError) as error:
            generate_text("prompt", settings=settings)

    assert "do-not-leak" not in str(error.value)


def test_generate_text_reports_sanitized_sdk_error_status_and_message():
    api_key = "test-secret-api-key"
    fake_client = Mock()
    fake_client.models.generate_content.side_effect = ClientError(
        404,
        {
            "error": {
                "status": "NOT_FOUND",
                "message": f"models/gemini-2.5-flash unavailable; api_key={api_key}",
            }
        },
    )
    settings = Settings(gemini_api_key=api_key, gemini_model="gemini-2.5-flash")

    with patch("ai.llm.gemini_client.genai.Client", return_value=fake_client):
        with pytest.raises(GeminiClientError) as error:
            generate_text("prompt", settings=settings)

    message = str(error.value)
    assert "ClientError, HTTP 404 NOT_FOUND" in message
    assert "configured model or endpoint was not found" in message
    assert api_key not in message


def test_generate_text_reports_quota_error_without_retry_or_secret_leak():
    api_key = "mocked-gemini-key-for-redaction-test"
    fake_client = Mock()
    fake_client.models.generate_content.side_effect = ClientError(
        429,
        {"error": {"status": "RESOURCE_EXHAUSTED", "message": f"quota key={api_key}"}},
    )
    with patch("ai.llm.gemini_client.genai.Client", return_value=fake_client) as factory:
        with pytest.raises(GeminiClientError) as error:
            generate_text("private session text", settings=Settings(api_key, "test-model"))

    factory.assert_called_once()
    fake_client.models.generate_content.assert_called_once()
    assert "HTTP 429 RESOURCE_EXHAUSTED" in str(error.value)
    assert "no retry attempted" in str(error.value)
    assert api_key not in str(error.value)
    assert "private session text" not in str(error.value)
