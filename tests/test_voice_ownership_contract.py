"""
Contract Tests for Voice Ownership Flow

DB-backed integration tests for voice channel ownership operations.
Uses in-memory SQLite database to test realistic flows.
"""

import pytest

from services.db.repository import BaseRepository
from tests.factories.db_factories import (
    get_voice_channel_count,
    seed_jtc_preferences,
    seed_voice_channels,
)


@pytest.mark.contract
class TestVoiceOwnershipListingContract:
    """Contract tests for voice ownership listing operations."""

    @pytest.mark.asyncio
    async def test_list_all_owners_for_guild(self, temp_db):
        """Contract: List all channel owners for a guild."""
        guild_id = 1111

        # Seed multiple owners
        await seed_voice_channels([
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": 111, "voice_channel_id": 3001, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": 222, "voice_channel_id": 3002, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": 333, "voice_channel_id": 3003, "is_active": 1},
            {"guild_id": 9999, "jtc_channel_id": 8888, "owner_id": 444, "voice_channel_id": 3004, "is_active": 1},  # Different guild
        ])

        # Query: List all active owners for guild
        results = await BaseRepository.fetch_all(
            """
            SELECT DISTINCT owner_id, COUNT(*) as channel_count
            FROM voice_channels
            WHERE guild_id = ? AND is_active = 1
            GROUP BY owner_id
            ORDER BY channel_count DESC
            """,
            (guild_id,),
        )

        owner_ids = [row[0] for row in results]

        # Contract assertions
        assert len(results) == 3  # 3 distinct owners in guild 1111
        assert 111 in owner_ids
        assert 222 in owner_ids
        assert 333 in owner_ids
        assert 444 not in owner_ids  # Different guild

    @pytest.mark.asyncio
    async def test_list_channels_for_owner(self, temp_db):
        """Contract: List all channels owned by a specific user."""
        owner_id = 123456789
        guild_id = 1111

        await seed_voice_channels([
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": owner_id, "voice_channel_id": 3001, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": owner_id, "voice_channel_id": 3002, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": owner_id, "voice_channel_id": 3003, "is_active": 0},  # Inactive
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": 999999, "voice_channel_id": 3004, "is_active": 1},  # Different owner
        ])

        # Query: List all channels for owner
        results = await BaseRepository.fetch_all(
            """
            SELECT voice_channel_id, is_active
            FROM voice_channels
            WHERE guild_id = ? AND owner_id = ?
            ORDER BY created_at DESC
            """,
            (guild_id, owner_id),
        )

        # Contract assertions
        assert len(results) == 3  # All channels for owner (active + inactive)

        active_channels = [row[0] for row in results if row[1] == 1]
        assert len(active_channels) == 2

    @pytest.mark.asyncio
    async def test_empty_owner_list_for_new_guild(self, temp_db):
        """Contract: New guild with no channels returns empty list."""
        new_guild_id = 999888777

        results = await BaseRepository.fetch_all(
            "SELECT owner_id FROM voice_channels WHERE guild_id = ?",
            (new_guild_id,),
        )

        assert len(results) == 0


