"""Tests for the periodic Discord event sync service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.event_sync_service import EventSyncService
from web.backend.core.event_service import SyncResult


class FakeConfigService:
    """Minimal async config service stub for event sync tests."""

    def __init__(
        self,
        global_settings: dict[str, object] | None = None,
        guild_settings: dict[tuple[int, str], object] | None = None,
    ) -> None:
        self.global_settings = global_settings or {}
        self.guild_settings = guild_settings or {}

    async def get_global_setting(self, key: str, default: object = None) -> object:
        """Return one global setting."""
        return self.global_settings.get(key, default)

    async def get_guild_setting(
        self, guild_id: int, key: str, default: object = None
    ) -> object:
        """Return one guild-specific setting."""
        return self.guild_settings.get((guild_id, key), default)


@pytest.mark.asyncio
async def test_event_sync_service_initialize_starts_loop_when_enabled() -> None:
    """Initialization should start the background loop when sync is enabled."""
    # Arrange
    config_service = FakeConfigService(
        global_settings={
            "events.sync.enabled": True,
            "events.sync.interval_minutes": 60,
            "events.sync.per_guild_delay_seconds": 0,
            "events.sync.startup_delay_seconds": 3600,
        }
    )
    bot = SimpleNamespace(guilds=[])
    internal_api_client = AsyncMock()
    service = EventSyncService(config_service, bot, internal_api_client)

    # Act
    await service.initialize()

    # Assert
    health = await service.health_check()
    assert health["enabled"] is True
    assert health["has_loop_task"] is True

    await service.shutdown()


@pytest.mark.asyncio
async def test_event_sync_service_reconcile_pulls_only_enabled_guilds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconcile should pull only for guilds with the events module enabled."""
    # Arrange
    config_service = FakeConfigService(
        global_settings={
            "events.sync.enabled": False,
        },
        guild_settings={
            (1, "events.enabled"): True,
            (2, "events.enabled"): False,
            (3, "events.enabled"): True,
        },
    )
    bot = SimpleNamespace(
        guilds=[
            SimpleNamespace(id=1),
            SimpleNamespace(id=2),
            SimpleNamespace(id=3),
        ]
    )
    internal_api_client = AsyncMock()
    service = EventSyncService(config_service, bot, internal_api_client)
    manual_sync_mock = AsyncMock(return_value=(SyncResult(processed=2, updated=1), []))
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "services.event_sync_service.EventService.manual_sync",
        manual_sync_mock,
    )
    monkeypatch.setattr("services.event_sync_service.asyncio.sleep", sleep_mock)

    await service.initialize()

    # Act
    await service.reconcile_all_guilds()

    # Assert
    assert manual_sync_mock.await_count == 2
    assert manual_sync_mock.await_args_list[0].kwargs["guild_id"] == 1
    assert manual_sync_mock.await_args_list[0].kwargs["direction"] == "pull"
    assert manual_sync_mock.await_args_list[1].kwargs["guild_id"] == 3
    sleep_mock.assert_awaited_once()

    await service.shutdown()
