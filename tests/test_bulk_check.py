# tests/test_bulk_check.py

from unittest.mock import AsyncMock, Mock

import pytest

from helpers.bulk_check import (
    MENTION_RE,
    StatusRow,
    _format_detail_line,
    _get_effective_status,
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


def test_mention_regex() -> None:
    """Test the mention regular expression."""
    text = "@user1 <@123456789012345678> <@!987654321098765432> 111222333444555666 not_a_mention 123"

    matches = list(MENTION_RE.finditer(text))
    assert len(matches) == 3

    # Test that we extract the right IDs using helper function
    ids = [_extract_id_from_match(match) for match in matches]

    expected_ids = [123456789012345678, 987654321098765432, 111222333444555666]
    assert ids == expected_ids


@pytest.mark.asyncio
async def test_parse_members_text() -> None:
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
        111222333444555666: None,  # Not found in cache
    }.get(user_id)

    guild.fetch_member = AsyncMock(
        side_effect=lambda user_id: {
            111222333444555666: Mock(id=111222333444555666)
        }.get(user_id)
    )

    text = "<@123456789012345678> <@!987654321098765432> 111222333444555666"

    members = await parse_members_text(guild, text)

    assert len(members) == 3
    member_ids = [member.id for member in members]
    expected_ids = [123456789012345678, 987654321098765432, 111222333444555666]
    assert member_ids == expected_ids


@pytest.mark.asyncio
async def test_parse_members_text_deduplicates_while_preserving_order() -> None:
    """Duplicate mentions should be collapsed without reordering first appearance."""
    # Arrange
    guild = Mock()

    member1 = Mock()
    member1.id = 123456789012345678

    member2 = Mock()
    member2.id = 987654321098765432

    guild.get_member.side_effect = lambda user_id: {
        123456789012345678: member1,
        987654321098765432: member2,
    }.get(user_id)
    guild.fetch_member = AsyncMock()

    text = "<@987654321098765432> <@123456789012345678> <@!987654321098765432>"

    # Act
    members = await parse_members_text(guild, text)

    # Assert
    assert [member.id for member in members] == [
        987654321098765432,
        123456789012345678,
    ]


@pytest.mark.asyncio
async def test_collect_targets_users() -> None:
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
async def test_collect_targets_voice_channel() -> None:
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
async def test_collect_targets_active_voice() -> None:
    """Test collecting targets in active voice mode."""
    guild = Mock()

    member1 = Mock()
    member1.id = 1
    member2 = Mock()
    member2.id = 2
    member3 = Mock()
    member3.id = 3

    # Mock voice channels
    vc1 = Mock()
    vc1.members = [member1, member2]

    vc2 = Mock()
    vc2.members = [member3]

    vc3 = Mock()
    vc3.members = []  # Empty channel should be ignored

    guild.voice_channels = [vc1, vc2, vc3]

    members = await collect_targets("active_voice", guild, None, None)

    # Should get unique members from non-empty channels in channel/member order
    assert members == [member1, member2, member3]


@pytest.mark.asyncio
async def test_collect_targets_active_voice_deduplicates_without_reordering() -> None:
    """Members in multiple channels should keep their first-seen position."""
    # Arrange
    guild = Mock()

    member1 = Mock()
    member1.id = 1
    member2 = Mock()
    member2.id = 2
    member3 = Mock()
    member3.id = 3

    vc1 = Mock()
    vc1.members = [member2, member1]

    vc2 = Mock()
    vc2.members = [member1, member3]

    guild.voice_channels = [vc1, vc2]

    # Act
    members = await collect_targets("active_voice", guild, None, None)

    # Assert
    assert members == [member2, member1, member3]


def test_status_row() -> None:
    """Test StatusRow structure."""
    row = StatusRow(
        user_id=123,
        username="TestUser",
        rsi_handle="test_handle",
        membership_status="main",
        last_updated=1609459200,
        voice_channel="General",
    )

    assert row.user_id == 123
    assert row.username == "TestUser"
    assert row.rsi_handle == "test_handle"
    assert row.membership_status == "main"
    assert row.last_updated == 1609459200
    assert row.voice_channel == "General"


