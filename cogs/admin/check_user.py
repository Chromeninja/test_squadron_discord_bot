"""Staff-level /check user command providing detailed verification info."""

from __future__ import annotations

import json
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from helpers.decorators import require_permission_level
from helpers.permissions_helper import PermissionLevel
from services.db.database import derive_membership_status
from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)


class CheckUserCommands(app_commands.Group):
    """Slash command group for staff-facing user lookups."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(name="check", description="Lookup commands for staff")
        self.bot = bot

    # Tier display configuration
    _TIER_EMOJI: dict[str, str] = {
        "hardcore": "🔴",
        "regular": "🟠",
        "casual": "🔵",
        "reserve": "⚪",
        "inactive": "⬛",
    }

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
            activity_tiers = await self._fetch_activity_tiers(
                interaction.guild.id, member.id,
            )
            embed = self._build_user_embed(
                requester=interaction.user,
                member=member,
                verification_row=verification_row,
                target_sid=target_sid,
                activity_tiers=activity_tiers,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to run /check user", exc_info=exc)
            await interaction.followup.send(
                "❌ Unable to fetch user details right now. Please try again soon.",
                ephemeral=True,
            )

    async def _fetch_verification_row(self, user_id: int) -> tuple[Any, ...] | None:
        """Fetch verification data (handle, moniker, timestamps, org lists)."""
        row = await BaseRepository.fetch_one(
            """
            SELECT rsi_handle, community_moniker, last_updated, main_orgs, affiliate_orgs
            FROM verification WHERE user_id = ?
            """,
            (user_id,),
        )
        return tuple(row) if row else None

    async def _fetch_activity_tiers(
        self, guild_id: int, user_id: int,
    ) -> dict[str, str] | None:
        """Fetch per-dimension activity tiers from the metrics service.

        Returns a dict with keys ``combined_tier``, ``voice_tier``,
        ``chat_tier``, ``game_tier`` or ``None`` when the metrics
        service is unavailable.

        AI Notes:
            Graceful — never raises.  If the metrics service is missing
            or the lookup fails the embed simply omits the section.
        """
        try:
            metrics_svc = getattr(
                getattr(self.bot, "services", None), "metrics", None,
            )
            if metrics_svc is None:
                return None

            buckets: dict[int, dict[str, Any]] = (
                await metrics_svc.get_member_activity_buckets(
                    guild_id=guild_id,
                    user_ids=[user_id],
                    lookback_days=30,
                )
            )
            user_data = buckets.get(user_id)
            if not user_data:
                # User has zero qualifying activity — all inactive.
                return {
                    "combined_tier": "inactive",
                    "voice_tier": "inactive",
                    "chat_tier": "inactive",
                    "game_tier": "inactive",
                }
            return {
                "combined_tier": user_data.get("combined_tier", "inactive"),
                "voice_tier": user_data.get("voice_tier", "inactive"),
                "chat_tier": user_data.get("chat_tier", "inactive"),
                "game_tier": user_data.get("game_tier", "inactive"),
            }
        except Exception as exc:
            logger.warning(
                "Could not fetch activity tiers for user %s in guild %s: %s",
                user_id, guild_id, exc,
            )
            return None

    async def _get_guild_org_sid(self, guild_id: int) -> str:
        """Return the guild's configured org SID (default TEST)."""
        result = await BaseRepository.fetch_value(
            """
            SELECT json_extract(value, '$') FROM guild_settings
            WHERE guild_id = ? AND key = 'organization.sid'
            """,
            (guild_id,),
        )
        if result:
            return str(result).strip('"').upper()
        return "TEST"

    def _build_user_embed(
        self,
        requester: discord.User | discord.Member,
        member: discord.Member,
        verification_row: tuple | None,
        target_sid: str,
        activity_tiers: dict[str, str] | None = None,
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
            joined_val = f"<t:{joined_ts}:R>"

        verify_status = "❌ Not in database"
        rsi_handle = "—"
        community_moniker = "—"
        last_verified = "—"
        main_org_lines: list[str] = []
        affiliate_org_lines: list[str] = []
        main_org_value = "—"
        affiliate_org_value = "—"

        if verification_row:
            (
                rsi_handle,
                community_moniker,
                last_updated,
                main_orgs_json,
                affiliate_orgs_json,
            ) = verification_row

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

            if not community_moniker:
                community_moniker = "—"

            if last_updated:
                last_verified = f"<t:{last_updated}:R>"

            main_org_lines = self._build_org_links(main_orgs)
            affiliate_org_lines = self._build_org_links(affiliate_orgs)
            if main_org_lines:
                main_org_value = main_org_lines[0]  # Only one main org allowed
            if affiliate_org_lines:
                affiliate_org_value = "\n".join(affiliate_org_lines)

        # First row (table style): Lock/UserLimit analogue
        embed.add_field(name="Verification Status", value=verify_status, inline=True)
        embed.add_field(name="RSI Handle", value=rsi_handle, inline=True)
        embed.add_field(name="Community Moniker", value=community_moniker, inline=True)

        # Second row: Last verified vs Joined date
        embed.add_field(name="Last Verified", value=last_verified, inline=True)
        embed.add_field(name="Joined Server", value=joined_val, inline=True)

        # Org sections displayed side-by-side like settings layout
        embed.add_field(name="Main Org", value=main_org_value, inline=True)
        embed.add_field(name="Affiliate Orgs", value=affiliate_org_value, inline=True)

        # Activity levels (tiers) — omitted when metrics service unavailable
        if activity_tiers is not None:
            embed.add_field(
                name="Activity Levels (30d)",
                value=self._format_activity_tiers(activity_tiers),
                inline=False,
            )

        embed.set_footer(text=f"Requested by {requester.display_name}")
        return embed

    def _format_activity_tiers(self, tiers: dict[str, str]) -> str:
        """Format activity tiers into a compact embed-friendly string.

        Example output::

            ⚡ Combined: 🔴 Hardcore
            🎤 Voice: 🟠 Regular
            💬 Text: 🔵 Casual
            🎮 Gaming: ⬛ Inactive
        """
        lines: list[str] = []
        for dim_key, label, icon in (
            ("combined_tier", "Combined", "⚡"),
            ("voice_tier", "Voice", "🎤"),
            ("chat_tier", "Text", "💬"),
            ("game_tier", "Gaming", "🎮"),
        ):
            tier = tiers.get(dim_key, "inactive")
            emoji = self._TIER_EMOJI.get(tier, "⬛")
            lines.append(f"{icon} **{label}:** {emoji} {tier.capitalize()}")
        return "\n".join(lines)

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
