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


class DraftMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1, max_length=100)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    createdAt: str = Field(default="", max_length=80)

    @field_validator("content")
    @classmethod
    def draft_message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Draft message must not be blank.")
        return value


class CreateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)


class UpdateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    messages: list[DraftMessage] = Field(max_length=40)


class DraftResponse(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[DraftMessage]


class StoredSessionResponse(BaseModel):
    session_id: str
    created_at: str
    session_text: str
    reasoning: ReasoningExtraction


class SessionHistoryResponse(BaseModel):
    items: list[StoredSessionResponse]
    limit: int
    offset: int
