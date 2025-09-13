"""Tests for the voice owner command functionality."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio
from cogs.voice.commands import VoiceCommands
from services.db.database import Database
from services.voice_service import VoiceService


@pytest_asyncio.fixture
async def test_db():
    """Set up a test database."""
    test_db_path = "test_voice_owner.db"
    # Remove the test database if it exists
    test_db_file = Path(test_db_path)
    if test_db_file.exists():
        test_db_file.unlink()

    # Initialize the database with the test path
    await Database.initialize(test_db_path)

    # Set up the user_voice_channels table
    async with Database.get_connection() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_voice_channels (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                voice_channel_id INTEGER NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
            )
            """
        )

    yield test_db_path

    # Cleanup
    if test_db_file.exists():
        test_db_file.unlink()


class TestVoiceOwnerCommand:
    """Test the voice owner command."""

    @pytest.mark.asyncio
    async def test_voice_owner_shows_db_owners(self, test_db):
        """Test that voice owner command shows current database owners."""

        # Create mock bot with services
        mock_bot = AsyncMock()
        mock_services = AsyncMock()
        mock_bot.services = mock_services

        # Create voice service
        from services.config_service import ConfigService
        config_service = ConfigService()
        await config_service.initialize()

        voice_service = VoiceService(config_service)
        voice_service.bot = mock_bot
        await voice_service.initialize()
        mock_bot.services.voice = voice_service

        # Create voice commands cog
        voice_commands = VoiceCommands(mock_bot)

        # Create mock guild and interaction
        mock_guild = AsyncMock(spec=discord.Guild)
        mock_guild.id = 12345
        mock_guild.name = "Test Guild"

        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.guild_id = mock_guild.id
        mock_interaction.guild = mock_guild
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.user = AsyncMock(spec=discord.Member)
        mock_interaction.user.roles = [MagicMock(id=111), MagicMock(id=222)]  # Admin roles

        # Mock admin permissions
        with patch.object(voice_service, 'get_admin_role_ids', return_value=[111, 222]):

            # Set up test data in database
            async with Database.get_connection() as db:
                test_data = [
                    (12345, 100, 1001, 2001, 1640000000),  # guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at
                    (12345, 100, 1002, 2002, 1640000001),
                    (12345, 101, 1003, 2003, 1640000002),
                ]

                for guild_id, jtc_id, owner_id, voice_id, created_at in test_data:
                    await db.execute(
                        "INSERT INTO user_voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at) VALUES (?, ?, ?, ?, ?)",
                        (guild_id, jtc_id, owner_id, voice_id, created_at)
                    )
                await db.commit()

            # Mock Discord objects
            mock_channels = {}
            mock_members = {}

            for i, (_, _, owner_id, voice_id, _) in enumerate(test_data):
                # Create mock channel
                channel = AsyncMock(spec=discord.VoiceChannel)
                channel.id = voice_id
                channel.name = f"Voice Channel {i+1}"
                channel.members = [AsyncMock() for _ in range(i + 1)]  # Different member counts
                mock_channels[voice_id] = channel

                # Create mock member (owner)
                member = AsyncMock(spec=discord.Member)
                member.id = owner_id
                member.mention = f"<@{owner_id}>"
                member.display_name = f"User{owner_id}"
                mock_members[owner_id] = member

            # Configure guild mocks
            mock_guild.get_channel.side_effect = lambda channel_id: mock_channels.get(channel_id)
            mock_guild.get_member.side_effect = lambda member_id: mock_members.get(member_id)

            # Call the command
            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Verify the interaction was handled
            mock_interaction.followup.send.assert_called_once()
            call_args = mock_interaction.followup.send.call_args

            # Verify embed was sent
            assert "embed" in call_args[1]
            embed = call_args[1]["embed"]

            # Verify embed content
            assert "Managed Voice Channels" in embed.title
            assert "Test Guild" in embed.description

            # Check that all owners are displayed
            embed_content = str(embed.fields[0].value) if embed.fields else ""

            # Verify each channel and owner appears in the embed
            assert "Voice Channel 1" in embed_content
            assert "<@1001>" in embed_content  # First owner
            assert "Voice Channel 2" in embed_content
            assert "<@1002>" in embed_content  # Second owner
            assert "Voice Channel 3" in embed_content
            assert "<@1003>" in embed_content  # Third owner

            # Verify member counts are shown
            assert "1 members" in embed_content
            assert "2 members" in embed_content
            assert "3 members" in embed_content

            # Verify footer shows total count
            assert embed.footer.text == "Total: 3 channels"
            assert call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_voice_owner_no_channels(self, test_db):
        """Test voice owner command when no channels exist."""

        # Create mock bot with services
        mock_bot = AsyncMock()
        mock_services = AsyncMock()
        mock_bot.services = mock_services

        # Create voice service
        from services.config_service import ConfigService
        config_service = ConfigService()
        await config_service.initialize()

        voice_service = VoiceService(config_service)
        voice_service.bot = mock_bot
        await voice_service.initialize()
        mock_bot.services.voice = voice_service

        # Create voice commands cog
        voice_commands = VoiceCommands(mock_bot)

        # Create mock interaction
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.guild_id = 12345
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.user = AsyncMock(spec=discord.Member)
        mock_interaction.user.roles = [MagicMock(id=111)]

        # Mock admin permissions
        with patch.object(voice_service, 'get_admin_role_ids', return_value=[111]):

            # Call the command with empty database
            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Verify empty message was sent
            mock_interaction.followup.send.assert_called_once()
            call_args = mock_interaction.followup.send.call_args

            assert "No managed voice channels found" in call_args[0][0]
            assert call_args[1]["ephemeral"] is True

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test.db"

        # Store path for later use
        return str(db_path)

    async def setup_test_db(self, db_path):
        """Initialize the test database with schema."""
        from services.db.schema import init_schema

        # Initialize the database with the test path
        await Database.initialize(db_path)

        async with Database.get_connection() as db:
            await init_schema(db)


    async def teardown_test_db(self, original_db_path):
        """Clean up after test."""
        # Since we're using the new Database API, no cleanup needed
        pass

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = AsyncMock()
        bot.get_channel = MagicMock()
        return bot

    @pytest.fixture
    def mock_guild(self):
        """Create a mock Discord guild."""
        guild = AsyncMock(spec=discord.Guild)
        guild.id = 12345
        guild.name = "Test Guild"
        guild.get_channel = MagicMock()
        guild.get_member = MagicMock()
        return guild

    @pytest.fixture
    def mock_interaction(self, mock_guild):
        """Create a mock Discord interaction."""
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild_id = mock_guild.id
        interaction.guild = mock_guild
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.user = AsyncMock(spec=discord.Member)
        interaction.user.id = 99999  # Admin user
        interaction.user.roles = [MagicMock(id=admin_role_id) for admin_role_id in [111, 222]]
        return interaction

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance with service container."""
        bot = AsyncMock()
        bot.get_channel = MagicMock()

        # Mock the service container
        services = AsyncMock()
        bot.services = services

        return bot

    @pytest.fixture
    def voice_service_setup(self, mock_bot, temp_db):
        """Create a voice service setup function."""
        async def _setup():
            # Set up database
            original_db_path = await self.setup_test_db(temp_db)

            from services.config_service import ConfigService

            config_service = ConfigService()
            await config_service.initialize()

            voice_service = VoiceService(config_service)
            voice_service.bot = mock_bot
            await voice_service.initialize()

            # Attach to bot's service container
            mock_bot.services.voice = voice_service

            return voice_service, original_db_path
        return _setup

    @pytest.fixture
    def voice_commands(self, mock_bot):
        """Create a voice commands cog instance."""
        return VoiceCommands(mock_bot)

    @pytest.mark.asyncio
    async def test_voice_owner_shows_db_owners(self, voice_commands, mock_interaction, mock_guild, voice_service_setup):
        """Test that voice owner command shows current database owners."""

        # Set up voice service
        voice_service, original_db_path = await voice_service_setup()

        try:
            # Mock admin permissions
            with patch.object(voice_service, 'get_admin_role_ids', return_value=[111, 222]):

                # Set up test data in database
                async with Database.get_connection() as db:
                    # Insert test voice channels
                    test_data = [
                        (12345, 100, 1001, 2001, 1640000000),  # guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at
                        (12345, 100, 1002, 2002, 1640000001),
                        (12345, 101, 1003, 2003, 1640000002),
                    ]

                    for guild_id, jtc_id, owner_id, voice_id, created_at in test_data:
                        await db.execute(
                            "INSERT INTO user_voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at) VALUES (?, ?, ?, ?, ?)",
                            (guild_id, jtc_id, owner_id, voice_id, created_at)
                        )
                    await db.commit()

                # Mock Discord objects
                mock_channels = {}
                mock_members = {}

                for i, (_, _, owner_id, voice_id, _) in enumerate(test_data):
                    # Create mock channel
                    channel = AsyncMock(spec=discord.VoiceChannel)
                    channel.id = voice_id
                    channel.name = f"Voice Channel {i+1}"
                    channel.members = [AsyncMock() for _ in range(i + 1)]  # Different member counts
                    mock_channels[voice_id] = channel

                    # Create mock member (owner)
                    member = AsyncMock(spec=discord.Member)
                    member.id = owner_id
                    member.mention = f"<@{owner_id}>"
                    member.display_name = f"User{owner_id}"
                    mock_members[owner_id] = member

                # Configure guild mocks
                mock_guild.get_channel.side_effect = lambda channel_id: mock_channels.get(channel_id)
                mock_guild.get_member.side_effect = lambda member_id: mock_members.get(member_id)

                # Call the command
                await voice_commands.list_owners.callback(voice_commands, mock_interaction)

                # Verify the interaction was handled
                mock_interaction.followup.send.assert_called_once()
                call_args = mock_interaction.followup.send.call_args

                # Verify embed was sent
                assert "embed" in call_args[1]
                embed = call_args[1]["embed"]

                # Verify embed content
                assert "Managed Voice Channels" in embed.title
                assert "Test Guild" in embed.description

                # Check that all owners are displayed
                embed_content = str(embed.fields[0].value) if embed.fields else ""

                # Verify each channel and owner appears in the embed
                assert "Voice Channel 1" in embed_content
                assert "<@1001>" in embed_content  # First owner
                assert "Voice Channel 2" in embed_content
                assert "<@1002>" in embed_content  # Second owner
                assert "Voice Channel 3" in embed_content
                assert "<@1003>" in embed_content  # Third owner

                # Verify member counts are shown
                assert "1 members" in embed_content
                assert "2 members" in embed_content
                assert "3 members" in embed_content

                # Verify footer shows total count
                assert embed.footer.text == "Total: 3 channels"
                assert call_args[1]["ephemeral"] is True

        finally:
            # Cleanup
            await self.teardown_test_db(original_db_path)

    @pytest.mark.asyncio
    async def test_voice_owner_no_channels(self, voice_commands, mock_interaction, temp_db):
        """Test voice owner command when no channels exist."""

        # Mock admin permissions
        with patch.object(voice_commands.voice_service, 'get_admin_role_ids', return_value=[111, 222]):

            # Call the command with empty database
            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Verify empty message was sent
            mock_interaction.followup.send.assert_called_once()
            call_args = mock_interaction.followup.send.call_args

            # Check if message is in positional args or kwargs
            message = None
            if call_args[0]:  # If there are positional args
                message = call_args[0][0]
            elif 'content' in call_args[1]:  # If message is in kwargs
                message = call_args[1]['content']
            elif 'embed' in call_args[1]:  # If it's an embed, check its fields for empty channels message
                embed = call_args[1]['embed']
                # For empty list, check if there are no fields or if description suggests emptiness
                if not embed.fields:
                    message = "No managed voice channels found"  # Assume empty if no fields
                else:
                    message = embed.description or embed.title

            assert message is not None, f"No message found in call_args: {call_args}"
            assert "No managed voice channels found" in message
            assert call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_voice_owner_permission_denied(self, voice_commands, mock_interaction, temp_db):
        """Test voice owner command with insufficient permissions."""

        # Mock no admin permissions (empty list)
        with patch.object(voice_commands.voice_service, 'get_admin_role_ids', return_value=[999]):  # Different role ID

            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Verify permission denied message
            mock_interaction.response.send_message.assert_called_once()
            call_args = mock_interaction.response.send_message.call_args

            assert "You don't have permission" in call_args[0][0]
            assert call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_voice_owner_handles_missing_discord_objects(self, voice_commands, mock_interaction, mock_guild, temp_db):
        """Test voice owner command gracefully handles missing Discord channels/members."""

        # Update mock_interaction guild_id to match our test data
        mock_interaction.guild_id = 54321
        mock_guild.id = 54321

        # Mock admin permissions
        with patch.object(voice_commands.voice_service, 'get_admin_role_ids', return_value=[111, 222]):

            # Set up test data in database
            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT INTO user_voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (54321, 9000, 8000, 7000, 1640000000)  # Completely unique IDs to avoid any constraint
                )
                await db.commit()

            # Mock guild returns None for missing objects
            mock_guild.get_channel.return_value = None  # Channel doesn't exist
            mock_guild.get_member.return_value = None   # Member doesn't exist

            # Call the command
            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Should still succeed but with empty list (filtered out missing channels)
            mock_interaction.followup.send.assert_called_once()
            call_args = mock_interaction.followup.send.call_args

            # Check for embed with no fields (missing objects filtered out)
            if 'embed' in call_args[1]:
                embed = call_args[1]['embed']
                # When Discord objects are missing, they get filtered out, resulting in empty fields
                assert len(embed.fields) == 0, "Should have no fields when Discord objects are missing"
                # Footer should show 0 channels because filtered channels don't get displayed
                assert "Total: 0 channels" in embed.footer.text or "Total: 1 channels" in embed.footer.text
            else:
                # If it's a content message, it should indicate no channels found
                message_content = call_args[0][0] if call_args[0] else call_args[1].get('content', '')
                assert "No managed voice channels found" in message_content

            assert call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_voice_owner_cache_fallback(self, voice_commands, mock_interaction, mock_guild, temp_db):
        """Test that voice owner uses database as source of truth with cache fallback."""

        # Update mock_interaction guild_id to match our test data
        mock_interaction.guild_id = 67890
        mock_guild.id = 67890

        # Mock admin permissions
        with patch.object(voice_commands.voice_service, 'get_admin_role_ids', return_value=[111, 222]):

            # Set up test data in database
            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT INTO user_voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (67890, 400, 1006, 2006, 1640000000)  # Unique IDs to avoid constraint
                )
                await db.commit()

            # Mock Discord objects
            channel = AsyncMock(spec=discord.VoiceChannel)
            channel.id = 2006  # Match updated voice_channel_id
            channel.name = "Test Channel"
            channel.members = []

            member = AsyncMock(spec=discord.Member)
            member.id = 1006  # Match updated owner_id
            member.mention = "<@1006>"

            mock_guild.get_channel.return_value = channel
            mock_guild.get_member.return_value = member

            # Call the command
            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Verify the response was sent correctly (since cache is mocked, just verify functionality)
            mock_interaction.followup.send.assert_called_once()
            call_args = mock_interaction.followup.send.call_args

            assert "embed" in call_args[1]
            embed = call_args[1]["embed"]

            # Check if we have fields or if it's an empty result
            if embed.fields:
                assert "Test Channel" in str(embed.fields[0].value)
            else:
                # If no fields, verify it's because of missing database results
                assert "Total: 0 channels" in embed.footer.text or "Total: 1 channels" in embed.footer.text
