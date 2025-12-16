import asyncio
import csv
import io
import re
import time
from collections import defaultdict

import discord
from discord.ext import commands, tasks

from helpers.http_helper import NotFoundError
from helpers.leadership_log import EventType, resolve_leadership_channel
from helpers.task_queue import flush_tasks
from helpers.username_404 import handle_username_404
from helpers.verification_logging import log_guild_sync
from services.db.database import Database
from services.guild_sync import sync_user_to_all_guilds
from services.verification_scheduler import (
    compute_next_retry,
    handle_recheck_failure,
    schedule_user_recheck,
)
from services.verification_state import compute_global_state, store_global_state
from utils.logging import get_logger

logger = get_logger(__name__)


def _auto_diff_changed(diff: dict) -> bool:
    if not diff:
        return False

    return any(
        [
            diff.get("status_before") != diff.get("status_after"),
            diff.get("moniker_before") != diff.get("moniker_after"),
            diff.get("handle_before") != diff.get("handle_after"),
            diff.get("username_before") != diff.get("username_after"),
            diff.get("main_orgs_before") != diff.get("main_orgs_after"),
            diff.get("affiliate_orgs_before") != diff.get("affiliate_orgs_after"),
            bool(diff.get("roles_added")),
            bool(diff.get("roles_removed")),
        ]
    )


def _build_auto_check_csv(rows: list[dict], guild_name: str) -> tuple[str, bytes]:
    timestamp_str = time.strftime("%Y%m%d_%H%M", time.gmtime())
    safe_guild = re.sub(r"[^\w\-]", "_", guild_name)[:30] or "guild"
    filename = f"auto_check_{safe_guild}_{timestamp_str}.csv"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "user_id",
            "username",
            "status_before",
            "status_after",
            "handle_before",
            "handle_after",
            "moniker_before",
            "moniker_after",
            "main_orgs_before",
            "main_orgs_after",
            "affiliate_orgs_before",
            "affiliate_orgs_after",
            "roles_added",
            "roles_removed",
        ]
    )

    def _fmt_list(val):
        if not val:
            return ""
        if isinstance(val, list):
            return ";".join(str(x) for x in val)
        return str(val)

    for row in rows:
        diff = row.get("diff", {})
        member = row.get("member")
        writer.writerow(
            [
                getattr(member, "id", ""),
                getattr(member, "display_name", getattr(member, "name", "")),
                diff.get("status_before", ""),
                diff.get("status_after", ""),
                diff.get("handle_before", ""),
                diff.get("handle_after", ""),
                diff.get("moniker_before", ""),
                diff.get("moniker_after", ""),
                _fmt_list(diff.get("main_orgs_before")),
                _fmt_list(diff.get("main_orgs_after")),
                _fmt_list(diff.get("affiliate_orgs_before")),
                _fmt_list(diff.get("affiliate_orgs_after")),
                _fmt_list(diff.get("roles_added")),
                _fmt_list(diff.get("roles_removed")),
            ]
        )

    return filename, output.getvalue().encode("utf-8")


