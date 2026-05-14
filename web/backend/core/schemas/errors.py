"""Error and exception schemas."""

from pydantic import BaseModel


class StructuredError(BaseModel):
    """Structured error log entry."""

    time: str
    error_type: str
    component: str
    message: str | None = None
    traceback: str | None = None


class ErrorsResponse(BaseModel):
    """Response for /api/errors/last."""

    success: bool = True
    errors: list[StructuredError]


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized error response."""

    success: bool = False
    error: ErrorDetail
