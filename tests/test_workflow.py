from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from ai.patterns.reasoning_patterns import detect_reasoning_patterns
from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import list_sessions, save_session
from ai.workflow import ReasoningWorkflowError, process_reasoning_session


@pytest.fixture
def database_path():
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "work") as folder:
        yield Path(folder) / "sessions.db"


def reasoning(text, evidence):
    return ReasoningExtraction(
        problem=None,
        decisions=[ReasoningItem(text=text, evidence=evidence)],
        justifications=[],
        alternatives_considered=[],
        assumptions=[],
    )


def seed_history(database_path):
    rows = [
        (
            "history-a",
            "I choose a queue to explore the graph level by level.",
            "Use a queue to explore graph level by level",
        ),
        (
            "history-b",
            "I use a queue for graph traversal, one level at a time.",
            "Use queue for graph traversal level at a time",
        ),
    ]
    for session_id, source, decision in rows:
        save_session(
            source,
            reasoning(decision, source),
            session_id=session_id,
            db_path=database_path,
        )


def test_successful_workflow_extracts_once_saves_retrieves_and_finds_patterns(database_path):
    seed_history(database_path)
    current_text = "I choose a queue to explore this graph level by level."
    extracted = reasoning("Use a queue to explore graph level by level", current_text)
    with (
        patch("ai.workflow.extract_reasoning", return_value=extracted) as extractor,
        patch("ai.llm.gemini_client.genai.Client") as gemini_client,
    ):
        result = process_reasoning_session(current_text, db_path=database_path)

    extractor.assert_called_once_with(current_text, settings=None)
    gemini_client.assert_not_called()
    assert result.session_id
    assert result.reasoning == extracted
    assert {item.session_id for item in result.relevant_previous_sessions} == {
        "history-a", "history-b"
    }
    assert len(result.detected_patterns) == 1
    assert result.detected_patterns[0].supporting_session_ids == ("history-a", "history-b")
    assert result.session_id not in result.detected_patterns[0].supporting_session_ids
    assert not result.insufficient_evidence
    assert result.previous_sessions_considered == 2
    assert len(list_sessions(db_path=database_path)) == 3
    payload = json.loads(result.to_json())
    assert payload == result.to_dict()
    assert payload["reasoning"]["decisions"][0]["text"] == extracted.decisions[0].text
    assert payload["detected_patterns"][0]["supporting_session_ids"] == [
        "history-a", "history-b"
    ]


def test_documented_workflow_public_signature():
    parameters = signature(process_reasoning_session).parameters

    assert list(parameters) == [
        "session_text", "db_path", "settings", "retrieval_limit", "owner_id", "store"
    ]
    assert parameters["retrieval_limit"].default == 10
    assert parameters["store"].default is None
    payload = json.loads(result.to_json())
    assert payload == result.to_dict()
    assert payload["reasoning"]["decisions"][0]["text"] == extracted.decisions[0].text
    assert payload["detected_patterns"][0]["supporting_session_ids"] == [
        "history-a", "history-b"
    ]


def test_documented_workflow_public_signature():
    parameters = signature(process_reasoning_session).parameters

    assert list(parameters) == [
        "session_text", "db_path", "settings", "retrieval_limit", "owner_id", "store"
    ]
    assert parameters["retrieval_limit"].default == 10
    assert parameters["store"].default is None


def test_extraction_failure_does_not_save_a_session(database_path):
    source = "private source text that must not appear in errors"
    with patch(
        "ai.workflow.extract_reasoning",
        side_effect=RuntimeError("provider detail and secret data"),
    ):
        with pytest.raises(ReasoningWorkflowError) as error:
            process_reasoning_session(source, db_path=database_path)

    assert error.value.stage == "extraction"
    assert not error.value.session_saved
    assert source not in str(error.value)
    assert "secret data" not in str(error.value)
    assert list_sessions(db_path=database_path) == []


def test_no_historical_matches_returns_empty_history_and_insufficient_status(database_path):
    current_text = "I chose a queue to explore this graph level by level."
    with patch(
        "ai.workflow.extract_reasoning",
        return_value=reasoning("Use a queue for graph traversal level by level", current_text),
    ):
        result = process_reasoning_session(current_text, db_path=database_path)

    assert result.relevant_previous_sessions == ()
    assert result.detected_patterns == ()
    assert result.insufficient_evidence
    assert result.previous_sessions_considered == 0


def test_one_relevant_previous_session_is_not_enough_for_pattern(database_path):
    prior = "I choose a queue to explore the graph level by level."
    save_session(
        prior,
        reasoning("Use a queue to explore graph level by level", prior),
        session_id="one-history",
        db_path=database_path,
    )
    current_text = "I choose a queue for graph traversal, one level at a time."
    with patch(
        "ai.workflow.extract_reasoning",
        return_value=reasoning("Use queue for graph traversal level at a time", current_text),
    ):
        result = process_reasoning_session(current_text, db_path=database_path)

    assert [item.session_id for item in result.relevant_previous_sessions] == ["one-history"]
    assert result.detected_patterns == ()
    assert result.insufficient_evidence


def test_new_session_is_never_returned_as_its_own_historical_match_or_pattern_evidence(database_path):
    seed_history(database_path)
    current_text = "I choose a queue to explore this graph level by level."
    with patch(
        "ai.workflow.extract_reasoning",
        return_value=reasoning("Use a queue to explore graph level by level", current_text),
    ):
        result = process_reasoning_session(current_text, db_path=database_path)

    assert all(item.session_id != result.session_id for item in result.relevant_previous_sessions)
    for pattern in result.detected_patterns:
        assert result.session_id not in pattern.supporting_session_ids
        assert all(item.session_id != result.session_id for item in pattern.supporting_evidence)


def test_workflow_uses_the_configured_database_path(database_path):
    session_text = "I choose a queue."
    extracted = reasoning("Use a queue", session_text)
    with patch("ai.workflow.extract_reasoning", return_value=extracted):
        result = process_reasoning_session(session_text, db_path=database_path)

    assert database_path.exists()
    assert any(item.session_id == result.session_id for item in list_sessions(db_path=database_path))


def test_detector_failure_reports_saved_session_id_without_echoing_session(database_path):
    source = "sensitive session text"
    with (
        patch("ai.workflow.extract_reasoning", return_value=reasoning("Use cache safely", source)),
        patch("ai.workflow.detect_reasoning_patterns", side_effect=RuntimeError(source)),
    ):
        with pytest.raises(ReasoningWorkflowError) as error:
            process_reasoning_session(source, db_path=database_path)

    assert error.value.stage == "pattern_detection"
    assert error.value.session_saved
    assert error.value.session_id
    assert source not in str(error.value)
    assert len(list_sessions(db_path=database_path)) == 1


@pytest.mark.parametrize("session_text", ["", " ", None])
def test_empty_session_is_rejected_before_extraction(database_path, session_text):
    with patch("ai.workflow.extract_reasoning") as extractor:
        with pytest.raises(ValueError, match="non-empty"):
            process_reasoning_session(session_text, db_path=database_path)
    extractor.assert_not_called()
import json
from inspect import signature
import json
from inspect import signature
