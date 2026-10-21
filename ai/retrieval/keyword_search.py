"""Explainable keyword search over locally stored reasoning sessions."""

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable

from ai.schemas.reasoning import ReasoningExtraction, ReasoningItem
from ai.storage.session_store import list_sessions


DEFAULT_RESULT_LIMIT = 10
_STOP_WORDS = frozenset(
    "a an and are as at be been being but by for from had has have he her hers him his "
    "i if in into is it its me my of on or our ours she so than that the their theirs "
    "them then there these they this those to too us was we were what when where which "
    "who why will with you your yours how do does did can could would should may might "
    "about after before between during each few more most other some such not no nor "
    "only own same very just also any both all again further once here".split()
)
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class SearchResult:
    """One stored session that matched a keyword query."""

    session_id: str
    timestamp: str
    relevance_score: int
    session_text: str
    reasoning: ReasoningExtraction


def _tokens(text: str) -> set[str]:
    """Lowercase and tokenize, naturally ignoring punctuation and whitespace."""
    return {token for token in _TOKEN_PATTERN.findall(text.casefold()) if token not in _STOP_WORDS}


def _category_text(items: Iterable[ReasoningItem]) -> str:
    # One combined field per reasoning category means repeated mentions in
    # that category contribute only one point per query term.
    return " ".join(f"{item.text} {item.evidence}" for item in items)


def _reasoning_fields(reasoning: ReasoningExtraction) -> list[str]:
    fields = [
        _category_text(reasoning.decisions),
        _category_text(reasoning.justifications),
        _category_text(reasoning.alternatives_considered),
        _category_text(reasoning.assumptions),
    ]
    if reasoning.problem is not None:
        fields.append(_category_text([reasoning.problem]))
    else:
        fields.append("")
    return fields


def _score(query_terms: set[str], session_text: str, reasoning: ReasoningExtraction) -> int:
    score = len(query_terms & _tokens(session_text))
    # Structured fields get two points per distinct matched term because they
    # directly describe extracted reasoning; source text gets one.
    for field in _reasoning_fields(reasoning):
        score += 2 * len(query_terms & _tokens(field))
    return score


def search_sessions(
    query: str,
    *,
    limit: int | None = DEFAULT_RESULT_LIMIT,
    db_path: str | Path | None = None,
    exclude_session_ids: set[str] | frozenset[str] | None = None,
) -> list[SearchResult]:
    """Return keyword matches ranked by field-weighted relevance.

    Empty and stop-word-only queries return an empty list. Query terms match
    complete tokens, not substrings; no external NLP or model calls are used.
    Pass ``limit=None`` to return all ranked matches.
    """
    if not isinstance(query, str):
        raise TypeError("Search query must be a string.")
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
    ):
        raise ValueError("Limit must be a positive integer or None.")
    query_terms = _tokens(query)
    if not query_terms:
        return []

    excluded_ids = exclude_session_ids or set()
    matches = []
    for session in list_sessions(limit=None, db_path=db_path):
        if session.session_id in excluded_ids:
            continue
        score = _score(query_terms, session.session_text, session.reasoning)
        if score:
            matches.append(
                SearchResult(
                    session_id=session.session_id,
                    timestamp=session.created_at,
                    relevance_score=score,
                    session_text=session.session_text,
                    reasoning=session.reasoning,
                )
            )
    matches.sort(
        key=lambda result: (result.relevance_score, result.timestamp, result.session_id),
        reverse=True,
    )
    return matches if limit is None else matches[:limit]