def test_build_summary_embed() -> None:
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
        members=members,  # type: ignore[arg-type]
        rows=rows,
        truncated_count=0,
        scope_label="specific users",
        scope_channel="#test-channel",
    )

    assert embed.title == "Bulk Verification Check"
    desc = embed.description or ""
    assert "**Requested by:** <@12345> (Admin)" in desc
    assert "**Scope:** specific users" in desc
    assert "**Channel:** #test-channel" in desc
    assert "**Checked:** 3 users" in desc
    assert "**Verified/Main:** 1" in desc
    assert "**Affiliate:** 1" in desc
    assert "**Unverified:** 1" in desc


def test_build_summary_embed_sets_footer_when_details_are_truncated() -> None:
    """Embed footer should surface when detail rows exceed the field budget."""
    # Arrange
    invoker = Mock()
    invoker.mention = "<@12345>"
    invoker.display_name = "TestAdmin"

    rows = [
        StatusRow(
            index,
            f"User{index}",
            f"handle_{index}",
            "main",
            1609459200,
            "General",
        )
        for index in range(1, 20)
    ]

    # Act
    embed = build_summary_embed(
        invoker=invoker,
        members=[],  # type: ignore[arg-type]
        rows=rows,
        truncated_count=0,
    )

    # Assert
    assert embed.footer.text is not None
    assert "see CSV for full results" in embed.footer.text
    assert embed.fields
    detail_value = embed.fields[0].value
    assert detail_value is not None
    detail_lines = detail_value.split("\n")
    assert len(detail_lines) < len(rows)


@pytest.mark.asyncio
async def test_write_csv() -> None:
    """Test CSV writing functionality."""
    rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", None, "unknown", None, None),
    ]

    filename, content_bytes = await write_csv(
        rows, guild_name="TestGuild", invoker_name="TestAdmin"
    )

    # Check filename format: verify_bulk_{guild}_{YYYYMMDD_HHMM}_{invoker}.csv
    assert filename.startswith("verify_bulk_TestGuild_")
    assert filename.endswith("_TestAdmin.csv")
    assert ".csv" in filename

    content = content_bytes.decode("utf-8")
    lines = content.strip().split("\n")

    # Check header includes RSI recheck fields and org affiliations
    assert (
        lines[0].strip()
        == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error,main_orgs,affiliate_orgs"
    )

    # Check data rows (RSI fields and org fields should be empty for rows without recheck)
    assert "1,User1,handle1,main,1609459200,General,,,,," in lines[1]
    assert "2,User2,handle2,affiliate,1609459200,Gaming,,,,," in lines[2]
    assert "3,User3,,unknown,,,,,,," in lines[3]  # All optional fields are None


@pytest.mark.asyncio
async def test_write_csv_empty() -> None:
    """Test CSV writing with empty rows."""
    filename, content_bytes = await write_csv(
        [], guild_name="TestGuild", invoker_name="TestAdmin"
    )

    # Check filename format even for empty results
    assert filename.startswith("verify_bulk_TestGuild_")
    assert filename.endswith("_TestAdmin.csv")

    content = content_bytes.decode("utf-8")
    assert (
        content
        == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error,main_orgs,affiliate_orgs\n"
    )


def test_status_row_with_rsi_recheck() -> None:
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
        rsi_error=None,
    )

    assert row.user_id == 123
    assert row.username == "TestUser"
    assert row.rsi_handle == "test_handle"
    assert row.membership_status == "main"
    assert row.last_updated == 1609459200
    assert row.voice_channel == "General"
    assert row.rsi_status == "affiliate"
    assert row.rsi_checked_at == 1609459300


def test_build_summary_embed_with_rsi_recheck() -> None:
    """Test building the summary embed with RSI recheck data."""
    invoker = Mock()
    invoker.mention = "<@12345>"
    invoker.display_name = "TestAdmin"

    members = [Mock() for _ in range(3)]

    rows = [
        StatusRow(
            1, "User1", "handle1", "main", 1609459200, "General", "main", 1609459300
        ),
        StatusRow(
            2,
            "User2",
            "handle2",
            "affiliate",
            1609459200,
            "Gaming",
            "non_member",
            1609459300,
        ),
        StatusRow(3, "User3", "handle3", "unknown", None, None, "unknown", 1609459300),
    ]

    embed = build_summary_embed(
        invoker=invoker,
        members=members,  # type: ignore[arg-type]
        rows=rows,
        truncated_count=0,
        scope_label="specific users",
        scope_channel="#test-channel",
    )

    assert embed.title == "Bulk Verification Check"
    desc = embed.description or ""
    assert "**Requested by:** <@12345> (Admin)" in desc
    assert "**Scope:** specific users" in desc
    assert "**Channel:** #test-channel" in desc
    assert "**Checked:** 3 users" in desc


