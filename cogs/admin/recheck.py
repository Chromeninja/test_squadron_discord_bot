import asyncio
import contextlib
import random
import time

import discord
from discord.ext import commands, tasks

from helpers.http_helper import NotFoundError
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from helpers.role_helper import _compute_next_recheck, assign_roles
from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import flush_tasks
from services.db.database import Database
from utils.logging import get_logger
from verification.rsi_verification import is_valid_rsi_handle

logger = get_logger(__name__)


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

        # Process users across ALL guilds
        for user_id, rsi_handle in rows:
            # Find all guilds where this user is a member
            user_guilds = [g for g in self.bot.guilds if g.get_member(int(user_id))]

            if not user_guilds:
                # User not in any guild - prune
                await self._prune_user_from_db(user_id)
                continue

            # Recheck in each guild separately
            for guild in user_guilds:
                member = guild.get_member(int(user_id))
                if member:
                    await self._handle_recheck(member, user_id, rsi_handle, now)

    async def _prune_user_from_db(self, user_id: int) -> None:
        """Remove user records when they're no longer in any guild."""
        try:
            async with Database.get_connection() as db:
                await db.execute(
                    "DELETE FROM auto_recheck_state WHERE user_id = ?",
                    (user_id,),
                )
                await db.execute(
                    "DELETE FROM verification WHERE user_id = ?",
                    (user_id,),
                )
                await db.commit()
            logger.info(f"Pruned user {user_id} from DB (left all guilds)")
        except Exception as e:
            logger.warning(f"Failed to prune user {user_id}: {e}")

    async def _fetch_member_or_prune(
        self, guild: discord.Guild, user_id: int
    ) -> discord.Member | None:
        """Return member if present; otherwise prune their records and return None."""
        member = guild.get_member(int(user_id))
        if member is None:
            try:
                member = await guild.fetch_member(int(user_id))
            except (discord.NotFound, discord.HTTPException):
                member = None

        # If member not found, allow a short delay and retry once to avoid
        # pruning during transient cache misses.
        if member is None:
            await asyncio.sleep(1)
            # Retry the same lookup strategy once more
            member = guild.get_member(int(user_id))
            if member is None:
                try:
                    member = await guild.fetch_member(int(user_id))
                except (discord.NotFound, discord.HTTPException):
                    member = None

        if member is None:
            try:
                async with Database.get_connection() as db:
                    await db.execute(
                        "DELETE FROM verification WHERE user_id = ?", (int(user_id),)
                    )
                    await db.execute(
                        "DELETE FROM auto_recheck_state WHERE user_id = ?",
                        (int(user_id),),
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to prune departed user {user_id}: {e}")
            return None

        return member

    async def _handle_recheck(
        self, member: discord.Member, user_id: int, rsi_handle: str, now: int
    ) -> None:
        try:
            # Validate handle and fetch current status
            # Get organization config from guild
            org_name = "test"  # Default fallback
            org_sid = None
            if hasattr(self.bot, "services") and hasattr(
                self.bot.services,  # type: ignore[attr-defined]
                "guild_config",  # type: ignore[attr-defined]
            ):
                try:
                    org_name_config = await self.bot.services.guild_config.get_setting(  # type: ignore[attr-defined]
                        member.guild.id, "organization.name", default="test"
                    )
                    org_name = (
                        org_name_config.strip().lower() if org_name_config else "test"
                    )

                    org_sid_config = await self.bot.services.guild_config.get_setting(  # type: ignore[attr-defined]
                        member.guild.id, "organization.sid", default=None
                    )
                    org_sid = org_sid_config.strip().upper() if org_sid_config else None
                except Exception as e:
                    logger.warning(
                        f"Failed to get org config: {e}",
                        extra={"guild_id": member.guild.id},
                    )

            (
                verify_value,
                cased_handle,
                community_moniker,
                main_orgs,
                affiliate_orgs,
            ) = await is_valid_rsi_handle(
                rsi_handle,
                self.bot.http_client,  # type: ignore[attr-defined]
                org_name,
                org_sid,  # type: ignore[attr-defined]
            )
            if verify_value is None or cased_handle is None:  # moniker optional
                # Transient fetch/parse failure: schedule backoff
                current_fc = await Database.get_auto_recheck_fail_count(int(user_id))
                delay = self._compute_backoff(fail_count=(current_fc or 0) + 1)
                await Database.upsert_auto_recheck_failure(
                    user_id=int(user_id),
                    next_retry_at=now + delay,
                    now=now,
                    error_msg="Fetch/parse failure",
                    inc=True,
                )
                return
            # Snapshot before
            import time as _t

            _start = _t.time()
            before_snap = await snapshot_member_state(self.bot, member)
            # Apply roles; get (old_status, new_status)
            _old_status, _new_status = await assign_roles(
                member,
                verify_value,
                cased_handle,
                self.bot,
                community_moniker=community_moniker,
                main_orgs=main_orgs,
                affiliate_orgs=affiliate_orgs,
            )
            with contextlib.suppress(Exception):
                await flush_tasks()
            after_snap = await snapshot_member_state(self.bot, member)
            diff = diff_snapshots(before_snap, after_snap)
            cs = ChangeSet(
                user_id=member.id,
                event=EventType.AUTO_CHECK,
                initiator_kind="Auto",
                initiator_name=None,
                notes=None,
                guild_id=member.guild.id if member.guild else None,
            )
            for k, v in diff.items():
                setattr(cs, k, v)
            # duration tracking removed
            try:
                await post_if_changed(self.bot, cs)
            except Exception:
                logger.debug("Leadership log post failed (auto recheck)")

            # Schedule next success recheck using cross-guild membership status
            next_retry = await _compute_next_recheck(self.bot, int(user_id), now)
            if next_retry > 0:
                await Database.upsert_auto_recheck_success(
                    user_id=int(user_id),
                    next_retry_at=next_retry,
                    now=now,
                    new_fail_count=0,
                )

        except NotFoundError:
            from helpers.username_404 import handle_username_404

            try:
                await handle_username_404(self.bot, member, rsi_handle)
            except Exception as e:
                logger.warning(f"Failed unified 404 handling for {user_id}: {e}")

        except Exception as e:
            # Other errors → exponential backoff and record error
            logger.warning(f"Auto recheck exception for {user_id}: {e}")
            current_fc = await Database.get_auto_recheck_fail_count(int(user_id))
            delay = self._compute_backoff(fail_count=(current_fc or 0) + 1)
            with contextlib.suppress(Exception):
                await Database.upsert_auto_recheck_failure(
                    user_id=int(user_id),
                    next_retry_at=now + delay,
                    now=now,
                    error_msg=str(e)[:500],
                    inc=True,
                )

    def _compute_backoff(self, fail_count: int) -> int:
        """
        Exponential backoff in seconds with jitter, capped.
        fail_count=1 -> base; 2 -> 2x base; etc.
        """
        base = self.backoff_base_m * 60
        cap = self.backoff_max_m * 60
        exp = base * (2 ** max(0, int(fail_count) - 1))
        jitter = random.randint(0, 600)  # Up to +10m
        return min(exp + jitter, cap)


async def setup(bot: commands.Bot) -> None:
    if (bot.config or {}).get("auto_recheck", {}).get("enabled", True):  # type: ignore[attr-defined]
        await bot.add_cog(AutoRecheck(bot))
        logger.info("AutoRecheck cog loaded.")
    else:
        logger.info("AutoRecheck disabled by config.")
