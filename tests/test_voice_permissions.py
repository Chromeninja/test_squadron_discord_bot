"""
Tests for voice permissions and channel resolution functions.

This file contains tests for the voice permissions enforcement
and channel resolution functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.voice_permissions import (
    _apply_lock_setting,
    _get_hierarchy_blocking_roles,
    assert_base_permissions,
    enforce_permission_changes,
)
from helpers.voice_utils import get_user_channel
from services.voice_service import VoiceService


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
    assert overwrites[bot_member].move_members is True
    assert overwrites[bot_member].view_channel is True

    # Owner only gets connect - channel management is via bot commands
    assert overwrites[owner_member].connect is True


@pytest.mark.asyncio
async def test_enforce_permission_changes() -> None:
    """Test that permissions are enforced in a single consolidated API call."""
    # Arrange
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345
    channel.overwrites = {}

    guild = MagicMock(spec=discord.Guild)
    guild.id = 98765

    bot = MagicMock(spec=discord.Client)
    bot.get_guild.return_value = guild

    owner_member = MagicMock(spec=discord.Member)
    bot_member = MagicMock(spec=discord.Member)
    default_role = MagicMock(spec=discord.Role)

    guild.me = bot_member
    guild.get_member.return_value = owner_member
    guild.default_role = default_role

    # Patch DB helpers to return no settings (base-only test)
    with (
        patch(
            "helpers.voice_permissions._apply_permit_reject_settings",
            new=AsyncMock(),
        ),
        patch(
            "helpers.voice_permissions._apply_voice_feature_settings",
            new=AsyncMock(),
        ),
        patch(
            "helpers.voice_permissions._apply_lock_setting",
            new=AsyncMock(),
        ),
    ):
        # Act
        await enforce_permission_changes(channel, bot, 1001, 98765, 101)

    # Assert — guild and member lookups happened
    bot.get_guild.assert_called_once_with(98765)
    guild.get_member.assert_called_once_with(1001)

    # Assert — single channel.edit call with consolidated overwrites
    channel.edit.assert_called_once()
    overwrites = channel.edit.call_args.kwargs["overwrites"]
    assert default_role in overwrites
    assert bot_member in overwrites
    assert owner_member in overwrites

    # Verify base permission values
    assert overwrites[default_role].connect is True
    assert overwrites[default_role].use_voice_activation is True
    assert overwrites[bot_member].manage_channels is True
    assert overwrites[bot_member].connect is True
    assert overwrites[bot_member].move_members is True
    assert overwrites[bot_member].view_channel is True
    assert overwrites[owner_member].connect is True


@pytest.mark.asyncio
async def test_get_user_channel() -> None:
    """Test that get_user_channel orders by created_at across scope variants."""
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

    # Setup a proper context manager for BaseRepository.transaction
    cm = AsyncMock()
    cm.__aenter__.return_value = db
    cm.__aexit__.return_value = None

    with patch("helpers.voice_utils.BaseRepository.transaction", return_value=cm):
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

        # Call with no specific guild or JTC (unscoped path)
        result = await get_user_channel(bot, user)
        assert result == channel

        # Check SQL query - should include is_active filter and ORDER BY LIMIT
        db.execute.assert_called_with(
            "SELECT voice_channel_id FROM voice_channels "
            "WHERE owner_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (1001,),
        )


@pytest.mark.asyncio
async def test_assert_base_permissions_merges_existing() -> None:
    """Test that base permissions merge with existing overwrites.

    When a channel already has JTC-inherited overwrites (e.g. speak=False
    on @everyone), assert_base_permissions should preserve those while
    adding the required base fields (connect, use_voice_activation).
    """
    # Arrange
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345

    bot_member = MagicMock(spec=discord.Member)
    owner_member = MagicMock(spec=discord.Member)
    default_role = MagicMock(spec=discord.Role)
    custom_role = MagicMock(spec=discord.Role)

    # Pre-existing overwrites from JTC channel copy
    existing_default = discord.PermissionOverwrite(speak=False, stream=False)
    existing_custom = discord.PermissionOverwrite(connect=False)
    channel.overwrites = {
        default_role: existing_default,
        custom_role: existing_custom,
    }

    # Act
    await assert_base_permissions(channel, bot_member, owner_member, default_role)

    # Assert
    channel.edit.assert_called_once()
    overwrites = channel.edit.call_args.kwargs["overwrites"]

    # default_role: base fields merged, JTC fields preserved
    assert overwrites[default_role].connect is True
    assert overwrites[default_role].use_voice_activation is True
    assert overwrites[default_role].speak is False  # preserved from JTC
    assert overwrites[default_role].stream is False  # preserved from JTC

    # bot_member: base fields set
    assert overwrites[bot_member].manage_channels is True
    assert overwrites[bot_member].connect is True
    assert overwrites[bot_member].move_members is True
    assert overwrites[bot_member].view_channel is True

    # owner_member: base fields set
    assert overwrites[owner_member].connect is True

    # custom_role: untouched by assert_base_permissions
    assert overwrites[custom_role].connect is False


@pytest.mark.asyncio
async def test_assert_base_permissions_empty_channel() -> None:
    """Test assert_base_permissions on a channel with no existing overwrites."""
    # Arrange
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 99999
    channel.overwrites = {}

    bot_member = MagicMock(spec=discord.Member)
    owner_member = MagicMock(spec=discord.Member)
    default_role = MagicMock(spec=discord.Role)

    # Act
    await assert_base_permissions(channel, bot_member, owner_member, default_role)

    # Assert
    channel.edit.assert_called_once()
    overwrites = channel.edit.call_args.kwargs["overwrites"]

    assert len(overwrites) == 3
    assert overwrites[default_role].connect is True
    assert overwrites[default_role].use_voice_activation is True
    assert overwrites[bot_member].manage_channels is True
    assert overwrites[bot_member].connect is True
    assert overwrites[bot_member].move_members is True
    assert overwrites[bot_member].view_channel is True
    assert overwrites[owner_member].connect is True


def test_get_hierarchy_blocking_roles_detects_conflicts() -> None:
    """Detect role overwrites blocked by bot role hierarchy."""
    # Arrange
    default_role = MagicMock(spec=discord.Role)
    default_role.id = 1
    default_role.name = "@everyone"
    default_role.position = 0

    bot_top_role = MagicMock(spec=discord.Role)
    bot_top_role.position = 10

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = bot_top_role

    low_role = MagicMock(spec=discord.Role)
    low_role.id = 2
    low_role.name = "LowRole"
    low_role.position = 2

    equal_role = MagicMock(spec=discord.Role)
    equal_role.id = 3
    equal_role.name = "EqualRole"
    equal_role.position = 10

    high_role = MagicMock(spec=discord.Role)
    high_role.id = 4
    high_role.name = "HighRole"
    high_role.position = 12

    overwrites: dict[object, discord.PermissionOverwrite] = {
        default_role: discord.PermissionOverwrite(),
        low_role: discord.PermissionOverwrite(),
        equal_role: discord.PermissionOverwrite(),
        high_role: discord.PermissionOverwrite(),
    }

    # Act
    blocked_roles = _get_hierarchy_blocking_roles(
        overwrites,
        bot_member,
        default_role,
    )

    # Assert
    assert blocked_roles == ["EqualRole", "HighRole"]


@pytest.mark.asyncio
async def test_assert_base_permissions_uses_set_permissions_when_hierarchy_blocks() -> (
    None
):
    """Use per-target set_permissions when blocking roles exist on channel."""
    # Arrange
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345

    default_role = MagicMock(spec=discord.Role)
    default_role.id = 1
    default_role.name = "@everyone"
    default_role.position = 0

    blocking_role = MagicMock(spec=discord.Role)
    blocking_role.id = 2
    blocking_role.name = "Admins"
    blocking_role.position = 10

    # Make __ge__ work for hierarchy detection
    default_role.__ge__ = lambda self, other: self.position >= other.position
    blocking_role.__ge__ = lambda self, other: self.position >= other.position

    channel.overwrites = {
        default_role: discord.PermissionOverwrite(),
        blocking_role: discord.PermissionOverwrite(),
    }

    bot_top_role = MagicMock(spec=discord.Role)
    bot_top_role.position = 10

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = bot_top_role

    owner_member = MagicMock(spec=discord.Member)

    # Act
    await assert_base_permissions(channel, bot_member, owner_member, default_role)

    # Assert — channel.edit NOT called (would wipe blocking role overwrites)
    channel.edit.assert_not_called()
    # Instead, set_permissions called for each base target
    assert channel.set_permissions.call_count == 3
    targets_set = [call.args[0] for call in channel.set_permissions.call_args_list]
    assert default_role in targets_set
    assert bot_member in targets_set
    assert owner_member in targets_set


@pytest.mark.asyncio
async def test_permission_precedence_lock_overrides_base() -> None:
    """Test that DB lock setting overrides base connect=True for @everyone.

    Layering: JTC overwrites → base perms (connect=True) → DB lock (connect=False).
    Final result for @everyone should be connect=False.
    """
    # Arrange
    default_role = MagicMock(spec=discord.Role)

    # Build overwrites dict as it would look after assert_base_permissions
    overwrites: dict = {
        default_role: discord.PermissionOverwrite(
            connect=True, use_voice_activation=True
        ),
    }

    guild = MagicMock(spec=discord.Guild)
    guild.default_role = default_role

    user_id = 1001
    guild_id = 98765
    jtc_channel_id = 101

    # Mock DB returning lock=1
    with patch(
        "helpers.voice_permissions.BaseRepository.fetch_one",
        new=AsyncMock(return_value=(1,)),
    ):
        # Act
        await _apply_lock_setting(overwrites, guild, user_id, guild_id, jtc_channel_id)

    # Assert — lock should override connect to False
    assert overwrites[default_role].connect is False
    # use_voice_activation untouched
    assert overwrites[default_role].use_voice_activation is True


@pytest.mark.asyncio
async def test_permission_precedence_no_lock() -> None:
    """Test that without a lock row, base connect=True remains."""
    # Arrange
    default_role = MagicMock(spec=discord.Role)
    overwrites: dict = {
        default_role: discord.PermissionOverwrite(
            connect=True, use_voice_activation=True
        ),
    }
    guild = MagicMock(spec=discord.Guild)
    guild.default_role = default_role

    # Mock DB returning no row
    with patch(
        "helpers.voice_permissions.BaseRepository.fetch_one",
        new=AsyncMock(return_value=None),
    ):
        await _apply_lock_setting(overwrites, guild, 1001, 98765, 101)

    # Assert — connect stays True
    assert overwrites[default_role].connect is True


# ======================================================================
# Tests for VoiceService._sanitize_overwrite (Fix 3)
# ======================================================================


class TestSanitizeOverwrite:
    """Tests for VoiceService._sanitize_overwrite static method."""

    def test_strips_allow_bits_bot_lacks(self) -> None:
        """Overwrite allow bits the bot doesn't have should be stripped."""
        # Arrange — overwrite allows manage_channels + connect,
        # but bot only has connect in the category.
        overwrite = discord.PermissionOverwrite(manage_channels=True, connect=True)
        bot_perms = discord.Permissions(connect=True)

        # Act
        result = VoiceService._sanitize_overwrite(overwrite, bot_perms)

        # Assert — manage_channels stripped, connect preserved
        allow, deny = result.pair()
        assert allow.connect is True
        assert allow.manage_channels is False
        assert deny.value == 0  # no deny bits

    def test_preserves_deny_bits_unconditionally(self) -> None:
        """Deny bits should never be stripped, even if bot lacks the permission."""
        # Arrange — deny speak, bot doesn't have speak
        overwrite = discord.PermissionOverwrite(speak=False)
        bot_perms = discord.Permissions.none()

        # Act
        result = VoiceService._sanitize_overwrite(overwrite, bot_perms)

        # Assert — deny preserved
        allow, deny = result.pair()
        assert deny.speak is True  # "deny" Permissions has speak=True means denied
        assert allow.value == 0

    def test_passthrough_when_bot_has_all_perms(self) -> None:
        """When bot has all perms, the overwrite should pass through unchanged."""
        # Arrange
        overwrite = discord.PermissionOverwrite(
            connect=True, speak=True, manage_channels=True
        )
        bot_perms = discord.Permissions.all()

        # Act
        result = VoiceService._sanitize_overwrite(overwrite, bot_perms)

        # Assert — all allow bits preserved
        allow, _deny = result.pair()
        assert allow.connect is True
        assert allow.speak is True
        assert allow.manage_channels is True

    def test_empty_overwrite_stays_empty(self) -> None:
        """Empty overwrite should remain empty after sanitization."""
        overwrite = discord.PermissionOverwrite()
        bot_perms = discord.Permissions(connect=True)

        result = VoiceService._sanitize_overwrite(overwrite, bot_perms)

        allow, deny = result.pair()
        assert allow.value == 0
        assert deny.value == 0

    def test_mixed_allow_deny_preserves_deny(self) -> None:
        """Overwrite with both allow and deny bits — only allow is filtered."""
        # Arrange — allow connect+speak, deny stream; bot only has connect
        overwrite = discord.PermissionOverwrite(connect=True, speak=True, stream=False)
        bot_perms = discord.Permissions(connect=True)

        # Act
        result = VoiceService._sanitize_overwrite(overwrite, bot_perms)

        # Assert
        allow, deny = result.pair()
        assert allow.connect is True
        assert allow.speak is False  # stripped — bot lacks speak
        assert deny.stream is True  # deny preserved


