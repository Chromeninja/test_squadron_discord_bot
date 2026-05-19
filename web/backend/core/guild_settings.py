"""Utility helpers for reading and writing guild_settings records."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from services.db.repository import BaseRepository
from core.logo_validator import LogoValidationError, validate_logo_url

if TYPE_CHECKING:
    from aiosqlite import Connection

logger = logging.getLogger(__name__)


BOT_ADMINS_KEY = "roles.bot_admins"
MODERATORS_KEY = "roles.moderators"
DISCORD_MANAGERS_KEY = "roles.discord_managers"
EVENT_COORDINATORS_KEY = "roles.event_coordinators"
STAFF_KEY = "roles.staff"
BOT_VERIFIED_ROLE_KEY = "roles.bot_verified_role"
MAIN_ROLE_KEY = "roles.main_role"
AFFILIATE_ROLE_KEY = "roles.affiliate_role"
NONMEMBER_ROLE_KEY = "roles.nonmember_role"
SELECTABLE_ROLES_KEY = "selectable_roles"
DELEGATION_POLICIES_KEY = "roles.delegation_policies"
ROLE_DELEGATION_POLICIES_KEY = DELEGATION_POLICIES_KEY

SETTINGS_VERSION_KEY = "meta.settings_version"
SETTINGS_VERSION_ROLES_SOURCE = "bot_roles"
SETTINGS_VERSION_DELEGATION_SOURCE = "role_delegation"

VERIFICATION_CHANNEL_KEY = "channels.verification_channel_id"
BOT_SPAM_CHANNEL_KEY = "channels.bot_spam_channel_id"
PUBLIC_ANNOUNCEMENT_CHANNEL_KEY = "channels.public_announcement_channel_id"
LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY = "channels.leadership_announcement_channel_id"
METRICS_EXCLUDED_CHANNEL_IDS_KEY = "metrics.excluded_channel_ids"
METRICS_TRACKED_GAMES_MODE_KEY = "metrics.tracked_games_mode"
METRICS_TRACKED_GAMES_KEY = "metrics.tracked_games"
METRICS_MIN_VOICE_MINUTES_KEY = "metrics.min_voice_minutes"
METRICS_MIN_GAME_MINUTES_KEY = "metrics.min_game_minutes"
METRICS_MIN_MESSAGES_KEY = "metrics.min_messages"
EVENTS_ENABLED_KEY = "events.enabled"
EVENTS_DEFAULT_NATIVE_SYNC_KEY = "events.default_native_sync"
EVENTS_DEFAULT_ANNOUNCEMENT_CHANNEL_KEY = "events.default_announcement_channel_id"
EVENTS_DEFAULT_VOICE_CHANNEL_KEY = "events.default_voice_channel_id"

ORGANIZATION_SID_KEY = "organization.sid"
ORGANIZATION_NAME_KEY = "organization.name"
ORGANIZATION_LOGO_URL_KEY = "organization.logo_url"

# New-member role keys
NEW_MEMBER_ROLE_ENABLED_KEY = "new_member_role.enabled"
NEW_MEMBER_ROLE_ID_KEY = "new_member_role.role_id"
NEW_MEMBER_ROLE_DURATION_DAYS_KEY = "new_member_role.duration_days"
NEW_MEMBER_ROLE_MAX_SERVER_AGE_DAYS_KEY = "new_member_role.max_server_age_days"
SETTINGS_VERSION_NEW_MEMBER_ROLE_SOURCE = "new_member_role"


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


def _coerce_channel_list(value: Any) -> list[str]:
    """Convert stored JSON values into a list of unique string channel IDs."""
    return _coerce_role_list(value)


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


def _normalize_delegation_policies(
    value: list | None, *, strict: bool = False
) -> list[dict]:
    """Normalize delegation policies to the new schema shape with string snowflakes.

    Supports older keys (grantor_roles/granted_role/requirements.required_roles)
    and new keys (grantor_role_ids/target_role_id/prerequisite_role_ids_all/
    prerequisite_role_ids_any).

    If ``strict`` is True, a ``ValueError`` is raised when a policy is missing a
    usable ``target_role_id`` instead of silently dropping it. This prevents the
    UI from appearing to save successfully while losing the policy.
    """
    if not value:
        return []

    normalized: list[dict] = []
    invalid_indices: list[int] = []

    for idx, policy in enumerate(value):
        if isinstance(policy, dict):
            data = policy
        elif hasattr(policy, "model_dump"):
            data = policy.model_dump()
        else:
            continue

        grantor_roles = data.get("grantor_role_ids") or data.get("grantor_roles")
        target_role_raw = data.get("target_role_id") or data.get("granted_role")

        requirements = data.get("requirements") or {}
        prereq_all = (
            data.get("prerequisite_role_ids_all")
            or data.get("prerequisite_role_ids")
            or requirements.get("required_roles")
        )
        prereq_any = data.get("prerequisite_role_ids_any")

        try:
            target_role_id = (
                str(int(target_role_raw)) if target_role_raw is not None else None
            )
        except (TypeError, ValueError):
            target_role_id = None

        if target_role_id is None:
            invalid_indices.append(idx)
            continue

        normalized.append(
            {
                "grantor_role_ids": _normalize_policy_roles(grantor_roles),
                "target_role_id": target_role_id,
                "prerequisite_role_ids_all": _normalize_policy_roles(prereq_all),
                "prerequisite_role_ids": _normalize_policy_roles(prereq_all),
                "prerequisite_role_ids_any": _normalize_policy_roles(prereq_any),
                "enabled": bool(data.get("enabled", True)),
                "note": data.get("note") or data.get("notes"),
            }
        )

    if strict and invalid_indices:
        raise ValueError(
            "One or more delegation policies are missing a valid target_role_id "
            f"(invalid entries at index/indices: {invalid_indices})."
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


async def get_bot_role_settings(db: Connection, guild_id: int) -> dict:
    """Fetch bot role settings for a guild with sensible defaults.

    Returns dict with keys: bot_admins, discord_managers, moderators,
    event_coordinators, staff,
    main_role, affiliate_role, nonmember_role (all list[str]), and
    delegation_policies (list[dict]).
    """
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor = await db.execute(
        query,
        (
            guild_id,
            BOT_ADMINS_KEY,
            MODERATORS_KEY,
            DISCORD_MANAGERS_KEY,
            EVENT_COORDINATORS_KEY,
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
        "event_coordinators": [],
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
        elif key == EVENT_COORDINATORS_KEY:
            result["event_coordinators"] = _coerce_role_list(value)
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
    event_coordinators: list[str],
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
        (EVENT_COORDINATORS_KEY, json.dumps(_normalize_role_ids(event_coordinators))),
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


async def get_metrics_settings(db: Connection, guild_id: int) -> dict[str, Any]:
    """Fetch metrics settings for a guild."""
    cursor = await db.execute(
        """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            METRICS_EXCLUDED_CHANNEL_IDS_KEY,
            METRICS_TRACKED_GAMES_MODE_KEY,
            METRICS_TRACKED_GAMES_KEY,
            METRICS_MIN_VOICE_MINUTES_KEY,
            METRICS_MIN_GAME_MINUTES_KEY,
            METRICS_MIN_MESSAGES_KEY,
        ),
    )
    rows = await cursor.fetchall()

    result: dict[str, Any] = {
        "excluded_channel_ids": [],
        "tracked_games_mode": "all",
        "tracked_games": [],
        "min_voice_minutes": 15,
        "min_game_minutes": 15,
        "min_messages": 5,
    }
    for key, value in rows:
        if key == METRICS_EXCLUDED_CHANNEL_IDS_KEY:
            result["excluded_channel_ids"] = _coerce_channel_list(value)
        elif key == METRICS_TRACKED_GAMES_MODE_KEY:
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                result["tracked_games_mode"] = (
                    parsed if parsed in ("all", "specific") else "all"
                )
            except (TypeError, json.JSONDecodeError):
                pass
        elif key == METRICS_TRACKED_GAMES_KEY:
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                result["tracked_games"] = (
                    [str(g) for g in parsed] if isinstance(parsed, list) else []
                )
            except (TypeError, json.JSONDecodeError):
                pass
        elif key == METRICS_MIN_VOICE_MINUTES_KEY:
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                result["min_voice_minutes"] = max(0, int(parsed))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        elif key == METRICS_MIN_GAME_MINUTES_KEY:
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                result["min_game_minutes"] = max(0, int(parsed))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        elif key == METRICS_MIN_MESSAGES_KEY:
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                result["min_messages"] = max(0, int(parsed))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    return result


