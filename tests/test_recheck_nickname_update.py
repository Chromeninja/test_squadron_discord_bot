import types

import pytest

from helpers.role_helper import assign_roles


class FakeRole:
    def __init__(self, rid, name) -> None:
        self.id = rid
        self.name = name


class FakeGuild:
    def __init__(self, owner_id, me_member) -> None:
        self.owner_id = owner_id
        self._me = me_member

    @property
    def me(self) -> None:  # bot member
        return self._me

    def get_role(self, rid) -> None:
        return None


class FakeBotMember:
    def __init__(self, top_role_position=10) -> None:
        self.top_role = types.SimpleNamespace(position=top_role_position)
        self.guild_permissions = types.SimpleNamespace(manage_nicknames=True)


class FakeMember:
    def __init__(self, user_id, display_name, guild, roles=None, nick=None) -> None:
        self.id = user_id
        self.display_name = display_name
        self.guild = guild
        self.roles = roles or []
        self.nick = nick


@pytest.mark.asyncio
async def test_assign_roles_updates_nickname_with_moniker(monkeypatch, temp_db) -> None:
    # Prepare bot namespace
    bot = types.SimpleNamespace()
    bot.config = {}
    # Role IDs
    bot.BOT_VERIFIED_ROLE_ID = 1
    bot.MAIN_ROLE_ID = 2
    bot.AFFILIATE_ROLE_ID = 3
    bot.NON_MEMBER_ROLE_ID = 4
    bot.role_cache = {
        1: FakeRole(1, "BotVerified"),
        2: FakeRole(2, "Main"),
        3: FakeRole(3, "Affiliate"),
        4: FakeRole(4, "NonMember"),
    }

    # Fake guild/me/member
    bot_member = FakeBotMember()
    guild = FakeGuild(owner_id=5000, me_member=bot_member)
    member = FakeMember(42, "Tester", guild, roles=[], nick=None)

    # Patch role/nick dependency helpers
    monkeypatch.setattr("helpers.role_helper.can_modify_nickname", lambda m: True)

    # Capture edit_member calls
    edits = {}

    async def fake_edit_member(member_obj, **kwargs) -> None:
        edits["nick"] = kwargs.get("nick")

    monkeypatch.setattr("helpers.role_helper.edit_member", fake_edit_member)

    async def immediate(task_fn) -> None:
        await task_fn()

    monkeypatch.setattr("helpers.role_helper.enqueue_task", lambda fn: immediate(fn))

    # Initial assignment with moniker1
    await assign_roles(member, 1, "CaseHandle", bot, community_moniker="Moniker One")
    # Policy: nickname always handle
    assert edits.get("nick") == "CaseHandle"

    # Second assignment with changed moniker
    await assign_roles(member, 1, "CaseHandle", bot, community_moniker="Moniker Two")
    assert edits.get("nick") == "CaseHandle"


@pytest.mark.asyncio
async def test_assign_roles_fallback_to_handle(monkeypatch, temp_db) -> None:
    bot = types.SimpleNamespace()
    bot.config = {}
    bot.BOT_VERIFIED_ROLE_ID = 1
    bot.MAIN_ROLE_ID = 2
    bot.AFFILIATE_ROLE_ID = 3
    bot.NON_MEMBER_ROLE_ID = 4
    bot.role_cache = {
        1: FakeRole(1, "BotVerified"),
        2: FakeRole(2, "Main"),
        3: FakeRole(3, "Affiliate"),
        4: FakeRole(4, "NonMember"),
    }
    bot_member = FakeBotMember()
    guild = FakeGuild(owner_id=5000, me_member=bot_member)
    member = FakeMember(43, "Tester2", guild, roles=[], nick=None)

    monkeypatch.setattr("helpers.role_helper.can_modify_nickname", lambda m: True)

    edits = {}

    async def fake_edit_member(member_obj, **kwargs) -> None:
        edits["nick"] = kwargs.get("nick")

    monkeypatch.setattr("helpers.role_helper.edit_member", fake_edit_member)

    async def immediate(task_fn) -> None:
        await task_fn()

    monkeypatch.setattr("helpers.role_helper.enqueue_task", lambda fn: immediate(fn))

    await assign_roles(member, 1, "HandleCase", bot, community_moniker=None)
    assert edits.get("nick") == "HandleCase"


@pytest.mark.asyncio
async def test_assign_roles_nickname_always_handle_even_if_moniker_present(
    monkeypatch, temp_db
) -> None:
    bot = types.SimpleNamespace()
    bot.config = {}
    bot.BOT_VERIFIED_ROLE_ID = 1
    bot.MAIN_ROLE_ID = 2
    bot.AFFILIATE_ROLE_ID = 3
    bot.NON_MEMBER_ROLE_ID = 4
    bot.role_cache = {
        1: FakeRole(1, "BotVerified"),
        2: FakeRole(2, "Main"),
        3: FakeRole(3, "Affiliate"),
        4: FakeRole(4, "NonMember"),
    }
    bot_member = FakeBotMember()
    guild = FakeGuild(owner_id=5000, me_member=bot_member)
    member = FakeMember(55, "Tester3", guild, roles=[], nick=None)

    monkeypatch.setattr("helpers.role_helper.can_modify_nickname", lambda m: True)

    edits = {}

    async def fake_edit_member(member_obj, **kwargs) -> None:
        edits.setdefault("calls", []).append(kwargs.get("nick"))
        edits["nick"] = kwargs.get("nick")

    monkeypatch.setattr("helpers.role_helper.edit_member", fake_edit_member)

    async def immediate(task_fn) -> None:
        await task_fn()

    monkeypatch.setattr("helpers.role_helper.enqueue_task", lambda fn: immediate(fn))

    await assign_roles(
        member, 1, "SuperHandle", bot, community_moniker="Different Moniker"
    )
    assert edits.get("nick") == "SuperHandle"
    # Re-run with different moniker to ensure it stays handle
    await assign_roles(
        member, 1, "SuperHandle", bot, community_moniker="Another Moniker"
    )
    assert edits.get("nick") == "SuperHandle"
    # Ensure calls captured both times with handle set
    assert all(c == "SuperHandle" for c in edits.get("calls", []))
