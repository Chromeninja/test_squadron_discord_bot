"""
Tests for voice settings functionality.

This file contains tests for the new voice settings helper functions
and the updated channel creation with settings loading.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

from helpers.voice_settings import (
    _create_settings_embed,
    _get_all_user_settings,
    fetch_channel_settings,
    get_voice_settings_snapshots,
)
from services.config_service import ConfigService
from services.voice_service import VoiceService


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock(spec=discord.Client)
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.default_role = MagicMock(spec=discord.Role)
    return guild


@pytest.fixture
def mock_member():
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 67890
    member.display_name = "TestUser"
    member.display_avatar = MagicMock()
    member.display_avatar.url = "http://example.com/avatar.png"
    return member


@pytest.fixture
def mock_voice_channel():
    """Create a mock Discord voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 98765
    channel.name = "TestUser's Channel"
    channel.bitrate = 64000
    channel.user_limit = 10
    channel.category = MagicMock()
    channel.members = []
    return channel


@pytest.fixture
def mock_jtc_channel():
    """Create a mock join-to-create voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 55555
    channel.name = "Join to Create"
    channel.bitrate = 64000
    channel.user_limit = 0
    channel.category = MagicMock()
    channel.category.permissions_for.return_value = discord.Permissions.all()
    channel.overwrites = {}
    return channel


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 12345
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 67890
    interaction.user.voice = None  # Default to not in voice
    return interaction


@pytest.fixture
def voice_service(mock_bot):
    """Create a VoiceService instance for testing."""
    config_service = MagicMock(spec=ConfigService)
    service = VoiceService(config_service, mock_bot)
    # Skip actual initialization
    service._initialized = True
    return service


class TestVoiceSettingsHelper:
    """Tests for the voice settings helper functions."""

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_active_voice_does_not_load_saved_fallback(
        self, mock_bot, mock_interaction, mock_voice_channel
    ) -> None:
        """Active managed channel settings should remain authoritative."""
        mock_interaction.user.voice = MagicMock()
        mock_interaction.user.voice.channel = mock_voice_channel

        active_settings = {
            "channel_name": "Active Channel",
            "user_limit": 5,
            "lock": True,
        }

        with (
            patch(
                "services.db.repository.BaseRepository.fetch_one",
                new_callable=AsyncMock,
                return_value=(55555,),
            ),
            patch(
                "helpers.voice_settings._get_all_user_settings",
                new_callable=AsyncMock,
                return_value=active_settings,
            ) as mock_get_settings,
            patch(
                "helpers.voice_settings._get_last_used_jtc_channel",
                new_callable=AsyncMock,
            ) as mock_last_used,
        ):
            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["is_active"] is True
            assert result["jtc_channel_id"] == 55555
            assert result["settings"] == active_settings
            assert len(result["embeds"]) == 1
            mock_get_settings.assert_awaited_once_with(12345, 55555, 67890)
            mock_last_used.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_active_unmanaged_voice_uses_saved_fallback(
        self, mock_bot, mock_interaction, mock_voice_channel
    ) -> None:
        """Users in unmanaged voice channels should still see saved settings."""
        mock_interaction.user.voice = MagicMock()
        mock_interaction.user.voice.channel = mock_voice_channel
        mock_interaction.guild = Mock(spec=discord.Guild)

        saved_settings = {
            "channel_name": "Saved Channel",
            "user_limit": 8,
            "lock": False,
        }

        with (
            patch(
                "services.db.repository.BaseRepository.fetch_one",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "helpers.voice_settings._get_last_used_jtc_channel",
                new_callable=AsyncMock,
                return_value=77777,
            ),
            patch(
                "helpers.voice_settings._get_all_user_settings",
                new_callable=AsyncMock,
                return_value=saved_settings,
            ) as mock_get_settings,
        ):
            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["is_active"] is True
            assert result["active_channel"] == mock_voice_channel
            assert result["settings"] == saved_settings
            assert result["jtc_channel_id"] == 77777
            assert len(result["embeds"]) == 1
            mock_get_settings.assert_awaited_once_with(12345, 77777, 67890)

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_no_voice_no_saved(
        self, mock_bot, mock_interaction
    ):
        """Test fetch_channel_settings when user has no active voice and no saved settings."""
        with (
            patch(
                "services.db.repository.BaseRepository.fetch_value",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.db.repository.BaseRepository.fetch_one",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.db.repository.BaseRepository.fetch_all",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["settings"] is None
            assert result["active_channel"] is None
            assert result["is_active"] is False
            assert result["jtc_channel_id"] is None
            assert result["embeds"] == []

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_stale_last_used_shows_available_jtcs(
        self, mock_bot, mock_interaction
    ) -> None:
        """A stale last-used JTC preference should fall back to current saved options."""
        with (
            patch(
                "helpers.voice_settings._get_last_used_jtc_channel",
                new_callable=AsyncMock,
                return_value=11111,
            ),
            patch(
                "helpers.voice_settings._get_all_user_settings",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "helpers.voice_settings._get_available_jtc_channels",
                new_callable=AsyncMock,
                return_value=[11111, 22222, 33333],
            ),
        ):
            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["settings"] is None
            assert result["jtc_channel_id"] is None
            assert len(result["embeds"]) == 1

            embed = result["embeds"][0]
            assert embed.title == "🎙️ Multiple JTC Channels Found"
            assert embed.fields
            field_value = embed.fields[0].value or ""
            assert "11111" not in field_value
            assert "22222" in field_value
            assert "33333" in field_value

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_active_voice_with_settings(
        self, mock_bot, mock_interaction, mock_voice_channel
    ):
        """Test fetch_channel_settings when user is in an active voice channel with settings."""
        # Setup user in voice channel
        mock_interaction.user.voice = MagicMock()
        mock_interaction.user.voice.channel = mock_voice_channel

        # Mock Database.get_connection for the transaction in _get_all_user_settings
        mock_conn = AsyncMock()
        basic_cursor = AsyncMock()
        basic_cursor.fetchall.return_value = [(55555, "Test Channel", 5, 1)]
        feature_cursor = AsyncMock()
        feature_cursor.fetchall.return_value = [
            (55555, "permissions", 1001, "user", "permit"),
            (55555, "ptt_settings", 1001, "user", 1),
        ]
        mock_conn.execute.side_effect = [basic_cursor, feature_cursor]

        # Return jtc_channel_id from voice_channels lookup
        async def mock_fetch_one(query, params=None):
            if "voice_channels" in query:
                return (55555,)  # jtc_channel_id
            return None

        with (
            patch(
                "services.db.repository.BaseRepository.fetch_one",
                new_callable=AsyncMock,
                side_effect=mock_fetch_one,
            ),
            patch("services.db.database.Database.get_connection") as mock_db,
        ):
            mock_db.return_value.__aenter__.return_value = mock_conn

            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["is_active"] is True
            assert result["active_channel"] == mock_voice_channel
            assert result["jtc_channel_id"] == 55555
            assert result["settings"] is not None
            assert result["settings"]["channel_name"] == "Test Channel"
            assert len(result["embeds"]) == 1

    @pytest.mark.asyncio
    async def test_get_all_user_settings_comprehensive(self):
        """Test _get_all_user_settings returns comprehensive settings."""
        mock_conn = AsyncMock()
        basic_cursor = AsyncMock()
        basic_cursor.fetchall.return_value = [(55555, "Custom Channel", 8, 1)]
        feature_cursor = AsyncMock()
        feature_cursor.fetchall.return_value = [
            (55555, "permissions", 1001, "user", "permit"),
            (55555, "permissions", 1002, "role", "reject"),
            (55555, "ptt_settings", 1001, "user", 1),
            (55555, "priority_settings", 1001, "user", 1),
            (55555, "soundboard_settings", 1002, "role", 0),
        ]
        mock_conn.execute.side_effect = [basic_cursor, feature_cursor]

        with patch("services.db.database.Database.get_connection") as mock_db:
            mock_db.return_value.__aenter__.return_value = mock_conn

            settings = await _get_all_user_settings(12345, 55555, 67890)

            assert settings["channel_name"] == "Custom Channel"
            assert settings["user_limit"] == 8
            assert settings["lock"] is True
            assert len(settings["permissions"]) == 2
            assert len(settings["ptt_settings"]) == 1
            assert len(settings["priority_settings"]) == 1
            assert len(settings["soundboard_settings"]) == 1
            assert mock_conn.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_get_voice_settings_snapshots_batches_jtc_reads(self):
        """Snapshot generation should fetch all JTC settings with grouped queries."""
        mock_conn = AsyncMock()
        basic_cursor = AsyncMock()
        basic_cursor.fetchall.return_value = [
            (100, "Channel One", 5, 1),
            (200, "Channel Two", 0, 0),
        ]
        feature_cursor = AsyncMock()
        feature_cursor.fetchall.return_value = [
            (100, "permissions", 1001, "user", "permit"),
            (100, "ptt_settings", 1001, "user", 1),
            (200, "soundboard_settings", 1002, "role", 0),
        ]
        mock_conn.execute.side_effect = [basic_cursor, feature_cursor]

        with patch("services.db.database.Database.get_connection") as mock_db:
            mock_db.return_value.__aenter__.return_value = mock_conn

            snapshots = await get_voice_settings_snapshots(12345, 67890)

            assert [snapshot.jtc_channel_id for snapshot in snapshots] == [100, 200]
            assert snapshots[0].channel_name == "Channel One"
            assert snapshots[0].is_locked is True
            assert len(snapshots[0].permissions) == 1
            assert len(snapshots[0].ptt_settings) == 1
            assert snapshots[1].channel_name == "Channel Two"
            assert len(snapshots[1].soundboard_settings) == 1
            assert mock_conn.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_create_settings_embed_shows_unlocked_state(
        self, mock_guild, mock_member
    ) -> None:
        """Unlocked channels should render their lock state explicitly."""
        settings = {
            "channel_name": "Open Channel",
            "user_limit": 0,
            "lock": False,
        }

        embed = await _create_settings_embed(mock_member, settings, mock_guild)

        channel_settings_field = next(
            field for field in embed.fields if field.name == "Channel Settings"
        )
        assert "🔓 Unlocked" in (channel_settings_field.value or "")


class TestVoiceServiceChannelCreation:
    """Tests for voice service channel creation with settings loading."""

    @pytest.mark.parametrize(
        "channel_name,user_limit,lock,expected_name,expected_limit",
        [
            # Test with saved settings
            ("My Custom Channel", 5, 1, "My Custom Channel", 5),
            ("🎮 Gaming Room", 10, 0, "🎮 Gaming Room", 10),
            (
                "Valid Channel",
                0,
                1,
                "Valid Channel",
                0,
            ),  # Edge case: zero limit but valid name
            ("Unicode Channel 你好", 99, 0, "Unicode Channel 你好", 99),
            # Test with no saved settings (None values)
            (None, None, None, "TestUser's Channel", 0),  # Should use defaults
        ],
    )
    @pytest.mark.asyncio
    async def test_create_user_channel_parametrized(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
        channel_name,
        user_limit,
        lock,
        expected_name,
        expected_limit,
    ):
        """Test _create_user_channel with various saved settings and defaults."""
        import discord

        # Configure database response
        if channel_name is None:
            # No saved settings case
            mock_db_connection.set_fetchone_result(None)
        else:
            # Saved settings case
            mock_db_connection.set_fetchone_result((channel_name, user_limit, lock))

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = expected_name
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock bot member for role comparison
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=True)
        mock_guild.get_member.return_value = mock_bot_member

        # Mock enforce_permission_changes and channel.send()
        created_channel.send = AsyncMock()
        with patch("services.voice_service.enforce_permission_changes") as mock_enforce:
            mock_enforce.return_value = None

            await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

            # Verify channel was created with expected settings
            mock_guild.create_voice_channel.assert_called_once()
            create_args = mock_guild.create_voice_channel.call_args

            assert create_args.kwargs["name"] == expected_name

            # For no saved settings, should use JTC channel's user_limit
            if channel_name is None:
                assert create_args.kwargs["user_limit"] == mock_jtc_channel.user_limit
            else:
                assert create_args.kwargs["user_limit"] == expected_limit

    @pytest.mark.asyncio
    async def test_create_user_channel_empty_name_fallback(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that empty channel names fall back to default."""
        import discord

        # Test case: saved settings with empty name should fall back to default
        mock_db_connection.set_fetchone_result(("", 5, 1))

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "TestUser's Channel"
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock bot member for role comparison
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=True)
        mock_guild.get_member.return_value = mock_bot_member

        # Mock enforce_permission_changes and channel.send()
        created_channel.send = AsyncMock()
        with patch("services.voice_service.enforce_permission_changes") as mock_enforce:
            mock_enforce.return_value = None

            await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

            # Verify channel was created with fallback name
            mock_guild.create_voice_channel.assert_called_once()
            create_args = mock_guild.create_voice_channel.call_args

            assert (
                create_args.kwargs["name"] == "TestUser's Channel"
            )  # Should fallback to default
            assert create_args.kwargs["user_limit"] == 5  # Should use saved limit

    @pytest.mark.asyncio
    async def test_create_user_channel_applies_saved_settings(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that _create_user_channel applies saved settings during creation."""
        import discord

        # Configure saved settings
        mock_db_connection.set_fetchone_result(("My Custom Channel", 5, 1))

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "My Custom Channel"
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock enforce_permission_changes
        created_channel.send = AsyncMock()
        spawned_task_names: list[str] = []

        def capture_background_task(coro, *, name: str) -> Mock:
            spawned_task_names.append(name)
            coro.close()
            return Mock()

        voice_service._send_settings_message_to_vc = AsyncMock()
        voice_service._spawn_background_task = Mock(
            side_effect=capture_background_task
        )

        with patch("services.voice_service.enforce_permission_changes") as mock_enforce:
            mock_enforce.return_value = None

            await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

            # Verify channel was created with saved settings
            mock_guild.create_voice_channel.assert_called_once()
            create_args = mock_guild.create_voice_channel.call_args

            assert create_args.kwargs["name"] == "My Custom Channel"
            assert create_args.kwargs["user_limit"] == 5

            # Verify settings were applied
            mock_enforce.assert_called_once()

            # Verify the settings message is scheduled off the hot path
            voice_service._send_settings_message_to_vc.assert_called_once()
            assert (
                f"voice.settings_message.{created_channel.id}" in spawned_task_names
            )
            created_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_user_channel_uses_defaults_no_saved_settings(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that _create_user_channel uses defaults when no saved settings exist."""
        import discord

        # Mock no saved settings
        mock_db_connection.set_fetchone_result(None)

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock enforce_permission_changes and channel.send()
        created_channel.send = AsyncMock()
        with patch("services.voice_service.enforce_permission_changes"):
            await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

            # Verify channel was created with default settings
            mock_guild.create_voice_channel.assert_called_once()
            create_args = mock_guild.create_voice_channel.call_args

            # Should use default name format
            assert create_args.kwargs["name"] == f"{mock_member.display_name}'s Channel"
            # Should use JTC channel's user_limit
            assert create_args.kwargs["user_limit"] == mock_jtc_channel.user_limit

    @pytest.mark.parametrize(
        "channel_name,user_limit,lock,expected_name,expected_limit,expected_lock",
        [
            # Test various valid settings
            ("Custom Name", 10, 0, "Custom Name", 10, False),
            ("🎮 Gaming Channel", 5, 1, "🎮 Gaming Channel", 5, True),
            (
                "Test Channel with Unicode 你好",
                99,
                0,
                "Test Channel with Unicode 你好",
                99,
                False,
            ),
            # Test edge cases
            ("", 0, 1, "", 0, True),  # Empty name, zero limit
            (
                "Very Long Channel Name That Exceeds Normal Limits",
                1,
                0,
                "Very Long Channel Name That Exceeds Normal Limits",
                1,
                False,
            ),
            # Test defaults/None handling
            (None, None, None, None, None, None),  # All None values
        ],
    )
    @pytest.mark.asyncio
    async def test_load_channel_settings_parametrized(
        self,
        voice_service,
        mock_db_connection,
        channel_name,
        user_limit,
        lock,
        expected_name,
        expected_limit,
        expected_lock,
    ):
        """Test _load_channel_settings with various parameter combinations."""
        if channel_name is None:
            # Test case where no settings exist
            mock_db_connection.set_fetchone_result(None)
            settings = await voice_service._load_channel_settings(12345, 55555, 67890)
            assert settings is None
        else:
            # Test case where settings exist
            mock_db_connection.set_fetchone_result((channel_name, user_limit, lock))
            settings = await voice_service._load_channel_settings(12345, 55555, 67890)

            assert settings["channel_name"] == expected_name
            assert settings["user_limit"] == expected_limit
            assert settings["lock"] == expected_lock

    @pytest.mark.asyncio
    async def test_load_channel_settings_success(
        self, voice_service, mock_db_connection
    ):
        """Test _load_channel_settings returns settings when they exist."""
        mock_db_connection.set_fetchone_result(("Custom Name", 10, 0))

        settings = await voice_service._load_channel_settings(12345, 55555, 67890)

        assert settings["channel_name"] == "Custom Name"
        assert settings["user_limit"] == 10
        assert settings["lock"] == 0

    @pytest.mark.asyncio
    async def test_load_channel_settings_no_settings(
        self, voice_service, mock_db_connection
    ):
        """Test _load_channel_settings returns None when no settings exist."""
        mock_db_connection.set_fetchone_result(None)

        settings = await voice_service._load_channel_settings(12345, 55555, 67890)

        assert settings is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_voice_command_integration(voice_service, mock_db_connection):
    """Integration test to verify voice command flow with fake Discord objects."""
    from unittest.mock import AsyncMock, MagicMock

    import discord

    # Create fake Discord objects
    fake_guild = MagicMock(spec=discord.Guild)
    fake_guild.id = 12345
    fake_guild.name = "Test Squadron"

    fake_member = MagicMock(spec=discord.Member)
    fake_member.id = 67890
    fake_member.display_name = "TestPilot"
    fake_member.guild = fake_guild

    # Create fake category for the JTC channel
    fake_category = MagicMock(spec=discord.CategoryChannel)
    fake_category.id = 44444
    fake_category.name = "Voice Channels"

    fake_jtc_channel = MagicMock(spec=discord.VoiceChannel)
    fake_jtc_channel.id = 55555
    fake_jtc_channel.name = "Join to Create"
    fake_jtc_channel.user_limit = 0
    fake_jtc_channel.category = fake_category
    fake_jtc_channel.bitrate = 64000
    fake_jtc_channel.overwrites = {}
    fake_category.permissions_for.return_value = discord.Permissions.all()

    fake_created_channel = AsyncMock(spec=discord.VoiceChannel)
    fake_created_channel.id = 99999
    fake_created_channel.name = "TestPilot's Channel"

    # Mock the guild's channel creation
    fake_guild.create_voice_channel.return_value = fake_created_channel

    # Mock member move functionality
    fake_member.move_to = AsyncMock()

    # Mock bot member for role comparison
    fake_bot_member = MagicMock()
    fake_bot_member.top_role = MagicMock()
    fake_bot_member.top_role.__gt__ = MagicMock(return_value=True)
    fake_guild.get_member.return_value = fake_bot_member

    # Set up database mock - no saved settings for this test
    mock_db_connection.set_fetchone_result(None)

    # Mock permission enforcement and schedule the settings message off the hot path
    fake_created_channel.send = AsyncMock()
    spawned_task_names: list[str] = []

    def capture_background_task(coro, *, name: str) -> MagicMock:
        spawned_task_names.append(name)
        coro.close()
        return MagicMock()

    voice_service._send_settings_message_to_vc = AsyncMock()
    voice_service._spawn_background_task = MagicMock(
        side_effect=capture_background_task
    )

    with patch("services.voice_service.enforce_permission_changes") as mock_enforce:
        mock_enforce.return_value = None

        # Execute the voice service flow: join-to-create → create channel → move member
        await voice_service._create_user_channel(
            fake_guild, fake_jtc_channel, fake_member
        )

        # Verify the integration flow worked
        # 1. Channel was created with default name (no saved settings)
        fake_guild.create_voice_channel.assert_called_once()
        create_call = fake_guild.create_voice_channel.call_args
        assert create_call.kwargs["name"] == "TestPilot's Channel"
        assert create_call.kwargs["user_limit"] == fake_jtc_channel.user_limit
        assert create_call.kwargs["category"] == fake_category

        # 2. Member was moved to the new channel
        fake_member.move_to.assert_called_once_with(fake_created_channel)

        # 3. Permissions were enforced
        mock_enforce.assert_called_once()

        # 4. Settings view is queued in the background instead of blocking creation
        voice_service._send_settings_message_to_vc.assert_called_once()
        assert f"voice.settings_message.{fake_created_channel.id}" in spawned_task_names
        fake_created_channel.send.assert_not_called()


class TestChannelCreationRoleCheck:
    """Tests for channel creation behavior when bot role hierarchy varies."""

    @pytest.mark.asyncio
    async def test_create_channel_continues_when_bot_role_too_low(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that channel creation continues when bot role < member role.

        Owner permissions are now handled by enforce_permission_changes;
        the standalone set_permissions call was removed.
        """
        # Configure database response - no saved settings
        mock_db_connection.set_fetchone_result(None)

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "TestUser's Channel"
        created_channel.send = AsyncMock()
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member's voice state (still connected)
        mock_member.voice = MagicMock()
        mock_member.voice.channel = MagicMock()
        mock_member.move_to = AsyncMock()

        # Mock bot member with LOWER role than member (role check fails)
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.name = "BotRole"
        # __gt__ returns False -> bot role is NOT higher than member role
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=False)
        mock_guild.get_member.return_value = mock_bot_member

        # Mock member's top role
        mock_member.top_role = MagicMock()
        mock_member.top_role.name = "AdminRole"

        # Execute
        with patch("services.voice_service.enforce_permission_changes"):
            result = await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

        # Verify: channel was NOT deleted - creation continues
        created_channel.delete.assert_not_called() if hasattr(
            created_channel, "delete"
        ) else None
        # Verify: returns the channel (success, just without owner perms)
        assert result == created_channel

    @pytest.mark.asyncio
    async def test_create_channel_succeeds_when_bot_role_higher(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that channel creation succeeds when bot role > member role.

        Owner permissions are now handled entirely by enforce_permission_changes
        (assert_base_permissions sets owner connect=True). The standalone
        set_permissions call was removed as redundant.
        """
        # Configure database response - no saved settings
        mock_db_connection.set_fetchone_result(None)

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "TestUser's Channel"
        created_channel.send = AsyncMock()
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member's voice state (still connected)
        mock_member.voice = MagicMock()
        mock_member.voice.channel = MagicMock()
        mock_member.move_to = AsyncMock()

        # Mock bot member with HIGHER role than member (role check passes)
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.name = "BotRole"
        # __gt__ returns True -> bot role IS higher than member role
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=True)
        mock_guild.get_member.return_value = mock_bot_member

        # Execute
        with patch("services.voice_service.enforce_permission_changes") as mock_enforce:
            result = await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )
            # Verify: enforce_permission_changes was called (handles all perms)
            mock_enforce.assert_called_once()

        # Verify: returns the channel (success)
        assert result == created_channel


