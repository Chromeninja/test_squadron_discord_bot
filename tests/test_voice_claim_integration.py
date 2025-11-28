import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService

# Reuse lightweight mocks similar to other test modules
from tests.test_voice_multiple_channels import (
    MockBot,
    MockGuild,
    MockMember,
    MockVoiceChannel,
)


@pytest_asyncio.fixture
async def voice_service_with_bot(temp_db):
    config_service = ConfigService()
    await config_service.initialize()

    mock_bot = MockBot()
    voice_service = VoiceService(config_service, bot=mock_bot)
    await voice_service.initialize()

    yield voice_service, mock_bot

    await voice_service.shutdown()
    await config_service.shutdown()


@pytest.mark.asyncio
async def test_claim_voice_channel_integration_orphan_channel(voice_service_with_bot):
    """End-to-end claim of orphaned channel.

    Ensures cooldown insertion uses 'timestamp' column via real
    transfer_channel_owner execution (permissions helper mocked only)."""
    voice_service, _mock_bot = voice_service_with_bot

    guild = MockGuild(guild_id=12345)
    channel = MockVoiceChannel(
        channel_id=99991,
        name="Orphaned",
        members=[],
        guild=guild,
    )
    user = MockMember(user_id=22223, display_name="Claimer")
    user.voice.channel = channel
    channel.members = [user]
    jtc_channel_id = 67890

    # Insert orphaned channel directly
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT INTO voice_channels
            (
                guild_id,
                jtc_channel_id,
                owner_id,
                voice_channel_id,
                created_at,
                last_activity,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild.id,
                jtc_channel_id,
                VoiceService.ORPHAN_OWNER_ID,
                channel.id,
                int(time.time()),
                int(time.time()),
                1,
            ),
        )
        await db.commit()

    # Patch permissions helper only (avoid external Discord state)
    with patch(
        "helpers.permissions_helper.update_channel_owner",
        new=AsyncMock(),
    ) as perms_mock:
        result = await voice_service.claim_voice_channel(guild.id, user.id, user)

    assert result.success, f"Claim failed: {result.error}"

    # Verify ownership transfer applied
    async with Database.get_connection() as db:
        owner_query = (
            "SELECT owner_id, previous_owner_id FROM voice_channels "
            "WHERE voice_channel_id = ?"
        )
        cursor = await db.execute(owner_query, (channel.id,))
        row = await cursor.fetchone()
        assert row is not None
        new_owner_id, previous_owner_id = row
        assert new_owner_id == user.id
        assert previous_owner_id is None

        # Verify cooldown row written with 'timestamp' column
        cooldown_query = (
            "SELECT timestamp FROM voice_cooldowns WHERE guild_id = ? "
            "AND jtc_channel_id = ? AND user_id = ?"
        )
        cursor = await db.execute(
            cooldown_query, (guild.id, jtc_channel_id, user.id)
        )
        cooldown_row = await cursor.fetchone()
        assert cooldown_row is not None
        assert isinstance(cooldown_row[0], int) and cooldown_row[0] > 0

    perms_mock.assert_awaited_once()