class AutoRecheck(commands.Cog):
    """
    Periodically re-checks verified members in small batches.
    Uses the shared HTTP client and DB schedule to avoid hammering RSI.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        cfg = (bot.config or {}).get("auto_recheck", {}) or {}  # type: ignore[attr-defined]
        batch_cfg = cfg.get("batch") or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.run_every_minutes = int(batch_cfg.get("run_every_minutes", 60))
        self.max_users_per_run = int(batch_cfg.get("max_users_per_run", 50))

        backoff = cfg.get("backoff") or {}
        self.backoff_base_m = int(backoff.get("base_minutes", 180))
        self.backoff_max_m = int(backoff.get("max_minutes", 1440))

        # Dynamic loop interval
        if self.enabled:
            self.recheck_loop.change_interval(minutes=max(1, self.run_every_minutes))
            self.recheck_loop.start()

    async def cog_unload(self) -> None:
        if self.recheck_loop.is_running():
            self.recheck_loop.cancel()

    @tasks.loop(minutes=60)
    async def recheck_loop(self) -> None:
        if not self.enabled:
            return
        await self.bot.wait_until_ready()

        guild_summaries: dict[int, dict] = defaultdict(
            lambda: {"checked": 0, "changed": 0, "rows": []}
        )

        # Check if manual bulk check is running - defer if so
        if (
            hasattr(self.bot, "services")
            and hasattr(self.bot.services, "verify_bulk")  # type: ignore[attr-defined]
            and self.bot.services.verify_bulk.is_running()  # type: ignore[attr-defined]
        ):
            logger.info("Auto-recheck deferred: manual bulk check is running")
            return

        now = int(time.time())
        # Batch size cap from config
        rows = await Database.get_due_auto_rechecks(now, self.max_users_per_run)
        if not rows:
            return

        # Process users globally
        for user_id, rsi_handle in rows:
            try:
                global_state = await compute_global_state(
                    int(user_id),
                    rsi_handle,
                    self.bot.http_client,  # type: ignore[attr-defined]
                    config=getattr(self.bot, "config", {}),
                )
            except NotFoundError:
                await self._handle_not_found(user_id, rsi_handle)
                continue
            except Exception as e:
                fail_count = await Database.get_auto_recheck_fail_count(int(user_id))
                await handle_recheck_failure(
                    int(user_id), str(e), fail_count=fail_count + 1, config=getattr(self.bot, "config", {})
                )
                continue

            if global_state.error:
                fail_count = await Database.get_auto_recheck_fail_count(int(user_id))
                await handle_recheck_failure(
                    int(user_id), global_state.error, fail_count=fail_count + 1, config=getattr(self.bot, "config", {})
                )
                continue

            # Apply to guilds first so snapshot 'before' reflects prior DB state
            results = await sync_user_to_all_guilds(
                global_state,
                self.bot,
                batch_size=max(3, self.max_users_per_run // 5),
                max_concurrency=3,
            )

            # Persist updated global verification state after guild sync
            try:
                await store_global_state(global_state)
            except ValueError as e:
                logger.warning("Handle conflict for user %s: %s", user_id, e)
                continue

            for res in results:
                summary = guild_summaries[res.guild_id]
                summary["checked"] += 1
                if _auto_diff_changed(res.diff):
                    summary["changed"] += 1
                    summary["rows"].append({"member": res.member, "diff": res.diff})

                await log_guild_sync(res, EventType.AUTO_CHECK, self.bot)

            try:
                next_retry = compute_next_retry(
                    global_state,
                    fail_count=0,
                    config=getattr(self.bot, "config", {}),
                )
                await schedule_user_recheck(int(user_id), next_retry)
            except Exception as e:
                logger.warning("Failed to schedule next retry for %s: %s", user_id, e)

        await self._post_auto_summaries(guild_summaries)

    async def _prune_user_from_db(self, user_id: int) -> None:
        """Remove user data only when they have left all managed guilds."""
        remaining = [g for g in self.bot.guilds if g.get_member(int(user_id))]
        if remaining:
            return
        await Database.cleanup_all_user_data(int(user_id))

    async def _fetch_member_or_prune(self, guild: discord.Guild, user_id: int) -> discord.Member | None:
        """
        Try to fetch a member from a guild, with retry on transient cache miss.
        If member not found after retry, prune (delete) their verification data.

        Returns:
            discord.Member if found, None if not found and pruned
        """
        # Try get_member first (cache)
        member = guild.get_member(user_id)
        if member:
            return member

        # Brief sleep to allow cache to update
        await asyncio.sleep(0.5)

        # Retry get_member
        member = guild.get_member(user_id)
        if member:
            return member

        # Try fetch_member (API call) as fallback
        try:
            member = await guild.fetch_member(user_id)
            return member
        except discord.NotFound:
            pass

        # Member not found anywhere - prune their data
        await Database.cleanup_all_user_data(int(user_id))
        return None

    async def _handle_not_found(self, user_id: int, rsi_handle: str) -> None:
        """Handle RSI 404 across all guilds for the user."""
        for guild in self.bot.guilds:
            member = guild.get_member(int(user_id))
            if not member:
                continue
            try:
                await handle_username_404(self.bot, member, rsi_handle)
                await flush_tasks()
            except Exception as e:
                logger.warning(
                    "Failed 404 remediation for %s in guild %s: %s",
                    user_id,
                    guild.id,
                    e,
                )

    async def _post_auto_summaries(self, guild_summaries: dict[int, dict]) -> None:
        """Post per-guild auto-check summaries to the leadership channel."""
        for guild_id, data in guild_summaries.items():
            checked = data.get("checked", 0)
            changed = data.get("changed", 0)
            rows = data.get("rows", [])

            if checked == 0:
                continue

            channel = await resolve_leadership_channel(self.bot, guild_id)
            if not channel:
                logger.debug(
                    "Leadership log channel missing for guild %s; skipping summary",
                    guild_id,
                )
                continue

            content = (
                f"[Auto Check Summary] Checked {checked} member(s); "
                f"changes: {changed}."
            )

            file = None
            if changed > 0 and rows:
                guild_name = getattr(channel.guild, "name", str(guild_id))
                filename, csv_bytes = _build_auto_check_csv(rows, guild_name)
                file = discord.File(io.BytesIO(csv_bytes), filename=filename)

            try:
                if file:
                    await channel.send(content, file=file)
                else:
                    await channel.send(content)
            except Exception as e:
                logger.warning(
                    "Failed posting auto-check summary for guild %s: %s", guild_id, e
                )


async def setup(bot: commands.Bot) -> None:
    if (bot.config or {}).get("auto_recheck", {}).get("enabled", True):  # type: ignore[attr-defined]
        await bot.add_cog(AutoRecheck(bot))
        logger.info("AutoRecheck cog loaded.")
    else:
        logger.info("AutoRecheck disabled by config.")
