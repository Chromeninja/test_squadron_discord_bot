"""Utility helpers for reading and writing guild_settings records."""

from __future__ import annotations

import json
from typing import Any

from aiosqlite import Connection

BOT_ADMINS_KEY = "roles.bot_admins"
LEAD_MODS_KEY = "roles.lead_moderators"
MAIN_ROLE_KEY = "roles.main_role"
AFFILIATE_ROLE_KEY = "roles.affiliate_role"
NONMEMBER_ROLE_KEY = "roles.nonmember_role"
SELECTABLE_ROLES_KEY = "selectable_roles"

VERIFICATION_CHANNEL_KEY = "channels.verification_channel_id"
BOT_SPAM_CHANNEL_KEY = "channels.bot_spam_channel_id"
PUBLIC_ANNOUNCEMENT_CHANNEL_KEY = "channels.public_announcement_channel_id"
LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY = "channels.leadership_announcement_channel_id"


def _coerce_role_list(value: Any) -> list[int]:
    """Convert stored JSON values into a list of ints."""
    if value is None:
        return []

    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    cleaned: list[int] = []
    seen = set()
    for item in data:
        try:
            role_id = int(item)
            if role_id not in seen:
                cleaned.append(role_id)
                seen.add(role_id)
        except (TypeError, ValueError):
            continue
    return cleaned


async def get_bot_role_settings(db: Connection, guild_id: int) -> dict[str, list[int]]:
    """Fetch bot role settings for a guild with sensible defaults."""
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?, ?)
    """
    cursor = await db.execute(
        query,
        (guild_id, BOT_ADMINS_KEY, LEAD_MODS_KEY, MAIN_ROLE_KEY, AFFILIATE_ROLE_KEY, NONMEMBER_ROLE_KEY)
    )
    rows = await cursor.fetchall()

    result = {
        "bot_admins": [],
        "lead_moderators": [],
        "main_role": [],
        "affiliate_role": [],
        "nonmember_role": [],
    }

    for key, value in rows:
        if key == BOT_ADMINS_KEY:
            result["bot_admins"] = _coerce_role_list(value)
        elif key == LEAD_MODS_KEY:
            result["lead_moderators"] = _coerce_role_list(value)
        elif key == MAIN_ROLE_KEY:
            result["main_role"] = _coerce_role_list(value)
        elif key == AFFILIATE_ROLE_KEY:
            result["affiliate_role"] = _coerce_role_list(value)
        elif key == NONMEMBER_ROLE_KEY:
            result["nonmember_role"] = _coerce_role_list(value)

    return result


async def set_bot_role_settings(
    db: Connection,
    guild_id: int,
    bot_admins: list[int],
    lead_moderators: list[int],
    main_role: list[int],
    affiliate_role: list[int],
    nonmember_role: list[int],
) -> None:
    """Persist bot role settings for a guild."""
    def _normalize_role_ids(values: list[int]) -> list[int]:
        normalized: list[int] = []
        for value in values:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(set(normalized))

    payloads = [
        (BOT_ADMINS_KEY, json.dumps(_normalize_role_ids(bot_admins))),
        (LEAD_MODS_KEY, json.dumps(_normalize_role_ids(lead_moderators))),
        (MAIN_ROLE_KEY, json.dumps(_normalize_role_ids(main_role))),
        (AFFILIATE_ROLE_KEY, json.dumps(_normalize_role_ids(affiliate_role))),
        (NONMEMBER_ROLE_KEY, json.dumps(_normalize_role_ids(nonmember_role))),
    ]

    await db.executemany(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        [(guild_id, key, value) for key, value in payloads],
    )
    await db.commit()


async def get_bot_channel_settings(db: Connection, guild_id: int) -> dict[str, int | None]:
    """Fetch bot channel settings for a guild."""
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?)
    """
    cursor = await db.execute(
        query,
        (
            guild_id,
            VERIFICATION_CHANNEL_KEY,
            BOT_SPAM_CHANNEL_KEY,
            PUBLIC_ANNOUNCEMENT_CHANNEL_KEY,
            LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY,
        ),
    )
    rows = await cursor.fetchall()

    result: dict[str, int | None] = {
        "verification_channel_id": None,
        "bot_spam_channel_id": None,
        "public_announcement_channel_id": None,
        "leadership_announcement_channel_id": None,
    }

    for key, value in rows:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            channel_id = int(parsed) if parsed is not None else None
        except (TypeError, ValueError, json.JSONDecodeError):
            channel_id = None

        if key == VERIFICATION_CHANNEL_KEY:
            result["verification_channel_id"] = channel_id
        elif key == BOT_SPAM_CHANNEL_KEY:
            result["bot_spam_channel_id"] = channel_id
        elif key == PUBLIC_ANNOUNCEMENT_CHANNEL_KEY:
            result["public_announcement_channel_id"] = channel_id
        elif key == LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY:
            result["leadership_announcement_channel_id"] = channel_id

    return result


async def set_bot_channel_settings(
    db: Connection,
    guild_id: int,
    verification_channel_id: int | None,
    bot_spam_channel_id: int | None,
    public_announcement_channel_id: int | None,
    leadership_announcement_channel_id: int | None,
) -> None:
    """Persist bot channel settings for a guild."""
    payloads = [
        (VERIFICATION_CHANNEL_KEY, json.dumps(verification_channel_id)),
        (BOT_SPAM_CHANNEL_KEY, json.dumps(bot_spam_channel_id)),
        (PUBLIC_ANNOUNCEMENT_CHANNEL_KEY, json.dumps(public_announcement_channel_id)),
        (LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY, json.dumps(leadership_announcement_channel_id)),
    ]

    for key, value in payloads:
        await db.execute(
            """
            INSERT INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
            """,
            (guild_id, key, value),
        )

    await db.commit()


async def get_voice_selectable_roles(db: Connection, guild_id: int) -> list[int]:
    """Fetch selectable voice role IDs for a guild."""
    cursor = await db.execute(
        """
        SELECT value
        FROM guild_settings
        WHERE guild_id = ? AND key = ?
        """,
        (guild_id, SELECTABLE_ROLES_KEY),
    )
    row = await cursor.fetchone()
    if not row:
        return []
    return _coerce_role_list(row[0])


async def set_voice_selectable_roles(
    db: Connection,
    guild_id: int,
    selectable_roles: list[int],
) -> None:
    """Persist selectable voice role IDs for a guild."""

    def _normalize(values: list[int]) -> list[int]:
        normalized: list[int] = []
        for value in values:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(set(normalized))

    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, SELECTABLE_ROLES_KEY, json.dumps(_normalize(selectable_roles))),
    )
    await db.commit()
