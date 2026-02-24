"""Integration tests for voice channel ownership *transfer* command.

Mirrors the claim-integration coverage in test_voice_claim_integration.py
and explicitly verifies that Discord permission overwrites are always
updated after a successful transfer -- the regression that prompted the
refactor into ``_perform_ownership_transfer``.
"""

import time
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService

# Reuse lightweight mocks from the existing test suite.
from tests.test_voice_multiple_channels import (
    MockBot,
    MockGuild,
    MockMember,
    MockVoiceChannel,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def voice_service_with_bot(temp_db):
    config_service = ConfigService()
    await config_service.initialize()

    mock_bot = MockBot()
    voice_service = VoiceService(config_service, bot=mock_bot)  # type: ignore[arg-type]
    await voice_service.initialize()

    yield voice_service, mock_bot

    await voice_service.shutdown()
    await config_service.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_owned_channel(
    guild_id: int,
    jtc_channel_id: int,
    owner_id: int,
    voice_channel_id: int,
) -> None:
    """Insert a voice_channels row owned by *owner_id*."""
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT INTO voice_channels
            (guild_id, jtc_channel_id, owner_id, voice_channel_id,
             created_at, last_activity, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                jtc_channel_id,
                owner_id,
                voice_channel_id,
                int(time.time()),
                int(time.time()),
                1,
            ),
        )
        await db.commit()


def _set_mock_guild_voice_channels(
    guild: MockGuild, channels: list[MockVoiceChannel]
) -> None:
    cast("Any", guild).voice_channels = channels


