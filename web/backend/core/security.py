"""
Security utilities for session management and authentication.

Server-side session storage backed by SQLite so that sessions survive
process restarts.  Browser cookies carry only a signed, compact token
that maps to the real payload stored in ``session_store``.
"""

import asyncio
import copy
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import session_store

# Import all environment configuration from centralized module
from .env_config import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    DISCORD_API_BASE,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_OAUTH_URL,
    DISCORD_REDIRECT_URI,
    DISCORD_TOKEN_URL,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    SESSION_SECRET,
)

# Re-export for backwards compatibility with existing imports
__all__ = [
    "COOKIE_SAMESITE",
    "COOKIE_SECURE",
    "DISCORD_API_BASE",
    "DISCORD_CLIENT_ID",
    "DISCORD_CLIENT_SECRET",
    "DISCORD_OAUTH_URL",
    "DISCORD_REDIRECT_URI",
    "DISCORD_TOKEN_URL",
    "JWT_ALGORITHM",
    "JWT_EXPIRATION_HOURS",
    "SESSION_COOKIE_NAME",
    "SESSION_MAX_AGE",
    "SESSION_SECRET",
    "check_user_has_roles",
    "cleanup_expired_states",
    "clear_session_cookie",
    "create_session_token",
    "create_session_token_async",
    "decode_session_token",
    "generate_oauth_state",
    "get_discord_authorize_url",
    "set_session_cookie",
    "validate_oauth_state",
]

# OAuth state management: in-memory store with 5-minute expiration.
# Acceptable for single-instance deployments. If scaling to multiple instances
# or workers, migrate to Redis or database-backed storage.
_oauth_states: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Server-side session store (SQLite-backed, signed cookie keys)
# ---------------------------------------------------------------------------

_session_signer = URLSafeTimedSerializer(SESSION_SECRET, salt="session")


def _cleanup_expired_sessions(now: datetime | None = None) -> None:
    """Schedule async cleanup of expired sessions (fire-and-forget).

    Kept for call-site compatibility; the actual purge happens in
    ``session_store.cleanup_expired()``.
    """
    # In pytest, function-scoped event loops are frequently torn down;
    # background cleanup tasks can outlive the loop and cause aiosqlite
    # thread callbacks to crash with "Event loop is closed".
    if os.getenv("PYTEST_CURRENT_TEST"):
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(session_store.cleanup_expired())
    except RuntimeError:
        pass  # no event loop — skip (e.g. test teardown)


def generate_oauth_state() -> str:
    """
    Generate a cryptographically random state for OAuth flow.

    Returns:
        Random state string
    """
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = datetime.now(UTC).timestamp()
    return state


def validate_oauth_state(state: str) -> bool:
    """
    Validate OAuth state and remove it (one-time use).

    Args:
        state: State string to validate

    Returns:
        True if valid, False otherwise
    """
    if state not in _oauth_states:
        return False

    # Check expiration (5 minutes)
    timestamp = _oauth_states.pop(state)
    age = datetime.now(UTC).timestamp() - timestamp
    return age < 300  # 5 minutes


def cleanup_expired_states() -> None:
    """Remove expired OAuth states (call periodically)."""
    now = datetime.now(UTC).timestamp()
    expired = [s for s, t in _oauth_states.items() if now - t > 300]
    for s in expired:
        _oauth_states.pop(s, None)


async def set_session_cookie(response: Response, user_data: dict) -> None:
    """Set a secure session cookie containing a signed session key only."""

    token = await create_session_token_async(user_data)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """
    Clear the session cookie.

    Args:
        response: FastAPI Response object
    """
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )


