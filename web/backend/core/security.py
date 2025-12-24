"""
Security utilities for session management and authentication.

Switches session handling to server-side storage keyed by a signed, small
token so browser cookies remain well under size limits even when users have
hundreds of guilds. Tokens are signed/timestamped with itsdangerous and map to
in-memory session records containing the actual payload.
"""

import copy
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

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
# Server-side session store (signed, size-safe cookies)
# ---------------------------------------------------------------------------


@dataclass
class SessionRecord:
    data: dict
    created_at: datetime
    expires_at: datetime


_session_store: dict[str, SessionRecord] = {}
_session_signer = URLSafeTimedSerializer(SESSION_SECRET, salt="session")


def _cleanup_expired_sessions(now: datetime | None = None) -> None:
    """Prune expired session records to keep memory bounded."""

    now = now or datetime.now(UTC)
    expired_keys = [sid for sid, rec in _session_store.items() if rec.expires_at <= now]
    for sid in expired_keys:
        _session_store.pop(sid, None)


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


def set_session_cookie(response: Response, user_data: dict) -> None:
    """Set a secure session cookie containing a signed session key only."""

    token = create_session_token(user_data)
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
    Create a signed session token backed by an in-memory session store.

    The cookie contains only the signed session key; the actual payload lives
    server-side, keeping cookies small even for large guild lists.

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

    # Normalize payload to ensure everything is JSON-serializable before storing
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
                # Best-effort conversion; skip invalid entries
                continue
        payload["authorized_guilds"] = normalized_auth

    payload["exp"] = int(expires_at.timestamp())
    payload["iat"] = int(now.timestamp())

    # Store payload server-side keyed by a random session id
    session_id = secrets.token_urlsafe(32)
    _session_store[session_id] = SessionRecord(
        data=payload,
        created_at=now,
        expires_at=expires_at,
    )

    _cleanup_expired_sessions(now)

    return _session_signer.dumps(session_id)


def decode_session_token(token: str) -> dict | None:
    """Resolve a session token to its server-side payload or return None.

    Returns a deep copy of the stored data to prevent callers from accidentally
    mutating the session store.
    """

    now = datetime.now(UTC)
    _cleanup_expired_sessions(now)

    try:
        session_id = _session_signer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None

    record = _session_store.get(session_id)
    if not record:
        return None

    if record.expires_at <= now:
        _session_store.pop(session_id, None)
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
