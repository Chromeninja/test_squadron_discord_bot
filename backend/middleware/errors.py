"""Global FastAPI exception handler returning structured JSON errors."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a 500 JSON response with correlation ID for unhandled exceptions."""
    correlation_id: str | None = None
    try:
        correlation_id = request.state.correlation_id
    except AttributeError:
        pass

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if exc else "An unexpected error occurred",
            "correlation_id": correlation_id,
        },
    )
