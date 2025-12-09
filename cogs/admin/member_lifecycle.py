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
from services.db.database import Database
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

        # Check if user has existing verification
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT rsi_handle, main_orgs, affiliate_orgs FROM verification WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

        if not row:
            # New user, no verification yet
            logger.debug(f"New member {user_id} joined {guild.name}, no existing verification")
            return

        # User has existing verification - restore roles
        rsi_handle, main_orgs_json, affiliate_orgs_json = row

        logger.info(
            f"Rejoining member {user_id} has existing verification ({rsi_handle}). "
            f"Restoring roles in guild {guild.name}"
        )

        # Import here to avoid circular dependency
        import json

        from helpers.role_helper import assign_roles
        from services.db.database import derive_membership_status

        try:
            # Parse org lists
            main_orgs = json.loads(main_orgs_json) if main_orgs_json else []
            affiliate_orgs = json.loads(affiliate_orgs_json) if affiliate_orgs_json else []

            # Get guild's org SID to determine status
            org_sid = "TEST"  # Default
            if hasattr(self.bot, "services") and self.bot.services:  # type: ignore
                try:
                    org_sid_config = await self.bot.services.config.get_guild_setting(  # type: ignore
                        guild.id, "organization.sid", default="TEST"
                    )
                    org_sid = org_sid_config.strip().upper() if org_sid_config else "TEST"
                except Exception as e:
                    logger.warning(f"Failed to get org SID for guild {guild.id}: {e}")

            # Derive membership status for this guild
            status = derive_membership_status(main_orgs, affiliate_orgs, org_sid)

            # Convert status to verify_value for assign_roles
            verify_value_map = {"main": 1, "affiliate": 2, "non_member": 0}
            verify_value = verify_value_map.get(status, 0)

            # Restore roles
            await assign_roles(
                member,
                verify_value,
                rsi_handle,
                self.bot,
                None,  # community_moniker - we don't have it readily available
                main_orgs,
                affiliate_orgs,
            )

            logger.info(
                f"Successfully restored {status} roles for rejoining member {user_id} "
                f"in guild {guild.name}"
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
                    f"Member rejoined guild {guild.name} with existing verification "
                    f"(RSI handle: {rsi_handle}). Restored {status} roles automatically."
                ),
            )

            try:
                await post_if_changed(self.bot, changeset)
            except Exception as e:
                logger.warning(f"Failed to post rejoin leadership log: {e}")

        except Exception as e:
            logger.exception(
                f"Failed to restore roles for rejoining member {user_id} in guild {guild.name}: {e}"
            )


async def setup(bot: commands.Bot) -> None:
    """Load the MemberLifecycle cog."""
    await bot.add_cog(MemberLifecycle(bot))
