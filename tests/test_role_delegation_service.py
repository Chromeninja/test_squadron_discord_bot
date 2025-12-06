from typing import TYPE_CHECKING, cast

import pytest

from services.role_delegation_service import RoleDelegationService

if TYPE_CHECKING:
    import discord


class DummyConfig:
    def __init__(self, policies):
        self.policies = policies

    async def get_guild_setting(self, guild_id, key, default=None):
        if key == "roles.delegation_policies":
            return self.policies
        return default


class DummyRole:
    def __init__(self, role_id: int):
        self.id = role_id


class DummyMember:
    def __init__(self, member_id: int, roles: list[int]):
        self.id = member_id
        self.roles = [DummyRole(rid) for rid in roles]
        self.add_roles_called = False
        self.add_roles_args = None

    async def add_roles(self, role_obj, reason=None):
        self.add_roles_called = True
        self.add_roles_args = (role_obj, reason)


class DummyGuild:
    def __init__(self, guild_id: int, roles: list[int]):
        self.id = guild_id
        self._roles = {rid: DummyRole(rid) for rid in roles}

    def get_role(self, role_id: int):
        return self._roles.get(role_id)


@pytest.mark.asyncio
async def test_can_grant_allows_when_requirements_met():
    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids": [444],
            "enabled": True,
        }
    ]
    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333, 444])
    grantor = DummyMember(10, [111])
    target = DummyMember(11, [444])

    allowed, reason = await svc.can_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_can_grant_blocks_missing_required():
    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids": [444],
        }
    ]
    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333, 444])
    grantor = DummyMember(10, [111])
    target = DummyMember(11, [])

    allowed, reason = await svc.can_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )
    assert allowed is False
    assert "missing" in reason.lower()


@pytest.mark.asyncio
async def test_can_grant_requires_any_role():
    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids_any": [999],
        }
    ]
    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333, 999])
    grantor = DummyMember(10, [111])
    target = DummyMember(11, [])

    allowed, reason = await svc.can_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )
    assert allowed is False
    assert "needs at least one" in reason.lower()

    target.roles.append(DummyRole(999))
    allowed2, reason2 = await svc.can_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )
    assert allowed2 is True
    assert reason2 == ""


@pytest.mark.asyncio
async def test_can_grant_ignores_disabled_policy():
    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids": [],
            "enabled": False,
        }
    ]
    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333, 555])
    grantor = DummyMember(10, [111])
    target = DummyMember(11, [])

    allowed, reason = await svc.can_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )
    assert allowed is False
    assert "policy" in reason.lower() or reason != ""


@pytest.mark.asyncio
async def test_apply_grant_invokes_discord_add_roles(monkeypatch):
    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids": [],
        }
    ]
    called = {}

    async def fake_add_roles(member, role_obj, reason=None):
        called["member"] = member
        called["role"] = role_obj
        called["reason"] = reason

    monkeypatch.setattr("services.role_delegation_service.add_roles", fake_add_roles)

    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333])
    grantor = DummyMember(10, [111])
    target = DummyMember(11, [])

    success, reason = await svc.apply_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )

    assert success is True
    assert reason == ""
    assert called["member"] is target
    assert called["role"].id == 333
    assert "Delegated" in (called["reason"] or "")
