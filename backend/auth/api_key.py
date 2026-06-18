"""Bot-to-backend API key authentication.

The Discord bot authenticates using a shared secret passed in the
X-Bot-Api-Key header. This keeps the internal routes separate from
the OAuth2-protected public dashboard routes.

Set BOT_API_KEY in the environment (same value on both bot and backend).
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-Bot-Api-Key", auto_error=False)


async def require_bot_api_key(api_key: str | None = Security(_API_KEY_HEADER)) -> str:
    """FastAPI dependency that validates the bot API key header."""
    expected = os.environ.get("BOT_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=503, detail="BOT_API_KEY not configured on server"
        )
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid bot API key")
    return api_key