@pytest.mark.asyncio
async def test_write_csv_with_rsi_recheck() -> None:
    """Test CSV writing with RSI recheck data."""
    rows = [
        StatusRow(
            1,
            "User1",
            "handle1",
            "main",
            1609459200,
            "General",
            "main",
            1609459300,
            None,
        ),
        StatusRow(
            2,
            "User2",
            "handle2",
            "affiliate",
            1609459200,
            "Gaming",
            "non_member",
            1609459300,
            None,
        ),
        StatusRow(
            3,
            "User3",
            None,
            "unknown",
            None,
            None,
            "unknown",
            1609459300,
            "No RSI handle",
        ),
    ]

    filename, content_bytes = await write_csv(
        rows, guild_name="TestGuild", invoker_name="TestAdmin"
    )

    # Check filename format
    assert filename.startswith("verify_bulk_TestGuild_")
    assert filename.endswith("_TestAdmin.csv")
    assert ".csv" in filename

    content = content_bytes.decode("utf-8")
    lines = content.strip().split("\n")

    # Check header includes RSI recheck columns with error field and org affiliations
    assert (
        lines[0].strip()
        == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error,main_orgs,affiliate_orgs"
    )

    # Check data rows include RSI recheck data (org fields empty since not provided in StatusRow)
    assert "1,User1,handle1,main,1609459200,General,main,1609459300,,," in lines[1]
    assert (
        "2,User2,handle2,affiliate,1609459200,Gaming,non_member,1609459300,,,"
        in lines[2]
    )
    assert "3,User3,,unknown,,,unknown,1609459300,No RSI handle,," in lines[3]


@pytest.mark.asyncio
async def test_write_csv_with_org_data() -> None:
    """Test CSV writing with organization data."""
    rows = [
        StatusRow(
            1,
            "User1",
            "handle1",
            "main",
            1609459200,
            "General",
            "main",
            1609459300,
            None,
            rsi_main_orgs=["TEST Squadron", "Another Org"],
            rsi_affiliate_orgs=["Affiliate One"],
        ),
        StatusRow(
            2,
            "User2",
            "handle2",
            "affiliate",
            1609459200,
            "Gaming",
            "non_member",
            1609459300,
            None,
            rsi_main_orgs=None,
            rsi_affiliate_orgs=["Affiliate Two", "Affiliate Three"],
        ),
    ]

    _filename, content_bytes = await write_csv(
        rows, guild_name="TestGuild", invoker_name="TestAdmin"
    )

    content = content_bytes.decode("utf-8")
    lines = content.strip().split("\n")

    # Check header includes org columns
    assert (
        lines[0].strip()
        == "user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error,main_orgs,affiliate_orgs"
    )

    # Check data rows include organization data (semicolon-separated)
    assert (
        "1,User1,handle1,main,1609459200,General,main,1609459300,,TEST Squadron;Another Org,Affiliate One"
        in lines[1]
    )
    assert (
        "2,User2,handle2,affiliate,1609459200,Gaming,non_member,1609459300,,,Affiliate Two;Affiliate Three"
        in lines[2]
    )


def test_format_detail_line_without_rsi_recheck() -> None:
    """Test formatting a detail line without RSI recheck data."""
    row = StatusRow(
        user_id=123456789,
        username="TestUser",
        rsi_handle="test_handle",
        membership_status="main",
        last_updated=1609459200,
        voice_channel="General",
    )

    detail_line = _format_detail_line(row)

    # Verify the basic format (DB-only)
    assert "<@123456789>" in detail_line
    assert "Verified/Main" in detail_line
    assert "test_handle" in detail_line
    assert "General" in detail_line
    assert "DB:" not in detail_line  # No DB→RSI comparison when no recheck data
    assert "RSI:" in detail_line  # RSI handle label still present


