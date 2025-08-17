# helpers/announcement.py

import datetime
import time
from typing import Dict, List, Tuple

import discord
from discord.ext import tasks, commands

from helpers.discord_api import channel_send_message
from helpers.logger import get_logger
from helpers.database import Database

logger = get_logger(__name__)

# ----------------------------
# Leadership log 
# ----------------------------
async def send_verification_announcements(
    bot,
    member: discord.Member,
    old_status: str,
    new_status: str,
    is_recheck: bool,
    by_admin: str = None
):
    """
    Posts verification/re-check logs to leadership channel.
    """
    config = bot.config
    lead_channel_id = config['channels'].get('leadership_announcement_channel_id')
    guild = member.guild

    if not isinstance(member, discord.Member) or (guild and guild.get_member(member.id) is None):
        try:
            member = await guild.fetch_member(member.id)
        except Exception as e:
            logger.warning(f"Failed to fetch full member object for {member.id}: {e}")

    lead_channel = guild.get_channel(lead_channel_id) if (guild and lead_channel_id) else None

    old_status = (old_status or '').lower()
    new_status = (new_status or '').lower()

    def status_str(s):
        if s == "main": return "**TEST Main**"
        if s == "affiliate": return "**TEST Affiliate**"
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
                    f"🗂️ {member.mention} {log_action}{admin_phrase}: **{status_str(old_status)}** → **{status_str(new_status)}**"
                )
            else:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} verified as {status_str(new_status)}"
                )
        except Exception as e:
            logger.warning(f"Could not send log to leadership channel: {e}")


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


