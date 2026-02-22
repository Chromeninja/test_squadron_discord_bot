"""
Unit tests for the SQLite-backed session store.

Covers CRUD operations, expiry semantics, upsert, cleanup, and lifecycle.
"""

import time

import pytest
import pytest_asyncio

from core import session_store
from core.session_store import SessionRow


@pytest_asyncio.fixture(autouse=True)
async def _fresh_store():
    """Ensure each test starts with a clean in-memory session store."""
    await session_store.initialize()  # defaults to :memory:
    yield
    await session_store.close()


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------

class TestSaveAndLoad:
    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self):
        now = time.time()
        await session_store.save("s1", {"user": "alice"}, now, now + 3600)

        row = await session_store.load("s1")
        assert row is not None
        assert isinstance(row, SessionRow)
        assert row.data == {"user": "alice"}
        assert row.created_at == pytest.approx(now, abs=0.01)
        assert row.expires_at == pytest.approx(now + 3600, abs=0.01)

    @pytest.mark.asyncio
    async def test_load_missing_returns_none(self):
        result = await session_store.load("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_overwrites_existing(self):
        now = time.time()
        await session_store.save("s1", {"v": 1}, now, now + 3600)
        await session_store.save("s1", {"v": 2}, now + 1, now + 7200)

        row = await session_store.load("s1")
        assert row is not None
        assert row.data == {"v": 2}
        assert row.created_at == pytest.approx(now + 1, abs=0.01)

    @pytest.mark.asyncio
    async def test_complex_data_roundtrip(self):
        """Nested dicts, lists, and special types survive JSON serialization."""
        data = {
            "user_id": "12345",
            "guilds": ["a", "b"],
            "nested": {"deep": True, "count": 42},
        }
        now = time.time()
        await session_store.save("complex", data, now, now + 3600)

        row = await session_store.load("complex")
        assert row is not None
        assert row.data == data


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

class TestExpiry:
    @pytest.mark.asyncio
    async def test_load_expired_returns_none(self):
        past = time.time() - 100
        await session_store.save("expired", {"x": 1}, past - 3600, past)

        result = await session_store.load("expired")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_not_yet_expired(self):
        future = time.time() + 9999
        await session_store.save("valid", {"x": 1}, time.time(), future)

        result = await session_store.load("valid")
        assert result is not None


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_existing(self):
        now = time.time()
        await session_store.save("del1", {"a": 1}, now, now + 3600)
        await session_store.delete("del1")

        assert await session_store.load("del1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_noop(self):
        # Should not raise
        await session_store.delete("no_such_session")


# ---------------------------------------------------------------------------
# Cleanup expired
# ---------------------------------------------------------------------------

class TestCleanupExpired:
    @pytest.mark.asyncio
    async def test_cleanup_removes_only_expired(self):
        now = time.time()
        # Two expired, one valid
        await session_store.save("old1", {}, now - 7200, now - 3600)
        await session_store.save("old2", {}, now - 7200, now - 1)
        await session_store.save("fresh", {}, now, now + 3600)

        removed = await session_store.cleanup_expired()
        assert removed == 2

        # fresh still loadable
        assert await session_store.load("fresh") is not None

    @pytest.mark.asyncio
    async def test_cleanup_with_nothing_expired(self):
        now = time.time()
        await session_store.save("a", {}, now, now + 3600)

        removed = await session_store.cleanup_expired()
        assert removed == 0


# ---------------------------------------------------------------------------
# Lifecycle (init / close / re-init)
# ---------------------------------------------------------------------------

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_double_initialize_is_idempotent(self):
        """Calling initialize() twice should not error or clear data."""
        now = time.time()
        await session_store.save("persist", {"k": 1}, now, now + 3600)

        await session_store.initialize()  # second call

        row = await session_store.load("persist")
        assert row is not None
        assert row.data == {"k": 1}

    @pytest.mark.asyncio
    async def test_close_and_reinitialize(self):
        """After close(), re-initialize gives a fresh store."""
        now = time.time()
        await session_store.save("gone", {}, now, now + 3600)

        await session_store.close()
        await session_store.initialize()

        # In-memory DB is gone after close
        assert await session_store.load("gone") is None
