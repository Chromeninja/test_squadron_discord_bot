from unittest.mock import AsyncMock, MagicMock

import pytest

from helpers.leadership_log import (
    ChangeSet,
    EventType,
    InitiatorKind,
    escape_md,
    # build_message,
    # is_effectively_unchanged,
    post_if_changed,
)


class DummyRole:
    def __init__(self, role_id: int, name: str) -> None:
        self.id = role_id
        self.name = name


class DummyGuild:
    def __init__(self) -> None:
        self.id = 123


class DummyBot:
    def __init__(self) -> None:
        self._channel = object()
        # Simulate managed roles (names used for filtering)
        self.BOT_VERIFIED_ROLE_ID = 1001
        self.MAIN_ROLE_ID = 1002
        self.AFFILIATE_ROLE_ID = 1003
        self.NON_MEMBER_ROLE_ID = 1004
        self.role_cache = {
            1001: DummyRole(1001, "BotVerified"),
            1002: DummyRole(1002, "Member"),
            1003: DummyRole(1003, "Affiliate"),
            1004: DummyRole(1004, "Not a Member"),
        }
        self._guild = DummyGuild()
        self.guilds = [self._guild]  # minimal for role lookup fallback

        # Mock services
        self.services = MagicMock()
        mock_config = AsyncMock()
        mock_config.get_global_setting = AsyncMock(return_value="compact")
        self.services.config = mock_config

        mock_guild_config = AsyncMock()
        mock_guild_config.get_channel = AsyncMock(return_value=self._channel)
        self.services.guild_config = mock_guild_config

    def get_channel(self, cid):
        return self._channel if cid == 123 else None

    def get_guild(self, guild_id):
        return self._guild if guild_id == 123 else None


# =============================================================================
# Parametrized: No-change / suppression scenarios
# =============================================================================
@pytest.mark.parametrize(
    "event,initiator,moniker_before,moniker_after,expect_sent,expect_text",
    [
        pytest.param(
            EventType.AUTO_CHECK,
            InitiatorKind.AUTO,
            None,
            None,
            False,
            None,
            id="auto_no_fields_suppressed",
        ),
        pytest.param(
            EventType.RECHECK,
            InitiatorKind.USER,
            "Alpha",
            "alpha",
            True,
            "No changes",
            id="case_only_moniker_shows_no_changes",
        ),
        pytest.param(
            EventType.AUTO_CHECK,
            InitiatorKind.AUTO,
            None,
            "NewMoniker",
            False,
            None,
            id="auto_initial_moniker_population_suppressed",
        ),
    ],
)
@pytest.mark.asyncio
async def test_no_change_suppression_scenarios(
    monkeypatch,
    event,
    initiator,
    moniker_before,
    moniker_after,
    expect_sent,
    expect_text,
) -> None:
    """Test various scenarios where no meaningful change should be posted."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=1,
        event=event,
        initiator_kind=initiator,
        guild_id=123,
    )
    if moniker_before is not None or moniker_after is not None:
        cs.moniker_before = moniker_before
        cs.moniker_after = moniker_after

    await post_if_changed(bot, cs)

    if expect_sent:
        assert len(sent) == 1
        if expect_text:
            assert expect_text in sent[0]
    else:
        assert not sent


# =============================================================================
# Parametrized: Single field change scenarios
# =============================================================================
@pytest.mark.parametrize(
    "event,initiator,field_name,before,after,initiator_name,expected_label",
    [
        pytest.param(
            EventType.VERIFICATION,
            InitiatorKind.USER,
            "moniker",
            "(none)",
            "NewMoniker",
            None,
            "Moniker:",
            id="user_verify_moniker_change",
        ),
        pytest.param(
            EventType.ADMIN_ACTION,
            InitiatorKind.ADMIN,
            "handle",
            "OldH",
            "NewH",
            "AdminX",
            "Handle: OldH → NewH",
            id="admin_handle_change",
        ),
        pytest.param(
            EventType.AUTO_CHECK,
            InitiatorKind.AUTO,
            "moniker",
            "Old",
            "New",
            None,
            "Moniker:",
            id="auto_moniker_change",
        ),
    ],
)
@pytest.mark.asyncio
async def test_single_field_change_scenarios(
    monkeypatch,
    event,
    initiator,
    field_name,
    before,
    after,
    initiator_name,
    expected_label,
) -> None:
    """Test that single field changes produce expected output."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=2,
        event=event,
        initiator_kind=initiator,
        initiator_name=initiator_name,
        guild_id=123,
    )
    setattr(cs, f"{field_name}_before", before)
    setattr(cs, f"{field_name}_after", after)

    await post_if_changed(bot, cs)

    assert len(sent) == 1
    assert expected_label in sent[0]


