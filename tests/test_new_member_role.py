"""
Tests for the new-member role lifecycle service.

Covers:
- Eligibility checks (server-age gate, missing joined_at)
- First-verification-only assignment
- Duplicate assignment prevention
- Expiry processing
- Manual removal cancellation
- Config parsing
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from services.db.database import Database
from services.new_member_role_service import (
    _has_previous_assignment,
    _insert_assignment,
    assign_if_eligible,
    get_active_assignment,
    get_expired_assignments,
    get_new_member_config,
    is_eligible,
    mark_removed,
    process_expired_roles,
    remove_expired_role,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def temp_db(tmp_path):
    """Initialize Database to a temporary file for isolation across tests."""
    orig_path = Database._db_path
    orig_initialized = Database._initialized
    Database._initialized = False
    Database._db_path = None  # type: ignore[assignment]
    db_file = tmp_path / "test.db"
    await Database.initialize(str(db_file))
    yield str(db_file)
    Database._db_path = orig_path
    Database._initialized = orig_initialized


def _make_member(
    user_id: int = 100,
    guild_id: int = 1,
    roles: list | None = None,
    joined_at: datetime | None = None,
    nick: str | None = None,
) -> MagicMock:
    """Return a fake discord.Member-like object."""
    member = MagicMock()
    member.id = user_id
    member.nick = nick
    member.display_name = f"User{user_id}"
    member.joined_at = joined_at

    guild = MagicMock()
    guild.id = guild_id
    guild.name = f"Guild{guild_id}"

    role_obj = MagicMock()
    role_obj.id = 555
    role_obj.name = "NewMember"
    guild.get_role = MagicMock(return_value=role_obj)

    member.guild = guild
    member.roles = roles or []
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


def _make_bot(
    *,
    enabled: bool = True,
    role_id: str = "555",
    duration_days: int = 14,
    max_server_age_days: int | None = None,
    guilds: list | None = None,
) -> MagicMock:
    """Return a fake bot with services.config resolving new-member settings."""
    cfg = MagicMock()

    settings: dict[str, Any] = {
        "new_member_role.enabled": enabled,
        "new_member_role.role_id": role_id,
        "new_member_role.duration_days": duration_days,
        "new_member_role.max_server_age_days": max_server_age_days,
    }

    async def fake_get(guild_id: int, key: str, default: Any = None, parser: Any = None) -> Any:
        val = settings.get(key, default)
        if parser and val is not None and val != default:
            return parser(val)
        return val

    async def fake_get_guild_setting(guild_id: int, key: str, default: Any = None) -> Any:
        return settings.get(key, default)

    cfg.get = fake_get
    cfg.get_guild_setting = fake_get_guild_setting

    services = SimpleNamespace(config=cfg)
    bot = MagicMock()
    bot.services = services
    bot.guilds = guilds or []
    bot.get_guild = MagicMock(return_value=None)
    return bot


# ---------------------------------------------------------------------------
# Eligibility tests
# ---------------------------------------------------------------------------


class TestIsEligible:
    """Tests for the server-age eligibility gate."""

    def test_no_gate_always_eligible(self) -> None:
        member = _make_member(joined_at=datetime.now(timezone.utc) - timedelta(days=365))
        assert is_eligible(member, max_server_age_days=None) is True

    def test_member_within_gate(self) -> None:
        member = _make_member(joined_at=datetime.now(timezone.utc) - timedelta(days=5))
        assert is_eligible(member, max_server_age_days=14) is True

    def test_member_outside_gate(self) -> None:
        member = _make_member(joined_at=datetime.now(timezone.utc) - timedelta(days=30))
        assert is_eligible(member, max_server_age_days=14) is False

    def test_missing_joined_at_passes(self) -> None:
        """Missing joined_at should fail-open (grant role)."""
        member = _make_member(joined_at=None)
        assert is_eligible(member, max_server_age_days=14) is True

    def test_exactly_on_boundary(self) -> None:
        """Member exactly at the boundary is NOT eligible (age < threshold)."""
        member = _make_member(joined_at=datetime.now(timezone.utc) - timedelta(days=14))
        assert is_eligible(member, max_server_age_days=14) is False


# ---------------------------------------------------------------------------
# Config parsing tests
# ---------------------------------------------------------------------------


class TestGetNewMemberConfig:
    """Tests for config parsing."""

    @pytest.mark.asyncio
    async def test_defaults_when_disabled(self) -> None:
        bot = _make_bot(enabled=False, role_id="555")
        cfg = await get_new_member_config(bot.services.config, 1)
        assert cfg["enabled"] is False
        assert cfg["role_id"] == "555"
        assert cfg["duration_days"] == 14
        assert cfg["max_server_age_days"] is None

    @pytest.mark.asyncio
    async def test_custom_values(self) -> None:
        bot = _make_bot(enabled=True, role_id="777", duration_days=30, max_server_age_days=7)
        cfg = await get_new_member_config(bot.services.config, 1)
        assert cfg["enabled"] is True
        assert cfg["role_id"] == "777"
        assert cfg["duration_days"] == 30
        assert cfg["max_server_age_days"] == 7


# ---------------------------------------------------------------------------
# Database helper tests
# ---------------------------------------------------------------------------


class TestDatabaseHelpers:
    """Tests for low-level DB functions."""

    @pytest.mark.asyncio
    async def test_insert_and_check(self, temp_db) -> None:
        assert await _has_previous_assignment(1, 100) is False
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now, now + 86400)
        assert await _has_previous_assignment(1, 100) is True

    @pytest.mark.asyncio
    async def test_get_active_assignment(self, temp_db) -> None:
        assert await get_active_assignment(1, 100) is None
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now, now + 86400)
        result = await get_active_assignment(1, 100)
        assert result is not None
        assert result[0] == 555  # role_id
        assert result[3] == 1   # active

    @pytest.mark.asyncio
    async def test_mark_removed(self, temp_db) -> None:
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now, now + 86400)
        await mark_removed(1, 100, reason="manual")
        assert await get_active_assignment(1, 100) is None

    @pytest.mark.asyncio
    async def test_get_expired_assignments(self, temp_db) -> None:
        now = int(time.time())
        # Active and expired
        await _insert_assignment(1, 100, 555, now - 100, now - 10)
        # Active and not expired
        await _insert_assignment(1, 200, 555, now, now + 86400)
        expired = await get_expired_assignments()
        assert len(expired) == 1
        assert expired[0] == (1, 100, 555)

    @pytest.mark.asyncio
    async def test_duplicate_insert_ignored(self, temp_db) -> None:
        """INSERT OR IGNORE ensures no error on duplicate PK."""
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now, now + 86400)
        # Second insert for same (guild, user) should be silently ignored
        await _insert_assignment(1, 100, 999, now, now + 999)
        result = await get_active_assignment(1, 100)
        assert result is not None
        assert result[0] == 555  # original role_id preserved


# ---------------------------------------------------------------------------
# assign_if_eligible tests
# ---------------------------------------------------------------------------


class TestAssignIfEligible:
    """Tests for the main assignment entry point."""

    @pytest.mark.asyncio
    async def test_assign_success(self, temp_db) -> None:
        member = _make_member(joined_at=datetime.now(timezone.utc) - timedelta(days=1))
        bot = _make_bot(enabled=True)
        result = await assign_if_eligible(member, bot)
        assert result is True
        member.add_roles.assert_called_once()

    @pytest.mark.asyncio
    async def test_disabled_module_skips(self, temp_db) -> None:
        member = _make_member()
        bot = _make_bot(enabled=False)
        result = await assign_if_eligible(member, bot)
        assert result is False
        member.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_role_configured_skips(self, temp_db) -> None:
        member = _make_member()
        bot = _make_bot(enabled=True, role_id="")
        # role_id="" should parse to None
        result = await assign_if_eligible(member, bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_first_verification_only(self, temp_db) -> None:
        """Second call for same user+guild should not assign again."""
        member = _make_member(joined_at=datetime.now(timezone.utc))
        bot = _make_bot(enabled=True)
        assert await assign_if_eligible(member, bot) is True
        assert await assign_if_eligible(member, bot) is False
        assert member.add_roles.call_count == 1

    @pytest.mark.asyncio
    async def test_server_age_gate_blocks(self, temp_db) -> None:
        member = _make_member(
            joined_at=datetime.now(timezone.utc) - timedelta(days=60)
        )
        bot = _make_bot(enabled=True, max_server_age_days=30)
        result = await assign_if_eligible(member, bot)
        assert result is False
        member.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_server_age_gate_allows(self, temp_db) -> None:
        member = _make_member(
            joined_at=datetime.now(timezone.utc) - timedelta(days=5)
        )
        bot = _make_bot(enabled=True, max_server_age_days=30)
        result = await assign_if_eligible(member, bot)
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_joined_at_allowed(self, temp_db) -> None:
        """If joined_at is None and gate is set, still assign."""
        member = _make_member(joined_at=None)
        bot = _make_bot(enabled=True, max_server_age_days=30)
        result = await assign_if_eligible(member, bot)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_services_returns_false(self, temp_db) -> None:
        member = _make_member()
        bot = MagicMock()
        bot.services = None
        assert await assign_if_eligible(member, bot) is False

    @pytest.mark.asyncio
    async def test_role_not_found_in_guild(self, temp_db) -> None:
        member = _make_member()
        member.guild.get_role = MagicMock(return_value=None)
        bot = _make_bot(enabled=True)
        result = await assign_if_eligible(member, bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_discord_api_error_returns_false(self, temp_db) -> None:
        member = _make_member(joined_at=datetime.now(timezone.utc))
        member.add_roles = AsyncMock(side_effect=Exception("Forbidden"))
        bot = _make_bot(enabled=True)
        result = await assign_if_eligible(member, bot)
        assert result is False
        # No DB record should be created on Discord failure
        assert await get_active_assignment(1, 100) is None


# ---------------------------------------------------------------------------
# Expiry processing tests
# ---------------------------------------------------------------------------


class TestExpiryProcessing:
    """Tests for removing expired roles."""

    @pytest.mark.asyncio
    async def test_remove_expired_role_success(self, temp_db) -> None:
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now - 200, now - 10)

        member = _make_member()
        role_obj = MagicMock()
        role_obj.id = 555
        guild = MagicMock()
        guild.get_member = MagicMock(return_value=member)
        guild.get_role = MagicMock(return_value=role_obj)

        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=guild)

        result = await remove_expired_role(1, 100, 555, bot)
        assert result is True
        member.remove_roles.assert_called_once()
        assert await get_active_assignment(1, 100) is None

    @pytest.mark.asyncio
    async def test_remove_expired_member_gone(self, temp_db) -> None:
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now - 200, now - 10)

        guild = MagicMock()
        guild.get_member = MagicMock(return_value=None)
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=guild)

        result = await remove_expired_role(1, 100, 555, bot)
        assert result is False
        # Should still mark as removed
        assert await get_active_assignment(1, 100) is None

    @pytest.mark.asyncio
    async def test_process_expired_roles_batch(self, temp_db) -> None:
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now - 200, now - 10)
        await _insert_assignment(1, 200, 555, now - 200, now - 10)

        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)

        count = await process_expired_roles(bot, batch_size=50)
        assert count == 2


# ---------------------------------------------------------------------------
# Manual removal tests
# ---------------------------------------------------------------------------


class TestManualRemoval:
    """Tests for the mark_removed flow."""

    @pytest.mark.asyncio
    async def test_mark_removed_cancels_assignment(self, temp_db) -> None:
        now = int(time.time())
        await _insert_assignment(1, 100, 555, now, now + 86400)
        await mark_removed(1, 100, reason="manual")
        assert await get_active_assignment(1, 100) is None
        # Still has a record (prevents re-assignment)
        assert await _has_previous_assignment(1, 100) is True

    @pytest.mark.asyncio
    async def test_mark_removed_no_active_is_noop(self, temp_db) -> None:
        """Calling mark_removed when no active assignment should not error."""
        await mark_removed(1, 999, reason="manual")
