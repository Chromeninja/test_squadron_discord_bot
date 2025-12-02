"""
Tests for race condition prevention in voice channel creation.

This module contains chaos tests and concurrency tests to verify that:
1. Only one channel is created per user even with concurrent requests
2. Database atomicity prevents duplicate rows
3. Per-user locks prevent race conditions across different JTC channels
4. Voice state updates are filtered correctly to avoid spurious creations
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


@pytest_asyncio.fixture
async def config_service(temp_db):
    """Create a config service for testing."""
    _ = temp_db  # Ensure shared temp_db fixture runs
    service = ConfigService()
    await service.initialize()
    return service


@pytest_asyncio.fixture
async def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock(spec=discord.Client)
    bot.user = MagicMock()
    bot.user.id = 12345
    bot.guilds = []
    return bot


@pytest_asyncio.fixture
async def voice_service(config_service, mock_bot):
    """Create a voice service for testing."""
    service = VoiceService(config_service, bot=mock_bot)
    service.debug_logging_enabled = True  # Enable debug logging for tests
    await service.initialize()
    return service


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 98765
    guild.name = "Test Guild"

    # Mock bot member for permission checks
    bot_member = MagicMock(spec=discord.Member)
    bot_member.id = 12345
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 100
    guild.get_member = MagicMock(return_value=bot_member)

    return guild


@pytest.fixture
def mock_jtc_channel():
    """Create a mock JTC voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 11111
    channel.name = "Join to Create"
    channel.bitrate = 64000
    channel.user_limit = 0

    # Mock category
    category = MagicMock(spec=discord.CategoryChannel)
    category.name = "Voice Channels"
    channel.category = category

    # Mock permissions
    perms = MagicMock()
    perms.manage_channels = True
    category.permissions_for = MagicMock(return_value=perms)

    return channel


@pytest.fixture
def mock_member():
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 55555
    member.display_name = "TestUser"
    member.bot = False

    # Mock voice state
    member.voice = MagicMock()
    member.voice.channel = None

    # Mock role for permission checks
    member.top_role = MagicMock()
    member.top_role.position = 50

    # Mock move_to
    member.move_to = AsyncMock()

    return member