def _set_mock_member_guild(member: MockMember, guild: MockGuild) -> None:
    cast("Any", member).guild = guild


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTransferOwnershipEndToEnd:
    """End-to-end tests for VoiceService.transfer_voice_channel_ownership."""

    @pytest.mark.asyncio
    async def test_transfer_updates_db_and_permissions(self, voice_service_with_bot):
        """Happy-path: DB owner row changes AND update_channel_owner is invoked."""
        voice_service, _bot = voice_service_with_bot

        guild = MockGuild(guild_id=10001)
        channel = MockVoiceChannel(channel_id=50001, name="Owner-VC", guild=guild)

        old_owner = MockMember(user_id=11111, display_name="OldOwner")
        new_owner = MockMember(user_id=22222, display_name="NewOwner")

        # New owner must be "in the channel"
        channel.members = [old_owner, new_owner]
        # The transfer command looks up voice_channels via guild.voice_channels
        _set_mock_guild_voice_channels(guild, [channel])
        _set_mock_member_guild(new_owner, guild)

        jtc_channel_id = 60001
        await _seed_owned_channel(guild.id, jtc_channel_id, old_owner.id, channel.id)

        with patch(
            "helpers.permissions_helper.update_channel_owner",
            new=AsyncMock(),
        ) as perms_mock:
            result = await voice_service.transfer_voice_channel_ownership(
                guild_id=guild.id,
                current_owner_id=old_owner.id,
                new_owner_id=new_owner.id,
                new_owner=new_owner,
            )

        # --- assertions ---
        assert result.success, f"Transfer failed: {result.error}"
        assert result.channel_id == channel.id

        # DB ownership updated
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id, previous_owner_id FROM voice_channels "
                "WHERE voice_channel_id = ?",
                (channel.id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            db_owner, db_prev = row
            assert db_owner == new_owner.id
            assert db_prev is None  # transfer_channel_owner clears previous_owner_id

        # Discord permission helper was called (the bug this test guards against)
        perms_mock.assert_awaited_once()
        call_kwargs = perms_mock.call_args
        assert call_kwargs.kwargs.get("new_owner_id") == new_owner.id or (
            call_kwargs[1].get("new_owner_id") == new_owner.id
            if call_kwargs[1]
            else call_kwargs[0][1] == new_owner.id
        )

    @pytest.mark.asyncio
    async def test_transfer_no_channel_returns_error(self, voice_service_with_bot):
        """Transfer when owner has no active channel should return NO_CHANNEL."""
        voice_service, _bot = voice_service_with_bot

        guild = MockGuild(guild_id=10002)
        new_owner = MockMember(user_id=33333, display_name="NewOwner")
        _set_mock_member_guild(new_owner, guild)
        _set_mock_guild_voice_channels(guild, [])

        result = await voice_service.transfer_voice_channel_ownership(
            guild_id=guild.id,
            current_owner_id=99999,  # no rows for this owner
            new_owner_id=new_owner.id,
            new_owner=new_owner,
        )

        assert not result.success
        assert result.error == "NO_CHANNEL"

    @pytest.mark.asyncio
    async def test_transfer_new_owner_not_in_channel(self, voice_service_with_bot):
        """Transfer should fail when the new owner is not in the voice channel."""
        voice_service, _bot = voice_service_with_bot

        guild = MockGuild(guild_id=10003)
        channel = MockVoiceChannel(channel_id=50003, name="Owner-VC", guild=guild)
        _set_mock_guild_voice_channels(guild, [channel])

        old_owner = MockMember(user_id=44444, display_name="OldOwner")
        new_owner = MockMember(user_id=55555, display_name="NewOwner")
        _set_mock_member_guild(new_owner, guild)

        channel.members = [old_owner]  # new_owner is NOT in the channel

        jtc_channel_id = 60003
        await _seed_owned_channel(guild.id, jtc_channel_id, old_owner.id, channel.id)

        result = await voice_service.transfer_voice_channel_ownership(
            guild_id=guild.id,
            current_owner_id=old_owner.id,
            new_owner_id=new_owner.id,
            new_owner=new_owner,
        )

        assert not result.success
        assert result.error == "NOT_IN_CHANNEL"

    @pytest.mark.asyncio
    async def test_transfer_db_failure_returns_temp_error(self, voice_service_with_bot):
        """When the DB transfer fails, we get DB_TEMP_ERROR and permissions are NOT touched."""
        voice_service, _bot = voice_service_with_bot

        guild = MockGuild(guild_id=10004)
        channel = MockVoiceChannel(channel_id=50004, name="Owner-VC", guild=guild)
        _set_mock_guild_voice_channels(guild, [channel])

        old_owner = MockMember(user_id=66666, display_name="OldOwner")
        new_owner = MockMember(user_id=77777, display_name="NewOwner")
        _set_mock_member_guild(new_owner, guild)
        channel.members = [old_owner, new_owner]

        jtc_channel_id = 60004
        await _seed_owned_channel(guild.id, jtc_channel_id, old_owner.id, channel.id)

        with (
            patch(
                "helpers.voice_repo.transfer_channel_owner",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "helpers.permissions_helper.update_channel_owner",
                new=AsyncMock(),
            ) as perms_mock,
        ):
            result = await voice_service.transfer_voice_channel_ownership(
                guild_id=guild.id,
                current_owner_id=old_owner.id,
                new_owner_id=new_owner.id,
                new_owner=new_owner,
            )

        assert not result.success
        assert result.error == "DB_TEMP_ERROR"
        perms_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transfer_cooldown_written(self, voice_service_with_bot):
        """Successful transfer should record a voice_cooldowns row for the new owner."""
        voice_service, _bot = voice_service_with_bot

        guild = MockGuild(guild_id=10005)
        channel = MockVoiceChannel(channel_id=50005, name="Owner-VC", guild=guild)
        _set_mock_guild_voice_channels(guild, [channel])

        old_owner = MockMember(user_id=88888, display_name="OldOwner")
        new_owner = MockMember(user_id=99990, display_name="NewOwner")
        _set_mock_member_guild(new_owner, guild)
        channel.members = [old_owner, new_owner]

        jtc_channel_id = 60005
        await _seed_owned_channel(guild.id, jtc_channel_id, old_owner.id, channel.id)

        with patch(
            "helpers.permissions_helper.update_channel_owner",
            new=AsyncMock(),
        ):
            result = await voice_service.transfer_voice_channel_ownership(
                guild_id=guild.id,
                current_owner_id=old_owner.id,
                new_owner_id=new_owner.id,
                new_owner=new_owner,
            )

        assert result.success

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT timestamp FROM voice_cooldowns "
                "WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?",
                (guild.id, jtc_channel_id, new_owner.id),
            )
            row = await cursor.fetchone()
            assert row is not None, "Cooldown row should exist for new owner"
            assert isinstance(row[0], int) and row[0] > 0
