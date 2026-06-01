"""Integration tests for backend repository classes against the real schema.

These tests exercise actual SQL against a temporary SQLite database
initialised from services/db/schema.py. They are the regression guard that
catches schema-mismatch bugs (wrong column names, missing NOT NULL fields)
that unit tests with mocked connections cannot detect.
"""

from __future__ import annotations

import pytest

from backend.db.repository.config import ConfigRepository
from backend.db.repository.tickets import TicketRepository
from backend.db.repository.verification import VerificationRepository
from backend.db.repository.voice import VoiceRepository

GUILD_ID = 555
USER_ID = 777


@pytest.mark.asyncio
async def test_ticket_create_get_update_close(temp_db: str) -> None:
    """Full ticket lifecycle against the real tickets schema."""
    repo = TicketRepository()

    created = await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": USER_ID,
            "initial_description": "help please",
        },
    )
    ticket_id = int(created["id"])  # type: ignore[arg-type]
    assert created["status"] == "open"
    assert created["thread_id"] == 2002
    assert created["channel_id"] == 1001

    # Listing returns the open ticket
    open_tickets = await repo.get_tickets(GUILD_ID, status="open")
    assert any(t["id"] == ticket_id for t in open_tickets)

    # get_ticket round-trips
    fetched = await repo.get_ticket(GUILD_ID, ticket_id)
    assert fetched is not None
    assert fetched["user_id"] == USER_ID

    # update_ticket changes a whitelisted column
    updated = await repo.update_ticket(
        GUILD_ID, ticket_id, {"close_reason": "resolved"}
    )
    assert updated is not None
    assert updated["close_reason"] == "resolved"

    # close_ticket records closed_at/closed_by and flips status
    assert await repo.close_ticket(GUILD_ID, ticket_id, closed_by=999) is True
    closed = await repo.get_ticket(GUILD_ID, ticket_id)
    assert closed is not None
    assert closed["status"] == "closed"
    assert closed["closed_by"] == 999
    assert closed["closed_at"] is not None

    # Closing again is a no-op (already closed)
    assert await repo.close_ticket(GUILD_ID, ticket_id) is False


@pytest.mark.asyncio
async def test_ticket_create_requires_not_null_fields(temp_db: str) -> None:
    """Missing NOT NULL columns raise a clear error, not an SQLite crash."""
    repo = TicketRepository()
    with pytest.raises(ValueError, match="thread_id"):
        await repo.create_ticket(GUILD_ID, {"channel_id": 1, "user_id": 2})


@pytest.mark.asyncio
async def test_voice_channel_crud(temp_db: str) -> None:
    """Voice channel create/get/delete against the real voice_channels schema."""
    repo = VoiceRepository()
    created = await repo.create_voice_channel(
        GUILD_ID,
        {"voice_channel_id": 4004, "jtc_channel_id": 3003, "owner_id": USER_ID},
    )
    assert created is not None

    fetched = await repo.get_voice_channel(GUILD_ID, 4004)
    assert fetched is not None
    assert fetched["owner_id"] == USER_ID
    assert fetched["is_active"] == 1

    # get_jtc_channels only returns active channels
    active = await repo.get_jtc_channels(GUILD_ID)
    assert any(c["voice_channel_id"] == 4004 for c in active)

    # delete is a soft-delete (is_active -> 0); the row remains queryable
    assert await repo.delete_voice_channel(GUILD_ID, 4004) is True
    after = await repo.get_voice_channel(GUILD_ID, 4004)
    assert after is not None
    assert after["is_active"] == 0

    # ...and is excluded from the active listing
    active_after = await repo.get_jtc_channels(GUILD_ID)
    assert not any(c["voice_channel_id"] == 4004 for c in active_after)


@pytest.mark.asyncio
async def test_verification_create_and_fetch(temp_db: str) -> None:
    """Verification upsert and fetch against the real verification schema."""
    repo = VerificationRepository()
    await repo.create_verification(
        GUILD_ID,
        {
            "user_id": USER_ID,
            "rsi_handle": "TestPilot",
            "community_moniker": "Pilot",
            "main_orgs": "TEST",
            "affiliate_orgs": "",
        },
    )
    rec = await repo.get_verification(GUILD_ID, USER_ID)
    assert rec is not None
    assert rec["rsi_handle"] == "TestPilot"


