"""
Shared bot-level utility helpers.

Eliminates repeated ``hasattr(bot, 'services')`` guard patterns and
duplicated organization-SID retrieval logic across the codebase.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service availability guards
# ---------------------------------------------------------------------------

def bot_has_services(bot: Any) -> bool:
    """Return True if *bot* has an initialised services container."""
    return getattr(bot, "services", None) is not None


def bot_has_guild_config(bot: Any) -> bool:
    """Return True if *bot* has an initialised guild_config helper."""
    services = getattr(bot, "services", None)
    if services is None:
        return False
    return getattr(services, "guild_config", None) is not None


# ---------------------------------------------------------------------------
# Organization SID retrieval
# ---------------------------------------------------------------------------

async def get_guild_org_sid(
    bot: Any,
    guild_id: int,
    *,
    default: str = "TEST",
) -> str:
    """Return the normalised (upper-case, quote-stripped) org SID for *guild_id*.

    Delegates to ``bot.services.guild_config.get_org_sid()`` when available,
    otherwise returns *default*.  All call-sites that previously duplicated
    this logic should use this helper instead.

    Parameters
    ----------
    bot:
        The bot instance (expected to have ``bot.services.guild_config``).
    guild_id:
        Discord guild ID whose org SID to look up.
    default:
        Fallback value when the config service is unavailable or the key is
        not set.  Callers may pass ``"ORG"``, ``None``, etc. as needed.

    Returns
    -------
    str
        Upper-cased org SID with surrounding quotes stripped.
    """
    if not bot_has_guild_config(bot):
        return default

    try:
        return await bot.services.guild_config.get_org_sid(guild_id)
    except Exception as e:
        logger.debug(
            "Failed to get org SID for guild %s, using default %r: %s",
            guild_id, default, e,
        )
        return default
