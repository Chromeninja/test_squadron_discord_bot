"""Global FastAPI exception handler returning structured JSON errors."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request

_log = logging.getLogger("backend.errors")


async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a 500 JSON response; log full exception server-side only."""
    correlation_id: str | None = None
    try:
        correlation_id = request.state.correlation_id
    except AttributeError:
        pass

    # Log full traceback server-side — never expose exc details to the client
    _log.exception("Unhandled exception", extra={"correlation_id": correlation_id})

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "correlation_id": correlation_id,
        },
    )
