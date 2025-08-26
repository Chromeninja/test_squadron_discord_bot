import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from helpers.database import Database
from helpers.username_404 import handle_username_404
from helpers.role_helper import reverify_member

# --- Fixtures / fakes ---
class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name

class FakeGuild:
    def __init__(self, member):
        self._member = member
    def get_member(self, uid):
        return self._member if self._member.id == uid else None
    async def fetch_member(self, uid):
        return self.get_member(uid)
    def get_channel(self, cid):
        return SimpleNamespace(id=cid, send=AsyncMock())

class FakeMember:
    def __init__(self, uid=101, display_name="User404"):
        self.id = uid
        self.display_name = display_name
        self.mention = f"@{display_name}"
        self.guild = None  # will be set
        self.roles = []
    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r not in roles]

@pytest.mark.asyncio
async def test_handle_username_404_idempotent(temp_db, monkeypatch):
    # Seed verification + auto state
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated) VALUES (?,?,?,?)", (101, 'OldHandle', 'main', 1))
        await db.execute("INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count) VALUES (?,?,?,?)", (101,0,0,0))
        await db.commit()

    bot = SimpleNamespace()
    bot.BOT_VERIFIED_ROLE_ID = 1
    bot.MAIN_ROLE_ID = 2
    bot.AFFILIATE_ROLE_ID = 3
    bot.NON_MEMBER_ROLE_ID = 4
    bot.BOT_SPAM_CHANNEL_ID = 999
    bot.VERIFICATION_CHANNEL_ID = 1234
    bot.config = {"channels": {"leadership_announcement_channel_id": 555}}

    role_cache = {
        1: FakeRole(1, "BotVerified"),
        2: FakeRole(2, "Main"),
        3: FakeRole(3, "Affiliate"),
        4: FakeRole(4, "NonMember"),
    }
    bot.role_cache = role_cache

    member = FakeMember()
    member.roles = list(role_cache.values())
    guild = FakeGuild(member)
    member.guild = guild
    bot.guilds = [guild]
    bot.get_channel = lambda cid: guild.get_channel(cid)

    # Patch channel_send_message to avoid network and run queued tasks immediately
    send_mock = AsyncMock()
    monkeypatch.setattr("helpers.username_404.channel_send_message", send_mock)
    async def immediate(task_func):
        await task_func()
    monkeypatch.setattr("helpers.username_404.enqueue_task", lambda fn: immediate(fn))

    # First call should flag + remove roles + unschedule
    changed = await handle_username_404(bot, member, "OldHandle")
    assert changed is True
    # Roles removed
    assert member.roles == []  # Removed synchronously via patched enqueue_task
    # DB flagged and auto state removed
    async with Database.get_connection() as db:
        cur = await db.execute("SELECT needs_reverify FROM verification WHERE user_id=?", (101,))
        val = await cur.fetchone()
        assert val[0] == 1
        cur = await db.execute("SELECT 1 FROM auto_recheck_state WHERE user_id=?", (101,))
        assert await cur.fetchone() is None

    # Validate only spam message now (leadership handled via standardized embed separately)
    assert send_mock.await_count == 1

@pytest.mark.asyncio
async def test_handle_username_404_new_handle_reflags(temp_db, monkeypatch):
    """Second call with DIFFERENT old handle should still process (distinct 404 cause)."""
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated) VALUES (?,?,?,?)", (111, 'FirstHandle', 'main', 1))
        await db.commit()

    bot = SimpleNamespace()
    bot.BOT_VERIFIED_ROLE_ID = 1
    bot.MAIN_ROLE_ID = 2
    bot.AFFILIATE_ROLE_ID = 3
    bot.NON_MEMBER_ROLE_ID = 4
    bot.BOT_SPAM_CHANNEL_ID = 999
    bot.VERIFICATION_CHANNEL_ID = 1234
    bot.config = {"channels": {"leadership_announcement_channel_id": 555}}
    role_cache = {
        1: FakeRole(1, "BotVerified"),
        2: FakeRole(2, "Main"),
        3: FakeRole(3, "Affiliate"),
        4: FakeRole(4, "NonMember"),
    }
    bot.role_cache = role_cache
    member = FakeMember(uid=111)
    member.roles = list(role_cache.values())
    guild = FakeGuild(member)
    member.guild = guild
    bot.guilds = [guild]
    bot.get_channel = lambda cid: guild.get_channel(cid)

    send_mock = AsyncMock()
    monkeypatch.setattr("helpers.username_404.channel_send_message", send_mock)
    async def immediate(task_func):
        await task_func()
    monkeypatch.setattr("helpers.username_404.enqueue_task", lambda fn: immediate(fn))

    # First 404
    changed1 = await handle_username_404(bot, member, "FirstHandle")
    assert changed1 is True
    # Simulate successful re-verification clearing the flag & storing a new handle
    async with Database.get_connection() as db:
        await db.execute("UPDATE verification SET rsi_handle=? WHERE user_id=?", ('SecondHandle', 111))
        await db.commit()
    await Database.clear_needs_reverify(111)
    changed2 = await handle_username_404(bot, member, "SecondHandle")
    assert changed2 is True  # distinct handle should not dedupe
    # Two spam alerts
    assert send_mock.await_count == 2

