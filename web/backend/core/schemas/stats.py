"""Statistics and status schemas."""

from pydantic import BaseModel


class StatusCounts(BaseModel):
    """Verification status breakdown."""

    main: int = 0
    affiliate: int = 0
    non_member: int = 0
    unknown: int = 0


class StatsOverview(BaseModel):
    """Dashboard statistics overview."""

    total_verified: int
    by_status: StatusCounts
    voice_active_count: int


class StatsResponse(BaseModel):
    """Response for /api/stats/overview."""

    success: bool = True
    data: StatsOverview
