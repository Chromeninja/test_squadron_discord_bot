"""Staff-role resolution helper for the ticket system.

Extracted from the legacy ``TicketService`` so bot-side view helpers can
resolve configured staff roles without importing the (now removed) service
monolith.  Reads only ``ConfigService`` — no direct DB access — keeping the
bot a thin client in the backend-first architecture.
"""

from __future__ import annotations

import json
from typing import Any


async def get_staff_role_ids(
    config_service: Any,
    guild_id: int,
) -> list[int]:
    """Return the configured staff role IDs for a guild.

    Parses the JSON array stored in ``tickets.staff_roles`` via
    ``ConfigService``.  All call-sites that need staff roles should use this
    function rather than duplicating the JSON parsing.

    Args:
        config_service: ``ConfigService`` instance (passed in to avoid
            circular imports).
        guild_id: Discord guild ID.

    Returns:
        List of Discord role ID integers.  Returns an empty list on any
        parse error so callers never crash on malformed config.
    """
    raw = await config_service.get_guild_setting(
        guild_id, "tickets.staff_roles", default="[]"
    )
    try:
        parsed: Any = raw
        # Handle values that may be JSON encoded more than once,
        # e.g. '"[123,456]"' from historical config writes.
        for _ in range(2):
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
                continue
            break
        if parsed is None:
            parsed = []
        return [int(r) for r in parsed]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
