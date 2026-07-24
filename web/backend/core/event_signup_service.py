"""EventSignupService — web signup, role, roster, and messaging orchestration.

This is the authoritative service for all dashboard-driven event signup logic.
It enforces every server-side rule (event visibility, signup open/closed,
capacity, locked roles, single-vs-multiple role signups) so routes stay thin and
security cannot be bypassed from the frontend or by crafting API calls.

Permission gating (who may call what) is handled by the route dependencies; the
``is_coordinator`` flag passed into write methods only controls *rule bypasses*
for legitimate coordinator management actions (manual assignment, etc.).

Discord-native RSVP counts (``user_count`` on the event) are intentionally kept
separate from web signups and are never merged.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, TypedDict

from backend.db.repository.event_role_signups import EventRoleSignupRepository
from backend.db.repository.event_roles import EventRoleRepository
from backend.db.repository.event_signups import EventSignupRepository
from backend.db.repository.events import invalidate_events_cache, is_active_event
from services.db.database import Database

if TYPE_CHECKING:
    from backend.db.repository.types import (
        EventRoleSignupRecord,
        ManagedEventRecord,
    )

    from .internal_api_client import InternalAPIClient

logger = logging.getLogger(__name__)

# Marker delimiting the bot-managed signup summary appended to event descriptions.
SIGNUP_SUMMARY_MARKER = "--- TEST Event Signups ---"

# Short-TTL per-guild cache of signup counts grouped by event, paired with the
# events-list cache in backend/db/repository/events.py so the event list
# endpoint costs ~zero DB work at steady state. Invalidated on every signup
# write in this process (all writes funnel through _refresh_event_description);
# a few seconds of count staleness is acceptable and self-heals.
_SIGNUP_COUNTS_TTL_SECONDS = 5.0
_signup_counts_cache: dict[int, tuple[float, dict[int, int]]] = {}


class SignupState(TypedDict):
    """Stable service contract for a member's whole-event signup state."""

    event_id: int
    signed_up: bool
    web_signup_count: int


class EventRoleView(TypedDict):
    """Role state exposed by the signup service."""

    id: int
    event_id: int
    name: str
    emoji: str | None
    description: str | None
    capacity: int | None
    sort_order: int
    locked: bool
    signup_count: int
    current_user_signed_up: bool


class EventRolesState(TypedDict):
    """Stable service contract for role-list responses."""

    roles: list[EventRoleView]
    allow_multiple_roles: bool
    signups_enabled: bool
    signups_closed: bool


class EventRosterUserState(TypedDict):
    """Member entry in a coordinator roster."""

    user_id: str
    display_name: str | None
    created_at: int | None


class EventRosterRoleState(TypedDict):
    """Role entry in a coordinator roster."""

    role_id: int
    name: str
    emoji: str | None
    capacity: int | None
    locked: bool
    users: list[EventRosterUserState]


class EventRosterState(TypedDict):
    """Stable service contract for coordinator roster responses."""

    event_id: int
    total_web_signups: int
    no_role_users: list[EventRosterUserState]
    roles: list[EventRosterRoleState]
    discord_user_count: int


def _invalidate_signup_caches(guild_id: int) -> None:
    """Drop cached signup counts (and the events list) after a signup write."""
    _signup_counts_cache.pop(guild_id, None)
    invalidate_events_cache(guild_id)


