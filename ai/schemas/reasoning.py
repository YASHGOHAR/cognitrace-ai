"""Pydantic schemas for reasoning extraction."""

from pydantic import BaseModel, ConfigDict, Field


class ReasoningItem(BaseModel):
    """One extracted statement paired with its exact supporting source text."""

    # Preserve evidence byte-for-byte so source validation checks the model's
    # actual quote rather than a Pydantic-trimmed substitute.
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="A concise reasoning statement grounded in the session.")
    evidence: str = Field(
        description="An exact, contiguous quote copied from the original session that supports text."
    )


class ReasoningExtraction(BaseModel):
    """Structured reasoning information found in one problem-solving session."""

    model_config = ConfigDict(extra="forbid")

    problem: ReasoningItem | None = Field(
        description="The problem being solved, or null when it is not stated."
    )
    decisions: list[ReasoningItem] = Field(
        description="Explicit choices made while solving the problem; empty when none are stated."
    )
    justifications: list[ReasoningItem] = Field(
        description="Explicit reasons supporting decisions; empty when none are stated."
    )
    alternatives_considered: list[ReasoningItem] = Field(
        description="Alternatives explicitly considered; empty when none are stated."
    )
    assumptions: list[ReasoningItem] = Field(
        description="Assumptions explicitly stated or clearly supported by the session; empty when none."
    )
