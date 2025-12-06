"""Utility helpers for reading and writing guild_settings records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiosqlite import Connection

BOT_ADMINS_KEY = "roles.bot_admins"
MODERATORS_KEY = "roles.moderators"
DISCORD_MANAGERS_KEY = "roles.discord_managers"
STAFF_KEY = "roles.staff"
BOT_VERIFIED_ROLE_KEY = "roles.bot_verified_role"
MAIN_ROLE_KEY = "roles.main_role"
AFFILIATE_ROLE_KEY = "roles.affiliate_role"
NONMEMBER_ROLE_KEY = "roles.nonmember_role"
SELECTABLE_ROLES_KEY = "selectable_roles"
DELEGATION_POLICIES_KEY = "roles.delegation_policies"
# Legacy alias retained for compatibility until callers are migrated.
ROLE_DELEGATION_POLICIES_KEY = DELEGATION_POLICIES_KEY

SETTINGS_VERSION_KEY = "meta.settings_version"
SETTINGS_VERSION_ROLES_SOURCE = "bot_roles"
SETTINGS_VERSION_DELEGATION_SOURCE = "role_delegation"

VERIFICATION_CHANNEL_KEY = "channels.verification_channel_id"
BOT_SPAM_CHANNEL_KEY = "channels.bot_spam_channel_id"
PUBLIC_ANNOUNCEMENT_CHANNEL_KEY = "channels.public_announcement_channel_id"
LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY = "channels.leadership_announcement_channel_id"

ORGANIZATION_SID_KEY = "organization.sid"
ORGANIZATION_NAME_KEY = "organization.name"


def _coerce_role_list(value: Any) -> list[str]:
    """Convert stored JSON values into a list of string IDs to preserve precision."""
    if value is None:
        return []

    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    cleaned: list[str] = []
    seen = set()
    for item in data:
        try:
            # Convert to string to preserve precision for large Discord snowflake IDs
            role_id = str(
                int(item)
            )  # int() validates it's numeric, str() preserves precision
            if role_id not in seen:
                cleaned.append(role_id)
                seen.add(role_id)
        except (TypeError, ValueError):
            continue
    return cleaned


def _normalize_policy_roles(raw_roles: Any) -> list[str]:
    """Normalize a role list to unique string IDs preserving numeric validity."""
    if raw_roles is None:
        return []
    normalized: list[str] = []
    seen = set()
    items = raw_roles if isinstance(raw_roles, list) else [raw_roles]
    for item in items:
        try:
            rid = str(int(item))
        except (TypeError, ValueError):
            continue
        if rid not in seen:
            seen.add(rid)
            normalized.append(rid)
    return normalized


def _normalize_delegation_policies(value: list[dict] | None) -> list[dict]:
    """Normalize delegation policies to the new schema shape with string snowflakes.

    Supports legacy keys (grantor_roles/granted_role/requirements.required_roles)
    and new keys (grantor_role_ids/target_role_id/prerequisite_role_ids_all/
    prerequisite_role_ids_any).
    """
    if not value:
        return []

    normalized: list[dict] = []
    for policy in value:
        if hasattr(policy, "model_dump"):
            policy = policy.model_dump()
        if not isinstance(policy, dict):
            continue

        grantor_roles = policy.get("grantor_role_ids") or policy.get("grantor_roles")
        target_role_raw = policy.get("target_role_id") or policy.get("granted_role")

        requirements = policy.get("requirements") or {}
        prereq_all = (
            policy.get("prerequisite_role_ids_all")
            or policy.get("prerequisite_role_ids")
            or requirements.get("required_roles")
        )
        prereq_any = policy.get("prerequisite_role_ids_any")

        try:
            target_role_id = (
                str(int(target_role_raw)) if target_role_raw is not None else None
            )
        except (TypeError, ValueError):
            target_role_id = None

        if target_role_id is None:
            # Skip invalid policies instead of storing partial data
            continue

        normalized.append(
            {
                "grantor_role_ids": _normalize_policy_roles(grantor_roles),
                "target_role_id": target_role_id,
                "prerequisite_role_ids_all": _normalize_policy_roles(prereq_all),
                "prerequisite_role_ids": _normalize_policy_roles(prereq_all),
                "prerequisite_role_ids_any": _normalize_policy_roles(prereq_any),
                "enabled": bool(policy.get("enabled", True)),
                "note": policy.get("note") or policy.get("notes"),
            }
        )
    return normalized


def _coerce_policy_list(value: Any) -> list[dict]:
    """Deserialize delegation policy JSON into normalized list of dicts."""
    if value is None:
        return []

    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    return _normalize_delegation_policies(data)


async def get_bot_role_settings(db: Connection, guild_id: int) -> dict[str, list[str]]:
    """Fetch bot role settings for a guild with sensible defaults.

    Returns dict with keys: bot_admins, discord_managers, moderators, staff,
    main_role, affiliate_role, nonmember_role.
    """
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor = await db.execute(
        query,
        (
            guild_id,
            BOT_ADMINS_KEY,
            MODERATORS_KEY,
            DISCORD_MANAGERS_KEY,
            STAFF_KEY,
            BOT_VERIFIED_ROLE_KEY,
            MAIN_ROLE_KEY,
            AFFILIATE_ROLE_KEY,
            NONMEMBER_ROLE_KEY,
            DELEGATION_POLICIES_KEY,
        ),
    )
    rows = await cursor.fetchall()

    result = {
        "bot_admins": [],
        "discord_managers": [],
        "moderators": [],
        "staff": [],
        "bot_verified_role": [],
        "main_role": [],
        "affiliate_role": [],
        "nonmember_role": [],
        "delegation_policies": [],
    }
    for key, value in rows:
        if key == BOT_ADMINS_KEY:
            result["bot_admins"] = _coerce_role_list(value)
        elif key == MODERATORS_KEY:
            result["moderators"] = _coerce_role_list(value)
        elif key == DISCORD_MANAGERS_KEY:
            result["discord_managers"] = _coerce_role_list(value)
        elif key == STAFF_KEY:
            result["staff"] = _coerce_role_list(value)
        elif key == BOT_VERIFIED_ROLE_KEY:
            result["bot_verified_role"] = _coerce_role_list(value)
        elif key == MAIN_ROLE_KEY:
            result["main_role"] = _coerce_role_list(value)
        elif key == AFFILIATE_ROLE_KEY:
            result["affiliate_role"] = _coerce_role_list(value)
        elif key == NONMEMBER_ROLE_KEY:
            result["nonmember_role"] = _coerce_role_list(value)
        elif key == DELEGATION_POLICIES_KEY:
            result["delegation_policies"] = _coerce_policy_list(value)

    return result


async def get_role_delegation_policies(db: Connection, guild_id: int) -> list[dict]:
    """Fetch delegation policies for a guild, normalized."""
    cursor = await db.execute(
        """
        SELECT value FROM guild_settings
        WHERE guild_id = ? AND key = ?
        """,
        (guild_id, DELEGATION_POLICIES_KEY),
    )
    row = await cursor.fetchone()
    if not row:
        return []
    return _coerce_policy_list(row[0])


def _make_version_payload(source: str | None = None) -> str:
    """Serialize a version payload with UTC timestamp for cache invalidation."""
    payload = {
        "version": datetime.now(UTC).isoformat(),
        "source": source or "unknown",
    }
    return json.dumps(payload)


async def _touch_settings_version(
    db: Connection, guild_id: int, *, source: str | None = None
) -> None:
    """Update the guild's settings version marker to signal downstream caches."""
    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, SETTINGS_VERSION_KEY, _make_version_payload(source)),
    )


