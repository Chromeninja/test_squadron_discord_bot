"""
Voice Integration Tests

Tests for voice channel management integration scenarios.
Uses in-memory database and mock Discord objects.
"""

import pytest

from tests.factories import (
    make_member,
    make_voice_channel,
    make_voice_state,
)
from tests.factories.db_factories import (
    get_voice_channel_count,
    seed_jtc_preferences,
    seed_voice_channels,
)


class TestVoiceChannelOwnership:
    """Test voice channel ownership scenarios."""

    @pytest.mark.asyncio
    async def test_owner_identified_from_database(self, temp_db):
        """Test that channel owner is correctly identified from database."""
        owner_id = 123456789
        guild_id = 1111
        voice_channel_id = 3333

        await seed_voice_channels([
            {
                "guild_id": guild_id,
                "jtc_channel_id": 2222,
                "owner_id": owner_id,
                "voice_channel_id": voice_channel_id,
                "is_active": 1,
            }
        ])

        from services.db.repository import BaseRepository

        result = await BaseRepository.fetch_value(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
            (voice_channel_id,),
        )
        assert result == owner_id

    @pytest.mark.asyncio
    async def test_multiple_channels_per_owner(self, temp_db):
        """Test that an owner can have multiple channels tracked."""
        owner_id = 123456789
        guild_id = 1111

        await seed_voice_channels([
            {
                "guild_id": guild_id,
                "jtc_channel_id": 2222,
                "owner_id": owner_id,
                "voice_channel_id": 3333,
                "is_active": 1,
            },
            {
                "guild_id": guild_id,
                "jtc_channel_id": 2222,
                "owner_id": owner_id,
                "voice_channel_id": 4444,
                "is_active": 0,  # Inactive/old channel
            },
        ])

        count = await get_voice_channel_count(guild_id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_channel_ownership_per_guild_isolation(self, temp_db):
        """Test that ownership is scoped per guild."""
        owner_id = 123456789

        await seed_voice_channels([
            {
                "guild_id": 1111,
                "jtc_channel_id": 2222,
                "owner_id": owner_id,
                "voice_channel_id": 3333,
                "is_active": 1,
            },
            {
                "guild_id": 9999,  # Different guild
                "jtc_channel_id": 8888,
                "owner_id": owner_id,
                "voice_channel_id": 7777,
                "is_active": 1,
            },
        ])

        # Should have one per guild
        count_guild1 = await get_voice_channel_count(1111)
        count_guild2 = await get_voice_channel_count(9999)
        assert count_guild1 == 1
        assert count_guild2 == 1


class TestVoiceChannelCreation:
    """Test voice channel creation scenarios with mock objects."""

    def test_voice_channel_factory_creates_valid_mock(self):
        """Test that voice channel factory creates usable mock."""
        member = make_member(user_id=123456789, name="TestOwner")
        vc = make_voice_channel(
            channel_id=444555666,
            name="TestOwner's Channel",
            members=[member],
        )

        assert vc.id == 444555666
        assert vc.name == "TestOwner's Channel"
        assert len(vc.members) == 1
        assert vc.members[0].id == 123456789

    def test_voice_state_links_member_to_channel(self):
        """Test that voice state correctly links member to channel."""
        vc = make_voice_channel(channel_id=444555666)
        voice_state = make_voice_state(channel=vc)
        member = make_member(user_id=123456789, voice=voice_state)

        assert member.voice is not None
        assert member.voice.channel is not None
        assert member.voice.channel.id == 444555666


class TestJtcPreferences:
    """Test JTC (join-to-create) preference handling."""

    @pytest.mark.asyncio
    async def test_user_preference_stored_correctly(self, temp_db):
        """Test that JTC preference is stored and retrievable."""
        await seed_jtc_preferences([
            {"guild_id": 123, "user_id": 456, "last_used_jtc_channel_id": 789},
        ])

        from services.db.repository import BaseRepository

        result = await BaseRepository.fetch_value(
            "SELECT last_used_jtc_channel_id FROM user_jtc_preferences WHERE guild_id = ? AND user_id = ?",
            (123, 456),
        )
        assert result == 789

    @pytest.mark.asyncio
    async def test_preference_scoped_per_guild_user(self, temp_db):
        """Test preferences are scoped to guild+user combination."""
        await seed_jtc_preferences([
            {"guild_id": 123, "user_id": 456, "last_used_jtc_channel_id": 789},
            {"guild_id": 123, "user_id": 999, "last_used_jtc_channel_id": 111},  # Same guild, different user
            {"guild_id": 888, "user_id": 456, "last_used_jtc_channel_id": 222},  # Same user, different guild
        ])

        from services.db.repository import BaseRepository

        # User 456 in guild 123
        result1 = await BaseRepository.fetch_value(
            "SELECT last_used_jtc_channel_id FROM user_jtc_preferences WHERE guild_id = ? AND user_id = ?",
            (123, 456),
        )
        assert result1 == 789

        # User 999 in guild 123
        result2 = await BaseRepository.fetch_value(
            "SELECT last_used_jtc_channel_id FROM user_jtc_preferences WHERE guild_id = ? AND user_id = ?",
            (123, 999),
        )
        assert result2 == 111

        # User 456 in guild 888
        result3 = await BaseRepository.fetch_value(
            "SELECT last_used_jtc_channel_id FROM user_jtc_preferences WHERE guild_id = ? AND user_id = ?",
            (888, 456),
        )
        assert result3 == 222
