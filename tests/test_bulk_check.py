# tests/test_bulk_check.py

from unittest.mock import AsyncMock, Mock

import pytest

from helpers.bulk_check import (
    MENTION_RE,
    StatusRow,
    build_summary_embed,
    collect_targets,
    parse_members_text,
    write_csv,
)


def _extract_id_from_match(match) -> int:
    """Helper to extract ID from a regex match object."""
    if match.group("id"):
        return int(match.group("id"))
    return int(match.group("raw"))


def test_mention_regex():
    """Test the mention regular expression."""
    text = "@user1 <@123456789012345678> <@!987654321098765432> 111222333444555666 not_a_mention 123"

    matches = list(MENTION_RE.finditer(text))
    assert len(matches) == 3

    # Test that we extract the right IDs using helper function
    ids = [_extract_id_from_match(match) for match in matches]

    expected_ids = [123456789012345678, 987654321098765432, 111222333444555666]
    assert ids == expected_ids


@pytest.mark.asyncio
async def test_parse_members_text():
    """Test parsing member text with mentions and IDs."""
    # Mock guild and members
    guild = Mock()

    member1 = Mock()
    member1.id = 123456789012345678

    member2 = Mock()
    member2.id = 987654321098765432

    guild.get_member.side_effect = lambda user_id: {
        123456789012345678: member1,
        987654321098765432: member2,
        111222333444555666: None  # Not found in cache
    }.get(user_id)

    guild.fetch_member = AsyncMock(side_effect=lambda user_id: {
        111222333444555666: Mock(id=111222333444555666)
    }.get(user_id))

    text = "<@123456789012345678> <@!987654321098765432> 111222333444555666"

    members = await parse_members_text(guild, text)

    assert len(members) == 3
    # Members can be in any order since we use sets internally
    member_ids = {member.id for member in members}
    expected_ids = {123456789012345678, 987654321098765432, 111222333444555666}
    assert member_ids == expected_ids


@pytest.mark.asyncio
async def test_collect_targets_users():
    """Test collecting targets in users mode."""
    guild = Mock()

    member1 = Mock()
    member1.id = 123

    guild.get_member.return_value = member1
    guild.fetch_member = AsyncMock(return_value=member1)

    members = await collect_targets("users", guild, "<@123>", None)

    assert len(members) == 1
    assert members[0].id == 123


@pytest.mark.asyncio
async def test_collect_targets_voice_channel():
    """Test collecting targets in voice channel mode."""
    guild = Mock()

    member1 = Mock()
    member2 = Mock()

    channel = Mock()
    channel.members = [member1, member2]

    members = await collect_targets("voice_channel", guild, None, channel)

    assert len(members) == 2
    assert members == [member1, member2]


@pytest.mark.asyncio
async def test_collect_targets_active_voice():
    """Test collecting targets in active voice mode."""
    guild = Mock()

    member1 = Mock()
    member2 = Mock()
    member3 = Mock()

    # Mock voice channels
    vc1 = Mock()
    vc1.members = [member1, member2]

    vc2 = Mock()
    vc2.members = [member3]

    vc3 = Mock()
    vc3.members = []  # Empty channel should be ignored

    guild.voice_channels = [vc1, vc2, vc3]

    members = await collect_targets("active_voice", guild, None, None)

    # Should get unique members from non-empty channels
    assert len(members) == 3
    assert member1 in members
    assert member2 in members
    assert member3 in members


def test_status_row():
    """Test StatusRow structure."""
    row = StatusRow(
        user_id=123,
        username="TestUser",
        rsi_handle="test_handle",
        membership_status="main",
        last_updated=1609459200,
        voice_channel="General"
    )

    assert row.user_id == 123
    assert row.username == "TestUser"
    assert row.rsi_handle == "test_handle"
    assert row.membership_status == "main"
    assert row.last_updated == 1609459200
    assert row.voice_channel == "General"


def test_build_summary_embed():
    """Test building the summary embed."""
    invoker = Mock()
    invoker.mention = "<@12345>"
    invoker.display_name = "TestAdmin"

    members = [Mock() for _ in range(3)]

    rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", None, "unknown", None, None),
    ]

    embed = build_summary_embed(
        invoker=invoker,
        members=members,
        rows=rows,
        truncated_count=0,
        scope_label="specific users",
        scope_channel="#test-channel"
    )

    assert embed.title == "Bulk Verification Check"
    assert "**Requested by:** <@12345> (Admin)" in embed.description
    assert "**Scope:** specific users" in embed.description
    assert "**Channel:** #test-channel" in embed.description
    assert "**Checked:** 3 users" in embed.description
    assert "**Verified/Main:** 1" in embed.description
    assert "**Affiliate:** 1" in embed.description
    assert "**Unverified:** 1" in embed.description


