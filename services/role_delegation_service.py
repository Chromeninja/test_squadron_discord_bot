"""Service handling role delegation policies and enforcement."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from helpers.discord_api import add_roles
from services.base import BaseService
from utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    import discord


class RoleDelegationService(BaseService):
    """Enforces per-guild role delegation policies for controlled grants."""

    def __init__(self, config_service, bot) -> None:
        super().__init__("role_delegation")
        self.config = config_service
        self.bot = bot
        self.logger = get_logger("services.role_delegation")

    async def _initialize_impl(self) -> None:  # pragma: no cover - no startup work
        # Config is loaded by ConfigService; nothing else to bootstrap.
        return None

    async def get_policies(self, guild_id: int) -> list[dict[str, Any]]:
        """Return normalized delegation policies for a guild."""
        self._ensure_initialized()
        raw = await self.config.get_guild_setting(
            guild_id, "roles.delegation_policies", []
        )
        policies = self._normalize_policies(raw, guild_id)
        self.logger.debug(
            "Loaded %s delegation policies for guild %s", len(policies), guild_id
        )
        return policies

    async def can_grant(
        self,
        guild: discord.Guild,
        grantor_member: discord.Member,
        target_member: discord.Member,
        role_id: int | str,
    ) -> tuple[bool, str]:
        """Check if grantor can grant role_id to target under delegation policies."""
        self._ensure_initialized()

        try:
            target_role_id = int(role_id)
        except (TypeError, ValueError):
            return False, "Invalid role id"

        policies = await self.get_policies(guild.id)
        if not policies:
            return False, "No delegation policies configured for this server"

        grantor_roles = _role_id_set(grantor_member.roles)
        target_roles = _role_id_set(target_member.roles)

        applicable = [
            p
            for p in policies
            if p.get("enabled", True)
            and p.get("granted_role") == target_role_id
            and grantor_roles.intersection(p.get("grantor_roles", []))
        ]
        if not applicable:
            return False, "You do not have permission to grant that role"

        for policy in applicable:
            reqs = policy.get("requirements", {})
            required = set(reqs.get("required_roles", []))
            any_roles = set(reqs.get("any_roles", []))
            forbidden = set(reqs.get("forbidden_roles", []))

            missing = required - target_roles
            if missing:
                return False, self._format_reason(guild, "missing_required", missing)

            if any_roles and not target_roles.intersection(any_roles):
                return False, self._format_reason(guild, "missing_any", any_roles)

            if target_roles.intersection(forbidden):
                return False, self._format_reason(guild, "has_forbidden", forbidden)

            return True, ""

        return False, "No matching delegation policy"

    async def apply_grant(
        self,
        guild: discord.Guild,
        grantor_member: discord.Member,
        target_member: discord.Member,
        role_id: int | str,
        reason: str | None = None,
    ) -> tuple[bool, str]:
        """Validate delegation policy and apply the role to the target member."""
        allowed, message = await self.can_grant(
            guild, grantor_member, target_member, role_id
        )
        if not allowed:
            return False, message

        try:
            role_obj = guild.get_role(int(role_id))
        except (TypeError, ValueError):
            role_obj = None

        if role_obj is None:
            return False, "Role not found in guild"

        apply_reason = reason or "Delegated role grant"
        try:
            await add_roles(target_member, role_obj, reason=apply_reason)
        except Exception:  # pragma: no cover - Discord API errors
            self.logger.exception(
                "Failed to apply delegated role",
                extra={
                    "guild_id": guild.id,
                    "grantor_id": grantor_member.id,
                    "target_id": target_member.id,
                    "role_id": role_id,
                },
            )
            return False, "Failed to grant role"

        self.logger.info(
            "Delegated role granted",
            extra={
                "guild_id": guild.id,
                "grantor_id": grantor_member.id,
                "target_id": target_member.id,
                "role_id": int(role_id),
                "reason": apply_reason,
            },
        )
        return True, ""

    def _format_reason(
        self, guild: discord.Guild, code: str, role_ids: set[int] | list[int]
    ) -> str:
        if not role_ids:
            return ""

        role_list = self._format_role_list(guild, role_ids)

        if code == "missing_required":
            return f"Member is missing required role(s): {role_list}"
        if code == "missing_any":
            return f"Member needs at least one of these roles: {role_list}"
        if code == "has_forbidden":
            return f"Member has a role that blocks this grant: {role_list}"
        return "Delegation policy check failed"

    def _format_role_list(
        self, guild: discord.Guild, role_ids: set[int] | list[int]
    ) -> str:
        formatted: list[str] = []
        for rid in sorted(role_ids):
            role_obj = guild.get_role(rid) if hasattr(guild, "get_role") else None
            mention = getattr(role_obj, "mention", None) if role_obj else None
            name = getattr(role_obj, "name", None) if role_obj else None
            formatted.append(mention or name or f"<@&{rid}>")
        return ", ".join(formatted)

    def _normalize_policies(
        self, raw_policies: Any, guild_id: int
    ) -> list[dict[str, Any]]:
        if not raw_policies:
            return []
        if not isinstance(raw_policies, list):
            return []

        normalized: list[dict[str, Any]] = []
        for policy in raw_policies:
            if not isinstance(policy, dict):
                continue

            grantor_roles = _role_id_list(
                policy.get("grantor_role_ids") or policy.get("grantor_roles")
            )
            granted_role = _role_id_scalar(
                policy.get("target_role_id") or policy.get("granted_role")
            )

            requirements = policy.get("requirements") or {}
            required_roles = _role_id_list(
                policy.get("prerequisite_role_ids")
                or policy.get("prerequisite_role_ids_all")
                or requirements.get("required_roles")
            )
            any_roles = _role_id_list(
                policy.get("prerequisite_role_ids_any") or requirements.get("any_roles")
            )
            forbidden_roles = _role_id_list(requirements.get("forbidden_roles"))

            normalized.append(
                {
                    "grantor_roles": grantor_roles,
                    "granted_role": granted_role,
                    "requirements": {
                        "required_roles": required_roles,
                        "any_roles": any_roles,
                        "forbidden_roles": forbidden_roles,
                    },
                    "notes": policy.get("notes") or policy.get("note"),
                    "enabled": bool(policy.get("enabled", True)),
                }
            )

        return normalized


def _role_id_list(values: Any) -> list[int]:
    if values is None:
        return []
    normalized: list[int] = []
    seen: set[int] = set()

    def _iter(val: Any) -> Iterable[Any]:
        if isinstance(val, (list, tuple, set)):
            for item in val:
                yield from _iter(item)
        else:
            yield val

    for raw in _iter(values):
        try:
            rid = int(str(raw))
        except (TypeError, ValueError):
            continue
        if rid < 0 or rid in seen:
            continue
        seen.add(rid)
        normalized.append(rid)
    return normalized


def _role_id_scalar(value: Any) -> int | None:
    try:
        rid = int(str(value))
    except (TypeError, ValueError):
        return None
    return rid if rid >= 0 else None


def _role_id_set(roles: Iterable[discord.abc.Snowflake]) -> set[int]:
    ids: set[int] = set()
    for role in roles:
        rid = getattr(role, "id", None)
        if isinstance(rid, int):
            ids.add(rid)
    return ids
