import pytest
from core.dependencies import _has_minimum_role
from core.role_utils import (
    can_assume_role,
    clear_guild_assumed_role,
    normalize_guild_permission,
    set_guild_assumed_role,
)

pytestmark = pytest.mark.contract


def test_event_coordinator_sits_between_staff_and_moderator() -> None:
    """Event coordinator should satisfy staff access but not moderator access."""
    assert _has_minimum_role("event_coordinator", "staff") is True
    assert _has_minimum_role("event_coordinator", "event_coordinator") is True
    assert _has_minimum_role("event_coordinator", "moderator") is False


def test_bot_owner_can_assume_lower_roles_only() -> None:
    """Role switching should only allow explicit downgrades."""
    assert can_assume_role("bot_owner", "bot_admin") is True
    assert can_assume_role("bot_owner", "staff") is True
    assert can_assume_role("bot_owner", "user") is True
    assert can_assume_role("bot_owner", "bot_owner") is False
    assert can_assume_role("moderator", "bot_admin") is False


def test_assumed_role_updates_effective_role_without_losing_base_role() -> None:
    """Assumed roles should downgrade effective access while preserving source role."""
    permission = normalize_guild_permission(
        "123",
        {"guild_id": "123", "role_level": "bot_owner", "source": "bot_owner"},
    )

    assumed = set_guild_assumed_role(permission, "123", "staff")

    assert assumed.base_role_level == "bot_owner"
    assert assumed.assumed_role_level == "staff"
    assert assumed.role_level == "staff"

    cleared = clear_guild_assumed_role(assumed, "123")
    assert cleared.base_role_level == "bot_owner"
    assert cleared.assumed_role_level is None
    assert cleared.role_level == "bot_owner"