# ======================================================================
# Tests for enforce_permission_changes with DB settings (Fix 5)
# ======================================================================


@pytest.mark.asyncio
async def test_enforce_merges_lock_into_single_call() -> None:
    """Lock setting should override @everyone connect in the same API call."""
    # Arrange
    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345
    channel.overwrites = {}

    guild = MagicMock(spec=discord.Guild)
    guild.id = 98765

    bot = MagicMock(spec=discord.Client)
    bot.get_guild.return_value = guild

    owner_member = MagicMock(spec=discord.Member)
    bot_member = MagicMock(spec=discord.Member)
    default_role = MagicMock(spec=discord.Role)

    guild.me = bot_member
    guild.get_member.return_value = owner_member
    guild.default_role = default_role

    async def apply_lock(overwrites: dict, *_args: object) -> None:
        """Simulate DB lock=1 by setting connect=False on @everyone."""
        ow = overwrites.get(default_role, discord.PermissionOverwrite())
        ow.connect = False
        overwrites[default_role] = ow

    with (
        patch(
            "helpers.voice_permissions._apply_permit_reject_settings",
            new=AsyncMock(),
        ),
        patch(
            "helpers.voice_permissions._apply_voice_feature_settings",
            new=AsyncMock(),
        ),
        patch(
            "helpers.voice_permissions._apply_lock_setting",
            side_effect=apply_lock,
        ),
    ):
        # Act
        await enforce_permission_changes(channel, bot, 1001, 98765, 101)

    # Assert — single API call with lock applied on top of base
    channel.edit.assert_called_once()
    overwrites = channel.edit.call_args.kwargs["overwrites"]
    assert overwrites[default_role].connect is False  # lock overrides base
    assert overwrites[default_role].use_voice_activation is True  # base preserved


