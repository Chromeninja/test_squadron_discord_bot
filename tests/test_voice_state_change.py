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
        member.guild, after_channel, member, bypass_cooldown=False
    )


@pytest.mark.asyncio
async def test_voice_state_change_move_to_jtc_triggers_creation(voice_service):
    """Moving from any channel to JTC should trigger creation (not same-channel reconnect)."""
    member = DummyMember(guild_id=54321)
    before_channel = DummyChannel(channel_id=111)
    after_channel = DummyChannel(channel_id=222)

    voice_service._is_managed_channel = AsyncMock(return_value=False)
    voice_service._is_join_to_create_channel = AsyncMock(return_value=True)
    voice_service._handle_join_to_create = AsyncMock()

    # Move between channels: before=channel, after=JTC (should create)
    await voice_service.handle_voice_state_change(member, before_channel, after_channel)

    voice_service._handle_join_to_create.assert_awaited_once_with(
        member.guild, after_channel, member, bypass_cooldown=False
    )


@pytest.mark.asyncio
async def test_voice_state_change_jtc_to_jtc_triggers_creation(voice_service):
    """Moving from one JTC channel to another should also trigger creation."""
    member = DummyMember(guild_id=54321)
    before_channel = DummyChannel(channel_id=111)
    after_channel = DummyChannel(channel_id=222)

    # Both channels are JTC
    voice_service._is_managed_channel = AsyncMock(return_value=False)
    voice_service._is_join_to_create_channel = AsyncMock(side_effect=[True, True])
    voice_service._handle_join_to_create = AsyncMock()

    await voice_service.handle_voice_state_change(member, before_channel, after_channel)

    voice_service._handle_join_to_create.assert_awaited_once_with(
        member.guild, after_channel, member, bypass_cooldown=False
    )


@pytest.mark.asyncio
async def test_voice_state_change_managed_to_jtc_bypasses_cooldown(voice_service):
    """Moving from managed channel back to JTC should bypass cooldown."""
    member = DummyMember(guild_id=54321)
    member.display_name = "TestUser"  # Add display_name for logging
    before_channel = DummyChannel(channel_id=111)
    before_channel.name = "Managed Channel"  # Add name for logging
    before_channel.members = []  # Empty members list for cleanup check
    after_channel = DummyChannel(channel_id=222)

    # Mark the channel the user is leaving as managed so cooldown is bypassed
    # Called twice: once for _handle_channel_left, once for bypass_cooldown check
    voice_service._is_managed_channel = AsyncMock(side_effect=[True, True])
    voice_service._is_join_to_create_channel = AsyncMock(return_value=True)
    voice_service._handle_join_to_create = AsyncMock()
    voice_service._cleanup_empty_channel = AsyncMock()  # Mock cleanup to avoid DB calls

    await voice_service.handle_voice_state_change(member, before_channel, after_channel)

    voice_service._handle_join_to_create.assert_awaited_once_with(
        member.guild, after_channel, member, bypass_cooldown=True
    )
