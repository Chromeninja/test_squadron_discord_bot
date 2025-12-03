"""
Request ID middleware for FastAPI backend.

Generates a unique correlation ID for each request and includes it
in all log entries for that request.
"""

import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable to store request ID for the current request
request_id_context: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates a unique request ID for each request.

    The request ID is:
    - Stored in context for access by log formatters
    - Returned in the X-Request-ID response header
    - Included in all logs for that request
    """

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Store in context for this request
        request_id_context.set(request_id)

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_context.get("")
