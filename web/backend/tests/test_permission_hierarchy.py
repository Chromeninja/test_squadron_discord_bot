import pytest

from core.dependencies import _has_minimum_role


pytestmark = pytest.mark.contract


def test_event_coordinator_sits_between_staff_and_moderator() -> None:
    """Event coordinator should satisfy staff access but not moderator access."""
    assert _has_minimum_role("event_coordinator", "staff") is True
    assert _has_minimum_role("event_coordinator", "event_coordinator") is True
    assert _has_minimum_role("event_coordinator", "moderator") is False