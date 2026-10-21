"""End-to-end orchestration for extracting and reflecting on one session."""

from dataclasses import dataclass
import json
from pathlib import Path

from ai.core.config import Settings
from ai.extraction.reasoning_extractor import extract_reasoning
from ai.patterns.reasoning_patterns import ReasoningPattern, detect_reasoning_patterns
from ai.retrieval.keyword_search import SearchResult, search_sessions
from ai.schemas.reasoning import ReasoningExtraction
from ai.storage.session_store import save_session


DEFAULT_RETRIEVAL_LIMIT = 10


class ReasoningWorkflowError(RuntimeError):
    """A safe workflow failure with its stage and persistence status."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        session_saved: bool,
        session_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.session_saved = session_saved
        self.session_id = session_id


@dataclass(frozen=True)
class ReasoningWorkflowResult:
    """Extraction, saved ID, relevant history, and supported pattern findings."""

    session_id: str
    reasoning: ReasoningExtraction
    relevant_previous_sessions: tuple[SearchResult, ...]
    detected_patterns: tuple[ReasoningPattern, ...]
    insufficient_evidence: bool
    previous_sessions_considered: int

    def to_dict(self) -> dict[str, object]:
        """Return a plain JSON-ready dictionary using the Pydantic schema dump."""
        return {
            "session_id": self.session_id,
            "reasoning": self.reasoning.model_dump(mode="json"),
            "relevant_previous_sessions": [
                {
                    "session_id": session.session_id,
                    "timestamp": session.timestamp,
                    "relevance_score": session.relevance_score,
                    "session_text": session.session_text,
                    "reasoning": session.reasoning.model_dump(mode="json"),
                }
                for session in self.relevant_previous_sessions
            ],
            "detected_patterns": [
                {
                    "description": pattern.description,
                    "category": pattern.category,
                    "supporting_session_ids": list(pattern.supporting_session_ids),
                    "supporting_evidence": [
                        {
                            "session_id": item.session_id,
                            "category": item.category,
                            "text": item.text,
                            "evidence": item.evidence,
                        }
                        for item in pattern.supporting_evidence
                    ],
                    "distinct_session_count": pattern.distinct_session_count,
                    "counterexamples": [
                        {
                            "session_id": item.session_id,
                            "category": item.category,
                            "text": item.text,
                            "evidence": item.evidence,
                        }
                        for item in pattern.counterexamples
                    ],
                    "reflection_question": pattern.reflection_question,
                }
                for pattern in self.detected_patterns
            ],
            "insufficient_evidence": self.insufficient_evidence,
            "previous_sessions_considered": self.previous_sessions_considered,
        }

    def to_json(self) -> str:
        """Serialize this result as JSON without requiring custom encoders."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


def process_reasoning_session(
    session_text: str,
    *,
    db_path: str | Path | None = None,
    settings: Settings | None = None,
    retrieval_limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> ReasoningWorkflowResult:
    """Extract, save, retrieve history, and detect tentative patterns.

    The extractor is called once. The newly saved session is explicitly
    excluded from historical search and pattern evidence. Extraction failure
    stops the workflow before anything is saved. Only historical results
    returned by keyword search are considered for patterns. Storage and
    analysis are local; extraction may make one Gemini request.

    Raises ``ValueError`` for invalid session text/limits and
    ``ReasoningWorkflowError`` for a failure in a workflow stage. Error
    messages deliberately omit source text, provider response bodies, and
    credentials. If ``session_saved`` is true, ``session_id`` identifies the
    persisted session in case a later history step failed.
    """
    if not isinstance(session_text, str) or not session_text.strip():
        raise ValueError("Session text must be a non-empty string.")
    if (
        isinstance(retrieval_limit, bool)
        or not isinstance(retrieval_limit, int)
        or retrieval_limit <= 0
    ):
        raise ValueError("Retrieval limit must be a positive integer.")

    try:
        reasoning = extract_reasoning(session_text, settings=settings)
    except Exception:
        raise ReasoningWorkflowError(
            "Reasoning extraction failed; no session was saved.",
            stage="extraction",
            session_saved=False,
        ) from None

    try:
        stored = save_session(session_text, reasoning, db_path=db_path)
    except Exception:
        raise ReasoningWorkflowError(
            "The extracted session could not be saved to local storage.",
            stage="storage",
            session_saved=False,
        ) from None

    excluded_ids = {stored.session_id}
    try:
        previous = search_sessions(
            session_text,
            limit=retrieval_limit,
            db_path=db_path,
            exclude_session_ids=excluded_ids,
        )
    except Exception:
        raise ReasoningWorkflowError(
            "The session was saved, but historical retrieval failed.",
            stage="retrieval",
            session_saved=True,
            session_id=stored.session_id,
        ) from None

    try:
        pattern_analysis = detect_reasoning_patterns(
            session_text,
            db_path=db_path,
            limit=retrieval_limit,
            exclude_session_ids=excluded_ids,
        )
    except Exception:
        raise ReasoningWorkflowError(
            "The session was saved, but pattern analysis failed.",
            stage="pattern_detection",
            session_saved=True,
            session_id=stored.session_id,
        ) from None

    return ReasoningWorkflowResult(
        session_id=stored.session_id,
        reasoning=reasoning,
        relevant_previous_sessions=tuple(previous),
        detected_patterns=pattern_analysis.patterns,
        insufficient_evidence=pattern_analysis.insufficient_evidence,
        previous_sessions_considered=pattern_analysis.sessions_considered,
    )
