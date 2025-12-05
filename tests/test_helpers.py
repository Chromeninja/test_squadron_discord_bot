"""Test helper classes for bot tests."""

from types import SimpleNamespace


class FakeUser:
    def __init__(self, user_id=1, display_name="User") -> None:  # minimal interface
        self.id = user_id
        self.display_name = display_name
        self.mention = f"@{display_name}"

    # Used by some code paths that DM; keep as no-op/mocked in tests
    async def send(self, *args, **kwargs) -> None:
        return None


class FakeResponse:
    def __init__(self) -> None:
        self._is_done = False
        self.sent_modal = None

    def is_done(self) -> bool:
        return self._is_done

    async def send_message(self, *args, **kwargs) -> None:
        self._is_done = True

    async def defer(self, *args, **kwargs) -> None:
        self._is_done = True

    async def send_modal(self, modal) -> None:
        self._is_done = True
        self.sent_modal = modal


class FakeFollowup:
    async def send(self, *args, **kwargs) -> None:
        return None


class FakeInteraction:
    def __init__(self, user=None) -> None:
        self.user = user or FakeUser()
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.guild = SimpleNamespace(id=123, name="TestGuild")

        async def _edit(**kwargs) -> None:
            return None

        self.message = SimpleNamespace(edit=_edit)
