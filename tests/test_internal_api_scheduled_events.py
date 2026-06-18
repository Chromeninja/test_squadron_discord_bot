"""Tests for scheduled event serialization and caching in the internal API."""

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import discord
import pytest
from aiohttp import web

from services.internal_api import InternalAPIServer, _ScheduledEventsCache


def test_serialize_scheduled_event_uses_discord_py_time_attributes() -> None:
    """Scheduled event serialization should use Discord.py start/end time fields."""
    start_time = datetime(2026, 4, 22, 22, 30, tzinfo=UTC)
    end_time = datetime(2026, 4, 22, 23, 30, tzinfo=UTC)
    channel = SimpleNamespace(id=123456789, name="Ops Voice")
    creator = SimpleNamespace(
        id=987654321, name="VerifyBot", display_name="TEST Verify Bot"
    )
    event = cast(
        "Any",
        SimpleNamespace(
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
        ),
    )

    payload = InternalAPIServer._serialize_scheduled_event(event)

    assert payload["scheduled_start_time"] == start_time.isoformat()
    assert payload["scheduled_end_time"] == end_time.isoformat()
    assert payload["channel_name"] == "Ops Voice"
    assert payload["creator_name"] == "TEST Verify Bot"
    assert payload["recurrence_rule"] is None
    assert payload["recurrence_rule_payload"] is None


def test_serialize_scheduled_event_formats_weekly_recurrence() -> None:
    """Scheduled event serialization should format weekly recurrence details."""
    start_time = datetime(2026, 4, 22, 22, 30, tzinfo=UTC)
    recurrence_rule = SimpleNamespace(
        frequency=SimpleNamespace(name="weekly"),
        interval=1,
        by_weekday=[
            SimpleNamespace(value=1),
            SimpleNamespace(value=3),
        ],
    )
    event = cast(
        "Any",
        SimpleNamespace(
            id=121212,
            name="Recurring Fleet",
            description="Two days each week",
            start_time=start_time,
            end_time=None,
            status=SimpleNamespace(name="scheduled"),
            entity_type=SimpleNamespace(name="voice"),
            channel=None,
            channel_id=None,
            location=None,
            user_count=3,
            creator=None,
            cover_image=None,
            recurrence_rule=recurrence_rule,
        ),
    )

    payload = InternalAPIServer._serialize_scheduled_event(event)

    assert payload["recurrence_rule"] == "Weekly on Tuesday, Thursday"
    assert payload["recurrence_rule_payload"] == {
        "start": start_time.isoformat(),
        "frequency": 2,
        "interval": 1,
        "by_weekday": [1, 3],
    }


def test_serialize_scheduled_event_uses_raw_recurrence_and_image_fallback() -> None:
    """Serialization should preserve REST-only recurrence and image metadata."""
    start_time = datetime(2026, 6, 2, 20, 0, tzinfo=UTC)
    event = cast(
        "Any",
        SimpleNamespace(
            id=999888777666555444,
            name="Repeat Test",
            description="Weekly op",
            start_time=start_time,
            end_time=None,
            status=SimpleNamespace(name="scheduled"),
            entity_type=SimpleNamespace(name="voice"),
            channel=None,
            channel_id=None,
            location=None,
            user_count=1,
            creator=None,
            cover_image=None,
        ),
    )
    raw_event_data = {
        "id": "999888777666555444",
        "image": "event-image-hash",
        "recurrence_rule": {
            "start": "2026-06-02T20:00:00+00:00",
            "frequency": 2,
            "interval": 1,
            "by_weekday": [1],
        },
    }

    payload = InternalAPIServer._serialize_scheduled_event(
        event,
        raw_event_data=raw_event_data,
    )

    assert payload["image_url"] == (
        "https://cdn.discordapp.com/guild-events/"
        "999888777666555444/event-image-hash.png?size=1024"
    )
    assert payload["recurrence_rule"] == "Weekly on Tuesday"
    assert payload["recurrence_rule_payload"] == {
        "start": "2026-06-02T20:00:00+00:00",
        "frequency": 2,
        "interval": 1,
        "by_weekday": [1],
    }


