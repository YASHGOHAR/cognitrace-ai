"""Request and response models for the session API."""

from pydantic import BaseModel, ConfigDict, field_validator

from ai.schemas.reasoning import ReasoningExtraction


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_text: str

    @field_validator("session_text")
    @classmethod
    def session_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Session text must not be blank.")
        return value


class StoredSessionResponse(BaseModel):
    session_id: str
    created_at: str
    session_text: str
    reasoning: ReasoningExtraction


class SessionHistoryResponse(BaseModel):
    items: list[StoredSessionResponse]
    limit: int
    offset: int
