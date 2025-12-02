import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Ensure project root is on sys.path for CI environments where
# Python might not automatically include it (e.g., some GitHub
# Actions runners invoking pytest differently).
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


# Ensure pytest-asyncio uses a dedicated loop
@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_bot() -> None:
    """A minimal bot-like object for cogs/views tests."""
    ns = SimpleNamespace()
    ns.guilds = []
    ns.uptime = "1h"

    def get_cog(name) -> None:
        return getattr(ns, f"_cog_{name}", None)

    ns.get_cog = get_cog
    return ns


@pytest_asyncio.fixture()
async def temp_db(tmp_path):
    """Initialize Database to a temporary file for isolation across tests."""
    # Save original state
    orig_path = Database._db_path
    orig_initialized = Database._initialized

    # Reset and initialize with temp database
    Database._initialized = False
    Database._db_path = None
    db_file = tmp_path / "test.db"
    await Database.initialize(str(db_file))

    # Verify initialization worked
    assert Database._initialized is True
    assert Database._db_path == str(db_file)

    yield str(db_file)

    # Restore original state completely
    Database._db_path = orig_path
    Database._initialized = orig_initialized


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

    def is_done(self) -> None:
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


@pytest.fixture
def mock_db_connection():
    """
    Patches Database.get_connection() to yield an async mock connection
    with helpers to set cursor.fetchone.return_value.

    Patches both the direct import path and the services.voice_service path
    to ensure compatibility with all test patterns.

    Returns a helper object with methods to configure the mock database responses.
    """

    class MockDBHelper:
        def __init__(self):
            self.mock_conn = AsyncMock()
            self.mock_cursor = AsyncMock()
            self.mock_conn.execute.return_value = self.mock_cursor

        def set_fetchone_result(self, result):
            """Set the result that cursor.fetchone() will return."""
            self.mock_cursor.fetchone.return_value = result

        def set_fetchall_result(self, result):
            """Set the result that cursor.fetchall() will return."""
            self.mock_cursor.fetchall.return_value = result

        def get_connection_calls(self):
            """Get all calls made to connection.execute()."""
            return self.mock_conn.execute.call_args_list

        def assert_query_called_with(self, query, params=None):
            """Assert a specific query was called with parameters."""
            calls = self.get_connection_calls()
            for call in calls:
                if call[0][0] == query and (params is None or call[0][1] == params):
                    return True
            raise AssertionError(f"Query not found: {query} with params {params}")

    helper = MockDBHelper()

    # Patch both possible import paths to ensure compatibility
    with (
        patch("services.voice_service.Database.get_connection") as mock_db1,
        patch("services.db.database.Database.get_connection") as mock_db2,
    ):
        mock_db1.return_value.__aenter__.return_value = helper.mock_conn
        mock_db2.return_value.__aenter__.return_value = helper.mock_conn
        yield helper


@pytest.fixture
def voice_service(mock_bot):
    """Create a VoiceService instance for testing."""
    config_service = MagicMock(spec=ConfigService)
    service = VoiceService(config_service, mock_bot)
    # Skip actual initialization to avoid database/network calls
    service._initialized = True
    return service
