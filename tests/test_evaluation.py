import json
from pathlib import Path

import pytest

import ai.evaluation.evaluate as evaluation_module
from ai.core.config import Settings
from ai.evaluation.evaluate import (
    CATEGORIES,
    EvaluationDataError,
    _metric_values,
    evaluate_predictions,
    load_dataset,
    load_saved_predictions,
    run_gemini,
)
from ai.extraction.reasoning_extractor import ReasoningExtractionError
from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem


DATA_DIRECTORY = Path(__file__).parents[1] / "ai" / "evaluation"


def test_dataset_has_at_least_fifteen_valid_examples_and_source_evidence():
    examples = load_dataset(DATA_DIRECTORY / "dataset.json")

    assert len(examples) >= 15
    assert len({example["id"] for example in examples}) == len(examples)
    for example in examples:
        expected = ReasoningExtraction.model_validate(example["expected"])
        items = [expected.problem] if expected.problem else []
        for category in CATEGORIES[1:]:
            items.extend(getattr(expected, category))
        assert all(item.evidence in example["session"] for item in items)


def test_saved_offline_outputs_are_valid_schema_instances():
    examples = load_dataset(DATA_DIRECTORY / "dataset.json")
    predictions = load_saved_predictions(DATA_DIRECTORY / "saved_predictions.json")

    assert set(predictions) == {example["id"] for example in examples}
    assert all(isinstance(value, ReasoningExtraction) for value in predictions.values())


def test_metric_counts_only_matching_text_and_evidence_and_normalizes_spacing_case():
    expected = [ReasoningItem(text="Use BFS", evidence="I chose BFS")]
    predicted = [
        ReasoningItem(text=" use   bfs ", evidence="I CHOSE bfs"),
        ReasoningItem(text="Use DFS", evidence="I chose BFS"),
    ]

    scores = _metric_values(expected, predicted)

    assert scores == {"precision": 0.5, "recall": 1.0, "f1": pytest.approx(2 / 3)}


def test_absent_categories_are_empty_and_have_not_applicable_scores():
    examples = load_dataset(DATA_DIRECTORY / "dataset.json")
    example = next(row for row in examples if row["id"] == "yellow-leaves")
    expected = ReasoningExtraction.model_validate(example["expected"])

    assert expected.decisions == []
    assert expected.justifications == []
    assert expected.alternatives_considered == []
    assert expected.assumptions == []
    assert expected.problem is not None

    report = evaluate_predictions([example], {example["id"]: expected})
    assert report["categories"]["decisions"] == {
        "precision": None, "recall": None, "f1": None
    }

    unresolved = next(row for row in examples if row["id"] == "travel-options-unresolved")
    unresolved_expected = ReasoningExtraction.model_validate(unresolved["expected"])
    assert unresolved_expected.problem is None
    assert unresolved_expected.decisions == []


def test_missing_prediction_counts_as_a_miss_when_reference_has_an_item():
    examples = load_dataset(DATA_DIRECTORY / "dataset.json")
    example = next(row for row in examples if row["id"] == "graph-bfs")

    report = evaluate_predictions([example], {})

    assert report["prediction_errors"] == 1
    assert report["categories"]["decisions"]["recall"] == 0.0
    assert report["examples_evaluated"] == 1
    assert report["successful_examples"] == 0


def _empty_extraction():
    return ReasoningExtraction(
        problem=None, decisions=[], justifications=[],
        alternatives_considered=[], assumptions=[]
    )


def test_metrics_match_within_each_session_not_across_sessions():
    first_expected = ReasoningItem(text="Use BFS", evidence="I chose BFS")
    second_expected = ReasoningItem(text="Use DFS", evidence="I chose DFS")
    examples = [
        {"id": "first", "expected": {**_empty_extraction().model_dump(), "decisions": [first_expected.model_dump()]}},
        {"id": "second", "expected": {**_empty_extraction().model_dump(), "decisions": [second_expected.model_dump()]}},
    ]
    # Each prediction is supported by the other session's reference only.
    first_prediction = _empty_extraction().model_copy(update={"decisions": [second_expected]})
    second_prediction = _empty_extraction().model_copy(update={"decisions": [first_expected]})
    report = evaluate_predictions(examples, {"first": first_prediction, "second": second_prediction})
    assert report["categories"]["decisions"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_partial_prediction_failures_count_successes_and_score_successful_items():
    example = load_dataset(DATA_DIRECTORY / "dataset.json")
    pair = [next(row for row in example if row["id"] == identifier) for identifier in ("graph-bfs", "yellow-leaves")]
    prediction = ReasoningExtraction.model_validate(pair[0]["expected"])
    report = evaluate_predictions(pair, {"graph-bfs": prediction, "yellow-leaves": None})
    assert report["examples_evaluated"] == 2
    assert report["successful_examples"] == 1
    assert report["prediction_errors"] == 1
    assert report["categories"]["decisions"]["f1"] == 1.0


def test_empty_expected_and_predicted_categories_are_not_applicable():
    assert _metric_values([], []) == {"precision": None, "recall": None, "f1": None}
    item = ReasoningItem(text="Extra", evidence="some quote")
    assert _metric_values([], [item]) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    assert _metric_values([item], []) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_live_runner_keeps_sanitized_error_summary_for_each_failed_example(
    monkeypatch, capsys
):
    secret = "local-api-key-do-not-print"
    example = {
        "id": "sample-case",
        "session": "A sample session.",
        "expected": {
            "problem": None,
            "decisions": [],
            "justifications": [],
            "alternatives_considered": [],
            "assumptions": [],
        },
    }
    monkeypatch.setattr(
        evaluation_module, "get_settings", lambda: Settings(secret, "test-model")
    )

    def fake_extractor(_session, *, settings):
        assert settings.gemini_api_key == secret
        raise ReasoningExtractionError(
            f"Gemini text generation failed (ClientError HTTP 404: api_key={secret})"
        )

    monkeypatch.setattr(evaluation_module, "extract_reasoning", fake_extractor)
    predictions, failures = run_gemini([example])
    report = evaluate_predictions([example], predictions)
    report["failure_summaries"] = failures
    evaluation_module._print_report(report, "mocked")

    assert predictions["sample-case"] is None
    assert "api_key=[REDACTED]" in failures["sample-case"]
    assert secret not in failures["sample-case"]
    printed = capsys.readouterr().out
    assert "sample-case" in printed
    assert "HTTP 404" in printed
    assert secret not in printed


def test_invalid_dataset_is_reported_clearly(monkeypatch):
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding=None: json.dumps({"examples": [{"id": "bad"}]}),
    )

    with pytest.raises(EvaluationDataError, match="valid reasoning evaluation dataset"):
        load_dataset(Path("invalid.json"))
