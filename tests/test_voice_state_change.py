import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.voice_service import VoiceService


class DummyChannel:
    def __init__(self, channel_id: int):
        self.id = channel_id


class DummyMember:
    def __init__(self, guild_id: int):
        self.id = 999
        self.guild = types.SimpleNamespace(id=guild_id)


@pytest.fixture
def voice_service():
    config_service = MagicMock()
    bot = MagicMock()
    service = VoiceService(config_service, bot=bot)
    return service


@pytest.mark.asyncio
async def test_voice_state_change_same_channel_does_not_trigger_jtc(voice_service):
    member = DummyMember(guild_id=12345)
    channel = DummyChannel(channel_id=555)

    voice_service._is_managed_channel = AsyncMock(return_value=False)
    voice_service._is_join_to_create_channel = AsyncMock(return_value=True)
    voice_service._handle_join_to_create = AsyncMock()

    await voice_service.handle_voice_state_change(member, channel, channel)

    voice_service._handle_join_to_create.assert_not_called()


@pytest.mark.asyncio
async def test_voice_state_change_new_jtc_channel_triggers_creation(voice_service):
    member = DummyMember(guild_id=54321)
    after_channel = DummyChannel(channel_id=222)

    voice_service._is_managed_channel = AsyncMock(return_value=False)
    voice_service._is_join_to_create_channel = AsyncMock(return_value=True)
    voice_service._handle_join_to_create = AsyncMock()

    # True join: before=None (user was not in voice), after=JTC channel
    await voice_service.handle_voice_state_change(member, None, after_channel)

    voice_service._handle_join_to_create.assert_awaited_once_with(
        member.guild, after_channel, member
    )


@pytest.mark.asyncio
async def test_voice_state_change_move_to_jtc_does_not_trigger(voice_service):
    """Test that moving from another channel to JTC does not trigger creation."""
    member = DummyMember(guild_id=54321)
    before_channel = DummyChannel(channel_id=111)
    after_channel = DummyChannel(channel_id=222)

    voice_service._is_managed_channel = AsyncMock(return_value=False)
    voice_service._is_join_to_create_channel = AsyncMock(return_value=True)
    voice_service._handle_join_to_create = AsyncMock()

    # Move between channels: before=channel, after=JTC (not a true join)
    await voice_service.handle_voice_state_change(member, before_channel, after_channel)

    # Should NOT trigger creation since before_channel is not None
    voice_service._handle_join_to_create.assert_not_called()