async def set_bot_role_settings(
    db: Connection,
    guild_id: int,
    bot_admins: list[str],
    discord_managers: list[str],
    moderators: list[str],
    staff: list[str],
    bot_verified_role: list[str],
    main_role: list[str],
    affiliate_role: list[str],
    nonmember_role: list[str],
    delegation_policies: list[dict] | None = None,
) -> None:
    """Persist bot role settings for a guild."""

    def _normalize_role_ids(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen = set()
        for value in values:
            try:
                # Validate it's numeric, keep as string to preserve precision
                role_id = str(int(value))
                if role_id not in seen:
                    normalized.append(role_id)
                    seen.add(role_id)
            except (TypeError, ValueError):
                continue
        return sorted(normalized, key=lambda x: int(x))

    payloads = [
        (BOT_ADMINS_KEY, json.dumps(_normalize_role_ids(bot_admins))),
        (DISCORD_MANAGERS_KEY, json.dumps(_normalize_role_ids(discord_managers))),
        (MODERATORS_KEY, json.dumps(_normalize_role_ids(moderators))),
        (STAFF_KEY, json.dumps(_normalize_role_ids(staff))),
        (BOT_VERIFIED_ROLE_KEY, json.dumps(_normalize_role_ids(bot_verified_role))),
        (MAIN_ROLE_KEY, json.dumps(_normalize_role_ids(main_role))),
        (AFFILIATE_ROLE_KEY, json.dumps(_normalize_role_ids(affiliate_role))),
        (NONMEMBER_ROLE_KEY, json.dumps(_normalize_role_ids(nonmember_role))),
    ]

    if delegation_policies is not None:
        payloads.append(
            (
                DELEGATION_POLICIES_KEY,
                json.dumps(_normalize_delegation_policies(delegation_policies)),
            )
        )

    await db.executemany(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        [(guild_id, key, value) for key, value in payloads],
    )
    if delegation_policies is not None:
        await _touch_settings_version(
            db, guild_id, source=SETTINGS_VERSION_DELEGATION_SOURCE
        )
    await _touch_settings_version(db, guild_id, source=SETTINGS_VERSION_ROLES_SOURCE)
    await db.commit()


async def set_role_delegation_policies(
    db: Connection, guild_id: int, policies: list[dict]
) -> list[dict]:
    """Persist delegation policies for a guild and return normalized payload."""
    normalized = _normalize_delegation_policies(policies)

    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, DELEGATION_POLICIES_KEY, json.dumps(normalized)),
    )
    await _touch_settings_version(
        db, guild_id, source=SETTINGS_VERSION_DELEGATION_SOURCE
    )
    await db.commit()
    return normalized


