"""
Tests for the MetricsEvents cog.

Tests cover:
- on_message ignores bots and DMs
- on_message records to metrics service
- on_voice_state_update detects join/leave/move
- on_presence_update detects game start/stop
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.metrics.events import MetricsEvents

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_metrics_service():
    """Create a mock MetricsService."""
    service = AsyncMock()
    service.record_message = MagicMock()
    service.record_voice_join = AsyncMock()
    service.record_voice_leave = AsyncMock()
    service.record_game_start = AsyncMock()
    service.record_game_stop = AsyncMock()
    service.get_excluded_channel_ids = AsyncMock(return_value=set())
    return service


@pytest.fixture
def cog_with_service(mock_metrics_service):
    """Create a MetricsEvents cog with a mocked service."""
    bot = MagicMock()
    bot.services = SimpleNamespace(metrics=mock_metrics_service)
    cog = MetricsEvents(bot)
    return cog, mock_metrics_service


# ---------------------------------------------------------------------------
# on_message tests
# ---------------------------------------------------------------------------


class TestOnMessage:
    @pytest.mark.asyncio
    async def test_records_guild_message(self, cog_with_service):
        cog, service = cog_with_service
        msg = MagicMock()
        msg.author.bot = False
        msg.guild = MagicMock()
        msg.guild.id = 100
        msg.author.id = 1
        msg.channel.id = 55

        await cog.on_message(msg)

        service.record_message.assert_called_once_with(100, 1, channel_id=55)

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self, cog_with_service):
        cog, service = cog_with_service
        msg = MagicMock()
        msg.author.bot = True

        await cog.on_message(msg)

        service.record_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_dm_messages(self, cog_with_service):
        cog, service = cog_with_service
        msg = MagicMock()
        msg.author.bot = False
        msg.guild = None

        await cog.on_message(msg)

        service.record_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_excluded_channel_messages(self, cog_with_service):
        cog, service = cog_with_service
        service.get_excluded_channel_ids.return_value = {77}
        msg = MagicMock()
        msg.author.bot = False
        msg.guild = MagicMock()
        msg.guild.id = 100
        msg.author.id = 1
        msg.channel.id = 77

        await cog.on_message(msg)

        service.record_message.assert_not_called()


# ---------------------------------------------------------------------------
# on_voice_state_update tests
# ---------------------------------------------------------------------------


def _make_voice_state(
    channel: MagicMock | None = None,
    *,
    self_mute: bool = False,
    self_deaf: bool = False,
) -> MagicMock:
    """Build a ``discord.VoiceState``-like mock with explicit mute/deaf flags."""
    state = MagicMock()
    state.channel = channel
    state.self_mute = self_mute
    state.self_deaf = self_deaf
    return state


def _make_channel(channel_id: int = 10) -> MagicMock:
    """Build a minimal voice channel mock."""
    ch = MagicMock()
    ch.id = channel_id
    return ch


class TestOnVoiceStateUpdate:
    @pytest.mark.asyncio
    async def test_join_records(self, cog_with_service):
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=None)
        after = _make_voice_state(channel=_make_channel(10))

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_called_once_with(100, 1, 10)

    @pytest.mark.asyncio
    async def test_leave_records(self, cog_with_service):
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=_make_channel(10))
        after = _make_voice_state(channel=None)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_leave.assert_called_once_with(100, 1)

    @pytest.mark.asyncio
    async def test_move_records_leave_and_join(self, cog_with_service):
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=_make_channel(10))
        after = _make_voice_state(channel=_make_channel(20))

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_leave.assert_called_once_with(100, 1)
        service.record_voice_join.assert_called_once_with(100, 1, 20)

    @pytest.mark.asyncio
    async def test_ignores_bots(self, cog_with_service):
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = True

        await cog.on_voice_state_update(
            member,
            _make_voice_state(channel=None),
            _make_voice_state(channel=None),
        )

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_channel_unmuted_no_action(self, cog_with_service):
        """Staying in the same channel while already eligible is a no-op."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        channel = _make_channel(10)
        before = _make_voice_state(channel=channel)
        after = _make_voice_state(channel=channel)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_excluded_channel_no_record(self, cog_with_service):
        cog, service = cog_with_service
        service.get_excluded_channel_ids.return_value = {10}
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=None)
        after = _make_voice_state(channel=_make_channel(10))

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()

    @pytest.mark.asyncio
    async def test_move_to_excluded_channel_only_records_leave(self, cog_with_service):
        cog, service = cog_with_service
        service.get_excluded_channel_ids.return_value = {20}
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=_make_channel(10))
        after = _make_voice_state(channel=_make_channel(20))

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_leave.assert_called_once_with(100, 1)
        service.record_voice_join.assert_not_called()

    # ---------------------------------------------------------------
    # Self-mute / self-deaf eligibility transitions
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_self_mute_triggers_leave(self, cog_with_service):
        """Toggling self-mute ON in the same channel closes the session."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        channel = _make_channel(10)
        before = _make_voice_state(channel=channel, self_mute=False)
        after = _make_voice_state(channel=channel, self_mute=True)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_leave.assert_called_once_with(100, 1)
        service.record_voice_join.assert_not_called()

    @pytest.mark.asyncio
    async def test_self_unmute_triggers_join(self, cog_with_service):
        """Toggling self-mute OFF in the same channel opens a session."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        channel = _make_channel(10)
        before = _make_voice_state(channel=channel, self_mute=True)
        after = _make_voice_state(channel=channel, self_mute=False)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_called_once_with(100, 1, 10)
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_self_deaf_triggers_leave(self, cog_with_service):
        """Toggling self-deaf ON in the same channel closes the session."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        channel = _make_channel(10)
        before = _make_voice_state(channel=channel, self_deaf=False)
        after = _make_voice_state(channel=channel, self_deaf=True)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_leave.assert_called_once_with(100, 1)
        service.record_voice_join.assert_not_called()

    @pytest.mark.asyncio
    async def test_self_undeaf_triggers_join(self, cog_with_service):
        """Toggling self-deaf OFF in the same channel opens a session."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        channel = _make_channel(10)
        before = _make_voice_state(channel=channel, self_deaf=True)
        after = _make_voice_state(channel=channel, self_deaf=False)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_called_once_with(100, 1, 10)
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_while_self_muted_no_session(self, cog_with_service):
        """Joining a channel while self-muted does not open a session."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=None)
        after = _make_voice_state(channel=_make_channel(10), self_mute=True)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_while_self_deafened_no_session(self, cog_with_service):
        """Joining a channel while self-deafened does not open a session."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=None)
        after = _make_voice_state(channel=_make_channel(10), self_deaf=True)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_move_while_muted_no_session(self, cog_with_service):
        """Moving channels while self-muted does not open or close sessions."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=_make_channel(10), self_mute=True)
        after = _make_voice_state(channel=_make_channel(20), self_mute=True)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_leave_while_muted_no_leave(self, cog_with_service):
        """Leaving voice while already self-muted has no session to close."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        before = _make_voice_state(channel=_make_channel(10), self_mute=True)
        after = _make_voice_state(channel=None)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()

    @pytest.mark.asyncio
    async def test_muted_to_muted_same_channel_no_action(self, cog_with_service):
        """Remaining muted in the same channel is a no-op."""
        cog, service = cog_with_service
        member = MagicMock()
        member.bot = False
        member.guild.id = 100
        member.id = 1

        channel = _make_channel(10)
        before = _make_voice_state(channel=channel, self_mute=True)
        after = _make_voice_state(channel=channel, self_mute=True)

        await cog.on_voice_state_update(member, before, after)

        service.record_voice_join.assert_not_called()
        service.record_voice_leave.assert_not_called()


