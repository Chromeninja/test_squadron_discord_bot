# Helpers/announcement.py

import datetime
import io
import time

import discord
from discord.ext import commands, tasks

from helpers.discord_api import channel_send_message
from services.db.database import Database
from utils.logging import get_logger

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
    bot,
    admin_display_name: str,
    member: discord.Member,
    old_status: str,
    new_status: str,
) -> tuple[bool, bool]:
    """
    Send admin recheck notification to leadership announcements channel.

    Args:
        bot: Bot instance with config
        admin_display_name: Display name of admin who initiated recheck
        member: Discord member being rechecked
        old_status: Previous status (internal format)
        new_status: New status (internal format)

    Returns:
        tuple[bool, bool]: (success, changed) where success indicates if message was sent and changed indicates if roles changed
    """
    config = bot.config
    leadership_channel_id = config.get("channels", {}).get(
        "leadership_announcement_channel_id"
    )

    if not leadership_channel_id:
        logger.warning(
            "No leadership_announcement_channel_id configured for admin recheck notification"
        )
        return False, False

    leadership_channel = bot.get_channel(leadership_channel_id)
    if not leadership_channel:
        logger.warning(
            f"Leadership announcement channel {leadership_channel_id} not found"
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
    bot,
    member: discord.Member,
    old_status: str,
    new_status: str,
    is_recheck: bool,
    by_admin: str | None = None,
):
    """
    Posts verification/re-check logs to leadership channel.
    """
    config = bot.config
    lead_channel_id = config["channels"].get("leadership_announcement_channel_id")
    guild = member.guild

    if not isinstance(member, discord.Member) or (
        guild and guild.get_member(member.id) is None
    ):
        try:
            member = await guild.fetch_member(member.id)
        except Exception as e:
            logger.warning(f"Failed to fetch full member object for {member.id}: {e}")
            return

    lead_channel = (
        guild.get_channel(lead_channel_id) if (guild and lead_channel_id) else None
    )

    old_status = (old_status or "").lower()
    new_status = (new_status or "").lower()

    def status_str(s):
        if s == "main":
            return "**TEST Main**"
        if s == "affiliate":
            return "**TEST Affiliate**"
        return "*Not a Member*" if s == "non_member" else str(s)

    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = ""
    if is_recheck and by_admin and by_admin != getattr(member, "display_name", None):
        admin_phrase = f" (**{by_admin}** Initiated)"

    if lead_channel:
        try:
            if is_recheck:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} {log_action}{admin_phrase}: "
                    f"**{status_str(old_status)}** → **{status_str(new_status)}**",
                )
            else:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} verified as {status_str(new_status)}",
                )
        except Exception as e:
            logger.warning(f"Could not send log to leadership channel: {e}")


