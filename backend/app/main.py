"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import get_allowed_origins
from backend.app.routes.sessions import router as sessions_router


app = FastAPI(title="Cognitrace AI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_private_network=True,
)


@app.middleware("http")
async def prevent_session_response_caching(request: Request, call_next):
    """Keep private transcripts and reasoning out of browser/proxy caches."""
    response = await call_next(request)
    if request.url.path.startswith("/api/sessions"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Avoid echoing rejected request bodies (which may contain session text)."""
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed."},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(sessions_router)
