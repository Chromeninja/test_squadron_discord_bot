"""
Voice Service Unit Tests

Unit tests for the VoiceService class covering core functionality.
Uses mocks and fakes - no real Discord connections.
"""

from unittest.mock import MagicMock

import pytest

from tests.factories import (
    make_member,
    make_voice_channel,
    make_voice_state,
)
from tests.factories.db_factories import (
    clear_all_voice_channels,
    get_voice_channel_count,
    seed_voice_channels,
)


class TestVoiceServiceInitialization:
    """Test VoiceService initialization scenarios."""

    @pytest.mark.asyncio
    async def test_initialize_in_test_mode_has_no_side_effects(
        self, temp_db, mock_bot
    ):
        """Real init should mark initialized without spawning background work."""
        from services.config_service import ConfigService
        from services.voice_service import VoiceService

        config_service = MagicMock(spec=ConfigService)
        service = VoiceService(config_service, mock_bot, test_mode=True)

        # Clean DB and capture baseline
        await clear_all_voice_channels()
        initial_count = await get_voice_channel_count()

        await service.initialize()

        # No DB changes in test mode
        assert await get_voice_channel_count() == initial_count
        # No background tasks scheduled when auto_start_background is False
        assert len(service._background_tasks) == 0
        assert service._initialized is True

        await service.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_idempotent_and_schedules_when_enabled(
        self, temp_db, mock_bot
    ):
        """Init should schedule background tasks once and be idempotent."""
        from services.config_service import ConfigService
        from services.voice_service import VoiceService

        config_service = MagicMock(spec=ConfigService)
        service = VoiceService(
            config_service, mock_bot, test_mode=False, auto_start_background=True
        )

        # Stub out task spawning to close coroutines immediately and avoid warnings
        service._spawn_background_task = MagicMock(
            side_effect=lambda coro, *args, **kwargs: coro.close()
        )

        await service.initialize()
        first_calls = service._spawn_background_task.call_count

        # Second initialize should be a no-op
        await service.initialize()
        second_calls = service._spawn_background_task.call_count

        assert first_calls > 0
        assert second_calls == first_calls
        assert service._initialized is True

        await service.shutdown()


class TestVoiceChannelOwnershipOperations:
    """Test voice channel ownership operations."""

    @pytest.mark.asyncio
    async def test_get_channel_owner_returns_correct_owner(self, temp_db):
        """Test retrieving the correct owner for a voice channel."""
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

        result = await BaseRepository.fetch_one(
            "SELECT owner_id, is_active FROM voice_channels WHERE voice_channel_id = ?",
            (voice_channel_id,),
        )

        assert result is not None
        assert result[0] == owner_id
        assert result[1] == 1  # is_active

    @pytest.mark.asyncio
    async def test_get_channel_owner_returns_none_for_nonexistent(self, temp_db):
        """Test that nonexistent channel returns None."""
        from services.db.repository import BaseRepository

        result = await BaseRepository.fetch_one(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
            (999999999,),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_list_user_owned_channels(self, temp_db):
        """Test listing all channels owned by a user."""
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
                "is_active": 1,
            },
            {
                "guild_id": guild_id,
                "jtc_channel_id": 2222,
                "owner_id": 999999,  # Different owner
                "voice_channel_id": 5555,
                "is_active": 1,
            },
        ])

        from services.db.repository import BaseRepository

        results = await BaseRepository.fetch_all(
            "SELECT voice_channel_id FROM voice_channels WHERE owner_id = ? AND guild_id = ? AND is_active = 1",
            (owner_id, guild_id),
        )

        channel_ids = [row[0] for row in results]
        assert len(channel_ids) == 2
        assert 3333 in channel_ids
        assert 4444 in channel_ids
        assert 5555 not in channel_ids


class TestVoiceChannelCleanup:
    """Test voice channel cleanup operations."""

    @pytest.mark.asyncio
    async def test_mark_channel_inactive(self, temp_db):
        """Test marking a channel as inactive."""
        voice_channel_id = 3333

        await seed_voice_channels([
            {
                "guild_id": 1111,
                "jtc_channel_id": 2222,
                "owner_id": 123456789,
                "voice_channel_id": voice_channel_id,
                "is_active": 1,
            }
        ])

        from services.db.repository import BaseRepository

        # Mark inactive
        await BaseRepository.execute(
            "UPDATE voice_channels SET is_active = 0 WHERE voice_channel_id = ?",
            (voice_channel_id,),
        )

        result = await BaseRepository.fetch_value(
            "SELECT is_active FROM voice_channels WHERE voice_channel_id = ?",
            (voice_channel_id,),
        )

        assert result == 0

    @pytest.mark.asyncio
    async def test_clear_all_channels_removes_all(self, temp_db):
        """Test that clear_all_voice_channels removes all records."""
        await seed_voice_channels([
            {"guild_id": 1111, "jtc_channel_id": 2222, "owner_id": 123, "voice_channel_id": 3333},
            {"guild_id": 1111, "jtc_channel_id": 2222, "owner_id": 456, "voice_channel_id": 4444},
        ])

        count_before = await get_voice_channel_count()
        assert count_before == 2

        deleted = await clear_all_voice_channels()
        assert deleted == 2

        count_after = await get_voice_channel_count()
        assert count_after == 0


class TestVoiceServiceEdgeCases:
    """Test edge cases and error handling in VoiceService."""

    def test_voice_channel_factory_with_no_members(self):
        """Test creating voice channel with no members."""
        vc = make_voice_channel(channel_id=123, name="Empty Channel")

        assert vc.id == 123
        assert vc.name == "Empty Channel"
        assert len(vc.members) == 0

    def test_member_with_voice_state(self):
        """Test member correctly linked to voice state."""
        vc = make_voice_channel(channel_id=123)
        vs = make_voice_state(channel=vc)
        member = make_member(user_id=456, voice=vs)

        assert member.voice is not None
        assert member.voice.channel is not None
        assert member.voice.channel.id == 123

    def test_member_without_voice_state(self):
        """Test member with no voice connection."""
        member = make_member(user_id=456)

        assert member.voice is None

    @pytest.mark.asyncio
    async def test_ownership_transfer_updates_database(self, temp_db):
        """Test that ownership transfer correctly updates the database."""
        original_owner = 123456789
        new_owner = 987654321
        voice_channel_id = 3333

        await seed_voice_channels([
            {
                "guild_id": 1111,
                "jtc_channel_id": 2222,
                "owner_id": original_owner,
                "voice_channel_id": voice_channel_id,
                "is_active": 1,
            }
        ])

        from services.db.repository import BaseRepository

        # Transfer ownership
        await BaseRepository.execute(
            "UPDATE voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
            (new_owner, voice_channel_id),
        )

        result = await BaseRepository.fetch_value(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
            (voice_channel_id,),
        )

        assert result == new_owner