# =============================================================================
# Parametrized: Multi-field change scenarios
# =============================================================================
@pytest.mark.parametrize(
    "event,initiator,fields,expected_labels,unexpected_labels,initiator_name",
    [
        pytest.param(
            EventType.ADMIN_ACTION,
            InitiatorKind.ADMIN,
            {
                "status_before": "Affiliate",
                "status_after": "Main",
                "username_before": "OldNick",
                "username_after": "NewNick",
            },
            ["Status: Affiliate → Main", "Username: OldNick → NewNick"],
            ["Handle:"],
            "Adm",
            id="status_and_username_multiline",
        ),
        pytest.param(
            EventType.VERIFICATION,
            InitiatorKind.USER,
            {
                "handle_before": "OldHandle",
                "handle_after": "NewHandle",
                "username_before": "OldHandle",
                "username_after": "NewHandle",
            },
            ["Handle:", "Username:"],
            [],
            None,
            id="handle_and_username_both_lines",
        ),
        pytest.param(
            EventType.AUTO_CHECK,
            InitiatorKind.AUTO,
            {
                "moniker_before": None,
                "moniker_after": "NewMoniker",
                "handle_before": "OldHandle",
                "handle_after": "NewHandle",
            },
            ["Handle:"],
            ["Moniker:"],
            None,
            id="auto_moniker_suppressed_handle_shown",
        ),
    ],
)
@pytest.mark.asyncio
async def test_multi_field_change_scenarios(
    monkeypatch,
    event,
    initiator,
    fields,
    expected_labels,
    unexpected_labels,
    initiator_name,
) -> None:
    """Test that multi-field changes produce expected output lines."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=5,
        event=event,
        initiator_kind=initiator,
        initiator_name=initiator_name,
        guild_id=123,
    )
    for attr, value in fields.items():
        setattr(cs, attr, value)

    await post_if_changed(bot, cs)

    assert len(sent) == 1
    for label in expected_labels:
        assert label in sent[0], f"Expected '{label}' in message"
    for label in unexpected_labels:
        assert label not in sent[0], f"Did not expect '{label}' in message"


# =============================================================================
# Distinct behavior tests (not consolidated)
# =============================================================================
@pytest.mark.asyncio
async def test_roles_diff_not_rendered(monkeypatch) -> None:
    """Roles changes should not be rendered in output."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=4,
        event=EventType.ADMIN_ACTION,
        initiator_kind=InitiatorKind.ADMIN,
        initiator_name="Adm",
        guild_id=123,
    )
    cs.roles_added = ["Member"]
    cs.roles_removed = ["Affiliate"]
    await post_if_changed(bot, cs)
    # No other field changed so this should be considered
    # no-change and still post header (admin path)
    assert len(sent) == 1
    assert "Roles:" not in sent[0]


@pytest.mark.asyncio
async def test_no_change_admin_and_user_post(monkeypatch) -> None:
    """Both admin and user recheck should post even with no changes."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs_admin = ChangeSet(
        user_id=10,
        event=EventType.ADMIN_ACTION,
        initiator_kind=InitiatorKind.ADMIN,
        initiator_name="Adm",
        guild_id=123,
    )
    await post_if_changed(bot, cs_admin)
    cs_user_recheck = ChangeSet(
        user_id=11,
        event=EventType.RECHECK,
        initiator_kind=InitiatorKind.USER,
        guild_id=123,
    )
    await post_if_changed(bot, cs_user_recheck)
    assert len(sent) == 2
    assert sent[0].endswith("No changes") or "No changes" in sent[0]
    assert sent[1]  # user recheck posts even without changes per spec


def test_escape_md_prevents_markdown_injection() -> None:
    """Escape function should wrap in backticks and escape special chars."""
    raw = "*weird*_`test`"
    esc = escape_md(raw)
    assert esc.startswith("`")
    assert esc.endswith("`")
    assert "\\*" in esc
    assert "\\_" in esc
    assert "\\`" in esc


@pytest.mark.asyncio
async def test_dedupe(monkeypatch) -> None:
    """Same changeset should only be posted once."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=50,
        event=EventType.AUTO_CHECK,
        initiator_kind=InitiatorKind.AUTO,
        guild_id=123,
    )
    cs.moniker_before = "Old"
    cs.moniker_after = "New"
    await post_if_changed(bot, cs)
    await post_if_changed(bot, cs)
    assert len(sent) == 1
