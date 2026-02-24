"""
New-member role background worker and manual-removal listener.

Periodically sweeps the ``new_member_roles`` table for expired assignments
and removes the Discord role.  Also listens for manual role removals so the
assignment record is marked canceled (not re-applied).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands, tasks

from services.new_member_role_service import (
    get_active_assignment,
    mark_removed,
    process_expired_roles,
)
from utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    import discord

# How often (in minutes) to sweep for expired assignments
EXPIRY_CHECK_INTERVAL_MINUTES = 5


class NewMemberRoleWorker(commands.Cog):
    """Background loop + listener for the new-member role lifecycle."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Start the expiry loop when the cog is loaded."""
        self._expiry_loop.start()

    async def cog_unload(self) -> None:
        """Cancel the expiry loop when the cog is unloaded."""
        self._expiry_loop.cancel()

    # ------------------------------------------------------------------
    # Expiry sweep loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=EXPIRY_CHECK_INTERVAL_MINUTES)
    async def _expiry_loop(self) -> None:
        """Remove new-member roles that have passed their expiry timestamp."""
        try:
            count = await process_expired_roles(self.bot)
            if count:
                logger.info("Processed %d expired new-member role(s)", count)
        except Exception:
            logger.exception("Error in new-member role expiry loop")

    @_expiry_loop.before_loop
    async def _before_expiry_loop(self) -> None:
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Manual removal detection
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """Detect when the new-member role is removed by staff/admin."""
        # Quick exit: role sets identical
        if {r.id for r in before.roles} == {r.id for r in after.roles}:
            return

        removed_roles = {r.id for r in before.roles} - {r.id for r in after.roles}
        if not removed_roles:
            return

        guild_id = after.guild.id
        user_id = after.id

        # Check if any removed role matches an active new-member assignment
        try:
            assignment = await get_active_assignment(guild_id, user_id)
        except Exception:
            logger.exception(
                "Failed to check new-member assignment for user %s in guild %s",
                user_id,
                guild_id,
            )
            return

        if assignment is None:
            return

        assigned_role_id = assignment[0]
        if assigned_role_id in removed_roles:
            logger.info(
                "New-member role %s manually removed from user %s in guild %s",
                assigned_role_id,
                user_id,
                guild_id,
            )
            try:
                await mark_removed(guild_id, user_id, reason="manual")
            except Exception:
                logger.exception(
                    "Failed to mark new-member role as manually removed for user %s in guild %s",
                    user_id,
                    guild_id,
                )


async def setup(bot: commands.Bot) -> None:
    """Load the NewMemberRoleWorker cog."""
    await bot.add_cog(NewMemberRoleWorker(bot))
