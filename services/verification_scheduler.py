"""
Global scheduler utilities for verification rechecks.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Any

from services.db.database import Database
from utils.logging import get_logger

if TYPE_CHECKING:
    from services.verification_state import GlobalVerificationState

logger = get_logger(__name__)


def _get_cadence_days(config: dict[str, Any] | None, status: str) -> int:
    cfg = (config or {}).get("auto_recheck", {}) if isinstance(config, dict) else {}
    cadence = cfg.get("cadence_days", {}) or {}
    default_map = {"main": 14, "affiliate": 7, "non_member": 3}
    return int(cadence.get(status, default_map.get(status, 7)))


def _get_jitter(config: dict[str, Any] | None) -> int:
    cfg = (config or {}).get("auto_recheck", {}) if isinstance(config, dict) else {}
    jitter_h = int(cfg.get("jitter_hours", 0))
    if jitter_h <= 0:
        return 0
    return random.randint(-jitter_h * 3600, jitter_h * 3600)


def _compute_backoff_seconds(config: dict[str, Any] | None, fail_count: int) -> int:
    cfg = (config or {}).get("auto_recheck", {}) if isinstance(config, dict) else {}
    backoff = cfg.get("backoff", {}) or {}
    base = int(backoff.get("base_minutes", 180)) * 60
    max_s = int(backoff.get("max_minutes", 1440)) * 60
    jitter = random.randint(0, 600)
    exp = base * (2 ** max(0, fail_count - 1))
    return min(exp + jitter, max_s)


def compute_next_retry(
    global_state: GlobalVerificationState,
    *,
    fail_count: int = 0,
    config: dict[str, Any] | None = None,
) -> int:
    """Compute the next retry timestamp using cadence or backoff."""
    now = int(time.time())
    if fail_count > 0 or global_state.error:
        return now + _compute_backoff_seconds(config, max(1, fail_count))

    status = global_state.status
    days = _get_cadence_days(config, status)
    jitter = _get_jitter(config)
    return now + days * 86400 + jitter


async def schedule_user_recheck(user_id: int, next_retry: int) -> None:
    await Database.upsert_auto_recheck_success(
        user_id=user_id,
        next_retry_at=next_retry,
        now=int(time.time()),
        new_fail_count=0,
    )


async def handle_recheck_failure(
    user_id: int,
    error: str,
    *,
    fail_count: int,
    config: dict[str, Any] | None = None,
) -> None:
    """Persist failure with backoff scheduling."""
    now = int(time.time())
    next_retry = now + _compute_backoff_seconds(config, max(1, fail_count))
    await Database.upsert_auto_recheck_failure(
        user_id=user_id,
        next_retry_at=next_retry,
        now=now,
        error_msg=error,
        inc=False,
    )