@pytest.mark.asyncio
async def test_concurrent_jtc_joins_create_only_one_channel(
    voice_service, config_service, mock_guild, mock_jtc_channel, mock_member
):
    """
    CHAOS TEST: Verify that 5 concurrent _handle_join_to_create calls
    for the same user result in only 1 channel being created.
    """
    # Setup guild configuration
    await config_service.set_guild_setting(
        mock_guild.id, "voice.jtc_channels", [mock_jtc_channel.id]
    )
    await config_service.set_guild_setting(mock_guild.id, "voice.cooldown_seconds", 0)

    # Track channel creation calls
    created_channels = []

    async def mock_create_voice_channel(name, category, **kwargs):
        """Mock channel creation to track calls."""
        await asyncio.sleep(0.01)  # Simulate Discord API delay
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 99000 + len(created_channels)
        channel.name = name
        channel.members = []
        created_channels.append(channel)
        return channel

    mock_guild.create_voice_channel = AsyncMock(side_effect=mock_create_voice_channel)
    mock_member.voice.channel = mock_jtc_channel  # User is in JTC

    # Launch 5 concurrent creation attempts
    tasks = [
        voice_service._handle_join_to_create(mock_guild, mock_jtc_channel, mock_member)
        for _ in range(5)
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    # Verify only 1 channel was actually created
    assert len(created_channels) == 1, (
        f"Expected 1 channel, but {len(created_channels)} were created"
    )

    # Verify only 1 DB row exists
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM voice_channels
            WHERE guild_id = ? AND owner_id = ? AND is_active = 1
            """,
            (mock_guild.id, mock_member.id),
        )
        count = (await cursor.fetchone())[0]

    assert count == 1, f"Expected 1 DB row, but found {count}"


@pytest.mark.asyncio
async def test_concurrent_different_jtc_creates_only_one_channel(
    voice_service, config_service, mock_guild, mock_member
):
    """
    Test that concurrent joins to different JTC channels by the same user
    are properly serialized and only create one channel.
    """
    # Create two JTC channels
    jtc1 = MagicMock(spec=discord.VoiceChannel)
    jtc1.id = 11111
    jtc1.name = "JTC 1"
    jtc1.bitrate = 64000
    jtc1.user_limit = 0

    jtc2 = MagicMock(spec=discord.VoiceChannel)
    jtc2.id = 22222
    jtc2.name = "JTC 2"
    jtc2.bitrate = 64000
    jtc2.user_limit = 0

    # Setup category for both
    category = MagicMock(spec=discord.CategoryChannel)
    category.name = "Voice Channels"
    perms = MagicMock()
    perms.manage_channels = True
    category.permissions_for = MagicMock(return_value=perms)

    jtc1.category = category
    jtc2.category = category

    # Configure guild
    await config_service.set_guild_setting(
        mock_guild.id, "voice.jtc_channels", [jtc1.id, jtc2.id]
    )
    await config_service.set_guild_setting(mock_guild.id, "voice.cooldown_seconds", 0)

    # Track creations
    created_channels = []

    async def mock_create_voice_channel(name, category, **kwargs):
        await asyncio.sleep(0.01)
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 99000 + len(created_channels)
        channel.name = name
        channel.members = []
        created_channels.append(channel)
        return channel

    mock_guild.create_voice_channel = AsyncMock(side_effect=mock_create_voice_channel)
    mock_guild.get_member = MagicMock(
        return_value=MagicMock(top_role=MagicMock(position=100))
    )

    mock_member.voice.channel = jtc1

    # Launch concurrent attempts from different JTC channels
    tasks = [
        voice_service._handle_join_to_create(mock_guild, jtc1, mock_member),
        voice_service._handle_join_to_create(mock_guild, jtc2, mock_member),
        voice_service._handle_join_to_create(mock_guild, jtc1, mock_member),
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    # Should still only create 1 channel due to per-user lock
    assert len(created_channels) <= 1, (
        f"Expected at most 1 channel, but {len(created_channels)} were created"
    )


@pytest.mark.asyncio
async def test_db_transaction_atomicity(voice_service, mock_guild, mock_member):
    """
    Test that _store_user_channel properly handles concurrent inserts
    with transaction atomicity.
    """
    # Simulate concurrent DB writes for the same user
    tasks = [
        voice_service._store_user_channel(
            mock_guild.id, 11111, mock_member.id, 90000 + i
        )
        for i in range(3)
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    # Verify only 1 active row exists (last one wins due to atomic replacement)
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM voice_channels
            WHERE guild_id = ? AND owner_id = ? AND is_active = 1
            """,
            (mock_guild.id, mock_member.id),
        )
        count = (await cursor.fetchone())[0]

    assert count == 1, (
        f"Expected 1 active DB row due to atomic transaction, but found {count}"
    )


@pytest.mark.asyncio
async def test_voice_state_filter_ignores_reconnects(
    voice_service, mock_guild, mock_member
):
    """
    Test that voice_state_update filters out reconnects and only processes true joins.
    """
    mock_jtc = MagicMock(spec=discord.VoiceChannel)
    mock_jtc.id = 11111

    await voice_service.config_service.set_guild_setting(
        mock_guild.id, "voice.jtc_channels", [mock_jtc.id]
    )

    voice_service._handle_join_to_create = AsyncMock()

    # Test 1: Reconnect (same channel before and after) should not trigger
    await voice_service.handle_voice_state_change(mock_member, mock_jtc, mock_jtc)
    voice_service._handle_join_to_create.assert_not_called()

    # Test 2: Move from another channel to JTC should not trigger (not a true join)
    other_channel = MagicMock(spec=discord.VoiceChannel)
    other_channel.id = 99999
    await voice_service.handle_voice_state_change(mock_member, other_channel, mock_jtc)
    voice_service._handle_join_to_create.assert_not_called()

    # Test 3: True join (before=None, after=JTC) should trigger
    mock_member.guild = mock_guild
    await voice_service.handle_voice_state_change(mock_member, None, mock_jtc)
    voice_service._handle_join_to_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_prevents_duplicate_creation(
    voice_service, mock_guild, mock_jtc_channel, mock_member
):
    """
    Test that _mark_user_creating prevents duplicate channel creation attempts.
    """
    # Mark user as creating
    voice_service._mark_user_creating(mock_guild.id, mock_member.id)

    # Verify marked
    assert voice_service._is_user_creating(mock_guild.id, mock_member.id)

    # Try to handle join while marked - should abort early
    voice_service._create_user_channel = AsyncMock()
    await voice_service._handle_join_to_create(
        mock_guild, mock_jtc_channel, mock_member
    )

    # Should not call creation
    voice_service._create_user_channel.assert_not_called()

    # Unmark
    voice_service._unmark_user_creating(mock_guild.id, mock_member.id)
    assert not voice_service._is_user_creating(mock_guild.id, mock_member.id)


