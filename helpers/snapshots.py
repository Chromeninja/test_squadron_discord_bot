# helpers/snapshots.py

from dataclasses import asdict, dataclass
from typing import Any

import discord
from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemberSnapshot:
    status: str
    moniker: str | None  # community_moniker from DB
    handle: str | None  # rsi_handle from DB
    username: str | None  # discord nickname/display
    roles: set[str]  # Role names (non-managed filtered later)


async def snapshot_member_state(bot, member: discord.Member) -> MemberSnapshot:
    # Fetch DB state
    status = "Not a Member"
    moniker = None
    handle = None
    try:
        async with Database.get_connection() as db:
            cur = await db.execute(
                "SELECT membership_status, community_moniker, rsi_handle FROM verification WHERE user_id=?",
                (member.id,),
            )
            row = await cur.fetchone()
            if row:
                status_db, moniker_db, handle_db = row
                # Map internal statuses to human terms for logs
                mapping = {
                    "main": "Main",
                    "affiliate": "Affiliate",
                    "non_member": "Not a Member",
                }
                status = mapping.get(status_db, status_db or "Not a Member")
                moniker = moniker_db
                handle = handle_db
    except Exception as e:
        logger.debug(f"Snapshot DB fetch failed for {member.id}: {e}")

    username = member.display_name or getattr(member, "name", None)
    roles = set()
    for r in getattr(member, "roles", []) or []:
        if not r:
            continue
        try:
            if getattr(r, "managed", False):
                continue
        except Exception:
            pass
        roles.add(getattr(r, "name", str(r)))
    return MemberSnapshot(
        status=status, moniker=moniker, handle=handle, username=username, roles=roles
    )


@dataclass
class MemberSnapshotDiff:
    status_before: str
    status_after: str
    moniker_before: str | None
    moniker_after: str | None
    handle_before: str | None
    handle_after: str | None
    username_before: str | None
    username_after: str | None
    roles_added: list[str]
    roles_removed: list[str]

    # Backwards‑compatibility helpers (dict-like access in existing callers)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def items(self) -> None:  # type: ignore[override]
        return self.to_dict().items()

    def get(self, key: str, default=None) -> None:
        return getattr(self, key, default)

    # Mapping compatibility for existing dict-style usage
    def __getitem__(self, key: str) -> None:  # pragma: no cover (thin wrapper)
        return getattr(self, key)

    def __setitem__(self, key: str, value) -> None:  # pragma: no cover
        setattr(self, key, value)

    def __contains__(self, key: str) -> None:  # pragma: no cover
        return hasattr(self, key)


def diff_snapshots(before: MemberSnapshot, after: MemberSnapshot) -> MemberSnapshotDiff:
    roles_added: list[str] = sorted(after.roles - before.roles)
    roles_removed: list[str] = sorted(before.roles - after.roles)
    return MemberSnapshotDiff(
        status_before=before.status,
        status_after=after.status,
        moniker_before=before.moniker,
        moniker_after=after.moniker,
        handle_before=before.handle,
        handle_after=after.handle,
        username_before=before.username,
        username_after=after.username,
        roles_added=roles_added,
        roles_removed=roles_removed,
    )


__all__ = [
    "MemberSnapshot",
    "MemberSnapshotDiff",
    "diff_snapshots",
    "snapshot_member_state",
]
