"""Tests for scheduled event serialization in the internal API."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from services.internal_api import InternalAPIServer


def test_serialize_scheduled_event_uses_discord_py_time_attributes() -> None:
    """Scheduled event serialization should use Discord.py start/end time fields."""
    start_time = datetime(2026, 4, 22, 22, 30, tzinfo=UTC)
    end_time = datetime(2026, 4, 22, 23, 30, tzinfo=UTC)
    channel = SimpleNamespace(id=123456789, name="Ops Voice")
    creator = SimpleNamespace(id=987654321, name="VerifyBot", display_name="TEST Verify Bot")
    event = cast(Any, SimpleNamespace(
        id=555666777,
        name="Fleet Night",
        description="Weekly op",
        start_time=start_time,
        end_time=end_time,
        status=SimpleNamespace(name="scheduled"),
        entity_type=SimpleNamespace(name="voice"),
        channel=channel,
        channel_id=channel.id,
        location=None,
        user_count=14,
        creator=creator,
        cover_image=None,
    ))

    payload = InternalAPIServer._serialize_scheduled_event(event)

    assert payload["scheduled_start_time"] == start_time.isoformat()
    assert payload["scheduled_end_time"] == end_time.isoformat()
    assert payload["channel_name"] == "Ops Voice"
    assert payload["creator_name"] == "TEST Verify Bot"


def test_serialize_scheduled_event_uses_guild_channel_fallback() -> None:
    """Scheduled event serialization should resolve the channel from the guild if needed."""
    start_time = datetime(2026, 4, 23, 1, 0, tzinfo=UTC)
    channel = SimpleNamespace(id=222333444, name="Live Event")
    guild = cast(
        Any,
        SimpleNamespace(
            get_channel=lambda channel_id: channel if channel_id == channel.id else None
        ),
    )
    event = cast(Any, SimpleNamespace(
        id=888999000,
        name="External Sync",
        description=None,
        start_time=start_time,
        end_time=None,
        status=SimpleNamespace(name="scheduled"),
        entity_type=SimpleNamespace(name="voice"),
        channel=None,
        channel_id=channel.id,
        location=None,
        user_count=1,
        creator=None,
        cover_image=None,
    ))

    payload = InternalAPIServer._serialize_scheduled_event(event, guild)

    assert payload["scheduled_start_time"] == start_time.isoformat()
    assert payload["channel_id"] == str(channel.id)
    assert payload["channel_name"] == "Live Event"