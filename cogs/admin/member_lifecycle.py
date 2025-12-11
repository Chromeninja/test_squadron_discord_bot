"""
Member Lifecycle Event Handlers

Handles on_member_remove and on_member_join events with multi-guild awareness.
Implements smart cleanup logic that only removes global verification when a user
has left ALL bot-managed guilds.
"""

import discord
from discord.ext import commands

from helpers.leadership_log import (
    ChangeSet,
    EventType,
    InitiatorKind,
    InitiatorSource,
    post_if_changed,
)
from helpers.task_queue import flush_tasks
from helpers.verification_logging import log_guild_sync
from services.db.database import Database
from services.guild_sync import apply_state_to_guild
from services.verification_scheduler import compute_next_retry, schedule_user_recheck
from services.verification_state import get_global_state
from utils.logging import get_logger

logger = get_logger(__name__)


class MemberLifecycle(commands.Cog):
    """
    Handles member join/leave events with multi-guild awareness.

    Key behaviors:
    - on_member_remove: Removes guild-specific data, but only removes global
      verification if the user has left ALL managed guilds.
    - on_member_join: Tracks membership and restores roles if user still has verification.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """
        Handle member leaving a guild with multi-guild cleanup logic.

        Process:
        1. Remove guild membership tracking for this guild
        2. Check if user is still in ANY other bot-managed guild
        3. If yes: Remove only guild-specific data, keep verification
        4. If no: Remove all data including global verification
        5. Log all actions to leadership log
        """
        guild = member.guild
        user_id = member.id

        logger.info(
            f"Member {member.display_name} ({user_id}) left guild {guild.name} ({guild.id})"
        )

        # Remove guild membership tracking for this specific guild
        await Database.remove_user_guild_membership(user_id, guild.id)

        # Check if user is still in any other bot-managed guild
        remaining_guilds = []
        for other_guild in self.bot.guilds:
            if other_guild.id == guild.id:
                continue  # Skip the guild they just left

            # Check if member is in this guild
            other_member = other_guild.get_member(user_id)
            if other_member:
                remaining_guilds.append(other_guild)

        if remaining_guilds:
            # User is still in other guilds - only remove guild-specific data
            deleted = await Database.cleanup_guild_specific_data(user_id, guild.id)

            guild_names = ", ".join([g.name for g in remaining_guilds])
            logger.info(
                f"User {user_id} left guild {guild.name} but is still active in "
                f"{len(remaining_guilds)} other guild(s): {guild_names}. "
                f"Removed guild-specific data only: {deleted}"
            )

            # Log to leadership log
            changeset = ChangeSet(
                user_id=user_id,
                event=EventType.AUTO_CHECK,  # System automated event
                initiator_kind=InitiatorKind.AUTO,
                initiator_name="System",
                initiator_source=InitiatorSource.SYSTEM,
                guild_id=guild.id,
                notes=(
                    f"Member left guild {guild.name}. Removed guild-specific data only. "
                    f"User is still active in {len(remaining_guilds)} other guild(s): {guild_names}. "
                    f"Global verification retained."
                ),
            )

            try:
                await post_if_changed(self.bot, changeset)
            except Exception as e:
                logger.warning(f"Failed to post guild-specific cleanup leadership log: {e}")

        else:
            # User is not in any other bot-managed guild - full cleanup
            deleted = await Database.cleanup_all_user_data(user_id)

            logger.info(
                f"User {user_id} left guild {guild.name} and is not in any other "
                f"managed guilds. Performed full cleanup: {deleted}"
            )

            # Log to leadership log
            changeset = ChangeSet(
                user_id=user_id,
                event=EventType.AUTO_CHECK,  # System automated event
                initiator_kind=InitiatorKind.AUTO,
                initiator_name="System",
                initiator_source=InitiatorSource.SYSTEM,
                guild_id=guild.id,
                notes=(
                    f"Member left guild {guild.name} and is not active in any other "
                    f"managed guilds. Full verification and all user data removed."
                ),
            )

            try:
                await post_if_changed(self.bot, changeset)
            except Exception as e:
                logger.warning(f"Failed to post full cleanup leadership log: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """
        Handle member joining/rejoining a guild.

        Process:
        1. Track guild membership
        2. Check if user has existing verification
        3. If yes: Restore appropriate roles
        4. Log rejoin events when appropriate
        """
        guild = member.guild
        user_id = member.id

        logger.info(
            f"Member {member.display_name} ({user_id}) joined guild {guild.name} ({guild.id})"
        )

        # Track guild membership
        await Database.track_user_guild_membership(user_id, guild.id)
        state = await get_global_state(user_id)
        if not state:
            logger.debug("Member %s joined %s with no stored verification", user_id, guild.name)
            return

        logger.info(
            "Rejoining member %s has stored verification (%s). Applying to guild %s",
            user_id,
            state.rsi_handle,
            guild.name,
        )

        try:
            res = await apply_state_to_guild(state, guild, self.bot)
            await flush_tasks()
            if res:
                await log_guild_sync(
                    res,
                    EventType.AUTO_CHECK,
                    self.bot,
                    initiator={
                        "user_id": user_id,
                        "kind": InitiatorKind.AUTO,
                        "source": InitiatorSource.SYSTEM,
                        "name": "System",
                        "notes": f"Member rejoined guild {guild.name}",
                    },
                )
                next_retry = compute_next_retry(state, config=getattr(self.bot, "config", {}))
                if next_retry:
                    await schedule_user_recheck(user_id, next_retry)
                logger.info(
                    "Applied stored verification (%s) to member %s in guild %s", state.status, user_id, guild.name
                )
        except Exception as e:
            logger.exception(
                "Failed to restore verification for member %s in guild %s: %s",
                user_id,
                guild.name,
                e,
            )


async def setup(bot: commands.Bot) -> None:
    """Load the MemberLifecycle cog."""
    await bot.add_cog(MemberLifecycle(bot))
