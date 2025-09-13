"""Simple test for the voice owner command functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from cogs.voice.commands import VoiceCommands
from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


@pytest.mark.asyncio
async def test_voice_owner_command_shows_db_owners():
    """Test that voice owner command shows current database owners from user_voice_channels table."""

    # Reset database for test
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name
    Database._initialized = False
    Database._db_path = temp_db
    await Database.initialize(temp_db)

    # Create mock bot with service container
    mock_bot = AsyncMock()
    mock_services = AsyncMock()
    mock_bot.services = mock_services

    # Initialize services
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
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.followup.send = AsyncMock()
    mock_interaction.user = AsyncMock(spec=discord.Member)
    mock_interaction.user.roles = [MagicMock(id=999999)]  # Admin role

    # Mock admin permissions (allow access)
    with patch.object(voice_service, "get_admin_role_ids", return_value=[999999]):
        # Clean up any existing test data first
        async with Database.get_connection() as db:
            await db.execute(
                "DELETE FROM user_voice_channels WHERE guild_id = ?", (12345,)
            )
            await db.commit()

        # Set up test data in database - insert test voice channels
        async with Database.get_connection() as db:
            test_data = [
                (
                    12345,
                    100,
                    1001,
                    2001,
                    1640000000,
                ),  # guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at
                (12345, 100, 1002, 2002, 1640000001),
            ]

            for guild_id, jtc_id, owner_id, voice_id, created_at in test_data:
                await db.execute(
                    "INSERT INTO user_voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (guild_id, jtc_id, owner_id, voice_id, created_at),
                )
            await db.commit()

        try:
            # Mock Discord objects
            mock_channels = {}
            mock_members = {}

            # Create mock channel 1
            channel1 = AsyncMock(spec=discord.VoiceChannel)
            channel1.id = 2001
            channel1.name = "Voice Channel 1"
            channel1.members = [AsyncMock()]  # 1 member
            mock_channels[2001] = channel1

            # Create mock channel 2
            channel2 = AsyncMock(spec=discord.VoiceChannel)
            channel2.id = 2002
            channel2.name = "Voice Channel 2"
            channel2.members = [AsyncMock(), AsyncMock()]  # 2 members
            mock_channels[2002] = channel2

            # Create mock members (owners)
            member1 = AsyncMock(spec=discord.Member)
            member1.id = 1001
            member1.mention = "<@1001>"
            mock_members[1001] = member1

            member2 = AsyncMock(spec=discord.Member)
            member2.id = 1002
            member2.mention = "<@1002>"
            mock_members[1002] = member2

            # Configure guild mocks
            mock_guild.get_channel.side_effect = lambda channel_id: mock_channels.get(
                channel_id
            )
            mock_guild.get_member.side_effect = lambda member_id: mock_members.get(
                member_id
            )

            # Call the command
            await voice_commands.list_owners.callback(voice_commands, mock_interaction)

            # Verify the interaction was handled properly
            mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
            mock_interaction.followup.send.assert_called_once()

            call_args = mock_interaction.followup.send.call_args

            # Verify embed was sent
            assert "embed" in call_args[1]
            embed = call_args[1]["embed"]

            # Verify embed content
            assert "Managed Voice Channels" in embed.title
            assert "Test Guild" in embed.description
            assert call_args[1]["ephemeral"] is True

            # Check that channel info is in the embed
            embed_content = str(embed.fields[0].value) if embed.fields else ""

            # Verify both channels and owners appear
            assert "Voice Channel 1" in embed_content
            assert "<@1001>" in embed_content
            assert "Voice Channel 2" in embed_content
            assert "<@1002>" in embed_content

            # Verify member counts
            assert "1 members" in embed_content
            assert "2 members" in embed_content

            # Verify footer shows total count
            assert embed.footer.text == "Total: 2 channels"

            print(
                "✅ Test passed: Voice owner command correctly shows database owners!"
            )

        finally:
            # Clean up test data
            async with Database.get_connection() as db:
                await db.execute(
                    "DELETE FROM user_voice_channels WHERE guild_id = ?", (12345,)
                )
                await db.commit()


@pytest.mark.asyncio
async def test_voice_owner_command_no_channels():
    """Test voice owner command when no channels exist."""

    # Reset database for test
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name
    Database._initialized = False
    Database._db_path = temp_db
    await Database.initialize(temp_db)

    # Create mock bot with service container
    mock_bot = AsyncMock()
    mock_services = AsyncMock()
    mock_bot.services = mock_services

    # Initialize services
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
    mock_interaction.guild_id = 54321
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.followup.send = AsyncMock()
    mock_interaction.user = AsyncMock(spec=discord.Member)
    mock_interaction.user.roles = [MagicMock(id=999999)]

    # Mock admin permissions
    with patch.object(voice_service, "get_admin_role_ids", return_value=[999999]):
        # Ensure no channels exist for this guild
        async with Database.get_connection() as db:
            await db.execute(
                "DELETE FROM user_voice_channels WHERE guild_id = ?", (54321,)
            )
            await db.commit()

        # Call the command
        await voice_commands.list_owners.callback(voice_commands, mock_interaction)

        # Verify empty message was sent
        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_interaction.followup.send.assert_called_once()

        call_args = mock_interaction.followup.send.call_args
        assert "No managed voice channels found" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True

        print("✅ Test passed: Voice owner command handles empty database correctly!")


@pytest.mark.asyncio
async def test_voice_owner_command_permission_denied():
    """Test voice owner command with insufficient permissions."""

    # Create mock bot with service container
    mock_bot = AsyncMock()
    mock_services = AsyncMock()
    mock_bot.services = mock_services

    # Initialize services
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
    mock_interaction.response.send_message = AsyncMock()
    mock_interaction.user = AsyncMock(spec=discord.Member)
    mock_interaction.user.roles = [MagicMock(id=111)]  # Not admin

    # Mock no admin permissions (different role ID)
    with patch.object(voice_service, "get_admin_role_ids", return_value=[999999]):
        await voice_commands.list_owners.callback(voice_commands, mock_interaction)

        # Verify permission denied message
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args

        assert "You don't have permission" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True

        print(
            "✅ Test passed: Voice owner command correctly denies access to non-admins!"
        )


if __name__ == "__main__":
    # Simple test runner
    import asyncio

    async def run_tests():
        print("Running voice owner command tests...")

        try:
            await test_voice_owner_command_shows_db_owners()
            await test_voice_owner_command_no_channels()
            await test_voice_owner_command_permission_denied()
            print("\n🎉 All tests passed!")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            raise

    asyncio.run(run_tests())