def test_format_detail_line_with_rsi_recheck() -> None:
    """Test formatting a detail line with RSI recheck data showing status transition."""
    row = StatusRow(
        user_id=123456789,
        username="TestUser",
        rsi_handle="test_handle",
        membership_status="main",
        last_updated=1609459200,
        voice_channel="General",
        rsi_status="affiliate",  # Changed from main to affiliate
        rsi_checked_at=1609459300,
        rsi_error=None,
    )

    detail_line = _format_detail_line(row)

    # Verify the transition format (DB status → effective RSI status)
    assert "<@123456789>" in detail_line
    assert "Verified/Main" in detail_line  # DB status shown in transition
    assert "**Affiliate**" in detail_line  # Effective status bolded
    assert "Handle: test_handle" in detail_line
    assert "VC: General" in detail_line
    assert "RSI Checked:" in detail_line


def test_format_detail_line_with_rsi_error() -> None:
    """Test formatting a detail line when RSI recheck fails."""
    row = StatusRow(
        user_id=123456789,
        username="TestUser",
        rsi_handle=None,
        membership_status="unknown",
        last_updated=None,
        voice_channel=None,
        rsi_status="unknown",
        rsi_checked_at=1609459300,
        rsi_error="No RSI handle found",
    )

    detail_line = _format_detail_line(row)

    # Verify error case formatting
    assert "<@123456789>" in detail_line
    assert "Unverified" in detail_line
    assert "\u26a0\ufe0f RSI error" in detail_line  # Error indicator shown


# --- Regression tests for effective status and source-of-truth fixes ---


def test_get_effective_status_prefers_rsi_on_success() -> None:
    """Effective status should use rsi_status when available and no error."""
    row = StatusRow(
        user_id=1,
        username="u",
        rsi_handle="h",
        membership_status="main",
        last_updated=1,
        voice_channel=None,
        rsi_status="affiliate",
        rsi_checked_at=2,
        rsi_error=None,
    )
    assert _get_effective_status(row) == "affiliate"


def test_get_effective_status_falls_back_on_error() -> None:
    """Effective status should fall back to DB when RSI check had an error."""
    row = StatusRow(
        user_id=1,
        username="u",
        rsi_handle="h",
        membership_status="main",
        last_updated=1,
        voice_channel=None,
        rsi_status="non_member",
        rsi_checked_at=2,
        rsi_error="RSI fetch failed",
    )
    assert _get_effective_status(row) == "main"


def test_get_effective_status_falls_back_when_no_rsi() -> None:
    """Effective status should use DB when no RSI data present."""
    row = StatusRow(
        user_id=1,
        username="u",
        rsi_handle="h",
        membership_status="affiliate",
        last_updated=1,
        voice_channel=None,
    )
    assert _get_effective_status(row) == "affiliate"


def test_count_uses_effective_status_from_rsi() -> None:
    """Summary counts must use live RSI status, not stale DB status."""
    from helpers.bulk_check import _count_membership_statuses

    rows = [
        # DB says main, RSI says affiliate → should count as affiliate
        StatusRow(1, "u1", "h1", "main", 1, None, "affiliate", 2, None),
        # DB says affiliate, RSI says non_member → should count as non_member
        StatusRow(2, "u2", "h2", "affiliate", 1, None, "non_member", 2, None),
        # No RSI data → should count as DB status (main)
        StatusRow(3, "u3", "h3", "main", 1, None),
    ]

    counts = _count_membership_statuses(rows)
    assert counts["Verified/Main"] == 1  # User 3 (DB-only)
    assert counts["Affiliate"] == 1  # User 1 (RSI effective)
    assert counts["Non-Member"] == 1  # User 2 (RSI effective)


def test_count_falls_back_to_db_on_rsi_error() -> None:
    """Summary counts must fall back to DB status when RSI errored."""
    from helpers.bulk_check import _count_membership_statuses

    rows = [
        StatusRow(1, "u1", "h1", "affiliate", 1, None, "non_member", 2, "fetch error"),
    ]

    counts = _count_membership_statuses(rows)
    # RSI error → effective falls back to DB → affiliate
    assert counts["Affiliate"] == 1
    assert counts["Non-Member"] == 0


def test_format_detail_line_unchanged_status() -> None:
    """Detail line shows simple format when DB and RSI status match."""
    row = StatusRow(
        user_id=1,
        username="u",
        rsi_handle="handle",
        membership_status="main",
        last_updated=1,
        voice_channel=None,
        rsi_status="main",
        rsi_checked_at=2,
        rsi_error=None,
    )

    line = _format_detail_line(row)
    assert "Verified/Main" in line
    # No transition arrow when status unchanged
    assert "\u2192" not in line
    assert "**" not in line