@pytest.mark.asyncio
async def test_config_set_get_roundtrip(temp_db: str) -> None:
    """Config set/get roundtrip against the real guild_settings schema."""
    repo = ConfigRepository()

    # set_setting with a string value
    await repo.set_setting(GUILD_ID, "prefix", "!")
    result = await repo.get_setting(GUILD_ID, "prefix")
    assert result == "!"

    # set_setting with a dict value (JSON-encoded)
    dict_value = {"role_id": 12345, "enabled": True}
    await repo.set_setting(GUILD_ID, "moderation", dict_value)
    result = await repo.get_setting(GUILD_ID, "moderation")
    assert result == dict_value

    # get_config returns all settings for a guild
    await repo.set_setting(GUILD_ID, "timezone", "UTC")
    config = await repo.get_config(GUILD_ID)
    assert config["prefix"] == "!"
    assert config["moderation"] == dict_value
    assert config["timezone"] == "UTC"

    # get_setting on non-existent setting returns None
    result = await repo.get_setting(GUILD_ID, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_config_get_guild_roles(temp_db: str) -> None:
    """Test get_guild_roles with single and list role configs."""
    repo = ConfigRepository()

    # Set single role IDs (stored as list, extract first)
    await repo.set_setting(GUILD_ID, "roles.bot_verified_role", [123])
    await repo.set_setting(GUILD_ID, "roles.main_role", [456])
    await repo.set_setting(GUILD_ID, "roles.non_member_role", [789])

    # Set admin roles (stored as list)
    await repo.set_setting(GUILD_ID, "roles.bot_admins", [111, 222, 333])
    await repo.set_setting(GUILD_ID, "roles.event_coordinators", [444, 555])

    roles = await repo.get_guild_roles(GUILD_ID)
    assert roles["bot_verified_role_id"] == 123
    assert roles["main_role_id"] == 456
    assert roles["non_member_role_id"] == 789
    assert roles["bot_admin_role_ids"] == [111, 222, 333]
    assert roles["event_coordinator_role_ids"] == [444, 555]


@pytest.mark.asyncio
async def test_config_get_guild_channels(temp_db: str) -> None:
    """Test get_guild_channels with channel IDs."""
    repo = ConfigRepository()

    # Set channel IDs as integers
    await repo.set_setting(GUILD_ID, "channels.verification_channel_id", 1001)
    await repo.set_setting(GUILD_ID, "channels.bot_spam_channel_id", 1002)
    await repo.set_setting(
        GUILD_ID, "channels.public_announcement_channel_id", 1003
    )
    await repo.set_setting(
        GUILD_ID, "channels.leadership_announcement_channel_id", 1004
    )

    channels = await repo.get_guild_channels(GUILD_ID)
    assert channels["verification_channel_id"] == 1001
    assert channels["bot_spam_channel_id"] == 1002
    assert channels["public_announcement_channel_id"] == 1003
    assert channels["leadership_announcement_channel_id"] == 1004


@pytest.mark.asyncio
async def test_config_get_jtc_channels(temp_db: str) -> None:
    """Test get_jtc_channels with list of channel IDs."""
    repo = ConfigRepository()

    # Set JTC channels as list of integers
    jtc_list = [2001, 2002, 2003]
    await repo.set_setting(GUILD_ID, "voice.jtc_channels", jtc_list)

    channels = await repo.get_jtc_channels(GUILD_ID)
    assert channels == jtc_list
    assert isinstance(channels, list)
    assert all(isinstance(c, int) for c in channels)


@pytest.mark.asyncio
async def test_config_get_role_ids(temp_db: str) -> None:
    """Test get_role_ids generic method for list role configs."""
    repo = ConfigRepository()

    # Set a list of role IDs
    role_list = [100, 200, 300]
    await repo.set_setting(GUILD_ID, "roles.moderators", role_list)

    roles = await repo.get_role_ids(GUILD_ID, "roles.moderators")
    assert roles == role_list


@pytest.mark.asyncio
async def test_config_get_single_setting_int(temp_db: str) -> None:
    """Test get_single_setting_int for channel/role ID parsing."""
    repo = ConfigRepository()

    # Set a channel ID
    await repo.set_setting(GUILD_ID, "channels.verification_channel_id", 5001)

    channel_id = await repo.get_single_setting_int(GUILD_ID, "channels.verification_channel_id")
    assert channel_id == 5001
    assert isinstance(channel_id, int)

    # Non-existent setting returns None
    result = await repo.get_single_setting_int(GUILD_ID, "nonexistent")
    assert result is None
