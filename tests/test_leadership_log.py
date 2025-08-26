import pytest

from helpers.leadership_log import (
    ChangeSet,
    EventType,
    post_if_changed,
    escape_md,
    # build_message,
    # is_effectively_unchanged,
)


class DummyRole:
    def __init__(self, role_id: int, name: str):
        self.id = role_id
        self.name = name


class DummyBot:
    def __init__(self):
        self.config = {"channels": {"leadership_announcement_channel_id": 123}, "leadership_log": {"verbosity": "compact"}}
        self._channel = object()
        # Simulate managed roles (names used for filtering)
        self.BOT_VERIFIED_ROLE_ID = 1001
        self.MAIN_ROLE_ID = 1002
        self.AFFILIATE_ROLE_ID = 1003
        self.NON_MEMBER_ROLE_ID = 1004
        self.role_cache = {
            1001: DummyRole(1001, 'BotVerified'),
            1002: DummyRole(1002, 'Member'),
            1003: DummyRole(1003, 'Affiliate'),
            1004: DummyRole(1004, 'Not a Member'),
        }
        self.guilds = []  # minimal for role lookup fallback

    def get_channel(self, cid):
        return self._channel if cid == 123 else None


@pytest.mark.asyncio
async def test_auto_recheck_suppressed_when_no_change(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=1, event=EventType.AUTO_CHECK, initiator_kind='Auto')
    await post_if_changed(bot, cs)
    assert sent == []  # suppressed


@pytest.mark.asyncio
async def test_user_verify_moniker_change(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=2, event=EventType.VERIFICATION, initiator_kind='User')
    cs.moniker_before = '(none)'
    cs.moniker_after = 'NewMoniker'
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert 'Moniker:' in sent[0]


@pytest.mark.asyncio
async def test_admin_recheck_handle_change_ignored(monkeypatch):
    """Handle changes alone are ignored; expect no-changes line."""
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=3, event=EventType.ADMIN_CHECK, initiator_kind='Admin', initiator_name='AdminX')
    cs.handle_before = 'OldH'
    cs.handle_after = 'NewH'
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert sent[0].endswith('No changes')


@pytest.mark.asyncio
async def test_roles_diff_not_rendered(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=4, event=EventType.ADMIN_CHECK, initiator_kind='Admin', initiator_name='Adm')
    cs.roles_added = ['Member']
    cs.roles_removed = ['Affiliate']
    await post_if_changed(bot, cs)
    # No other field changed so this should be considered no-change and still post header (admin path)
    assert len(sent) == 1
    assert 'Roles:' not in sent[0]


@pytest.mark.asyncio
async def test_status_and_nickname_changes_multiline(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=5, event=EventType.ADMIN_CHECK, initiator_kind='Admin', initiator_name='Adm')
    cs.status_before = 'Affiliate'
    cs.status_after = 'Main'
    cs.username_before = 'OldNick'
    cs.username_after = 'NewNick'
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    assert 'Status: Affiliate → Main' in sent[0]
    assert 'Username: OldNick → NewNick' in sent[0]


@pytest.mark.asyncio
async def test_no_change_admin_and_user_post(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs_admin = ChangeSet(user_id=10, event=EventType.ADMIN_CHECK, initiator_kind='Admin', initiator_name='Adm')
    await post_if_changed(bot, cs_admin)
    cs_user_recheck = ChangeSet(user_id=11, event=EventType.RECHECK, initiator_kind='User')
    await post_if_changed(bot, cs_user_recheck)
    assert len(sent) == 2
    assert sent[0].endswith('No changes') or 'No changes' in sent[0]
    assert sent[1]  # user recheck posts even without changes per spec


def test_escape_md_prevents_markdown_injection():
    raw = "*weird*_`test`"
    esc = escape_md(raw)
    assert esc.startswith('`') and esc.endswith('`')
    assert '\\*' in esc and '\\_' in esc and '\\`' in esc


@pytest.mark.asyncio
async def test_case_only_moniker_change_user_recheck_posts_no_change(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=30, event=EventType.RECHECK, initiator_kind='User')
    cs.moniker_before = 'Alpha'
    cs.moniker_after = 'alpha'
    await post_if_changed(bot, cs)
    # Should show header only (no changes)
    assert len(sent) == 1
    assert 'Alpha → alpha' not in sent[0]
    assert 'No changes' in sent[0]


@pytest.mark.asyncio
async def test_single_field_auto(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=40, event=EventType.AUTO_CHECK, initiator_kind='Auto')
    cs.moniker_before = 'Old'
    cs.moniker_after = 'New'
    await post_if_changed(bot, cs)
    assert len(sent) == 1
    # Multi-line: header + field
    assert '\n' in sent[0]
    assert 'Moniker:' in sent[0]


@pytest.mark.asyncio
async def test_dedupe(monkeypatch):
    bot = DummyBot()
    sent = []
    async def fake_send(channel, content, embed=None):
        sent.append(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', fake_send)
    cs = ChangeSet(user_id=50, event=EventType.AUTO_CHECK, initiator_kind='Auto')
    cs.moniker_before = 'Old'
    cs.moniker_after = 'New'
    await post_if_changed(bot, cs)
    await post_if_changed(bot, cs)
    assert len(sent) == 1
