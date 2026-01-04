import contextlib
import datetime
import io
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from helpers.discord_api import channel_send_message
from services.db.repository import BaseRepository
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


# ----------------------------
# Leadership log
# ----------------------------


def canonicalize_status_for_display(status: str) -> str:
    """
    Convert internal status strings to canonical display format.

    Args:
        status: Internal status string (e.g., 'main', 'affiliate', 'non_member', 'unknown')

    Returns:
        Canonical display string: "Main", "Affiliate", or "Not a Member"
    """
    status_normalized = (status or "").lower().strip()

    if status_normalized == "main":
        return "Main"
    elif status_normalized == "affiliate":
        return "Affiliate"
    elif status_normalized in ("non_member", "unknown"):
        return "Not a Member"
    else:
        # Fallback for any unexpected status
        return "Not a Member"


def format_admin_recheck_message(
    admin_display_name: str, user_id: int, old_status: str, new_status: str
) -> tuple[str, bool]:
    """
    Format admin recheck message with exact specification.

    Args:
        admin_display_name: Display name of the admin who initiated the recheck
        user_id: Discord user ID for mention
        old_status: Previous status (internal format)
        new_status: New status (internal format)

    Returns:
        tuple[str, bool]: (formatted_message, changed_bool)
        - formatted_message: The formatted message string
        - changed_bool: True if roles changed, False if no change
    """
    old_pretty = canonicalize_status_for_display(old_status)
    new_pretty = canonicalize_status_for_display(new_status)

    # Determine if there was actually a status change
    changed = old_status != new_status

    # Set emoji and status word based on whether status changed
    if changed:
        emoji = "🔁"
        status_word = "Updated"
        # Two-line format with status change
        message = (
            f"[Admin Check • Admin: {admin_display_name}] <@{user_id}> {emoji} {status_word}\n"
            f"Status: {old_pretty} → {new_pretty}"
        )
    else:
        emoji = "🥺"
        status_word = "No changes"
        # Single-line format for no change
        message = f"[Admin Check • Admin: {admin_display_name}] <@{user_id}> {emoji} {status_word}"

    return message, changed


async def send_admin_recheck_notification(
    bot: "MyBot",
    admin_display_name: str,
    member: discord.Member,
    old_status: str,
    new_status: str,
) -> tuple[bool, bool]:
    """
    Send admin recheck notification to leadership announcements channel.

    Args:
        bot: Bot instance with config service
        admin_display_name: Display name of admin who initiated recheck
        member: Discord member being rechecked
        old_status: Previous status (internal format)
        new_status: New status (internal format)

    Returns:
        tuple[bool, bool]: (success, changed) where success indicates if message was sent and changed indicates if roles changed
    """
    guild = member.guild
    guild_config = bot.services.guild_config

    # Debug-only context without sensitive names
    logger.debug(
        "send_admin_recheck_notification called",
        extra={"user_id": member.id, "guild_id": guild.id},
    )

    # Get leadership announcement channel via config service
    leadership_channel = await guild_config.get_channel(
        guild.id, "leadership_announcement_channel_id", guild
    )

    if not leadership_channel:
        logger.warning(
            f"No leadership_announcement_channel_id configured for guild {guild.id} (admin recheck notification)"
        )
        return False, False

    try:
        message, changed = format_admin_recheck_message(
            admin_display_name=admin_display_name,
            user_id=member.id,
            old_status=old_status,
            new_status=new_status,
        )

        await channel_send_message(leadership_channel, message)

        logger.info(
            f"Admin recheck notification sent to {leadership_channel.name}: {message.replace(chr(10), ' | ')}"
        )

        return True, changed
    except Exception as e:
        logger.warning(f"Failed to send admin recheck notification: {e}")
        return False, False


async def send_verification_announcements(
    bot: "MyBot",
    member: discord.Member,
    old_status: str,
    new_status: str,
    is_recheck: bool,
    by_admin: str | None = None,
):
    """
    Posts verification/re-check logs to leadership channel.
    """
    guild_config = bot.services.guild_config
    guild = member.guild

    lead_channel = await guild_config.get_channel(
        guild.id, "leadership_announcement_channel_id", guild
    )

    if not isinstance(member, discord.Member) or (
        guild and guild.get_member(member.id) is None
    ):
        try:
            member = await guild.fetch_member(member.id)
        except Exception as e:
            logger.warning(f"Failed to fetch full member object for {member.id}: {e}")
            return

    if not lead_channel:
        logger.warning(f"No leadership channel configured for guild {guild.id}")
        return

    old_status = (old_status or "").lower()
    new_status = (new_status or "").lower()

    def status_str(s, org_sid="ORG"):
        """Return formatted status string with organization SID."""
        if s == "main":
            return f"**{org_sid} Main**"
        if s == "affiliate":
            return f"**{org_sid} Affiliate**"
        return "*Not a Member*" if s == "non_member" else str(s)

    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = ""
    if is_recheck and by_admin and by_admin != getattr(member, "display_name", None):
        admin_phrase = f" (**{by_admin}** Initiated)"

    # Fetch organization SID for dynamic status strings
    org_sid = "ORG"
    if hasattr(bot, "services") and bot.services.guild_config:
        with contextlib.suppress(Exception):
            org_sid = await bot.services.guild_config.get_setting(
                member.guild.id, "organization.sid", default="ORG"
            )

    if lead_channel:
        try:
            if is_recheck:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} {log_action}{admin_phrase}: "
                    f"**{status_str(old_status, org_sid)}** → **{status_str(new_status, org_sid)}**",
                )
            else:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} verified as {status_str(new_status, org_sid)}",
                )
        except Exception as e:
            logger.warning(f"Could not send log to leadership channel: {e}")


