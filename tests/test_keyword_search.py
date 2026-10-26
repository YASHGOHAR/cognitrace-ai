import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from ai.retrieval.keyword_search import search_sessions
from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import save_session


@pytest.fixture
def database_path():
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "work") as folder:
        yield Path(folder) / "sessions.db"


def reasoning(*, decision_text=None, decision_evidence=None, problem=None):
    return ReasoningExtraction(
        problem=problem,
        decisions=(
            [ReasoningItem(text=decision_text, evidence=decision_evidence)]
            if decision_text is not None
            else []
        ),
        justifications=[],
        alternatives_considered=[],
        assumptions=[],
    )


def save(database_path, session_id, text, result=None):
    return save_session(
        text, result or reasoning(), session_id=session_id, db_path=database_path
    )


def test_search_is_case_insensitive(database_path):
    save(database_path, "case", "The GRAPH uses BFS.")

    results = search_sessions("graph bfs", db_path=database_path)

    assert [item.session_id for item in results] == ["case"]


def test_search_ignores_punctuation_and_repeated_whitespace(database_path):
    save(database_path, "punctuation", "A graph,   with BFS!")

    results = search_sessions("graph---with    bfs", db_path=database_path)

    assert [item.session_id for item in results] == ["punctuation"]


def test_search_matches_extracted_reasoning_fields(database_path):
    source = "I will use a queue."
    result = reasoning(decision_text="Use a FIFO data structure", decision_evidence=source)
    save(database_path, "structured", source, result)

    results = search_sessions("FIFO", db_path=database_path)

    assert len(results) == 1
    assert results[0].session_id == "structured"
    assert results[0].relevance_score == 2
    assert results[0].reasoning.decisions[0].text == "Use a FIFO data structure"
    assert results[0].session_text == source


def test_more_distinct_matching_terms_rank_higher(database_path):
    save(database_path, "one-term", "BFS traversal", reasoning())
    source = "BFS shortest path graph"
    result = reasoning(
        decision_text="Use BFS for shortest path",
        decision_evidence=source,
        problem=ReasoningItem(text="Find a path in graph", evidence="graph"),
    )
    save(database_path, "many-terms", source, result)

    results = search_sessions("BFS shortest path graph", db_path=database_path)

    assert [item.session_id for item in results] == ["many-terms", "one-term"]
    assert results[0].relevance_score > results[1].relevance_score


def test_repeated_term_in_one_field_counts_once(database_path):
    source = "queue queue queue"
    result = reasoning(decision_text="queue queue", decision_evidence=source)
    save(database_path, "repeated", source, result)

    results = search_sessions("queue", db_path=database_path)

    # One source-text point plus one decision-field match worth two points.
    assert results[0].relevance_score == 3


def test_ties_use_newest_timestamp_then_session_id(database_path):
    save(database_path, "older", "BFS", reasoning())
    save(database_path, "newer-b", "BFS", reasoning())
    save(database_path, "newer-a", "BFS", reasoning())
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                "UPDATE reasoning_sessions SET created_at = ? WHERE session_id = ?",
                ("2026-01-01T00:00:00+00:00", "older"),
            )
            for identifier in ("newer-a", "newer-b"):
                connection.execute(
                    "UPDATE reasoning_sessions SET created_at = ? WHERE session_id = ?",
                    ("2026-01-02T00:00:00+00:00", identifier),
                )

    results = search_sessions("BFS", db_path=database_path)

    assert [item.session_id for item in results] == ["newer-b", "newer-a", "older"]


def test_result_limit_is_applied_after_ranking(database_path):
    save(database_path, "a", "BFS")
    save(database_path, "b", "BFS graph")

    results = search_sessions("BFS graph", limit=1, db_path=database_path)

    assert [item.session_id for item in results] == ["b"]


@pytest.mark.parametrize("query", ["", "   ", "the and for"])
def test_empty_or_stop_word_only_queries_return_no_results(database_path, query):
    save(database_path, "existing", "A graph uses BFS")
    assert search_sessions(query, db_path=database_path) == []


def test_no_matches_and_empty_database_return_no_results(database_path):
    assert search_sessions("BFS", db_path=database_path) == []
    save(database_path, "existing", "A graph uses BFS")
    assert search_sessions("Dijkstra", db_path=database_path) == []


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_invalid_limits_are_rejected(database_path, limit):
    with pytest.raises(ValueError, match="positive integer"):
        search_sessions("BFS", limit=limit, db_path=database_path)


def test_search_never_creates_a_gemini_client(database_path):
    save(database_path, "offline", "A graph uses BFS")
    with patch("ai.llm.gemini_client.genai.Client") as client:
        results = search_sessions("graph", db_path=database_path)
    assert results
    client.assert_not_called()
