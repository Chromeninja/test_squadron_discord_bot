"""
Metrics Events Cog

Listens for Discord events (messages, voice state changes, presence updates)
and delegates to MetricsService for recording. Separate from the voice cog
to keep metrics concerns decoupled from JTC channel management.
"""

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from utils.logging import get_logger

if TYPE_CHECKING:
    from services.metrics_service import MetricsService

logger = get_logger(__name__)


class MetricsEvents(commands.Cog):
    """Captures Discord events for metrics collection."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def metrics_service(self) -> "MetricsService":
        """Get the metrics service from the bot's service container."""
        if not hasattr(self.bot, "services") or self.bot.services is None:  # type: ignore[attr-defined]
            raise RuntimeError("Bot services not initialized")
        return self.bot.services.metrics  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Message tracking
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Count guild messages (ignore bots and DMs)."""
        if message.author.bot:
            return
        if not message.guild:
            return

        try:
            guild_id = message.guild.id
            channel_id = getattr(message.channel, "id", None)
            excluded_channel_ids = await self.metrics_service.get_excluded_channel_ids(
                guild_id
            )
            if channel_id in excluded_channel_ids:
                return

            self.metrics_service.record_message(
                guild_id,
                message.author.id,
                channel_id=channel_id,
            )
        except Exception:
            logger.debug("Failed to record message metric", exc_info=True)

    # ------------------------------------------------------------------
    # Voice tracking
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Track voice channel join/leave/move for duration metrics.

        A user is considered *eligible* for voice tracking when they are in a
        non-excluded channel **and** are not self-muted or self-deafened.
        Transitions between eligible/ineligible states drive session open/close.

        AI Notes:
            Self-mute and self-deaf are the only disqualifiers; server-mute,
            server-deaf, and stage-suppress are intentionally ignored so that
            moderator actions do not penalise a user's activity metrics.
        """
        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id

        try:
            excluded_channel_ids = await self.metrics_service.get_excluded_channel_ids(
                guild_id
            )

            was_eligible = _is_voice_eligible(before, excluded_channel_ids)
            now_eligible = _is_voice_eligible(after, excluded_channel_ids)

            if was_eligible and not now_eligible:
                # Lost eligibility (left channel, muted, deafened, moved to excluded)
                await self.metrics_service.record_voice_leave(guild_id, user_id)
            elif not was_eligible and now_eligible:
                # Gained eligibility (joined channel, unmuted, undeafened)
                await self.metrics_service.record_voice_join(
                    guild_id, user_id, after.channel.id  # type: ignore[union-attr]
                )
            elif was_eligible and now_eligible:
                # Still eligible — check for channel move
                assert before.channel is not None  # guarded by was_eligible  # noqa: S101
                assert after.channel is not None  # guarded by now_eligible  # noqa: S101
                if before.channel.id != after.channel.id:
                    await self.metrics_service.record_voice_leave(guild_id, user_id)
                    await self.metrics_service.record_voice_join(
                        guild_id, user_id, after.channel.id
                    )
            # else: was ineligible → still ineligible → no-op
        except Exception:
            logger.debug(
                "Failed to record voice metric for %s", member, exc_info=True
            )

    # ------------------------------------------------------------------
    # Game / presence tracking
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_presence_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """Detect game start/stop from presence changes."""
        if after.bot:
            return

        guild_id = after.guild.id
        user_id = after.id

        try:
            excluded_channel_ids = await self.metrics_service.get_excluded_channel_ids(
                guild_id
            )
            voice_state = getattr(after, "voice", None)
            current_voice_channel_id = (
                voice_state.channel.id
                if voice_state is not None and voice_state.channel is not None
                else None
            )
            if current_voice_channel_id in excluded_channel_ids:
                await self.metrics_service.record_game_stop(guild_id, user_id)
                return

            before_game = _get_playing_game(before)
            after_game = _get_playing_game(after)

            if before_game == after_game:
                return  # No change

            if before_game and not after_game:
                # Stopped playing
                await self.metrics_service.record_game_stop(guild_id, user_id)
            elif not before_game and after_game:
                # Started playing
                await self.metrics_service.record_game_start(
                    guild_id, user_id, after_game
                )
            else:
                # Switched games
                await self.metrics_service.record_game_stop(guild_id, user_id)
                if after_game:
                    await self.metrics_service.record_game_start(
                        guild_id, user_id, after_game
                    )
        except Exception:
            logger.debug(
                "Failed to record presence metric for %s", after, exc_info=True
            )

    # ------------------------------------------------------------------
    # Backfill on ready
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Backfill voice and game sessions from current state on bot startup."""
        try:
            await self.metrics_service.backfill_voice_state(self.bot)
            await self.metrics_service.backfill_game_state(self.bot)
        except Exception:
            logger.exception("Failed to backfill metrics on ready")


def _is_voice_eligible(
    state: discord.VoiceState, excluded_channel_ids: set[int]
) -> bool:
    """Return True when the voice state should count as active voice time.

    Eligibility requires:
    - Connected to a voice channel that is not excluded.
    - Not self-muted.
    - Not self-deafened.
    """
    if state.channel is None:
        return False
    if state.channel.id in excluded_channel_ids:
        return False
    if state.self_mute or state.self_deaf:
        return False
    return True


def _get_playing_game(member: discord.Member) -> str | None:
    """Extract the name of the game a member is currently playing, or None."""
    for activity in member.activities:
        if activity.type == discord.ActivityType.playing and hasattr(activity, "name"):
            return activity.name
    return None


async def setup(bot: commands.Bot) -> None:
    """Set up the Metrics Events cog."""
    await bot.add_cog(MetricsEvents(bot))
