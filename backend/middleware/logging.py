"""Structured JSON logging middleware for FastAPI/Starlette."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured JSON log line per request to the backend.access logger."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.time()
        # Validate inbound header to UUID format to prevent header-injection attacks.
        # Any non-UUID value is replaced with a fresh one.
        raw = request.headers.get("X-Correlation-ID", "")
        try:
            correlation_id = str(uuid.UUID(raw))
        except ValueError:
            correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        response = await call_next(request)

        duration_ms = int((time.time() - start) * 1000)
        log = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": "INFO",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "correlation_id": correlation_id,
        }
        logging.getLogger("backend.access").info(json.dumps(log))
        response.headers["X-Correlation-ID"] = correlation_id
        return response
