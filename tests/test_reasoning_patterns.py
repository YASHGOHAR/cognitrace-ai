from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from ai.patterns.reasoning_patterns import detect_reasoning_patterns
from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import save_session


@pytest.fixture
def database_path():
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "work") as folder:
        yield Path(folder) / "sessions.db"


def extraction(decision_texts=(), evidence_texts=None):
    evidence_texts = evidence_texts or decision_texts
    return ReasoningExtraction(
        problem=None,
        decisions=[
            ReasoningItem(text=text, evidence=evidence)
            for text, evidence in zip(decision_texts, evidence_texts)
        ],
        justifications=[],
        alternatives_considered=[],
        assumptions=[],
    )


def add(database_path, session_id, source, decision_texts=(), evidence_texts=None):
    save_session(
        source,
        extraction(decision_texts, evidence_texts),
        session_id=session_id,
        db_path=database_path,
    )


def add_two_supporting_sessions(database_path):
    source_a = "I choose a queue to explore the graph level by level."
    source_b = "I use a queue for graph traversal, one level at a time."
    add(
        database_path,
        "session-a",
        source_a,
        ["Use a queue to explore graph level by level"],
        [source_a],
    )
    add(
        database_path,
        "session-b",
        source_b,
        ["Use queue for graph traversal level at a time"],
        [source_b],
    )


def test_detects_similar_reasoning_supported_by_two_distinct_sessions(database_path):
    add_two_supporting_sessions(database_path)

    analysis = detect_reasoning_patterns(db_path=database_path)

    assert not analysis.insufficient_evidence
    assert analysis.sessions_considered == 2
    assert len(analysis.patterns) == 1
    pattern = analysis.patterns[0]
    assert pattern.category == "decisions"
    assert pattern.distinct_session_count == 2
    assert pattern.supporting_session_ids == ("session-a", "session-b")
    assert "Possible recurring decision" in pattern.description
    assert pattern.reflection_question.endswith("?")


def test_repeated_wording_inside_one_session_does_not_count_as_recurrence(database_path):
    source = "I use a queue to explore the graph level by level."
    statement = "Use a queue to explore graph level by level"
    add(database_path, "only-session", source, [statement, statement], [source, source])

    analysis = detect_reasoning_patterns(db_path=database_path)

    assert analysis.patterns == ()
    assert analysis.insufficient_evidence


def test_pattern_evidence_is_exact_and_ids_refer_to_stored_sessions(database_path):
    add_two_supporting_sessions(database_path)

    pattern = detect_reasoning_patterns(db_path=database_path).patterns[0]

    assert set(pattern.supporting_session_ids) == {"session-a", "session-b"}
    assert {item.session_id for item in pattern.supporting_evidence} == {
        "session-a", "session-b"
    }
    for item in pattern.supporting_evidence:
        assert item.evidence in {"I choose a queue to explore the graph level by level.", "I use a queue for graph traversal, one level at a time."}
        assert item.text


def test_related_different_approach_is_returned_as_counterexample(database_path):
    add_two_supporting_sessions(database_path)
    counterexample = "Avoid queue when processing graph edges by priority."
    add(
        database_path,
        "session-c",
        counterexample,
        ["Avoid queue when processing graph edges by priority"],
        [counterexample],
    )

    analysis = detect_reasoning_patterns(db_path=database_path)

    assert len(analysis.patterns) == 1
    pattern = analysis.patterns[0]
    assert len(pattern.counterexamples) == 1
    assert pattern.counterexamples[0].session_id == "session-c"
    assert pattern.counterexamples[0].evidence == counterexample


def test_one_supporting_session_returns_insufficient_evidence(database_path):
    source = "I use a queue to explore the graph level by level."
    add(database_path, "one", source, ["Use a queue to explore graph level by level"], [source])

    analysis = detect_reasoning_patterns(db_path=database_path)

    assert analysis.patterns == ()
    assert analysis.insufficient_evidence


def test_unrelated_sessions_are_not_grouped(database_path):
    source_a = "I use a queue for graph traversal level by level."
    source_b = "I check the calendar before planning a trip."
    add(database_path, "graph", source_a, ["Use queue for graph traversal level by level"], [source_a])
    add(database_path, "travel", source_b, ["Check calendar before planning the trip"], [source_b])

    analysis = detect_reasoning_patterns(db_path=database_path)

    assert analysis.patterns == ()
    assert analysis.insufficient_evidence


def test_results_are_deterministic(database_path):
    add_two_supporting_sessions(database_path)

    first = detect_reasoning_patterns(db_path=database_path)
    second = detect_reasoning_patterns(db_path=database_path)

    assert first == second


def test_optional_keyword_query_uses_existing_retrieval_to_scope_sessions(database_path):
    add_two_supporting_sessions(database_path)
    source = "I check the calendar before planning a trip."
    add(database_path, "travel", source, ["Check calendar before planning the trip"], [source])

    analysis = detect_reasoning_patterns("graph queue", db_path=database_path)

    assert analysis.sessions_considered == 2
    assert len(analysis.patterns) == 1


def test_analysis_never_calls_gemini(database_path):
    add_two_supporting_sessions(database_path)
    with patch("ai.llm.gemini_client.genai.Client") as client:
        analysis = detect_reasoning_patterns(db_path=database_path)

    assert analysis.patterns
    client.assert_not_called()


def test_repeated_single_keyword_is_not_considered_similar_reasoning(database_path):
    source_a = "I choose BFS to find shortest paths."
    source_b = "I avoid BFS when the graph has weighted edges."
    add(database_path, "a", source_a, ["Choose BFS for shortest paths"], [source_a])
    add(database_path, "b", source_b, ["Avoid BFS for weighted edges"], [source_b])

    analysis = detect_reasoning_patterns(db_path=database_path)

    assert analysis.patterns == ()
    assert analysis.insufficient_evidence
