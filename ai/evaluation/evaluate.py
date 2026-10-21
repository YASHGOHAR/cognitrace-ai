"""Score reasoning extractions against hand-written references."""

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from ai.core.config import get_settings
from ai.extraction.reasoning_extractor import ReasoningExtractionError, extract_reasoning
from ai.llm.gemini_client import sanitize_error_detail
from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem


DATA_DIRECTORY = Path(__file__).parent
CATEGORIES = (
    "problem",
    "decisions",
    "justifications",
    "alternatives_considered",
    "assumptions",
)


class EvaluationDataError(ValueError):
    """Raised when an evaluation file does not match the expected format."""


def load_dataset(path: Path = DATA_DIRECTORY / "dataset.json") -> list[dict[str, Any]]:
    """Load and validate reference examples, including source evidence quotes."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        examples = payload["examples"]
        if not isinstance(examples, list):
            raise ValueError
        seen_ids: set[str] = set()
        for example in examples:
            identifier = example["id"]
            session = example["session"]
            if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
                raise ValueError
            if not isinstance(session, str) or not session.strip():
                raise ValueError
            seen_ids.add(identifier)
            expected = ReasoningExtraction.model_validate(example["expected"])
            for item in _items(expected):
                if item.evidence not in session:
                    raise ValueError
        return examples
    except (OSError, KeyError, TypeError, ValueError):
        raise EvaluationDataError(
            f"Could not load a valid reasoning evaluation dataset from {path}."
        ) from None


def _items(extraction: ReasoningExtraction, category: str | None = None) -> list[ReasoningItem]:
    if category == "problem":
        return [extraction.problem] if extraction.problem is not None else []
    if category:
        return getattr(extraction, category)
    return [item for name in CATEGORIES for item in _items(extraction, name)]


def _normalized_item(item: ReasoningItem) -> tuple[str, str]:
    """Ignore case and repeated whitespace, while preserving all wording/punctuation."""
    normalize = lambda value: " ".join(value.casefold().split())
    return normalize(item.text), normalize(item.evidence)


def _metric_values(expected: list[ReasoningItem], predicted: list[ReasoningItem]) -> dict[str, float | None]:
    expected_counts = Counter(_normalized_item(item) for item in expected)
    predicted_counts = Counter(_normalized_item(item) for item in predicted)
    true_positives = sum((expected_counts & predicted_counts).values())
    false_positives = sum(predicted_counts.values()) - true_positives
    false_negatives = sum(expected_counts.values()) - true_positives

    if not (true_positives or false_positives or false_negatives):
        return {"precision": None, "recall": None, "f1": None}

    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_predictions(
    examples: list[dict[str, Any]],
    predictions: dict[str, ReasoningExtraction | None],
) -> dict[str, Any]:
    """Compute exact-item micro precision, recall, and F1 per output category.

    None predictions count as no extracted items. Case and whitespace are
    normalized; wording and evidence still need to match, so unsupported or
    invented items do not count as correct.
    """
    # Match inside each session first. Pooling items before matching can let a
    # prediction from one session incorrectly satisfy another session's target.
    totals = {category: Counter() for category in CATEGORIES}
    errors = 0
    for example in examples:
        expected = ReasoningExtraction.model_validate(example["expected"])
        predicted = predictions.get(example["id"])
        if predicted is None:
            errors += 1
            predicted = ReasoningExtraction(
                problem=None,
                decisions=[],
                justifications=[],
                alternatives_considered=[],
                assumptions=[],
            )
        for category in CATEGORIES:
            expected_counts = Counter(
                _normalized_item(item) for item in _items(expected, category)
            )
            predicted_counts = Counter(
                _normalized_item(item) for item in _items(predicted, category)
            )
            true_positives = sum((expected_counts & predicted_counts).values())
            totals[category]["tp"] += true_positives
            totals[category]["fp"] += sum(predicted_counts.values()) - true_positives
            totals[category]["fn"] += sum(expected_counts.values()) - true_positives

    category_scores = {}
    for category, counts in totals.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        if not (tp or fp or fn):
            category_scores[category] = {
                "precision": None, "recall": None, "f1": None
            }
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        category_scores[category] = {
            "precision": precision, "recall": recall, "f1": f1
        }

    return {
        "examples_evaluated": len(examples),
        "successful_examples": len(examples) - errors,
        "prediction_errors": errors,
        "categories": category_scores,
    }


def load_saved_predictions(path: Path = DATA_DIRECTORY / "saved_predictions.json") -> dict[str, ReasoningExtraction]:
    """Read deterministic offline fixtures (not recorded Gemini responses)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        predictions = {
            row["id"]: ReasoningExtraction.model_validate(row["output"])
            for row in payload["predictions"]
        }
        return predictions
    except (OSError, KeyError, TypeError, ValueError):
        raise EvaluationDataError(f"Could not load saved predictions from {path}.") from None


def run_gemini(
    examples: list[dict[str, Any]],
) -> tuple[dict[str, ReasoningExtraction | None], dict[str, str]]:
    """Call Gemini once per example, keeping sanitized failure summaries."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise EvaluationDataError(
            "GEMINI_API_KEY is not configured. Set it in .env before using --mode gemini."
        )
    predictions: dict[str, ReasoningExtraction | None] = {}
    failures: dict[str, str] = {}
    for example in examples:
        try:
            predictions[example["id"]] = extract_reasoning(example["session"], settings=settings)
        except ReasoningExtractionError as exc:
            predictions[example["id"]] = None
            failures[example["id"]] = sanitize_error_detail(
                str(exc), settings.gemini_api_key
            )
    return predictions, failures


def _print_report(report: dict[str, Any], mode: str) -> None:
    print(f"Mode: {mode}")
    print(f"Examples evaluated: {report['examples_evaluated']}")
    print(f"Successful examples: {report['successful_examples']}")
    print(f"Prediction errors: {report['prediction_errors']}")
    print("Category                  Precision   Recall      F1")
    for category, scores in report["categories"].items():
        shown = ["N/A" if scores[key] is None else f"{scores[key]:.3f}" for key in ("precision", "recall", "f1")]
        print(f"{category:26} {shown[0]:>9} {shown[1]:>9} {shown[2]:>9}")
    failures = report.get("failure_summaries", {})
    if failures:
        print("Failure summaries (sanitized):")
        for example_id, summary in failures.items():
            print(f"- {example_id}: {summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Cognitrace reasoning extraction.")
    parser.add_argument(
        "--mode",
        choices=("saved", "gemini"),
        default="saved",
        help="saved uses offline fixtures; gemini makes one real API request per session",
    )
    args = parser.parse_args()
    examples = load_dataset()
    if args.mode == "saved":
        predictions = load_saved_predictions()
        failures = {}
        mode_label = "saved offline fixtures (not live Gemini results)"
    else:
        predictions, failures = run_gemini(examples)
        mode_label = "live Gemini"
    report = evaluate_predictions(examples, predictions)
    report["failure_summaries"] = failures
    _print_report(report, mode_label)


if __name__ == "__main__":
    main()