@pytest.mark.contract
class TestVoiceOwnershipResetContract:
    """Contract tests for voice ownership reset operations."""

    @pytest.mark.asyncio
    async def test_reset_single_channel_ownership(self, temp_db):
        """Contract: Reset ownership of a single channel."""
        original_owner = 111
        new_owner = 222
        voice_channel_id = 3001

        await seed_voice_channels([
            {"guild_id": 1111, "jtc_channel_id": 2222, "owner_id": original_owner, "voice_channel_id": voice_channel_id, "is_active": 1},
        ])

        # Reset: Transfer ownership
        await BaseRepository.execute(
            "UPDATE voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
            (new_owner, voice_channel_id),
        )

        # Verify
        result = await BaseRepository.fetch_value(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
            (voice_channel_id,),
        )

        assert result == new_owner

    @pytest.mark.asyncio
    async def test_reset_all_channels_for_user(self, temp_db):
        """Contract: Reset all channels for a specific user to inactive."""
        owner_id = 123456789
        guild_id = 1111

        await seed_voice_channels([
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": owner_id, "voice_channel_id": 3001, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": owner_id, "voice_channel_id": 3002, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 2222, "owner_id": 999999, "voice_channel_id": 3003, "is_active": 1},  # Different owner
        ])

        # Reset: Deactivate all channels for user
        await BaseRepository.execute(
            "UPDATE voice_channels SET is_active = 0 WHERE owner_id = ? AND guild_id = ?",
            (owner_id, guild_id),
        )

        # Verify owner's channels are inactive
        owner_active = await BaseRepository.fetch_value(
            "SELECT COUNT(*) FROM voice_channels WHERE owner_id = ? AND guild_id = ? AND is_active = 1",
            (owner_id, guild_id),
        )
        assert owner_active == 0

        # Verify other owner's channel is still active
        other_active = await BaseRepository.fetch_value(
            "SELECT COUNT(*) FROM voice_channels WHERE owner_id = 999999 AND is_active = 1",
            (),
        )
        assert other_active == 1

    @pytest.mark.asyncio
    async def test_reset_nonexistent_channel(self, temp_db):
        """Contract: Reset of nonexistent channel affects no rows."""
        # No seeding - empty database

        await BaseRepository.execute(
            "UPDATE voice_channels SET owner_id = 999 WHERE voice_channel_id = 12345678",
            (),
        )

        # Should execute without error but affect no rows
        count = await get_voice_channel_count()
        assert count == 0


@pytest.mark.contract
class TestVoiceOwnershipEdgeCases:
    """Contract tests for edge cases in voice ownership."""

    @pytest.mark.asyncio
    async def test_concurrent_channel_creation_scenario(self, temp_db):
        """Contract: Handle rapid channel creation (sequential simulation)."""
        owner_id = 123456789
        guild_id = 1111
        jtc_id = 2222

        # Simulate rapid creation of multiple channels
        channels = [
            {"guild_id": guild_id, "jtc_channel_id": jtc_id, "owner_id": owner_id, "voice_channel_id": 3000 + i, "is_active": 1}
            for i in range(5)
        ]
        await seed_voice_channels(channels)

        # All should be present
        count = await BaseRepository.fetch_value(
            "SELECT COUNT(*) FROM voice_channels WHERE owner_id = ? AND guild_id = ?",
            (owner_id, guild_id),
        )
        assert count == 5

    @pytest.mark.asyncio
    async def test_ownership_across_multiple_jtc_channels(self, temp_db):
        """Contract: User can own channels from different JTC sources."""
        owner_id = 123456789
        guild_id = 1111

        await seed_voice_channels([
            {"guild_id": guild_id, "jtc_channel_id": 1001, "owner_id": owner_id, "voice_channel_id": 3001, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 1002, "owner_id": owner_id, "voice_channel_id": 3002, "is_active": 1},
            {"guild_id": guild_id, "jtc_channel_id": 1003, "owner_id": owner_id, "voice_channel_id": 3003, "is_active": 1},
        ])

        # Count distinct JTC sources for owner
        results = await BaseRepository.fetch_all(
            "SELECT DISTINCT jtc_channel_id FROM voice_channels WHERE owner_id = ? AND guild_id = ?",
            (owner_id, guild_id),
        )

        assert len(results) == 3  # 3 different JTC channels

    @pytest.mark.asyncio
    async def test_preference_persists_after_channel_cleanup(self, temp_db):
        """Contract: JTC preference persists even after channel is deactivated."""
        guild_id = 1111
        user_id = 123456789
        jtc_id = 2222

        # Create preference and channel
        await seed_jtc_preferences([
            {"guild_id": guild_id, "user_id": user_id, "last_used_jtc_channel_id": jtc_id},
        ])
        await seed_voice_channels([
            {"guild_id": guild_id, "jtc_channel_id": jtc_id, "owner_id": user_id, "voice_channel_id": 3001, "is_active": 1},
        ])

        # Deactivate channel
        await BaseRepository.execute(
            "UPDATE voice_channels SET is_active = 0 WHERE voice_channel_id = 3001",
            (),
        )

        # Preference should still exist
        pref = await BaseRepository.fetch_value(
            "SELECT last_used_jtc_channel_id FROM user_jtc_preferences WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        assert pref == jtc_id
