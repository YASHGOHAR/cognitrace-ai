"""Request and response models for the session API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Chat message must not be blank.")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatResponse(BaseModel):
    message: str


class StoredSessionResponse(BaseModel):
    session_id: str
    created_at: str
    session_text: str
    reasoning: ReasoningExtraction


class SessionHistoryResponse(BaseModel):
    items: list[StoredSessionResponse]
    limit: int
    offset: int