async def send_admin_bulk_check_summary(
    bot: "MyBot",
    *,
    guild: discord.Guild,
    invoker: discord.Member,
    scope_label: str,
    scope_channel: str | None,
    embed: discord.Embed,
    csv_bytes: bytes,
    csv_filename: str,
) -> str:
    """
    Send bulk verification check summary to leadership/admin announcement channel.

    Posts a single message containing:
    - Detailed embed with requester, scope, channel, counts, and per-user info
    - CSV attachment with complete results

    Args:
        bot: Bot instance with config
        guild: Discord guild
        invoker: Admin who initiated the check
        scope_label: "specific users" | "voice channel" | "all active voice"
        scope_channel: Channel name if applicable (e.g., "#General-Voice")
        embed: Pre-built summary embed
        csv_bytes: CSV file content as bytes
        csv_filename: Filename for the CSV attachment

    Returns:
        Channel name (e.g., "leadership-announcements") for user acknowledgment

    Raises:
        Exception if channel not configured or message fails to send
    """
    guild_config = bot.services.guild_config

    # Get leadership announcement channel
    channel = await guild_config.get_channel(
        guild.id, "leadership_announcement_channel_id", guild
    )

    if not channel:
        logger.error(
            f"No leadership_announcement_channel_id configured for guild {guild.id}"
        )
        raise ValueError("Leadership announcement channel not configured")

    try:
        # Create CSV file attachment
        csv_file = discord.File(fp=io.BytesIO(csv_bytes), filename=csv_filename)

        # Send embed + CSV to leadership channel (NOT using leadership_log header)
        await channel.send(embed=embed, file=csv_file)

        logger.info(
            f"Bulk check summary posted to #{channel.name} by {invoker.display_name} "
            f"(scope: {scope_label}, checked: {len(csv_bytes)} bytes CSV)"
        )

        return channel.name

    except Exception as e:
        logger.exception(
            f"Failed to send bulk check summary to leadership channel: {e}"
        )
        raise

        # ----------------------------
        # Queue helpers
        # ----------------------------


def _classify_event(old_status: str, new_status: str) -> str | None:
    """
    Map a status transition to an announceable event type.

    Only promotions are announced:
    - non_member → main: "joined_main"
    - non_member → affiliate: "joined_affiliate"
    - affiliate → main: "promoted_to_main"

    Demotions return None (not announced).
    Treats "unknown" as equivalent to "non_member" for classification.

    Args:
        old_status: Previous membership status
        new_status: New membership status

    Returns:
        Event type string for promotions, None for demotions/no-change
    """
    o = (old_status or "").lower().strip()
    n = (new_status or "").lower().strip()

    # Normalize 'unknown' to 'non_member' (defensive edge case handling)
    if o == "unknown":
        o = "non_member"
    if n == "unknown":
        n = "non_member"

    if not o or not n or o == n:
        return None

    # Promotions only
    if n == "main" and o == "non_member":
        return "joined_main"
    if n == "affiliate" and o == "non_member":
        return "joined_affiliate"
    if o == "affiliate" and n == "main":
        return "promoted_to_main"

    # Demotions (main→affiliate, main→non_member, affiliate→non_member) are not announced
    return None


