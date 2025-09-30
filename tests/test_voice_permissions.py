"""
Tests for voice permissions and channel resolution functions.

This file contains tests for the voice permissions enforcement
and channel resolution functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.voice_permissions import (
    assert_base_permissions,
    enforce_permission_changes,
)
from helpers.voice_utils import get_user_channel


@pytest.mark.asyncio
async def test_assert_base_permissions() -> None:
    """Test that base permissions are properly asserted."""
    # Create mocks
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345
    channel.overwrites = {}

    bot_member = MagicMock(spec=discord.Member)
    owner_member = MagicMock(spec=discord.Member)
    default_role = MagicMock(spec=discord.Role)

    # Call the function
    await assert_base_permissions(channel, bot_member, owner_member, default_role)

    # Check that channel.edit was called with the correct overwrites
    channel.edit.assert_called_once()
    kwargs = channel.edit.call_args.kwargs
    assert "overwrites" in kwargs

    # Check that the overwrites contain the expected entries
    overwrites = kwargs["overwrites"]
    assert default_role in overwrites
    assert bot_member in overwrites
    assert owner_member in overwrites

    # Check the specific permissions
    assert overwrites[default_role].connect is True
    assert overwrites[default_role].use_voice_activation is True

    assert overwrites[bot_member].manage_channels is True
    assert overwrites[bot_member].connect is True

    assert overwrites[owner_member].manage_channels is True
    assert overwrites[owner_member].connect is True


@pytest.mark.asyncio
async def test_enforce_permission_changes() -> None:
    """Test that permissions are enforced properly."""
    # Create mocks
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345

    guild = MagicMock(spec=discord.Guild)
    guild.id = 98765

    bot = MagicMock(spec=discord.Client)
    bot.get_guild.return_value = guild

    owner_member = MagicMock(spec=discord.Member)
    bot_member = MagicMock(spec=discord.Member)
    default_role = MagicMock(spec=discord.Role)

    # Use get_me as a property instead of a method
    guild.me = bot_member
    guild.get_member.return_value = owner_member
    guild.default_role = default_role

    # Setup patch for assert_base_permissions
    with patch(
        "helpers.voice_permissions.assert_base_permissions", new=AsyncMock()
    ) as mock_assert:
        # Call the function
        await enforce_permission_changes(channel, bot, 1001, 98765, 101)

        # Check that the correct functions were called
        bot.get_guild.assert_called_once_with(98765)
        guild.get_member.assert_called_once_with(1001)

        # Check that assert_base_permissions was called with the correct arguments
        mock_assert.assert_called_once_with(
            channel, bot_member, owner_member, default_role
        )


@pytest.mark.asyncio
async def test_get_user_channel() -> None:
    """Test that get_user_channel properly orders by created_at
    when using legacy path."""
    # Create mock user
    user = MagicMock(spec=discord.abc.User)
    user.id = 1001

    # Create mock bot
    bot = MagicMock(spec=discord.Client)

    # Create mock channel
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 5001
    bot.get_channel.return_value = channel

    # Create mock db cursor and connection
    cursor = AsyncMock()
    cursor.fetchone.return_value = [5001]  # Return channel_id

    db = AsyncMock()
    db.execute.return_value = cursor

    # Setup a proper context manager for Database.get_connection
    cm = AsyncMock()
    cm.__aenter__.return_value = db
    cm.__aexit__.return_value = None

    with patch("helpers.voice_utils.Database.get_connection", return_value=cm):
        # Call with specific guild and JTC
        result = await get_user_channel(bot, user, 1, 101)
        assert result == channel

        # Check SQL query - should include is_active filter and ORDER BY LIMIT
        db.execute.assert_called_with(
            "SELECT voice_channel_id FROM voice_channels "
            "WHERE owner_id = ? AND guild_id = ? AND "
            "jtc_channel_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (1001, 1, 101),
        )

        # Reset mocks
        db.execute.reset_mock()

        # Call with only guild
        result = await get_user_channel(bot, user, 1)
        assert result == channel

        # Check SQL query - should include is_active filter and ORDER BY LIMIT
        db.execute.assert_called_with(
            "SELECT voice_channel_id FROM voice_channels "
            "WHERE owner_id = ? AND guild_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (1001, 1),
        )

        # Reset mocks
        db.execute.reset_mock()

        # Call with no specific guild or JTC (legacy path)
        result = await get_user_channel(bot, user)
        assert result == channel

        # Check SQL query - should include is_active filter and ORDER BY LIMIT
        db.execute.assert_called_with(
            "SELECT voice_channel_id FROM voice_channels "
            "WHERE owner_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (1001,),
        )
