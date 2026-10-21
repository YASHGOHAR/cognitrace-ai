"""Deterministic comparison of similar reasoning statements across sessions.

This module finds textual similarity, not a proven behavioral trait. Its
results are tentative observations and should be reviewed alongside evidence.
"""

from dataclasses import dataclass
import re
from pathlib import Path

from ai.retrieval.keyword_search import search_sessions
from ai.schemas.reasoning import ReasoningItem
from ai.storage.session_store import StoredSession, list_sessions


MINIMUM_DISTINCT_SESSIONS = 2
SIMILARITY_THRESHOLD = 0.5
MINIMUM_SHARED_TERMS = 2
_STOP_WORDS = frozenset(
    "a an and are as at be been being but by for from had has have he her hers him his "
    "i if in into is it its me my of on or our ours she so than that the their theirs "
    "them then there these they this those to too us was we were what when where which "
    "who why will with you your yours how do does did can could would should may might "
    "about after before between each few more most other some such not no nor only own "
    "same very just also any both all again further once here use used using".split()
)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CATEGORY_LABELS = {
    "decisions": "decision",
    "justifications": "justification",
    "alternatives_considered": "alternative",
    "assumptions": "assumption",
}


@dataclass(frozen=True)
class PatternEvidence:
    """One exact reasoning record and the stored session that contains it."""

    session_id: str
    category: str
    text: str
    evidence: str


@dataclass(frozen=True)
class ReasoningPattern:
    """A tentative pattern supported by multiple distinct sessions."""

    description: str
    category: str
    supporting_session_ids: tuple[str, ...]
    supporting_evidence: tuple[PatternEvidence, ...]
    distinct_session_count: int
    counterexamples: tuple[PatternEvidence, ...]
    reflection_question: str


@dataclass(frozen=True)
class PatternAnalysis:
    """Patterns found within the selected sessions and analysis status."""

    patterns: tuple[ReasoningPattern, ...]
    sessions_considered: int
    insufficient_evidence: bool


@dataclass(frozen=True)
class _Candidate:
    item: PatternEvidence
    terms: frozenset[str]
    normalized_text: str


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _WORD.findall(text.casefold())
        if token not in _STOP_WORDS and len(token) > 1
    )


def _similarity(left: _Candidate, right: _Candidate) -> bool:
    shared = left.terms & right.terms
    union = left.terms | right.terms
    return (
        len(shared) >= MINIMUM_SHARED_TERMS
        and len(shared) / len(union) >= SIMILARITY_THRESHOLD
    )


def _candidates(sessions: list[StoredSession]) -> dict[str, list[_Candidate]]:
    by_category: dict[str, list[_Candidate]] = {
        category: [] for category in _CATEGORY_LABELS
    }
    # Repeated identical statements within one session are collapsed, so they
    # can never manufacture cross-session recurrence.
    seen: set[tuple[str, str, str]] = set()
    for session in sessions:
        for category in _CATEGORY_LABELS:
            for item in getattr(session.reasoning, category):
                terms = _terms(item.text)
                if len(terms) < MINIMUM_SHARED_TERMS:
                    continue
                normalized = " ".join(_WORD.findall(item.text.casefold()))
                key = (session.session_id, category, normalized)
                if key in seen:
                    continue
                seen.add(key)
                by_category[category].append(
                    _Candidate(
                        PatternEvidence(
                            session_id=session.session_id,
                            category=category,
                            text=item.text,
                            evidence=item.evidence,
                        ),
                        terms,
                        normalized,
                    )
                )
    for candidates in by_category.values():
        candidates.sort(
            key=lambda candidate: (
                candidate.normalized_text,
                candidate.item.session_id,
                candidate.item.evidence,
            )
        )
    return by_category


def _clusters(candidates: list[_Candidate]) -> list[list[_Candidate]]:
    """Greedily build complete-link clusters in a stable order.

    Each cluster has at most one candidate per session, and every pair must
    meet the similarity threshold. This avoids chaining unrelated statements
    together through a single intermediate phrase.
    """
    groups: list[list[_Candidate]] = []
    for candidate in candidates:
        for group in groups:
            if any(
                member.item.session_id == candidate.item.session_id
                for member in group
            ):
                continue
            if all(_similarity(candidate, member) for member in group):
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return groups