async def get_bot_channel_settings(
    db: Connection, guild_id: int
) -> dict[str, str | None]:
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

    result: dict[str, str | None] = {
        "verification_channel_id": None,
        "bot_spam_channel_id": None,
        "public_announcement_channel_id": None,
        "leadership_announcement_channel_id": None,
    }

    for key, value in rows:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            # Keep as string to preserve precision (Discord snowflakes are 64-bit)
            channel_id = str(parsed) if parsed is not None else None
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
    verification_channel_id: str | None,
    bot_spam_channel_id: str | None,
    public_announcement_channel_id: str | None,
    leadership_announcement_channel_id: str | None,
) -> None:
    """Persist bot channel settings for a guild."""
    payloads = [
        (VERIFICATION_CHANNEL_KEY, json.dumps(verification_channel_id)),
        (BOT_SPAM_CHANNEL_KEY, json.dumps(bot_spam_channel_id)),
        (PUBLIC_ANNOUNCEMENT_CHANNEL_KEY, json.dumps(public_announcement_channel_id)),
        (
            LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY,
            json.dumps(leadership_announcement_channel_id),
        ),
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

    await _touch_settings_version(db, guild_id, source="bot_channels")
    await db.commit()


async def get_voice_selectable_roles(db: Connection, guild_id: int) -> list[str]:
    """Fetch selectable voice role IDs for a guild as strings to preserve precision."""
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
    selectable_roles: list[str],
) -> None:
    """Persist selectable voice role IDs for a guild."""

    def _normalize(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen = set()
        for value in values:
            try:
                # Validate it's numeric, keep as string to preserve precision
                role_id = str(int(value))
                if role_id not in seen:
                    normalized.append(role_id)
                    seen.add(role_id)
            except (TypeError, ValueError):
                continue
        return sorted(normalized, key=lambda x: int(x))

    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, SELECTABLE_ROLES_KEY, json.dumps(_normalize(selectable_roles))),
    )
    await _touch_settings_version(db, guild_id, source="voice_selectable_roles")
    await db.commit()


async def get_organization_settings(
    db: Connection, guild_id: int
) -> dict[str, str | None]:
    """Fetch organization settings for a guild."""
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?)
    """
    cursor = await db.execute(
        query,
        (guild_id, ORGANIZATION_SID_KEY, ORGANIZATION_NAME_KEY),
    )
    rows = await cursor.fetchall()

    result: dict[str, str | None] = {
        "organization_sid": None,
        "organization_name": None,
    }

    for key, value in rows:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            string_value = str(parsed) if parsed is not None else None
        except (TypeError, ValueError, json.JSONDecodeError):
            string_value = None

        if key == ORGANIZATION_SID_KEY:
            result["organization_sid"] = string_value
        elif key == ORGANIZATION_NAME_KEY:
            result["organization_name"] = string_value

    return result


async def set_organization_settings(
    db: Connection,
    guild_id: int,
    organization_sid: str | None,
    organization_name: str | None,
) -> None:
    """Persist organization settings for a guild."""
    # Normalize SID to uppercase if provided
    normalized_sid = organization_sid.upper() if organization_sid else None

    payloads = [
        (ORGANIZATION_SID_KEY, json.dumps(normalized_sid)),
        (ORGANIZATION_NAME_KEY, json.dumps(organization_name)),
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

    await _touch_settings_version(db, guild_id, source="organization")
    await db.commit()
