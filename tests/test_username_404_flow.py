import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from helpers.database import Database
from helpers.username_404 import handle_username_404
from helpers import task_queue as tq
from cogs.recheck import AutoRecheck
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
    spam_call = send_mock.await_args_list[0]
    spam_msg = spam_call[0][1]
    assert member.mention in spam_msg
    assert f"<#{bot.VERIFICATION_CHANNEL_ID}>" in spam_msg
    assert "reverify your account" in spam_msg.lower()

    # Second call should be idempotent (no change)
    changed2 = await handle_username_404(bot, member, "OldHandle")
    assert changed2 is False
    # No additional sends
    assert send_mock.await_count == 1

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
