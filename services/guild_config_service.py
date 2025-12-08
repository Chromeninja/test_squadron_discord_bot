"""Retired GuildConfigService module.

This module previously implemented a database-backed caching layer for guild
settings. The functionality now lives in ``services.config_service.ConfigService``
and ``services.guild_config_helper.GuildConfigHelper``. Importing this module is
treated as an error so that any remaining stale references are surfaced during
development.
"""

from __future__ import annotations

raise RuntimeError(
    "GuildConfigService has been removed. Switch to ConfigService or "
    "GuildConfigHelper for guild-scoped configuration access."
)