@pytest.mark.asyncio
async def test_per_user_lock_serializes_requests(
    voice_service, mock_guild, mock_member
):
    """
    Test that per-user locks properly serialize concurrent requests.
    """
    lock = await voice_service._get_creation_lock(mock_guild.id, mock_member.id)

    # Verify it's the same lock for the same user
    lock2 = await voice_service._get_creation_lock(mock_guild.id, mock_member.id)
    assert lock is lock2

    # Verify different user gets different lock
    other_member_id = 66666
    lock3 = await voice_service._get_creation_lock(mock_guild.id, other_member_id)
    assert lock is not lock3


@pytest.mark.asyncio
async def test_reconcile_startup_does_not_create_new_channels(
    voice_service, config_service, mock_guild, mock_jtc_channel, mock_member
):
    """
    Test that _reconcile_jtc_members_on_startup only moves users to existing
    channels and does not create new ones.
    """
    # Setup
    voice_service.bot.guilds = [mock_guild]
    voice_service.bot.wait_until_ready = AsyncMock()
    mock_guild.get_channel = MagicMock(return_value=mock_jtc_channel)
    mock_jtc_channel.members = [mock_member]

    await config_service.set_guild_setting(
        mock_guild.id, "voice.jtc_channels", [mock_jtc_channel.id]
    )

    # Track creation calls
    voice_service._handle_join_to_create = AsyncMock()

    # Run reconciliation
    await voice_service._reconcile_jtc_members_on_startup()

    # Verify no new channels were created
    voice_service._handle_join_to_create.assert_not_called()


@pytest.mark.asyncio
async def test_db_prevents_duplicate_inserts_same_transaction(
    voice_service, mock_guild, mock_member
):
    """
    Test that calling _store_user_channel twice with the same channel ID
    within transaction doesn't create duplicates.
    """
    channel_id = 99999
    jtc_id = 11111

    # Insert once
    await voice_service._store_user_channel(
        mock_guild.id, jtc_id, mock_member.id, channel_id
    )

    # Insert again with same channel_id (should be no-op)
    await voice_service._store_user_channel(
        mock_guild.id, jtc_id, mock_member.id, channel_id
    )

    # Verify still only 1 row
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ?",
            (channel_id,),
        )
        count = (await cursor.fetchone())[0]

    assert count == 1, f"Expected 1 row, but found {count}"


@pytest.mark.asyncio
async def test_delayed_unmark_clears_creating_flag(
    voice_service, mock_guild, mock_jtc_channel, mock_member
):
    """
    Test that _delayed_unmark_user_creating properly clears the creating flag after delay.
    """
    # Mark user
    voice_service._mark_user_creating(mock_guild.id, mock_member.id)
    assert voice_service._is_user_creating(mock_guild.id, mock_member.id)

    # Schedule delayed unmark with short delay
    await voice_service._delayed_unmark_user_creating(
        mock_guild.id, mock_member.id, delay=0.05
    )

    # Should be cleared now
    is_creating = voice_service._is_user_creating(mock_guild.id, mock_member.id)
    assert not is_creating