@pytest.mark.asyncio
async def test_write_csv():
    """Test CSV writing functionality."""
    rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", None, "unknown", None, None),
    ]

    filename, content_bytes = await write_csv(
        rows,
        guild_name="TestGuild",
        invoker_name="TestAdmin"
    )

    # Check filename format: verify_bulk_{guild}_{YYYYMMDD_HHMM}_{invoker}.csv
    assert filename.startswith("verify_bulk_TestGuild_")
    assert filename.endswith("_TestAdmin.csv")
    assert ".csv" in filename

    content = content_bytes.decode('utf-8')
    lines = content.strip().split('\n')

    # Check header includes RSI recheck fields (backward compatible)
    assert lines[0].strip() == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error"

    # Check data rows (RSI fields should be empty for rows without recheck)
    assert "1,User1,handle1,main,1609459200,General,,," in lines[1]
    assert "2,User2,handle2,affiliate,1609459200,Gaming,,," in lines[2]
    assert "3,User3,,unknown,,,,," in lines[3]  # All optional fields are None


@pytest.mark.asyncio
async def test_write_csv_empty():
    """Test CSV writing with empty rows."""
    filename, content_bytes = await write_csv(
        [],
        guild_name="TestGuild",
        invoker_name="TestAdmin"
    )

    # Check filename format even for empty results
    assert filename.startswith("verify_bulk_TestGuild_")
    assert filename.endswith("_TestAdmin.csv")

    content = content_bytes.decode('utf-8')
    assert content == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error\n"


def test_status_row_with_rsi_recheck():
    """Test StatusRow with RSI recheck fields."""
    row = StatusRow(
        user_id=123,
        username="TestUser",
        rsi_handle="test_handle",
        membership_status="main",
        last_updated=1609459200,
        voice_channel="General",
        rsi_status="affiliate",
        rsi_checked_at=1609459300,
        rsi_error=None
    )

    assert row.user_id == 123
    assert row.username == "TestUser"
    assert row.rsi_handle == "test_handle"
    assert row.membership_status == "main"
    assert row.last_updated == 1609459200
    assert row.voice_channel == "General"
    assert row.rsi_status == "affiliate"
    assert row.rsi_checked_at == 1609459300


def test_build_summary_embed_with_rsi_recheck():
    """Test building the summary embed with RSI recheck data."""
    invoker = Mock()
    invoker.mention = "<@12345>"
    invoker.display_name = "TestAdmin"

    members = [Mock() for _ in range(3)]

    rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General", "main", 1609459300),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming", "non_member", 1609459300),
        StatusRow(3, "User3", "handle3", "unknown", None, None, "unknown", 1609459300),
    ]

    embed = build_summary_embed(
        invoker=invoker,
        members=members,
        rows=rows,
        truncated_count=0,
        scope_label="specific users",
        scope_channel="#test-channel"
    )

    assert embed.title == "Bulk Verification Check"
    assert "**Requested by:** <@12345> (Admin)" in embed.description
    assert "**Scope:** specific users" in embed.description
    assert "**Channel:** #test-channel" in embed.description
    assert "**Checked:** 3 users" in embed.description


@pytest.mark.asyncio
async def test_write_csv_with_rsi_recheck():
    """Test CSV writing with RSI recheck data."""
    rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General", "main", 1609459300, None),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming", "non_member", 1609459300, None),
        StatusRow(3, "User3", None, "unknown", None, None, "unknown", 1609459300, "No RSI handle"),
    ]

    filename, content_bytes = await write_csv(
        rows,
        guild_name="TestGuild",
        invoker_name="TestAdmin"
    )

    # Check filename format
    assert filename.startswith("verify_bulk_TestGuild_")
    assert filename.endswith("_TestAdmin.csv")
    assert ".csv" in filename

    content = content_bytes.decode('utf-8')
    lines = content.strip().split('\n')

    # Check header includes RSI recheck columns with error field
    assert lines[0].strip() == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error"

    # Check data rows include RSI recheck data
    assert "1,User1,handle1,main,1609459200,General,main,1609459300," in lines[1]
    assert "2,User2,handle2,affiliate,1609459200,Gaming,non_member,1609459300," in lines[2]
    assert "3,User3,,unknown,,,unknown,1609459300,No RSI handle" in lines[3]

