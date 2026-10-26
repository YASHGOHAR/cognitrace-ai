import json
from unittest.mock import patch

import pytest

from ai.core.config import Settings
from ai.extraction.reasoning_extractor import (
    ReasoningExtractionError,
    extract_reasoning,
)
from ai.llm.gemini_client import GeminiClientError


SETTINGS = Settings(gemini_api_key="test-key", gemini_model="test-model")
SESSION = (
    "I need to find the shortest path in an unweighted graph. "
    "I considered Dijkstra, but I chose BFS because every edge has equal cost. "
    "I will use a queue to explore nodes level by level."
)


def valid_output():
    return {
        "problem": {
            "text": "Find the shortest path in an unweighted graph.",
            "evidence": "find the shortest path in an unweighted graph",
        },
        "decisions": [{"text": "Use BFS.", "evidence": "I chose BFS"}],
        "justifications": [
            {"text": "Every edge has equal cost.", "evidence": "every edge has equal cost"}
        ],
        "alternatives_considered": [
            {"text": "Dijkstra.", "evidence": "I considered Dijkstra"}
        ],
        "assumptions": [],
    }


def test_extract_reasoning_returns_validated_items_with_source_evidence():
    output = json.dumps(valid_output())
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=output) as model:
        result = extract_reasoning(SESSION, settings=SETTINGS)

    assert result.problem.text == "Find the shortest path in an unweighted graph."
    assert result.decisions[0].text == "Use BFS."
    assert result.justifications[0].evidence == "every edge has equal cost"
    assert result.alternatives_considered[0].text == "Dijkstra."
    assert result.assumptions == []
    model.assert_called_once()
    prompt = model.call_args.args[0]
    assert SESSION in prompt
    assert "Return only valid JSON" in prompt


def test_extract_reasoning_accepts_a_standard_json_markdown_fence():
    output = f"```json\n{json.dumps(valid_output())}\n```"
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=output):
        result = extract_reasoning(SESSION, settings=SETTINGS)

    assert result.decisions[0].text == "Use BFS."


def test_extract_reasoning_accepts_null_problem():
    output = {
        "problem": None,
        "decisions": [],
        "justifications": [],
        "alternatives_considered": [],
        "assumptions": [],
    }
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=json.dumps(output)):
        result = extract_reasoning("I will start now.", settings=SETTINGS)
    assert result.problem is None


def test_extract_reasoning_accepts_empty_problem_object():
    output = {
        "problem": {"text": None, "evidence": None},
        "decisions": [],
        "justifications": [],
        "alternatives_considered": [],
        "assumptions": [],
    }
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=json.dumps(output)):
        result = extract_reasoning("I will start now.", settings=SETTINGS)
    assert result.problem is None


@pytest.mark.parametrize("bad_problem", [
    {"text": ["not", "text"], "evidence": "I will start"},
    {"text": "Start", "evidence": {"quote": "I will start"}},
])
def test_extract_reasoning_reports_invalid_problem_field_types(bad_problem):
    output = {
        "problem": bad_problem,
        "decisions": [],
        "justifications": [],
        "alternatives_considered": [],
        "assumptions": [],
    }
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=json.dumps(output)):
        with pytest.raises(ReasoningExtractionError) as error:
            extract_reasoning("I will start now.", settings=SETTINGS)
    assert error.value.category == "schema_validation"
    assert "problem.text" in str(error.value) or "problem.evidence" in str(error.value)
    assert "I will start now." not in str(error.value)


@pytest.mark.parametrize("session_text", ["", "   ", None])
def test_extract_reasoning_rejects_empty_input_without_calling_model(session_text):
    with patch("ai.extraction.reasoning_extractor.generate_text") as model:
        with pytest.raises(ValueError, match="non-empty"):
            extract_reasoning(session_text, settings=SETTINGS)
    model.assert_not_called()


def test_extract_reasoning_reports_malformed_json_without_echoing_response():
    sensitive_response = 'not json containing "private session details"'
    with patch(
        "ai.extraction.reasoning_extractor.generate_text", return_value=sensitive_response
    ):
        with pytest.raises(ReasoningExtractionError, match="malformed JSON") as error:
            extract_reasoning(SESSION, settings=SETTINGS)

    assert error.value.category == "malformed_json"
    assert "line 1, column" in str(error.value)
    assert "private session details" not in str(error.value)


def test_extract_reasoning_reports_missing_schema_fields_without_echoing_input():
    incomplete_output = json.dumps(
        {"decisions": [{"text": "private session details", "evidence": "some quote"}]}
    )
    with patch(
        "ai.extraction.reasoning_extractor.generate_text", return_value=incomplete_output
    ):
        with pytest.raises(ReasoningExtractionError, match="did not match the reasoning schema") as error:
            extract_reasoning(SESSION, settings=SETTINGS)

    assert error.value.category == "schema_validation"
    assert "problem: missing (Field required)" in str(error.value)
    assert "private session details" not in str(error.value)


def test_extract_reasoning_rejects_evidence_not_found_in_session():
    output = valid_output()
    output["decisions"][0]["evidence"] = "I selected BFS after benchmarking"
    with patch(
        "ai.extraction.reasoning_extractor.generate_text", return_value=json.dumps(output)
    ):
        with pytest.raises(ReasoningExtractionError, match="does not exactly match"):
            extract_reasoning(SESSION, settings=SETTINGS)


def test_extract_reasoning_rejects_empty_evidence_instead_of_treating_it_as_a_quote():
    output = valid_output()
    output["decisions"][0]["evidence"] = ""
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=json.dumps(output)):
        with pytest.raises(ReasoningExtractionError, match="does not exactly match"):
            extract_reasoning(SESSION, settings=SETTINGS)


def test_extract_reasoning_does_not_trim_or_substitute_evidence():
    output = valid_output()
    output["decisions"][0]["evidence"] = "  I chose BFS"
    with patch("ai.extraction.reasoning_extractor.generate_text", return_value=json.dumps(output)):
        with pytest.raises(ReasoningExtractionError, match="does not exactly match"):
            extract_reasoning(SESSION, settings=SETTINGS)


def test_extract_reasoning_wraps_provider_failure_clearly():
    with patch(
        "ai.extraction.reasoning_extractor.generate_text",
        side_effect=GeminiClientError("Gemini text generation failed."),
    ):
        with pytest.raises(ReasoningExtractionError, match="Could not extract reasoning"):
            extract_reasoning(SESSION, settings=SETTINGS)
