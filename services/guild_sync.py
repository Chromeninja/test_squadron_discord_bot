"""
Guild synchronization layer.

Applies a global verification state to individual guilds with bounded
concurrency, no-op detection, and task-queue-based Discord updates.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import flush_tasks
from services.db.database import Database, derive_membership_status
from utils.logging import get_logger

if TYPE_CHECKING:
    import discord

    from services.verification_state import GlobalVerificationState

logger = get_logger(__name__)


@dataclass
class GuildSyncResult:
    guild_id: int
    user_id: int
    member: discord.Member
    before: object
    after: object

    @property
    def diff(self) -> dict:
        # Type: ignore because before/after are runtime MemberSnapshot objects
        return diff_snapshots(self.before, self.after).to_dict()  # type: ignore[attr-defined]


async def _get_org_sid(bot, guild_id: int) -> str:
    if (
        hasattr(bot, "services")
        and bot.services
        and hasattr(bot.services, "guild_config")
    ):
        try:
            return await bot.services.guild_config.get_org_sid(guild_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "Failed to fetch org SID for guild %s: %s", guild_id, e
            )
    return "TEST"


async def apply_state_to_guild(
    global_state: GlobalVerificationState,
    guild: discord.Guild,
    bot,
) -> GuildSyncResult | None:
    """Apply a global verification state to a specific guild."""
    member = guild.get_member(global_state.user_id)
    if not member:
        return None

    # Derive guild-specific status
    org_sid = await _get_org_sid(bot, guild.id)
    guild_status = derive_membership_status(
        global_state.main_orgs,
        global_state.affiliate_orgs,
        org_sid,
    )

    # Snapshot before
    before = await snapshot_member_state(bot, member)

    # Apply roles and nickname (no-op safe)
    from helpers.role_helper import apply_roles_for_status

    await apply_roles_for_status(
        member,
        guild_status,
        global_state.rsi_handle,
        bot,
        community_moniker=global_state.community_moniker,
        main_orgs=global_state.main_orgs,
        affiliate_orgs=global_state.affiliate_orgs,
    )

    # Flush queued Discord tasks for timely state
    await flush_tasks()

    # Use global_state org lists for "after" snapshot since DB isn't updated yet
    after = await snapshot_member_state(
        bot,
        member,
        main_orgs_override=global_state.main_orgs,
        affiliate_orgs_override=global_state.affiliate_orgs,
    )
    return GuildSyncResult(
        guild_id=guild.id,
        user_id=member.id,
        member=member,
        before=before,
        after=after,
    )


async def sync_user_to_all_guilds(
    global_state: GlobalVerificationState,
    bot,
    *,
    batch_size: int = 5,
    max_concurrency: int = 3,
) -> list[GuildSyncResult]:
    """Sync a user to all guilds with bounded parallelism."""
    guild_ids = await Database.get_user_active_guilds(global_state.user_id)
    if not guild_ids:
        # Fallback to bot guilds if membership table missing
        guild_ids = [g.id for g in bot.guilds if g.get_member(global_state.user_id)]

    results: list[GuildSyncResult] = []
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _sync_one(guild_id: int) -> GuildSyncResult | None:
        guild = bot.get_guild(guild_id)
        if not guild:
            return None
        async with semaphore:
            res = await apply_state_to_guild(global_state, guild, bot)
            return res

    # Process in batches to avoid thundering herd
    for i in range(0, len(guild_ids), batch_size):
        batch = guild_ids[i : i + batch_size]
        batch_results = await asyncio.gather(*(_sync_one(gid) for gid in batch))
        results.extend([r for r in batch_results if r])

    return results