# ---------------------------------------------------------------------------
# on_presence_update tests
# ---------------------------------------------------------------------------


class TestOnPresenceUpdate:
    def _make_member(self, guild_id=100, user_id=1, bot=False, activities=None):
        member = MagicMock()
        member.bot = bot
        member.guild = MagicMock()
        member.guild.id = guild_id
        member.id = user_id
        member.activities = activities or []
        return member

    def _game_activity(self, name="Star Citizen"):
        act = MagicMock()
        act.type = discord.ActivityType.playing
        act.name = name
        return act

    def _custom_activity(self, name="Chilling"):
        act = MagicMock()
        act.type = discord.ActivityType.custom
        act.name = name
        return act

    @pytest.mark.asyncio
    async def test_game_start(self, cog_with_service):
        cog, service = cog_with_service
        before = self._make_member(activities=[])
        after = self._make_member(activities=[self._game_activity("Star Citizen")])

        await cog.on_presence_update(before, after)

        service.record_game_start.assert_called_once_with(100, 1, "Star Citizen")

    @pytest.mark.asyncio
    async def test_game_stop(self, cog_with_service):
        cog, service = cog_with_service
        before = self._make_member(activities=[self._game_activity("Star Citizen")])
        after = self._make_member(activities=[])

        await cog.on_presence_update(before, after)

        service.record_game_stop.assert_called_once_with(100, 1)

    @pytest.mark.asyncio
    async def test_game_switch(self, cog_with_service):
        cog, service = cog_with_service
        before = self._make_member(activities=[self._game_activity("Star Citizen")])
        after = self._make_member(activities=[self._game_activity("EVE Online")])

        await cog.on_presence_update(before, after)

        service.record_game_stop.assert_called_once_with(100, 1)
        service.record_game_start.assert_called_once_with(100, 1, "EVE Online")

    @pytest.mark.asyncio
    async def test_ignores_bots(self, cog_with_service):
        cog, service = cog_with_service
        before = self._make_member(bot=True)
        after = self._make_member(bot=True, activities=[self._game_activity()])

        await cog.on_presence_update(before, after)

        service.record_game_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_game_activity_change(self, cog_with_service):
        """Non-game activity changes should not trigger anything."""
        cog, service = cog_with_service
        before = self._make_member(activities=[self._custom_activity()])
        after = self._make_member(activities=[self._custom_activity()])

        await cog.on_presence_update(before, after)

        service.record_game_start.assert_not_called()
        service.record_game_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_game_no_action(self, cog_with_service):
        """Same game before and after should not trigger start/stop."""
        cog, service = cog_with_service
        game = self._game_activity("Star Citizen")
        before = self._make_member(activities=[game])
        after = self._make_member(activities=[self._game_activity("Star Citizen")])

        await cog.on_presence_update(before, after)

        service.record_game_start.assert_not_called()
        service.record_game_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_stops_game_when_in_excluded_voice_channel(self, cog_with_service):
        cog, service = cog_with_service
        service.get_excluded_channel_ids.return_value = {99}
        before = self._make_member(activities=[self._game_activity("Star Citizen")])
        after = self._make_member(activities=[self._game_activity("Star Citizen")])
        after.voice = MagicMock()
        after.voice.channel = MagicMock()
        after.voice.channel.id = 99

        await cog.on_presence_update(before, after)

        service.record_game_stop.assert_called_once_with(100, 1)
        service.record_game_start.assert_not_called()