def test_internal_api_allows_event_cover_upload_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Internal API request body limit should allow Discord image data payloads."""
    monkeypatch.setenv("ENV", "test")
    server = InternalAPIServer(cast("Any", SimpleNamespace(bot=None)))

    assert server.app._client_max_size >= 12 * 1024 * 1024


@pytest.mark.asyncio
async def test_create_scheduled_event_raw_payload_includes_image_data() -> None:
    """Raw scheduled event creation should pass image data to Discord."""
    image_data = "data:image/png;base64,iVBORw0KGgo="
    captured_payload: dict[str, object] = {}

    async def request(route: object, json: dict[str, object]) -> dict[str, object]:
        del route
        captured_payload.update(json)
        return {"id": "999888777666555444", "image": "event-image-hash"}

    event = cast("Any", SimpleNamespace(id=999888777666555444))
    guild = cast(
        "Any",
        SimpleNamespace(
            id=123456789,
            _state=SimpleNamespace(http=SimpleNamespace(request=request)),
            fetch_scheduled_event=AsyncMock(return_value=event),
        ),
    )
    channel = cast("Any", SimpleNamespace(id=222333444))
    server = object.__new__(InternalAPIServer)

    result, raw_data = await server._create_scheduled_event_with_recurrence(
        guild=guild,
        name="Image Event",
        entity_type=discord.EntityType.voice,
        start_time=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
        end_time=None,
        channel=channel,
        location=None,
        description="Cover art test",
        recurrence_rule=None,
        image_data=image_data,
    )

    assert result is event
    assert captured_payload["image"] == image_data
    assert captured_payload["channel_id"] == "222333444"
    assert "recurrence_rule" not in captured_payload
    assert raw_data["image"] == "event-image-hash"


@pytest.mark.asyncio
async def test_update_scheduled_event_raw_payload_includes_image_data() -> None:
    """Raw scheduled event update should pass replacement image data to Discord."""
    image_data = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    captured_payload: dict[str, object | None] = {}

    async def request(
        route: object, json: dict[str, object | None]
    ) -> dict[str, object]:
        del route
        captured_payload.update(json)
        return {"id": "999888777666555444", "image": "replacement-image-hash"}

    event = cast("Any", SimpleNamespace(id=999888777666555444))
    guild = cast(
        "Any",
        SimpleNamespace(
            id=123456789,
            _state=SimpleNamespace(http=SimpleNamespace(request=request)),
            fetch_scheduled_event=AsyncMock(return_value=event),
        ),
    )
    channel = cast("Any", SimpleNamespace(id=222333444))
    server = object.__new__(InternalAPIServer)

    result, raw_data = await server._update_scheduled_event_with_recurrence(
        guild=guild,
        event_id=999888777666555444,
        name="Image Event Updated",
        entity_type=discord.EntityType.voice,
        start_time=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
        end_time=None,
        channel=channel,
        location=None,
        description="Replacement cover art test",
        recurrence_rule=None,
        image_data=image_data,
    )

    assert result is event
    assert captured_payload["image"] == image_data
    assert captured_payload["channel_id"] == "222333444"
    assert "location" not in captured_payload
    assert "recurrence_rule" not in captured_payload
    assert raw_data["image"] == "replacement-image-hash"


def test_serialize_scheduled_event_uses_guild_channel_fallback() -> None:
    """Scheduled event serialization should resolve the channel from the guild if needed."""
    start_time = datetime(2026, 4, 23, 1, 0, tzinfo=UTC)
    channel = SimpleNamespace(id=222333444, name="Live Event")
    guild = cast(
        "Any",
        SimpleNamespace(
            get_channel=lambda channel_id: channel if channel_id == channel.id else None
        ),
    )
    event = cast(
        "Any",
        SimpleNamespace(
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
        ),
    )

    payload = InternalAPIServer._serialize_scheduled_event(event, guild)

    assert payload["scheduled_start_time"] == start_time.isoformat()
    assert payload["channel_id"] == str(channel.id)
    assert payload["channel_name"] == "Live Event"


def test_events_cache_is_fresh_within_ttl() -> None:
    """Cache should report fresh when within TTL."""
    cache = _ScheduledEventsCache(
        events=[{"id": "1", "name": "Test"}],
        fetched_at=time.monotonic(),
    )
    assert cache.is_fresh() is True


def test_events_cache_is_stale_after_ttl() -> None:
    """Cache should report stale when past TTL."""
    cache = _ScheduledEventsCache(
        events=[{"id": "1", "name": "Test"}],
        fetched_at=time.monotonic() - 60.0,
    )
    assert cache.is_fresh() is False


def test_events_cache_empty_is_stale() -> None:
    """Default cache (fetched_at=0) should always be stale."""
    cache = _ScheduledEventsCache()
    assert cache.is_fresh() is False


@pytest.mark.asyncio
async def test_fetch_and_cache_events_populates_cache() -> None:
    """_fetch_and_cache_events should populate the cache."""
    start_time = datetime(2026, 5, 1, 20, 0, tzinfo=UTC)
    event = cast(
        "Any",
        SimpleNamespace(
            id=111222333,
            name="Cached Event",
            description=None,
            start_time=start_time,
            end_time=None,
            status=SimpleNamespace(name="scheduled"),
            entity_type=SimpleNamespace(name="voice"),
            channel=None,
            channel_id=None,
            location=None,
            user_count=0,
            creator=None,
            cover_image=None,
        ),
    )

    guild = cast(
        "Any",
        SimpleNamespace(
            id=999888777,
            fetch_scheduled_events=AsyncMock(return_value=[event]),
            get_channel=lambda _: None,
        ),
    )

    server = object.__new__(InternalAPIServer)
    server._events_cache = {}

    result = await server._fetch_and_cache_events(guild)

    assert len(result) == 1
    assert result[0]["name"] == "Cached Event"
    assert guild.id in server._events_cache
    assert server._events_cache[guild.id].is_fresh()
    guild.fetch_scheduled_events.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_and_cache_events_uses_cache_on_second_call() -> None:
    """Second call within TTL should use cache, not fetch again."""
    start_time = datetime(2026, 5, 2, 20, 0, tzinfo=UTC)
    event = cast(
        "Any",
        SimpleNamespace(
            id=444555666,
            name="Cached Again",
            description=None,
            start_time=start_time,
            end_time=None,
            status=SimpleNamespace(name="scheduled"),
            entity_type=SimpleNamespace(name="voice"),
            channel=None,
            channel_id=None,
            location=None,
            user_count=0,
            creator=None,
            cover_image=None,
        ),
    )

    guild = cast(
        "Any",
        SimpleNamespace(
            id=111222333,
            fetch_scheduled_events=AsyncMock(return_value=[event]),
            get_channel=lambda _: None,
        ),
    )

    server = object.__new__(InternalAPIServer)
    server._events_cache = {}

    # First call populates cache
    await server._fetch_and_cache_events(guild)
    # Second call should use cache
    result = await server._fetch_and_cache_events(guild)

    assert len(result) == 1
    assert result[0]["name"] == "Cached Again"
    # Should only have fetched once
    guild.fetch_scheduled_events.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_and_cache_events_preserves_raw_recurrence_metadata() -> None:
    """Fetch cache should keep recurrence metadata only present in raw REST data."""
    start_time = datetime(2026, 6, 2, 20, 0, tzinfo=UTC)
    event = cast(
        "Any",
        SimpleNamespace(
            id=999888777666555444,
            name="Raw Recurring Event",
            description="Weekly op",
            start_time=start_time,
            end_time=None,
            status=SimpleNamespace(name="scheduled"),
            entity_type=SimpleNamespace(name="voice"),
            channel=None,
            channel_id=222333444,
            location=None,
            user_count=1,
            creator=None,
            cover_image=None,
        ),
    )
    raw_event_data = {
        "id": "999888777666555444",
        "guild_id": "123456789",
        "entity_id": None,
        "name": "Raw Recurring Event",
        "description": "Weekly op",
        "scheduled_start_time": "2026-06-02T20:00:00+00:00",
        "scheduled_end_time": None,
        "privacy_level": 2,
        "status": 1,
        "entity_type": 2,
        "channel_id": "222333444",
        "entity_metadata": None,
        "user_count": 1,
        "image": "event-image-hash",
        "recurrence_rule": {
            "start": "2026-06-02T20:00:00+00:00",
            "frequency": 2,
            "interval": 1,
            "by_weekday": [1],
        },
    }
    http_client = SimpleNamespace(
        get_scheduled_events=AsyncMock(return_value=[raw_event_data]),
    )
    state = SimpleNamespace(http=http_client)
    channel = SimpleNamespace(id=222333444, name="Event Coms")
    guild = cast(
        "Any",
        SimpleNamespace(
            id=123456789,
            _state=state,
            fetch_scheduled_events=AsyncMock(return_value=[event]),
            get_channel=lambda channel_id: (
                channel if channel_id == channel.id else None
            ),
        ),
    )

    server = object.__new__(InternalAPIServer)
    server._events_cache = {}

    result = await server._fetch_and_cache_events(guild)

    assert result[0]["channel_name"] == "Event Coms"
    assert result[0]["image_url"] == (
        "https://cdn.discordapp.com/guild-events/"
        "999888777666555444/event-image-hash.png?size=1024"
    )
    assert result[0]["recurrence_rule"] == "Weekly on Tuesday"
    assert result[0]["recurrence_rule_payload"] == {
        "start": "2026-06-02T20:00:00+00:00",
        "frequency": 2,
        "interval": 1,
        "by_weekday": [1],
    }


def test_invalidate_events_cache_removes_entry() -> None:
    """_invalidate_events_cache should remove the guild entry."""
    server = object.__new__(InternalAPIServer)
    server._events_cache = {
        12345: _ScheduledEventsCache(
            events=[{"id": "1"}],
            fetched_at=time.monotonic(),
        )
    }

    server._invalidate_events_cache(12345)

    assert 12345 not in server._events_cache


def test_invalidate_events_cache_ignores_missing_guild() -> None:
    """_invalidate_events_cache should not raise for missing guild."""
    server = object.__new__(InternalAPIServer)
    server._events_cache = {}

    server._invalidate_events_cache(99999)  # Should not raise


@pytest.mark.asyncio
async def test_load_scheduled_event_request_rejects_unknown_entity_type() -> None:
    """Unknown scheduled event entity types should be rejected."""
    server = object.__new__(InternalAPIServer)
    guild = cast("Any", SimpleNamespace(id=123))
    server.bot = cast("Any", SimpleNamespace(get_guild=lambda guild_id: guild))

    request = cast(
        "web.Request",
        SimpleNamespace(
            match_info={"guild_id": "123"},
            json=AsyncMock(
                return_value={
                    "name": "Unknown Attempt",
                    "entity_type": "webinar",
                    "scheduled_start_time": "2026-04-10T20:00:00+00:00",
                }
            ),
        ),
    )

    result = await server._load_scheduled_event_request(request)

    assert isinstance(result, web.Response)
    assert result.status == 400
    payload = json.loads(result.text or "{}")
    assert payload["error"] == "Unsupported scheduled event type"


@pytest.mark.asyncio
async def test_load_scheduled_event_request_accepts_external_location() -> None:
    """External scheduled events should validate location instead of channel."""
    server = object.__new__(InternalAPIServer)
    guild = cast("Any", SimpleNamespace(id=123))
    server.bot = cast("Any", SimpleNamespace(get_guild=lambda guild_id: guild))

    request = cast(
        "web.Request",
        SimpleNamespace(
            match_info={"guild_id": "123"},
            json=AsyncMock(
                return_value={
                    "name": "External Event",
                    "entity_type": "external",
                    "scheduled_start_time": "2026-04-10T20:00:00+00:00",
                    "scheduled_end_time": "2026-04-10T22:00:00+00:00",
                    "location": "Area 18",
                }
            ),
        ),
    )

    result = await server._load_scheduled_event_request(request)

    assert not isinstance(result, web.Response)
    assert result[3] is discord.EntityType.external
    assert result[6] is None
    assert result[7] == "Area 18"


@pytest.mark.asyncio
async def test_create_guild_scheduled_event_posts_announcement() -> None:
    """Create flow should post an embed announcement and signup buttons."""
    server = object.__new__(InternalAPIServer)
    server.bot = cast("Any", object())

    def check_auth(request: web.Request) -> bool:
        return True

    def invalidate_events_cache(guild_id: int) -> None:
        del guild_id

    def serialize_scheduled_event(
        event: Any,
        guild: Any = None,
        raw_data: dict[str, object] | None = None,
    ) -> dict[str, str]:
        del event, guild, raw_data
        return {"id": "123", "name": "TEST 2"}

    cast("Any", server)._check_auth = check_auth
    cast("Any", server)._invalidate_events_cache = invalidate_events_cache
    cast("Any", server)._serialize_scheduled_event = serialize_scheduled_event

    announcement_channel = cast("Any", AsyncMock(spec=discord.TextChannel))
    announcement_channel.send = AsyncMock()
    voice_channel = cast("Any", SimpleNamespace(id=111222333))
    start_time = datetime(2026, 4, 14, 20, 0, tzinfo=UTC)
    event = cast(
        "Any",
        SimpleNamespace(
            id=123,
            name="TEST 2",
            start_time=start_time,
            end_time=None,
            creator=SimpleNamespace(
                display_name="EventCoordinator", name="Coordinator"
            ),
            channel=SimpleNamespace(name="Op Voice", mention="#op-voice"),
            url="https://discord.com/events/123/123",
        ),
    )

    guild_any = cast(
        "Any", SimpleNamespace(create_scheduled_event=AsyncMock(return_value=event))
    )
    guild = cast(
        "Any",
        SimpleNamespace(
            id=123,
            get_channel=lambda channel_id: (
                announcement_channel if channel_id == 555 else None
            ),
            fetch_scheduled_events=AsyncMock(return_value=[]),
            create_scheduled_event=guild_any.create_scheduled_event,
        ),
    )

    server._load_scheduled_event_request = AsyncMock(
        return_value=(
            guild,
            {
                "announcement_channel_id": "555",
                "announcement_message": "Custom announcement body",
                "created_by_name": "T.Riley",
            },
            "TEST 2",
            discord.EntityType.voice,
            start_time,
            None,
            voice_channel,
            None,
            None,
        )
    )

    request = cast("web.Request", SimpleNamespace())

    response = await server.create_guild_scheduled_event(request)

    assert response.status == 200
    assert announcement_channel.send.await_count == 1
    first_call = announcement_channel.send.await_args_list[0]
    assert "embed" in first_call.kwargs
    embed = first_call.kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.description == "Custom announcement body"
    assert embed.footer.text == "Created by T.Riley"


@pytest.mark.asyncio
async def test_create_guild_scheduled_event_uses_description_for_default_message() -> (
    None
):
    """Create flow should default embed body to event description when needed."""
    server = object.__new__(InternalAPIServer)
    server.bot = cast("Any", object())

    cast("Any", server)._check_auth = lambda request: True
    cast("Any", server)._invalidate_events_cache = lambda guild_id: guild_id
    cast("Any", server)._serialize_scheduled_event = (
        lambda event, guild=None, raw_data=None: {
            "id": "123",
            "name": "TEST 2",
        }
    )

    announcement_channel = cast("Any", AsyncMock(spec=discord.TextChannel))
    announcement_channel.send = AsyncMock()
    voice_channel = cast("Any", SimpleNamespace(id=111222333))
    start_time = datetime(2026, 4, 14, 20, 0, tzinfo=UTC)
    event = cast(
        "Any",
        SimpleNamespace(
            id=123,
            name="TEST 2",
            start_time=start_time,
            end_time=None,
            creator=SimpleNamespace(
                display_name="EventCoordinator", name="Coordinator"
            ),
            channel=SimpleNamespace(name="Op Voice", mention="#op-voice"),
            url="https://discord.com/events/123/123",
        ),
    )

    guild_any = cast(
        "Any", SimpleNamespace(create_scheduled_event=AsyncMock(return_value=event))
    )
    guild = cast(
        "Any",
        SimpleNamespace(
            id=123,
            get_channel=lambda channel_id: (
                announcement_channel if channel_id == 555 else None
            ),
            get_role=lambda role_id: None,
            fetch_scheduled_events=AsyncMock(return_value=[]),
            create_scheduled_event=guild_any.create_scheduled_event,
        ),
    )

    server._load_scheduled_event_request = AsyncMock(
        return_value=(
            guild,
            {"announcement_channel_id": "555", "announcement_message": "   "},
            "TEST 2",
            discord.EntityType.voice,
            start_time,
            None,
            voice_channel,
            None,
            "test event brief",
        )
    )

    request = cast("web.Request", SimpleNamespace())

    response = await server.create_guild_scheduled_event(request)

    assert response.status == 200
    first_call = announcement_channel.send.await_args_list[0]
    embed = first_call.kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.description == "test event brief"
    assert embed.footer.text == "Created by EventCoordinator"


@pytest.mark.asyncio
async def test_delete_guild_scheduled_event_success() -> None:
    """Delete flow should remove event and invalidate scheduled-event cache."""
    server = object.__new__(InternalAPIServer)
    server.bot = cast("Any", object())
    server._check_auth = lambda request: True

    invalidated_guilds: list[int] = []

    def mock_invalidate(guild_id: int) -> None:
        invalidated_guilds.append(guild_id)

    server._invalidate_events_cache = mock_invalidate

    event_any = cast("Any", SimpleNamespace(delete=AsyncMock()))
    guild = cast(
        "Any",
        SimpleNamespace(
            id=123,
            fetch_scheduled_event=AsyncMock(return_value=event_any),
        ),
    )
    server.bot = cast("Any", SimpleNamespace(get_guild=lambda guild_id: guild))

    request = cast(
        "web.Request",
        SimpleNamespace(match_info={"guild_id": "123", "event_id": "555"}),
    )

    response = await server.delete_guild_scheduled_event(request)

    assert response.status == 200
    payload = json.loads(response.text or "{}")
    assert payload["success"] is True
    event_any.delete.assert_awaited_once()
    assert invalidated_guilds == [123]


@pytest.mark.asyncio
async def test_delete_guild_scheduled_event_not_found() -> None:
    """Delete flow should return 404 when Discord scheduled event is missing."""
    server = object.__new__(InternalAPIServer)
    server.bot = cast("Any", object())
    server._check_auth = lambda request: True
    server._invalidate_events_cache = lambda guild_id: None

    guild = cast(
        "Any",
        SimpleNamespace(
            id=123,
            fetch_scheduled_event=AsyncMock(
                side_effect=discord.NotFound(
                    response=cast(
                        "Any", SimpleNamespace(status=404, reason="Not Found")
                    ),
                    message="Not Found",
                )
            ),
        ),
    )
    server.bot = cast("Any", SimpleNamespace(get_guild=lambda guild_id: guild))

    request = cast(
        "web.Request",
        SimpleNamespace(match_info={"guild_id": "123", "event_id": "555"}),
    )

    response = await server.delete_guild_scheduled_event(request)

    assert response.status == 404
    payload = json.loads(response.text or "{}")
    assert payload["error"] == "Scheduled event not found"