def create_session_token(user_data: dict, expires_in_seconds: int | None = None) -> str:
    """
    Create a signed session token backed by SQLite session store.

    The cookie contains only the signed session key; the actual payload lives
    server-side, keeping cookies small even for large guild lists.

    The DB write is scheduled as a fire-and-forget asyncio task so that this
    function can remain synchronous (required by ``set_session_cookie``).
    Use ``create_session_token_async`` when you need to await persistence.

    Args:
        user_data: Session payload (user profile and permissions)
        expires_in_seconds: Optional TTL override for the session record. Uses
            SESSION_MAX_AGE when omitted. Values greater than SESSION_MAX_AGE
            are clamped; negative values expire immediately (test helper).

    Returns:
        Signed, time-stamped token representing the session key.
    """

    now = datetime.now(UTC)
    ttl = SESSION_MAX_AGE if expires_in_seconds is None else min(expires_in_seconds, SESSION_MAX_AGE)
    ttl = max(ttl, 0)
    expires_at = now + timedelta(seconds=ttl)

    payload = _normalize_session_payload(user_data, now, expires_at)

    session_id = secrets.token_urlsafe(32)

    # Schedule the async DB write
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            session_store.save(
                session_id,
                payload,
                created_at=now.timestamp(),
                expires_at=expires_at.timestamp(),
            )
        )
    except RuntimeError:
        # No running loop — fall back to sync-ish approach (test helpers)
        pass

    _cleanup_expired_sessions(now)

    return _session_signer.dumps(session_id)


async def create_session_token_async(
    user_data: dict, expires_in_seconds: int | None = None
) -> str:
    """Awaitable variant of ``create_session_token`` that guarantees the DB
    write completes before returning the signed token.
    """

    now = datetime.now(UTC)
    ttl = SESSION_MAX_AGE if expires_in_seconds is None else min(expires_in_seconds, SESSION_MAX_AGE)
    ttl = max(ttl, 0)
    expires_at = now + timedelta(seconds=ttl)

    payload = _normalize_session_payload(user_data, now, expires_at)

    session_id = secrets.token_urlsafe(32)
    await session_store.save(
        session_id,
        payload,
        created_at=now.timestamp(),
        expires_at=expires_at.timestamp(),
    )

    _cleanup_expired_sessions(now)
    return _session_signer.dumps(session_id)


def _normalize_session_payload(
    user_data: dict, now: datetime, expires_at: datetime
) -> dict:
    """Prepare session payload for storage (normalise guild permissions)."""
    payload = dict(user_data)
    authorized = payload.get("authorized_guilds") or {}
    if isinstance(authorized, dict):
        normalized_auth: dict[str, dict] = {}
        for gid, perm in authorized.items():
            if hasattr(perm, "model_dump"):
                normalized_auth[gid] = perm.model_dump()
            elif isinstance(perm, dict):
                normalized_auth[gid] = perm
            else:
                continue
        payload["authorized_guilds"] = normalized_auth

    payload["exp"] = int(expires_at.timestamp())
    payload["iat"] = int(now.timestamp())
    return payload


async def decode_session_token(token: str) -> dict | None:
    """Resolve a session token to its server-side payload or return None.

    Returns a deep copy of the stored data to prevent callers from accidentally
    mutating the session store.
    """

    _cleanup_expired_sessions()

    try:
        session_id = _session_signer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None

    record = await session_store.load(session_id)
    if not record:
        return None

    # Return a deep copy to prevent mutation of the stored session data
    return copy.deepcopy(record.data)


def get_discord_authorize_url(state: str) -> str:
    """
    Generate Discord OAuth2 authorization URL with state.

    Args:
        state: State parameter for CSRF protection (required)

    Returns:
        Full authorization URL
    """
    from urllib.parse import urlencode

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds guilds.members.read",  # Added guilds scopes for role checking
        "state": state,
    }

    query_string = urlencode(params)
    return f"{DISCORD_OAUTH_URL}?{query_string}"


def check_user_has_roles(
    user_role_ids: list[str], admin_role_ids: list, moderator_role_ids: list
) -> tuple[bool, bool]:
    """
    Check if a user has admin or moderator roles.

    Args:
        user_role_ids: List of role IDs the user has (as strings from Discord API)
        admin_role_ids: List of admin role IDs from config
        moderator_role_ids: List of moderator role IDs from config

    Returns:
        Tuple of (is_admin, is_moderator)
    """
    # Convert all to strings for comparison
    user_roles_str = {str(rid) for rid in user_role_ids}
    admin_roles_str = {str(rid) for rid in admin_role_ids}
    mod_roles_str = {str(rid) for rid in moderator_role_ids}

    is_admin = bool(user_roles_str & admin_roles_str)  # Check for intersection
    is_moderator = bool(user_roles_str & mod_roles_str)

    return is_admin, is_moderator