@pytest.mark.asyncio
async def test_enforce_uses_per_target_with_hierarchy_blocks() -> None:
    """When hierarchy-blocking roles exist, use per-target set_permissions."""
    # Arrange
    default_role = MagicMock(spec=discord.Role)
    default_role.id = 1
    default_role.name = "@everyone"
    default_role.position = 0

    blocking_role = MagicMock(spec=discord.Role)
    blocking_role.id = 99
    blocking_role.name = "Admin"
    blocking_role.position = 50

    channel = AsyncMock(spec=discord.VoiceChannel)
    channel.id = 12345
    channel.overwrites = {
        default_role: discord.PermissionOverwrite(),
        blocking_role: discord.PermissionOverwrite(connect=True),
    }

    guild = MagicMock(spec=discord.Guild)
    guild.id = 98765

    bot = MagicMock(spec=discord.Client)
    bot.get_guild.return_value = guild

    owner_member = MagicMock(spec=discord.Member)
    bot_member = MagicMock(spec=discord.Member)
    bot_top_role = MagicMock(spec=discord.Role)
    bot_top_role.position = 10
    bot_member.top_role = bot_top_role

    guild.me = bot_member
    guild.get_member.return_value = owner_member
    guild.default_role = default_role

    with (
        patch(
            "helpers.voice_permissions._apply_permit_reject_settings",
            new=AsyncMock(),
        ),
        patch(
            "helpers.voice_permissions._apply_voice_feature_settings",
            new=AsyncMock(),
        ),
        patch(
            "helpers.voice_permissions._apply_lock_setting",
            new=AsyncMock(),
        ),
    ):
        # Act
        await enforce_permission_changes(channel, bot, 1001, 98765, 101)

    # Assert — channel.edit NOT called, set_permissions called instead
    channel.edit.assert_not_called()
    assert channel.set_permissions.call_count > 0
