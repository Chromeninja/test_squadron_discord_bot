"""Staff-level /check user command providing detailed verification info."""

from __future__ import annotations

import json
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from helpers.decorators import require_permission_level
from helpers.permissions_helper import PermissionLevel
from services.db.database import Database, derive_membership_status
from utils.logging import get_logger

logger = get_logger(__name__)


class CheckUserCommands(app_commands.Group):
    """Slash command group for staff-facing user lookups."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(name="check", description="Lookup commands for staff")
        self.bot = bot

    @app_commands.command(
        name="user",
        description="Show verification details for a user",
    )
    @app_commands.describe(member="Member to inspect")
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.STAFF)
    async def user_command(  # type: ignore[override]
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """Display rich verification data for the requested user."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            verification_row = await self._fetch_verification_row(member.id)
            target_sid = await self._get_guild_org_sid(interaction.guild.id)
            embed = self._build_user_embed(
                requester=interaction.user,
                member=member,
                verification_row=verification_row,
                target_sid=target_sid,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to run /check user", exc_info=exc)
            await interaction.followup.send(
                "❌ Unable to fetch user details right now. Please try again soon.",
                ephemeral=True,
            )

    async def _fetch_verification_row(self, user_id: int) -> tuple[Any, ...] | None:
        """Fetch verification data (handle, timestamps, org lists)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT rsi_handle, last_updated, main_orgs, affiliate_orgs
                FROM verification
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            return tuple(row) if row else None

    async def _get_guild_org_sid(self, guild_id: int) -> str:
        """Return the guild's configured org SID (default TEST)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT json_extract(value, '$')
                FROM guild_settings
                WHERE guild_id = ? AND key = 'organization.sid'
                """,
                (guild_id,),
            )
            row = await cursor.fetchone()
        if row and row[0]:
            return str(row[0]).strip('"').upper()
        return "TEST"

    def _build_user_embed(
        self,
        requester: discord.User | discord.Member,
        member: discord.Member,
        verification_row: tuple | None,
        target_sid: str,
    ) -> discord.Embed:
        """Compose an embed mirroring the clean layout from channel settings."""
        embed = discord.Embed(
            title=f"User Check • {member.display_name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        embed.add_field(
            name="Discord",
            value=f"{member.mention}\n`{member.name}` (ID: `{member.id}`)",
            inline=False,
        )

        joined_val = "Unknown"
        if member.joined_at:
            joined_ts = int(member.joined_at.timestamp())
            joined_val = f"<t:{joined_ts}:F>\n<t:{joined_ts}:R>"

        verify_status = "❌ Not in database"
        rsi_handle = "—"
        last_verified = "—"
        main_org_lines: list[str] = []
        affiliate_org_lines: list[str] = []
        main_org_value = "—"
        affiliate_org_value = "—"

        if verification_row:
            rsi_handle, last_updated, main_orgs_json, affiliate_orgs_json = (
                verification_row
            )

            main_orgs = self._parse_org_list(main_orgs_json)
            affiliate_orgs = self._parse_org_list(affiliate_orgs_json)
            membership_status = derive_membership_status(
                main_orgs, affiliate_orgs, target_sid
            )

            status_label, status_color = self._status_badge(membership_status)
            verify_status = f"{status_color} {status_label}"

            if rsi_handle:
                rsi_url = f"https://robertsspaceindustries.com/citizens/{rsi_handle}"
                rsi_handle = f"[{rsi_handle}]({rsi_url})"

            if last_updated:
                last_verified = f"<t:{last_updated}:F>\n<t:{last_updated}:R>"

            main_org_lines = self._build_org_links(main_orgs)
            affiliate_org_lines = self._build_org_links(affiliate_orgs)
            if main_org_lines:
                main_org_value = main_org_lines[0]  # Only one main org allowed
            if affiliate_org_lines:
                affiliate_org_value = "\n".join(affiliate_org_lines)

        # First row (table style): Lock/UserLimit analogue
        embed.add_field(name="Verification Status", value=verify_status, inline=True)
        embed.add_field(name="RSI Handle", value=rsi_handle, inline=True)

        # Second row: Last verified vs Joined date
        embed.add_field(name="Last Verified", value=last_verified, inline=True)
        embed.add_field(name="Joined Server", value=joined_val, inline=True)

        # Org sections displayed side-by-side like settings layout
        embed.add_field(name="Main Org", value=main_org_value, inline=True)
        embed.add_field(name="Affiliate Orgs", value=affiliate_org_value, inline=True)

        embed.set_footer(text=f"Requested by {requester.display_name}")
        return embed

    @staticmethod
    def _parse_org_list(raw_json: str | None) -> list[str]:
        try:
            return json.loads(raw_json) if raw_json else []
        except Exception:
            return []

    @staticmethod
    def _build_org_links(org_sids: list[str]) -> list[str]:
        links = []
        for sid in org_sids:
            sid_clean = sid.upper()
            url = f"https://robertsspaceindustries.com/orgs/{sid_clean}"
            links.append(f"[{sid_clean}]({url})")
        return links

    @staticmethod
    def _status_badge(status: str | None) -> tuple[str, str]:
        badge_map = {
            "main": ("Verified – Main", "✅"),
            "affiliate": ("Verified – Affiliate", "🟦"),
            "non_member": ("Verified – Non-Member", "⚠️"),
            "unknown": ("Not Verified", "❌"),
        }
        label, emoji = badge_map.get(status or "unknown", ("Unknown", "❔"))
        return label, emoji


class CheckUserCog(commands.Cog):
    """Cog wrapper that registers the /check command group."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.group = CheckUserCommands(bot)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.group)
        logger.info("Loaded CheckUserCommands")

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.group.name)
        logger.info("Unloaded CheckUserCommands")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CheckUserCog(bot))