class SignupError(Exception):
    """Domain error carrying an HTTP status code for the route layer to surface."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class EventSignupService:
    """Encapsulates all event signup, role, roster, and summary operations."""

    def __init__(self) -> None:
        self.signups = EventSignupRepository()
        self.roles = EventRoleRepository()
        self.role_signups = EventRoleSignupRepository()

    # ------------------------------------------------------------------
    # Event loading / visibility
    # ------------------------------------------------------------------
    async def load_event(
        self, guild_id: int, event_id: int, *, is_coordinator: bool
    ) -> ManagedEventRecord:
        """Return a non-deleted event, enforcing visibility for regular users.

        Regular users (non-coordinator) may only ever load active/upcoming/
        recurring events — past events raise 404 so they cannot be probed.
        Coordinators (and bot owners) may load any non-deleted event.
        """
        event = await Database.get_managed_event(guild_id, event_id)
        if event is None:
            raise SignupError(404, "Event not found")
        if not is_coordinator and not is_active_event(event):
            # TODO(channel-visibility): also hide events whose attached Discord
            # channel this user cannot view once channel-permission filtering
            # lands. user_id/guild context is available at the call sites.
            raise SignupError(404, "Event not found")
        return event

    @staticmethod
    def _require_signups_open(event: ManagedEventRecord) -> None:
        """Raise if signups are disabled or closed for regular users."""
        if not event.get("signups_enabled"):
            raise SignupError(403, "Signups are not enabled for this event")
        if event.get("signups_closed"):
            raise SignupError(403, "Signups are closed for this event")

    # ------------------------------------------------------------------
    # Whole-event interest
    # ------------------------------------------------------------------
    async def mark_interest(
        self, guild_id: int, event_id: int, user_id: str, *, is_coordinator: bool
    ) -> SignupState:
        """Mark whole-event interest. 409 if already interested."""
        event = await self.load_event(guild_id, event_id, is_coordinator=is_coordinator)
        if not is_coordinator:
            self._require_signups_open(event)

        created = await self.signups.create_signup(
            guild_id, event_id, user_id, created_by_user_id=user_id
        )
        if created is None:
            raise SignupError(409, "Already interested in this event")

        await self._refresh_event_description(guild_id, event_id)
        return await self.get_signup_state(guild_id, event_id, user_id)

    async def withdraw_interest(
        self, guild_id: int, event_id: int, user_id: str, *, is_coordinator: bool
    ) -> SignupState:
        """Withdraw interest (hard delete) and drop all of the user's role signups."""
        await self.load_event(guild_id, event_id, is_coordinator=is_coordinator)
        await self.role_signups.delete_all_for_user_event(guild_id, event_id, user_id)
        await self.signups.delete_signup(guild_id, event_id, user_id)
        await self._refresh_event_description(guild_id, event_id)
        return await self.get_signup_state(guild_id, event_id, user_id)

    async def get_signup_state(
        self, guild_id: int, event_id: int, user_id: str
    ) -> SignupState:
        """Return current-user whole-event signup state and total count."""
        signup = await self.signups.get_signup(guild_id, event_id, user_id)
        count = await self.signups.count_signups(guild_id, event_id)
        return {
            "event_id": event_id,
            "signed_up": signup is not None,
            "web_signup_count": count,
        }

    # ------------------------------------------------------------------
    # Roles (read state)
    # ------------------------------------------------------------------
    async def list_roles_with_state(
        self, guild_id: int, event_id: int, user_id: str, *, is_coordinator: bool
    ) -> EventRolesState:
        """Return roles for an event with counts and the current user's selections."""
        event = await self.load_event(guild_id, event_id, is_coordinator=is_coordinator)
        roles = await self.roles.list_roles(guild_id, event_id)
        user_role_ids = {
            rs["role_id"]
            for rs in await self.role_signups.list_role_signups(guild_id, event_id)
            if rs["user_id"] == user_id
        }

        role_views: list[EventRoleView] = []
        for role in roles:
            rid = role["id"]
            role_views.append(
                {
                    "id": rid,
                    "event_id": event_id,
                    "name": role["name"],
                    "emoji": role["emoji"],
                    "description": role["description"],
                    "capacity": role["capacity"],
                    "sort_order": role["sort_order"],
                    "locked": role["locked"],
                    "signup_count": await self.role_signups.count_for_role(
                        guild_id, rid
                    ),
                    "current_user_signed_up": rid in user_role_ids,
                }
            )

        return {
            "roles": role_views,
            "allow_multiple_roles": bool(event.get("allow_multiple_roles")),
            "signups_enabled": bool(event.get("signups_enabled")),
            "signups_closed": bool(event.get("signups_closed")),
        }

    # ------------------------------------------------------------------
    # Role signups (write)
    # ------------------------------------------------------------------
    async def sign_up_for_role(
        self,
        guild_id: int,
        event_id: int,
        role_id: int,
        user_id: str,
        *,
        is_coordinator: bool,
        acting_user_id: str | None = None,
    ) -> None:
        """Add a user to a role, enforcing all server-side rules.

        Coordinators bypass locked / multiple-role / capacity rules so they can
        manually manage rosters; regular users are fully constrained.
        """
        event = await self.load_event(guild_id, event_id, is_coordinator=is_coordinator)
        role = await self.roles.get_role(guild_id, role_id)
        if role is None or role["event_id"] != event_id:
            raise SignupError(404, "Role not found for this event")

        if not is_coordinator:
            self._require_signups_open(event)
            if role["locked"]:
                raise SignupError(403, "This role is locked")
            if not event.get("allow_multiple_roles"):
                existing = await self.role_signups.user_role_count_for_event(
                    guild_id, event_id, user_id
                )
                already_in_role = (
                    await self.role_signups.get_role_signup(guild_id, role_id, user_id)
                    is not None
                )
                if existing > 0 and not already_in_role:
                    raise SignupError(
                        409, "Only one role signup is allowed for this event"
                    )

        # Capacity is enforced atomically inside the INSERT so concurrent
        # signups cannot oversubscribe a role; coordinators bypass the limit.
        capacity = None if is_coordinator else role["capacity"]
        created = await self.role_signups.create_role_signup(
            guild_id,
            event_id,
            role_id,
            user_id,
            created_by_user_id=acting_user_id or user_id,
            capacity=capacity,
        )
        if created is None:
            duplicate = await self.role_signups.get_role_signup(
                guild_id, role_id, user_id
            )
            if duplicate is not None:
                raise SignupError(409, "Already signed up for this role")
            raise SignupError(409, "This role is full")

        # A role signup implies whole-event interest; ensure the row exists.
        await self.signups.create_signup(
            guild_id, event_id, user_id, created_by_user_id=acting_user_id or user_id
        )
        await self._refresh_event_description(guild_id, event_id)

    async def withdraw_from_role(
        self,
        guild_id: int,
        event_id: int,
        role_id: int,
        user_id: str,
        *,
        is_coordinator: bool,
    ) -> None:
        """Remove a user from a single role (hard delete)."""
        await self.load_event(guild_id, event_id, is_coordinator=is_coordinator)
        removed = await self.role_signups.delete_role_signup(guild_id, role_id, user_id)
        if not removed:
            raise SignupError(404, "Role signup not found")
        await self._refresh_event_description(guild_id, event_id)

    async def remove_user_from_event(
        self, guild_id: int, event_id: int, user_id: str
    ) -> None:
        """Coordinator action: remove a user's interest and all their role signups."""
        await self.load_event(guild_id, event_id, is_coordinator=True)
        await self.role_signups.delete_all_for_user_event(guild_id, event_id, user_id)
        await self.signups.delete_signup(guild_id, event_id, user_id)
        await self._refresh_event_description(guild_id, event_id)

    # ------------------------------------------------------------------
    # Attaching signup state to event summaries (list/detail views)
    # ------------------------------------------------------------------
    async def attach_signup_state(
        self,
        guild_id: int,
        events: list[ManagedEventRecord],
        user_id: str,
    ) -> list[ManagedEventRecord]:
        """Augment each event dict with web signup count and current-user state.

        Uses two guild-wide batched queries (counts grouped by event, plus the
        user's own signups) so the event list endpoint costs a constant number
        of queries no matter how many events a guild has — this is the hottest
        read path in the dashboard.
        """
        if not events:
            return events
        now = time.monotonic()
        cached = _signup_counts_cache.get(guild_id)
        if cached is not None and now - cached[0] < _SIGNUP_COUNTS_TTL_SECONDS:
            counts = cached[1]
        else:
            counts = await self.signups.count_signups_by_event(guild_id)
            _signup_counts_cache[guild_id] = (now, counts)
        user_signups = await self.signups.list_signups_for_user(guild_id, user_id)
        for event in events:
            try:
                event_id = int(str(event.get("id")))
            except (TypeError, ValueError):
                continue
            signup = user_signups.get(event_id)
            event["web_signup_count"] = counts.get(event_id, 0)
            event["current_user_signed_up"] = signup is not None
            event["current_user_signup_id"] = (
                int(str(signup["id"])) if signup is not None else None
            )
        return events

    # ------------------------------------------------------------------
    # Coordinator roster
    # ------------------------------------------------------------------
    async def get_roster(
        self,
        guild_id: int,
        event_id: int,
        internal_api: InternalAPIClient | None = None,
    ) -> EventRosterState:
        """Build the full coordinator roster (web signups + Discord RSVP count)."""
        event = await self.load_event(guild_id, event_id, is_coordinator=True)

        signups = await self.signups.list_signups(guild_id, event_id)
        role_rows = await self.roles.list_roles(guild_id, event_id)
        role_signups = await self.role_signups.list_role_signups(guild_id, event_id)

        # Resolve display names best-effort; never fail the roster on lookup error.
        name_cache: dict[str, str | None] = {}

        async def _name(uid: str) -> str | None:
            if uid in name_cache:
                return name_cache[uid]
            resolved: str | None = None
            if internal_api is not None:
                try:
                    member = await internal_api.get_guild_member(guild_id, int(uid))
                    resolved = member.get("global_name") or member.get("username")
                except Exception:  # pragma: no cover - best-effort enrichment
                    resolved = None
            name_cache[uid] = resolved
            return resolved

        users_in_roles = {rs["user_id"] for rs in role_signups}

        no_role_users: list[EventRosterUserState] = []
        for s in signups:
            uid = s["user_id"]
            if uid in users_in_roles:
                continue
            no_role_users.append(
                {
                    "user_id": uid,
                    "display_name": await _name(uid),
                    "created_at": s["created_at"],
                }
            )

        signups_by_role: dict[int, list[EventRoleSignupRecord]] = {}
        for rs in role_signups:
            signups_by_role.setdefault(rs["role_id"], []).append(rs)

        roles_out: list[EventRosterRoleState] = []
        for role in role_rows:
            rid = role["id"]
            members: list[EventRosterUserState] = []
            for rs in signups_by_role.get(rid, []):
                uid = rs["user_id"]
                members.append(
                    {
                        "user_id": uid,
                        "display_name": await _name(uid),
                        "created_at": rs["created_at"],
                    }
                )
            roles_out.append(
                {
                    "role_id": rid,
                    "name": role["name"],
                    "emoji": role["emoji"],
                    "capacity": role["capacity"],
                    "locked": role["locked"],
                    "users": members,
                }
            )

        discord_user_count = event["user_count"]

        return {
            "event_id": event_id,
            "total_web_signups": len(signups),
            "no_role_users": no_role_users,
            "roles": roles_out,
            "discord_user_count": discord_user_count,
        }

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------
    async def build_csv(self, guild_id: int, event_id: int) -> str:
        """Return CSV text for an event's web signups (source=web)."""
        import csv
        import io

        event = await self.load_event(guild_id, event_id, is_coordinator=True)
        event_name = str(event.get("name") or "")

        signups = await self.signups.list_signups(guild_id, event_id)
        role_rows = {
            r["id"]: r for r in await self.roles.list_roles(guild_id, event_id)
        }
        role_signups = await self.role_signups.list_role_signups(guild_id, event_id)

        roles_by_user: dict[str, list[int]] = {}
        for rs in role_signups:
            roles_by_user.setdefault(rs["user_id"], []).append(rs["role_id"])

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "guild_id",
                "event_id",
                "event_name",
                "user_id",
                "signup_created_at",
                "selected_roles",
                "role_capacities",
                "source",
            ]
        )
        for s in signups:
            uid = str(s["user_id"])
            role_ids = roles_by_user.get(uid, [])
            role_names = "; ".join(
                str(role_rows[rid]["name"]) for rid in role_ids if rid in role_rows
            )
            role_caps = "; ".join(
                f"{role_rows[rid]['name']}:{role_rows[rid]['capacity']}"
                for rid in role_ids
                if rid in role_rows and role_rows[rid]["capacity"] is not None
            )
            writer.writerow(
                [
                    guild_id,
                    event_id,
                    event_name,
                    uid,
                    s["created_at"],
                    role_names,
                    role_caps,
                    "web",
                ]
            )
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Messaging target resolution
    # ------------------------------------------------------------------
    async def resolve_message_targets(
        self,
        guild_id: int,
        event_id: int,
        target: str,
        role_id: int | None,
    ) -> list[str]:
        """Return the list of user IDs for a coordinator message target segment."""
        await self.load_event(guild_id, event_id, is_coordinator=True)
        role_signups = await self.role_signups.list_role_signups(guild_id, event_id)
        users_in_roles = {str(rs["user_id"]) for rs in role_signups}

        if target == "all":
            return [
                str(s["user_id"])
                for s in await self.signups.list_signups(guild_id, event_id)
            ]
        if target == "no_role":
            return [
                str(s["user_id"])
                for s in await self.signups.list_signups(guild_id, event_id)
                if str(s["user_id"]) not in users_in_roles
            ]
        if target == "all_roles":
            return sorted(users_in_roles)
        if target == "role":
            if role_id is None:
                raise SignupError(400, "role_id is required for role target")
            return [
                str(rs["user_id"])
                for rs in role_signups
                if rs["role_id"] == role_id
            ]
        raise SignupError(400, "Unknown message target")

    # ------------------------------------------------------------------
    # Discord description summary
    # ------------------------------------------------------------------
    async def build_summary_block(self, guild_id: int, event_id: int) -> str:
        """Build the bot-managed signup summary block for an event description."""
        interested = await self.signups.count_signups(guild_id, event_id)
        roles = await self.roles.list_roles(guild_id, event_id)
        lines = [SIGNUP_SUMMARY_MARKER, f"Interested: {interested}"]
        if roles:
            lines.append("Roles:")
            for role in roles:
                rid = role["id"]
                count = await self.role_signups.count_for_role(guild_id, rid)
                emoji = f"{role['emoji']} " if role.get("emoji") else ""
                capacity = role["capacity"]
                fill = f"{count}/{capacity}" if capacity is not None else str(count)
                lines.append(f"{emoji}{role['name']}: {fill}")
        return "\n".join(lines)

    async def refresh_event_summary(self, guild_id: int, event_id: int) -> None:
        """Public wrapper to rebuild the managed signup summary for an event."""
        await self._refresh_event_description(guild_id, event_id)

    @staticmethod
    def _strip_summary_block(description: str | None) -> str:
        """Remove any existing managed summary block from a description."""
        if not description:
            return ""
        idx = description.find(SIGNUP_SUMMARY_MARKER)
        if idx == -1:
            return description.rstrip()
        return description[:idx].rstrip()

    async def _refresh_event_description(self, guild_id: int, event_id: int) -> None:
        """Rebuild the event description with an updated managed summary block.

        Conservative Discord sync: we only update the DB description and mark the
        event ``sync_status='pending'`` so the bot's existing projection loop
        pushes the change. The original briefing is preserved; the managed block
        is replaced (never duplicated) on each update.

        TODO(discord-description): if Discord later supports targeted partial
        updates to a scheduled event description without a full event replace,
        push the summary directly here. For now we rely on the pending-sync loop.
        """
        # Every signup mutation funnels through here, making it the single
        # invalidation point for the signup-count and events-list caches.
        _invalidate_signup_caches(guild_id)
        try:
            event = await Database.get_managed_event(guild_id, event_id)
            if event is None:
                return
            description = event.get("description")
            base = self._strip_summary_block(
                description if isinstance(description, str) else ""
            )
            block = await self.build_summary_block(guild_id, event_id)
            new_description = f"{base}\n\n{block}".strip() if base else block

            async with Database.get_connection() as db:
                await db.execute(
                    """
                    UPDATE managed_events
                    SET description = ?, sync_status = 'pending', updated_at = ?
                    WHERE guild_id = ? AND id = ? AND deleted_at IS NULL
                    """,
                    (new_description, int(time.time()), guild_id, event_id),
                )
                await db.commit()
        except Exception as exc:  # pragma: no cover - best-effort summary update
            logger.warning(
                "Failed to refresh signup summary for event %s in guild %s: %s",
                event_id,
                guild_id,
                exc,
            )


def get_event_signup_service() -> EventSignupService:
    """Dependency provider for EventSignupService."""
    return EventSignupService()