async def enqueue_verification_event(member: discord.Member, old_status: str, new_status: str):
    """
    Append an announceable verification event to the durable queue.
    Idempotent for identical pending event_type per user.
    """
    et = _classify_event(old_status, new_status)
    if not et:
        return

    now = int(time.time())
    try:
        async with Database.get_connection() as db:
            # Dedupe: skip if an identical pending event already exists
            cur = await db.execute(
                "SELECT id FROM announcement_events "
                "WHERE user_id = ? AND event_type = ? AND announced_at IS NULL",
                (member.id, et)
            )
            if await cur.fetchone():
                return

            await db.execute(
                "INSERT INTO announcement_events (user_id, old_status, new_status, event_type, created_at, announced_at) "
                "VALUES (?, ?, ?, ?, ?, NULL)",
                (member.id, old_status or "non_member", new_status or "", et, now),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to enqueue announcement event for user {member.id}: {e}")


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
    """

    def __init__(self, bot):
        self.bot = bot

        cfg = bot.config or {}
        chan_cfg = cfg.get("channels", {}) or {}
        self.public_channel_id: int | None = chan_cfg.get("public_announcement_channel_id")

        bulk_cfg = cfg.get("bulk_announcement", {}) or {}
        self.hour_utc: int = int(bulk_cfg.get("hour_utc", 18))
        self.minute_utc: int = int(bulk_cfg.get("minute_utc", 0))
        self.threshold: int = int(bulk_cfg.get("threshold", 50))
        self.max_mentions_per_message: int = int(bulk_cfg.get("max_mentions_per_message", 50))
        self.max_chars_per_message: int = int(bulk_cfg.get("max_chars_per_message", 1800))

        # Validate & clamp
        if not (0 <= self.hour_utc < 24):
            logger.warning("Invalid hour_utc in config; using 18")
            self.hour_utc = 18
        if not (0 <= self.minute_utc < 60):
            logger.warning("Invalid minute_utc in config; using 0")
            self.minute_utc = 0
        if self.max_mentions_per_message < 5:
            self.max_mentions_per_message = 5
        if self.max_chars_per_message > 1950:
            self.max_chars_per_message = 1950

        # Daily timer
        self.daily_flush.change_interval(
            time=datetime.time(
                hour=self.hour_utc,
                minute=self.minute_utc,
                tzinfo=datetime.timezone.utc,
            )
        )
        self.daily_flush.reconnect = False

        if self.public_channel_id:
            self.daily_flush.start()
            self.threshold_watch.start()
        else:
            logger.warning("BulkAnnouncer disabled: public_announcement_channel_id not configured.")

    def cog_unload(self):
        self.daily_flush.cancel()
        self.threshold_watch.cancel()

    # ---------- Public helpers ----------
    async def flush_pending(self) -> bool:
        """
        Flush all pending queued events into one digest (split into multiple messages as needed).
        Returns True if anything was sent.
        """
        channel = self.bot.get_channel(self.public_channel_id) if self.public_channel_id else None
        if channel is None:
            logger.warning("BulkAnnouncer: public_announcement_channel_id missing or channel not found.")
            return False

        async with Database.get_connection() as db:
            cur = await db.execute(
                "SELECT id, user_id, event_type FROM announcement_events "
                "WHERE announced_at IS NULL "
                "ORDER BY created_at ASC"
            )
            rows = await cur.fetchall()

        if not rows:
            logger.info("BulkAnnouncer: no pending announcements to flush.")
            return False

        events_by_type: Dict[str, List[Tuple[int, int]]] = {
            "joined_main": [],
            "joined_affiliate": [],
            "promoted_to_main": [],
        }
        for _id, user_id, et in rows:
            if et in events_by_type:
                events_by_type[et].append((_id, user_id))

        guild = channel.guild
        allowed = discord.AllowedMentions(users=True, roles=False, everyone=False)

        sent_any = False
        announced_ids: List[int] = []

        sections = [
            ("joined_main",
             "🍻 **New TEST Main reporting in!**",
             "You made the right call. Welcome to TEST Squadron — BEST Squadron."),
            ("joined_affiliate",
             "🤝 **New TEST Affiliates**",
             "Glad to have you aboard! Ready to go all-in? Set TEST as your **Main Org** to fully commit to the BEST SQUADRON."),
            ("promoted_to_main",
             "⬆️ **Promotions: Affiliate → TEST Main**",
             "o7 and welcome to the big chair. 🍻"),
        ]
        
        for key, header, footer in sections:
            items = events_by_type.get(key, [])
            if not items:
                continue

            id_mention_pairs: List[Tuple[int, str]] = []
            for ev_id, uid in items:
                m = guild.get_member(uid)
                if m:
                    id_mention_pairs.append((ev_id, m.mention))
                else:
                    id_mention_pairs.append((ev_id, f"<@{uid}>"))

            if not id_mention_pairs:
                continue

            for batch_ids, batch_mentions in self._build_batches(
                id_mention_pairs,
                header=header,
                footer=footer,
                max_mentions=self.max_mentions_per_message,
                max_chars=self.max_chars_per_message
            ):
                content = self._compose_message(header, batch_mentions, footer)
                try:
                    await channel.send(content, allowed_mentions=allowed)
                    sent_any = True
                    announced_ids.extend(batch_ids)
                except Exception as e:
                    logger.warning(f"BulkAnnouncer: failed sending a batch for {key}: {e}")

        if announced_ids:
            now = int(time.time())
            try:
                async with Database.get_connection() as db:
                    CHUNK = 500
                    for i in range(0, len(announced_ids), CHUNK):
                        chunk = announced_ids[i:i+CHUNK]
                        qmarks = ",".join("?" for _ in chunk)
                        await db.execute(
                            f"UPDATE announcement_events SET announced_at = ? WHERE id IN ({qmarks})",
                            (now, *chunk)
                        )
                    await db.commit()
            except Exception as e:
                logger.warning(f"BulkAnnouncer: failed to mark events announced: {e}")

        return sent_any

    # ---------- Internal helpers ----------
    def _compose_message(self, header: str, mentions: List[str], footer: str) -> str:
        body = "\n".join(mentions)
        parts = [header, body]
        if footer:
            parts.extend(["", footer])
        return "\n".join(parts)

    def _build_batches(
        self,
        id_mention_pairs: List[Tuple[int, str]],
        header: str,
        footer: str,
        max_mentions: int,
        max_chars: int
    ) -> List[Tuple[List[int], List[str]]]:
        """
        Produces batches where each batch:
          • has <= max_mentions mentions
          • and the full message length (header + mentions + footer) stays under max_chars
        Returns list of (ids, mentions) for each batch.
        """
        batches: List[Tuple[List[int], List[str]]] = []

        current_ids: List[int] = []
        current_mentions: List[str] = []

        def msg_len(mentions_list: List[str]) -> int:
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
                prospective = current_mentions + [mention]
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