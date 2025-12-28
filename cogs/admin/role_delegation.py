"""Discord commands for delegated role grants."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.log_context import get_interaction_extra
from utils.logging import get_logger

if TYPE_CHECKING:
    from services.role_delegation_service import RoleDelegationService

logger = get_logger(__name__)


class RoleDelegationCog(commands.Cog):
    """Slash commands that enforce role delegation policies."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = get_logger(__name__)

    async def _get_service(self) -> RoleDelegationService:
        svc = getattr(getattr(self.bot, "services", None), "role_delegation", None)
        if not svc:
            raise RuntimeError("RoleDelegationService not initialized")
        return svc

    @app_commands.command(
        name="role-grant", description="Grant a role under delegation policy"
    )
    @app_commands.describe(member="Member to grant the role to", role="Role to grant")
    @app_commands.guild_only()
    async def role_grant(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        """Grant a role to a member if delegation policy permits."""
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "This command can only be used in a guild.", ephemeral=True
            )
            return

        grantor = interaction.user
        if not isinstance(grantor, discord.Member):
            await interaction.followup.send(
                "This command can only be used by guild members.", ephemeral=True
            )
            return

        try:
            svc = await self._get_service()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("RoleDelegationService unavailable", exc_info=exc)
            await interaction.followup.send(
                "Delegation service unavailable.", ephemeral=True
            )
            return

        allowed, reason = await svc.can_grant(
            interaction.guild, grantor, member, role.id
        )
        if not allowed:
            await interaction.followup.send(
                f"❌ Cannot grant {role.mention}: {reason}", ephemeral=True
            )
            return

        success, apply_reason = await svc.apply_grant(
            interaction.guild,
            grantor,
            member,
            role.id,
            reason=f"Delegated grant by {grantor} via /role-grant",
        )
        if not success:
            await interaction.followup.send(
                f"❌ Failed to grant {role.mention}: {apply_reason}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Granted {role.mention} to {member.mention}.", ephemeral=True
        )

        logger.info(
            "Delegated role granted via command",
            extra={
                **get_interaction_extra(interaction, target_user_id=str(member.id)),
                "granted_role_id": role.id,
            },
        )


async def setup(bot):
    await bot.add_cog(RoleDelegationCog(bot))
