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
    def __init__(self, role_id: int, name: str = "TestRole"):
        self.id = role_id
        self.name = name


class DummyMember:
    def __init__(self, member_id: int, roles: list[int], name: str = "TestUser"):
        self.id = member_id
        self.roles = [DummyRole(rid) for rid in roles]
        self.add_roles_called = False
        self.add_roles_args = None
        self.name = name
        self.display_name = name

    async def add_roles(self, role_obj, reason=None):
        self.add_roles_called = True
        self.add_roles_args = (role_obj, reason)


class DummyGuild:
    def __init__(self, guild_id: int, roles: list[int]):
        self.id = guild_id
        self._roles = {rid: DummyRole(rid, f"Role{rid}") for rid in roles}

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


@pytest.mark.asyncio
async def test_apply_grant_logs_leadership_change(monkeypatch):
    """Verify delegated role grants are logged to the leadership log with expected metadata."""
    from helpers.leadership_log import (
        ChangeSet,
        EventType,
        InitiatorKind,
    )

    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids": [],
        }
    ]

    # Track calls to post_if_changed
    captured_changeset: dict = {}

    async def fake_add_roles(member, role_obj, reason=None):
        pass  # No-op for role assignment

    async def fake_post_if_changed(bot, change_set: ChangeSet):
        captured_changeset["value"] = change_set

    monkeypatch.setattr("services.role_delegation_service.add_roles", fake_add_roles)
    monkeypatch.setattr(
        "services.role_delegation_service.post_if_changed", fake_post_if_changed
    )

    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333])
    grantor = DummyMember(10, [111], name="GrantorUser")
    target = DummyMember(11, [], name="TargetUser")

    success, reason = await svc.apply_grant(
        cast("discord.Guild", guild),
        cast("discord.Member", grantor),
        cast("discord.Member", target),
        333,
    )

    assert success is True
    assert reason == ""
    assert "value" in captured_changeset

    cs = captured_changeset["value"]
    assert isinstance(cs, ChangeSet)
    assert cs.event is EventType.ADMIN_ACTION
    assert cs.initiator_kind is InitiatorKind.ADMIN
    assert cs.user_id == target.id
    assert cs.guild_id == guild.id

    # Notes should include role name and grantor display_name with @
    notes = cs.notes or ""
    role = guild.get_role(333)
    assert role is not None
    assert role.name in notes
    assert f"@{grantor.display_name}" in notes


@pytest.mark.asyncio
async def test_apply_grant_logs_error_when_leadership_log_fails(monkeypatch, caplog):
    """Verify leadership log failures are logged but do not change apply_grant's return value."""
    import logging

    policies = [
        {
            "grantor_role_ids": [111],
            "target_role_id": 333,
            "prerequisite_role_ids": [],
        }
    ]

    async def fake_add_roles(member, role_obj, reason=None):
        pass  # No-op for role assignment

    async def failing_post_if_changed(bot, change_set):
        raise RuntimeError("simulated leadership log failure")

    monkeypatch.setattr("services.role_delegation_service.add_roles", fake_add_roles)
    monkeypatch.setattr(
        "services.role_delegation_service.post_if_changed", failing_post_if_changed
    )

    svc = RoleDelegationService(DummyConfig(policies), bot=None)
    await svc.initialize()

    guild = DummyGuild(1, [111, 333])
    grantor = DummyMember(10, [111], name="GrantorUser")
    target = DummyMember(11, [], name="TargetUser")

    with caplog.at_level(logging.DEBUG):
        success, reason = await svc.apply_grant(
            cast("discord.Guild", guild),
            cast("discord.Member", grantor),
            cast("discord.Member", target),
            333,
        )

    # apply_grant should still report success despite the logging failure
    assert success is True
    assert reason == ""

    # An error should have been logged mentioning the leadership log failure
    assert any(
        "leadership" in rec.message.lower() for rec in caplog.records
    )