async def enqueue_announcement_for_guild(
    bot,
    member: discord.Member,
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    prev_main_orgs: list[str] | None,
    prev_affiliate_orgs: list[str] | None,
) -> None:
    """
    Guild-aware announcement enqueuing that derives status from org lists.

    Compares previous and current org lists to determine status change for THIS guild's
    tracked organization, then enqueues if it's a promotion (not a demotion).

    Args:
        bot: Bot instance with services
        member: Discord member being verified/rechecked
        main_orgs: Current main organization SIDs
        affiliate_orgs: Current affiliate organization SIDs
        prev_main_orgs: Previous main organization SIDs (None if initial verification)
        prev_affiliate_orgs: Previous affiliate organization SIDs (None if initial verification)
    """
    from services.db.database import derive_membership_status

    try:
        # Get this guild's tracked organization SID
        guild_org_sid = "ORG"  # Default fallback
        if (
            hasattr(bot, "services")
            and bot.services
            and hasattr(bot.services, "guild_config")
        ):
            try:
                guild_org_sid = await bot.services.guild_config.get_setting(
                    member.guild.id, "organization.sid", default="ORG"
                )
                # Remove JSON quotes if present
                if isinstance(guild_org_sid, str) and guild_org_sid.startswith('"'):
                    guild_org_sid = guild_org_sid.strip('"')
            except Exception as e:
                logger.debug(f"Failed to get guild org SID, using ORG: {e}")

        # Derive status for this guild before and after
        old_status = derive_membership_status(
            prev_main_orgs, prev_affiliate_orgs, guild_org_sid
        )
        new_status = derive_membership_status(main_orgs, affiliate_orgs, guild_org_sid)

        # Business-level visibility: record the derived transition for this guild
        logger.info(
            "Announcement status check",
            extra={
                "user_id": member.id,
                "guild_id": member.guild.id,
                "old_status": old_status,
                "new_status": new_status,
                "org_sid": guild_org_sid,
            },
        )

        # Enqueue if it's a promotion; also log classification decision
        et = _classify_event(old_status, new_status)
        logger.info(
            "Announcement classification",
            extra={
                "user_id": member.id,
                "guild_id": member.guild.id,
                "old_status": old_status,
                "new_status": new_status,
                "event_type": et,
            },
        )

        if not et:
            return

        await enqueue_verification_event(member, old_status, new_status)

    except Exception as e:
        logger.warning(
            f"Failed to enqueue guild-aware announcement for user {member.id}: {e}"
        )


async def enqueue_verification_event(
    member: discord.Member, old_status: str, new_status: str
):
    """
    Append an announceable verification event to the durable queue.

    Coalescing behavior:
      • Remove any other pending events for this user first (ensures 1 pending/user).
      • Insert only the newest event. This prevents double-announcements
        when a user moves quickly (non_member → affiliate → main).
      • NOTE: Rapid status changes will only announce the FINAL state, not intermediate
        milestones. E.g., non_member → affiliate → main will only announce "promoted_to_main",
        not "joined_affiliate". This is intentional to reduce announcement spam.
    """
    et = _classify_event(old_status, new_status)
    if not et:
        logger.debug(
            f"Status transition not announceable: {old_status} → {new_status}",
            extra={
                "user_id": member.id,
                "guild_id": member.guild.id if member.guild else None,
            },
        )
        return

    now = int(time.time())
    guild_id = member.guild.id if member.guild else None

    if guild_id is None:
        logger.warning(
            f"Cannot enqueue announcement event for user {member.id}: no guild context"
        )
        return

    try:
        async with BaseRepository.transaction() as db:
            # Coalesce: drop older pending events for this user in this guild
            await db.execute(
                "DELETE FROM announcement_events WHERE user_id = ? AND guild_id = ? AND announced_at IS NULL",
                (member.id, guild_id),
            )

            # Insert the latest event with guild_id
            await db.execute(
                (
                    "INSERT INTO announcement_events (user_id, guild_id, old_status, new_status, event_type, created_at, "
                    "announced_at) VALUES (?, ?, ?, ?, ?, ?, NULL)"
                ),
                (
                    member.id,
                    guild_id,
                    (old_status or "non_member"),
                    (new_status or ""),
                    et,
                    now,
                ),
            )
            await db.commit()
            logger.info(
                "Announcement queued",
                extra={
                    "user_id": member.id,
                    "guild_id": guild_id,
                    "event_type": et,
                },
            )
    except Exception as e:
        logger.warning(
            f"Failed to enqueue announcement event for user {member.id} in guild {guild_id}: {e}"
        )

        # ----------------------------
        # Bulk Announcer v2 (queue-driven)
        # ----------------------------


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
                await config_service.get_global_setting("bulk_announcement.hour_utc", 18),
                18,
            )
            self.minute_utc = _to_int(
                await config_service.get_global_setting("bulk_announcement.minute_utc", 0),
                0,
            )
            self.threshold = _to_int(
                await config_service.get_global_setting("bulk_announcement.threshold", 50),
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
                org_sid = None
                org_name = None
                if hasattr(self.bot, "services") and self.bot.services.guild_config:
                    try:
                        org_sid = await self.bot.services.guild_config.get_setting(
                            guild_id, "organization.sid", default=None
                        )
                        org_name = await self.bot.services.guild_config.get_setting(
                            guild_id, "organization.name", default=None
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch org settings for guild {guild_id}: {e}"
                        )

                # Fallback to "ORG" if no settings
                if not org_sid:
                    org_sid = "ORG"
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
                logger.info(f"BulkAnnouncer: marked {len(announced_ids)} events as announced")
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

            # ---------- Tasks ----------

    @tasks.loop()
    async def daily_flush(self):
        """
        Fires at the configured UTC time daily, flushing all pending events.
        """
        await self.flush_pending()

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