async def set_metrics_settings(
    db: Connection,
    guild_id: int,
    excluded_channel_ids: list[str],
    tracked_games_mode: str = "all",
    tracked_games: list[str] | None = None,
    min_voice_minutes: int = 15,
    min_game_minutes: int = 15,
    min_messages: int = 5,
) -> None:
    """Persist metrics settings for a guild."""

    normalized: list[str] = []
    seen = set()
    for value in excluded_channel_ids:
        try:
            channel_id = str(int(value))
        except (TypeError, ValueError):
            continue
        if channel_id in seen:
            continue
        seen.add(channel_id)
        normalized.append(channel_id)

    normalized.sort(key=lambda x: int(x))

    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, METRICS_EXCLUDED_CHANNEL_IDS_KEY, json.dumps(normalized)),
    )

    # Tracked games mode
    mode = tracked_games_mode if tracked_games_mode in ("all", "specific") else "all"
    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, METRICS_TRACKED_GAMES_MODE_KEY, json.dumps(mode)),
    )

    # Tracked games list
    games_list = (
        [str(g).strip() for g in tracked_games if str(g).strip()]
        if tracked_games
        else []
    )
    await db.execute(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        (guild_id, METRICS_TRACKED_GAMES_KEY, json.dumps(games_list)),
    )

    # Activity thresholds
    for threshold_key, threshold_val in (
        (METRICS_MIN_VOICE_MINUTES_KEY, max(0, int(min_voice_minutes))),
        (METRICS_MIN_GAME_MINUTES_KEY, max(0, int(min_game_minutes))),
        (METRICS_MIN_MESSAGES_KEY, max(0, int(min_messages))),
    ):
        await db.execute(
            """
            INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            """,
            (guild_id, threshold_key, json.dumps(threshold_val)),
        )

    await _touch_settings_version(db, guild_id, source="metrics_settings")
    await db.commit()


