from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.admin.role_delegation import RoleDelegationCog
from helpers.permissions_helper import PermissionLevel
from tests.factories import make_guild, make_interaction


def test_role_grant_has_no_default_permissions(mock_bot) -> None:
    """`/role-grant` should not be hidden behind manage_roles defaults."""

    cog = RoleDelegationCog(mock_bot)

    assert cog.role_grant.default_permissions is None


@pytest.mark.asyncio
async def test_role_grant_does_not_require_staff_decorator(
    monkeypatch: pytest.MonkeyPatch, mock_bot
) -> None:
    """Non-staff members should reach delegation policy checks."""

    async def fake_get_permission_level(*_args, **_kwargs) -> PermissionLevel:
        return PermissionLevel.USER

    monkeypatch.setattr(
        "helpers.decorators.get_permission_level",
        fake_get_permission_level,
    )

    service = SimpleNamespace(
        can_grant=AsyncMock(return_value=(False, "Policy denied")),
        apply_grant=AsyncMock(return_value=(True, "")),
    )
    mock_bot.services = SimpleNamespace(role_delegation=service)

    cog = RoleDelegationCog(mock_bot)
    guild = make_guild(guild_id=123)

    grantor = MagicMock(spec=discord.Member)
    grantor.id = 10
    grantor.mention = "<@10>"

    target = MagicMock(spec=discord.Member)
    target.id = 11
    target.mention = "<@11>"

    role = MagicMock(spec=discord.Role)
    role.id = 333
    role.mention = "<@&333>"

    interaction = make_interaction(user=grantor, guild=guild)
    interaction.command = SimpleNamespace(qualified_name="role-grant")

    await cog.role_grant.callback(cog, interaction, target, role)  # type: ignore[arg-type]

    service.can_grant.assert_awaited_once_with(guild, grantor, target, role.id)
    service.apply_grant.assert_not_awaited()
    assert len(interaction.followup._messages) == 1
    assert "Cannot grant" in interaction.followup._messages[0]["content"]


@pytest.mark.asyncio
async def test_role_grant_success_sends_confirmation(mock_bot) -> None:
    """Successful grants should call the service and send a success message."""
    service = SimpleNamespace(
        can_grant=AsyncMock(return_value=(True, "")),
        apply_grant=AsyncMock(return_value=(True, "")),
    )
    mock_bot.services = SimpleNamespace(role_delegation=service)

    cog = RoleDelegationCog(mock_bot)
    guild = make_guild(guild_id=321)

    grantor = MagicMock(spec=discord.Member)
    grantor.id = 10
    grantor.mention = "<@10>"

    target = MagicMock(spec=discord.Member)
    target.id = 11
    target.mention = "<@11>"

    role = MagicMock(spec=discord.Role)
    role.id = 333
    role.mention = "<@&333>"

    interaction = make_interaction(user=grantor, guild=guild)
    interaction.command = SimpleNamespace(qualified_name="role-grant")

    await cog.role_grant.callback(cog, interaction, target, role)  # type: ignore[arg-type]

    service.can_grant.assert_awaited_once_with(guild, grantor, target, role.id)
    service.apply_grant.assert_awaited_once_with(
        guild,
        grantor,
        target,
        role.id,
        reason=f"Delegated grant by {grantor} via /role-grant",
    )
    assert interaction.followup._messages == [
        {
            "content": f"✅ Granted {role.mention} to {target.mention}.",
            "ephemeral": True,
        }
    ]


@pytest.mark.asyncio
async def test_role_revoke_failure_surfaces_service_reason(mock_bot) -> None:
    """Failed revokes should return the service-provided reason to the user."""
    service = SimpleNamespace(
        apply_revoke=AsyncMock(return_value=(False, "Policy denied")),
    )
    mock_bot.services = SimpleNamespace(role_delegation=service)

    cog = RoleDelegationCog(mock_bot)
    guild = make_guild(guild_id=654)

    revoker = MagicMock(spec=discord.Member)
    revoker.id = 12
    revoker.mention = "<@12>"

    target = MagicMock(spec=discord.Member)
    target.id = 13
    target.mention = "<@13>"

    role = MagicMock(spec=discord.Role)
    role.id = 444
    role.mention = "<@&444>"

    interaction = make_interaction(user=revoker, guild=guild)

    await cog.role_revoke.callback(cog, interaction, target, role)  # type: ignore[arg-type]

    service.apply_revoke.assert_awaited_once_with(
        guild,
        revoker,
        target,
        role.id,
        reason=f"Delegated revoke by {revoker} via /role-revoke",
    )
    assert interaction.followup._messages == [
        {
            "content": f"❌ Cannot revoke {role.mention}: Policy denied",
            "ephemeral": True,
        }
    ]
