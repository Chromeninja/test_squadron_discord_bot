"""
Security utilities for session management and authentication.

Handles Discord OAuth2 flow, session tokens, and access control.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired
from jose import JWTError, jwt

# Session configuration
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev_only_change_me_in_production")
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400 * 7  # 7 days
COOKIE_SECURE = (
    os.getenv("COOKIE_SECURE", "false").lower() == "true"
)  # Set true in production
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")  # lax or strict

# JWT configuration for session tokens
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# Discord OAuth2 configuration
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI", "http://localhost:8081/auth/callback"
)
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
DISCORD_OAUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_BASE = "https://discord.com/api/v10"

# State management for OAuth (simple in-memory store for dev, use Redis in production)
_oauth_states: dict[str, float] = {}


def generate_oauth_state() -> str:
    """
    Generate a cryptographically random state for OAuth flow.

    Returns:
        Random state string
    """
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = datetime.now(timezone.utc).timestamp()
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
    age = datetime.now(timezone.utc).timestamp() - timestamp
    return age < 300  # 5 minutes


def cleanup_expired_states() -> None:
    """Remove expired OAuth states (call periodically)."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [s for s, t in _oauth_states.items() if now - t > 300]
    for s in expired:
        _oauth_states.pop(s, None)


def set_session_cookie(response: Response, user_data: dict) -> None:
    """
    Set a secure session cookie on the response.

    Args:
        response: FastAPI Response object
        user_data: User data to encode in session
    """
    token = create_session_token(user_data)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,  # Not accessible via JavaScript
        secure=COOKIE_SECURE,  # Only over HTTPS (disabled for local dev)
        samesite=COOKIE_SAMESITE,  # CSRF protection
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


def create_session_token(user_data: dict) -> str:
    """
    Create a signed JWT session token.

    Args:
        user_data: User information to encode (user_id, username, etc.)

    Returns:
        Signed JWT token string
    """
    now = datetime.now(timezone.utc)
    payload = {
        **user_data,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> dict | None:
    """
    Decode and validate a session token.

    Args:
        token: JWT token string

    Returns:
        Decoded user data dict or None if invalid
    """
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except (JWTError, SignatureExpired, BadSignature):
        return None


def get_discord_authorize_url(state: str) -> str:
    """
    Generate Discord OAuth2 authorization URL with state.

    Args:
        state: State parameter for CSRF protection (required)

    Returns:
        Full authorization URL
    """
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds guilds.members.read",  # Added guilds scopes for role checking
        "state": state,
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
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
