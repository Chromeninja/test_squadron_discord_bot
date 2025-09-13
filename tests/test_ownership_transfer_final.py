import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio
from helpers.voice_repo import transfer_channel_owner
from services.db.database import Database
from services.voice_service import VoiceService


@pytest_asyncio.fixture
async def test_db():
    """Set up test database with proper schema."""
    # Create a temporary database file
    test_db_fd, test_db_path = tempfile.mkstemp()
    os.close(test_db_fd)

    try:
        # Reset the Database singleton to ensure clean state
        Database._instance = None

        # Initialize the database with the test path - this will set up all tables
        await Database.initialize(test_db_path)

        yield test_db_path

    finally:
        # Clean up
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)
        # Reset singleton for next test
        Database._instance = None


@pytest_asyncio.fixture
async def voice_service(test_db):
    """Set up voice service instance with mocked dependencies."""
    mock_config_service = MagicMock()
    mock_config_service.get_guild_config = AsyncMock()
    mock_config_service.get_guild_config.return_value = {
        'voice': {'channels': {'default': {'user_limit': 0}}}
    }

    service = VoiceService(config_service=mock_config_service)
    return service


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.default_role = MagicMock(spec=discord.Role)
    guild.default_role.id = 67890
    return guild


@pytest.fixture
def mock_channel(mock_guild):
    """Create a mock Discord voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 98765
    channel.name = "Test Voice Channel"
    channel.guild = mock_guild
    channel.members = []
    channel.overwrites = {}
    channel.edit = AsyncMock()
    return channel


@pytest.fixture
def mock_members(mock_guild):
    """Create mock Discord members."""
    old_owner = MagicMock(spec=discord.Member)
    old_owner.id = 11111
    old_owner.display_name = "OldOwner"
    old_owner.guild = mock_guild

    new_owner = MagicMock(spec=discord.Member)
    new_owner.id = 22222
    new_owner.display_name = "NewOwner"
    new_owner.guild = mock_guild

    return old_owner, new_owner


class TestOwnershipTransferSanity:
    """Test comprehensive ownership transfer functionality."""

    @pytest.mark.asyncio
    async def test_voice_repo_transfer_updates_database_correctly(self, test_db):
        """Test that voice_repo transfer_channel_owner updates all database tables."""
        # Set up test data
        guild_id = 12345
        jtc_channel_id = 54321
        voice_channel_id = 98765
        old_owner_id = 11111
        new_owner_id = 22222

        # Insert initial data
        async with Database.get_connection() as db:
            await db.execute(
                """INSERT INTO user_voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id)
                   VALUES (?, ?, ?, ?)""",
                (guild_id, jtc_channel_id, old_owner_id, voice_channel_id)
            )

            await db.execute(
                """INSERT INTO channel_settings (guild_id, jtc_channel_id, user_id, channel_name)
                   VALUES (?, ?, ?, ?)""",
                (guild_id, jtc_channel_id, old_owner_id, "Old Owner's Channel")
            )

            await db.commit()

        # Test the transfer (correct function signature)
        result = await transfer_channel_owner(
            voice_channel_id, new_owner_id, guild_id, jtc_channel_id
        )

        assert result is True, "Transfer should succeed"

        # Verify database changes
        async with Database.get_connection() as db:
            # Verify user_voice_channels updated (authoritative table)
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (voice_channel_id,)
            )
            row = await cursor.fetchone()
            assert row[0] == new_owner_id, "user_voice_channels.owner_id should be updated"

            # Verify settings transferred
            cursor = await db.execute(
                "SELECT user_id, channel_name FROM channel_settings WHERE jtc_channel_id = ? AND user_id = ?",
                (jtc_channel_id, new_owner_id)
            )
            row = await cursor.fetchone()
            assert row is not None, f"New owner {new_owner_id} should have settings"
            assert row[0] == new_owner_id, "Settings should belong to new owner"
            assert row[1] == "Old Owner's Channel", "Settings should be transferred from old owner"

    @pytest.mark.asyncio
    async def test_transfer_handles_missing_channel_gracefully(self, test_db):
        """Test that transfer handles missing channel records gracefully."""
        # Test with non-existent channel (correct function signature)
        result = await transfer_channel_owner(
            99999, 22222, 12345, 54321  # Non-existent voice_channel_id
        )

        assert result is False, "Transfer should fail gracefully for missing channel"
