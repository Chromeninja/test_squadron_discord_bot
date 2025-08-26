from dataclasses import dataclass
from typing import Optional, Set, Dict, Any
import discord

from helpers.database import Database
from helpers.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MemberSnapshot:
    status: str
    moniker: Optional[str]  # community_moniker from DB
    handle: Optional[str]   # rsi_handle from DB
    username: Optional[str]  # discord nickname/display
    roles: Set[str]  # Role names (non-managed filtered later)


async def snapshot_member_state(bot, member: discord.Member) -> MemberSnapshot:
    # Fetch DB state
    status = 'Not a Member'
    moniker = None
    handle = None
    try:
        async with Database.get_connection() as db:
            cur = await db.execute("SELECT membership_status, community_moniker, rsi_handle FROM verification WHERE user_id=?", (member.id,))
            row = await cur.fetchone()
            if row:
                status_db, moniker_db, handle_db = row
                # Map internal statuses to human terms for logs
                mapping = {
                    'main': 'Main',
                    'affiliate': 'Affiliate',
                    'non_member': 'Not a Member',
                }
                status = mapping.get(status_db, status_db or 'Not a Member')
                moniker = moniker_db
                handle = handle_db
    except Exception as e:
        logger.debug(f"Snapshot DB fetch failed for {member.id}: {e}")

    username = member.display_name or getattr(member, 'name', None)
    roles = set()
    for r in getattr(member, 'roles', []) or []:
        if not r:
            continue
        try:
            if getattr(r, 'managed', False):
                continue
        except Exception:
            pass
        roles.add(getattr(r, 'name', str(r)))
    return MemberSnapshot(status=status, moniker=moniker, handle=handle, username=username, roles=roles)


def diff_snapshots(before: MemberSnapshot, after: MemberSnapshot) -> Dict[str, Any]:
    roles_added = sorted(list(after.roles - before.roles))
    roles_removed = sorted(list(before.roles - after.roles))
    return {
        'status_before': before.status,
        'status_after': after.status,
        'moniker_before': before.moniker,
        'moniker_after': after.moniker,
        'handle_before': before.handle,
        'handle_after': after.handle,
        'username_before': before.username,
        'username_after': after.username,
        'roles_added': roles_added,
        'roles_removed': roles_removed,
    }


__all__ = ['MemberSnapshot', 'snapshot_member_state', 'diff_snapshots']
