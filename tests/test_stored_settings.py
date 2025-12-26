"""
Stored Settings Tests

Tests for voice settings persistence and retrieval.
Covers deterministic channel selection, permission settings, and edge cases.
"""

import pytest

from helpers.voice_settings import (
    _get_available_jtc_channels,
    _get_last_used_jtc_channel,
    update_last_used_jtc_channel,
)
from tests.factories.db_factories import (
    seed_jtc_preferences,
    seed_voice_channels,
)


class TestDeterministicChannelSelection:
    """Test deterministic JTC channel selection logic."""

    @pytest.mark.asyncio
    async def test_no_channels_returns_none(self, temp_db):
        """Test that no available channels returns None."""
        # Don't seed any channels
        result = await _get_available_jtc_channels(guild_id=12345, user_id=67890)
        assert result == []

    @pytest.mark.asyncio
    async def test_reuses_last_used_channel_when_available(self, temp_db):
        """Test that last used JTC channel is preferred."""
        guild_id = 12345
        user_id = 67890
        preferred_jtc = 55555

        await seed_jtc_preferences([
            {"guild_id": guild_id, "user_id": user_id, "jtc_channel_id": preferred_jtc},
        ])

        result = await _get_last_used_jtc_channel(guild_id, user_id)
        assert result == preferred_jtc

    @pytest.mark.asyncio
    async def test_no_preference_returns_none(self, temp_db):
        """Test that missing preference returns None."""
        result = await _get_last_used_jtc_channel(guild_id=12345, user_id=67890)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_preference_overwrites_existing(self, temp_db):
        """Test that updating preference overwrites previous value."""
        guild_id = 12345
        user_id = 67890

        await seed_jtc_preferences([
            {"guild_id": guild_id, "user_id": user_id, "jtc_channel_id": 11111},
        ])

        # Update to new channel
        await update_last_used_jtc_channel(guild_id, user_id, 22222)

        result = await _get_last_used_jtc_channel(guild_id, user_id)
        assert result == 22222


class TestVoiceSettingsEdgeCases:
    """Test edge cases in voice settings handling."""

    @pytest.mark.asyncio
    async def test_same_input_produces_same_output(self, temp_db):
        """Test deterministic behavior - same inputs always produce same outputs."""
        guild_id = 12345
        user_id = 67890
        jtc_id = 55555

        await seed_jtc_preferences([
            {"guild_id": guild_id, "user_id": user_id, "jtc_channel_id": jtc_id},
        ])

        results = []
        for _ in range(5):
            result = await _get_last_used_jtc_channel(guild_id, user_id)
            results.append(result)

        # All results should be identical
        assert all(r == jtc_id for r in results)
        assert len(set(results)) == 1

    @pytest.mark.asyncio
    async def test_different_users_have_independent_preferences(self, temp_db):
        """Test that user preferences don't affect each other."""
        guild_id = 12345

        await seed_jtc_preferences([
            {"guild_id": guild_id, "user_id": 111, "jtc_channel_id": 1001},
            {"guild_id": guild_id, "user_id": 222, "jtc_channel_id": 1002},
            {"guild_id": guild_id, "user_id": 333, "jtc_channel_id": 1003},
        ])

        from helpers.voice_settings import _get_last_used_jtc_channel

        assert await _get_last_used_jtc_channel(guild_id, 111) == 1001
        assert await _get_last_used_jtc_channel(guild_id, 222) == 1002
        assert await _get_last_used_jtc_channel(guild_id, 333) == 1003

    @pytest.mark.asyncio
    async def test_different_guilds_have_independent_preferences(self, temp_db):
        """Test that guild preferences don't affect each other."""
        user_id = 67890

        await seed_jtc_preferences([
            {"guild_id": 111, "user_id": user_id, "jtc_channel_id": 1001},
            {"guild_id": 222, "user_id": user_id, "jtc_channel_id": 1002},
        ])

        from helpers.voice_settings import _get_last_used_jtc_channel

        assert await _get_last_used_jtc_channel(111, user_id) == 1001
        assert await _get_last_used_jtc_channel(222, user_id) == 1002


class TestStoredPermissionSettings:
    """Test stored permission settings for voice channels."""

    @pytest.mark.asyncio
    async def test_channel_with_stored_owner(self, temp_db):
        """Test retrieving stored owner for a voice channel."""
        owner_id = 123456789
        voice_channel_id = 3333

        await seed_voice_channels([
            {
                "guild_id": 1111,
                "jtc_channel_id": 2222,
                "owner_id": owner_id,
                "voice_channel_id": voice_channel_id,
                "is_active": 1,
            }
        ])

        from services.db.repository import BaseRepository

        result = await BaseRepository.fetch_value(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
            (voice_channel_id,),
        )
        assert result == owner_id

    @pytest.mark.asyncio
    async def test_inactive_channel_not_counted_as_active(self, temp_db):
        """Test that inactive channels are excluded from active queries."""
        await seed_voice_channels([
            {
                "guild_id": 1111,
                "jtc_channel_id": 2222,
                "owner_id": 123,
                "voice_channel_id": 3333,
                "is_active": 0,  # Inactive
            }
        ])

        from services.db.repository import BaseRepository

        result = await BaseRepository.fetch_value(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
            (3333,),
        )
        assert result is None  # Should not find inactive channel
