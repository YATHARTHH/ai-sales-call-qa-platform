"""Standard API error response envelope."""

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error object."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable explanation of error")
    request_id: str | None = Field(default=None, description="Request tracking ID")
    details: dict[str, str] | None = Field(default=None, description="Optional diagnostic details")


class ErrorResponse(BaseModel):
    """Standard top-level API error envelope."""

    error: ErrorDetail