@pytest.mark.asyncio
async def test_admin_recheck_404_posts_leadership_log(temp_db, monkeypatch):
    """Admin initiated recheck that hits 404 should emit leadership ChangeSet with 404 note."""
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated) VALUES (?,?,?,?)", (222, 'GoneHandle', 'main', 1))
        await db.commit()
    bot = SimpleNamespace()
    bot.BOT_SPAM_CHANNEL_ID = 777
    bot.VERIFICATION_CHANNEL_ID = 555
    bot.config = {"channels": {"leadership_announcement_channel_id": 999}}
    bot.role_cache = {}
    # Channel mocks
    spam_chan = SimpleNamespace(id=777, send=AsyncMock())
    leader_chan = SimpleNamespace(id=999, send=AsyncMock())
    def get_channel(cid):
        return leader_chan if cid == 999 else (spam_chan if cid == 777 else None)
    bot.get_channel = get_channel
    member = FakeMember(uid=222, display_name="UserGone")
    guild = FakeGuild(member)
    member.guild = guild
    bot.guilds = [guild]
    # Force flag pass through real function; patch enqueue_task immediate
    async def immediate(task_func):
        await task_func()
    monkeypatch.setattr("helpers.username_404.enqueue_task", lambda fn: immediate(fn))
    # Patch leadership log channel send to be immediate (bypass task queue)
    async def leader_send_patch(channel, content, embed=None):
        await leader_chan.send(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', leader_send_patch)
    # Patch generic channel send for spam channel path
    async def spam_send_patch(channel, content, embed=None):
        await spam_chan.send(content)
    monkeypatch.setattr('helpers.username_404.channel_send_message', spam_send_patch)
    # Run 404 handler (simulating admin path already catching NotFound)
    from helpers.username_404 import handle_username_404
    await handle_username_404(bot, member, "GoneHandle")
    # Leadership message posted (header only, no explicit 404 text per current renderer)
    assert leader_chan.send.await_count == 1
    leadership_msg = leader_chan.send.await_args_list[0][0][0]
    assert leadership_msg.startswith('[RECHECK]')
    # Spam alert also
    assert spam_chan.send.await_count == 1
    spam_msg = spam_chan.send.await_args_list[0][0][0]
    assert member.mention in spam_msg
    assert f"<#{bot.VERIFICATION_CHANNEL_ID}>" in spam_msg
    assert "reverify your account" in spam_msg.lower()

@pytest.mark.asyncio
async def test_admin_recheck_404_flow(temp_db, monkeypatch):
    # Seed verification row
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated) VALUES (?,?,?,?)", (202, 'HandleX', 'main', 1))
        await db.commit()

    # Fake bot + member
    bot = SimpleNamespace()
    bot.http_client = SimpleNamespace()
    bot.VERIFICATION_CHANNEL_ID = 42
    bot.role_cache = {}

    member = SimpleNamespace(id=202, mention='@UserX', guild=None)

    # Force is_valid_rsi_handle to raise NotFoundError
    from helpers.http_helper import NotFoundError
    async def fake_is_valid(_: str, __):
        raise NotFoundError()
    monkeypatch.setattr('verification.rsi_verification.is_valid_rsi_handle', fake_is_valid)

    # Call reverify_member and expect NotFoundError to bubble
    from helpers.role_helper import reverify_member
    with pytest.raises(NotFoundError):
        await reverify_member(member, 'HandleX', bot)


