"""Periodic background tasks and alert helpers for MyBot."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

import discord
from discord.ext import commands

from helpers.token_manager import cleanup_tokens
from services.log_cleanup import LogCleanupService
from utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from services.service_container import ServiceContainer

logger = get_logger(__name__)


class BotTaskContext(Protocol):
    """Structural type for bot background task helpers."""

    config: dict
    services: ServiceContainer

    @property
    def guilds(self) -> Sequence[discord.Guild]:
        ...

    async def wait_until_ready(self) -> None:
        ...

    def is_closed(self) -> bool:
        ...


async def token_cleanup_task(bot: BotTaskContext) -> None:
    """Periodically cleans up expired tokens."""
    while not bot.is_closed():
        await asyncio.sleep(300)  # Run every 5 minutes
        cleanup_tokens()
        logger.debug("Expired tokens cleaned up.")


async def attempts_cleanup_task(bot: BotTaskContext) -> None:
    """Periodically cleans up expired rate-limiting data."""
    from helpers.rate_limiter import cleanup_attempts

    while not bot.is_closed():
        await asyncio.sleep(300)  # Run every 5 minutes
        await cleanup_attempts()


async def log_cleanup_task(bot: BotTaskContext) -> None:
    """Daily cleanup of old logs based on retention policies.

    Runs at the configured cleanup_hour_utc time each day.
    """
    await bot.wait_until_ready()

    cleanup_cfg = getattr(bot, "config", {}) or {}
    cleanup_hour_utc = cleanup_cfg.get("log_retention", {}).get("cleanup_hour_utc", 3)

    while not bot.is_closed():
        try:
            now = datetime.now(UTC)
            target_time = now.replace(hour=cleanup_hour_utc, minute=0, second=0, microsecond=0)

            if now >= target_time:
                target_time += timedelta(days=1)

            seconds_until_cleanup = (target_time - now).total_seconds()

            logger.info(
                f"Log cleanup scheduled for {target_time.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                f"({seconds_until_cleanup / 3600:.1f} hours from now)"
            )

            await asyncio.sleep(seconds_until_cleanup)

            logger.info("Starting scheduled log cleanup")
            cleanup_service = LogCleanupService(cleanup_cfg)
            summary = await cleanup_service.cleanup_all()

            logger.info(
                f"Log cleanup completed: {summary}",
                extra={"cleanup_summary": summary},
            )

        except asyncio.CancelledError:
            logger.info("Log cleanup task cancelled")
            break
        except Exception as e:
            logger.exception("Error in log cleanup task", exc_info=e)
            await asyncio.sleep(3600)


async def alert_prefix_warnings(bot: BotTaskContext) -> None:
    """Send admin channel alert if there were prefix normalization warnings."""
    from bot import PREFIX_WARNINGS

    if not PREFIX_WARNINGS:
        return

    await asyncio.gather(
        *(send_prefix_warning_for_guild(bot, guild) for guild in bot.guilds)
    )


async def send_prefix_warning_for_guild(
    bot: BotTaskContext,
    guild: discord.Guild,
) -> None:
    """Send a prefix warning alert for a single guild if configured."""
    from bot import get_prefix, get_prefix_warnings

    try:
        bot_spam_id = await bot.services.config.get_guild_setting(
            guild.id, "channels.bot_spam_channel_id"
        )
        if not bot_spam_id:
            return

        channel = guild.get_channel(int(bot_spam_id))
        if not channel or not isinstance(channel, discord.abc.Messageable):
            return

        embed = discord.Embed(
            title="⚠️ Prefix Configuration Warning",
            description="The command prefix configuration had issues during startup.",
            color=discord.Color.orange(),
        )
        current_prefix = get_prefix()
        warnings = get_prefix_warnings()

        embed.add_field(
            name="Warnings",
            value="\n".join(f"• {w}" for w in warnings[:10]),
            inline=False,
        )
        embed.add_field(
            name="Current Mode",
            value="Mention-only"
            if commands.when_mentioned == current_prefix
            else f"Prefixes: {current_prefix}",
            inline=False,
        )
        embed.set_footer(text="Check config.yaml prefix settings")

        await channel.send(embed=embed)
        logger.info(f"Sent prefix warning alert to guild {guild.name}")

    except Exception as e:
        logger.warning(f"Failed to send prefix warning to guild {guild.name}: {e}")