async def send_admin_bulk_check_summary(
    bot: commands.Bot,
    *,
    guild: discord.Guild,
    invoker: discord.Member,
    scope_label: str,
    scope_channel: str | None,
    embed: discord.Embed,
    csv_bytes: bytes,
    csv_filename: str
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
    config = bot.config

    # Get leadership announcement channel
    channel_id = config.get("channels", {}).get("leadership_announcement_channel_id")

    if not channel_id:
        logger.error("No leadership_announcement_channel_id configured for bulk check summary")
        raise ValueError("Leadership announcement channel not configured")

    channel = bot.get_channel(channel_id)
    if not channel:
        logger.error(f"Leadership announcement channel {channel_id} not found")
        raise ValueError(f"Leadership channel {channel_id} not found")

    try:
        # Create CSV file attachment
        csv_file = discord.File(
            fp=io.BytesIO(csv_bytes),
            filename=csv_filename
        )

        # Send embed + CSV to leadership channel (NOT using leadership_log header)
        await channel.send(embed=embed, file=csv_file)

        logger.info(
            f"Bulk check summary posted to #{channel.name} by {invoker.display_name} "
            f"(scope: {scope_label}, checked: {len(csv_bytes)} bytes CSV)"
        )

        return channel.name

    except Exception as e:
        logger.exception(f"Failed to send bulk check summary to leadership channel: {e}")
        raise

            # ----------------------------
            # Queue helpers
            # ----------------------------


def _classify_event(old_status: str, new_status: str) -> str | None:
    """
    Map a status transition to an announceable event type.
    """
    o = (old_status or "").lower().strip()
    n = (new_status or "").lower().strip()

    if not o or not n or o == n:
        return None

    if n == "main" and o == "non_member":
        return "joined_main"
    if n == "affiliate" and o == "non_member":
        return "joined_affiliate"
    if o == "affiliate" and n == "main":
        return "promoted_to_main"
    return None


async def enqueue_verification_event(
    member: discord.Member, old_status: str, new_status: str
):
    """
    Append an announceable verification event to the durable queue.

    Coalescing behavior:
      • Remove any other pending events for this user first (ensures 1 pending/user).
      • Insert only the newest event. This prevents double-announcements
        when a user moves quickly (non_member → affiliate → main).
    """
    et = _classify_event(old_status, new_status)
    if not et:
        return

    now = int(time.time())
    try:
        async with Database.get_connection() as db:
            # Coalesce: drop older pending events for this user
            await db.execute(
                "DELETE FROM announcement_events WHERE user_id = ? AND announced_at IS NULL",
                (member.id,),
            )

            # Insert the latest event
            await db.execute(
                (
                    "INSERT INTO announcement_events (user_id, old_status, new_status, event_type, created_at, "
                    "announced_at) VALUES (?, ?, ?, ?, ?, NULL)"
                ),
                (member.id, (old_status or "non_member"), (new_status or ""), et, now),
            )
            await db.commit()
    except Exception as e:
        logger.warning(
            f"Failed to enqueue announcement event for user {member.id}: {e}"
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

        cfg = bot.config or {}
        chan_cfg = cfg.get("channels", {}) or {}
        self.public_channel_id: int | None = chan_cfg.get(
            "public_announcement_channel_id"
        )

        bulk_cfg = cfg.get("bulk_announcement", {}) or {}
        self.hour_utc: int = int(bulk_cfg.get("hour_utc", 18))
        self.minute_utc: int = int(bulk_cfg.get("minute_utc", 0))
        self.threshold: int = int(bulk_cfg.get("threshold", 50))
        self.max_mentions_per_message: int = int(
            bulk_cfg.get("max_mentions_per_message", 50)
        )
        self.max_chars_per_message: int = int(
            bulk_cfg.get("max_chars_per_message", 1800)
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

        # Daily timer
        self.daily_flush.change_interval(
            time=datetime.time(
                hour=self.hour_utc,
                minute=self.minute_utc,
                tzinfo=datetime.UTC,
            )
        )
        self.daily_flush.reconnect = False

        if self.public_channel_id:
            self.daily_flush.start()
            self.threshold_watch.start()
        else:
            logger.warning(
                "BulkAnnouncer disabled: public_announcement_channel_id not configured."
            )

    def cog_unload(self):
        self.daily_flush.cancel()
        self.threshold_watch.cancel()

        # ---------- Public helpers ----------

    async def flush_pending(self) -> bool:
        """
        Flush all pending queued events into one digest (split into multiple messages as needed).
        Returns True if anything was sent.
        """
        channel = (
            self.bot.get_channel(self.public_channel_id)
            if self.public_channel_id
            else None
        )
        if channel is None:
            logger.warning(
                "BulkAnnouncer: public_announcement_channel_id missing or channel not found."
            )
            return False

        async with Database.get_connection() as db:
            cur = await db.execute(
                "SELECT id, user_id, event_type, created_at FROM announcement_events "
                "WHERE announced_at IS NULL "
                "ORDER BY created_at ASC"
            )
            rows = await cur.fetchall()

        if not rows:
            logger.info("BulkAnnouncer: no pending announcements to flush.")
            return False

        latest_by_user: dict[int, tuple] = {}  # User_id -> (id, event_type, created_at)
        for _id, user_id, et, ts in rows:
            prev = latest_by_user.get(user_id)
            if (prev is None) or (ts >= prev[2]):
                latest_by_user[user_id] = (_id, et, ts)

        events_by_type: dict[str, list[tuple[int, int]]] = {
            "joined_main": [],
            "joined_affiliate": [],
            "promoted_to_main": [],
        }
        for user_id, (ev_id, et, _) in latest_by_user.items():
            if et in events_by_type:
                events_by_type[et].append((ev_id, user_id))

        guild = channel.guild
        allowed = discord.AllowedMentions(users=True, roles=False, everyone=False)

        sent_any = False
        announced_ids: list[int] = []

        sections = [
            (
                "joined_main",
                "🍻 **New TEST Main reporting in!**",
                "You made the right call. Welcome to TEST Squadron — BEST Squardon.",
            ),
            (
                "joined_affiliate",
                "🤝 **New TEST Affiliates**",
                (
                    "Glad to have you aboard! Ready to go all-in? Set TEST as your "
                    "**Main Org** to fully commit to the Best Squardon."
                ),
            ),
            (
                "promoted_to_main",
                "⬆️ **Promotion from TEST Affiliate → TEST Main**",
                "o7 and welcome fully to TEST Squadron — BEST Squardon. 🍻",
            ),
        ]

        for key, header, footer in sections:
            items = events_by_type.get(key, [])
            if not items:
                continue

                # Build (id, mention) list with fallback mention
            id_mention_pairs: list[tuple[int, str]] = []
            user_ids_in_section: list[int] = []
            for ev_id, uid in items:
                m = guild.get_member(uid)
                mention = m.mention if m else f"<@{uid}>"
                id_mention_pairs.append((ev_id, mention))
                user_ids_in_section.append(uid)

            if not id_mention_pairs:
                continue

            for _batch_ids, batch_mentions in self._build_batches(
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
                except Exception as e:
                    logger.warning(
                        f"BulkAnnouncer: failed sending a batch for {key}: {e}"
                    )

                    # Track users for deletion
            announced_ids.extend(user_ids_in_section)

            # 4) Delete all pending rows for the announced users (keep table lean)
        if announced_ids:
            try:
                async with Database.get_connection() as db:
                    CHUNK = 500
                    for i in range(0, len(announced_ids), CHUNK):
                        chunk = announced_ids[i : i + CHUNK]
                        qmarks = ",".join("?" for _ in chunk)
                        await db.execute(
                            f"DELETE FROM announcement_events "
                            f"WHERE announced_at IS NULL AND user_id IN ({qmarks})",
                            (*chunk,),
                        )
                    await db.commit()
            except Exception as e:
                logger.warning(f"BulkAnnouncer: failed to delete announced events: {e}")

        return sent_any

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
        """
        batches: list[tuple[list[int], list[str]]] = []

        current_ids: list[int] = []
        current_mentions: list[str] = []

        def msg_len(mentions_list: list[str]) -> int:
            content = self._compose_message(header, mentions_list, footer)
            return len(content)

        for ev_id, mention in id_mention_pairs:
            # Enforce mention cap
            if len(current_mentions) >= max_mentions:
                if current_mentions:
                    batches.append((current_ids, current_mentions))
                current_ids, current_mentions = [], []

                # Enforce char cap (simulate before adding)
            if current_mentions:
                prospective = [*current_mentions, mention]
                if msg_len(prospective) > max_chars:
                    batches.append((current_ids, current_mentions))
                    current_ids, current_mentions = [], []

                    # Safe to add
            current_ids.append(ev_id)
            current_mentions.append(mention)

            # Final batch
        if current_mentions:
            batches.append((current_ids, current_mentions))

        return batches

    async def _count_pending(self) -> int:
        async with Database.get_connection() as db:
            cur = await db.execute(
                "SELECT COUNT(1) FROM announcement_events WHERE announced_at IS NULL"
            )
            row = await cur.fetchone()
            return int(row[0] if row and row[0] is not None else 0)

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
                    f"BulkAnnouncer: threshold reached ({pending} >= {self.threshold}); flushing."
                )
                await self.flush_pending()
        except Exception as e:
            logger.warning(f"BulkAnnouncer threshold watch error: {e}")

    @threshold_watch.before_loop
    async def before_watch(self):
        await self.bot.wait_until_ready()
