"""Endpoints for creating and reading reasoning sessions."""

from fastapi import APIRouter, HTTPException, Query, Request

from ai.storage.session_store import StoredSession, get_session, list_sessions
from ai.workflow import ReasoningWorkflowError, process_reasoning_session
from backend.app.config import get_database_path
from backend.app.schemas import (
    CreateSessionRequest,
    SessionHistoryResponse,
    StoredSessionResponse,
)
from backend.app.security import require_api_token


router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
)


def _to_response(session: StoredSession) -> StoredSessionResponse:
    return StoredSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        session_text=session.session_text,
        reasoning=session.reasoning,
    )


@router.post("")
def create_session(
    body: CreateSessionRequest, request: Request
) -> dict[str, object]:
    """Run the existing AI workflow and return its JSON-ready result."""
    require_api_token(request.headers.get("authorization"))
    try:
        result = process_reasoning_session(
            body.session_text,
            db_path=get_database_path(),
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="Session input is invalid.") from None
    except ReasoningWorkflowError as exc:
        if exc.stage == "extraction":
            status_code = 502
            message = "Reasoning extraction failed; no session was saved."
        elif exc.session_saved:
            status_code = 500
            message = "The session was saved, but a later processing step failed."
        else:
            status_code = 500
            message = "The session could not be saved."
        detail: dict[str, object] = {
            "message": message,
            "session_saved": exc.session_saved,
        }
        if exc.session_id:
            detail["session_id"] = exc.session_id
        raise HTTPException(status_code=status_code, detail=detail) from None
    except Exception:
        # Do not include provider/SQLite exception text or session content.
        raise HTTPException(
            status_code=500,
            detail="The session could not be processed.",
        ) from None
    return result.to_dict()


@router.get("", response_model=SessionHistoryResponse)
def get_session_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SessionHistoryResponse:
    """Return one newest-first page of stored sessions."""
    require_api_token(request.headers.get("authorization"))
    try:
        sessions = list_sessions(
            limit=limit,
            offset=offset,
            db_path=get_database_path(),
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Session history could not be loaded.",
        ) from None
    return SessionHistoryResponse(
        items=[_to_response(session) for session in sessions],
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=StoredSessionResponse)
def get_session_by_id(session_id: str, request: Request) -> StoredSessionResponse:
    """Return a stored session, or a 404 without exposing database details."""
    require_api_token(request.headers.get("authorization"))
    try:
        session = get_session(session_id, db_path=get_database_path())
    except ValueError:
        raise HTTPException(status_code=422, detail="Session ID is invalid.") from None
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="The session could not be loaded.",
        ) from None
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _to_response(session)
