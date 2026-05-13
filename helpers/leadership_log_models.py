"""
Leadership Log Data Models — enums and ChangeSet dataclass.

Extracted from helpers/leadership_log.py to keep file sizes manageable.
Import from helpers.leadership_log for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class EventType(str, Enum):
    VERIFICATION = "VERIFICATION"  # User initial verification ("User Verify")
    RECHECK = "RECHECK"  # User initiated re-check via button
    AUTO_CHECK = "AUTO_CHECK"  # Scheduled automatic re-check
    ADMIN_ACTION = "ADMIN_ACTION"  # Admin initiated action (check, role grant, etc)
    # Backward compatibility alias for persisted data using the old name
    ADMIN_CHECK = "ADMIN_CHECK"  # @deprecated: use ADMIN_ACTION for new code


class InitiatorKind(str, Enum):
    USER = "User"
    ADMIN = "Admin"
    AUTO = "Auto"


class InitiatorSource(str, Enum):
    COMMAND = "command"
    WEB = "web"
    BULK = "bulk"
    VOICE = "voice"
    BUTTON = "button"
    AUTO = "auto"
    SYSTEM = "system"


VALID_COMBINATIONS: dict[EventType, set[InitiatorKind]] = {
    EventType.VERIFICATION: {InitiatorKind.USER},
    EventType.RECHECK: {InitiatorKind.USER, InitiatorKind.ADMIN, InitiatorKind.AUTO},
    EventType.AUTO_CHECK: {InitiatorKind.AUTO},
    EventType.ADMIN_ACTION: {InitiatorKind.ADMIN},
    EventType.ADMIN_CHECK: {InitiatorKind.ADMIN},  # Backward compatibility
}


@dataclass
class ChangeSet:
    user_id: int
    event: EventType
    initiator_kind: InitiatorKind | str
    initiator_name: str | None = None
    initiator_source: InitiatorSource | str | None = None
    guild_id: int | None = None  # Guild where the event occurred

    status_before: str | None = None
    status_after: str | None = None
    moniker_before: str | None = None
    moniker_after: str | None = None
    handle_before: str | None = None
    handle_after: str | None = None
    username_before: str | None = None
    username_after: str | None = None

    # Organization changes
    main_orgs_before: list[str] | None = None
    main_orgs_after: list[str] | None = None
    affiliate_orgs_before: list[str] | None = None
    affiliate_orgs_after: list[str] | None = None

    roles_added: list[str] = field(default_factory=list)
    roles_removed: list[str] = field(default_factory=list)

    notes: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = 0

    def __post_init__(self):
        if isinstance(self.event, str):
            try:
                self.event = EventType(self.event)
            except ValueError:
                # Unknown event string; keep raw but avoid attribute errors
                pass
        if isinstance(self.initiator_kind, str):
            self.initiator_kind = InitiatorKind(self.initiator_kind)
        if self.initiator_source and isinstance(self.initiator_source, str):
            try:
                self.initiator_source = InitiatorSource(self.initiator_source)
            except ValueError:
                # Allow passthrough of unknown custom sources without failing init
                pass

        valid_kinds = VALID_COMBINATIONS.get(self.event, set())
        if valid_kinds and self.initiator_kind not in valid_kinds:
            raise ValueError(
                f"Invalid ChangeSet combination: event={self.event.value} "
                f"initiator={self.initiator_kind.value}"
            )
