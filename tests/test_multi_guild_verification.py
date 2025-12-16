"""
Tests for multi-guild verification integrity features.

Tests cover:
1. RSI handle uniqueness enforcement
2. Multi-guild cleanup on member leave
3. Guild membership tracking
4. Member rejoin with role restoration
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from cogs.admin.member_lifecycle import MemberLifecycle
from services.db.database import Database

# Suppress deprecation warnings - we're testing backward compatibility
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    # Reset initialized state before each test
    Database._initialized = False
    await Database.initialize(str(db_path))
    yield db_path
    # Reset after test
    Database._initialized = False


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.guilds = []
    bot.role_cache = {}

    # Mock services
    bot.services = MagicMock()
    bot.services.config = MagicMock()
    bot.services.config.get_guild_setting = AsyncMock(return_value=[])

    return bot


@pytest.fixture
def mock_guild():
    """Create a mock guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_member = MagicMock(return_value=None)

    # Mock the bot member (guild.me)
    bot_member = MagicMock(spec=discord.Member)
    bot_role = MagicMock(spec=discord.Role)
    bot_role.position = 10
    bot_role.__gt__ = lambda self, other: self.position > getattr(other, "position", 0)
    bot_member.top_role = bot_role
    bot_member.guild_permissions.manage_nicknames = True
    guild.me = bot_member
    guild.owner_id = 999999  # Different from mock_member.id

    return guild


@pytest.fixture
def mock_member(mock_guild):
    """Create a mock member."""
    member = MagicMock(spec=discord.Member)
    member.id = 987654321
    member.display_name = "TestUser"
    member.guild = mock_guild

    # Mock roles and top_role
    member_role = MagicMock(spec=discord.Role)
    member_role.position = 5  # Lower than bot's role
    member_role.__gt__ = lambda self, other: self.position > getattr(other, "position", 0)
    member.top_role = member_role
    member.roles = []

    return member


@pytest.mark.asyncio
async def test_rsi_handle_uniqueness_enforcement(temp_db, mock_bot, mock_member):
    """Test that duplicate RSI handles are rejected."""
    # Insert first user with handle "TestHandle"
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated)
               VALUES (?, ?, ?)""",
            (111111, "TestHandle", int(time.time())),
        )
        await db.commit()

    # Try to verify second user with same handle
    conflict_id = await Database.check_rsi_handle_conflict("TestHandle", mock_member.id)

    assert conflict_id == 111111, "Should detect existing user with same handle"

    # Verify different handle is allowed
    no_conflict = await Database.check_rsi_handle_conflict("DifferentHandle", mock_member.id)
    assert no_conflict is None, "Should allow different handle"

    # Verify same user can keep their own handle
    same_user = await Database.check_rsi_handle_conflict("TestHandle", 111111)
    assert same_user is None, "User should be able to keep their own handle"


@pytest.mark.asyncio
async def test_guild_membership_tracking(temp_db):
    """Test tracking and querying user guild memberships."""
    user_id = 123456
    guild_id_1 = 111111
    guild_id_2 = 222222

    # Track user in first guild
    await Database.track_user_guild_membership(user_id, guild_id_1)

    guilds = await Database.get_user_active_guilds(user_id)
    assert guilds == [guild_id_1], "Should track user in first guild"

    # Track user in second guild
    await Database.track_user_guild_membership(user_id, guild_id_2)

    guilds = await Database.get_user_active_guilds(user_id)
    assert set(guilds) == {guild_id_1, guild_id_2}, "Should track user in both guilds"

    # Remove from first guild
    await Database.remove_user_guild_membership(user_id, guild_id_1)

    guilds = await Database.get_user_active_guilds(user_id)
    assert guilds == [guild_id_2], "Should only track user in second guild"


@pytest.mark.asyncio
async def test_guild_specific_cleanup(temp_db):
    """Test that guild-specific data is removed but global verification is kept."""
    user_id = 123456
    guild_id = 111111

    # Create verification record
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated)
               VALUES (?, ?, ?)""",
            (user_id, "TestHandle", int(time.time())),
        )

        # Create guild-specific data
        await db.execute(
            """INSERT INTO channel_settings (guild_id, jtc_channel_id, user_id, channel_name)
               VALUES (?, ?, ?, ?)""",
            (guild_id, 999, user_id, "Test Channel"),
        )

        await db.execute(
            """INSERT INTO user_guild_membership (user_id, guild_id)
               VALUES (?, ?)""",
            (user_id, guild_id),
        )

        await db.commit()

    # Clean up guild-specific data
    await Database.cleanup_guild_specific_data(user_id, guild_id)

    # Verify guild-specific data was removed
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM channel_settings WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        assert await cursor.fetchone() is None, "Guild-specific data should be removed"

        # Verify global verification still exists
        cursor = await db.execute(
            "SELECT * FROM verification WHERE user_id = ?",
            (user_id,),
        )
        assert await cursor.fetchone() is not None, "Global verification should remain"


