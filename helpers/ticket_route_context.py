"""In-progress ticket route session state.

Extracted from the legacy ``TicketFormService`` so the bot's dynamic form
view helpers can carry route state without importing the (now removed)
service monolith.  The backend persists sessions via
``TicketFormRepository``; the bot reconstructs this dataclass from the
connector's session dict when resuming a flow.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from helpers.constants import ROUTE_SESSION_TTL_SECONDS


@dataclass
class RouteExecutionContext:
    """State container for a user's in-progress ticket route flow.

    Persisted to ``ticket_route_sessions`` on every state change so the
    flow can survive bot restarts.

    AI Notes:
        ``collected_answers`` maps ``question_id`` →
        ``{"answer": str, "label": str, "step": int, "sort_order": int}``.
    """

    guild_id: int
    user_id: int
    category_id: int
    category: dict[str, Any] | None = None
    current_step: int = 1
    collected_answers: dict[str, dict[str, Any]] = field(default_factory=dict)
    session_id: int | None = None
    interaction_token: str | None = None
    is_public: bool = False
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(
        default_factory=lambda: time.time() + ROUTE_SESSION_TTL_SECONDS
    )

    def add_answers(
        self,
        step_number: int,
        answers: dict[str, dict[str, Any]],
    ) -> None:
        """Merge answers from a completed step into collected state."""
        for qid, data in answers.items():
            self.collected_answers[qid] = {
                **data,
                "step": step_number,
            }

    def is_expired(self) -> bool:
        """Return ``True`` if this session has passed its TTL."""
        return time.time() > self.expires_at

    def to_db_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for DB storage."""
        return {
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "current_step": self.current_step,
            "collected_data": json.dumps(self.collected_answers),
            "interaction_token": self.interaction_token,
            "is_public": 1 if self.is_public else 0,
            "created_at": int(self.created_at),
            "expires_at": int(self.expires_at),
        }

    @classmethod
    def from_db_row(cls, row: Any) -> RouteExecutionContext:
        """Reconstruct from a DB row (``aiosqlite.Row`` or tuple)."""
        collected = json.loads(row["collected_data"] or "{}")
        try:
            is_public_raw = row["is_public"]
        except (TypeError, KeyError, IndexError):
            is_public_raw = 0
        return cls(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            category_id=int(row["category_id"]),
            current_step=int(row["current_step"]),
            collected_answers=collected,
            session_id=int(row["id"]),
            interaction_token=row["interaction_token"],
            is_public=bool(is_public_raw),
            created_at=float(row["created_at"]),
            expires_at=float(row["expires_at"]),
        )
