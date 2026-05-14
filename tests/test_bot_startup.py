"""Tests for startup orchestration in the bot ready flow."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

import bot as bot_module
import bot_tasks
from bot import MyBot


@pytest.mark.asyncio
async def test_on_ready_chunks_guilds_concurrently() -> None:
    """Guild chunking should run concurrently during startup."""
    bot_instance = Mock(spec=MyBot)
    bot_instance.user = SimpleNamespace(id=123)
    bot_instance.guilds = [
        SimpleNamespace(id=1, name="Guild One"),
        SimpleNamespace(id=2, name="Guild Two"),
    ]
    bot_instance.check_bot_permissions = AsyncMock()

    started_guild_ids: list[int] = []
    all_started = asyncio.Event()

    async def chunk_guild(guild: SimpleNamespace) -> None:
        started_guild_ids.append(guild.id)
        if len(started_guild_ids) == 2:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=0.1)

    bot_instance._chunk_guild_members = AsyncMock(side_effect=chunk_guild)

    with patch.object(bot_tasks, "alert_prefix_warnings", new_callable=AsyncMock) as mock_alert:
        await cast("Any", MyBot).on_ready(bot_instance)
        mock_alert.assert_awaited_once_with(bot_instance)

    assert started_guild_ids == [1, 2]
    assert bot_instance.check_bot_permissions.await_count == 2


@pytest.mark.asyncio
async def test_alert_prefix_warnings_sends_per_guild_concurrently(monkeypatch) -> None:
    """Prefix warning sends should not serialize across guilds."""
    monkeypatch.setattr(bot_module, "PREFIX_WARNINGS", ["warning"])

    bot_instance = Mock(spec=MyBot)
    bot_instance.guilds = [
        SimpleNamespace(id=1, name="Guild One"),
        SimpleNamespace(id=2, name="Guild Two"),
    ]

    started_guild_ids: list[int] = []
    all_started = asyncio.Event()

    async def send_warning(bot: Any, guild: SimpleNamespace) -> None:
        started_guild_ids.append(guild.id)
        if len(started_guild_ids) == 2:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=0.1)

    with patch.object(bot_tasks, "send_prefix_warning_for_guild", side_effect=send_warning):
        await bot_tasks.alert_prefix_warnings(bot_instance)

    assert started_guild_ids == [1, 2]