async def get_organization_settings(
    db: Connection, guild_id: int
) -> dict[str, str | None]:
    """Fetch organization settings for a guild."""
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?)
    """
    cursor = await db.execute(
        query,
        (
            guild_id,
            ORGANIZATION_SID_KEY,
            ORGANIZATION_NAME_KEY,
            ORGANIZATION_LOGO_URL_KEY,
        ),
    )
    rows = await cursor.fetchall()

    result: dict[str, str | None] = {
        "organization_sid": None,
        "organization_name": None,
        "organization_logo_url": None,
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
        elif key == ORGANIZATION_LOGO_URL_KEY:
            result["organization_logo_url"] = string_value

    return result


async def set_organization_settings(
    db: Connection,
    guild_id: int,
    organization_sid: str | None,
    organization_name: str | None,
    organization_logo_url: str | None = None,
) -> None:
    """Persist organization settings for a guild."""
    # Normalize SID to uppercase if provided
    normalized_sid = organization_sid.upper() if organization_sid else None

    payloads = [
        (ORGANIZATION_SID_KEY, json.dumps(normalized_sid)),
        (ORGANIZATION_NAME_KEY, json.dumps(organization_name)),
        (ORGANIZATION_LOGO_URL_KEY, json.dumps(organization_logo_url)),
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


# -----------------------------------------------------------------------------
# Standalone BaseRepository-based functions (no db parameter required)
# -----------------------------------------------------------------------------


async def fetch_bot_role_settings(guild_id: int) -> dict:
    """Fetch bot role settings for a guild using BaseRepository.

    Standalone version that doesn't require a db connection parameter.

    Returns dict with keys: bot_admins, discord_managers, moderators,
    event_coordinators, staff,
    main_role, affiliate_role, nonmember_role (all list[str]), and
    delegation_policies (list[dict]).
    """
    query = """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    rows = await BaseRepository.fetch_all(
        query,
        (
            guild_id,
            BOT_ADMINS_KEY,
            MODERATORS_KEY,
            DISCORD_MANAGERS_KEY,
            EVENT_COORDINATORS_KEY,
            STAFF_KEY,
            BOT_VERIFIED_ROLE_KEY,
            MAIN_ROLE_KEY,
            AFFILIATE_ROLE_KEY,
            NONMEMBER_ROLE_KEY,
            DELEGATION_POLICIES_KEY,
        ),
    )

    result = {
        "bot_admins": [],
        "discord_managers": [],
        "moderators": [],
        "event_coordinators": [],
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
        elif key == EVENT_COORDINATORS_KEY:
            result["event_coordinators"] = _coerce_role_list(value)
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


async def fetch_role_delegation_policies(guild_id: int) -> list[dict]:
    """Fetch delegation policies for a guild using BaseRepository.

    Standalone version that doesn't require a db connection parameter.
    """
    row = await BaseRepository.fetch_one(
        """
        SELECT value FROM guild_settings
        WHERE guild_id = ? AND key = ?
        """,
        (guild_id, DELEGATION_POLICIES_KEY),
    )
    if not row:
        return []
    return _coerce_policy_list(row[0])


# ---------------------------------------------------------------------------
# New-member role settings
# ---------------------------------------------------------------------------


async def get_new_member_role_settings(db: Connection, guild_id: int) -> dict[str, Any]:
    """Fetch new-member role settings for a guild."""
    cursor = await db.execute(
        """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?)
        """,
        (
            guild_id,
            NEW_MEMBER_ROLE_ENABLED_KEY,
            NEW_MEMBER_ROLE_ID_KEY,
            NEW_MEMBER_ROLE_DURATION_DAYS_KEY,
            NEW_MEMBER_ROLE_MAX_SERVER_AGE_DAYS_KEY,
        ),
    )
    rows = await cursor.fetchall()

    result: dict[str, Any] = {
        "enabled": False,
        "role_id": None,
        "duration_days": 14,
        "max_server_age_days": None,
    }

    for key, value in rows:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            continue

        if key == NEW_MEMBER_ROLE_ENABLED_KEY:
            result["enabled"] = bool(parsed)
        elif key == NEW_MEMBER_ROLE_ID_KEY:
            if parsed is not None:
                try:
                    result["role_id"] = str(int(parsed))
                except (TypeError, ValueError):
                    result["role_id"] = None
            else:
                result["role_id"] = None
        elif key == NEW_MEMBER_ROLE_DURATION_DAYS_KEY:
            try:
                result["duration_days"] = max(1, int(parsed))
            except (TypeError, ValueError):
                pass
        elif key == NEW_MEMBER_ROLE_MAX_SERVER_AGE_DAYS_KEY:
            if parsed is not None:
                try:
                    result["max_server_age_days"] = max(1, int(parsed))
                except (TypeError, ValueError):
                    pass

    return result


async def set_new_member_role_settings(
    db: Connection,
    guild_id: int,
    *,
    enabled: bool,
    role_id: str | None,
    duration_days: int,
    max_server_age_days: int | None,
) -> None:
    """Persist new-member role settings for a guild."""
    # Normalize
    normalized_role_id: str | None = None
    if role_id is not None:
        try:
            normalized_role_id = str(int(role_id))
        except (TypeError, ValueError):
            normalized_role_id = None

    payloads = [
        (NEW_MEMBER_ROLE_ENABLED_KEY, json.dumps(enabled)),
        (NEW_MEMBER_ROLE_ID_KEY, json.dumps(normalized_role_id)),
        (NEW_MEMBER_ROLE_DURATION_DAYS_KEY, json.dumps(max(1, duration_days))),
        (NEW_MEMBER_ROLE_MAX_SERVER_AGE_DAYS_KEY, json.dumps(max_server_age_days)),
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

    await _touch_settings_version(
        db, guild_id, source=SETTINGS_VERSION_NEW_MEMBER_ROLE_SOURCE
    )
    await db.commit()


async def get_event_module_settings(db: Connection, guild_id: int) -> dict[str, Any]:
    """Fetch event module settings for a guild."""
    cursor = await db.execute(
        """
        SELECT key, value
        FROM guild_settings
        WHERE guild_id = ? AND key IN (?, ?, ?, ?)
        """,
        (
            guild_id,
            EVENTS_ENABLED_KEY,
            EVENTS_DEFAULT_NATIVE_SYNC_KEY,
            EVENTS_DEFAULT_ANNOUNCEMENT_CHANNEL_KEY,
            EVENTS_DEFAULT_VOICE_CHANNEL_KEY,
        ),
    )
    rows = await cursor.fetchall()

    result: dict[str, Any] = {
        "enabled": True,
        "default_native_sync": True,
        "default_announcement_channel_id": None,
        "default_voice_channel_id": None,
    }

    for key, value in rows:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            continue

        if key == EVENTS_ENABLED_KEY:
            result["enabled"] = bool(parsed)
        elif key == EVENTS_DEFAULT_NATIVE_SYNC_KEY:
            result["default_native_sync"] = bool(parsed)
        elif key == EVENTS_DEFAULT_ANNOUNCEMENT_CHANNEL_KEY:
            if parsed is not None:
                try:
                    result["default_announcement_channel_id"] = str(int(parsed))
                except (TypeError, ValueError):
                    result["default_announcement_channel_id"] = None
        elif key == EVENTS_DEFAULT_VOICE_CHANNEL_KEY:
            if parsed is not None:
                try:
                    result["default_voice_channel_id"] = str(int(parsed))
                except (TypeError, ValueError):
                    result["default_voice_channel_id"] = None

    return result


async def set_event_module_settings(
    db: Connection,
    guild_id: int,
    *,
    enabled: bool,
    default_native_sync: bool,
    default_announcement_channel_id: str | None,
    default_voice_channel_id: str | None,
) -> None:
    """Persist event module settings for a guild."""

    def _normalize_channel_id(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return None

    payloads = [
        (EVENTS_ENABLED_KEY, json.dumps(enabled)),
        (EVENTS_DEFAULT_NATIVE_SYNC_KEY, json.dumps(default_native_sync)),
        (
            EVENTS_DEFAULT_ANNOUNCEMENT_CHANNEL_KEY,
            json.dumps(_normalize_channel_id(default_announcement_channel_id)),
        ),
        (
            EVENTS_DEFAULT_VOICE_CHANNEL_KEY,
            json.dumps(_normalize_channel_id(default_voice_channel_id)),
        ),
    ]

    await db.executemany(
        """
        INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
        VALUES (?, ?, ?)
        """,
        [(guild_id, key, value) for key, value in payloads],
    )
    await _touch_settings_version(db, guild_id, source="event_module")
    await db.commit()
