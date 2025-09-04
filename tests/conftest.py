import asyncio
from types import SimpleNamespace
import os
import sys

import pytest
import pytest_asyncio

# Ensure project root is on sys.path for CI environments where Python might
# not automatically include it (e.g., some GitHub Actions runners invoking pytest differently).
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from helpers.database import Database  # noqa: E402


# Ensure pytest-asyncio uses a dedicated loop
@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def mock_bot():
    """A minimal bot-like object for cogs/views tests."""
    ns = SimpleNamespace()
    ns.guilds = []
    ns.uptime = "1h"
    ns.BOT_ADMIN_ROLE_IDS = []
    ns.LEAD_MODERATOR_ROLE_IDS = []

    def get_cog(name):
        return getattr(ns, f"_cog_{name}", None)

    ns.get_cog = get_cog
    return ns


@pytest_asyncio.fixture()
async def temp_db(tmp_path):
    """Initialize Database to a temporary file for isolation across tests."""
    orig_path = Database._db_path
    Database._initialized = False
    db_file = tmp_path / "test.db"
    await Database.initialize(str(db_file))
    yield str(db_file)
    # Restore
    Database._db_path = orig_path
    Database._initialized = False


class FakeUser:
    def __init__(self, user_id=1, display_name="User"):  # minimal interface
        self.id = user_id
        self.display_name = display_name
        self.mention = f"@{display_name}"

    # Used by some code paths that DM; keep as no-op/mocked in tests
    async def send(self, *args, **kwargs):
        return None


class FakeResponse:
    def __init__(self):
        self._is_done = False
        self.sent_modal = None

    def is_done(self):
        return self._is_done

    async def send_message(self, *args, **kwargs):
        self._is_done = True
        return None

    async def defer(self, *args, **kwargs):
        self._is_done = True
        return None

    async def send_modal(self, modal):
        self._is_done = True
        self.sent_modal = modal
        return None


class FakeFollowup:
    async def send(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user=None):
        self.user = user or FakeUser()
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.guild = SimpleNamespace(id=123, name="TestGuild")
        async def _edit(**kwargs):
            return None

        self.message = SimpleNamespace(edit=_edit)
