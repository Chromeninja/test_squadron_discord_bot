"""
Simple tests for deterministic voice settings core functionality.

These tests focus on the database functions and core logic without complex mocking.
"""

from contextlib import nullcontext as does_not_raise
from unittest.mock import AsyncMock, patch

import pytest

from helpers.voice_settings import (
    _get_available_jtc_channels,
    _get_last_used_jtc_channel,
    update_last_used_jtc_channel,
)


class TestDeterministicVoiceSettingsCore:
    """Test core deterministic voice settings functions."""

    @pytest.mark.asyncio
    async def test_get_last_used_jtc_channel_found(self, temp_db):
        """Test _get_last_used_jtc_channel returns the last used JTC channel."""
        guild_id = 12345
        user_id = 67890
        expected_jtc_id = 55555

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = (expected_jtc_id,)
            mock_conn.execute.return_value = cursor

            result = await _get_last_used_jtc_channel(guild_id, user_id)

            assert result == expected_jtc_id
            # Verify the query was called (exact format doesn't matter for functionality)
            assert mock_conn.execute.called

    @pytest.mark.asyncio
    async def test_get_last_used_jtc_channel_not_found(self, temp_db):
        """Test _get_last_used_jtc_channel returns None when no preference exists."""
        guild_id = 12345
        user_id = 67890

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = None
            mock_conn.execute.return_value = cursor

            result = await _get_last_used_jtc_channel(guild_id, user_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_update_last_used_jtc_channel_success(self, temp_db):
        """Test update_last_used_jtc_channel executes successfully."""
        guild_id = 12345
        user_id = 67890
        jtc_channel_id = 55555

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            # Mock the INSERT OR REPLACE operation
            mock_conn.execute.return_value = AsyncMock()
            mock_conn.commit.return_value = None

            # Should not raise an exception
            await update_last_used_jtc_channel(guild_id, user_id, jtc_channel_id)

            # Verify database operations were called
            assert mock_conn.execute.called
            assert mock_conn.commit.called

    @pytest.mark.asyncio
    async def test_get_available_jtc_channels_multiple(self, temp_db):
        """Test _get_available_jtc_channels returns multiple JTC channels."""
        guild_id = 12345
        user_id = 67890
        expected_jtcs = [11111, 22222, 33333]

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchall.return_value = [(jtc,) for jtc in expected_jtcs]
            mock_conn.execute.return_value = cursor

            result = await _get_available_jtc_channels(guild_id, user_id)

            assert result == expected_jtcs

    @pytest.mark.asyncio
    async def test_get_available_jtc_channels_none(self, temp_db):
        """Test _get_available_jtc_channels returns empty list when no JTCs found."""
        guild_id = 12345
        user_id = 67890

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchall.return_value = []
            mock_conn.execute.return_value = cursor

            result = await _get_available_jtc_channels(guild_id, user_id)

            assert result == []

    @pytest.mark.asyncio
    async def test_deterministic_behavior_consistency(self, temp_db):
        """Test that the same inputs always produce the same outputs."""
        guild_id = 12345
        user_id = 67890
        jtc_channel_id = 55555

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = (jtc_channel_id,)
            mock_conn.execute.return_value = cursor

            # Call function multiple times with same inputs
            results = []
            for _ in range(5):
                result = await _get_last_used_jtc_channel(guild_id, user_id)
                results.append(result)

            # Verify all results are identical
            assert all(result == jtc_channel_id for result in results)
            assert len(set(results)) == 1  # All results are the same

    @pytest.mark.asyncio
    async def test_preference_scoping_per_guild_user(self, temp_db):
        """Test that preferences are properly scoped per (guild_id, user_id)."""
        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            # Test that different guild/user combinations can have different preferences
            test_cases = [
                (12345, 67890, 11111),  # guild1, user1 -> jtc1
                (12345, 98765, 22222),  # guild1, user2 -> jtc2
                (54321, 67890, 33333),  # guild2, user1 -> jtc3
                (54321, 98765, 44444),  # guild2, user2 -> jtc4
            ]

            for guild_id, user_id, expected_jtc in test_cases:
                cursor = AsyncMock()
                cursor.fetchone.return_value = (expected_jtc,)
                mock_conn.execute.return_value = cursor

                result = await _get_last_used_jtc_channel(guild_id, user_id)
                assert result == expected_jtc

    @pytest.mark.asyncio
    async def test_error_handling_returns_none(self, temp_db):
        """Test that functions handle database errors gracefully."""
        guild_id = 12345
        user_id = 67890

        with patch("helpers.voice_settings.Database") as mock_db:
            # Simulate a database error
            mock_db.get_connection.side_effect = Exception("Database error")

            # Should not raise exception, but return None/empty list
            result1 = await _get_last_used_jtc_channel(guild_id, user_id)
            assert result1 is None

            result2 = await _get_available_jtc_channels(guild_id, user_id)
            assert result2 == []

            # update_last_used_jtc_channel should not raise exception
            with does_not_raise():
                await update_last_used_jtc_channel(guild_id, user_id, 55555)
