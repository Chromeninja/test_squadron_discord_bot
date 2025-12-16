"""
Global verification state computation and caching.

Provides a single entry point for fetching RSI verification data per user with
rate limiting, short-term caching, and error backoff support. All verification
flows (auto, manual, bulk) should call `compute_global_state` to avoid duplicate
RSI fetches and to share throttling safeguards.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

from helpers.http_helper import HTTPClient, NotFoundError
from utils.logging import get_logger
from verification.rsi_verification import is_valid_rsi_handle

logger = get_logger(__name__)

VerificationStatus = Literal["main", "affiliate", "non_member"]


@dataclass
class GlobalVerificationState:
    user_id: int
    rsi_handle: str
    status: VerificationStatus
    main_orgs: list[str]
    affiliate_orgs: list[str]
    community_moniker: str | None
    checked_at: int
    error: str | None = None


# In-process cache: {(user_id, handle_lower): (expires_at, GlobalVerificationState)}
_cache: dict[tuple[int, str], tuple[float, GlobalVerificationState]] = {}
_cache_lock = asyncio.Lock()

# Simple concurrency + pacing controls for RSI fetches
_rsi_semaphore: asyncio.Semaphore | None = None
_last_rsi_request_at: float = 0.0


def _get_limits(config: dict[str, Any] | None) -> dict[str, Any]:
    """Extract rate limit settings with safe defaults."""
    rsi_cfg = (config or {}).get("rsi", {}) if isinstance(config, dict) else {}
    return {
        "cache_ttl": int(rsi_cfg.get("cache_ttl_seconds", 300)),
        "max_concurrency": int(rsi_cfg.get("max_concurrent_requests", 3)),
        "min_interval": float(rsi_cfg.get("min_interval_seconds", 0.5)),
        "backoff_base": int(rsi_cfg.get("backoff_base_seconds", 60)),
        "backoff_max": int(rsi_cfg.get("backoff_max_seconds", 3600)),
    }


async def _maybe_init_semaphore(max_concurrency: int) -> asyncio.Semaphore:
    global _rsi_semaphore
    if _rsi_semaphore is None:
        _rsi_semaphore = asyncio.Semaphore(max(1, max_concurrency))
    return _rsi_semaphore


async def _throttled_fetch(fetch_coro, *, min_interval: float, semaphore: asyncio.Semaphore):
    """Throttle RSI requests with concurrency and pacing controls."""
    global _last_rsi_request_at
    async with semaphore:
        # Enforce minimum spacing between outbound requests
        now = time.monotonic()
        sleep_for = _last_rsi_request_at + min_interval - now
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
        try:
            return await fetch_coro
        finally:
            _last_rsi_request_at = time.monotonic()


async def compute_global_state(
    user_id: int,
    rsi_handle: str,
    http_client: HTTPClient,
    *,
    config: dict[str, Any] | None = None,
    org_name: str | None = None,
    force_refresh: bool = False,
) -> GlobalVerificationState:
    """
    Fetch the global verification state for a user with caching and throttling.

    Args:
        user_id: Discord user ID.
        rsi_handle: RSI handle provided by the user or stored in DB.
        http_client: Shared HTTP client with connection pooling.
        config: Optional bot config for rate limit settings.
        org_name: Optional org name fallback for RSI parsing (default "test").
        force_refresh: Bypass cache when True.

    Returns:
        GlobalVerificationState with error populated on failure instead of raising
        (except for 404 NotFound, which is propagated so callers can remediate).
    """
    if not rsi_handle or not rsi_handle.strip():
        logger.warning(
            "RSI handle missing for user %s; user must verify before recheck",
            user_id,
        )
        return GlobalVerificationState(
            user_id=user_id,
            rsi_handle="",
            status="non_member",
            main_orgs=[],
            affiliate_orgs=[],
            community_moniker=None,
            checked_at=int(time.time()),
            error="User is not verified yet. Please complete verification first.",
        )

    limits = _get_limits(config)
    cache_ttl = limits["cache_ttl"]
    key = (int(user_id), rsi_handle.lower())

    # Cache check
    if not force_refresh:
        async with _cache_lock:
            cached = _cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]

    semaphore = await _maybe_init_semaphore(limits["max_concurrency"])

    async def _do_fetch():
        return await is_valid_rsi_handle(
            rsi_handle,
            http_client,
            (org_name or "test"),
            None,
        )

    try:
        result = await _throttled_fetch(
            _do_fetch(),
            min_interval=limits["min_interval"],
            semaphore=semaphore,
        )
    except NotFoundError:
        raise
    except Exception as e:  # Transient/unknown errors captured as error state
        logger.warning(
            "RSI fetch failed for handle %s: %s", rsi_handle, e, exc_info=True
        )
        return GlobalVerificationState(
            user_id=user_id,
            rsi_handle=rsi_handle,
            status="non_member",
            main_orgs=[],
            affiliate_orgs=[],
            community_moniker=None,
            checked_at=int(time.time()),
            error=str(e),
        )

    (
        verify_value,
        cased_handle,
        community_moniker,
        main_orgs,
        affiliate_orgs,
    ) = result

    # verify_value None indicates transient parse/fetch failure
    if verify_value is None or cased_handle is None:
        logger.warning(
            "RSI fetch/parse failure for handle %s (verify_value=%s, cased_handle=%s, force_refresh=%s, main_orgs=%s, affiliate_orgs=%s)",
            rsi_handle,
            verify_value,
            cased_handle,
            force_refresh,
            main_orgs,
            affiliate_orgs,
        )
        return GlobalVerificationState(
            user_id=user_id,
            rsi_handle=rsi_handle,
            status="non_member",
            main_orgs=main_orgs or [],
            affiliate_orgs=affiliate_orgs or [],
            community_moniker=community_moniker,
            checked_at=int(time.time()),
            error="RSI fetch/parse failure — please complete verification again",
        )

    # Filter out REDACTED entries for status computation
    # (REDACTED orgs are unknown to the bot, so treat as non_member)
    non_redacted_main = [s for s in (main_orgs or []) if s != "REDACTED"]
    non_redacted_affiliate = [s for s in (affiliate_orgs or []) if s != "REDACTED"]

    status: VerificationStatus
    if non_redacted_main:
        status = "main"
    elif non_redacted_affiliate:
        status = "affiliate"
    else:
        status = "non_member"

    state = GlobalVerificationState(
        user_id=user_id,
        rsi_handle=cased_handle,
        status=status,
        main_orgs=main_orgs or [],
        affiliate_orgs=affiliate_orgs or [],
        community_moniker=community_moniker,
        checked_at=int(time.time()),
        error=None,
    )

    # Update cache
    async with _cache_lock:
        _cache[key] = (time.monotonic() + cache_ttl, state)

    return state


async def store_global_state(state: GlobalVerificationState) -> None:
    """Persist global verification state to the database."""
    from services.db.database import Database

    conflict = await Database.check_rsi_handle_conflict(state.rsi_handle, state.user_id)
    if conflict:
        raise ValueError(
            f"RSI handle '{state.rsi_handle}' is already verified by another user: {conflict}"
        )

    # Log what we're about to persist for observability
    from utils.logging import get_logger
    _logger = get_logger(__name__)
    _logger.info(
        "Persisting verification state",
        extra={
            "user_id": state.user_id,
            "rsi_handle": state.rsi_handle,
            "main_orgs": state.main_orgs,
            "affiliate_orgs": state.affiliate_orgs,
            "community_moniker": state.community_moniker,
            "last_updated": state.checked_at,
        },
    )

    await Database.update_global_verification_state(
        state.user_id,
        {
            "rsi_handle": state.rsi_handle,
            "main_orgs": state.main_orgs,
            "affiliate_orgs": state.affiliate_orgs,
            "community_moniker": state.community_moniker,
            "last_updated": state.checked_at,
        },
    )


async def get_global_state(user_id: int) -> GlobalVerificationState | None:
    """Load the latest stored global verification state from the database."""
    from services.db.database import Database

    row = await Database.get_global_verification_state(user_id)
    if not row:
        return None

    # Filter out REDACTED entries for status computation
    non_redacted_main = [s for s in (row["main_orgs"] or []) if s != "REDACTED"]
    non_redacted_affiliate = [s for s in (row["affiliate_orgs"] or []) if s != "REDACTED"]

    status: VerificationStatus
    if non_redacted_main:
        status = "main"
    elif non_redacted_affiliate:
        status = "affiliate"
    else:
        status = "non_member"

    return GlobalVerificationState(
        user_id=user_id,
        rsi_handle=row["rsi_handle"],
        status=status,
        main_orgs=row["main_orgs"],
        affiliate_orgs=row["affiliate_orgs"],
        community_moniker=row.get("community_moniker"),
        checked_at=int(row.get("last_updated", time.time())),
        error=None,
    )
