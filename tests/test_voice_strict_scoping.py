"""
Tests for strict voice settings scoping per JTC/guild/user.

Ensures voice settings are properly scoped to (guild_id, jtc_channel_id, user_id) and
there's no unintended bleeding between JTCs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.voice_permissions import (
    _apply_lock_setting,
    _apply_permit_reject_settings,
    _apply_voice_feature_settings,
)
from helpers.voice_settings import _get_all_user_settings
from helpers.voice_utils import update_channel_settings
from services.voice_service import VoiceService


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    return MagicMock(spec=discord.Client)


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.default_role = MagicMock(spec=discord.Role)
    guild.default_role.id = 99999
    return guild


@pytest.fixture
def mock_user():
    """Create a mock Discord user."""
    user = MagicMock(spec=discord.Member)
    user.id = 67890
    user.display_name = "TestUser"
    return user


@pytest.fixture
def mock_voice_channel():
    """Create a mock Discord voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 111
    channel.name = "Test Channel"
    channel.user_limit = 5
    channel.overwrites = {}
    return channel


class TestStrictScoping:
    """Test strict scoping behavior for voice settings."""

    @pytest.mark.asyncio
    async def test_voice_service_load_settings_strict_scope(self, mock_bot, mock_guild, mock_user, mock_db_connection):
        """Test that voice service only loads settings with exact guild/JTC match."""
        voice_service = VoiceService(mock_bot)
        guild_id = 12345
        jtc_channel_id = 100
        user_id = 67890

        # Configure mock to return settings for exact match
        mock_db_connection.set_fetchone_result(("Test Channel", 10, 1))
        mock_db_connection.set_fetchall_result([(user_id, "user", "permit")])

        await voice_service._load_channel_settings(guild_id, jtc_channel_id, user_id)

        # Verify queries are made with strict scoping
        calls = mock_db_connection.get_connection_calls()
        for call in calls:
            query = call[0][0]
            params = call[0][1]
            if "WHERE" in query:
                # All queries should have guild_id, jtc_channel_id, user_id
                assert guild_id in params
                assert jtc_channel_id in params
                assert user_id in params

    @pytest.mark.asyncio
    async def test_permit_reject_settings_strict_scope(self, mock_voice_channel, mock_guild):
        """Test that permit/reject settings only apply with exact guild/JTC match."""
        guild_id = 12345
        jtc_channel_id = 100
        user_id = 67890

        with patch('services.db.database.Database.get_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute.return_value = mock_cursor

            # Mock query returns permissions for exact match only
            mock_cursor.fetchall.return_value = [(user_id, "user", "permit")]

            overwrites = {}
            await _apply_permit_reject_settings(overwrites, mock_guild, user_id, guild_id, jtc_channel_id)

            # Verify query uses strict scoping
            query_call = mock_conn.execute.call_args_list[0]
            query = query_call[0][0]
            params = query_call[0][1]

            assert "WHERE" in query
            assert guild_id in params
            assert jtc_channel_id in params
            assert user_id in params

    @pytest.mark.asyncio
    async def test_voice_feature_settings_strict_scope(self, mock_voice_channel, mock_guild):
        """Test that voice feature settings only apply with exact guild/JTC match."""
        guild_id = 12345
        jtc_channel_id = 100
        user_id = 67890

        with patch('services.db.database.Database.get_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute.return_value = mock_cursor

            # Mock query returns feature settings for exact match only
            mock_cursor.fetchall.return_value = [(user_id, "user", 1)]

            overwrites = {}
            await _apply_voice_feature_settings(
                overwrites, mock_guild, user_id, guild_id, jtc_channel_id
            )

            # Verify query uses strict scoping
            query_call = mock_conn.execute.call_args_list[0]
            query = query_call[0][0]
            params = query_call[0][1]

            assert "WHERE" in query
            assert guild_id in params
            assert jtc_channel_id in params
            assert user_id in params

    @pytest.mark.asyncio
    async def test_lock_setting_strict_scope(self, mock_voice_channel, mock_guild):
        """Test that lock settings only apply with exact guild/JTC match."""
        guild_id = 12345
        jtc_channel_id = 100
        user_id = 67890

        with patch('services.db.database.Database.get_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute.return_value = mock_cursor

            # Mock query returns lock setting for exact match only
            mock_cursor.fetchone.return_value = (1,)

            overwrites = {}
            await _apply_lock_setting(overwrites, mock_guild, user_id, guild_id, jtc_channel_id)

            # Verify query uses strict scoping
            query_call = mock_conn.execute.call_args_list[0]
            query = query_call[0][0]
            params = query_call[0][1]

            assert "WHERE" in query
            assert guild_id in params
            assert jtc_channel_id in params
            assert user_id in params

    @pytest.mark.asyncio
    async def test_get_all_user_settings_strict_scope(self):
        """Test that _get_all_user_settings only queries with exact guild/JTC match."""
        guild_id = 12345
        jtc_channel_id = 100
        user_id = 67890

        with patch('services.db.database.Database.get_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute.return_value = mock_cursor

            # Mock all queries return data for exact match only
            mock_cursor.fetchone.return_value = ("Test Channel", 10, 1)
            mock_cursor.fetchall.return_value = [(user_id, "user", "permit")]

            await _get_all_user_settings(guild_id, jtc_channel_id, user_id)

            # Verify all queries use strict scoping
            calls = mock_conn.execute.call_args_list
            for call in calls:
                query = call[0][0]
                params = call[0][1]
                if "WHERE" in query:
                    # All queries should have guild_id, jtc_channel_id, user_id
                    assert guild_id in params
                    assert jtc_channel_id in params
                    assert user_id in params

    @pytest.mark.asyncio
    async def test_update_channel_settings_requires_guild_and_jtc(self):
        """Test that update_channel_settings requires both guild_id and jtc_channel_id."""
        user_id = 67890

        # Test missing guild_id
        with patch('helpers.voice_utils.logger') as mock_logger:
            await update_channel_settings(user_id, guild_id=None, jtc_channel_id=100, channel_name="Test")
            mock_logger.error.assert_called_once()

        # Test missing jtc_channel_id
        with patch('helpers.voice_utils.logger') as mock_logger:
            await update_channel_settings(user_id, guild_id=12345, jtc_channel_id=None, channel_name="Test")
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_voice_feature_setting_requires_guild_and_jtc(self):
        """Test that set_voice_feature_setting requires both guild_id and jtc_channel_id."""
        from helpers.voice_utils import set_voice_feature_setting

        user_id = 67890
        target_id = 12345

        # Test missing guild_id
        with patch('helpers.voice_utils.logger') as mock_logger:
            await set_voice_feature_setting(
                "ptt", user_id, target_id, "user", True, guild_id=None, jtc_channel_id=100
            )
            mock_logger.error.assert_called_once()

        # Test missing jtc_channel_id
        with patch('helpers.voice_utils.logger') as mock_logger:
            await set_voice_feature_setting(
                "ptt", user_id, target_id, "user", True, guild_id=12345, jtc_channel_id=None
            )
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_settings_bleeding_between_jtcs(self):
        """Test that settings for one JTC don't bleed into another JTC."""
        guild_id = 12345
        jtc_channel_id_1 = 100
        jtc_channel_id_2 = 200
        user_id = 67890

        with patch('services.db.database.Database.get_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute.return_value = mock_cursor

            # Mock query for JTC 1 returns settings
            mock_cursor.fetchone.return_value = ("JTC1 Channel", 10, 1)
            mock_cursor.fetchall.return_value = [(user_id, "user", "permit")]

            settings_jtc1 = await _get_all_user_settings(guild_id, jtc_channel_id_1, user_id)

            # Mock query for JTC 2 returns no settings (None/empty)
            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            settings_jtc2 = await _get_all_user_settings(guild_id, jtc_channel_id_2, user_id)

            # Verify JTC1 has settings but JTC2 doesn't (no fallback)
            assert settings_jtc1.get("channel_name") == "JTC1 Channel"
            assert settings_jtc1.get("permissions") == [(user_id, "user", "permit")]

            # JTC2 should have no settings since there's no fallback
            assert "channel_name" not in settings_jtc2
            assert "permissions" not in settings_jtc2
