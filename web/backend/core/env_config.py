"""
Centralized environment configuration.

Single source of truth for all environment-derived settings.
Derives URLs from PUBLIC_URL to eliminate redundant variables.

Usage:
    from core.env_config import (
        PUBLIC_URL,
        FRONTEND_URL,
        DISCORD_CLIENT_ID,
        DISCORD_CLIENT_SECRET,
        DISCORD_REDIRECT_URI,
        DISCORD_BOT_REDIRECT_URI,
        INTERNAL_API_URL,
        INTERNAL_API_KEY,
        BOT_OWNER_IDS,
        SESSION_SECRET,
        COOKIE_SECURE,
        COOKIE_SAMESITE,
        ENV,
    )
"""

import os
from typing import Literal, cast
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Environment Mode
# ---------------------------------------------------------------------------
ENV = os.getenv("ENV", "development").lower()
IS_PRODUCTION = ENV == "production"
IS_DEV = ENV in {"dev", "development", "test"}

# ---------------------------------------------------------------------------
# Public URL (single source of truth for external-facing URLs)
# ---------------------------------------------------------------------------
# In production: https://your-domain.com
# In development: http://localhost:8081 (backend port)
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8081").rstrip("/")

# Parse PUBLIC_URL to extract components
_parsed_public = urlparse(PUBLIC_URL)
_public_scheme = _parsed_public.scheme or "http"
_public_host = _parsed_public.netloc or "localhost:8081"

# ---------------------------------------------------------------------------
# Frontend URL (derived from PUBLIC_URL)
# ---------------------------------------------------------------------------
# In production with nginx: same as PUBLIC_URL (nginx serves frontend at /)
# In development: different port for Vite dev server
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))

if IS_DEV:
    # Development: frontend runs on separate Vite port
    _frontend_host = _public_host.split(":")[0]  # Strip port
    FRONTEND_URL = f"{_public_scheme}://{_frontend_host}:{FRONTEND_PORT}"
else:
    # Production: nginx serves frontend from same origin
    FRONTEND_URL = PUBLIC_URL

# ---------------------------------------------------------------------------
# Discord OAuth2 Configuration
# ---------------------------------------------------------------------------
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")

# Derived from PUBLIC_URL - paths are fixed
DISCORD_REDIRECT_URI = f"{PUBLIC_URL}/auth/callback"
DISCORD_BOT_REDIRECT_URI = f"{PUBLIC_URL}/auth/bot-callback"

# Discord API endpoints (constants - never change)
DISCORD_OAUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_BASE = "https://discord.com/api/v10"

# ---------------------------------------------------------------------------
# Internal API Configuration (bot <-> backend communication)
# ---------------------------------------------------------------------------
INTERNAL_API_HOST = os.getenv("INTERNAL_API_HOST", "127.0.0.1")
INTERNAL_API_PORT = int(os.getenv("INTERNAL_API_PORT", "8082"))
INTERNAL_API_URL = f"http://{INTERNAL_API_HOST}:{INTERNAL_API_PORT}"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# ---------------------------------------------------------------------------
# Bot Owner IDs (unified - comma-separated list)
# ---------------------------------------------------------------------------
_raw_owner_ids = os.getenv("BOT_OWNER_IDS", "")
BOT_OWNER_IDS: set[int] = set()
for _id_str in _raw_owner_ids.split(","):
    _id_str = _id_str.strip()
    if _id_str:
        try:
            BOT_OWNER_IDS.add(int(_id_str))
        except ValueError:
            pass

# ---------------------------------------------------------------------------
# Session & Cookie Configuration
# ---------------------------------------------------------------------------
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev_only_change_me_in_production")
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

# Auto-detect secure cookies based on PUBLIC_URL scheme
_auto_cookie_secure = _public_scheme == "https"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", str(_auto_cookie_secure).lower()).lower() == "true"

_cookie_samesite_raw = os.getenv("COOKIE_SAMESITE", "lax").lower()
COOKIE_SAMESITE: Literal["lax", "strict", "none"] | None = cast(
    "Literal['lax', 'strict', 'none'] | None",
    _cookie_samesite_raw if _cookie_samesite_raw in {"lax", "strict", "none"} else None,
)

# JWT configuration (retained for compatibility)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# ---------------------------------------------------------------------------
# Validation & Warnings
# ---------------------------------------------------------------------------
import logging

_logger = logging.getLogger(__name__)

if IS_PRODUCTION:
    # Validate critical settings in production
    if SESSION_SECRET == "dev_only_change_me_in_production":
        _logger.critical(
            "SESSION_SECRET must be set to a secure value in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if not INTERNAL_API_KEY:
        _logger.critical(
            "INTERNAL_API_KEY must be set in production for secure bot-backend communication"
        )

    if not COOKIE_SECURE:
        _logger.warning(
            "COOKIE_SECURE is false in production - cookies may be vulnerable to interception"
        )

if IS_DEV and SESSION_SECRET == "dev_only_change_me_in_production":
    _logger.warning(
        "Using default SESSION_SECRET for development. "
        "Set a secure value before deploying to production."
    )

# Log configuration summary (debug level to avoid noise)
_logger.debug(
    "Environment configuration loaded",
    extra={
        "env": ENV,
        "public_url": PUBLIC_URL,
        "frontend_url": FRONTEND_URL,
        "discord_redirect_uri": DISCORD_REDIRECT_URI,
        "internal_api_url": INTERNAL_API_URL,
        "cookie_secure": COOKIE_SECURE,
        "bot_owner_count": len(BOT_OWNER_IDS),
    },
)