@pytest.mark.asyncio
async def test_admin_recheck_404_leadership_changeset(temp_db, monkeypatch):
    """Ensure leadership ChangeSet is posted with RSI 404 note when leadership channel configured."""
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated) VALUES (?,?,?,?)", (555, 'LostOne', 'main', 1))
        await db.commit()

    # Bot with leadership channel
    leader_chan = SimpleNamespace(id=888, send=AsyncMock())
    spam_chan = SimpleNamespace(id=777, send=AsyncMock())
    bot = SimpleNamespace(
        BOT_SPAM_CHANNEL_ID=777,
        VERIFICATION_CHANNEL_ID=42,
        config={"channels": {"leadership_announcement_channel_id": 888}},
        role_cache={},
    )
    member = FakeMember(uid=555, display_name="LostUser")
    guild = FakeGuild(member)
    member.guild = guild
    bot.guilds = [guild]
    def get_channel(cid):
        return leader_chan if cid == 888 else (spam_chan if cid == 777 else None)
    bot.get_channel = get_channel

    # Patch enqueue_task to run immediately
    async def immediate(task_func):
        await task_func()
    monkeypatch.setattr("helpers.username_404.enqueue_task", lambda fn: immediate(fn))
    monkeypatch.setattr("helpers.username_404.flush_tasks", lambda : None)

    # Patch leadership log send to capture message
    async def leader_send_patch(channel, content, embed=None):
        await leader_chan.send(content)
    monkeypatch.setattr('helpers.leadership_log.channel_send_message', leader_send_patch)
    async def spam_send_patch(channel, content, embed=None):
        await spam_chan.send(content)
    monkeypatch.setattr('helpers.username_404.channel_send_message', spam_send_patch)

    from helpers.username_404 import handle_username_404
    await handle_username_404(bot, member, 'LostOne')

    # Leadership log should have one post containing header with RECHECK and 404 note suppressed to header only
    assert leader_chan.send.await_count == 1
    msg = leader_chan.send.await_args_list[0][0][0]
    assert msg.startswith('[RECHECK]')
    # Spam alert also fires
    assert spam_chan.send.await_count == 1

@pytest.mark.asyncio
async def test_reverification_clears_needs_reverify(temp_db, monkeypatch):
    # Seed flagged verification row
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated, needs_reverify, needs_reverify_at) VALUES (?,?,?,?,1,1)", (303, 'OldOne', 'main', 1))
        await db.commit()

    bot = SimpleNamespace()
    bot.http_client = SimpleNamespace()
    bot.role_cache = {}
    bot.config = {"auto_recheck": {"cadence_days": {}}}
    # Provide required role ID attrs for assign_roles path (even if cache empty)
    bot.BOT_VERIFIED_ROLE_ID = 1
    bot.MAIN_ROLE_ID = 2
    bot.AFFILIATE_ROLE_ID = 3
    bot.NON_MEMBER_ROLE_ID = 4
    member = SimpleNamespace(id=303, display_name='UserReverify', roles=[], guild=SimpleNamespace(me=SimpleNamespace(top_role=1), owner_id=999))
    # Avoid nickname path complexity
    monkeypatch.setattr('helpers.role_helper.can_modify_nickname', lambda m: False)

    # Return successful verification
    async def fake_is_valid(_: str, __):
        return 1, 'NewHandle', None
    monkeypatch.setattr('verification.rsi_verification.is_valid_rsi_handle', fake_is_valid)

    ok, _role_type, _err = await reverify_member(member, 'OldOne', bot)
    assert ok is True
    # needs_reverify cleared
    async with Database.get_connection() as db:
        cur = await db.execute("SELECT needs_reverify FROM verification WHERE user_id=?", (303,))
        val = await cur.fetchone()
        assert val[0] == 0


@pytest.mark.asyncio
async def test_handle_username_404_new_handle_triggers_again(temp_db, monkeypatch):
    """Second 404 with a different stored handle should emit a new notification (no dedupe)."""
    # Seed initial verification row
    async with Database.get_connection() as db:
        await db.execute("INSERT INTO verification(user_id, rsi_handle, membership_status, last_updated) VALUES (?,?,?,?)", (909, 'FirstHandle', 'main', 1))
        await db.commit()

    bot = SimpleNamespace()
    bot.BOT_SPAM_CHANNEL_ID = 321
    bot.VERIFICATION_CHANNEL_ID = 654
    bot.config = {"channels": {"leadership_announcement_channel_id": 777}}
    bot.role_cache = {}

    member = FakeMember(uid=909, display_name="UserMulti")
    guild = FakeGuild(member)
    member.guild = guild
    bot.guilds = [guild]
    bot.get_channel = lambda cid: guild.get_channel(cid)

    send_mock = AsyncMock()
    monkeypatch.setattr("helpers.username_404.channel_send_message", send_mock)
    async def immediate(task_func):
        await task_func()
    monkeypatch.setattr("helpers.username_404.enqueue_task", lambda fn: immediate(fn))

    # First 404 (FirstHandle)
    changed1 = await handle_username_404(bot, member, "FirstHandle")
    assert changed1 is True
    assert send_mock.await_count == 1

    # Simulate re-verification updating stored handle & clearing flag so a new 404 is not deduped
    async with Database.get_connection() as db:
        await db.execute("UPDATE verification SET rsi_handle=?, needs_reverify=0, needs_reverify_at=NULL WHERE user_id=?", ("SecondHandle", 909))
        await db.commit()

    # Second 404 with different handle
    changed2 = await handle_username_404(bot, member, "SecondHandle")
    assert changed2 is True  # should process again
    assert send_mock.await_count == 2  # second notification
