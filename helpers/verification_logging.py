"""
Centralized logging and announcement helpers for verification flows.
"""

from __future__ import annotations

from typing import Any

from helpers.announcement import enqueue_announcement_for_guild
from helpers.leadership_log import (
    ChangeSet,
    EventType,
    InitiatorKind,
    InitiatorSource,
    post_if_changed,
)
from utils.logging import get_logger

logger = get_logger(__name__)


def _is_downgrade(old_status: str | None, new_status: str | None) -> bool:
    order = {"main": 3, "affiliate": 2, "non_member": 1, None: 0}
    return order.get(new_status, 0) < order.get(old_status, 0)


def _should_suppress(diff: dict, event: EventType, *, notes: str | None = None) -> bool:
    if not diff:
        return True

    # Never suppress events with explicit notes (e.g., "RSI 404")
    if notes:
        return False

    # Check for no-op scenarios (no actual changes)
    status_same = diff.get("status_before") == diff.get("status_after")
    orgs_same = diff.get("main_orgs_before") == diff.get("main_orgs_after") and diff.get(
        "affiliate_orgs_before"
    ) == diff.get("affiliate_orgs_after")
    roles_same = not diff.get("roles_added") and not diff.get("roles_removed")
    username_same = diff.get("username_before") == diff.get("username_after")

    # Suppress AUTO_CHECK events when nothing changed
    if event == EventType.AUTO_CHECK:
        if status_same and orgs_same and roles_same:
            return True

    # Suppress RECHECK events when truly nothing changed (including username)
    if event == EventType.RECHECK:
        if status_same and orgs_same and roles_same and username_same:
            return True

    return False


def _build_changeset(diff: dict, event: EventType, guild_id: int, initiator: dict[str, Any]) -> ChangeSet:
    cs = ChangeSet(
        user_id=int(initiator.get("user_id", 0)) if initiator.get("user_id") else 0,
        event=event,
        initiator_kind=initiator.get("kind", InitiatorKind.AUTO),
        initiator_source=initiator.get("source", InitiatorSource.SYSTEM),
        initiator_name=initiator.get("name"),
        guild_id=guild_id,
        notes=initiator.get("notes"),
    )
    for k, v in diff.items():
        setattr(cs, k, v)
    return cs


def _maybe_announce(sync_result, diff: dict, bot) -> None:
    old_status = diff.get("status_before")
    new_status = diff.get("status_after")
    try:
        # Delegate announcement decision to _classify_event (DRY, single source of truth)
        bot.loop.create_task(
            enqueue_announcement_for_guild(
                bot,
                sync_result.member,
                diff.get("main_orgs_after"),
                diff.get("affiliate_orgs_after"),
                diff.get("main_orgs_before"),
                diff.get("affiliate_orgs_before"),
            )
        )
        logger.info(
            "Announcement enqueue requested",
            extra={
                "user_id": sync_result.user_id,
                "guild_id": sync_result.guild_id,
                "old_status": old_status,
                "new_status": new_status,
            },
        )
    except Exception as e:
        logger.warning("Failed to queue public announcement: %s", e)


async def log_guild_sync(sync_result, event: EventType, bot, *, initiator: dict[str, Any] | None = None) -> None:
    """Post leadership log entry based on diff and event type."""
    diff = sync_result.diff
    initiator_info = initiator or {}
    notes = initiator_info.get("notes")
    if _should_suppress(diff, event, notes=notes):
        return

    initiator_info.setdefault("user_id", sync_result.user_id)
    cs = _build_changeset(diff, event, sync_result.guild_id, initiator_info)

    # Announcements for promotions only
    try:
        _maybe_announce(sync_result, diff, bot)
    except Exception:
        logger.debug("Announcement enqueue failed", exc_info=True)

    try:
        await post_if_changed(bot, cs)
    except Exception:
        logger.debug("Leadership log post failed", exc_info=True)


async def log_transition_if_needed(sync_result, bot, event: EventType) -> None:
    """Helper to log downgrades or org changes consistently."""
    diff = sync_result.diff
    if _should_suppress(diff, event):
        return
    if (
        _is_downgrade(diff.get("status_before"), diff.get("status_after"))
        or diff.get("main_orgs_before") != diff.get("main_orgs_after")
        or diff.get("affiliate_orgs_before") != diff.get("affiliate_orgs_after")
    ):
        await log_guild_sync(sync_result, event, bot)