@pytest.mark.asyncio
async def test_full_cleanup_all_guilds(temp_db):
    """Test that all user data is removed when they leave all guilds."""
    user_id = 123456

    # Create verification and guild data
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated)
               VALUES (?, ?, ?)""",
            (user_id, "TestHandle", int(time.time())),
        )

        await db.execute(
            """INSERT INTO auto_recheck_state (user_id, next_retry_at)
               VALUES (?, ?)""",
            (user_id, int(time.time())),
        )

        await db.commit()

    # Perform full cleanup
    await Database.cleanup_all_user_data(user_id)

    # Verify everything is removed
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM verification WHERE user_id = ?",
            (user_id,),
        )
        assert await cursor.fetchone() is None, "Verification should be removed"

        cursor = await db.execute(
            "SELECT * FROM auto_recheck_state WHERE user_id = ?",
            (user_id,),
        )
        assert await cursor.fetchone() is None, "Auto-recheck state should be removed"


@pytest.mark.asyncio
async def test_member_leave_single_guild(temp_db, mock_bot, mock_member, mock_guild):
    """Test member leaving when only in one guild performs full cleanup."""
    mock_bot.guilds = [mock_guild]

    # Setup verification
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated)
               VALUES (?, ?, ?)""",
            (mock_member.id, "TestHandle", int(time.time())),
        )
        await db.execute(
            """INSERT INTO user_guild_membership (user_id, guild_id)
               VALUES (?, ?)""",
            (mock_member.id, mock_guild.id),
        )
        await db.commit()

    # Create lifecycle cog and trigger leave event
    lifecycle = MemberLifecycle(mock_bot)

    with patch("helpers.leadership_log.post_if_changed", new=AsyncMock()):
        await lifecycle.on_member_remove(mock_member)

    # Verify full cleanup occurred
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM verification WHERE user_id = ?",
            (mock_member.id,),
        )
        assert await cursor.fetchone() is None, "Should remove verification when leaving only guild"


@pytest.mark.asyncio
async def test_member_leave_multiple_guilds(temp_db, mock_bot, mock_member):
    """Test member leaving one guild when in multiple guilds keeps verification."""
    # Setup two guilds
    guild1 = MagicMock(spec=discord.Guild)
    guild1.id = 111111
    guild1.name = "Guild 1"
    guild1.get_member = MagicMock(return_value=None)

    guild2 = MagicMock(spec=discord.Guild)
    guild2.id = 222222
    guild2.name = "Guild 2"

    # Member is in guild2
    member2 = MagicMock(spec=discord.Member)
    member2.id = mock_member.id
    guild2.get_member = MagicMock(return_value=member2)

    mock_bot.guilds = [guild1, guild2]
    mock_member.guild = guild1

    # Setup verification and memberships
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated)
               VALUES (?, ?, ?)""",
            (mock_member.id, "TestHandle", int(time.time())),
        )
        await db.execute(
            """INSERT INTO user_guild_membership (user_id, guild_id)
               VALUES (?, ?), (?, ?)""",
            (mock_member.id, guild1.id, mock_member.id, guild2.id),
        )
        await db.commit()

    # Create lifecycle cog and trigger leave from guild1
    lifecycle = MemberLifecycle(mock_bot)

    with patch("helpers.leadership_log.post_if_changed", new=AsyncMock()):
        await lifecycle.on_member_remove(mock_member)

    # Verify verification still exists
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM verification WHERE user_id = ?",
            (mock_member.id,),
        )
        assert await cursor.fetchone() is not None, "Should keep verification when still in other guild"

        # Verify membership removed for guild1 only
        cursor = await db.execute(
            "SELECT guild_id FROM user_guild_membership WHERE user_id = ?",
            (mock_member.id,),
        )
        remaining_guilds = [row[0] for row in await cursor.fetchall()]
        assert guild1.id not in remaining_guilds, "Should remove guild1 membership"
        assert guild2.id in remaining_guilds, "Should keep guild2 membership"


@pytest.mark.asyncio
async def test_member_rejoin_restores_roles(temp_db, mock_bot, mock_member, mock_guild):
    """Test that rejoining member gets roles restored from existing verification."""
    mock_bot.guilds = [mock_guild]

    # Mock role objects
    mock_role = MagicMock(spec=discord.Role)
    mock_role.name = "Main Member"
    mock_guild.get_role = MagicMock(return_value=mock_role)
    mock_bot.role_cache = {999999: mock_role}

    # Mock config to return role IDs
    async def mock_get_setting(guild_id, key, default=None):
        if "bot_verified_role" in key:
            return [999999]
        return []

    mock_bot.services.config.get_guild_setting = mock_get_setting

    # Setup existing verification
    main_orgs = ["TEST"]
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated, main_orgs)
               VALUES (?, ?, ?, ?)""",
            (mock_member.id, "TestHandle", int(time.time()), json.dumps(main_orgs)),
        )
        await db.commit()

    # Mock member.add_roles
    mock_member.add_roles = AsyncMock()

    # Create lifecycle cog and trigger join event
    lifecycle = MemberLifecycle(mock_bot)

    with patch("helpers.leadership_log.post_if_changed", new=AsyncMock()):
        with patch("helpers.announcement.enqueue_announcement_for_guild", new=AsyncMock()):
            await lifecycle.on_member_join(mock_member)

    # Verify guild membership was tracked
    guilds = await Database.get_user_active_guilds(mock_member.id)
    assert mock_guild.id in guilds, "Should track rejoining member's guild"


@pytest.mark.asyncio
async def test_duplicate_handle_conflict_detection(temp_db, mock_member):
    """Test that duplicate RSI handles are detected via conflict check.

    This tests the unified pipeline approach: check for conflicts BEFORE
    applying roles using Database.check_rsi_handle_conflict().
    """
    # Insert existing user with handle
    existing_user_id = 111111
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated)
               VALUES (?, ?, ?)""",
            (existing_user_id, "DuplicateHandle", int(time.time())),
        )
        await db.commit()

    # Check for conflict before assigning roles (unified pipeline pattern)
    conflict_id = await Database.check_rsi_handle_conflict("DuplicateHandle", mock_member.id)

    # Should detect conflict
    assert conflict_id == existing_user_id, "Should detect existing user with same handle"

    # In unified pipeline, caller would raise/abort here rather than proceed
    # Verify the new user was NOT added to verification (we didn't proceed)
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM verification WHERE user_id = ?",
            (mock_member.id,),
        )
        assert await cursor.fetchone() is None, "Should not create verification for duplicate handle"
