import pytest

from helpers.leadership_log import (
    ChangeSet,
    EventType,
    escape_md,
    # build_message,
    # is_effectively_unchanged,
    post_if_changed,
)


class DummyRole:
    def __init__(self, role_id: int, name: str) -> None:
        self.id = role_id
        self.name = name


class DummyBot:
    def __init__(self) -> None:
        self.config = {
            "channels": {"leadership_announcement_channel_id": 123},
            "leadership_log": {"verbosity": "compact"},
        }
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
        self.guilds = []  # minimal for role lookup fallback

    def get_channel(self, cid) -> None:
        return self._channel if cid == 123 else None


@pytest.mark.asyncio
async def test_auto_recheck_suppressed_when_no_change(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=1, event=EventType.AUTO_CHECK, initiator_kind="Auto")
    await post_if_changed(bot, cs)
    assert not sent  # suppressed


@pytest.mark.asyncio
async def test_user_verify_moniker_change(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=2, event=EventType.VERIFICATION, initiator_kind="User")
    cs.moniker_before = "(none)"
    cs.moniker_after = "NewMoniker"
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert "Moniker:" in sent[0]


@pytest.mark.asyncio
async def test_admin_recheck_handle_change_includes_handle_line(
    monkeypatch
) -> None:
    """Handle change should now produce a Handle line
    (policy: handle drives nickname)."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=3,
        event=EventType.ADMIN_CHECK,
        initiator_kind="Admin",
        initiator_name="AdminX",
    )
    cs.handle_before = "OldH"
    cs.handle_after = "NewH"
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert "Handle: OldH → NewH" in sent[0]
    # No username change present, so only one line besides header
    assert "Username:" not in sent[0]


@pytest.mark.asyncio
async def test_roles_diff_not_rendered(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=4,
        event=EventType.ADMIN_CHECK,
        initiator_kind="Admin",
        initiator_name="Adm",
    )
    cs.roles_added = ["Member"]
    cs.roles_removed = ["Affiliate"]
    await post_if_changed(bot, cs)
    # No other field changed so this should be considered
    # no-change and still post header (admin path)
    assert len(sent) == 1
    assert "Roles:" not in sent[0]


@pytest.mark.asyncio
async def test_status_and_nickname_changes_multiline(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(
        user_id=5,
        event=EventType.ADMIN_CHECK,
        initiator_kind="Admin",
        initiator_name="Adm",
    )
    cs.status_before = "Affiliate"
    cs.status_after = "Main"
    cs.username_before = "OldNick"
    cs.username_after = "NewNick"
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert "Status: Affiliate → Main" in sent[0]
    assert "Username: OldNick → NewNick" in sent[0]
    # Ensure old test still passes with new handle line logic when no handle change
    assert "Handle:" not in sent[0]


@pytest.mark.asyncio
async def test_no_change_admin_and_user_post(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs_admin = ChangeSet(
        user_id=10,
        event=EventType.ADMIN_CHECK,
        initiator_kind="Admin",
        initiator_name="Adm",
    )
    await post_if_changed(bot, cs_admin)
    cs_user_recheck = ChangeSet(
        user_id=11, event=EventType.RECHECK, initiator_kind="User"
    )
    await post_if_changed(bot, cs_user_recheck)
    assert len(sent) == 2
    assert sent[0].endswith("No changes") or "No changes" in sent[0]
    assert sent[1]  # user recheck posts even without changes per spec


def test_escape_md_prevents_markdown_injection() -> None:
    raw = "*weird*_`test`"
    esc = escape_md(raw)
    assert esc.startswith("`")
    assert esc.endswith("`")
    assert "\\*" in esc
    assert "\\_" in esc
    assert "\\`" in esc


@pytest.mark.asyncio
async def test_case_only_moniker_change_user_recheck_posts_no_change(
    monkeypatch
) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=30, event=EventType.RECHECK, initiator_kind="User")
    cs.moniker_before = "Alpha"
    cs.moniker_after = "alpha"
    await post_if_changed(bot, cs)
    # Should show header only (no changes)
    assert len(sent) == 1
    assert "Alpha → alpha" not in sent[0]
    assert "No changes" in sent[0]


@pytest.mark.asyncio
async def test_single_field_auto(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=40, event=EventType.AUTO_CHECK, initiator_kind="Auto")
    cs.moniker_before = "Old"
    cs.moniker_after = "New"
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    # Multi-line: header + field
    assert "\n" in sent[0]
    assert "Moniker:" in sent[0]


@pytest.mark.asyncio
async def test_handle_and_username_change_both_lines(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=60, event=EventType.VERIFICATION, initiator_kind="User")
    cs.handle_before = "OldHandle"
    cs.handle_after = "NewHandle"
    cs.username_before = "OldHandle"  # prior nickname followed old handle
    cs.username_after = "NewHandle"  # updated due to policy
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert "Handle:" in sent[0]
    assert "Username:" in sent[0]


@pytest.mark.asyncio
async def test_auto_moniker_initial_suppressed_handle_not_suppressed(
    monkeypatch
) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=61, event=EventType.AUTO_CHECK, initiator_kind="Auto")
    cs.moniker_before = None
    cs.moniker_after = "NewMoniker"
    cs.handle_before = "OldHandle"
    cs.handle_after = "NewHandle"
    await post_if_changed(bot, cs)
    # Should post because handle changed even though
    # moniker initial population suppressed
    assert len(sent) == 1
    assert "Handle:" in sent[0]
    # Moniker suppressed (initial population auto check)
    assert "Moniker:" not in sent[0]


@pytest.mark.asyncio
async def test_auto_initial_moniker_population_suppressed(
    monkeypatch
) -> None:
    """Auto check should NOT show moniker change if previous
    value absent/none placeholder."""
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=41, event=EventType.AUTO_CHECK, initiator_kind="Auto")
    cs.moniker_before = None  # or '(none)'
    cs.moniker_after = "NewMoniker"
    await post_if_changed(bot, cs)
    # Should suppress entirely (no message) because only change was initial population
    assert not sent


@pytest.mark.asyncio
async def test_dedupe(monkeypatch) -> None:
    bot = DummyBot()
    sent = []

    async def fake_send(channel, content, embed=None) -> None:
        sent.append(content)

    monkeypatch.setattr("helpers.leadership_log.channel_send_message", fake_send)
    cs = ChangeSet(user_id=50, event=EventType.AUTO_CHECK, initiator_kind="Auto")
    cs.moniker_before = "Old"
    cs.moniker_after = "New"
    await post_if_changed(bot, cs)
    await post_if_changed(bot, cs)
    assert len(sent) == 1
