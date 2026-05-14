"""User verification and search schemas."""

from pydantic import BaseModel, Field


class VerificationRecord(BaseModel):
    """User verification record."""

    user_id: int
    rsi_handle: str
    membership_status: str | None = None
    community_moniker: str | None = None
    last_updated: int
    needs_reverify: bool = False
    main_orgs: list[str] | None = None
    affiliate_orgs: list[str] | None = None


class UserSearchResponse(BaseModel):
    """Response for /api/users/search."""

    success: bool = True
    items: list[VerificationRecord]
    total: int
    page: int
    page_size: int
