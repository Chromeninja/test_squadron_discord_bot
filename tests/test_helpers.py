"""Compatibility helpers for older bot tests.

Prefer importing richer fakes from tests.factories for new tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from tests.factories.discord_factories import (
    FakeFollowup as _FactoryFakeFollowup,
    FakeResponse as _FactoryFakeResponse,
    FakeUser as _FactoryFakeUser,
)


class FakeUser(_FactoryFakeUser):
    """Backward-compatible fake user with the older constructor shape."""

    def __init__(self, user_id: int = 1, display_name: str = "User") -> None:
        super().__init__(
            user_id=user_id,
            name=display_name,
            display_name=display_name,
        )
        self.mention = f"@{display_name}"


class FakeResponse(_FactoryFakeResponse):
    """Re-export the shared fake response implementation."""


class FakeFollowup(_FactoryFakeFollowup):
    """Re-export the shared fake followup implementation."""

    async def send(self, *args: Any, **kwargs: Any) -> None:
        await super().send(*args, **kwargs)


class FakeInteraction:
    """Backward-compatible minimal interaction wrapper for legacy tests."""

    def __init__(self, user: FakeUser | None = None) -> None:
        self.user = user or FakeUser()
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.guild = SimpleNamespace(id=123, name="TestGuild")
        self.channel = None
        self.channel_id = None
        self.token = "fake_interaction_token"

        async def _edit(**kwargs: Any) -> None:
            return None

        self.message = SimpleNamespace(edit=_edit)