class TestJtcOverwriteHandling:
    """Tests for JTC overwrite copying, filtering, and fallback."""

    @pytest.mark.asyncio
    async def test_filters_out_bot_own_roles(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ) -> None:
        """Test that overwrites for bot's own assigned roles are excluded.

        AI Notes:
        - Changed from filtering by role position (>= bot_top_role)
        - Now filters only roles the bot actually has assigned (in bot.roles)
        - Allows copying overwrites for high-position roles like YJ Chief
        """
        mock_db_connection.set_fetchone_result(None)

        # Create roles: @everyone (pos 0), low_role (pos 1), YJ Chief (pos 10),
        # bot (pos 12)
        everyone_role = MagicMock(spec=discord.Role)
        everyone_role.name = "@everyone"
        everyone_role.id = mock_guild.id  # @everyone role ID == guild ID
        everyone_role.is_default = MagicMock(return_value=True)
        low_role = MagicMock(spec=discord.Role)
        low_role.name = "LowRole"
        low_role.id = 11111
        low_role.position = 1
        low_role.is_default = MagicMock(return_value=False)
        yj_chief_role = MagicMock(spec=discord.Role)
        yj_chief_role.name = "YJ Chief"
        yj_chief_role.id = 22222
        yj_chief_role.position = 10
        yj_chief_role.is_default = MagicMock(return_value=False)
        bot_role = MagicMock(spec=discord.Role)
        bot_role.name = "BotRole"
        bot_role.id = 33333
        bot_role.position = 12  # Bot role higher than YJ roles
        bot_role.is_default = MagicMock(return_value=False)

        everyone_overwrite = discord.PermissionOverwrite(connect=False)
        yj_overwrite = discord.PermissionOverwrite(speak=False)
        bot_overwrite = discord.PermissionOverwrite(move_members=True)
        low_overwrite = discord.PermissionOverwrite(connect=True)
        mock_jtc_channel.overwrites = {
            everyone_role: everyone_overwrite,
            low_role: low_overwrite,
            yj_chief_role: yj_overwrite,
            bot_role: bot_overwrite,  # Bot's own role on JTC channel
        }

        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "TestUser's Channel"
        created_channel.send = AsyncMock()
        mock_guild.create_voice_channel.return_value = created_channel

        mock_member.voice = MagicMock()
        mock_member.voice.channel = MagicMock()
        mock_member.move_to = AsyncMock()

        mock_bot_member = MagicMock()
        mock_bot_member.top_role = bot_role
        # In discord.py, Member.roles always includes @everyone
        mock_bot_member.roles = [everyone_role, bot_role]
        mock_guild.get_member.return_value = mock_bot_member

        with patch("services.voice_service.enforce_permission_changes"):
            result = await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

        assert result == created_channel
        call_kwargs = mock_guild.create_voice_channel.call_args.kwargs
        passed_overwrites = call_kwargs["overwrites"]
        # @everyone, low_role, yj_chief_role should all be included
        assert everyone_role in passed_overwrites, "@everyone must be copied"
        assert low_role in passed_overwrites
        assert yj_chief_role in passed_overwrites
        # bot_role should be filtered out (is one of bot's own non-default roles)
        assert bot_role not in passed_overwrites

    @pytest.mark.asyncio
    async def test_falls_back_without_overwrites_on_forbidden(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ) -> None:
        """Test that channel is still created when Forbidden blocks overwrites."""
        mock_db_connection.set_fetchone_result(None)

        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "TestUser's Channel"
        created_channel.send = AsyncMock()

        forbidden = discord.Forbidden(MagicMock(status=403), {"code": 50013})
        mock_guild.create_voice_channel.side_effect = [forbidden, created_channel]

        mock_member.voice = MagicMock()
        mock_member.voice.channel = MagicMock()
        mock_member.move_to = AsyncMock()

        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=True)
        mock_guild.get_member.return_value = mock_bot_member

        with patch("services.voice_service.enforce_permission_changes"):
            result = await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

        # Verify: channel was created on the fallback (second) call
        assert result == created_channel
        assert mock_guild.create_voice_channel.call_count == 2

        # Second call should include essential overwrites only (bot + member)
        second_call_kwargs = mock_guild.create_voice_channel.call_args_list[1].kwargs
        assert "overwrites" in second_call_kwargs
        essential_targets = second_call_kwargs["overwrites"]
        assert mock_bot_member in essential_targets
        assert mock_member in essential_targets
