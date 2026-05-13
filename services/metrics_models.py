"""Data models for in-memory metrics session tracking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VoiceSessionInfo:
    """Tracks an active voice session for a user."""

    guild_id: int
    user_id: int
    channel_id: int
    joined_at: int


@dataclass
class GameSessionInfo:
    """Tracks an active game session for a user."""

    guild_id: int
    user_id: int
    game_name: str
    started_at: int


@dataclass
class MetricsSnapshot:
    """Point-in-time snapshot of live metrics for a guild."""

    messages_today: int = 0
    active_voice_users: int = 0
    active_game_sessions: int = 0
    top_game: str | None = None
