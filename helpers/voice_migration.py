# helpers/voice_migration.py

"""Safe, application-driven migration helpers for voice/guild settings.

This module contains an idempotent migration routine that can be run at
startup by the application. It avoids destructive SQL and makes conservative
decisions when the correct guild target is ambiguous.

Policy used:
- If no legacy `join_to_create_channel_ids` setting exists -> no-op.
- If the legacy value parses as a JSON list or a comma-separated list and the
  bot is in exactly one guild, migrate that list into `guild_settings` for
  that guild (INSERT OR IGNORE). This is safe and idempotent.
- If the bot is in multiple guilds, log an actionable warning and do nothing
  (manual resolution required).
"""

import contextlib
import json

from helpers.database import Database
from helpers.logger import get_logger

logger = get_logger(__name__)


async def _parse_legacy_jtc(value: str) -> list[int] | None:
    if not value:
        return None
    # Try JSON first (most robust)
    with contextlib.suppress(Exception):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
        if isinstance(parsed, int):
            return [int(parsed)]

    # Fallback: comma-separated string of ints
    with contextlib.suppress(Exception):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return [int(p) for p in parts]
    return None


async def run_voice_data_migration(bot) -> None:
    """Run a small, conservative voice data migration.

    This routine is intentionally limited: it only migrates a global
    `join_to_create_channel_ids` legacy setting into `guild_settings` when the
    bot is in exactly one guild. It is idempotent and logs any ambiguous
    situations for manual resolution.
    """
    # Acquire a DB connection via the project's Database helper
    async with Database.get_connection() as db:
        try:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("join_to_create_channel_ids",),
            )
            row = await cursor.fetchone()
            if not row or not row[0]:
                logger.debug(
                    "Voice migration: no legacy join_to_create_channel_ids found; "
                    "skipping."
                )
                return

            legacy_val = row[0]
            jtc_list = await _parse_legacy_jtc(legacy_val)
            if not jtc_list:
                logger.warning(
                    "Voice migration: could not parse legacy "
                    "join_to_create_channel_ids value; skipping. value=%r",
                    legacy_val,
                )
                return

            # If there is already any guild-scoped setting, don't overwrite it
            cursor = await db.execute(
                "SELECT 1 FROM guild_settings WHERE key = ? LIMIT 1",
                ("join_to_create_channel_ids",),
            )
            if await cursor.fetchone():
                logger.info(
                    "Voice migration: guild-scoped join_to_create_channel_ids "
                    "already present; skipping migration."
                )
                return

            # If bot is in exactly one guild, safely migrate the legacy list to
            # that guild
            guilds = list(bot.guilds)
            if len(guilds) == 1:
                target_guild_id = guilds[0].id
                # Insert idempotently
                await db.execute(
                    "INSERT OR IGNORE INTO guild_settings "
                    "(guild_id, key, value) VALUES (?, ?, ?)",
                    (
                        target_guild_id,
                        "join_to_create_channel_ids",
                        json.dumps(jtc_list),
                    ),
                )
                await db.commit()
                logger.info(
                    "Voice migration: migrated legacy join_to_create_channel_ids "
                    "to guild %s (N=%d entries).",
                    target_guild_id,
                    len(jtc_list),
                )
                return

            # Ambiguous: multiple guilds or zero guilds — leave for manual resolution
            if len(guilds) == 0:
                logger.info(
                    "Voice migration: bot is not in any guilds; skipping "
                    "automatic migration."
                )
            else:
                logger.warning(
                    "Voice migration: multiple guilds detected (%d); automatic "
                    "migration skipped. Please run a per-guild migration tool.",
                    len(guilds),
                )

        except Exception:
            with contextlib.suppress(Exception):
                await db.rollback()
            logger.exception("Voice migration: unexpected error")
