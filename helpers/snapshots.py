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
    main_orgs: list[str] | None = None  # Main organization SIDs
    affiliate_orgs: list[str] | None = None  # Affiliate organization SIDs


async def snapshot_member_state(bot, member: discord.Member) -> MemberSnapshot:
    # Fetch DB state
    status = "non_member"
    moniker = None
    handle = None
    main_orgs = None
    affiliate_orgs = None
    try:
        import json

        from services.db.database import derive_membership_status

        async with Database.get_connection() as db:
            cur = await db.execute(
                "SELECT community_moniker, rsi_handle, main_orgs, affiliate_orgs FROM verification WHERE user_id=?",
                (member.id,),
            )
            row = await cur.fetchone()
            if row:
                moniker_db, handle_db, main_orgs_json, affiliate_orgs_json = row
                moniker = moniker_db
                handle = handle_db
                # Parse JSON org lists
                main_orgs = json.loads(main_orgs_json) if main_orgs_json else None
                affiliate_orgs = (
                    json.loads(affiliate_orgs_json) if affiliate_orgs_json else None
                )

                # Derive status from org lists for this guild
                if (
                    hasattr(bot, "services")
                    and bot.services
                    and hasattr(bot.services, "guild_config")
                ):
                    try:
                        guild_org_sid = await bot.services.guild_config.get_setting(
                            member.guild.id, "organization.sid", default="TEST"
                        )
                        # Remove JSON quotes if present
                        if isinstance(guild_org_sid, str) and guild_org_sid.startswith(
                            '"'
                        ):
                            guild_org_sid = guild_org_sid.strip('"')
                        status = derive_membership_status(
                            main_orgs, affiliate_orgs, guild_org_sid
                        )
                    except Exception as e:
                        logger.debug(
                            f"Failed to get guild org SID for status derivation: {e}"
                        )
                        status = derive_membership_status(
                            main_orgs, affiliate_orgs, "TEST"
                        )
                else:
                    # Fallback to TEST if services not available
                    status = derive_membership_status(main_orgs, affiliate_orgs, "TEST")
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
        status=status,
        moniker=moniker,
        handle=handle,
        username=username,
        roles=roles,
        main_orgs=main_orgs,
        affiliate_orgs=affiliate_orgs,
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
    main_orgs_before: list[str] | None = None
    main_orgs_after: list[str] | None = None
    affiliate_orgs_before: list[str] | None = None
    affiliate_orgs_after: list[str] | None = None

    # Backwards‑compatibility helpers (dict-like access in existing callers)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def items(self):
        return self.to_dict().items()

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    # Mapping compatibility for existing dict-style usage
    def __getitem__(self, key: str) -> Any:  # pragma: no cover (thin wrapper)
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:  # pragma: no cover
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:  # pragma: no cover
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
        main_orgs_before=before.main_orgs,
        main_orgs_after=after.main_orgs,
        affiliate_orgs_before=before.affiliate_orgs,
        affiliate_orgs_after=after.affiliate_orgs,
    )


__all__ = [
    "MemberSnapshot",
    "MemberSnapshotDiff",
    "diff_snapshots",
    "snapshot_member_state",
]
