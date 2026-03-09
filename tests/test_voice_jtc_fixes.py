"""
Tests for JTC voice channel bug fixes.

Covers:
- Fix 1: _validate_jtc_permissions checks manage_roles
- Fix 2: Per-overwrite Forbidden fallback in _create_user_channel
- Fix 4: asyncio.sleep(0) yield before re-check in _handle_channel_left
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from services.config_service import ConfigService
from services.voice_service import VoiceService


def _make_voice_service() -> VoiceService:
    """Create a minimal VoiceService for unit testing."""
    config_service = MagicMock(spec=ConfigService)
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 99999
    service = VoiceService(config_service, bot, test_mode=True)
    service._initialized = True
    return service


# ======================================================================
# Fix 1: _validate_jtc_permissions now checks manage_roles
# ======================================================================


@pytest.mark.asyncio
async def test_validate_jtc_missing_manage_roles() -> None:
    """Should fail when bot lacks manage_roles (Manage Permissions) in category."""
    # Arrange
    service = _make_voice_service()

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100
    category.name = "Voice"

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.name = "TestGuild"
    category.guild = guild

    bot_member = MagicMock(spec=discord.Member)
    guild.get_member.return_value = bot_member

    # Bot has manage_channels but NOT manage_roles
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = False
    category.permissions_for.return_value = perms

    guild_perms = MagicMock()
    guild_perms.move_members = True
    bot_member.guild_permissions = guild_perms

    # Act
    ok, error = await service._validate_jtc_permissions(category)

    # Assert
    assert ok is False
    assert error is not None
    assert "Manage Permissions" in error


@pytest.mark.asyncio
async def test_validate_jtc_passes_with_all_perms() -> None:
    """Should pass when bot has manage_channels, manage_roles, and move_members."""
    # Arrange
    service = _make_voice_service()

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100
    category.name = "Voice"

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.name = "TestGuild"
    category.guild = guild

    bot_member = MagicMock(spec=discord.Member)
    guild.get_member.return_value = bot_member

    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    category.permissions_for.return_value = perms

    guild_perms = MagicMock()
    guild_perms.move_members = True
    bot_member.guild_permissions = guild_perms

    # Act
    ok, error = await service._validate_jtc_permissions(category)

    # Assert
    assert ok is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_jtc_missing_manage_channels() -> None:
    """Should fail when bot lacks manage_channels, before checking manage_roles."""
    # Arrange
    service = _make_voice_service()

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100
    category.name = "Voice"

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    category.guild = guild

    bot_member = MagicMock(spec=discord.Member)
    guild.get_member.return_value = bot_member

    perms = MagicMock()
    perms.manage_channels = False
    perms.manage_roles = True
    category.permissions_for.return_value = perms

    # Act
    ok, error = await service._validate_jtc_permissions(category)

    # Assert
    assert ok is False
    assert error is not None
    assert "Manage Channels" in error


# ======================================================================
# Fix 4: _handle_channel_left yields to event loop before re-check
# ======================================================================


@pytest.mark.asyncio
async def test_handle_channel_left_yields_before_recheck() -> None:
    """After finding channel empty, should yield then re-check count."""
    # Arrange
    service = _make_voice_service()
    service.debug_logging_enabled = False

    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 5001
    channel.name = "test-channel"

    member = MagicMock(spec=discord.Member)
    member.display_name = "TestUser"

    # First call returns 0 (empty), second call returns 1 (someone joined)
    mock_count = MagicMock(side_effect=[0, 1])
    mock_cleanup = AsyncMock()

    # Act
    with (
        patch.object(service, "_get_member_count", mock_count),
        patch.object(service, "_cleanup_empty_channel", mock_cleanup),
        patch("services.voice_service.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        await service._handle_channel_left(channel, member)

    # Assert — yielded to event loop
    mock_sleep.assert_awaited_once_with(0)

    # Assert — checked count twice
    assert mock_count.call_count == 2

    # Assert — did NOT clean up because second check found a member
    mock_cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_channel_left_cleans_up_when_still_empty() -> None:
    """Should clean up when channel is empty both before and after yield."""
    # Arrange
    service = _make_voice_service()
    service.debug_logging_enabled = False

    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 5001
    channel.name = "test-channel"

    member = MagicMock(spec=discord.Member)
    member.display_name = "TestUser"

    # Both checks return 0
    mock_count = MagicMock(side_effect=[0, 0])
    mock_cleanup = AsyncMock()

    # Act
    with (
        patch.object(service, "_get_member_count", mock_count),
        patch.object(service, "_cleanup_empty_channel", mock_cleanup),
        patch("services.voice_service.asyncio.sleep", new=AsyncMock()),
    ):
        await service._handle_channel_left(channel, member)

    # Assert — cleanup was called
    mock_cleanup.assert_awaited_once_with(channel)


@pytest.mark.asyncio
async def test_handle_channel_left_skips_yield_when_not_empty() -> None:
    """If channel has members after first check, should skip yield and cleanup."""
    # Arrange
    service = _make_voice_service()
    service.debug_logging_enabled = True

    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 5001
    channel.name = "test-channel"

    member = MagicMock(spec=discord.Member)
    member.display_name = "TestUser"

    # First check: channel still has members
    mock_count = MagicMock(return_value=2)
    mock_cleanup = AsyncMock()

    # Act
    with (
        patch.object(service, "_get_member_count", mock_count),
        patch.object(service, "_cleanup_empty_channel", mock_cleanup),
        patch("services.voice_service.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        await service._handle_channel_left(channel, member)

    # Assert — no sleep, no cleanup
    mock_sleep.assert_not_awaited()
    mock_cleanup.assert_not_awaited()


# ======================================================================
# Fix 2: Per-overwrite Forbidden fallback in channel creation
# ======================================================================


@pytest.mark.asyncio
async def test_create_user_channel_falls_back_per_overwrite() -> None:
    """When bulk create raises Forbidden, should create bare then apply each overwrite."""
    # Arrange
    service = _make_voice_service()
    service.debug_logging_enabled = True

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.name = "TestGuild"

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100
    category.name = "Voice"
    category.guild = guild

    jtc_channel = MagicMock(spec=discord.VoiceChannel)
    jtc_channel.id = 200
    jtc_channel.name = "Join to Create"
    jtc_channel.bitrate = 64000
    jtc_channel.user_limit = 0
    jtc_channel.category = category

    member = MagicMock(spec=discord.Member)
    member.id = 1001
    member.display_name = "TestUser"
    member.guild = guild
    member.voice = MagicMock()
    member.voice.channel = MagicMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_top_role = MagicMock(spec=discord.Role)
    bot_top_role.position = 10
    bot_member.top_role = bot_top_role
    guild.get_member.return_value = bot_member

    bot_category_perms = discord.Permissions.all()
    category.permissions_for.return_value = bot_category_perms

    # JTC channel has one overwrite — lower than bot role
    role_a = MagicMock(spec=discord.Role)
    role_a.position = 2
    role_a.name = "RoleA"
    role_a.__ge__ = lambda self, other: self.position >= other.position

    jtc_channel.overwrites = {
        role_a: discord.PermissionOverwrite(connect=True),
    }

    # First create_voice_channel call raises Forbidden, second succeeds
    bare_channel = AsyncMock(spec=discord.VoiceChannel)
    bare_channel.id = 9001
    guild.create_voice_channel = AsyncMock(
        side_effect=[discord.Forbidden(MagicMock(), "missing perms"), bare_channel]
    )

    # Act — call _create_user_channel directly
    with (
        patch("services.voice_service.enforce_permission_changes", new=AsyncMock()),
        patch.object(service, "_store_user_channel", new=AsyncMock()),
        patch.object(
            service,
            "_validate_jtc_permissions",
            new=AsyncMock(return_value=(True, None)),
        ),
        patch.object(
            service, "_load_channel_settings", new=AsyncMock(return_value=None)
        ),
        patch.object(service, "_update_cooldown", new=AsyncMock()),
        patch.object(service, "_send_settings_message_to_vc", new=AsyncMock()),
        patch(
            "services.voice_service.update_last_used_jtc_channel",
            new=AsyncMock(),
        ),
    ):
        result = await service._create_user_channel(guild, jtc_channel, member)

    # Assert — two create_voice_channel calls (first failed, second bare)
    assert guild.create_voice_channel.call_count == 2

    # Second call should NOT have overwrites (bare channel)
    second_call_kwargs = guild.create_voice_channel.call_args_list[1].kwargs
    assert "overwrites" not in second_call_kwargs

    # Per-overwrite set_permissions should have been called on the bare channel
    bare_channel.set_permissions.assert_called()
    assert result is not None
