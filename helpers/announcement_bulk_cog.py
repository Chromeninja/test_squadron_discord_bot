"""
BulkAnnouncer Cog — queue-driven daily announcement dispatcher.

Extracted from helpers/announcement.py to keep file sizes manageable.
All imports of BulkAnnouncer should use helpers.announcement for backward compatibility.
"""

from __future__ import annotations

import datetime
import time

import discord  # type: ignore[import-not-found]
from discord.ext import commands, tasks  # type: ignore[import-not-found]

from helpers.bot_utils import get_guild_org_sid
from helpers.constants import DEFAULT_ORG_SID
from helpers.daily_activity_tracker import DailyActivityTracker
from helpers.leadership_log import resolve_leadership_channel
from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)


class BulkAnnouncer(commands.Cog):
    """
    Queue-driven announcer:
      • Enqueues events via enqueue_verification_event(...) when roles change.
      • Flushes once per day at configured UTC time.
      • Also flushes whenever pending >= threshold (checked once per minute).
      • Batches by max mentions and character headroom to avoid 2000 char limit.
      • Announces 3 sections: joined_main, joined_affiliate, promoted_to_main.
      • On flush, dedupes to the latest event per user and then DELETES pending rows
        for those users (keeping the table lean: only not-yet-announced events).
    """

    def __init__(self, bot):
        self.bot = bot

        # Initialize with defaults; actual config loaded in before_daily/before_watch
        self.hour_utc: int = 18
        self.minute_utc: int = 0
        self.threshold: int = 50
        self.max_mentions_per_message: int = 50
        self.max_chars_per_message: int = 1800
        self._config_loaded = False

        # Start tasks (config will be loaded before first execution)
        self.daily_flush.start()
        self.threshold_watch.start()

    async def _load_config(self):
        """Load configuration from config service on first run."""
        if self._config_loaded:
            return

        def _to_int(value, default: int) -> int:
            """Safely coerce to int with a fallback default."""
            try:
                return int(value)
            except Exception:
                return default

        try:
            config_service = self.bot.services.config

            # Get bulk announcement settings (global) with defensive coercion
            self.hour_utc = _to_int(
                await config_service.get_global_setting(
                    "bulk_announcement.hour_utc", 18
                ),
                18,
            )
            self.minute_utc = _to_int(
                await config_service.get_global_setting(
                    "bulk_announcement.minute_utc", 0
                ),
                0,
            )
            self.threshold = _to_int(
                await config_service.get_global_setting(
                    "bulk_announcement.threshold", 50
                ),
                50,
            )
            self.max_mentions_per_message = _to_int(
                await config_service.get_global_setting(
                    "bulk_announcement.max_mentions_per_message", 50
                ),
                50,
            )
            self.max_chars_per_message = _to_int(
                await config_service.get_global_setting(
                    "bulk_announcement.max_chars_per_message", 1800
                ),
                1800,
            )

            # Validate & clamp
            if not (0 <= self.hour_utc < 24):
                logger.warning("Invalid hour_utc in config; using 18")
                self.hour_utc = 18
            if not (0 <= self.minute_utc < 60):
                logger.warning("Invalid minute_utc in config; using 0")
                self.minute_utc = 0
            self.max_mentions_per_message = max(self.max_mentions_per_message, 5)
            self.max_chars_per_message = min(self.max_chars_per_message, 1950)

            # Update daily timer with loaded config
            self.daily_flush.change_interval(
                time=datetime.time(
                    hour=self.hour_utc,
                    minute=self.minute_utc,
                    tzinfo=datetime.UTC,
                )
            )

            self._config_loaded = True

        except Exception as e:
            logger.exception(f"Failed to load BulkAnnouncer config: {e}")
            # Leave _config_loaded as False so a subsequent attempt can retry

    async def cog_unload(self) -> None:
        self.daily_flush.cancel()
        self.threshold_watch.cancel()

    # ---------- Public helpers ----------

    async def flush_pending(self) -> tuple[bool, list[int]]:
        """
        Flush all pending queued events grouped by guild.
        For each guild:
          • Fetch guild's organization SID and name
          • Post announcements to that guild's public_announcement_channel
          • Use SID in headers, full name in footers

        Returns:
            (sent_any, missing_channel_guilds)
                sent_any: True if at least one announcement was sent
                missing_channel_guilds: guild ids skipped due to missing public announcement channel
        """
        rows = await BaseRepository.fetch_all(
            "SELECT id, user_id, guild_id, event_type, created_at FROM announcement_events "
            "WHERE announced_at IS NULL AND guild_id IS NOT NULL "
            "ORDER BY guild_id ASC, created_at ASC"
        )

        if not rows:
            logger.info("BulkAnnouncer: no pending announcements to flush.")
            return False, []

        # Group events by guild_id
        events_by_guild: dict[int, list[tuple]] = {}
        for row in rows:
            ev_id, user_id, guild_id, event_type, created_at = row
            if guild_id not in events_by_guild:
                events_by_guild[guild_id] = []
            events_by_guild[guild_id].append((ev_id, user_id, event_type, created_at))

        sent_any = False
        announced_ids: list[int] = []
        missing_channel_guilds: list[int] = []

        # Process each guild separately
        for guild_id, guild_events in events_by_guild.items():
            try:
                # Get guild object
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    logger.warning(
                        f"BulkAnnouncer: guild {guild_id} not found, skipping {len(guild_events)} events"
                    )
                    continue

                # Fetch guild's organization settings
                org_sid = await get_guild_org_sid(self.bot, guild_id, default="ORG")
                org_name = None
                if hasattr(self.bot, "services") and self.bot.services.guild_config:
                    try:
                        org_name = await self.bot.services.guild_config.get_setting(
                            guild_id, "organization.name", default=None
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch org name for guild {guild_id}: {e}"
                        )

                # Fallback to DEFAULT_ORG_SID if no settings
                if not org_sid:
                    org_sid = DEFAULT_ORG_SID
                if not org_name:
                    org_name = "Organization"

                # Get public announcement channel for this guild
                channel = None
                if hasattr(self.bot, "services") and self.bot.services.guild_config:
                    try:
                        channel = await self.bot.services.guild_config.get_channel(
                            guild_id, "public_announcement_channel_id", guild
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch announcement channel for guild {guild_id}: {e}"
                        )

                if not channel:
                    logger.warning(
                        f"BulkAnnouncer: public_announcement_channel_id not configured for guild {guild_id}, skipping"
                    )
                    missing_channel_guilds.append(guild_id)
                    continue

                # Deduplicate: keep only latest event per user in this guild
                latest_by_user: dict[
                    int, tuple
                ] = {}  # user_id -> (id, event_type, created_at)
                for ev_id, user_id, event_type, created_at in guild_events:
                    prev = latest_by_user.get(user_id)
                    if (prev is None) or (created_at >= prev[2]):
                        latest_by_user[user_id] = (ev_id, event_type, created_at)

                # Group by event type
                events_by_type: dict[str, list[tuple[int, int]]] = {
                    "joined_main": [],
                    "joined_affiliate": [],
                    "promoted_to_main": [],
                }
                for user_id, (ev_id, event_type, _) in latest_by_user.items():
                    if event_type in events_by_type:
                        events_by_type[event_type].append((ev_id, user_id))

                allowed = discord.AllowedMentions(
                    users=True, roles=False, everyone=False
                )

                # Define announcement sections with dynamic org SID/name (org-agnostic)
                sections = [
                    (
                        "joined_main",
                        f"🍻 **New {org_sid} Main reporting in!**",
                        f"Welcome to {org_name}!",
                    ),
                    (
                        "joined_affiliate",
                        f"🤝 **New {org_sid} Affiliates**",
                        f"Welcome aboard! Next up, consider setting {org_sid} as your **Main Org** to fully join.",
                    ),
                    (
                        "promoted_to_main",
                        f"⬆️ **Promotion from {org_sid} Affiliate → {org_sid} Main**",
                        f"🫡 Welcome fully to {org_name}!",
                    ),
                ]

                # Send announcements for each section
                for key, header, footer in sections:
                    items = events_by_type.get(key, [])
                    if not items:
                        continue

                    # Build (id, mention) list
                    id_mention_pairs: list[tuple[int, str]] = []
                    user_ids_in_section: list[int] = []
                    for ev_id, uid in items:
                        m = guild.get_member(uid)
                        mention = m.mention if m else f"<@{uid}>"
                        id_mention_pairs.append((ev_id, mention))
                        user_ids_in_section.append(uid)

                    if not id_mention_pairs:
                        continue

                    # Send batched messages
                    for batch_ids, batch_mentions in self._build_batches(
                        id_mention_pairs,
                        header=header,
                        footer=footer,
                        max_mentions=self.max_mentions_per_message,
                        max_chars=self.max_chars_per_message,
                    ):
                        content = self._compose_message(header, batch_mentions, footer)
                        try:
                            await channel.send(content, allowed_mentions=allowed)
                            sent_any = True
                            announced_ids.extend(batch_ids)
                        except Exception as e:
                            logger.warning(
                                f"BulkAnnouncer: failed sending batch for {key} in guild {guild_id}: {e}"
                            )

            except Exception as e:
                logger.exception(
                    f"BulkAnnouncer: error processing guild {guild_id}: {e}"
                )
                continue

        # Mark all announced events with timestamp (preserve history, prevent re-sending)
        if announced_ids:
            try:
                async with BaseRepository.transaction() as db:
                    now = int(time.time())
                    CHUNK = 500
                    for i in range(0, len(announced_ids), CHUNK):
                        chunk = announced_ids[i : i + CHUNK]
                        qmarks = ",".join("?" for _ in chunk)
                        await db.execute(
                            f"UPDATE announcement_events SET announced_at = ? WHERE id IN ({qmarks})",
                            (now, *chunk),
                        )
                logger.info(
                    f"BulkAnnouncer: marked {len(announced_ids)} events as announced"
                )
            except Exception as e:
                logger.warning(f"BulkAnnouncer: failed to mark announced events: {e}")

        return sent_any, missing_channel_guilds

        # ---------- Internal helpers ----------

    def _compose_message(self, header: str, mentions: list[str], footer: str) -> str:
        body = ",".join(mentions)
        parts = [header, body]
        if footer:
            parts.extend(["", footer])
        return "\n".join(parts)

    def _build_batches(
        self,
        id_mention_pairs: list[tuple[int, str]],
        header: str,
        footer: str,
        max_mentions: int,
        max_chars: int,
    ) -> list[tuple[list[int], list[str]]]:
        """
        Produces batches where each batch:
          • has <= max_mentions mentions
          • and the full message length (header + mentions + footer) stays under max_chars
        Returns list of (ids, mentions) for each batch.

        Optimized to O(n) by pre-calculating header/footer length
        and tracking running total.
        """
        batches: list[tuple[list[int], list[str]]] = []

        current_ids: list[int] = []
        current_mentions: list[str] = []

        # Pre-calculate fixed overhead (header + footer + newlines)
        # Format is: "header\nbody\n\nfooter" if footer else "header\nbody"
        base_length = len(header) + 1  # header + newline
        if footer:
            base_length += 2 + len(footer)  # 2 newlines + footer

        # Track current body length (mentions + commas)
        current_body_length = 0

        for ev_id, mention in id_mention_pairs:
            mention_len = len(mention)
            # Add 1 for comma separator (except for first mention)
            addition = mention_len + (1 if current_mentions else 0)

            # Enforce mention cap
            if len(current_mentions) >= max_mentions:
                if current_mentions:
                    batches.append((current_ids, current_mentions))
                current_ids, current_mentions = [], []
                current_body_length = 0

            # Enforce char cap before adding
            if current_mentions:
                prospective_total = base_length + current_body_length + addition
                if prospective_total > max_chars:
                    batches.append((current_ids, current_mentions))
                    current_ids, current_mentions = [], []
                    current_body_length = 0
                    addition = mention_len  # No comma for first in new batch

            # Safe to add
            current_ids.append(ev_id)
            current_mentions.append(mention)
            current_body_length += addition

        # Final batch
        if current_mentions:
            batches.append((current_ids, current_mentions))

        return batches

    async def _count_pending(self) -> int:
        count = await BaseRepository.fetch_value(
            "SELECT COUNT(1) FROM announcement_events WHERE announced_at IS NULL",
            default=0,
        )
        return int(count)

    # ---------- Daily leadership summary ----------

    async def _post_daily_leadership_summary(self) -> None:
        """Post a once-daily summary to each guild's leadership channel.

        Includes total checked, changed, first-time manual, recheck, and
        admin-triggered counts.  Counters are always reset after the
        snapshot regardless of send outcome (reset-on-flush policy).
        """
        tracker = DailyActivityTracker.get()
        snapshot = tracker.snapshot_and_reset()

        if not snapshot:
            logger.debug("DailyLeadershipSummary: nothing to report.")
            return

        for guild_id, totals in snapshot.items():
            checked = totals.get("checked", 0)
            changed = totals.get("changed", 0)
            first_time = totals.get("first_time_manual", 0)
            recheck = totals.get("recheck", 0)
            admin = totals.get("admin", 0)

            if checked == 0:
                continue

            channel = await resolve_leadership_channel(self.bot, guild_id)
            if not channel:
                logger.debug(
                    "DailyLeadershipSummary: no leadership channel for guild %s",
                    guild_id,
                )
                continue

            lines = [
                "📊 **Daily Verification Summary**",
                f"• Checked: **{checked}**",
                f"• Changed: **{changed}**",
                f"• First-time verifications: **{first_time}**",
                f"• Rechecks: **{recheck}**",
                f"• Admin-triggered: **{admin}**",
            ]
            content = "\n".join(lines)

            try:
                await channel.send(content)
                logger.info(
                    "DailyLeadershipSummary sent for guild %s: checked=%d changed=%d",
                    guild_id,
                    checked,
                    changed,
                )
            except Exception as e:
                logger.warning(
                    "DailyLeadershipSummary: failed for guild %s: %s",
                    guild_id,
                    e,
                )

            # ---------- Tasks ----------

    @tasks.loop()
    async def daily_flush(self):
        """
        Fires at the configured UTC time daily, flushing all pending events.
        Also posts a daily leadership summary with verification activity totals.
        """
        await self.flush_pending()
        await self._post_daily_leadership_summary()

    @daily_flush.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()
        await self._load_config()

    @tasks.loop(minutes=1.0)
    async def threshold_watch(self):
        """
        Lightweight poll that triggers an immediate flush when the queue grows large.
        This reduces spam while ensuring big bursts get announced promptly.
        """
        try:
            pending = await self._count_pending()
            if pending >= self.threshold:
                logger.info(
                    f"BulkAnnouncer: threshold reached "
                    f"({pending} >= {self.threshold}); flushing."
                )
                await self.flush_pending()
        except Exception as e:
            logger.warning(f"BulkAnnouncer threshold watch error: {e}")

    @threshold_watch.before_loop
    async def before_watch(self):
        await self.bot.wait_until_ready()
        await self._load_config()
