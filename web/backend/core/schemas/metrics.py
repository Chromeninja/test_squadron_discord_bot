"""Metrics and analytics schemas."""

from pydantic import BaseModel, ConfigDict, Field


class MetricsLive(BaseModel):
    """Live snapshot of current metrics."""

    messages_today: int = 0
    active_voice_users: int = 0
    active_game_sessions: int = 0
    top_game: str | None = None


class MetricsPeriod(BaseModel):
    """Aggregated metrics for a time period."""

    total_messages: int = 0
    unique_messagers: int = 0
    avg_messages_per_user: float = 0.0
    total_voice_seconds: int = 0
    unique_voice_users: int = 0
    avg_voice_per_user: int = 0
    unique_users: int = 0
    top_games: list[dict] = []


class MetricsOverview(BaseModel):
    """Combined live + period metrics overview."""

    live: MetricsLive
    period: MetricsPeriod


class MetricsOverviewResponse(BaseModel):
    """Response for /api/metrics/overview."""

    success: bool = True
    data: MetricsOverview


class VoiceLeaderboardEntry(BaseModel):
    """Single entry in voice time leaderboard."""

    user_id: str
    total_seconds: int
    username: str | None = None
    avatar_url: str | None = None


class MessageLeaderboardEntry(BaseModel):
    """Single entry in message count leaderboard."""

    user_id: str
    total_messages: int
    username: str | None = None
    avatar_url: str | None = None


class LeaderboardResponse(BaseModel):
    """Response for leaderboard endpoints."""

    success: bool = True
    entries: list[dict]


class GameStats(BaseModel):
    """Stats for a single game."""

    game_name: str
    total_seconds: int
    session_count: int
    avg_seconds: int = 0
    unique_players: int = 0


class TopGamesResponse(BaseModel):
    """Response for /api/metrics/games/top."""

    success: bool = True
    games: list[GameStats]


class GameTopPlayer(BaseModel):
    """Top player entry for a specific game."""

    user_id: str
    total_seconds: int
    session_count: int
    avg_seconds: int = 0
    username: str | None = None
    avatar_url: str | None = None


class GameMetrics(BaseModel):
    """Detailed metrics for a specific game."""

    game_name: str
    days: int
    total_seconds: int
    session_count: int
    avg_seconds: int
    unique_players: int
    top_players: list[GameTopPlayer]
    timeseries: list[dict]


class GameMetricsResponse(BaseModel):
    """Response for /api/metrics/games/detail."""

    success: bool = True
    data: GameMetrics


class TimeSeriesPoint(BaseModel):
    """Single data point in a time series."""

    timestamp: int
    value: int | None = None
    unique_users: int | None = None
    top_game: str | None = None


class TimeSeriesResponse(BaseModel):
    """Response for /api/metrics/timeseries."""

    success: bool = True
    metric: str
    days: int
    data: list[dict]


class UserGameStats(BaseModel):
    """Per-user game breakdown."""

    game_name: str
    total_seconds: int


class UserTimeSeriesPoint(BaseModel):
    """Per-user time series point."""

    timestamp: int
    messages: int = 0
    voice_seconds: int = 0
    game_seconds: int = 0


class UserMetrics(BaseModel):
    """Detailed metrics for a single user."""

    user_id: str
    username: str | None = None
    avatar_url: str | None = None
    total_messages: int = 0
    total_voice_seconds: int = 0
    avg_messages_per_day: float = 0.0
    avg_voice_per_day: int = 0
    top_games: list[UserGameStats] = []
    timeseries: list[UserTimeSeriesPoint] = []
    # Per-dimension activity tiers
    voice_tier: str | None = None
    chat_tier: str | None = None
    game_tier: str | None = None
    combined_tier: str | None = None
    last_voice_at: int | None = None
    last_chat_at: int | None = None
    last_game_at: int | None = None


class UserMetricsResponse(BaseModel):
    """Response for /api/metrics/user/{user_id}."""

    success: bool = True
    data: UserMetrics


class ActivityTierCounts(BaseModel):
    """Counts of members per activity tier for one dimension."""

    hardcore: int = 0
    regular: int = 0
    casual: int = 0
    reserve: int = 0
    inactive: int = 0


class ActivityGroupCounts(BaseModel):
    """Per-dimension activity group counts."""

    model_config = ConfigDict(populate_by_name=True)

    all: ActivityTierCounts = Field(
        default_factory=ActivityTierCounts, validation_alias="combined"
    )
    voice: ActivityTierCounts = Field(default_factory=ActivityTierCounts)
    chat: ActivityTierCounts = Field(default_factory=ActivityTierCounts)
    game: ActivityTierCounts = Field(default_factory=ActivityTierCounts)


class ActivityGroupCountsResponse(BaseModel):
    """Response for /api/metrics/activity-groups."""

    success: bool = True
    data: ActivityGroupCounts


class DashboardMetricsBundle(BaseModel):
    """Bundled metrics payload for the dashboard page."""

    overview: MetricsOverview
    voice_leaderboard: list[VoiceLeaderboardEntry] = Field(default_factory=list)
    message_leaderboard: list[MessageLeaderboardEntry] = Field(default_factory=list)
    top_games: list[GameStats] = Field(default_factory=list)
    message_timeseries: list[dict] = Field(default_factory=list)
    voice_timeseries: list[dict] = Field(default_factory=list)
    activity_counts: ActivityGroupCounts = Field(default_factory=ActivityGroupCounts)


class DashboardMetricsResponse(BaseModel):
    """Response for the bundled dashboard metrics endpoint."""

    success: bool = True
    data: DashboardMetricsBundle
