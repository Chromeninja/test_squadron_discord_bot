"""
In-memory per-guild daily activity tracker.

Accumulates verification event counts by category so a single
daily leadership summary can be posted.  Counters are reset
atomically via :meth:`snapshot_and_reset` after each flush.

Categories tracked:
  • checked   – total users processed (all sources)
  • changed   – users whose profile/roles changed
  • first_time_manual – first-time verifications by a user
  • recheck   – user-initiated or auto rechecks
  • admin     – admin-triggered actions

Note: admin-triggered rechecks increment **both** ``admin`` and
``recheck`` so the daily summary reflects both perspectives.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _GuildCounters:
    checked: int = 0
    changed: int = 0
    first_time_manual: int = 0
    recheck: int = 0
    admin: int = 0


class DailyActivityTracker:
    """Thread-safe singleton that accumulates daily per-guild activity counts."""

    _instance: DailyActivityTracker | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._guilds: dict[int, _GuildCounters] = defaultdict(_GuildCounters)
        self._data_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------
    @classmethod
    def get(cls) -> DailyActivityTracker:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (mainly for testing)."""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------
    def record_check(self, guild_id: int, *, changed: bool = False) -> None:
        """Record one user check (auto or any source)."""
        with self._data_lock:
            c = self._guilds[guild_id]
            c.checked += 1
            if changed:
                c.changed += 1

    def record_first_time_manual(self, guild_id: int) -> None:
        """Record a first-time user-initiated verification."""
        with self._data_lock:
            self._guilds[guild_id].first_time_manual += 1

    def record_recheck(self, guild_id: int) -> None:
        """Record a user or auto recheck."""
        with self._data_lock:
            self._guilds[guild_id].recheck += 1

    def record_admin(self, guild_id: int) -> None:
        """Record an admin-triggered action."""
        with self._data_lock:
            self._guilds[guild_id].admin += 1

    # ------------------------------------------------------------------
    # Snapshot & reset
    # ------------------------------------------------------------------
    def snapshot_and_reset(self) -> dict[int, dict[str, int]]:
        """Atomically return current totals and reset all counters.

        Returns a plain dict keyed by guild_id with counter dicts:
            {guild_id: {"checked": N, "changed": N, ...}}
        Guilds with all-zero counters are omitted.
        """
        with self._data_lock:
            result: dict[int, dict[str, int]] = {}
            for gid, c in list(self._guilds.items()):
                totals = {
                    "checked": c.checked,
                    "changed": c.changed,
                    "first_time_manual": c.first_time_manual,
                    "recheck": c.recheck,
                    "admin": c.admin,
                }
                if any(v > 0 for v in totals.values()):
                    result[gid] = totals
            # Reset
            self._guilds.clear()
            return result

    def peek(self, guild_id: int) -> dict[str, int]:
        """Return current counters for a guild without resetting."""
        with self._data_lock:
            c = self._guilds.get(guild_id, _GuildCounters())
            return {
                "checked": c.checked,
                "changed": c.changed,
                "first_time_manual": c.first_time_manual,
                "recheck": c.recheck,
                "admin": c.admin,
            }
