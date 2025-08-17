# cogs/recheck.py

import time
import random
from typing import Tuple

import discord
from discord.ext import commands, tasks

from helpers.logger import get_logger
from helpers.database import Database
from verification.rsi_verification import is_valid_rsi_handle
from helpers.role_helper import assign_roles
from helpers.announcement import send_verification_announcements

logger = get_logger(__name__)

class AutoRecheck(commands.Cog):
    """
    Periodically re-checks verified members in small batches.
    Uses the shared HTTP client and DB schedule to avoid hammering RSI.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = (bot.config or {}).get("auto_recheck", {}) or {}
        batch_cfg = (cfg.get("batch") or {})
        self.enabled = bool(cfg.get("enabled", True))
        self.run_every_minutes = int(batch_cfg.get("run_every_minutes", 60))
        self.max_users_per_run = int(batch_cfg.get("max_users_per_run", 50))

        backoff = (cfg.get("backoff") or {})
        self.backoff_base_m = int(backoff.get("base_minutes", 180))
        self.backoff_max_m = int(backoff.get("max_minutes", 1440))

        # dynamic loop interval
        if self.enabled:
            self.recheck_loop.change_interval(minutes=max(1, self.run_every_minutes))
            self.recheck_loop.start()

    def cog_unload(self):
        if self.recheck_loop.is_running():
            self.recheck_loop.cancel()

    @tasks.loop(minutes=60)
    async def recheck_loop(self):
        if not self.enabled:
            return
        await self.bot.wait_until_ready()

        try:
            now = int(time.time())
            # Batch size cap from config
            rows = await Database.get_due_auto_rechecks(now, self.max_users_per_run)
            if not rows:
                return

            guild: discord.Guild | None = self.bot.guilds[0] if self.bot.guilds else None
            if not guild:
                return

            for user_id, rsi_handle, _prev_status in rows:
                # Prune users who left
                member = guild.get_member(int(user_id))
                if member is None:
                    try:
                        member = await guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        member = None
                    except discord.HTTPException:
                        member = None
                if member is None:
                    try:
                        async with Database.get_connection() as db:
                            await db.execute("DELETE FROM verification WHERE user_id = ?", (int(user_id),))
                            await db.execute("DELETE FROM auto_recheck_state WHERE user_id = ?", (int(user_id),))
                            await db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to prune departed user {user_id}: {e}")
                    continue

                try:
                    verify_value, cased_handle = await is_valid_rsi_handle(rsi_handle, self.bot.http_client)
                    if verify_value is None or cased_handle is None:
                        delay = self._compute_backoff(user_id=user_id)
                        try:
                            await Database.upsert_auto_recheck_failure(
                                user_id=int(user_id),
                                next_retry_at=now + delay,
                                now=now,
                                error_msg="Fetch/parse failure",
                                inc=True
                            )
                        except Exception as e:
                            logger.warning(f"Failed to schedule backoff for {user_id}: {e}")
                        continue

                    old_status, new_status = await assign_roles(member, verify_value, cased_handle, self.bot)

                    # Only announce on change
                    if (old_status or "").lower() != (new_status or "").lower():
                        try:
                            await send_verification_announcements(
                                self.bot, member, old_status, new_status, is_recheck=True, by_admin="auto"
                            )
                        except Exception as e:
                            logger.warning(f"Auto log failed for {user_id}: {e}")

                    # Success: assign_roles already refreshed next schedule
                except Exception as e:
                    logger.warning(f"Auto recheck exception for {user_id}: {e}")
                    delay = self._compute_backoff(user_id=user_id)
                    try:
                        await Database.upsert_auto_recheck_failure(
                            user_id=int(user_id),
                            next_retry_at=now + delay,
                            now=now,
                            error_msg=str(e)[:500],
                            inc=True
                        )
                    except Exception:
                        pass

        except Exception as outer:
            logger.exception(f"Auto recheck loop error: {outer}")

    def _compute_backoff(self, user_id: int) -> int:
        base = self.backoff_base_m * 60
        cap = self.backoff_max_m * 60
        jitter = random.randint(0, 600)  # up to +10m
        return min(base + jitter, cap)

async def setup(bot: commands.Bot):
    if (bot.config or {}).get("auto_recheck", {}).get("enabled", True):
        await bot.add_cog(AutoRecheck(bot))
        logger.info("AutoRecheck cog loaded.")
    else:
        logger.info("AutoRecheck disabled by config.")