def _reflection_question(category: str) -> str:
    if category == "decisions":
        return "What factors made this approach useful in these sessions, and when might another option fit better?"
    if category == "justifications":
        return "What evidence or conditions made this reason relevant in these sessions?"
    if category == "alternatives_considered":
        return "What helped you compare these alternatives, and what might change that comparison?"
    return "Which conditions did these assumptions depend on, and how could you check them?"


def _pattern_for_group(
    category: str,
    group: list[_Candidate],
    all_candidates: list[_Candidate],
) -> ReasoningPattern:
    support = tuple(
        sorted(
            (candidate.item for candidate in group),
            key=lambda item: (item.session_id, item.text, item.evidence),
        )
    )
    core_terms = set.intersection(*(set(candidate.terms) for candidate in group))
    representative = min(
        group,
        key=lambda candidate: (
            -len(candidate.terms), candidate.normalized_text, candidate.item.session_id
        ),
    )
    counterexamples: dict[str, PatternEvidence] = {}
    support_ids = {item.session_id for item in support}
    for candidate in all_candidates:
        if candidate.item.session_id in support_ids:
            continue
        if core_terms & candidate.terms and not all(
            _similarity(candidate, member) for member in group
        ):
            current = counterexamples.get(candidate.item.session_id)
            if current is None or (candidate.normalized_text, candidate.item.text) < (
                " ".join(_WORD.findall(current.text.casefold())), current.text
            ):
                counterexamples[candidate.item.session_id] = candidate.item

    label = _CATEGORY_LABELS[category]
    return ReasoningPattern(
        description=(
            f"Possible recurring {label}: {representative.item.text}"
        ),
        category=category,
        supporting_session_ids=tuple(sorted({item.session_id for item in support})),
        supporting_evidence=support,
        distinct_session_count=len({item.session_id for item in support}),
        counterexamples=tuple(
            sorted(counterexamples.values(), key=lambda item: item.session_id)
        ),
        reflection_question=_reflection_question(category),
    )


def detect_reasoning_patterns(
    query: str | None = None,
    *,
    db_path: str | Path | None = None,
    limit: int | None = None,
    exclude_session_ids: set[str] | frozenset[str] | None = None,
) -> PatternAnalysis:
    """Find tentative repeated reasoning statements across stored sessions.

    With a query, existing keyword retrieval scopes the comparison to matching
    sessions. Without one, all stored sessions are compared. A statement must
    have at least two meaningful terms and match another statement in the same
    reasoning category with Jaccard similarity >= 0.5 and at least two shared
    terms. No LLM or network request is made.
    """
    excluded_ids = exclude_session_ids or set()
    if query is None:
        sessions: list[StoredSession] = [
            session
            for session in list_sessions(limit=None, db_path=db_path)
            if session.session_id not in excluded_ids
        ]
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("Limit must be a positive integer or None.")
            sessions = sessions[:limit]
    else:
        if not isinstance(query, str):
            raise TypeError("Pattern query must be a string or None.")
        sessions = search_sessions(
            query,
            limit=limit,
            db_path=db_path,
            exclude_session_ids=excluded_ids,
        )

    by_category = _candidates(sessions)
    patterns = []
    for category, candidates in by_category.items():
        for group in _clusters(candidates):
            if len({member.item.session_id for member in group}) < MINIMUM_DISTINCT_SESSIONS:
                continue
            patterns.append(_pattern_for_group(category, group, candidates))
    patterns.sort(
        key=lambda pattern: (
            pattern.category,
            pattern.description.casefold(),
            pattern.supporting_session_ids,
        )
    )
    return PatternAnalysis(
        patterns=tuple(patterns),
        sessions_considered=len(sessions),
        insufficient_evidence=not patterns,
    )
